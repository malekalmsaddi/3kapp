"""
services/entitlements.py — Entitlement enforcement middleware for Flask.

Provides decorators that check plan-level quotas and feature flags
before allowing a request to proceed. Returns HTTP 402 (Payment Required)
when a tenant exceeds their plan limits.
"""
from functools import wraps
from flask import g, jsonify, abort

from services.tenant_service import get_plan_entitlements
from logati import logger


def require_feature(feature_name: str):
    """Decorator: require a boolean feature flag from the tenant's plan.

    Returns 402 if the feature is not enabled for the tenant's plan.
    Super admins bypass all checks.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.role == 'super_admin':
                return fn(*args, **kwargs)
            if not g.tenant_id:
                abort(403)
            entitlements = get_plan_entitlements(g.tenant_id)
            if not entitlements.get(feature_name, False):
                return jsonify({
                    'error': 'Feature not available on your current plan',
                    'feature': feature_name,
                    'upgrade_required': True,
                }), 402
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def require_quota(metric: str, get_current_usage_fn, requested: int = 1):
    """Decorator: check a numeric quota from the tenant's plan.

    get_current_usage_fn(tenant_id) -> int returns the current usage count.
    Returns 402 if the quota would be exceeded.
    Super admins bypass all checks.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.role == 'super_admin':
                return fn(*args, **kwargs)
            if not g.tenant_id:
                abort(403)
            entitlements = get_plan_entitlements(g.tenant_id)
            limit = entitlements.get(metric, 0)
            if limit == -1:  # unlimited
                return fn(*args, **kwargs)
            current = get_current_usage_fn(g.tenant_id)
            if current + requested > limit:
                return jsonify({
                    'error': f'Plan quota exceeded for {metric}',
                    'metric': metric,
                    'current': current,
                    'limit': limit,
                    'upgrade_required': True,
                }), 402
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def check_admin_count(tenant_id: str) -> bool:
    """Check if the tenant can add another admin user."""
    entitlements = get_plan_entitlements(tenant_id)
    max_admins = entitlements.get('max_admins', 1)
    if max_admins == -1:
        return True
    from db import get_conn
    from psycopg2.extras import RealDictCursor
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM users WHERE tenant_id = %s AND role = 'tenant'",
                (tenant_id,),
            )
            current = cur.fetchone()['n']
    return current < max_admins
