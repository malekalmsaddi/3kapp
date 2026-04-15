"""
blueprints/dashboard.py — Dashboard and data endpoints.

  GET  /dashboard       — conversation list + CSV upload (POST)
  GET  /dashboard/data  — 10-minute chart data
"""
import json
import hashlib
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, abort, Response, g
from psycopg2.extras import RealDictCursor
from werkzeug.exceptions import RequestEntityTooLarge

from db import get_conn, LEGACY_TENANT_ID
from logati import logger

dashboard_bp = Blueprint('dashboard', __name__)


def _get_tenant_id() -> str:
    return g.tenant_id or LEGACY_TENANT_ID


@dashboard_bp.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Please upload a CSV file.'}), 400
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'status': 'error', 'message': 'Only CSV files are accepted.'}), 400
        try:
            from itsdangerous import URLSafeSerializer
            from flask import current_app
            serializer = URLSafeSerializer(current_app.secret_key)
            content = file.read().decode('utf-8')
            from tasks import process_bulk_file
            task = process_bulk_file.delay(tenant_id, content)
            ref = serializer.dumps(task.id)
            return jsonify({'status': 'ok', 'task_id': ref}), 202
        except RequestEntityTooLarge:
            return jsonify({'status': 'error', 'message': 'File too large. Max 5 MB.'}), 413
        except Exception as e:
            logger.error(f'Bulk upload error: {e}')
            return jsonify({'status': 'error', 'message': 'Error processing CSV.'}), 500

    conversations, users = {}, []
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            try:
                cur.execute(
                    """
                    SELECT phone, direction, timestamp, message, sentiment
                    FROM messages
                    WHERE tenant_id = %s
                    ORDER BY phone, timestamp
                    LIMIT 2000
                    """,
                    (tenant_id,),
                )
            except Exception:
                conn.rollback()
                cur.execute(
                    "SELECT phone, direction, timestamp, message, sentiment "
                    "FROM messages ORDER BY phone, timestamp LIMIT 2000"
                )
            for r in cur.fetchall():
                conversations.setdefault(r['phone'], []).append(dict(r))

            try:
                cur.execute(
                    """
                    SELECT DISTINCT ON (m.phone)
                           m.phone,
                           m.timestamp AS last_seen,
                           m.message   AS last_message,
                           COALESCE(ut.escalation_status, 'bot') AS escalation_status
                    FROM messages m
                    LEFT JOIN user_threads ut
                      ON ut.tenant_id = %s AND ut.user_id = m.phone
                    WHERE m.tenant_id = %s
                    ORDER BY m.phone, m.timestamp DESC
                    """,
                    (tenant_id, tenant_id),
                )
            except Exception:
                conn.rollback()
                cur.execute(
                    """
                    SELECT DISTINCT ON (m.phone)
                           m.phone, m.timestamp AS last_seen, m.message AS last_message,
                           COALESCE(ut.escalation_status, 'bot') AS escalation_status
                    FROM messages m
                    LEFT JOIN user_threads ut ON ut.user_id = m.phone
                    ORDER BY m.phone, m.timestamp DESC
                    """
                )
            users = sorted(
                [dict(r) for r in cur.fetchall()],
                key=lambda x: x['last_seen'],
                reverse=True,
            )
    except Exception as e:
        logger.error(f'🧭 [dashboard] Load error: {e}', exc_info=True)
        return jsonify({'status': 'error', 'message': 'Could not load dashboard data.'}), 500

    body = json.dumps({'conversations': conversations, 'users': users}, default=str, sort_keys=True)
    etag = f'"{hashlib.md5(body.encode()).hexdigest()}"'
    if request.headers.get('If-None-Match') == etag:
        return Response(status=304)
    resp = Response(body, mimetype='application/json')
    resp.headers['ETag'] = etag
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@dashboard_bp.route('/dashboard/data')
def dashboard_data():
    if not g.authenticated:
        abort(401)

    tenant_id = _get_tenant_id()
    now = datetime.now(timezone.utc)
    minutes = [now - timedelta(minutes=i) for i in range(9, -1, -1)]
    labels = [m.strftime('%H:%M') for m in minutes]
    inbound_counts  = {label: 0 for label in labels}
    outbound_counts = {label: 0 for label in labels}
    escalated_count = 0

    try:
        with get_conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT date_trunc('minute', timestamp) AS minute, direction, COUNT(*)
                    FROM messages
                    WHERE tenant_id = %s AND timestamp >= NOW() - INTERVAL '10 minutes'
                    GROUP BY minute, direction
                    """,
                    (tenant_id,),
                )
            except Exception:
                conn.rollback()
                cur.execute(
                    """
                    SELECT date_trunc('minute', timestamp) AS minute, direction, COUNT(*)
                    FROM messages
                    WHERE timestamp >= NOW() - INTERVAL '10 minutes'
                    GROUP BY minute, direction
                    """
                )
            for minute, direction, count in cur.fetchall():
                label = minute.strftime('%H:%M')
                if direction == 'inbound':
                    inbound_counts[label] = count
                else:
                    outbound_counts[label] = count

            try:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM user_threads
                    WHERE tenant_id = %s AND escalation_status = 'escalated'
                    """,
                    (tenant_id,),
                )
            except Exception:
                conn.rollback()
                cur.execute(
                    "SELECT COUNT(*) FROM user_threads WHERE escalation_status = 'escalated'"
                )
            escalated_count = cur.fetchone()[0]
    except Exception as e:
        logger.error(f'📊 [dashboard_data] error: {e}', exc_info=True)

    return jsonify({
        'labels': labels,
        'inbound': [inbound_counts[l] for l in labels],
        'outbound': [outbound_counts[l] for l in labels],
        'escalated_count': escalated_count,
    })
