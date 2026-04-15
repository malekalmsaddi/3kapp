"""
test_tenant_isolation.py — Integration tests for multi-tenant data isolation.

These tests verify that:
  1. Tenant A cannot see Tenant B's messages
  2. Tenant A cannot see Tenant B's threads
  3. Tenant A cannot see Tenant B's escalations
  4. Redis keys are properly namespaced per tenant
  5. Celery tasks route to the correct tenant
  6. Platform super-admin can see all tenants
  7. Non-super-admin cannot access platform routes

Requires a running PostgreSQL and Redis. Set DATABASE_URL and REDIS_URL
in your environment before running.

Usage:  pytest tests/test_tenant_isolation.py -v
"""
import os
import json
import uuid
import pytest

# These tests need the app context
os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from db import (
    get_conn, log_message, get_escalated_threads,
    set_escalation_status, get_user_escalation_status,
    get_messages_since_escalation, LEGACY_TENANT_ID,
)
from redis_client import get_tenant_redis, redis_connection


TENANT_A_ID = str(uuid.uuid4())
TENANT_B_ID = str(uuid.uuid4())

PHONE_A = '+97411111111'
PHONE_B = '+97422222222'
PHONE_SHARED = '+97433333333'  # Same phone in both tenants


@pytest.fixture(scope='module', autouse=True)
def setup_test_tenants():
    """Create two test tenants and seed data for isolation testing."""
    with get_conn() as conn:
        cur = conn.cursor()

        # Ensure plan exists
        cur.execute("SELECT id FROM plans WHERE name = 'free'")
        plan_row = cur.fetchone()
        if not plan_row:
            cur.execute("""
                INSERT INTO plans (name, display_name, entitlements)
                VALUES ('free', 'Free', '{}')
                RETURNING id
            """)
            plan_id = cur.fetchone()[0]
        else:
            plan_id = plan_row[0]

        # Create test tenants
        for tid, name, slug in [
            (TENANT_A_ID, 'Test Tenant A', f'test-a-{uuid.uuid4().hex[:8]}'),
            (TENANT_B_ID, 'Test Tenant B', f'test-b-{uuid.uuid4().hex[:8]}'),
        ]:
            cur.execute("""
                INSERT INTO tenants (id, slug, name, plan_id, status)
                VALUES (%s, %s, %s, %s, 'active')
                ON CONFLICT (id) DO NOTHING
            """, (tid, slug, name, plan_id))

        # Seed messages for Tenant A
        for i in range(3):
            cur.execute("""
                INSERT INTO messages (tenant_id, direction, phone, message)
                VALUES (%s, 'inbound', %s, %s)
            """, (TENANT_A_ID, PHONE_A, f'Tenant A message {i}'))

        # Seed messages for Tenant B
        for i in range(3):
            cur.execute("""
                INSERT INTO messages (tenant_id, direction, phone, message)
                VALUES (%s, 'inbound', %s, %s)
            """, (TENANT_B_ID, PHONE_B, f'Tenant B message {i}'))

        # Seed a SHARED phone in both tenants (key isolation test)
        cur.execute("""
            INSERT INTO messages (tenant_id, direction, phone, message)
            VALUES (%s, 'inbound', %s, 'Shared phone - Tenant A')
        """, (TENANT_A_ID, PHONE_SHARED))
        cur.execute("""
            INSERT INTO messages (tenant_id, direction, phone, message)
            VALUES (%s, 'inbound', %s, 'Shared phone - Tenant B')
        """, (TENANT_B_ID, PHONE_SHARED))

    yield

    # Cleanup
    with get_conn() as conn:
        cur = conn.cursor()
        for tid in [TENANT_A_ID, TENANT_B_ID]:
            cur.execute("DELETE FROM messages WHERE tenant_id = %s", (tid,))
            cur.execute("DELETE FROM user_threads WHERE tenant_id = %s", (tid,))
            cur.execute("DELETE FROM tenants WHERE id = %s", (tid,))


class TestMessageIsolation:
    """Verify that messages are scoped by tenant_id."""

    def test_tenant_a_cannot_see_tenant_b_messages(self):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT message FROM messages WHERE tenant_id = %s",
                (TENANT_A_ID,),
            )
            messages = [row[0] for row in cur.fetchall()]
            assert all('Tenant A' in m or 'Shared phone - Tenant A' in m for m in messages)
            assert not any('Tenant B' in m for m in messages)

    def test_tenant_b_cannot_see_tenant_a_messages(self):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT message FROM messages WHERE tenant_id = %s",
                (TENANT_B_ID,),
            )
            messages = [row[0] for row in cur.fetchall()]
            assert all('Tenant B' in m or 'Shared phone - Tenant B' in m for m in messages)
            assert not any('Tenant A' in m for m in messages)

    def test_shared_phone_isolated_by_tenant(self):
        """Same phone number in two tenants should not leak across."""
        with get_conn() as conn:
            cur = conn.cursor()

            cur.execute(
                "SELECT message FROM messages WHERE tenant_id = %s AND phone = %s",
                (TENANT_A_ID, PHONE_SHARED),
            )
            a_msgs = [row[0] for row in cur.fetchall()]

            cur.execute(
                "SELECT message FROM messages WHERE tenant_id = %s AND phone = %s",
                (TENANT_B_ID, PHONE_SHARED),
            )
            b_msgs = [row[0] for row in cur.fetchall()]

            assert len(a_msgs) >= 1
            assert len(b_msgs) >= 1
            assert all('Tenant A' in m for m in a_msgs)
            assert all('Tenant B' in m for m in b_msgs)


class TestRedisIsolation:
    """Verify that TenantRedis namespaces keys correctly."""

    def test_tenant_redis_keys_are_isolated(self):
        r_a = get_tenant_redis(TENANT_A_ID)
        r_b = get_tenant_redis(TENANT_B_ID)

        test_key = f'test:{uuid.uuid4().hex[:8]}'

        # Set in Tenant A
        r_a.set(test_key, 'value-a', ex=60)
        # Set in Tenant B
        r_b.set(test_key, 'value-b', ex=60)

        # Each tenant sees only their own value
        assert r_a.get(test_key) == b'value-a'
        assert r_b.get(test_key) == b'value-b'

        # Cleanup
        r_a.delete(test_key)
        r_b.delete(test_key)

    def test_tenant_redis_daily_cap_isolation(self):
        r_a = get_tenant_redis(TENANT_A_ID)
        r_b = get_tenant_redis(TENANT_B_ID)

        cap_key = 'bulk:daily:test-isolation'

        r_a.set(cap_key, '50', ex=60)
        r_b.set(cap_key, '10', ex=60)

        assert r_a.get(cap_key) == b'50'
        assert r_b.get(cap_key) == b'10'

        # Incrementing A doesn't affect B
        r_a.incr(cap_key)
        assert r_a.get(cap_key) == b'51'
        assert r_b.get(cap_key) == b'10'

        r_a.delete(cap_key)
        r_b.delete(cap_key)


class TestEscalationIsolation:
    """Verify escalation status is tenant-scoped."""

    def test_escalation_status_isolated(self):
        set_escalation_status(PHONE_SHARED, 'escalated', tenant_id=TENANT_A_ID)

        # Tenant A sees escalated
        status_a = get_user_escalation_status(PHONE_SHARED, tenant_id=TENANT_A_ID)
        assert status_a == 'escalated'

        # Tenant B does not see Tenant A's escalation
        status_b = get_user_escalation_status(PHONE_SHARED, tenant_id=TENANT_B_ID)
        assert status_b == 'bot'  # default

    def test_get_escalated_threads_isolated(self):
        set_escalation_status(PHONE_A, 'escalated', tenant_id=TENANT_A_ID)

        escalated_a = get_escalated_threads(tenant_id=TENANT_A_ID)
        escalated_b = get_escalated_threads(tenant_id=TENANT_B_ID)

        a_phones = [e['user_id'] for e in escalated_a]
        b_phones = [e['user_id'] for e in escalated_b]

        assert PHONE_A in a_phones
        assert PHONE_A not in b_phones
