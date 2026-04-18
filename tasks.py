"""
tasks.py — Celery task definitions.

All tasks accept tenant_id as their first positional argument.
At the top of each task, tenant config is loaded and a TenantRedis
wrapper is created for namespaced Redis operations.
"""
import os
import json
import csv
import io
import ssl
import time
from datetime import datetime, timezone
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv()

from celery import Celery, shared_task
from celery.exceptions import SoftTimeLimitExceeded, MaxRetriesExceededError
from celery.signals import after_setup_logger
from twilio.base.exceptions import TwilioRestException

from db import (
    init_db, log_message, update_message_sentiment,
    set_escalation_status, get_user_escalation_status,
    get_messages_since_escalation, log_usage_event,
    LEGACY_TENANT_ID,
)
from logati import logger
from redis_client import redis_connection as redis_client, get_tenant_redis
from utils import normalize_phone, send_whatsapp, PHONE_REGEX
from twilio_helpers import get_twilio_client, notify_error, send_placeholder

# ─────────────────────────────────────────────────────────────────────────────
# Celery configuration
# ─────────────────────────────────────────────────────────────────────────────

if os.getenv('RUN_INIT_DB', 'false').lower() == 'true':
    required_vars = ['REDIS_URL', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise RuntimeError(f'Missing required environment variables: {missing}')
    logger.info('✅ Initializing DB from worker...')
    init_db()

REDIS_URL = os.getenv('REDIS_URL')
CELERY_BROKER  = REDIS_URL
CELERY_BACKEND = REDIS_URL

TASK_TIMEOUTS = {
    'process_openai': (90, 100),
    'send_template':  (15, 20),
    'process_bulk':   (600, 650),
    'default':        (30, 35),
}

celery_app = Celery('moeen_tasks', broker=CELERY_BROKER, backend=CELERY_BACKEND)

_celery_conf = dict(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_track_started=True,
    worker_prefetch_multiplier=int(os.getenv('WORKER_PREFETCH', 1)),
    task_soft_time_limit=TASK_TIMEOUTS['default'][0],
    task_time_limit=TASK_TIMEOUTS['default'][1],
    broker_connection_retry_on_startup=True,
    task_default_retry_delay=int(os.getenv('TASK_RETRY_DELAY', 30)),
)
if REDIS_URL and REDIS_URL.startswith('rediss://'):
    _celery_conf['broker_use_ssl'] = {'ssl_cert_reqs': ssl.CERT_NONE}
    _celery_conf['redis_backend_use_ssl'] = {'ssl_cert_reqs': ssl.CERT_NONE}

celery_app.conf.update(**_celery_conf)

def setup_loggers(logger_inst, *args, **kwargs):
    logger_inst.setLevel(os.getenv('CELERY_LOG_LEVEL', 'INFO'))
after_setup_logger.connect(setup_loggers)

# ── Legacy env-based config (used as fallback if tenant config unavailable) ──
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')
TWILIO_SERVICE_SID     = os.getenv('TWILIO_SERVICE_SID')
TEMPLATE_CONTENT_SID   = os.getenv('TEMPLATE_CONTENT_SID')
BULK_MAX_BATCH = int(os.getenv('BULK_MAX_BATCH', 500))
BULK_DAILY_CAP = int(os.getenv('BULK_DAILY_CAP', 1000))
BULK_MSG_DELAY = float(os.getenv('BULK_MSG_DELAY', 1.5))

# Register Celery Beat schedule for nightly usage rollup
try:
    from services.usage_rollup import register_beat_schedule
    register_beat_schedule(celery_app)
except Exception as e:
    logger.warning(f'Could not register beat schedule: {e}')

# ─────────────────────────────────────────────────────────────────────────────
# Tenant context loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_ai_provider(tenant_id: str):
    """Load AI provider + TenantRedis for the given tenant."""
    from services.tenant_service import load_tenant_context
    from services.ai.factory import get_ai_provider, build_ai_config, build_tenant_context

    config, ai_config_raw = load_tenant_context(tenant_id)
    ai_config   = build_ai_config(ai_config_raw)
    tenant_ctx  = build_tenant_context(tenant_id, config)
    r           = get_tenant_redis(tenant_id)
    provider    = get_ai_provider(ai_config, tenant_ctx, r)
    return provider, config, r


# ─────────────────────────────────────────────────────────────────────────────
# Per-tenant daily cap helpers
# ─────────────────────────────────────────────────────────────────────────────

def _daily_cap_key() -> str:
    return f"bulk:daily:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

def _get_daily_sent(tenant_redis=None) -> int:
    r = tenant_redis or redis_client
    try:
        val = r.get(_daily_cap_key())
        return int(val) if val else 0
    except Exception:
        return 0

def _incr_daily_sent(tenant_redis=None) -> None:
    r = tenant_redis or redis_client
    try:
        key = _daily_cap_key()
        r.incr(key)
        r.expire(key, 90000)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Task: process_openai
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(name='tasks.process_openai', bind=True, max_retries=3,
             soft_time_limit=TASK_TIMEOUTS['process_openai'][0],
             time_limit=TASK_TIMEOUTS['process_openai'][1])
def process_openai(self, tenant_id: str, user_number: str, user_message: str = ''):
    """Process a user message via OpenAI and reply over WhatsApp."""
    provider, config, r = _load_ai_provider(tenant_id)

    try:
        # 1. Escalation gate
        escalation_status = get_user_escalation_status(user_number, tenant_id=tenant_id)
        if escalation_status == 'escalated':
            if r.get(f'escalation_hold:{user_number}'):
                return {'status': 'human_active', 'to': user_number}
            else:
                set_escalation_status(user_number, 'bot', tenant_id=tenant_id)
                r.delete(f'neg_streak:{user_number}')
                missed = get_messages_since_escalation(user_number, tenant_id=tenant_id)
                if len(missed) > 1:
                    user_message = (
                        '[Context: user waited for a team member who stopped replying. '
                        'All messages during wait:]\n\n'
                        + '\n'.join(f'- {m}' for m in missed)
                    )

        # 2. Sentiment
        sentiment = provider.analyze_sentiment(user_message)
        update_message_sentiment(user_number, user_message, sentiment, tenant_id=tenant_id)

        # 3. Generate
        response = provider.generate(
            user_message, user_number,
            notify_fn=lambda num: send_placeholder(num),
        )

        if response is None:
            log_usage_event(tenant_id, 'ai.run', metadata={'escalated': True})
            return {'status': 'escalated', 'to': user_number}

        if response == '':
            from tasks import monitor_openai_thread_and_flush
            monitor_openai_thread_and_flush.delay(tenant_id, user_number)
            return {'status': 'queued', 'to': user_number}

        # 4. Send reply
        client = get_twilio_client()
        from_whatsapp = f"whatsapp:{normalize_phone(config.get('twilio_whatsapp_number') or TWILIO_WHATSAPP_NUMBER)}"
        to_whatsapp   = f"whatsapp:{normalize_phone(user_number)}"
        client.messages.create(from_=from_whatsapp, to=to_whatsapp, body=response)
        log_message(datetime.now(timezone.utc).isoformat(), 'outbound', user_number, response,
                    tenant_id=tenant_id)
        log_usage_event(tenant_id, 'ai.run')
        log_usage_event(tenant_id, 'message.outbound')
        return {'status': 'sent', 'to': user_number}

    except SoftTimeLimitExceeded:
        notify_error(user_number, '⚠️ Taking longer than expected. Try again later.')
        return {'status': 'timeout', 'to': user_number}
    except Exception as exc:
        logger.exception('OpenAI task failed')
        try:
            self.retry(countdown=int(os.getenv('TASK_RETRY_DELAY', 10)))
        except MaxRetriesExceededError:
            notify_error(user_number, '⚠️ Something went wrong. Please try again.')


# ─────────────────────────────────────────────────────────────────────────────
# Task: monitor_openai_thread_and_flush
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(name='tasks.monitor_openai_thread_and_flush')
def monitor_openai_thread_and_flush(tenant_id: str, user_number: str = ''):
    """Wait for an active OpenAI run to complete, then flush queued messages."""
    provider, config, r = _load_ai_provider(tenant_id)

    thread_id = provider.get_or_create_thread(user_number)

    # Wait for active run to complete
    for _ in range(15):
        if not r.get(f'active_run:thread:{thread_id}'):
            break
        time.sleep(5)
    r.delete(f'active_run:thread:{thread_id}')

    run = provider.flush_queue(thread_id, user_number)
    if not run:
        return

    try:
        run = provider._poll(thread_id, run.id, user_number)
        response = provider._fetch_response(thread_id, run.id)
        if response:
            send_whatsapp(user_number, response)
            log_message(datetime.now(timezone.utc).isoformat(), 'outbound', user_number, response,
                        tenant_id=tenant_id)
            log_usage_event(tenant_id, 'message.outbound')
    except Exception as e:
        logger.exception(f'Flush error: {e}')
        try:
            notify_error(user_number, '⚠️ Something went wrong.')
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Task: send_bulk_contacts
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True,
                 soft_time_limit=TASK_TIMEOUTS['process_bulk'][0],
                 time_limit=TASK_TIMEOUTS['process_bulk'][1])
def send_bulk_contacts(self, tenant_id: str, payload: list, content_sid: str = None):
    """Send bulk WhatsApp template messages for a tenant."""
    r = get_tenant_redis(tenant_id)
    from services.tenant_service import load_tenant_context
    config, _ = load_tenant_context(tenant_id)
    bulk_max_batch = int(config.get('bulk_max_batch', BULK_MAX_BATCH))
    bulk_daily_cap = int(config.get('bulk_daily_cap', BULK_DAILY_CAP))
    bulk_msg_delay = float(config.get('bulk_msg_delay_sec', BULK_MSG_DELAY))

    total = len(payload)

    if total > bulk_max_batch:
        try:
            r.set(f'progress:{self.request.id}', f'0/{total}', ex=86400)
            r.rpush(f'log:{self.request.id}', json.dumps({
                'to': '—', 'result': 'rejected',
                'reason': f'Batch {total} > max {bulk_max_batch}',
            }))
        except Exception:
            pass
        return {'status': 'rejected', 'reason': 'batch_too_large', 'total': total}

    seen = set()
    dedup_key = f'dedup:{self.request.id}'
    try:
        r.expire(dedup_key, 86400)
    except Exception:
        pass

    for idx, entry in enumerate(payload, start=1):
        raw_to = entry.get('to', '').strip()
        to = normalize_phone(raw_to)
        result, reason = 'queued', ''

        if not to or not PHONE_REGEX.match(to):
            result, reason = 'failed', 'Invalid phone number'
        elif to in seen:
            result, reason = 'skipped', 'Duplicate (this job)'
        else:
            try:
                if r.sismember(dedup_key, to):
                    result, reason = 'skipped', 'Duplicate (sent within 24h)'
            except Exception:
                pass

        if result == 'queued':
            daily_sent = _get_daily_sent(r)
            if daily_sent >= bulk_daily_cap:
                result, reason = 'skipped', f'Daily cap {bulk_daily_cap} reached'

        if result == 'queued':
            params = {k: entry.get(k, '') for k in ('param1', 'param2')}
            try:
                send_whatsapp_template.apply_async(
                    args=(tenant_id, to, params, content_sid),
                    countdown=idx * bulk_msg_delay,
                )
                seen.add(to)
                try:
                    r.sadd(dedup_key, to)
                except Exception:
                    pass
                _incr_daily_sent(r)
            except Exception as e:
                result, reason = 'failed', f'Dispatch error: {e}'

        try:
            log_entry = {'to': raw_to, 'result': result}
            if reason:
                log_entry['reason'] = reason
            r.rpush(f'log:{self.request.id}', json.dumps(log_entry))
            r.set(f'progress:{self.request.id}', f'{idx}/{total}')
        except Exception:
            pass

    for key in [f'log:{self.request.id}', f'progress:{self.request.id}', dedup_key]:
        try:
            r.expire(key, 86400)
        except Exception:
            pass

    log_usage_event(tenant_id, 'bulk.send', quantity=len(seen))


# ─────────────────────────────────────────────────────────────────────────────
# Task: send_whatsapp_template
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(name='tasks.send_whatsapp_template', bind=True, max_retries=5,
             soft_time_limit=TASK_TIMEOUTS['send_template'][0],
             time_limit=TASK_TIMEOUTS['send_template'][1])
def send_whatsapp_template(self, tenant_id: str, to: str, params: dict = None, content_sid: str = None):
    """Send a single WhatsApp template message for a tenant."""
    r = get_tenant_redis(tenant_id)
    from services.tenant_service import load_tenant_context
    config, _ = load_tenant_context(tenant_id)
    whatsapp_num = config.get('twilio_whatsapp_number') or TWILIO_WHATSAPP_NUMBER
    service_sid  = config.get('twilio_service_sid') or TWILIO_SERVICE_SID
    template_sid = content_sid or config.get('extra', {}).get('template_content_sid') or TEMPLATE_CONTENT_SID

    try:
        client = get_twilio_client()
        create_kwargs = {
            'to': f'whatsapp:{to}',
            'content_sid': template_sid,
            'content_variables': json.dumps(params or {}),
        }
        if service_sid:
            create_kwargs['messaging_service_sid'] = service_sid
        else:
            create_kwargs['from_'] = f'whatsapp:{normalize_phone(whatsapp_num)}'

        msg = client.messages.create(**create_kwargs)
        log_message(datetime.now(timezone.utc).isoformat(), 'outbound', to,
                    f'TEMPLATE: {params}', tenant_id=tenant_id)
        log_usage_event(tenant_id, 'message.outbound')
        return {'status': 'sent', 'sid': msg.sid, 'to': to}

    except SoftTimeLimitExceeded:
        return {'status': 'timeout', 'to': to}
    except TwilioRestException as exc:
        if exc.status == 429:
            backoff = min(60 * (2 ** self.request.retries), 960)
            raise self.retry(countdown=backoff)
        elif 400 <= exc.status < 500:
            return {'status': 'failed', 'to': to, 'twilio_code': exc.code, 'reason': exc.msg}
        else:
            raise self.retry(countdown=int(os.getenv('TEMPLATE_RETRY_DELAY', 60)))
    except Exception:
        logger.exception(f'Template send error to {to}')
        raise self.retry(countdown=int(os.getenv('TEMPLATE_RETRY_DELAY', 60)))


# ─────────────────────────────────────────────────────────────────────────────
# Task: process_bulk_file
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=2,
             soft_time_limit=TASK_TIMEOUTS['process_bulk'][0],
             time_limit=TASK_TIMEOUTS['process_bulk'][1])
def process_bulk_file(self, tenant_id: str, file_contents: str = ''):

    results = defaultdict(list)
    reader = csv.DictReader(io.StringIO(file_contents))
    if not reader.fieldnames:
        return {'status': 'failed', 'error': 'CSV empty or invalid'}

    idx = 0
    for idx, row in enumerate(reader, start=1):
        phone_raw = row.get('to', '')
        phone = normalize_phone(phone_raw)
        if not phone or not PHONE_REGEX.match(phone):
            results['invalid_phone'].append(idx)
            continue
        params = {k: v.strip() for k, v in row.items() if k.startswith('param') and v.strip()}
        if not params:
            results['missing_params'].append(idx)
            continue
        try:
            send_whatsapp_template.apply_async(args=(tenant_id, phone, params))
            results['success'].append(idx)
            log_message(datetime.now(timezone.utc).isoformat(), 'outbound', phone,
                        f'BULK: {params}', tenant_id=tenant_id)
        except Exception:
            results['failed'].append(idx)

    total = idx
    rate = f"{len(results['success'])/total:.1%}" if total else '0%'
    return {'status': 'completed', 'total_rows': total, 'results': dict(results), 'success_rate': rate}
