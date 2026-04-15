import os
import json
import uuid
import hashlib
import bcrypt
from datetime import datetime, timedelta, timezone
import threading
import time
from flask import (
    Flask, request, session,
    jsonify, abort, Response
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeSerializer
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from werkzeug.exceptions import RequestEntityTooLarge

from db import (
    connection_health_check, get_conn, init_db, log_message,
    get_escalated_threads, set_escalation_status, get_admin,
)
from logati import logger
from redis_client import redis_connection
from tasks import (
    process_bulk_file, process_openai, send_bulk_contacts, send_whatsapp_template,
    BULK_MAX_BATCH, BULK_DAILY_CAP, BULK_MSG_DELAY, _get_daily_sent, _daily_cap_key,
)
from utils import normalize_phone, send_email, send_whatsapp
from twilio_helpers import get_twilio_client
from twilio.request_validator import RequestValidator
from sentiment import reset_neg_streak


# --- Environment & Validation ---
load_dotenv()

REQUIRED_ENV = [
    'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_NUMBER',
    'OPENAI_API_KEY', 'ASSISTANT_ID', 'REDIS_URL',
    'FLASK_SECRET_KEY'
]
missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {missing}")

# Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config.update(
    SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV', 'production') == 'production',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # 5 MB upload limit
)

try:
    init_db()
except Exception as e:
    app.logger.warning(f"Database initialization failed: {e}")

serializer = URLSafeSerializer(app.secret_key)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv('REDIS_URL'),
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

@app.before_request
def assign_correlation_id():
    request.correlation_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())

@app.after_request
def add_correlation_header(response):
    if hasattr(request, 'correlation_id'):
        response.headers['X-Correlation-ID'] = request.correlation_id
    return response


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route('/login', methods=['POST'])
@limiter.limit('5 per minute')
def login():
    user = request.form.get('username', '').strip()
    pw = request.form.get('password', '').strip()

    logger.info("🔍 Login attempt for user %s", user)

    valid = False
    try:
        admin = get_admin(user)
        if admin:
            valid = bcrypt.checkpw(pw.encode(), admin['password_hash'].encode())
            logger.debug("✅ bcrypt match: %s", valid)
        else:
            logger.warning("❌ No admin found for username: %s", user)
    except Exception as e:
        logger.error("❌ bcrypt error: %s", e)
        valid = False

    if valid:
        session['logged_in'] = True
        return jsonify({'status': 'ok'}), 200

    return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'ok'}), 200


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/dashboard', methods=['GET', 'POST'])
@limiter.limit('200 per minute')
def dashboard():
    if not session.get('logged_in'):
        return abort(401)

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'status': 'error', 'message': 'Please upload a CSV file.'}), 400
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'status': 'error', 'message': 'Only CSV files are accepted.'}), 400
        try:
            content = file.read().decode('utf-8')
            task = process_bulk_file.delay(content)
            ref = serializer.dumps(task.id)
            return jsonify({'status': 'ok', 'task_id': ref}), 202
        except RequestEntityTooLarge:
            return jsonify({'status': 'error', 'message': 'File too large. Maximum size is 5 MB.'}), 413
        except Exception as e:
            app.logger.error(f'Bulk upload error: {e}')
            return jsonify({'status': 'error', 'message': 'Error processing CSV.'}), 500

    conversations, users = {}, []
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                "SELECT phone,direction,timestamp,message,sentiment "
                "FROM messages ORDER BY phone,timestamp LIMIT 2000"
            )
            for r in cur.fetchall():
                conversations.setdefault(r['phone'], []).append(dict(r))
            cur.execute(
                """
                SELECT DISTINCT ON (m.phone)
                       m.phone,
                       m.timestamp AS last_seen,
                       m.message   AS last_message,
                       COALESCE(ut.escalation_status, 'bot') AS escalation_status
                FROM messages m
                LEFT JOIN user_threads ut ON ut.user_id = m.phone
                ORDER BY m.phone, m.timestamp DESC
                """
            )
            users = sorted([dict(r) for r in cur.fetchall()], key=lambda x: x['last_seen'], reverse=True)
    except Exception as e:
        app.logger.error(f'🧭 [dashboard] Load error: {e}', exc_info=True)
        return jsonify({'status': 'error', 'message': 'Could not load dashboard data.'}), 500

    body = json.dumps({'conversations': conversations, 'users': users}, default=str, sort_keys=True)
    etag = f'"{hashlib.md5(body.encode()).hexdigest()}"'
    if request.headers.get('If-None-Match') == etag:
        return Response(status=304)
    resp = Response(body, mimetype='application/json')
    resp.headers['ETag'] = etag
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.route('/dashboard/data')
@limiter.limit('200 per minute')
def dashboard_data():
    if not session.get('logged_in'):
        return abort(401)

    now = datetime.now(timezone.utc)
    minutes = [now - timedelta(minutes=i) for i in range(9, -1, -1)]
    labels = [m.strftime('%H:%M') for m in minutes]
    inbound_counts = {label: 0 for label in labels}
    outbound_counts = {label: 0 for label in labels}

    escalated_count = 0
    try:
        with get_conn() as conn:
            cur = conn.cursor()
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
            cur.execute(
                "SELECT COUNT(*) FROM user_threads WHERE escalation_status = 'escalated'"
            )
            escalated_count = cur.fetchone()[0]
    except Exception as e:
        app.logger.error(f'📊 [dashboard_data] Load error: {e}', exc_info=True)

    return jsonify({
        'labels': labels,
        'inbound': [inbound_counts[l] for l in labels],
        'outbound': [outbound_counts[l] for l in labels],
        'escalated_count': escalated_count,
    })


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.route('/settings', methods=['GET', 'POST'])
@limiter.limit('50 per minute')
def settings():
    if not session.get('logged_in'):
        return abort(401)

    if request.method == 'POST':
        data = request.get_json() or {}
        notify = data.get('notify', False)
        session['notify'] = notify
        return jsonify({'status': 'ok', 'notify': notify})

    return jsonify({'notify': session.get('notify', True)})


# ---------------------------------------------------------------------------
# WhatsApp webhook (Twilio)
# ---------------------------------------------------------------------------

@app.route('/whatsapp', methods=['POST'])
@limiter.limit('20 per minute', key_func=lambda: request.form.get('From') or request.remote_addr)
def whatsapp_webhook():
    validator = RequestValidator(os.getenv('TWILIO_AUTH_TOKEN', ''))
    signature = request.headers.get('X-Twilio-Signature', '')
    if not validator.validate(request.url, request.form, signature):
        app.logger.warning("❌ Invalid Twilio signature on /whatsapp — request rejected")
        abort(403)

    msg = request.form.get('Body', '').strip()
    user_raw = request.form.get('From', '').strip()
    user = normalize_phone(user_raw)

    if user == normalize_phone(os.getenv('TWILIO_WHATSAPP_NUMBER', '')):
        app.logger.info(f"📵 Ignored Twilio status callback from number: {user_raw}")
        return 'Ignored Twilio status callback', 200

    if not msg or not user:
        app.logger.warning(f"📵 Rejected incoming msg. Raw user: {user_raw}, Msg: {msg}")
        return 'Ignored invalid message', 200

    message_sid = request.form.get('MessageSid') or request.form.get('SmsSid', '')
    if message_sid:
        dedup_key = f'msg:{message_sid}'
        if redis_connection.get(dedup_key):
            app.logger.info(f"💬 Duplicate Twilio webhook ignored: {message_sid}")
            return 'Duplicate message, ignored', 200
        redis_connection.set(dedup_key, 'processed', ex=3600)

    timestamp = datetime.now(timezone.utc).isoformat()
    log_message(timestamp, 'inbound', user, msg)

    try:
        logger.info(f"🚦 Dispatching OpenAI task for {user}")
        process_openai.delay(user, msg)
        logger.info(f"✅ OpenAI task dispatched for {user}")
    except Exception as e:
        logger.error(f'❌ Webhook dispatch failed: {e}', exc_info=True)
        return 'Task dispatch failed but acknowledged', 200

    return 'OK', 200


# ---------------------------------------------------------------------------
# Template sending
# ---------------------------------------------------------------------------

@app.route('/send_template', methods=['POST'])
@limiter.limit('20 per minute')
def send_template():
    if not session.get('logged_in'):
        return abort(401)

    data = request.get_json() or request.form
    sid = data.get('template_sid')
    user_number = normalize_phone(data.get('user_number', ''))
    params = {'param1': data.get('param1', ''), 'param2': data.get('param2', '')}

    if not sid or not user_number:
        return jsonify({'status': 'error', 'message': 'template_sid and user_number are required'}), 400

    send_whatsapp_template.apply_async(args=(user_number, params, sid))
    return jsonify({'status': 'ok', 'to': user_number}), 202


# ---------------------------------------------------------------------------
# Bulk send
# ---------------------------------------------------------------------------

@app.route('/start_bulk_send', methods=['POST'])
@limiter.limit('10 per minute')
def start_bulk_send():
    if not session.get('logged_in'):
        abort(401)
    try:
        data = request.get_json() or {}
        payload = data.get('payload', [])
        payload_str = json.dumps(payload)
        template_sid = data.get('template_sid')

        if not isinstance(payload, list) or not template_sid:
            raise ValueError("Invalid input")

        # ── Batch-size guard ─────────────────────────────────────────────────
        batch_size = len(payload)
        if batch_size == 0:
            return jsonify({'error': 'Payload is empty'}), 400
        if batch_size > BULK_MAX_BATCH:
            return jsonify({
                'error': (
                    f'Batch too large: {batch_size} recipients requested but the '
                    f'maximum per job is {BULK_MAX_BATCH} '
                    f'(Meta/Twilio compliance limit). '
                    f'Split into smaller batches.'
                ),
                'limit': BULK_MAX_BATCH,
                'requested': batch_size,
            }), 422

        # ── Daily-cap pre-check ──────────────────────────────────────────────
        daily_sent = _get_daily_sent()
        daily_remaining = max(BULK_DAILY_CAP - daily_sent, 0)
        if daily_remaining == 0:
            return jsonify({
                'error': (
                    f'Daily recipient cap of {BULK_DAILY_CAP} reached '
                    f'(Meta Tier 1 limit). No more messages can be sent today. '
                    f'Resets at midnight UTC.'
                ),
                'daily_cap': BULK_DAILY_CAP,
                'daily_sent': daily_sent,
            }), 429

        if batch_size > daily_remaining:
            app.logger.warning(
                f"[bulk] Job requests {batch_size} recipients but only "
                f"{daily_remaining} remain in today's cap — "
                f"{batch_size - daily_remaining} will be skipped by the worker."
            )

        # ── Duplicate-job lock ───────────────────────────────────────────────
        lock_key = f"lock:bulk:{hashlib.sha256(payload_str.encode()).hexdigest()}"
        if redis_connection.get(lock_key):
            return jsonify({'error': 'Bulk send already initiated for this payload'}), 429

        redis_connection.set(lock_key, "1", ex=600)
        task = send_bulk_contacts.delay(payload, template_sid)
        redis_connection.set('latest_bulk_task', task.id)
        return jsonify({
            'task_id': task.id,
            'batch_size': batch_size,
            'daily_sent': daily_sent,
            'daily_remaining': daily_remaining,
        })

    except Exception as e:
        app.logger.error(f"Bulk send error: {e}")
        return jsonify({'error': 'Invalid payload or server error'}), 400


@app.route('/bulk_limits')
def bulk_limits():
    """Return live Meta/Twilio compliance limits and today's usage.
    Used by the frontend to display warnings before the user submits a bulk job.
    """
    if not session.get('logged_in'):
        abort(401)
    daily_sent = _get_daily_sent()
    return jsonify({
        'max_batch': BULK_MAX_BATCH,
        'daily_cap': BULK_DAILY_CAP,
        'daily_sent': daily_sent,
        'daily_remaining': max(BULK_DAILY_CAP - daily_sent, 0),
        'msg_delay_s': BULK_MSG_DELAY,
    })


@app.route('/progress/<task_id>')
def get_progress(task_id):
    if not session.get('logged_in'):
        abort(401)
    prog = redis_connection.get(f'progress:{task_id}')
    logs = redis_connection.lrange(f'log:{task_id}', 0, -1)
    parsed_logs = []
    for l in logs:
        try:
            parsed_logs.append(json.loads(l.decode()))
        except Exception:
            pass
    return jsonify({
        'progress': prog.decode() if prog else '0/0',
        'logs': parsed_logs
    })


@app.route('/task/status')
def task_status():
    if not session.get('logged_in'):
        abort(401)
    ref = request.args.get('ref')
    if not ref:
        abort(400, 'Missing reference')
    try:
        task_id = serializer.loads(ref)
        task = process_bulk_file.AsyncResult(task_id)
        result_val = None
        if task.ready():
            result_val = task.result if task.successful() else str(task.result)
        return jsonify({
            'ready': task.ready(),
            'successful': task.successful(),
            'status': task.status,
            'result': result_val
        })
    except Exception as e:
        app.logger.error(f'Task status error: {e}')
        abort(400, 'Invalid reference')


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

@app.route('/send_email', methods=['POST'])
@limiter.limit('20 per minute')
def send_email_endpoint():
    if not session.get('logged_in'):
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


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('logged_in'):
        abort(401)
    filter_term = request.args.get('filter', '').lower()
    limiter_results = {}
    for k in redis_connection.scan_iter('LIMITER/*', count=100):
        if len(limiter_results) >= 500:
            break
        try:
            name = k.decode()
            if filter_term and filter_term not in name.lower():
                continue
            val = redis_connection.get(k)
            limiter_results[name] = val.decode() if val else ''
        except Exception:
            pass

    bulk_logs = []
    latest = redis_connection.get('latest_bulk_task')
    if latest:
        for l in redis_connection.lrange(f'log:{latest.decode()}', 0, -1):
            try:
                bulk_logs.append(json.loads(l.decode()))
            except Exception:
                pass

    thread_map, messages = [], []
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT user_id,thread_id,last_accessed FROM user_threads ORDER BY last_accessed DESC")
            thread_map = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT timestamp,direction,phone,message FROM messages ORDER BY timestamp DESC LIMIT 50")
            messages = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        app.logger.error(f'Admin load error: {e}')

    return jsonify({
        'limiter_keys': limiter_results,
        'bulk_logs': bulk_logs,
        'thread_map': thread_map,
        'messages': messages,
    })


@app.route('/admin/delete_thread/<thread_id>', methods=['POST'])
def delete_thread(thread_id):
    if not session.get('logged_in'):
        abort(401)
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM user_threads WHERE thread_id=%s", (thread_id,))
        return jsonify({'status': 'ok', 'deleted': thread_id})
    except Exception as e:
        app.logger.error(f'Delete thread error: {e}')
        return jsonify({'status': 'error', 'message': 'Could not delete thread.'}), 500


@app.route('/admin/respond', methods=['POST'])
def admin_respond():
    if not session.get('logged_in'):
        abort(401)
    data = request.get_json() or request.form
    user = normalize_phone(data.get('user_number', ''))
    msg = str(data.get('message', '')).strip()
    mode = data.get('mode', '')
    ts = datetime.now(timezone.utc).isoformat()
    if not user or not msg:
        abort(400, 'Missing fields')
    try:
        if mode == 'user_to_bot':
            process_openai.delay(user, msg)
        else:
            send_whatsapp(user, msg)
            log_message(ts, 'outbound', user, msg)
            human_window = int(os.getenv("HUMAN_ACTIVE_WINDOW", 1800))
            redis_connection.set(f"escalation_hold:{user}", "1", ex=human_window)
        return jsonify({'status': 'ok', 'to': user})
    except Exception as e:
        app.logger.error(f'Respond error: {e}')
        abort(500, 'Error responding')


@app.route('/admin/escalations')
def list_escalations():
    if not session.get('logged_in'):
        abort(401)
    return jsonify(get_escalated_threads())


@app.route('/admin/escalations/<path:user_number>/resolve', methods=['POST'])
def resolve_escalation(user_number):
    if not session.get('logged_in'):
        abort(401)
    phone = normalize_phone(user_number)
    if not phone:
        return jsonify({'status': 'error', 'message': 'Invalid phone number'}), 400
    set_escalation_status(phone, 'bot')
    reset_neg_streak(phone)
    logger.info(f"[escalation] {phone} resolved by admin — returned to bot")
    return jsonify({'status': 'ok', 'user': phone})


@app.route('/get_templates')
def get_templates():
    if not session.get('logged_in'):
        abort(401)
    try:
        client = get_twilio_client()
        templates = [
            {'label': c.friendly_name, 'value': c.sid}
            for c in client.content.v1.contents.list()
        ]
        return jsonify(templates)
    except Exception as e:
        app.logger.error(f'Template fetch error: {e}')
        return jsonify({'error': 'Could not fetch templates'}), 500


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

@app.route('/metrics')
def metrics():
    if not session.get('logged_in'):
        abort(401)
    stats = connection_health_check()
    lines = [
        f"db_connections_available {stats.get('available', 0)}",
        f"db_connections_active {stats.get('active', 0)}",
        f"db_messages_total {stats.get('message_count', 0)}"
    ]
    return Response("\n".join(lines), mimetype='text/plain')


@app.route('/health')
@limiter.exempt
def health():
    logger.info("✅ /health checked")
    return jsonify({'status': 'ok'}), 200


# ---------------------------------------------------------------------------
# Heartbeat thread
# ---------------------------------------------------------------------------

def _heartbeat():
    while True:
        logger.info("💓 Heartbeat - Flask is alive")
        time.sleep(600)

threading.Thread(target=_heartbeat, daemon=True).start()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False)
