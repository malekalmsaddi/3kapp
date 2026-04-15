"""
services/ai/openai_assistants.py — OpenAI Assistants v2 provider.

Tenant-aware implementation that wraps the logic from the old llm_utils.py.
Each instance receives per-tenant AIConfig + TenantContext so it uses
the correct API key, assistant ID, credentials, and Redis namespace.
"""
import os
import json
import time
import uuid
from contextlib import contextmanager
from typing import Optional, Callable

import httpx
from openai import OpenAI, BadRequestError, OpenAIError

from services.ai.base import AIProvider, AIConfig, TenantContext
from db import get_or_create_thread_id, set_escalation_status, log_message
from redis_client import TenantRedis
from logati import logger

BACKOFF_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]


class PollTimeout(Exception):
    pass


class OpenAIAssistantsProvider(AIProvider):
    """Concrete AI provider backed by OpenAI Assistants API v2."""

    def __init__(self, ai_config: AIConfig, tenant_ctx: TenantContext, tenant_redis: TenantRedis):
        super().__init__(ai_config, tenant_ctx)
        self._client = OpenAI(
            api_key=ai_config.api_key,
            http_client=httpx.Client(
                event_hooks={
                    'request':  [lambda req: logger.debug(f'➡️ OpenAI [{tenant_ctx.tenant_id[:8]}]: {req.method} {req.url}')],
                    'response': [lambda res: logger.debug(f'⬅️ OpenAI [{tenant_ctx.tenant_id[:8]}]: {res.status_code}')],
                },
            ),
        )
        self._r = tenant_redis
        self._max_twilio = tenant_ctx.max_twilio_length
        self._lock_expiry = ai_config.lock_expiry_seconds

    # ── Thread management ────────────────────────────────────────────────
    def get_or_create_thread(self, user_number: str) -> str:
        return get_or_create_thread_id(
            user_id=user_number,
            tenant_id=self.tenant_ctx.tenant_id,
            openai_api_key=self.ai_config.api_key,
        )

    # ── Main generate ────────────────────────────────────────────────────
    def generate(self, prompt: str, user_number: str, notify_fn: Optional[Callable] = None) -> Optional[str]:
        start_total = time.monotonic()

        short = prompt.strip().lower()
        if len(prompt.strip()) < 4 and short not in {'hi', 'ok', 'yes', 'لا', 'شو', 'كيف', 'متى'}:
            return '📝 Could you please provide more detail? Your message is too short.'

        thread_id = self.get_or_create_thread(user_number)
        active_key = f'active_run:thread:{thread_id}'
        queue_key  = f'queue:thread:{thread_id}'
        lock_key   = f'lock:thread:{thread_id}'

        # Check for active run
        if self._has_active_run(thread_id):
            self._r.rpush(queue_key, prompt)
            return ''

        lock_id = str(uuid.uuid4())
        with self._redis_lock(lock_key, lock_id) as acquired:
            if not acquired:
                self._r.rpush(queue_key, prompt)
                return ''
            self._r.set(active_key, '1', ex=self._lock_expiry)
            try:
                # Submit user message
                self._submit_message(thread_id, prompt, user_number)

                # Start run
                run = self._start_run(thread_id)

                # Poll
                run = self._poll(thread_id, run.id, user_number, notify_fn=notify_fn)

                # Handle tool calls
                escalation_flag = []
                tool_rounds = 0
                max_rounds = self.ai_config.max_tool_rounds
                while run.status.startswith('requires_') and tool_rounds < max_rounds:
                    run = self._process_tool_calls(thread_id, run, user_number, escalation_flag)
                    run = self._poll(thread_id, run.id, user_number, notify_fn=notify_fn)
                    tool_rounds += 1

                if escalation_flag:
                    return None  # escalation triggered

                response = self._fetch_response(thread_id, run.id)
                total = time.monotonic() - start_total
                logger.info(f'✅ generate [{self.tenant_ctx.tenant_id[:8]}] took {total:.2f}s')
                return response

            except PollTimeout as e:
                logger.error(str(e))
                self._r.rpush(queue_key, prompt)
                return '😓 This took too long. I\'ve queued your message.'
            except Exception:
                logger.exception('Unexpected error during generation')
                return '⚠️ Unexpected error — please try again later.'
            finally:
                self._r.delete(active_key)

    # ── Queue flushing ───────────────────────────────────────────────────
    def flush_queue(self, thread_id: str, user_number: str):
        queue_key = f'queue:thread:{thread_id}'
        queued = self._r.lrange(queue_key, 0, -1)
        if not queued:
            return None

        prompts = [q.decode() for q in queued]
        combined = '\n\n'.join(f'User message {i+1}: {m}' for i, m in enumerate(prompts))
        self._r.delete(queue_key)

        try:
            self._submit_message(thread_id, combined, user_number)
            run = self._start_run(thread_id)
            return run
        except Exception as e:
            logger.exception(f'flush_queue failed for {thread_id}: {e}')
            self._r.rpush(queue_key, combined)
            return None

    # ── Sentiment analysis ───────────────────────────────────────────────
    def analyze_sentiment(self, message: str) -> str:
        if not self.ai_config.sentiment_enabled:
            return 'neutral'
        try:
            resp = self._client.chat.completions.create(
                model=self.ai_config.sentiment_model,
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Classify the sentiment of the following message as exactly one word: '
                            'positive, neutral, or negative. No explanation. Supports English and Arabic.'
                        ),
                    },
                    {'role': 'user', 'content': message[:500]},
                ],
                max_tokens=5,
                temperature=0,
            )
            result = resp.choices[0].message.content.strip().lower()
            return result if result in ('positive', 'neutral', 'negative') else 'neutral'
        except Exception as e:
            logger.warning(f'[sentiment] error: {e}')
            return 'neutral'

    # ── Internals ────────────────────────────────────────────────────────

    def _has_active_run(self, thread_id: str) -> bool:
        key = f'active_run:thread:{thread_id}'
        if self._r.get(key):
            return True
        try:
            runs = self._client.beta.threads.runs.list(
                thread_id=thread_id, limit=5, order='desc',
                extra_headers={'OpenAI-Beta': 'assistants=v2'},
            )
            for run in runs.data:
                if run.status in {'queued', 'in_progress'}:
                    self._r.set(key, run.id, ex=int(os.getenv('RUN_CACHE_TTL', '90')))
                    return True
        except Exception as e:
            logger.error(f'Failed to check active run for {thread_id}: {e}')
        return False

    def _submit_message(self, thread_id: str, prompt: str, user_number: str):
        content = f'(User Info: WhatsApp number = {user_number})\n\n{prompt}'
        return self._client.beta.threads.messages.create(
            thread_id=thread_id, role='user', content=content,
            extra_headers={'OpenAI-Beta': 'assistants=v2'},
        )

    def _start_run(self, thread_id: str):
        return self._client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=self.ai_config.assistant_id,
            extra_headers={'OpenAI-Beta': 'assistants=v2'},
        )

    def _poll(self, thread_id: str, run_id: str, user_number: str,
              max_total: int | None = None, notify_fn=None):
        max_total = max_total or self.ai_config.max_poll_seconds
        waited, notified = 0, False

        for interval in BACKOFF_INTERVALS:
            if waited > max_total:
                break
            try:
                run = self._client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=run_id,
                    extra_headers={'OpenAI-Beta': 'assistants=v2'},
                )
            except OpenAIError as e:
                logger.error(f'Error retrieving run {run_id}: {e}')
                raise

            status = getattr(run, 'status', None)
            if status in ('completed', 'failed', 'cancelled', 'expired',
                          'requires_action', 'requires_tool', 'requires_tools'):
                return run

            if not notified and waited >= 30 and notify_fn:
                try:
                    notify_fn(user_number)
                    notified = True
                except Exception:
                    pass

            time.sleep(interval)
            waited += interval

        # Timeout — cancel
        try:
            self._client.beta.threads.runs.cancel(
                thread_id=thread_id, run_id=run_id,
                extra_headers={'OpenAI-Beta': 'assistants=v2'},
            )
        except Exception:
            pass
        raise PollTimeout(f'Polling timeout ({max_total}s)')

    def _process_tool_calls(self, thread_id: str, run, user_number: str, escalation_flag: list):
        if run.status not in ('requires_action', 'requires_tool', 'requires_tools'):
            return run

        try:
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
        except AttributeError:
            try:
                tool_calls = run.required_action.tool_calls
            except AttributeError:
                return run

        outputs = []
        for call in tool_calls:
            fn_name = call.function.name
            args = json.loads(call.function.arguments or '{}')

            try:
                if fn_name == 'escalate_to_human':
                    result = self._handle_escalation(user_number, **args)
                    escalation_flag.append(True)
                elif fn_name == 'send_email':
                    result = self._handle_send_email(**args)
                elif fn_name == 'create_calendar_event':
                    result = self._handle_calendar_event(**args)
                elif fn_name == 'get_available_time_slots':
                    result = self._handle_time_slots(**args)
                else:
                    result = f'Unknown tool: {fn_name}'
            except Exception as e:
                logger.exception(f'Tool handler {fn_name} failed')
                result = '⚠️ Tool call failed'

            outputs.append({'tool_call_id': call.id, 'output': result})

        return self._client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id, run_id=run.id, tool_outputs=outputs,
            extra_headers={'OpenAI-Beta': 'assistants=v2'},
        )

    def _fetch_response(self, thread_id: str, run_id: str) -> str:
        messages = self._client.beta.threads.messages.list(
            thread_id=thread_id, order='desc', limit=5,
            extra_headers={'OpenAI-Beta': 'assistants=v2'},
        )
        for msg in messages.data:
            if msg.run_id == run_id and msg.role == 'assistant':
                if not msg.content or not hasattr(msg.content[0], 'text'):
                    continue
                text = msg.content[0].text.value.strip()
                if len(text) <= self._max_twilio:
                    return text
                return text[:self._max_twilio - 50] + '\n\n[⚠️ Truncated]'
        return '🤖 Could not retrieve assistant response.'

    # ── Tool handlers (use per-tenant config) ────────────────────────────

    def _handle_escalation(self, user_number: str, reason: str = '') -> str:
        from utils import send_whatsapp
        ctx = self.tenant_ctx
        human_window = ctx.human_active_window_sec
        set_escalation_status(user_number, 'escalated', tenant_id=ctx.tenant_id)
        self._r.delete(f'neg_streak:{user_number}')
        self._r.set(f'escalation_hold:{user_number}', '1', ex=human_window)
        send_whatsapp(user_number, ctx.escalation_msg)
        logger.info(f'[escalation] {user_number} escalated. Reason: {reason}')
        return 'Escalation initiated successfully.'

    def _handle_send_email(self, to_email: str, subject: str, body: str) -> str:
        from utils import send_email
        result = send_email(to_email, subject, body)
        return result.get('message', str(result.get('status', 'done')))

    def _handle_calendar_event(self, **kwargs) -> str:
        ctx = self.tenant_ctx
        if not ctx.calendar_config.get('enabled'):
            return 'Calendar not enabled for this tenant.'
        from calendar_handlers import create_calendar_event
        result = create_calendar_event(**kwargs)
        status = result.get('status', 'error')
        message = result.get('message', '')
        return f'{"SUCCESS" if status == "success" else "ERROR"}: {message}'

    def _handle_time_slots(self, **kwargs) -> str:
        ctx = self.tenant_ctx
        if not ctx.calendar_config.get('enabled'):
            return 'Calendar not enabled for this tenant.'
        from calendar_handlers import get_available_time_slots
        result = get_available_time_slots(**kwargs)
        if result.get('status') == 'error':
            return result.get('message', 'Error fetching slots')
        slots = result.get('slots', [])
        if not slots:
            return '❌ No available time slots found.'
        return '📆 Available slots:\n' + '\n'.join(f"- {s['start']} → {s['end']}" for s in slots)

    @contextmanager
    def _redis_lock(self, lock_key: str, lock_id: str, ex: int | None = None):
        ex = ex or self._lock_expiry
        acquired = self._r.set(lock_key, lock_id, nx=True, ex=ex)
        try:
            yield acquired
        finally:
            try:
                if self._r.get(lock_key) == lock_id.encode():
                    self._r.delete(lock_key)
            except Exception as e:
                logger.warning(f'Failed to release lock {lock_key}: {e}')
