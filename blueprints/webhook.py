"""
blueprints/webhook.py — Twilio WhatsApp webhook with per-tenant routing.

  POST /whatsapp/<tenant_slug>  — incoming WhatsApp messages
"""
import os
from datetime import datetime, timezone

from flask import Blueprint, request, abort
from twilio.request_validator import RequestValidator

from db import log_message
from logati import logger
from redis_client import get_tenant_redis
from services.tenant_service import resolve_tenant_by_slug, get_effective_config_value
from utils import normalize_phone

webhook_bp = Blueprint('webhook', __name__)

TWILIO_AUTH_TOKEN       = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER  = os.getenv('TWILIO_WHATSAPP_NUMBER', '')


@webhook_bp.route('/whatsapp/<tenant_slug>', methods=['POST'])
def whatsapp_webhook_tenant(tenant_slug: str):
    """Per-tenant webhook: /whatsapp/acme receives messages for the 'acme' tenant."""
    # 1. Resolve tenant
    tenant = resolve_tenant_by_slug(tenant_slug)
    if not tenant:
        abort(404)
    if tenant.get('status') in ('suspended', 'cancelled'):
        abort(403)

    tenant_id = str(tenant['id'])

    # 2. Load config to get the correct auth token
    try:
        from services.tenant_service import load_tenant_context
        config, _ = load_tenant_context(tenant_id)
    except Exception:
        config = {}

    auth_token = get_effective_config_value(
        config, 'twilio_auth_token', 'TWILIO_AUTH_TOKEN', TWILIO_AUTH_TOKEN,
    )

    # 3. Validate Twilio signature
    validator = RequestValidator(auth_token)
    signature = request.headers.get('X-Twilio-Signature', '')
    if not validator.validate(request.url, request.form, signature):
        logger.warning(f'❌ Invalid Twilio signature for tenant {tenant_slug}')
        abort(403)

    # 4. Extract message
    msg      = request.form.get('Body', '').strip()
    user_raw = request.form.get('From', '').strip()
    user     = normalize_phone(user_raw)

    # Ignore self-callback
    whatsapp_number = get_effective_config_value(
        config, 'twilio_whatsapp_number', 'TWILIO_WHATSAPP_NUMBER', TWILIO_WHATSAPP_NUMBER,
    )
    if user == normalize_phone(whatsapp_number):
        return 'Ignored status callback', 200

    if not msg or not user:
        return 'Ignored invalid message', 200

    # 5. Dedup via tenant-scoped Redis key
    r = get_tenant_redis(tenant_id)
    message_sid = request.form.get('MessageSid') or request.form.get('SmsSid', '')
    if message_sid:
        dedup_key = f'msg:{message_sid}'
        if r.get(dedup_key):
            return 'Duplicate', 200
        r.set(dedup_key, 'processed', ex=3600)

    # 6. Log inbound message
    timestamp = datetime.now(timezone.utc).isoformat()
    log_message(timestamp, 'inbound', user, msg, tenant_id=tenant_id)

    # 7. Dispatch OpenAI task with tenant_id
    try:
        from tasks import process_openai
        process_openai.delay(tenant_id, user, msg)
        logger.info(f'🚦 Dispatched task for {user} [tenant={tenant_slug}]')
    except Exception as e:
        logger.error(f'❌ Webhook dispatch failed for {tenant_slug}: {e}', exc_info=True)
        return 'Task dispatch failed but acknowledged', 200

    return 'OK', 200


@webhook_bp.route('/whatsapp', methods=['POST'])
def whatsapp_webhook_legacy():
    """Legacy endpoint removed — all webhooks must use /whatsapp/<tenant_slug>."""
    abort(410)
