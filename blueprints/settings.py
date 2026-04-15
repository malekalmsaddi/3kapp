"""
blueprints/settings.py — User settings and utility endpoints.

  GET/POST /settings    — notification preferences
  POST     /send_email  — send email via SendGrid
  GET      /metrics     — Prometheus-format DB pool metrics
  GET      /health      — service liveness probe
"""
import os
from flask import Blueprint, request, jsonify, abort, g, session, Response

from db import connection_health_check, LEGACY_TENANT_ID
from utils import send_email
from logati import logger

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if not g.authenticated:
        abort(401)

    if request.method == 'POST':
        data = request.get_json() or {}
        notify = data.get('notify', False)
        session['notify'] = notify
        return jsonify({'status': 'ok', 'notify': notify})

    return jsonify({'notify': session.get('notify', True)})


@settings_bp.route('/send_email', methods=['POST'])
def send_email_endpoint():
    if not g.authenticated:
        abort(401)

    data = request.get_json() or {}
    if not {'to_email', 'subject', 'body'}.issubset(data):
        return jsonify({'status': 'error', 'message': 'Missing fields'}), 400
    try:
        result = send_email(data['to_email'], data['subject'], data['body'])
    except RuntimeError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    status = result.get('status', 'error')
    payload = {'status': status}
    if 'sent' in result:
        payload['sent'] = result['sent']
    if 'failed' in result:
        payload['failed'] = result['failed']
    http_status = 200 if status in ('success', 'partial') else 400
    return jsonify(payload), http_status


@settings_bp.route('/metrics')
def metrics():
    if not g.authenticated:
        abort(401)
    stats = connection_health_check()
    lines = [
        f'db_connections_available {stats.get("available", 0)}',
        f'db_connections_active {stats.get("active", 0)}',
        f'db_messages_total {stats.get("message_count", 0)}',
    ]
    return Response('\n'.join(lines), mimetype='text/plain')


@settings_bp.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200
