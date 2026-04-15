"""
tenant_service.py — Tenant config loading (with Redis caching) and entitlement checks.
"""
import json
import os

from db import (
    get_tenant_by_slug, get_tenant_by_id,
    get_tenant_config, get_assistant_config,
    LEGACY_TENANT_ID,
)
from crypto import (
    decrypt_dict_fields,
    TENANT_CONFIG_ENCRYPTED_FIELDS,
    ASSISTANT_CONFIG_ENCRYPTED_FIELDS,
)
from redis_client import redis_connection
from logati import logger

CONFIG_CACHE_TTL = 300  # 5 minutes


def load_tenant_context(tenant_id: str) -> tuple[dict, dict]:
    """Load tenant_config and assistant_config, using Redis cache.

    Returns (tenant_config, assistant_config) dicts with sensitive
    fields decrypted.
    """
    config_key = f'tenant:{tenant_id}:config'
    ai_key     = f'tenant:{tenant_id}:assistant_config'

    # Try cache
    raw_config = redis_connection.get(config_key)
    raw_ai     = redis_connection.get(ai_key)

    if raw_config and raw_ai:
        config    = json.loads(raw_config)
        ai_config = json.loads(raw_ai)
    else:
        config    = get_tenant_config(tenant_id)
        ai_config = get_assistant_config(tenant_id)

        if config is None or ai_config is None:
            raise ValueError(f'Tenant {tenant_id} not found or missing config')

        # Decrypt sensitive fields
        config    = decrypt_dict_fields(config, TENANT_CONFIG_ENCRYPTED_FIELDS)
        ai_config = decrypt_dict_fields(ai_config, ASSISTANT_CONFIG_ENCRYPTED_FIELDS)

        # Cache (store decrypted for quick access — Redis is trusted infra)
        try:
            redis_connection.setex(config_key, CONFIG_CACHE_TTL, json.dumps(config, default=str))
            redis_connection.setex(ai_key, CONFIG_CACHE_TTL, json.dumps(ai_config, default=str))
        except Exception as e:
            logger.warning(f'Failed to cache tenant config: {e}')

    return config, ai_config


def invalidate_tenant_cache(tenant_id: str) -> None:
    """Purge the cached config for a tenant (call after config changes)."""
    redis_connection.delete(f'tenant:{tenant_id}:config')
    redis_connection.delete(f'tenant:{tenant_id}:assistant_config')
    redis_connection.delete(f'platform:tenant_slug_cache')  # slug lookup too


def resolve_tenant_by_slug(slug: str) -> dict | None:
    """Look up a tenant by slug, using Redis cache for the slug→id mapping."""
    cache_key = f'platform:tenant_slug:{slug}'
    cached = redis_connection.get(cache_key)
    if cached:
        tenant_id = cached.decode() if isinstance(cached, bytes) else cached
        return get_tenant_by_id(tenant_id)

    tenant = get_tenant_by_slug(slug)
    if tenant:
        try:
            redis_connection.setex(cache_key, CONFIG_CACHE_TTL, str(tenant['id']))
        except Exception:
            pass
    return tenant


def get_plan_entitlements(tenant_id: str) -> dict:
    """Return the plan entitlements for a tenant."""
    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        return {}
    entitlements = tenant.get('plan_entitlements', {})
    if isinstance(entitlements, str):
        entitlements = json.loads(entitlements)
    return entitlements


def check_entitlement(tenant_id: str, feature: str) -> bool:
    """Check if a tenant's plan allows a boolean feature."""
    entitlements = get_plan_entitlements(tenant_id)
    return bool(entitlements.get(feature, False))


def check_quota(tenant_id: str, metric: str, current_usage: int, requested: int = 1) -> tuple[bool, int]:
    """Check if tenant is within their plan quota.

    Returns (allowed, limit).
    A limit of -1 means unlimited.
    """
    entitlements = get_plan_entitlements(tenant_id)
    limit = entitlements.get(metric, 0)
    if limit == -1:  # unlimited
        return True, -1
    return (current_usage + requested <= limit), limit


def get_effective_config_value(config: dict, key: str, env_fallback: str | None = None, default=None):
    """Get a config value from the tenant config, falling back to env var if not set."""
    val = config.get(key)
    if val is not None and val != '':
        return val
    if env_fallback:
        env_val = os.getenv(env_fallback)
        if env_val:
            return env_val
    return default
