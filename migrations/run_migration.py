#!/usr/bin/env python3
"""
Migration runner for Moeen AI multi-tenant foundation.

Usage:
    python migrations/run_migration.py

This script:
  1. Runs 001_multi_tenant_foundation.sql
  2. Seeds the default tenant's tenant_configs and assistant_configs
     from current environment variables (encrypted with Fernet).
  3. Verifies the migration completed successfully.

Safe to run multiple times (idempotent).
"""
import os
import sys
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import RealDictCursor

DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001'
MIGRATION_SQL_PATH = os.path.join(os.path.dirname(__file__), '001_multi_tenant_foundation.sql')


def get_connection():
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        raise RuntimeError('DATABASE_URL is not set')
    return psycopg2.connect(dsn)


def run_sql_file(conn, path: str):
    print(f"▶ Running {os.path.basename(path)}...")
    with open(path) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"✅ {os.path.basename(path)} completed")


def encrypt_value(value: str) -> str:
    """
    Encrypt a string value using Fernet symmetric encryption.
    Falls back to plaintext if crypto module unavailable (for dev environments).
    """
    if not value:
        return ''
    try:
        from crypto import encrypt
        return encrypt(value)
    except ImportError:
        # crypto.py not yet created — store plaintext temporarily
        print("  ⚠️  crypto.py not found — storing plaintext (update after crypto.py is created)")
        return value


def seed_default_tenant_configs(conn):
    """Populate tenant_configs and assistant_configs for the default tenant
    using values from the current environment."""
    print("▶ Seeding default tenant configs from environment...")

    # Collect env values (will be encrypted at rest)
    twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID', '')
    twilio_auth_token  = os.getenv('TWILIO_AUTH_TOKEN', '')
    twilio_number      = os.getenv('TWILIO_WHATSAPP_NUMBER', '')
    twilio_service_sid = os.getenv('TWILIO_SERVICE_SID', '')
    template_sid       = os.getenv('TEMPLATE_CONTENT_SID', '')
    sendgrid_key       = os.getenv('SENDGRID_API_KEY', '')
    sender_email       = os.getenv('SENDER_EMAIL', '')

    calendar_b64       = os.getenv('GOOGLE_CALENDAR_CREDENTIALS_B64', '')
    calendar_id        = os.getenv('GOOGLE_CALENDAR_ID', '')
    calendar_user      = os.getenv('GOOGLE_CALENDAR_USER', '')
    calendar_tz        = 'Asia/Qatar'  # current hardcoded default

    openai_key         = os.getenv('OPENAI_API_KEY', '')
    assistant_id       = os.getenv('ASSISTANT_ID', '')

    # Build calendar_credentials JSONB (decoded base64 → JSON)
    calendar_creds_json = None
    if calendar_b64:
        import base64
        try:
            decoded = base64.b64decode(calendar_b64).decode('utf-8')
            calendar_creds_json = json.loads(decoded)
        except Exception as e:
            print(f"  ⚠️  Could not decode calendar credentials: {e}")

    with conn.cursor() as cur:
        # Update tenant_configs for the default tenant
        cur.execute("""
            UPDATE tenant_configs SET
                twilio_account_sid      = %s,
                twilio_auth_token       = %s,
                twilio_whatsapp_number  = %s,
                twilio_service_sid      = %s,
                sendgrid_api_key        = %s,
                sender_email            = %s,
                sender_name             = %s,
                calendar_enabled        = %s,
                calendar_credentials    = %s,
                calendar_id             = %s,
                calendar_timezone       = %s,
                default_country_code    = %s,
                human_active_window_sec = %s,
                max_twilio_length       = %s,
                bulk_max_batch          = %s,
                bulk_daily_cap          = %s,
                bulk_msg_delay_sec      = %s,
                extra                   = %s,
                updated_at              = NOW()
            WHERE tenant_id = %s
        """, (
            encrypt_value(twilio_account_sid),
            encrypt_value(twilio_auth_token),
            twilio_number,
            twilio_service_sid or None,
            encrypt_value(sendgrid_key),
            sender_email,
            'Moeen AI',
            bool(calendar_b64),
            json.dumps(calendar_creds_json) if calendar_creds_json else None,
            calendar_id or None,
            calendar_tz if calendar_b64 else None,
            os.getenv('DEFAULT_COUNTRY_CODE', '974'),
            int(os.getenv('HUMAN_ACTIVE_WINDOW', 1800)),
            int(os.getenv('MAX_TWILIO_LENGTH', 1550)),
            int(os.getenv('BULK_MAX_BATCH', 500)),
            int(os.getenv('BULK_DAILY_CAP', 1000)),
            float(os.getenv('BULK_MSG_DELAY', 1.5)),
            json.dumps({
                'template_content_sid': template_sid,
                'calendar_user': calendar_user,
            }),
            DEFAULT_TENANT_ID,
        ))

        # Update assistant_configs for the default tenant
        cur.execute("""
            UPDATE assistant_configs SET
                openai_api_key         = %s,
                assistant_id           = %s,
                model                  = %s,
                provider               = %s,
                tools_enabled          = %s,
                sentiment_enabled      = %s,
                updated_at             = NOW()
            WHERE tenant_id = %s
        """, (
            encrypt_value(openai_key),
            assistant_id,
            'gpt-4o',
            'openai_assistants',
            json.dumps(['escalate_to_human', 'send_email', 'create_calendar_event',
                        'get_available_time_slots']),
            True,
            DEFAULT_TENANT_ID,
        ))

        # Also update tenants.brand_name from env if available
        cur.execute("""
            UPDATE tenants SET
                brand_name            = %s,
                brand_color_primary   = %s,
                brand_color_secondary = %s,
                timezone              = %s,
                updated_at            = NOW()
            WHERE id = %s
        """, (
            'Moeen AI',
            '#b00909',
            '#891565',
            'Asia/Qatar',
            DEFAULT_TENANT_ID,
        ))

    conn.commit()
    print("✅ Default tenant configs seeded")


def verify_migration(conn):
    print("▶ Verifying migration...")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        checks = [
            ("plans count",        "SELECT COUNT(*) AS n FROM plans"),
            ("tenants count",      "SELECT COUNT(*) AS n FROM tenants"),
            ("users count",        "SELECT COUNT(*) AS n FROM users"),
            ("messages with tid",  "SELECT COUNT(*) AS n FROM messages WHERE tenant_id IS NOT NULL"),
            ("threads with tid",   "SELECT COUNT(*) AS n FROM user_threads WHERE tenant_id IS NOT NULL"),
            ("tenant_configs",     "SELECT COUNT(*) AS n FROM tenant_configs"),
            ("assistant_configs",  "SELECT COUNT(*) AS n FROM assistant_configs"),
        ]
        for label, sql in checks:
            cur.execute(sql)
            row = cur.fetchone()
            print(f"  {label}: {row['n']}")

        # Verify the composite PK on user_threads
        cur.execute("""
            SELECT array_agg(a.attname ORDER BY a.attnum) AS pk_cols
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.conrelid = 'user_threads'::regclass AND c.contype = 'p'
            GROUP BY c.conname
        """)
        row = cur.fetchone()
        pk_cols = row['pk_cols'] if row else []
        if set(pk_cols) == {'tenant_id', 'user_id'}:
            print("  user_threads PK: ✅ composite (tenant_id, user_id)")
        else:
            print(f"  user_threads PK: ⚠️  {pk_cols} — expected (tenant_id, user_id)")

    print("✅ Migration verification complete")


def main():
    print("=" * 60)
    print("Moeen AI — Multi-Tenant Foundation Migration")
    print("=" * 60)

    conn = get_connection()
    try:
        run_sql_file(conn, MIGRATION_SQL_PATH)
        seed_default_tenant_configs(conn)
        verify_migration(conn)
        print("\n🎉 Migration completed successfully!")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
