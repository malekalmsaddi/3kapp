"""
services/ai/factory.py — AI provider factory.

Creates the correct AIProvider implementation based on the tenant's
assistant_config.provider setting.
"""
from services.ai.base import AIConfig, TenantContext, AIProvider
from redis_client import TenantRedis


def get_ai_provider(
    ai_config: AIConfig,
    tenant_ctx: TenantContext,
    tenant_redis: TenantRedis,
) -> AIProvider:
    """Instantiate the correct AI provider for the given config."""
    if ai_config.provider == 'openai_assistants':
        from services.ai.openai_assistants import OpenAIAssistantsProvider
        return OpenAIAssistantsProvider(ai_config, tenant_ctx, tenant_redis)
    elif ai_config.provider == 'openai_responses':
        # Future: OpenAI Responses API provider
        raise NotImplementedError(
            f'Provider "openai_responses" is not yet implemented. '
            f'Use "openai_assistants" for now.'
        )
    else:
        raise ValueError(f'Unknown AI provider: {ai_config.provider}')


def build_ai_config(raw: dict) -> AIConfig:
    """Build an AIConfig dataclass from a raw assistant_configs DB row."""
    tools = raw.get('tools_enabled', ['escalate_to_human'])
    if isinstance(tools, str):
        import json
        tools = json.loads(tools)

    api_key      = raw.get('openai_api_key', '')
    assistant_id = raw.get('assistant_id', '')
    if not api_key or not assistant_id:
        raise ValueError(
            f'AI config is missing required fields: '
            f'{"openai_api_key" if not api_key else "assistant_id"}'
        )

    return AIConfig(
        provider=raw.get('provider', 'openai_assistants'),
        api_key=api_key,
        assistant_id=assistant_id,
        model=raw.get('model', 'gpt-4o'),
        tools_enabled=tools,
        temperature=float(raw['temperature']) if raw.get('temperature') is not None else None,
        max_poll_seconds=int(raw.get('max_poll_seconds', 90)),
        lock_expiry_seconds=int(raw.get('lock_expiry_seconds', 300)),
        max_tool_rounds=int(raw.get('max_tool_rounds', 10)),
        sentiment_enabled=bool(raw.get('sentiment_enabled', True)),
        sentiment_model=raw.get('sentiment_model', 'gpt-4o-mini'),
    )


def build_tenant_context(tenant_id: str, config: dict) -> TenantContext:
    """Build a TenantContext from a raw tenant_configs DB row."""
    # Default escalation/placeholder messages (fallback if tenant hasn't customized)
    default_escalation = (
        "We're connecting you with a member of our team. Please hold on. 🙏\n\n"
        "نقوم بتحويلك إلى أحد أعضاء فريقنا. يرجى الانتظار. 🙏"
    )
    default_placeholder = '💭 Processing your message... يرجى الإنتظار'

    return TenantContext(
        tenant_id=tenant_id,
        twilio_config={
            'account_sid': config.get('twilio_account_sid'),
            'auth_token': config.get('twilio_auth_token'),
            'whatsapp_number': config.get('twilio_whatsapp_number'),
            'service_sid': config.get('twilio_service_sid'),
        },
        calendar_config={
            'enabled': bool(config.get('calendar_enabled')),
            'credentials': config.get('calendar_credentials'),
            'calendar_id': config.get('calendar_id'),
            'timezone': config.get('calendar_timezone', 'UTC'),
        },
        email_config={
            'api_key': config.get('sendgrid_api_key'),
            'sender_email': config.get('sender_email'),
            'sender_name': config.get('sender_name'),
        },
        escalation_msg=config.get('escalation_msg') or default_escalation,
        placeholder_msg=config.get('placeholder_msg') or default_placeholder,
        human_active_window_sec=int(config.get('human_active_window_sec', 1800)),
        default_country_code=config.get('default_country_code', '974'),
        max_twilio_length=int(config.get('max_twilio_length', 1550)),
    )
