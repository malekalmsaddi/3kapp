"""
redis_client.py — Redis connection pool + TenantRedis namespace wrapper.

TenantRedis automatically prefixes every key with tenant:{tenant_id}:
so operations are isolated per tenant without changing key names in
calling code.
"""
import redis
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
pool = redis.ConnectionPool.from_url(
    redis_url,
    socket_timeout=10,
    socket_connect_timeout=10,
    retry_on_timeout=True,
)
redis_connection = redis.Redis(connection_pool=pool)

RATELIMIT_STORAGE_URI = redis_url


class TenantRedis:
    """Thin wrapper that prefixes every key with tenant:{tenant_id}: automatically.

    Usage:
        r = TenantRedis(redis_connection, 'some-uuid')
        r.set('msg:abc', '1', ex=3600)
        # Actual Redis key: tenant:some-uuid:msg:abc
    """

    def __init__(self, conn: redis.Redis, tenant_id: str):
        self._conn = conn
        self._prefix = f"tenant:{tenant_id}:"

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}"

    # ── String commands ──────────────────────────────────────────────────
    def get(self, key):
        return self._conn.get(self._k(key))

    def set(self, key, value, **kwargs):
        return self._conn.set(self._k(key), value, **kwargs)

    def setex(self, key, time, value):
        return self._conn.setex(self._k(key), time, value)

    def delete(self, *keys):
        return self._conn.delete(*[self._k(k) for k in keys])

    def incr(self, key):
        return self._conn.incr(self._k(key))

    def decr(self, key):
        return self._conn.decr(self._k(key))

    def exists(self, *keys):
        return self._conn.exists(*[self._k(k) for k in keys])

    def expire(self, key, seconds):
        return self._conn.expire(self._k(key), seconds)

    def ttl(self, key):
        return self._conn.ttl(self._k(key))

    # ── List commands ────────────────────────────────────────────────────
    def rpush(self, key, *values):
        return self._conn.rpush(self._k(key), *values)

    def lpush(self, key, *values):
        return self._conn.lpush(self._k(key), *values)

    def lpop(self, key):
        return self._conn.lpop(self._k(key))

    def lrange(self, key, start, end):
        return self._conn.lrange(self._k(key), start, end)

    def llen(self, key):
        return self._conn.llen(self._k(key))

    # ── Set commands ─────────────────────────────────────────────────────
    def sadd(self, key, *values):
        return self._conn.sadd(self._k(key), *values)

    def sismember(self, key, value):
        return self._conn.sismember(self._k(key), value)

    def smembers(self, key):
        return self._conn.smembers(self._k(key))

    # ── Scan ─────────────────────────────────────────────────────────────
    def scan_iter(self, match=None, count=100):
        pattern = self._k(match) if match else f"{self._prefix}*"
        return self._conn.scan_iter(match=pattern, count=count)

    # ── Pipeline ─────────────────────────────────────────────────────────
    def pipeline(self, transaction=True):
        return _TenantPipeline(self._conn.pipeline(transaction=transaction), self._prefix)

    @property
    def raw(self) -> redis.Redis:
        """Access the underlying Redis connection for operations that don't need namespacing."""
        return self._conn


class _TenantPipeline:
    """Pipeline wrapper that applies tenant prefix to all keys."""

    def __init__(self, pipe, prefix: str):
        self._pipe = pipe
        self._prefix = prefix

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def set(self, key, value, **kwargs):
        self._pipe.set(self._k(key), value, **kwargs)
        return self

    def get(self, key):
        self._pipe.get(self._k(key))
        return self

    def expire(self, key, seconds):
        self._pipe.expire(self._k(key), seconds)
        return self

    def rpush(self, key, *values):
        self._pipe.rpush(self._k(key), *values)
        return self

    def incr(self, key):
        self._pipe.incr(self._k(key))
        return self

    def execute(self):
        return self._pipe.execute()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._pipe.__exit__(*args)


def get_tenant_redis(tenant_id: str) -> TenantRedis:
    """Factory function to create a tenant-scoped Redis wrapper."""
    return TenantRedis(redis_connection, tenant_id)


__all__ = ["redis_connection", "redis_url", "TenantRedis", "get_tenant_redis"]
