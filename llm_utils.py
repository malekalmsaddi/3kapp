import os
import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from openai import OpenAI, BadRequestError, OpenAIError
from redis_client import redis_connection as r

# Local modules
from calendar_handlers import create_calendar_event, get_available_time_slots
from db import get_or_create_thread_id, set_escalation_status
from logati import logger
from sentiment import ESCALATION_MSG, reset_neg_streak
from utils import has_active_run, send_email, send_whatsapp

# Load environment variables and validate
load_dotenv()
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not ASSISTANT_ID:
    raise RuntimeError("ASSISTANT_ID environment variable must be set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable must be set")

# Configuration constants
def _safe_int(env_var: str, default: int) -> int:
    try:
        return int(os.getenv(env_var, str(default)))
    except ValueError:
        logger.warning(f"Invalid value for {env_var}, using default {default}")
        return default

MAX_TWILIO_LENGTH = _safe_int("MAX_TWILIO_LENGTH", 1550)
LOCK_EXPIRY_SECONDS = _safe_int("LOCK_EXPIRY_SECONDS", 300)  # ensure exceeds max poll time
BACKOFF_INTERVALS = [1, 2, 3, 5, 8, 13, 21, 34]


# Initialize OpenAI client with HTTPX hooks
client = OpenAI(
    api_key=OPENAI_API_KEY,
    http_client=httpx.Client(
        event_hooks={
            "request": [lambda req: logger.debug(f"➡️ OpenAI Request: {req.method} {req.url}")],
            "response": [lambda res: logger.debug(f"⬅️ OpenAI Response: {res.status_code}")]
        }
    )
)

# Redis-based active run flag
ACTIVE_RUN_PREFIX = "active_run:thread:"
QUEUE_PREFIX = "queue:thread:"
LOCK_KEY_PREFIX = "lock:thread:"


def flush_queued_messages(thread_id: str, user_number: str):
    queue_key = QUEUE_PREFIX + thread_id
    queued = r.lrange(queue_key, 0, -1)
    if not queued:
        logger.info(f"No messages to flush for {thread_id}")
        return None

    prompts = [q.decode() for q in queued]
    combined_prompt = "\n\n".join(f"User message {i+1}: {msg}" for i, msg in enumerate(prompts))
    r.delete(queue_key)

    try:
        submit_user_message(thread_id, combined_prompt, user_number)
        run = start_run(thread_id)
        logger.info(f"🌀 Flushed and started run for thread {thread_id}")
        return run
    except Exception as e:
        logger.exception(f"🔻 flush_queued_messages failed for thread {thread_id}: {e}")
        r.rpush(QUEUE_PREFIX + thread_id, combined_prompt)
        return None

# Tool handler registry
def _handle_send_email(to_email, subject, body):
    result = send_email(to_email, subject, body)
    return result.get("message", "")

def _handle_create_calendar_event(**kwargs):
    t0 = time.monotonic()
    result = create_calendar_event(**kwargs)
    elapsed = time.monotonic() - t0
    logger.info(f"🛠 create_calendar_event took {elapsed:.2f}s")
    status = result.get("status", "error")
    message = result.get("message", "")
    if status != "success":
        return f"ERROR: {message}"
    return f"SUCCESS: {message}"

def _handle_get_available_time_slots(**kwargs):
    t0 = time.monotonic()
    result = get_available_time_slots(**kwargs)
    elapsed = time.monotonic() - t0
    logger.info(f"🛠 get_available_time_slots took {elapsed:.2f}s")
    if result.get("status") == "error":
        return result.get("message", "Error fetching slots")
    slots = result.get("slots", [])
    if not slots:
        return "❌ No available time slots found."
    return "📆 Available slots:\n" + "\n".join(f"- {s['start']} → {s['end']}" for s in slots)

TOOL_HANDLERS = {
    "send_email": _handle_send_email,
    "create_calendar_event": _handle_create_calendar_event,
    "get_available_time_slots": _handle_get_available_time_slots,
}

# escalate_to_human is handled inline in process_tool_calls because it
# needs access to user_number (not passed through generic TOOL_HANDLERS)
# and must signal back to generate_with_openai to suppress the follow-up reply.
def _handle_escalate_to_human(user_number: str, reason: str = "") -> str:
    HUMAN_WINDOW = int(os.getenv("HUMAN_ACTIVE_WINDOW", 1800))
    set_escalation_status(user_number, "escalated")
    reset_neg_streak(user_number)
    r.set(f"escalation_hold:{user_number}", "1", ex=HUMAN_WINDOW)
    send_whatsapp(user_number, ESCALATION_MSG)
    logger.info(f"[escalation] {user_number} escalated via tool call. Reason: {reason}")
    return "Escalation initiated successfully."

# Redis lock context manager
def redis_lock(lock_key, lock_id, ex=LOCK_EXPIRY_SECONDS):
    @contextmanager
    def _lock():
        acquired = r.set(lock_key, lock_id, nx=True, ex=ex)
        try:
            yield acquired
        finally:
            try:
                if r.get(lock_key) == lock_id.encode():
                    r.delete(lock_key)
            except Exception as e:
                logger.warning(f"⚠️ Failed to release Redis lock for {lock_key}: {e}")
    return _lock()

# Polling with backoff


class PollTimeout(Exception):
    """Raised when polling a run exceeds the maximum allowed time."""
    pass

def poll_with_backoff(thread_id, run_id, user_number, max_total=90, notify_fn=None):
    waited = 0
    notified = False

    for interval in BACKOFF_INTERVALS:
        if waited > max_total:
            break

        try:
            run = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id,
                extra_headers={"OpenAI-Beta": "assistants=v2"}
            )
            if run is None:
                raise RuntimeError(f"⚠️ OpenAI returned None for run {run_id}")
        except OpenAIError as e:
            logger.error(f"❌ Error retrieving run {run_id}: {e}")
            raise
        except Exception as unknown_err:
            logger.exception(f"⚠️ Unexpected error in run polling for {run_id}")
            raise

        status = getattr(run, "status", None)
        logger.info(f"🔁 Polling: run.status = '{status}' after {waited}s")

        if status in (
            "completed", "failed", "cancelled", "expired",
            "requires_action", "requires_tool", "requires_tools"
        ):
            logger.info(f"✅ Run status '{status}' triggered exit after {waited}s")
            return run

        if not notified and waited >= 30 and notify_fn:
            try:
                notify_fn(user_number)
                notified = True
            except Exception as nerr:
                logger.warning(f"⚠️ Failed to notify user {user_number}: {nerr}")

        time.sleep(interval)
        waited += interval

    logger.warning(f"⏱ Timeout exceeded ({waited}s). Attempting to cancel run {run_id}...")
    try:
        client.beta.threads.runs.cancel(
            thread_id=thread_id,
            run_id=run_id,
            extra_headers={"OpenAI-Beta": "assistants=v2"}
        )
        logger.info(f"🛑 Run {run_id} canceled after timeout.")
    except Exception as cancel_err:
        logger.error(f"❌ Failed to cancel run {run_id}: {cancel_err}")

    raise PollTimeout(f"Polling timeout exceeded ({max_total}s)")

def submit_user_message(thread_id: str, prompt: str, user_number: str):
    content = f"(User Info: WhatsApp number = {user_number})\n\n{prompt}"
    return client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=content,
        extra_headers={"OpenAI-Beta": "assistants=v2"}
    )


def start_run(thread_id: str):
    return client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
        extra_headers={"OpenAI-Beta": "assistants=v2"}
    )


def process_tool_calls(thread_id: str, run, notify_fn=None, user_number: str = None, escalation_flag: list = None):
    # Log the run status
    logger.info(f"process_tool_calls: run.status = {run.status!r}")

    # Update this list based on what OpenAI actually returns
    if run.status not in ("requires_action", "requires_tool", "requires_tools"):
        return run

    # Try to extract tool calls
    tool_calls = []
    try:
        # This is where the tool calls typically live for assistants v2
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
    except AttributeError:
        try:
            # Fallback in case they're under run.required_action.tool_calls
            tool_calls = run.required_action.tool_calls
        except AttributeError:
            logger.error("⚠️ Could not extract tool_calls from run.required_action")
            return run

    # Log the full raw required_action object
    try:
        logger.info("Raw required_action payload:\n" +
                    json.dumps(run.required_action, default=lambda o: o.__dict__, indent=2))
    except Exception as e:
        logger.warning(f"Failed to serialize required_action: {e}")

    # Process each tool call
    outputs = []
    for call in tool_calls:
        function_name = call.function.name
        arguments_json = call.function.arguments or "{}"

        try:
            if function_name == "escalate_to_human":
                args = json.loads(arguments_json)
                logger.info(f"🔧 Calling tool: escalate_to_human with args: {args}")
                result = _handle_escalate_to_human(user_number, **args)
                if escalation_flag is not None:
                    escalation_flag.append(True)
            else:
                handler = TOOL_HANDLERS.get(function_name)
                if handler:
                    args = json.loads(arguments_json)
                    logger.info(f"🔧 Calling tool: {function_name} with args: {args}")
                    result = handler(**args)
                else:
                    logger.warning(f"❓ Unknown tool call: {function_name}")
                    result = f"❓ Unknown tool: {function_name}"
        except Exception as e:
            logger.exception(f"💥 Error in tool handler '{function_name}'")
            result = "⚠️ Tool call failed"

        outputs.append({
            "tool_call_id": call.id,
            "output": result
        })

    return client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run.id,
        tool_outputs=outputs,
        extra_headers={"OpenAI-Beta": "assistants=v2"}
    )

def fetch_response(thread_id: str, run_id: str) -> str:
    messages = client.beta.threads.messages.list(
        thread_id=thread_id,
        order="desc",
        limit=5,
        extra_headers={"OpenAI-Beta": "assistants=v2"}
    )
    for msg in messages.data:
        if msg.run_id == run_id and msg.role == "assistant":
            if not msg.content or not hasattr(msg.content[0], 'text'):
                continue
            text = msg.content[0].text.value.strip()
            if len(text) <= MAX_TWILIO_LENGTH:
                return text
            return text[:MAX_TWILIO_LENGTH - 50] + "\n\n[⚠️ Truncated due to limit]"
    logger.error(f"No assistant message found for run {run_id} on thread {thread_id}")
    return "🤖 Could not retrieve assistant response."


def generate_with_openai(prompt: str, user_number: str, notify_fn=None) -> str:
    """
    Generate a response via the OpenAI assistant, with fine-grained timing instrumentation for each stage.
    """
    start_total = time.monotonic()

    logger.info(f"Received prompt from {user_number}: {prompt}")

    # Early length check
    short = prompt.strip().lower()
    if len(prompt.strip()) < 4 and short not in {"hi", "ok", "yes", "لا", "شو", "كيف", "متى"}:
        return "📝 Could you please provide more detail? Your message is too short."

    thread_id = get_or_create_thread_id(user_number)
    active_key = ACTIVE_RUN_PREFIX + thread_id

    # Check for an active run
    if has_active_run(thread_id, r, client):
        r.rpush(QUEUE_PREFIX + thread_id, prompt)
        logger.info(f"🔁 Queued prompt for busy thread {thread_id}")
        return ""  # Silent marker for caller to optionally trigger monitor

    lock_key = LOCK_KEY_PREFIX + thread_id
    lock_id = str(uuid.uuid4())
    with redis_lock(lock_key, lock_id) as acquired:
        if not acquired:
            r.rpush(QUEUE_PREFIX + thread_id, prompt)
            logger.info(f"🔁 Lock not acquired, queuing for thread {thread_id}")
            return ""
        r.set(active_key, "1", ex=LOCK_EXPIRY_SECONDS)
        try:
            # 1) Submit user message
            t0 = time.monotonic()
            try:
                submit_user_message(thread_id, prompt, user_number)
            except BadRequestError as bre:
                msg = str(bre)
                if "while a run" in msg:
                    logger.warning("Attempted to submit during active run; queuing")
                    r.rpush(QUEUE_PREFIX + thread_id, prompt)
                    return "⏳ I'm still working on your last message. I'll reply to this one soon."
                raise
            logger.info(f"▶️ submit_user_message took {time.monotonic() - t0:.2f}s")

            # 2) Start the assistant run
            t1 = time.monotonic()
            run = start_run(thread_id)
            logger.info(f"▶️ start_run took {time.monotonic() - t1:.2f}s")

            # 3) Poll with backoff until status changes
            t3 = time.monotonic()
            run = poll_with_backoff(thread_id, run.id, user_number, notify_fn=notify_fn)
            logger.info(f"▶️ poll_with_backoff took {time.monotonic() - t3:.2f}s")

            # 4) Handle tool calls — loop to support multi-round tool execution
            MAX_TOOL_ROUNDS = 10
            tool_rounds = 0
            escalation_flag = []
            t2 = time.monotonic()
            while run.status.startswith("requires_") and tool_rounds < MAX_TOOL_ROUNDS:
                run = process_tool_calls(thread_id, run, notify_fn, user_number=user_number, escalation_flag=escalation_flag)
                logger.info(f"▶️ process_tool_calls took {time.monotonic() - t2:.2f}s")

                t3b = time.monotonic()
                run = poll_with_backoff(thread_id, run.id, user_number, notify_fn=notify_fn)
                logger.info(f"▶️ post-tool poll_with_backoff took {time.monotonic() - t3b:.2f}s")
                t2 = time.monotonic()
                tool_rounds += 1
            if tool_rounds >= MAX_TOOL_ROUNDS:
                logger.error(f"⚠️ Max tool rounds ({MAX_TOOL_ROUNDS}) exceeded for thread {thread_id}")

            # If escalate_to_human was called, ESCALATION_MSG was already sent directly.
            # Return None so the caller knows not to send any additional reply.
            if escalation_flag:
                return None

            # 6) Fetch assistant response
            t4 = time.monotonic()
            response = fetch_response(thread_id, run.id)
            logger.info(f"▶️ fetch_response took {time.monotonic() - t4:.2f}s")

            total_elapsed = time.monotonic() - start_total
            logger.info(f"✅ total generate_with_openai took {total_elapsed:.2f}s")

            return response

        except PollTimeout as e:
            logger.error(str(e))
            r.rpush(QUEUE_PREFIX + thread_id, prompt)
            return "😓 This took too long to complete. I’ve queued your message and will follow up shortly."
        except Exception as e:
            logger.exception("Unexpected error during generation")
            return "⚠️ Unexpected error occurred—please try again later."
        finally:
            r.delete(active_key)
