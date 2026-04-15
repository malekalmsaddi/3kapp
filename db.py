import os
import time
import threading
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from psycopg2 import OperationalError, InterfaceError
from contextlib import contextmanager
from dotenv import load_dotenv
from openai import OpenAI
from logati import logger

# Load environment variables
load_dotenv()


# Database DSN (PostgreSQL connection URL)
dsn = os.getenv("DATABASE_URL")
if not dsn:
    logger.warning("⚠️ DATABASE_URL is missing; database features are disabled.")

# Read-only replica DSN (falls back to primary if not set)
dsn_ro = os.getenv("DATABASE_RO_URL", dsn)

# Connection pool parameters
POOL_CONFIG = {
    'minconn': 5,
    'maxconn': 20,
    'max_retries': 3,
    'retry_delay': 2,
    'connection_timeout': 30,
    'max_lifetime': 3600,
}

class HealthyConnectionPool(ThreadedConnectionPool):
    """Custom connection pool with health checks and auto-recycling"""
    def __init__(self, *args, **kwargs):
        self.max_retries = kwargs.pop('max_retries', 3)
        self.retry_delay = kwargs.pop('retry_delay', 2)
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
                cur.execute("SELECT 1 AS ok")
                row = cur.fetchone()
                if not isinstance(row, dict):
                    raise TypeError(f"Expected dict row, got {type(row)}")
                if row.get("ok") != 1:
                    raise Exception("Database validation query failed")
        except (OperationalError, InterfaceError) as e:
            logger.error(f"Connection validation failed: {e}")
            conn.close()
            raise

conn_timestamps: dict = {}
_conn_timestamps_lock = threading.Lock()
_pool = None
_pool_ro = None

def _init_pool(url, label="primary"):
    for attempt in range(3):
        try:
            pool = HealthyConnectionPool(
                minconn=POOL_CONFIG['minconn'],
                maxconn=POOL_CONFIG['maxconn'],
                max_retries=POOL_CONFIG['max_retries'],
                retry_delay=POOL_CONFIG['retry_delay'],
                max_lifetime=POOL_CONFIG['max_lifetime'],
                dsn=url
            )
            return pool
        except Exception as e:
            logger.warning(f"Attempt {attempt+1}/3: Failed to init {label} DB pool: {e}")
            time.sleep(2)
    raise RuntimeError(f"❌ Failed to initialize {label} DB pool after retries.")

def get_pool():
    global _pool
    if dsn is None:
        raise RuntimeError("DATABASE_URL is not configured")
    if _pool is None:
        _pool = _init_pool(dsn, "primary")
    return _pool

def get_pool_ro():
    global _pool_ro
    if dsn_ro is None:
        raise RuntimeError("DATABASE_URL is not configured")
    if _pool_ro is None:
        _pool_ro = _init_pool(dsn_ro, "replica")
    return _pool_ro

@contextmanager
def _conn_from(pool_fn):
    """Shared connection checkout logic for both primary and replica pools."""
    conn = None
    for attempt in range(3):
        try:
            pool = pool_fn()
            conn = pool.getconn()
            conn_id = id(conn)
            with _conn_timestamps_lock:
                created_at = conn_timestamps.get(conn_id, 0)
            if (time.time() - created_at) > POOL_CONFIG['max_lifetime']:
                logger.info("♻️ Recycling aged connection")
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
            logger.warning(f"⚠️ Connection attempt {attempt} failed: {e}")
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
    """Read-write connection from the primary."""
    with _conn_from(get_pool) as conn:
        yield conn

@contextmanager
def get_ro_conn():
    """Read-only connection from the replica (falls back to primary if DATABASE_RO_URL is unset)."""
    with _conn_from(get_pool_ro) as conn:
        yield conn

def init_db():
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        direction VARCHAR(10) NOT NULL CHECK (direction IN ('inbound','outbound','queued')),
                        phone VARCHAR(20) NOT NULL,
                        message TEXT NOT NULL,
                        status VARCHAR(20) CHECK (status IN ('sent','failed','delivered','read')),
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
                        user_id VARCHAR(255) PRIMARY KEY,
                        thread_id VARCHAR(255) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_accessed TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_threads_last_accessed
                    ON user_threads (last_accessed);
                """)
                # Sentiment + escalation columns (safe to run on existing DBs)
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
                        username VARCHAR(255) PRIMARY KEY,
                        password_hash VARCHAR(255) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
        logger.info("🎉 Database schema initialized successfully")
    except Exception as e:
        logger.error(f"🚨 Could not initialize the database schema: {e}")
        raise RuntimeError("❌ Failed to set up the database. Please review your configuration.") from e

def log_message(timestamp, direction, phone, message, status=None):
    if not isinstance(message, str):
        raise ValueError("⚠️ Message must be a plain text string. Received a different type.")
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO messages (timestamp, direction, phone, message, status) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (timestamp, direction, phone, message, status)
                )
                row = cur.fetchone()
                return row["id"] if row else None
    except Exception as e:
        logger.error(f"📭 Failed to save message to database: {e}")
        raise

def connection_health_check():
    pool = get_pool()
    # _pool = idle connections (list), _used = in-use connections (dict key->conn)
    idle_conns = list(pool._pool)
    active_conns = list(pool._used.values())
    all_conns = idle_conns + active_conns
    status = {
        'total_connections': len(all_conns),
        'available': len(idle_conns),
        'active': len(active_conns),
        'invalid': 0,
        'avg_age_seconds': 0,
        'message_count': 0
    }
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) FROM messages")
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
            ages = [(now - conn_timestamps.get(id(conn), now)) for conn in valid_conns]
        status['avg_age_seconds'] = sum(ages) / len(ages) if ages else 0
        return status
    except Exception as e:
        logger.error(f"⚠️ Database health check failed: {e}")
        status['error'] = str(e)
        return status

def close_pool():
    try:
        get_pool().closeall()
        logger.info("Connection pool closed successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Could not close the connection pool properly: {e}")
        return False

def update_message_sentiment(phone: str, message: str, sentiment: str) -> None:
    """Update the sentiment column on the most recent inbound message for this phone + text."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE messages SET sentiment = %s
                    WHERE id = (
                        SELECT id FROM messages
                        WHERE phone = %s AND direction = 'inbound' AND message = %s
                        ORDER BY timestamp DESC
                        LIMIT 1
                    )
                    """,
                    (sentiment, phone, message),
                )
    except Exception as e:
        logger.error(f"Failed to update message sentiment for {phone}: {e}")


def set_escalation_status(user_id: str, status: str) -> None:
    """
    Upsert escalation_status for a user thread.

    Uses INSERT … ON CONFLICT so it also works for users who trigger escalation
    on their very first message (no user_threads row exists yet). A placeholder
    thread_id of 'pending' is set on new rows and will be overwritten by
    get_or_create_thread_id once the bot resumes.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_threads (user_id, thread_id, escalation_status, escalated_at)
                    VALUES (
                        %s,
                        'pending',
                        %s,
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
        logger.error(f"Failed to set escalation status for {user_id}: {e}")


def get_escalated_threads() -> list:
    """Return all conversations with escalation_status = 'escalated', newest first."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ut.user_id, ut.thread_id, ut.escalated_at,
                           m.message  AS last_message,
                           m.timestamp AS last_msg_time
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
        logger.error(f"Failed to fetch escalated threads: {e}")
        return []


def get_messages_since_escalation(user_id: str) -> list:
    """Return inbound message texts sent after the user's escalated_at timestamp, oldest first."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor() as cur:
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
        logger.error(f"Failed to get messages since escalation for {user_id}: {e}")
        return []


def get_user_escalation_status(user_id: str) -> str:
    """Return the escalation_status for a user ('bot', 'escalated', or 'resolved'). Defaults to 'bot'."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT escalation_status FROM user_threads WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
                return row[0] if row else "bot"
    except Exception as e:
        logger.error(f"Failed to get escalation status for {user_id}: {e}")
        return "bot"


def get_or_create_thread_id(user_id: str) -> str:
    client_sync = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT thread_id FROM user_threads WHERE user_id = %s FOR UPDATE",
                    (user_id,)
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE user_threads SET last_accessed = NOW() WHERE user_id = %s",
                        (user_id,)
                    )
                    return row['thread_id']
                # No existing row — create thread inside the same transaction so that
                # concurrent callers are serialized by the FOR UPDATE lock, preventing
                # multiple OpenAI threads from being created for the same user.
                thread = client_sync.beta.threads.create(
                    extra_headers={"OpenAI-Beta": "assistants=v2"}
                )
                cur.execute(
                    """
                    INSERT INTO user_threads (user_id, thread_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                        SET updated_at = NOW(),
                            last_accessed = NOW()
                    RETURNING thread_id
                    """,
                    (user_id, thread.id)
                )
                result = cur.fetchone()
                return result['thread_id']
    except Exception as e:
        logger.error(f"⚠️ Unable to manage user thread record: {e}")
        raise RuntimeError("❌ Failed to manage user thread record") from e


def get_admin(username: str) -> dict | None:
    """Fetch admin record by username from the DB. Returns dict with password_hash or None."""
    try:
        with get_ro_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT username, password_hash FROM admins WHERE username = %s",
                    (username,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to fetch admin '{username}': {e}")
        return None
        raise RuntimeError("❌ Failed to manage user thread record") from e
