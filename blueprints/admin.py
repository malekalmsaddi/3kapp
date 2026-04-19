"""
blueprints/admin.py — Tenant-scoped admin endpoints.

  GET  /admin/dashboard                     — threads, rate limiters, messages, bulk logs
  POST /admin/delete_thread/<thread_id>     — delete a thread
  POST /admin/respond                       — admin reply or route to bot
  GET  /admin/escalations                   — list escalated conversations
  POST /admin/escalations/<phone>/resolve   — resolve escalation
"""
import os
import json
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, abort, g
from psycopg2.extras import RealDictCursor

from db import (
    get_conn, get_escalated_threads, set_escalation_status,
    log_message, log_audit, LEGACY_TENANT_ID,
)
from logati import logger
from redis_client import redis_connection, get_tenant_redis
from utils import normalize_phone, send_whatsapp

admin_bp = Blueprint('admin', __name__)


def _get_tenant_id() -> str:
    return g.tenant_id or LEGACY_TENANT_ID


@admin_bp.route('/dashboard')
def admin_dashboard():
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    r = get_tenant_redis(tenant_id)
    filter_term = request.args.get('filter', '').lower()

    # Rate limiter keys (scoped to this tenant's IP/identity patterns)
    limiter_results = {}
    for k in r.scan_iter('LIMITER/*', count=100):
        if len(limiter_results) >= 500:
            break
        try:
            name = k.decode()
            if filter_term and filter_term not in name.lower():
                continue
            val = r.raw.get(k)
            limiter_results[name] = val.decode() if val else ''
        except Exception:
            pass

    # Bulk logs (tenant-scoped first, then global fallback)
    bulk_logs = []
    latest = r.get('latest_bulk_task')
    if not latest:
        latest = redis_connection.get('latest_bulk_task')
    if latest:
        task_id = latest.decode() if isinstance(latest, bytes) else latest
        logs_raw = r.lrange(f'log:{task_id}', 0, -1)
        if not logs_raw:
            logs_raw = redis_connection.lrange(f'log:{task_id}', 0, -1)
        for entry in logs_raw:
            try:
                bulk_logs.append(json.loads(entry.decode()))
            except Exception:
                pass

    thread_map, messages = [], []
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT user_id, thread_id, last_accessed
                FROM user_threads
                WHERE tenant_id = %s
                ORDER BY last_accessed DESC
                """,
                (tenant_id,),
            )
            thread_map = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT timestamp, direction, phone, message
                FROM messages
                WHERE tenant_id = %s
                ORDER BY timestamp DESC LIMIT 50
                """,
                (tenant_id,),
            )
            messages = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f'Admin load error: {e}')

    return jsonify({
        'limiter_keys': limiter_results,
        'bulk_logs': bulk_logs,
        'thread_map': thread_map,
        'messages': messages,
    })


@admin_bp.route('/delete_thread/<thread_id>', methods=['POST'])
def delete_thread(thread_id):
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                'DELETE FROM user_threads WHERE tenant_id = %s AND thread_id = %s',
                (tenant_id, thread_id),
            )

        log_audit(
            tenant_id=tenant_id,
            actor_user_id=g.user_id,
            action='thread.delete',
            resource_type='thread',
            resource_id=thread_id,
            ip_address=request.remote_addr,
        )
        return jsonify({'status': 'ok', 'deleted': thread_id})
    except Exception as e:
        logger.error(f'Delete thread error: {e}')
        return jsonify({'status': 'error', 'message': 'Could not delete thread.'}), 500


@admin_bp.route('/respond', methods=['POST'])
def admin_respond():
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    data = request.get_json() or request.form
    user = normalize_phone(data.get('user_number', ''))
    msg  = str(data.get('message', '')).strip()
    mode = data.get('mode', '')
    ts   = datetime.now(timezone.utc).isoformat()

    if not user or not msg:
        abort(400, 'Missing required fields: user_number and message')

    try:
        if mode == 'user_to_bot':
            from tasks import process_openai
            process_openai.delay(tenant_id, user, msg)
        else:
            send_whatsapp(user, msg)
            log_message(ts, 'outbound', user, msg, tenant_id=tenant_id)
            human_window = int(os.getenv('HUMAN_ACTIVE_WINDOW', 1800))
            r = get_tenant_redis(tenant_id)
            r.set(f'escalation_hold:{user}', '1', ex=human_window)

        log_audit(
            tenant_id=tenant_id,
            actor_user_id=g.user_id,
            action='admin.respond',
            resource_type='conversation',
            resource_id=user,
            payload={'mode': mode},
            ip_address=request.remote_addr,
        )
        return jsonify({'status': 'ok', 'to': user})
    except Exception as e:
        logger.exception(f'Admin respond error for {user}: {e}')
        abort(500, f'Failed to send response: {type(e).__name__}')


@admin_bp.route('/escalations')
def list_escalations():
    if not g.authenticated:
        abort(401)
    return jsonify(get_escalated_threads(tenant_id=_get_tenant_id()))


@admin_bp.route('/escalations/<path:user_number>/resolve', methods=['POST'])
def resolve_escalation(user_number):
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    phone = normalize_phone(user_number)
    if not phone:
        return jsonify({'status': 'error', 'message': 'Invalid phone number'}), 400

    set_escalation_status(phone, 'bot', tenant_id=tenant_id)
    r = get_tenant_redis(tenant_id)
    r.delete(f'neg_streak:{phone}')

    log_audit(
        tenant_id=tenant_id,
        actor_user_id=g.user_id,
        action='escalation.resolve',
        resource_type='conversation',
        resource_id=phone,
        ip_address=request.remote_addr,
    )
    logger.info(f'[escalation] {phone} resolved by admin [tenant={tenant_id}]')
    return jsonify({'status': 'ok', 'user': phone})
