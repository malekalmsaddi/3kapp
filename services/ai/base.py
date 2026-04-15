"""
services/ai/base.py — Abstract base classes for AI providers.

The AIProvider ABC defines the contract that all AI backends must satisfy.
Currently implemented: OpenAI Assistants v2.
Future: OpenAI Responses API, Anthropic Claude, etc.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class AIConfig:
    """Per-tenant AI provider configuration loaded from assistant_configs."""
    provider: str               # 'openai_assistants' | 'openai_responses'
    api_key: str
    assistant_id: str
    model: str
    tools_enabled: list[str]    = field(default_factory=lambda: ['escalate_to_human'])
    temperature: float | None   = None
    max_poll_seconds: int       = 90
    lock_expiry_seconds: int    = 300
    max_tool_rounds: int        = 10
    sentiment_enabled: bool     = True
    sentiment_model: str        = 'gpt-4o-mini'


@dataclass
class TenantContext:
    """Runtime context for a tenant, carrying credentials and settings
    needed by tool handlers (email, calendar, escalation)."""
    tenant_id: str
    twilio_config: dict         # whatsapp_number, account_sid, auth_token, service_sid
    calendar_config: dict       # credentials, calendar_id, timezone, enabled
    email_config: dict          # api_key, sender_email, sender_name
    escalation_msg: str
    placeholder_msg: str
    human_active_window_sec: int = 1800
    default_country_code: str   = '974'
    max_twilio_length: int      = 1550


class AIProvider(ABC):
    """Abstract AI provider.  Each implementation wraps a specific AI backend."""

    def __init__(self, ai_config: AIConfig, tenant_ctx: TenantContext):
        self.ai_config  = ai_config
        self.tenant_ctx = tenant_ctx

    @abstractmethod
    def generate(
        self,
        prompt: str,
        user_number: str,
        notify_fn: Optional[Callable] = None,
    ) -> Optional[str]:
        """Process a user message and return the assistant's reply.

        Returns:
            str   — assistant reply text (may be empty string if queued)
            None  — escalation was triggered (caller must not send additional reply)
            ""    — run queued, caller should trigger monitor_and_flush task
        """

    @abstractmethod
    def get_or_create_thread(self, user_number: str) -> str:
        """Return the thread_id for this user, creating a new thread if needed."""

    @abstractmethod
    def flush_queue(self, thread_id: str, user_number: str):
        """Process any queued messages for a thread after a run completes."""

    @abstractmethod
    def analyze_sentiment(self, message: str) -> str:
        """Analyze sentiment of a message. Returns 'positive', 'neutral', or 'negative'."""
