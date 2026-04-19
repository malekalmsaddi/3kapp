"""
blueprints/messaging.py — Template sending and bulk messaging endpoints.

  POST /send_template     — send single template
  POST /start_bulk_send   — start bulk template job
  GET  /bulk_limits       — compliance limits
  GET  /progress/<id>     — poll bulk job progress
  GET  /task/status       — check CSV processing task
  GET  /get_templates     — list Twilio template SIDs
"""
import os
import json
import hashlib

from flask import Blueprint, request, jsonify, abort, g
from itsdangerous import URLSafeSerializer

from logati import logger
from redis_client import redis_connection, get_tenant_redis
from utils import normalize_phone
from twilio_helpers import get_twilio_client

messaging_bp = Blueprint('messaging', __name__)


def _get_tenant_id() -> str:
    if not g.tenant_id:
        abort(401)
    return g.tenant_id


@messaging_bp.route('/send_template', methods=['POST'])
def send_template():
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    data = request.get_json() or request.form
    sid  = data.get('template_sid')
    user_number = normalize_phone(data.get('user_number', ''))
    params = {'param1': data.get('param1', ''), 'param2': data.get('param2', '')}

    if not sid or not user_number:
        return jsonify({'status': 'error', 'message': 'template_sid and user_number required'}), 400

    from tasks import send_whatsapp_template
    send_whatsapp_template.apply_async(args=(tenant_id, user_number, params, sid))
    return jsonify({'status': 'ok', 'to': user_number}), 202


@messaging_bp.route('/start_bulk_send', methods=['POST'])
def start_bulk_send():
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    r = get_tenant_redis(tenant_id)

    try:
        data = request.get_json() or {}
        payload      = data.get('payload', [])
        payload_str  = json.dumps(payload)
        template_sid = data.get('template_sid')

        if not isinstance(payload, list) or not template_sid:
            raise ValueError('Invalid input')

        # Load per-tenant limits
        try:
            from services.tenant_service import load_tenant_context
            config, _ = load_tenant_context(tenant_id)
            bulk_max_batch = config.get('bulk_max_batch', 500)
            bulk_daily_cap = config.get('bulk_daily_cap', 1000)
        except Exception:
            bulk_max_batch = int(os.getenv('BULK_MAX_BATCH', 500))
            bulk_daily_cap = int(os.getenv('BULK_DAILY_CAP', 1000))

        batch_size = len(payload)
        if batch_size == 0:
            return jsonify({'error': 'Payload is empty'}), 400
        if batch_size > bulk_max_batch:
            return jsonify({
                'error': f'Batch too large: {batch_size} > max {bulk_max_batch}',
                'limit': bulk_max_batch,
                'requested': batch_size,
            }), 422

        # Per-tenant daily cap (scoped key)
        daily_key = f"bulk:daily:{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d')}"
        raw = r.get(daily_key)
        daily_sent = int(raw) if raw else 0
        daily_remaining = max(bulk_daily_cap - daily_sent, 0)

        if daily_remaining == 0:
            return jsonify({
                'error': f'Daily cap of {bulk_daily_cap} reached. Resets at midnight UTC.',
                'daily_cap': bulk_daily_cap,
                'daily_sent': daily_sent,
            }), 429

        # Duplicate-job lock (tenant-scoped)
        lock_key = f"lock:bulk:{hashlib.sha256(payload_str.encode()).hexdigest()}"
        if r.get(lock_key):
            return jsonify({'error': 'Bulk send already initiated for this payload'}), 429
        r.set(lock_key, '1', ex=600)

        from tasks import send_bulk_contacts
        task = send_bulk_contacts.delay(tenant_id, payload, template_sid)
        r.set('latest_bulk_task', task.id)

        return jsonify({
            'task_id': task.id,
            'batch_size': batch_size,
            'daily_sent': daily_sent,
            'daily_remaining': daily_remaining,
        })

    except Exception as e:
        logger.error(f'Bulk send error: {e}')
        return jsonify({'error': 'Invalid payload or server error'}), 400


@messaging_bp.route('/bulk_limits')
def bulk_limits():
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()

    try:
        from services.tenant_service import load_tenant_context
        config, _ = load_tenant_context(tenant_id)
        bulk_max_batch = config.get('bulk_max_batch', 500)
        bulk_daily_cap = config.get('bulk_daily_cap', 1000)
        bulk_msg_delay = float(config.get('bulk_msg_delay_sec', 1.5))
    except Exception:
        bulk_max_batch = int(os.getenv('BULK_MAX_BATCH', 500))
        bulk_daily_cap = int(os.getenv('BULK_DAILY_CAP', 1000))
        bulk_msg_delay = float(os.getenv('BULK_MSG_DELAY', 1.5))

    r = get_tenant_redis(tenant_id)
    daily_key = f"bulk:daily:{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d')}"
    raw = r.get(daily_key)
    daily_sent = int(raw) if raw else 0

    return jsonify({
        'max_batch': bulk_max_batch,
        'daily_cap': bulk_daily_cap,
        'daily_sent': daily_sent,
        'daily_remaining': max(bulk_daily_cap - daily_sent, 0),
        'msg_delay_s': bulk_msg_delay,
    })


@messaging_bp.route('/progress/<task_id>')
def get_progress(task_id):
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    r = get_tenant_redis(tenant_id)

    # Try tenant-scoped keys first, fall back to global
    prog = r.get(f'progress:{task_id}')
    if prog is None:
        prog = redis_connection.get(f'progress:{task_id}')
    logs_raw = r.lrange(f'log:{task_id}', 0, -1)
    if not logs_raw:
        logs_raw = redis_connection.lrange(f'log:{task_id}', 0, -1)

    parsed_logs = []
    for entry in logs_raw:
        try:
            parsed_logs.append(json.loads(entry.decode()))
        except Exception:
            pass

    return jsonify({
        'progress': prog.decode() if prog else '0/0',
        'logs': parsed_logs,
    })


@messaging_bp.route('/task/status')
def task_status():
    if not g.authenticated:
        abort(401)

    ref = request.args.get('ref')
    if not ref:
        abort(400, 'Missing reference')
    try:
        from flask import current_app
        serializer = URLSafeSerializer(current_app.secret_key)
        task_id = serializer.loads(ref)
        from tasks import process_bulk_file
        task = process_bulk_file.AsyncResult(task_id)
        result_val = None
        if task.ready():
            result_val = task.result if task.successful() else str(task.result)
        return jsonify({
            'ready': task.ready(),
            'successful': task.successful(),
            'status': task.status,
            'result': result_val,
        })
    except Exception as e:
        logger.error(f'Task status error: {e}')
        abort(400, 'Invalid reference')


@messaging_bp.route('/get_templates')
def get_templates():
    if not g.authenticated:
        abort(401)
    try:
        client = get_twilio_client()
        templates = [
            {'label': c.friendly_name, 'value': c.sid}
            for c in client.content.v1.contents.list()
        ]
        return jsonify(templates)
    except Exception as e:
        logger.error(f'Template fetch error: {e}')
        return jsonify({'error': 'Could not fetch templates'}), 500
