import redis
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
pool = redis.ConnectionPool.from_url(
    redis_url,
    socket_timeout=10,
    socket_connect_timeout=10,
    retry_on_timeout=True
)
redis_connection = redis.Redis(connection_pool=pool)

RATELIMIT_STORAGE_URI = redis_url  # Use Redis for storing rate limit counters

__all__ = ["redis_connection", "redis_url"]

