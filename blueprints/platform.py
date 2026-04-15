"""
blueprints/platform.py — Super-admin platform management endpoints.

  GET  /tenants            — list all tenants
  GET  /tenants/<id>       — tenant detail
  POST /tenants/<id>/suspend — suspend a tenant
  POST /tenants/<id>/activate — activate a tenant
  GET  /usage              — cross-tenant usage stats
  GET  /plans              — list all plans
"""
import json
from flask import Blueprint, request, jsonify, abort, g
from psycopg2.extras import RealDictCursor

from db import get_all_tenants, get_tenant_by_id, get_conn, log_audit
from middleware.jwt_middleware import require_super_admin
from logati import logger

platform_bp = Blueprint('platform', __name__)


@platform_bp.route('/tenants')
@require_super_admin
def list_tenants():
    tenants = get_all_tenants()
    return jsonify([
        {k: str(v) if k.endswith('_id') or k == 'id' else v
         for k, v in t.items()}
        for t in tenants
    ])


@platform_bp.route('/tenants/<tenant_id>')
@require_super_admin
def get_tenant(tenant_id):
    tenant = get_tenant_by_id(tenant_id)
    if not tenant:
        abort(404)

    # Fetch associated users
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT id, email, role, is_active, last_login_at, created_at
                FROM users WHERE tenant_id = %s ORDER BY created_at
                """,
                (tenant_id,),
            )
            users = [dict(r) for r in cur.fetchall()]
    except Exception:
        users = []

    # Fetch usage summary
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT event_type, COUNT(*) AS count, SUM(quantity) AS total
                FROM usage_events
                WHERE tenant_id = %s
                  AND created_at >= NOW() - INTERVAL '30 days'
                GROUP BY event_type
                """,
                (tenant_id,),
            )
            usage = {r['event_type']: {'count': r['count'], 'total': r['total']}
                     for r in cur.fetchall()}
    except Exception:
        usage = {}

    result = {k: str(v) if k.endswith('_id') or k == 'id' else v
              for k, v in tenant.items()}
    result['users'] = users
    result['usage_30d'] = usage
    return jsonify(result)


@platform_bp.route('/tenants/<tenant_id>/suspend', methods=['POST'])
@require_super_admin
def suspend_tenant(tenant_id):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tenants SET status = 'suspended', updated_at = NOW() WHERE id = %s",
                (tenant_id,),
            )
        log_audit(
            tenant_id=tenant_id,
            actor_user_id=g.user_id,
            action='tenant.suspend',
            resource_type='tenant',
            resource_id=tenant_id,
            ip_address=request.remote_addr,
        )
        return jsonify({'status': 'ok', 'tenant_id': tenant_id, 'new_status': 'suspended'})
    except Exception as e:
        logger.error(f'Failed to suspend tenant: {e}')
        return jsonify({'error': 'Failed to suspend tenant'}), 500


@platform_bp.route('/tenants/<tenant_id>/activate', methods=['POST'])
@require_super_admin
def activate_tenant(tenant_id):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tenants SET status = 'active', updated_at = NOW() WHERE id = %s",
                (tenant_id,),
            )
        log_audit(
            tenant_id=tenant_id,
            actor_user_id=g.user_id,
            action='tenant.activate',
            resource_type='tenant',
            resource_id=tenant_id,
            ip_address=request.remote_addr,
        )
        return jsonify({'status': 'ok', 'tenant_id': tenant_id, 'new_status': 'active'})
    except Exception as e:
        logger.error(f'Failed to activate tenant: {e}')
        return jsonify({'error': 'Failed to activate tenant'}), 500


@platform_bp.route('/usage')
@require_super_admin
def platform_usage():
    """Cross-tenant usage dashboard."""
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT t.slug, t.name, ue.event_type,
                       COUNT(*) AS event_count, SUM(ue.quantity) AS total_quantity
                FROM usage_events ue
                JOIN tenants t ON t.id = ue.tenant_id
                WHERE ue.created_at >= NOW() - INTERVAL '30 days'
                GROUP BY t.slug, t.name, ue.event_type
                ORDER BY t.name, ue.event_type
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

        # Reshape: {tenant_slug: {event_type: {count, total}}}
        by_tenant = {}
        for row in rows:
            slug = row['slug']
            if slug not in by_tenant:
                by_tenant[slug] = {'name': row['name'], 'events': {}}
            by_tenant[slug]['events'][row['event_type']] = {
                'count': row['event_count'],
                'total': row['total_quantity'],
            }

        return jsonify(by_tenant)
    except Exception as e:
        logger.error(f'Platform usage error: {e}')
        return jsonify({}), 500


@platform_bp.route('/plans')
@require_super_admin
def list_plans():
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM plans ORDER BY sort_order')
            return jsonify([dict(r) for r in cur.fetchall()])
    except Exception as e:
        logger.error(f'Plans fetch error: {e}')
        return jsonify([]), 500
