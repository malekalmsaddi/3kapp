"""
db.py — PostgreSQL connection pool + all database query functions.

All query functions accept tenant_id as their first argument.
During Phase 1 the default value is LEGACY_TENANT_ID so existing call sites
continue to work unchanged.  Once all callers are updated (Phase 2+) the
default will be removed to enforce explicit tenant scoping.
"""
import os
import time
import threading
import json
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from psycopg2 import OperationalError, InterfaceError
from contextlib import contextmanager
from dotenv import load_dotenv
from logati import logger

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# The UUID of the default (legacy/migrated) tenant.
# All pre-migration data belongs to this tenant.
# ─────────────────────────────────────────────────────────────────────────────
LEGACY_TENANT_ID = '00000000-0000-0000-0000-000000000001'

# ─────────────────────────────────────────────────────────────────────────────
# Connection pool configuration
# ─────────────────────────────────────────────────────────────────────────────
dsn    = os.getenv('DATABASE_URL')
dsn_ro = os.getenv('DATABASE_RO_URL', dsn)

if not dsn:
    logger.warning('⚠️ DATABASE_URL is missing; database features are disabled.')

POOL_CONFIG = {
    'minconn': 5,
    'maxconn': 20,
    'max_retries': 3,
    'retry_delay': 2,
    'connection_timeout': 30,
    'max_lifetime': 3600,
}


class HealthyConnectionPool(ThreadedConnectionPool):
    """Connection pool with health checks and automatic connection recycling."""

    def __init__(self, *args, **kwargs):
        self.max_retries  = kwargs.pop('max_retries', 3)
        self.retry_delay  = kwargs.pop('retry_delay', 2)
        self.max_lifetime = kwargs.pop('max_lifetime', 3600)
        super().__init__(*args, **kwargs)

    def _create_connection(self):
        conn = psycopg2.connect(dsn=dsn)
        self._validate_connection(conn)
        with _conn_timestamps_lock:
            conn_timestamps[id(conn)] = time.time()
        return conn

    def _validate_connection(self, conn):
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT 1 AS ok')
                row = cur.fetchone()
                if not isinstance(row, dict) or row.get('ok') != 1:
                    raise Exception('Database validation query failed')
        except (OperationalError, InterfaceError) as e:
            logger.error(f'Connection validation failed: {e}')
            conn.close()
            raise


conn_timestamps: dict = {}
_conn_timestamps_lock = threading.Lock()
_pool    = None
_pool_ro = None


def _init_pool(url: str, label: str = 'primary') -> HealthyConnectionPool:
    for attempt in range(3):
        try:
            return HealthyConnectionPool(
                minconn=POOL_CONFIG['minconn'],
                maxconn=POOL_CONFIG['maxconn'],
                max_retries=POOL_CONFIG['max_retries'],
                retry_delay=POOL_CONFIG['retry_delay'],
                max_lifetime=POOL_CONFIG['max_lifetime'],
                dsn=url,
            )
        except Exception as e:
            logger.warning(f'Attempt {attempt+1}/3: Failed to init {label} DB pool: {e}')
            time.sleep(2)
    raise RuntimeError(f'❌ Failed to initialize {label} DB pool after retries.')


def get_pool() -> HealthyConnectionPool:
    global _pool
    if dsn is None:
        raise RuntimeError('DATABASE_URL is not configured')
    if _pool is None:
        _pool = _init_pool(dsn, 'primary')
    return _pool


def get_pool_ro() -> HealthyConnectionPool:
    global _pool_ro
    if dsn_ro is None:
        raise RuntimeError('DATABASE_URL is not configured')
    if _pool_ro is None:
        _pool_ro = _init_pool(dsn_ro, 'replica')
    return _pool_ro


@contextmanager
def _conn_from(pool_fn):
    conn = None
    for attempt in range(3):
        try:
            pool = pool_fn()
            conn = pool.getconn()
            conn_id = id(conn)
            with _conn_timestamps_lock:
                created_at = conn_timestamps.get(conn_id, 0)
            if (time.time() - created_at) > POOL_CONFIG['max_lifetime']:
                logger.info('♻️ Recycling aged connection')
                with _conn_timestamps_lock:
                    conn_timestamps.pop(conn_id, None)
                pool.putconn(conn, close=True)
                conn = pool.getconn()
                conn_id = id(conn)
                with _conn_timestamps_lock:
                    conn_timestamps[conn_id] = time.time()
            pool._validate_connection(conn)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                pool.putconn(conn)
            break
        except Exception as e:
            logger.warning(f'⚠️ Connection attempt {attempt} failed: {e}')
            if conn:
                try:
                    pool_fn().putconn(conn, close=True)
                except Exception:
                    pass
                conn = None
            if attempt == 2:
                raise


@contextmanager
def get_conn():
    """Read-write connection from the primary pool."""
    with _conn_from(get_pool) as conn:
        yield conn


@contextmanager
def get_ro_conn():
    """Read-only connection from the replica (falls back to primary)."""
    with _conn_from(get_pool_ro) as conn:
        yield conn


# ─────────────────────────────────────────────────────────────────────────────
# Schema initialisation
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    """Create the legacy single-tenant schema if it doesn't exist yet.

    The full multi-tenant schema is applied separately via
    migrations/run_migration.py.  This function keeps backward compatibility
    for local dev environments that haven't run the migration yet.
    """
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id        BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        direction VARCHAR(10) NOT NULL
                                  CHECK (direction IN ('inbound','outbound','queued')),
                        phone     VARCHAR(20) NOT NULL,
                        message   TEXT NOT NULL,
                        status    VARCHAR(20) CHECK (status IN ('sent','failed','delivered','read')),
                        CONSTRAINT valid_phone CHECK (phone ~ '^\\+[1-9]\\d{1,14}$')
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_phone_timestamp
                    ON messages (phone, timestamp DESC);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                    ON messages (timestamp DESC);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_threads (
                        user_id     VARCHAR(255) PRIMARY KEY,
                        thread_id   VARCHAR(255) NOT NULL,
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_accessed TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_threads_last_accessed
                    ON user_threads (last_accessed);
                """)
                cur.execute("""
                    ALTER TABLE messages
                    ADD COLUMN IF NOT EXISTS sentiment VARCHAR(10)
                    CHECK (sentiment IN ('positive','neutral','negative'));
                """)
                cur.execute("""
                    ALTER TABLE user_threads
                    ADD COLUMN IF NOT EXISTS escalation_status VARCHAR(20)
                    NOT NULL DEFAULT 'bot'
                    CHECK (escalation_status IN ('bot','escalated','resolved'));
                """)
                cur.execute("""
                    ALTER TABLE user_threads
                    ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ;
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        username      VARCHAR(255) PRIMARY KEY,
                        password_hash VARCHAR(255) NOT NULL,
                        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
        logger.info('🎉 Database schema initialized successfully')
    except Exception as e:
        logger.error(f'🚨 Could not initialize the database schema: {e}')
        raise RuntimeError('❌ Failed to set up the database.') from e


# ─────────────────────────────────────────────────────────────────────────────
# Message functions
# ─────────────────────────────────────────────────────────────────────────────

def log_message(
    timestamp,
    direction: str,
    phone: str,
    message: str,
    status: str | None = None,
    tenant_id: str = LEGACY_TENANT_ID,
) -> int | None:
    """Insert a message row and return its id."""
    if not isinstance(message, str):
        raise ValueError('⚠️ Message must be a plain text string.')
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Support both old schema (no tenant_id) and new schema
                try:
                    cur.execute(
                        'INSERT INTO messages (tenant_id, timestamp, direction, phone, message, status) '
                        'VALUES (%s, %s, %s, %s, %s, %s) RETURNING id',
                        (tenant_id, timestamp, direction, phone, message, status),
                    )
                except psycopg2.errors.UndefinedColumn:
                    # Migration not run yet — fall back to old schema
                    conn.rollback()
                    cur.execute(
                        'INSERT INTO messages (timestamp, direction, phone, message, status) '
                        'VALUES (%s, %s, %s, %s, %s) RETURNING id',
                        (timestamp, direction, phone, message, status),
                    )
                row = cur.fetchone()
                return row['id'] if row else None
    except Exception as e:
        logger.error(f'📭 Failed to save message: {e}')
        raise


def update_message_sentiment(
    phone: str,
    message: str,
    sentiment: str,
    tenant_id: str = LEGACY_TENANT_ID,
) -> None:
    """Update sentiment on the most recent inbound message for this phone+text."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        UPDATE messages SET sentiment = %s
                        WHERE id = (
                            SELECT id FROM messages
                            WHERE tenant_id = %s AND phone = %s
                              AND direction = 'inbound' AND message = %s
                            ORDER BY timestamp DESC LIMIT 1
                        )
                        """,
                        (sentiment, tenant_id, phone, message),
                    )
                except psycopg2.errors.UndefinedColumn:
                    conn.rollback()
                    cur.execute(
                        """
                        UPDATE messages SET sentiment = %s
                        WHERE id = (
                            SELECT id FROM messages
                            WHERE phone = %s AND direction = 'inbound' AND message = %s
                            ORDER BY timestamp DESC LIMIT 1
                        )
                        """,
                        (sentiment, phone, message),
                    )
    except Exception as e:
        logger.error(f'Failed to update message sentiment for {phone}: {e}')


# ─────────────────────────────────────────────────────────────────────────────
# Thread / escalation functions
# ─────────────────────────────────────────────────────────────────────────────

def set_escalation_status(
    user_id: str,
    status: str,
    tenant_id: str = LEGACY_TENANT_ID,
) -> None:
    """Upsert escalation_status for a user thread."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO user_threads (tenant_id, user_id, thread_id,
                                                  escalation_status, escalated_at)
                        VALUES (
                            %s, %s, 'pending', %s,
                            CASE WHEN %s = 'escalated' THEN NOW() ELSE NULL END
                        )
                        ON CONFLICT (tenant_id, user_id) DO UPDATE
                        SET escalation_status = EXCLUDED.escalation_status,
                            escalated_at = CASE
                                WHEN EXCLUDED.escalation_status = 'escalated' THEN NOW()
                                ELSE user_threads.escalated_at
                            END,
                            updated_at = NOW()
                        """,
                        (tenant_id, user_id, status, status),
                    )
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    # Fall back to old schema ON CONFLICT (user_id)
                    cur.execute(
                        """
                        INSERT INTO user_threads (user_id, thread_id, escalation_status, escalated_at)
                        VALUES (
                            %s, 'pending', %s,
                            CASE WHEN %s = 'escalated' THEN NOW() ELSE NULL END
                        )
                        ON CONFLICT (user_id) DO UPDATE
                        SET escalation_status = EXCLUDED.escalation_status,
                            escalated_at = CASE
                                WHEN EXCLUDED.escalation_status = 'escalated' THEN NOW()
                                ELSE user_threads.escalated_at
                            END,
                            updated_at = NOW()
                        """,
                        (user_id, status, status),
                    )
    except Exception as e:
        logger.error(f'Failed to set escalation status for {user_id}: {e}')


def get_escalated_threads(tenant_id: str = LEGACY_TENANT_ID) -> list:
    """Return escalated conversations for this tenant, newest first."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(
                        """
                        SELECT ut.user_id, ut.thread_id, ut.escalated_at,
                               m.message  AS last_message,
                               m.timestamp AS last_msg_time
                        FROM user_threads ut
                        LEFT JOIN LATERAL (
                            SELECT message, timestamp FROM messages
                            WHERE tenant_id = %s AND phone = ut.user_id
                            ORDER BY timestamp DESC LIMIT 1
                        ) m ON true
                        WHERE ut.tenant_id = %s AND ut.escalation_status = 'escalated'
                        ORDER BY ut.escalated_at DESC
                        """,
                        (tenant_id, tenant_id),
                    )
                except psycopg2.errors.UndefinedColumn:
                    conn.rollback()
                    cur.execute(
                        """
                        SELECT ut.user_id, ut.thread_id, ut.escalated_at,
                               m.message AS last_message, m.timestamp AS last_msg_time
                        FROM user_threads ut
                        LEFT JOIN LATERAL (
                            SELECT message, timestamp FROM messages
                            WHERE phone = ut.user_id
                            ORDER BY timestamp DESC LIMIT 1
                        ) m ON true
                        WHERE ut.escalation_status = 'escalated'
                        ORDER BY ut.escalated_at DESC
                        """
                    )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f'Failed to fetch escalated threads: {e}')
        return []


def get_messages_since_escalation(
    user_id: str,
    tenant_id: str = LEGACY_TENANT_ID,
) -> list:
    """Return inbound messages sent after this user's escalation timestamp."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT m.message
                        FROM messages m
                        JOIN user_threads ut
                          ON ut.tenant_id = %s AND ut.user_id = m.phone
                        WHERE m.tenant_id = %s AND m.phone = %s
                          AND m.direction = 'inbound'
                          AND ut.escalated_at IS NOT NULL
                          AND m.timestamp >= ut.escalated_at
                        ORDER BY m.timestamp ASC
                        """,
                        (tenant_id, tenant_id, user_id),
                    )
                except psycopg2.errors.UndefinedColumn:
                    conn.rollback()
                    cur.execute(
                        """
                        SELECT m.message
                        FROM messages m
                        JOIN user_threads ut ON ut.user_id = m.phone
                        WHERE m.phone = %s
                          AND m.direction = 'inbound'
                          AND ut.escalated_at IS NOT NULL
                          AND m.timestamp >= ut.escalated_at
                        ORDER BY m.timestamp ASC
                        """,
                        (user_id,),
                    )
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f'Failed to get messages since escalation for {user_id}: {e}')
        return []


def get_user_escalation_status(
    user_id: str,
    tenant_id: str = LEGACY_TENANT_ID,
) -> str:
    """Return escalation_status ('bot', 'escalated', 'resolved')."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT escalation_status FROM user_threads
                        WHERE tenant_id = %s AND user_id = %s
                        """,
                        (tenant_id, user_id),
                    )
                except psycopg2.errors.UndefinedColumn:
                    conn.rollback()
                    cur.execute(
                        'SELECT escalation_status FROM user_threads WHERE user_id = %s',
                        (user_id,),
                    )
                row = cur.fetchone()
                return row[0] if row else 'bot'
    except Exception as e:
        logger.error(f'Failed to get escalation status for {user_id}: {e}')
        return 'bot'


def get_or_create_thread_id(
    user_id: str,
    tenant_id: str = LEGACY_TENANT_ID,
    openai_api_key: str | None = None,
) -> str:
    """Get or create an OpenAI thread for this (tenant, user) pair."""
    from openai import OpenAI
    api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
    client_sync = OpenAI(api_key=api_key)

    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(
                        """
                        SELECT thread_id FROM user_threads
                        WHERE tenant_id = %s AND user_id = %s
                        FOR UPDATE
                        """,
                        (tenant_id, user_id),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute(
                            """
                            UPDATE user_threads SET last_accessed = NOW()
                            WHERE tenant_id = %s AND user_id = %s
                            """,
                            (tenant_id, user_id),
                        )
                        return row['thread_id']
                    thread = client_sync.beta.threads.create(
                        extra_headers={'OpenAI-Beta': 'assistants=v2'}
                    )
                    cur.execute(
                        """
                        INSERT INTO user_threads (tenant_id, user_id, thread_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (tenant_id, user_id) DO UPDATE
                            SET updated_at = NOW(), last_accessed = NOW()
                        RETURNING thread_id
                        """,
                        (tenant_id, user_id, thread.id),
                    )
                    result = cur.fetchone()
                    return result['thread_id']
                except psycopg2.errors.UndefinedColumn:
                    # Fall back to old single-tenant schema
                    conn.rollback()
                    cur.execute(
                        'SELECT thread_id FROM user_threads WHERE user_id = %s FOR UPDATE',
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute(
                            'UPDATE user_threads SET last_accessed = NOW() WHERE user_id = %s',
                            (user_id,),
                        )
                        return row['thread_id']
                    thread = client_sync.beta.threads.create(
                        extra_headers={'OpenAI-Beta': 'assistants=v2'}
                    )
                    cur.execute(
                        """
                        INSERT INTO user_threads (user_id, thread_id)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id) DO UPDATE
                            SET updated_at = NOW(), last_accessed = NOW()
                        RETURNING thread_id
                        """,
                        (user_id, thread.id),
                    )
                    result = cur.fetchone()
                    return result['thread_id']
    except Exception as e:
        logger.error(f'⚠️ Unable to manage user thread record: {e}')
        raise RuntimeError('❌ Failed to manage user thread record') from e


# ─────────────────────────────────────────────────────────────────────────────
# Auth / user functions
# ─────────────────────────────────────────────────────────────────────────────

def get_admin(username: str) -> dict | None:
    """Legacy: fetch admin by username.  Tries users table first, then admins."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Try new users table first
                try:
                    cur.execute(
                        """
                        SELECT id, email AS username, password_hash, role,
                               tenant_id, email_verified, is_active
                        FROM users WHERE email = %s
                        """,
                        (username,),
                    )
                    row = cur.fetchone()
                    if row:
                        return dict(row)
                except psycopg2.errors.UndefinedTable:
                    pass
                # Fall back to legacy admins table
                cur.execute(
                    'SELECT username, password_hash FROM admins WHERE username = %s',
                    (username,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch admin '{username}': {e}")
        return None


def get_user_by_email(email: str) -> dict | None:
    """Fetch a user record by email (searches across all tenants)."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT u.id, u.email, u.password_hash, u.role, u.tenant_id,
                           u.email_verified, u.is_active, u.full_name, u.last_login_at,
                           t.slug AS tenant_slug, t.brand_name, t.status AS tenant_status
                    FROM users u
                    LEFT JOIN tenants t ON t.id = u.tenant_id
                    WHERE u.email = %s
                    """,
                    (email.lower().strip(),),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch user by email '{email}': {e}")
        return None


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user record by UUID."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT u.*, t.slug AS tenant_slug, t.brand_name
                    FROM users u
                    LEFT JOIN tenants t ON t.id = u.tenant_id
                    WHERE u.id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch user by id '{user_id}': {e}")
        return None


def update_user_last_login(user_id: str) -> None:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE users SET last_login_at = NOW() WHERE id = %s',
                    (user_id,),
                )
    except Exception as e:
        logger.error(f'Failed to update last_login for {user_id}: {e}')


# ─────────────────────────────────────────────────────────────────────────────
# Tenant + config functions
# ─────────────────────────────────────────────────────────────────────────────

def get_tenant_by_slug(slug: str) -> dict | None:
    """Fetch a tenant record by slug."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.*, p.entitlements AS plan_entitlements, p.name AS plan_name
                    FROM tenants t
                    JOIN plans p ON p.id = t.plan_id
                    WHERE t.slug = %s AND t.deleted_at IS NULL
                    """,
                    (slug,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch tenant by slug '{slug}': {e}")
        return None


def get_tenant_by_id(tenant_id: str) -> dict | None:
    """Fetch a tenant record by UUID."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.*, p.entitlements AS plan_entitlements, p.name AS plan_name
                    FROM tenants t
                    JOIN plans p ON p.id = t.plan_id
                    WHERE t.id = %s AND t.deleted_at IS NULL
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch tenant '{tenant_id}': {e}")
        return None


def get_tenant_config(tenant_id: str) -> dict | None:
    """Fetch the tenant_configs row for this tenant."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    'SELECT * FROM tenant_configs WHERE tenant_id = %s',
                    (tenant_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch tenant config for '{tenant_id}': {e}")
        return None


def get_assistant_config(tenant_id: str) -> dict | None:
    """Fetch the assistant_configs row for this tenant."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    'SELECT * FROM assistant_configs WHERE tenant_id = %s',
                    (tenant_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch assistant config for '{tenant_id}': {e}")
        return None


def create_tenant(
    slug: str,
    name: str,
    plan_name: str,
    owner_email: str,
    owner_password_hash: str,
    timezone: str = 'UTC',
) -> dict:
    """Create a new tenant + owner user + empty config rows."""
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get plan id
                cur.execute('SELECT id FROM plans WHERE name = %s', (plan_name,))
                plan_row = cur.fetchone()
                if not plan_row:
                    raise ValueError(f"Plan '{plan_name}' not found")
                plan_id = plan_row['id']

                # Create tenant
                cur.execute(
                    """
                    INSERT INTO tenants (slug, name, plan_id, status, timezone)
                    VALUES (%s, %s, %s, 'trialing', %s)
                    RETURNING *
                    """,
                    (slug, name, plan_id, timezone),
                )
                tenant = dict(cur.fetchone())

                # Create owner user
                cur.execute(
                    """
                    INSERT INTO users (tenant_id, email, password_hash, role,
                                       email_verified, is_active)
                    VALUES (%s, %s, %s, 'tenant_admin', FALSE, TRUE)
                    RETURNING *
                    """,
                    (tenant['id'], owner_email.lower().strip(), owner_password_hash),
                )
                user = dict(cur.fetchone())

                # Create empty config rows
                cur.execute(
                    'INSERT INTO tenant_configs (tenant_id) VALUES (%s) ON CONFLICT DO NOTHING',
                    (tenant['id'],),
                )
                cur.execute(
                    """
                    INSERT INTO assistant_configs (tenant_id, openai_api_key, assistant_id)
                    VALUES (%s, '', '') ON CONFLICT DO NOTHING
                    """,
                    (tenant['id'],),
                )
                cur.execute(
                    """
                    INSERT INTO onboarding_state (tenant_id) VALUES (%s) ON CONFLICT DO NOTHING
                    """,
                    (tenant['id'],),
                )

                return {'tenant': tenant, 'user': user}
    except Exception as e:
        logger.error(f'Failed to create tenant: {e}')
        raise


def get_all_tenants() -> list:
    """Return all active tenants (platform super-admin use)."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.*, p.name AS plan_name, p.display_name AS plan_display_name,
                           COUNT(DISTINCT u.id) AS user_count
                    FROM tenants t
                    JOIN plans p ON p.id = t.plan_id
                    LEFT JOIN users u ON u.tenant_id = t.id
                    WHERE t.deleted_at IS NULL
                    GROUP BY t.id, p.name, p.display_name
                    ORDER BY t.created_at DESC
                    """
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f'Failed to fetch all tenants: {e}')
        return []


def update_tenant_config(tenant_id: str, updates: dict) -> None:
    """Update tenant_configs fields for a tenant."""
    if not updates:
        return
    set_clauses = ', '.join(f'{k} = %s' for k in updates)
    values = list(updates.values()) + [tenant_id]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'UPDATE tenant_configs SET {set_clauses}, updated_at = NOW() WHERE tenant_id = %s',
                    values,
                )
    except Exception as e:
        logger.error(f'Failed to update tenant config for {tenant_id}: {e}')
        raise


def update_assistant_config(tenant_id: str, updates: dict) -> None:
    """Update assistant_configs fields for a tenant."""
    if not updates:
        return
    set_clauses = ', '.join(f'{k} = %s' for k in updates)
    values = list(updates.values()) + [tenant_id]
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'UPDATE assistant_configs SET {set_clauses}, updated_at = NOW() WHERE tenant_id = %s',
                    values,
                )
    except Exception as e:
        logger.error(f'Failed to update assistant config for {tenant_id}: {e}')
        raise


def update_onboarding_step(tenant_id: str, step: str, completed_steps: list) -> None:
    """Update onboarding progress for a tenant."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO onboarding_state (tenant_id, current_step, completed_steps)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tenant_id) DO UPDATE
                    SET current_step = EXCLUDED.current_step,
                        completed_steps = EXCLUDED.completed_steps,
                        updated_at = NOW()
                    """,
                    (tenant_id, step, json.dumps(completed_steps)),
                )
    except Exception as e:
        logger.error(f'Failed to update onboarding step for {tenant_id}: {e}')
        raise


def complete_onboarding(tenant_id: str) -> None:
    """Mark onboarding as complete."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE onboarding_state
                    SET completed_at = NOW(), updated_at = NOW()
                    WHERE tenant_id = %s
                    """,
                    (tenant_id,),
                )
    except Exception as e:
        logger.error(f'Failed to complete onboarding for {tenant_id}: {e}')
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Audit + usage logging
# ─────────────────────────────────────────────────────────────────────────────

def log_audit(
    tenant_id: str | None,
    actor_user_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    payload: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Write an audit log entry."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_logs
                        (tenant_id, actor_user_id, action, resource_type,
                         resource_id, payload, ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::inet, %s)
                    """,
                    (
                        tenant_id, actor_user_id, action, resource_type,
                        resource_id,
                        json.dumps(payload) if payload else None,
                        ip_address, user_agent,
                    ),
                )
    except Exception as e:
        # Audit log failures must never crash the main flow
        logger.error(f'Failed to write audit log [{action}]: {e}')


def log_usage_event(
    tenant_id: str,
    event_type: str,
    quantity: int = 1,
    metadata: dict | None = None,
) -> None:
    """Record a metered usage event."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usage_events (tenant_id, event_type, quantity, metadata)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        tenant_id, event_type, quantity,
                        json.dumps(metadata) if metadata else None,
                    ),
                )
    except Exception as e:
        logger.error(f'Failed to log usage event [{event_type}] for {tenant_id}: {e}')


# ─────────────────────────────────────────────────────────────────────────────
# Observability
# ─────────────────────────────────────────────────────────────────────────────

def connection_health_check() -> dict:
    pool = get_pool()
    idle_conns   = list(pool._pool)
    active_conns = list(pool._used.values())
    all_conns    = idle_conns + active_conns
    status = {
        'total_connections': len(all_conns),
        'available': len(idle_conns),
        'active': len(active_conns),
        'invalid': 0,
        'avg_age_seconds': 0,
        'message_count': 0,
    }
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT COUNT(*) FROM messages')
                status['message_count'] = cur.fetchone()['count']
        valid_conns = []
        now = time.time()
        for conn in all_conns:
            try:
                pool._validate_connection(conn)
                valid_conns.append(conn)
            except Exception:
                status['invalid'] += 1
        with _conn_timestamps_lock:
            ages = [(now - conn_timestamps.get(id(c), now)) for c in valid_conns]
        status['avg_age_seconds'] = sum(ages) / len(ages) if ages else 0
        return status
    except Exception as e:
        logger.error(f'⚠️ Database health check failed: {e}')
        status['error'] = str(e)
        return status


def close_pool() -> bool:
    try:
        get_pool().closeall()
        logger.info('Connection pool closed successfully')
        return True
    except Exception as e:
        logger.error(f'❌ Could not close the connection pool: {e}')
        return False
