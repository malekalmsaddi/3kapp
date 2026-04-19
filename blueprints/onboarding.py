"""
blueprints/onboarding.py — Tenant onboarding wizard endpoints.

  GET  /onboarding/status         — current onboarding state
  POST /onboarding/assistant      — Step 1: AI assistant config
  POST /onboarding/whatsapp       — Step 2: Twilio config
  POST /onboarding/calendar       — Step 3: Google Calendar (optional)
  POST /onboarding/branding       — Step 4: Brand customization
  POST /onboarding/complete       — Step 5: Mark done
"""
import json

from flask import Blueprint, request, jsonify, abort, g

from db import (
    get_tenant_by_id, update_tenant_config, update_assistant_config,
    update_onboarding_step, complete_onboarding, log_audit,
)
from crypto import encrypt
from middleware.jwt_middleware import require_auth
from logati import logger
from services.tenant_service import invalidate_tenant_cache

onboarding_bp = Blueprint('onboarding', __name__)


def _get_tenant_id() -> str:
    if not g.tenant_id:
        abort(403, 'No tenant context')
    return g.tenant_id


@onboarding_bp.route('/status')
@require_auth
def onboarding_status():
    from db import get_conn
    from psycopg2.extras import RealDictCursor
    tenant_id = _get_tenant_id()
    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                'SELECT * FROM onboarding_state WHERE tenant_id = %s',
                (tenant_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({'current_step': 'assistant', 'completed_steps': [], 'completed': False})
            return jsonify({
                'current_step': row['current_step'],
                'completed_steps': row['completed_steps'],
                'completed': row['completed_at'] is not None,
            })
    except Exception as e:
        logger.error(f'Onboarding status error: {e}')
        return jsonify({'error': 'Could not load onboarding status'}), 500


@onboarding_bp.route('/assistant', methods=['POST'])
@require_auth
def onboarding_assistant():
    """Step 1: Configure OpenAI assistant."""
    tenant_id = _get_tenant_id()
    data = request.get_json() or {}
    openai_key   = data.get('openai_api_key', '').strip()
    assistant_id = data.get('assistant_id', '').strip()

    if not openai_key or not assistant_id:
        return jsonify({'error': 'openai_api_key and assistant_id required'}), 400

    # Validate by trying to retrieve the assistant
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        assistant = client.beta.assistants.retrieve(assistant_id)
        model = assistant.model or 'gpt-4o'
    except Exception as e:
        return jsonify({'error': f'Could not validate assistant: {e}'}), 400

    # Store encrypted
    update_assistant_config(tenant_id, {
        'openai_api_key': encrypt(openai_key),
        'assistant_id': assistant_id,
        'model': model,
        'tools_enabled': json.dumps(['escalate_to_human', 'send_email',
                                      'create_calendar_event', 'get_available_time_slots']),
    })
    update_onboarding_step(tenant_id, 'whatsapp', ['assistant'])
    invalidate_tenant_cache(tenant_id)

    log_audit(tenant_id=tenant_id, actor_user_id=g.user_id,
              action='onboarding.assistant', ip_address=request.remote_addr)

    return jsonify({'status': 'ok', 'next_step': 'whatsapp', 'model': model})


@onboarding_bp.route('/whatsapp', methods=['POST'])
@require_auth
def onboarding_whatsapp():
    """Step 2: Configure Twilio/WhatsApp."""
    tenant_id = _get_tenant_id()
    data = request.get_json() or {}

    # Per-tenant creds are optional (Pro plan feature)
    updates = {}
    if data.get('twilio_account_sid'):
        updates['twilio_account_sid']     = encrypt(data['twilio_account_sid'].strip())
        updates['twilio_auth_token']      = encrypt(data.get('twilio_auth_token', '').strip())
        updates['twilio_whatsapp_number'] = data.get('twilio_whatsapp_number', '').strip()
        updates['twilio_service_sid']     = data.get('twilio_service_sid', '').strip() or None

    if updates:
        update_tenant_config(tenant_id, updates)

    update_onboarding_step(tenant_id, 'calendar', ['assistant', 'whatsapp'])
    invalidate_tenant_cache(tenant_id)

    # Return the webhook URL the tenant should register in Twilio
    tenant = get_tenant_by_id(tenant_id)
    webhook_url = f'/whatsapp/{tenant["slug"]}' if tenant else ''

    log_audit(tenant_id=tenant_id, actor_user_id=g.user_id,
              action='onboarding.whatsapp', ip_address=request.remote_addr)

    return jsonify({'status': 'ok', 'next_step': 'calendar', 'webhook_url': webhook_url})


@onboarding_bp.route('/calendar', methods=['POST'])
@require_auth
def onboarding_calendar():
    """Step 3: Configure Google Calendar (optional)."""
    tenant_id = _get_tenant_id()
    data = request.get_json() or {}
    skip = data.get('skip', False)

    if skip:
        update_onboarding_step(tenant_id, 'branding', ['assistant', 'whatsapp', 'calendar'])
        return jsonify({'status': 'ok', 'next_step': 'branding', 'skipped': True})

    calendar_id   = data.get('calendar_id', '').strip()
    timezone      = data.get('timezone', 'UTC').strip()
    credentials   = data.get('credentials')  # JSON object (service account key)

    if not calendar_id or not credentials:
        return jsonify({'error': 'calendar_id and credentials required (or skip: true)'}), 400

    update_tenant_config(tenant_id, {
        'calendar_enabled': True,
        'calendar_id': calendar_id,
        'calendar_timezone': timezone,
        'calendar_credentials': encrypt(json.dumps(credentials)),
    })
    update_onboarding_step(tenant_id, 'branding', ['assistant', 'whatsapp', 'calendar'])
    invalidate_tenant_cache(tenant_id)

    log_audit(tenant_id=tenant_id, actor_user_id=g.user_id,
              action='onboarding.calendar', ip_address=request.remote_addr)

    return jsonify({'status': 'ok', 'next_step': 'branding'})


@onboarding_bp.route('/branding', methods=['POST'])
@require_auth
def onboarding_branding():
    """Step 4: Brand customization."""
    tenant_id = _get_tenant_id()
    data = request.get_json() or {}

    brand_name      = data.get('brand_name', '').strip()
    color_primary   = data.get('brand_color_primary', '').strip()
    color_secondary = data.get('brand_color_secondary', '').strip()
    logo_url        = data.get('brand_logo_url', '').strip()

    from db import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            updates = []
            params = []
            if brand_name:
                updates.append('brand_name = %s')
                params.append(brand_name)
            if color_primary:
                updates.append('brand_color_primary = %s')
                params.append(color_primary)
            if color_secondary:
                updates.append('brand_color_secondary = %s')
                params.append(color_secondary)
            if logo_url:
                updates.append('brand_logo_url = %s')
                params.append(logo_url)
            if updates:
                updates.append('updated_at = NOW()')
                params.append(tenant_id)
                cur.execute(
                    f"UPDATE tenants SET {', '.join(updates)} WHERE id = %s",
                    params,
                )

    update_onboarding_step(
        tenant_id, 'done',
        ['assistant', 'whatsapp', 'calendar', 'branding'],
    )
    invalidate_tenant_cache(tenant_id)

    log_audit(tenant_id=tenant_id, actor_user_id=g.user_id,
              action='onboarding.branding', ip_address=request.remote_addr)

    return jsonify({'status': 'ok', 'next_step': 'done'})


@onboarding_bp.route('/complete', methods=['POST'])
@require_auth
def onboarding_complete_endpoint():
    """Step 5: Mark onboarding as complete."""
    tenant_id = _get_tenant_id()
    complete_onboarding(tenant_id)

    log_audit(tenant_id=tenant_id, actor_user_id=g.user_id,
              action='onboarding.complete', ip_address=request.remote_addr)

    return jsonify({'status': 'ok', 'message': 'Onboarding complete'})
