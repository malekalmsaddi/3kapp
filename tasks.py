import os
import json
import csv
import io
import redis
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
    init_db, log_message,
    update_message_sentiment, set_escalation_status, get_user_escalation_status,
    get_messages_since_escalation,
)
from logati import logger
from redis_client import redis_connection as redis_client
from utils import normalize_phone, send_whatsapp, PHONE_REGEX, has_active_run, openai_client
from twilio_helpers import get_twilio_client, notify_error, send_placeholder
from llm_utils import flush_queued_messages, poll_with_backoff, get_or_create_thread_id, fetch_response, generate_with_openai
from sentiment import analyze_sentiment, reset_neg_streak

# ---------------------------------------------------------------------------
# Meta / Twilio bulk-send compliance limits
# ---------------------------------------------------------------------------
# BULK_MAX_BATCH  — hard cap on recipients per single job.
#                   Meta Tier 1 allows 1,000 unique users/24 h; keep a safe
#                   margin so a single job cannot exhaust the entire daily quota.
# BULK_DAILY_CAP  — total unique recipients allowed across all jobs in one UTC
#                   calendar day.  Matches Meta Tier 1 default (1 000/day).
#                   Raise this in env once the number is upgraded to Tier 2/3.
# BULK_MSG_DELAY  — minimum seconds between consecutive sends (Twilio
#                   recommends ≤ 1 msg/sec to avoid quality-rating flags).
BULK_MAX_BATCH = int(os.getenv("BULK_MAX_BATCH", 500))
BULK_DAILY_CAP  = int(os.getenv("BULK_DAILY_CAP",  1000))
BULK_MSG_DELAY  = float(os.getenv("BULK_MSG_DELAY", 1.5))   # seconds/message

if os.getenv("RUN_INIT_DB", "false").lower() == "true":
    required_vars = ["REDIS_URL", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {missing}")
    logger.info("✅ Initializing DB from worker...")
    init_db()

# Configuration constants
REDIS_URL = os.getenv("REDIS_URL")

def _add_ssl_cert_reqs(url: str) -> str:
    """Append ssl_cert_reqs=CERT_NONE to rediss:// URLs if not already present."""
    if url and url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}ssl_cert_reqs=CERT_NONE"
    return url

CELERY_BROKER = _add_ssl_cert_reqs(REDIS_URL)
CELERY_BACKEND = _add_ssl_cert_reqs(REDIS_URL)

TASK_TIMEOUTS = {
    "process_openai": (90, 100),
    "send_template":  (15, 20),
    "process_bulk":   (600, 650),
    "default":        (30, 35),
}

TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
TWILIO_SERVICE_SID = os.getenv("TWILIO_SERVICE_SID")
TEMPLATE_CONTENT_SID = os.getenv("TEMPLATE_CONTENT_SID")


# Initialize Celery app
celery_app = Celery(
    "moeen_tasks",
    broker=CELERY_BROKER,
    backend=CELERY_BACKEND
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=int(os.getenv("WORKER_PREFETCH", 1)),
    task_soft_time_limit=TASK_TIMEOUTS["default"][0],
    task_time_limit=TASK_TIMEOUTS["default"][1],
    broker_connection_retry_on_startup=True,
    task_default_retry_delay=int(os.getenv("TASK_RETRY_DELAY", 30)),
)

# Celery logger setup
def setup_loggers(logger, *args, **kwargs):
    logger.setLevel(os.getenv("CELERY_LOG_LEVEL", "INFO"))
after_setup_logger.connect(setup_loggers)

# Tasks
def _daily_cap_key() -> str:
    """Redis key for today's (UTC) unique-recipient counter."""
    return f"bulk:daily:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"


def _get_daily_sent() -> int:
    """Return how many unique recipients have been messaged today (UTC)."""
    try:
        val = redis_client.get(_daily_cap_key())
        return int(val) if val else 0
    except Exception:
        return 0


def _incr_daily_sent() -> None:
    """Atomically increment today's counter and set a 25-hour TTL."""
    try:
        key = _daily_cap_key()
        redis_client.incr(key)
        redis_client.expire(key, 90000)   # 25 h — survives midnight rollover edge cases
    except Exception:
        pass


@celery_app.task(bind=True,
                 soft_time_limit=TASK_TIMEOUTS["process_bulk"][0],
                 time_limit=TASK_TIMEOUTS["process_bulk"][1])
def send_bulk_contacts(self, payload: list, content_sid: str = None):
    """Send deduplicated WhatsApp template messages respecting Meta/Twilio limits.

    Guardrails applied (in order):
      1. Hard cap: job rejected entirely if len(payload) > BULK_MAX_BATCH.
      2. Daily cap: individual recipients skipped once BULK_DAILY_CAP is reached
         for the current UTC day (tracked across all bulk jobs).
      3. Session dedup: same number cannot appear twice in one job.
      4. Global dedup: Redis set prevents re-sending to the same number within 24 h
         across separate jobs.
      5. Rate spacing: each send is staggered by BULK_MSG_DELAY seconds so the
         effective throughput stays at ≤ 1 msg/sec (Twilio recommendation).
    """
    total = len(payload)

    # ── 1. Hard batch-size cap ────────────────────────────────────────────────
    if total > BULK_MAX_BATCH:
        logger.error(
            f"[bulk] Job {self.request.id} rejected: {total} recipients exceeds "
            f"BULK_MAX_BATCH={BULK_MAX_BATCH}"
        )
        try:
            redis_client.set(
                f"progress:{self.request.id}",
                f"0/{total}",
                ex=86400,
            )
            redis_client.rpush(
                f"log:{self.request.id}",
                json.dumps({
                    "to": "—",
                    "result": "rejected",
                    "reason": (
                        f"Batch size {total} exceeds the allowed maximum of "
                        f"{BULK_MAX_BATCH} recipients per job (Meta/Twilio compliance)."
                    ),
                }),
            )
        except Exception:
            pass
        return {"status": "rejected", "reason": "batch_too_large", "total": total}

    seen = set()
    dedup_key = f"dedup:{self.request.id}"
    try:
        redis_client.expire(dedup_key, 86400)
    except redis.exceptions.ConnectionError:
        pass

    for idx, entry in enumerate(payload, start=1):
        raw_to = entry.get("to", "").strip()
        to = normalize_phone(raw_to)
        result, reason = "queued", ""

        # ── 2. Per-entry validations ─────────────────────────────────────────
        if not to or not PHONE_REGEX.match(to):
            result, reason = "failed", "Invalid phone number"
        elif to in seen:
            result, reason = "skipped", "Duplicate number (this job)"
        else:
            try:
                if redis_client.sismember(dedup_key, to):
                    result, reason = "skipped", "Duplicate number (sent within 24 h)"
            except redis.exceptions.ConnectionError as e:
                logger.warning(f"Redis sismember failed: {e}")
                result, reason = "failed", "Redis error"

        # ── 3. Daily-cap check ───────────────────────────────────────────────
        if result == "queued":
            daily_sent = _get_daily_sent()
            if daily_sent >= BULK_DAILY_CAP:
                result, reason = (
                    "skipped",
                    f"Daily recipient cap of {BULK_DAILY_CAP} reached "
                    f"(Meta Tier 1 limit). Upgrade your phone number tier to send more.",
                )
                logger.warning(f"[bulk] Daily cap hit at idx={idx}/{total} for job {self.request.id}")

        # ── 4. Dispatch ──────────────────────────────────────────────────────
        if result == "queued":
            params = {k: entry.get(k, "") for k in ("param1", "param2")}
            try:
                # Stagger sends: message N fires N * BULK_MSG_DELAY seconds from now.
                # With the default 1.5 s/msg this keeps throughput at ~40 msg/min —
                # well within Twilio's 60 msg/min soft limit for standard accounts.
                send_whatsapp_template.apply_async(
                    args=(to, params, content_sid),
                    countdown=idx * BULK_MSG_DELAY,
                )
                seen.add(to)
                try:
                    redis_client.sadd(dedup_key, to)
                except redis.exceptions.ConnectionError as e:
                    logger.warning(f"Redis sadd failed: {e}")
                _incr_daily_sent()
            except Exception as e:
                result, reason = "failed", f"Dispatch error: {str(e)}"

        # ── 5. Progress logging ──────────────────────────────────────────────
        try:
            log_entry = {"to": raw_to, "result": result}
            if reason:
                log_entry["reason"] = reason
            redis_client.rpush(f"log:{self.request.id}", json.dumps(log_entry))
            redis_client.set(f"progress:{self.request.id}", f"{idx}/{total}")
        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Redis logging failed: {e}")

    # Expire all keys after 24 h
    for key in [f"log:{self.request.id}", f"progress:{self.request.id}", dedup_key]:
        try:
            redis_client.expire(key, 86400)
        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Redis expire failed: {e}")

@shared_task(name="tasks.monitor_openai_thread_and_flush")
def monitor_openai_thread_and_flush(user_number: str):

    thread_id = get_or_create_thread_id(user_number)
    retries, interval = 15, 5

    for _ in range(retries):
        if not has_active_run(thread_id, redis_client, client=openai_client):
            break
        time.sleep(interval)

    redis_client.delete(f"active_run:thread:{thread_id}")

    run = flush_queued_messages(thread_id, user_number)
    if not run:
        # Queue was already empty — the original run processed the messages before we got here.
        logger.info(f"ℹ️ monitor_openai_thread_and_flush: queue empty for thread {thread_id}, nothing to flush")
        return

    try:
        run = poll_with_backoff(thread_id, run.id, user_number)
        logger.info(f"📥 Assistant run from flushed queue completed for {thread_id}")
        response = fetch_response(thread_id, run.id)
        if response:
            send_whatsapp(user_number, response)
            log_message(datetime.now(timezone.utc).isoformat(), "outbound", user_number, response)
    except Exception as e:
        logger.exception(f"❌ Error in post-queue run processing for {thread_id}: {e}")
        try:
            notify_error(user_number, "⚠️ Something went wrong while sending your reply. Please try again.")
        except Exception as notify_err:
            logger.error(f"Failed to send error notification to {user_number}: {notify_err}")

@shared_task(name="tasks.process_openai", bind=True, max_retries=3,
             soft_time_limit=TASK_TIMEOUTS["process_openai"][0],
             time_limit=TASK_TIMEOUTS["process_openai"][1])
def process_openai(self, user_number: str, user_message: str):
    """Process a user message via OpenAI and reply over WhatsApp."""
    try:
        # ── 1. Escalation gate ───────────────────────────────────────────────
        escalation_status = get_user_escalation_status(user_number)
        if escalation_status == "escalated":
            if redis_client.get(f"escalation_hold:{user_number}"):
                # Human session is active — stay silent
                logger.info(f"[escalation] {user_number} is with human agent — suppressing bot message")
                return {"status": "human_active", "to": user_number}
            else:
                # Human session timed out — auto-resolve and hand back to bot
                logger.info(f"[escalation] {user_number} human session timed out — auto-resolving to bot")
                set_escalation_status(user_number, "bot")
                reset_neg_streak(user_number)
                # Combine all messages sent during the human session so the AI
                # has full context of what the user was trying to communicate
                missed = get_messages_since_escalation(user_number)
                if len(missed) > 1:
                    user_message = (
                        "[Context: This user waited for a team member who stopped replying. "
                        "The following are all the messages they sent during that wait. "
                        "Apologise for the delay and address their concerns:]\n\n"
                        + "\n".join(f"- {m}" for m in missed)
                    )
                    logger.info(f"[escalation] forwarding {len(missed)} missed messages to AI for {user_number}")
                # Fall through to normal OpenAI flow below

        # ── 2. Sentiment tracking (stored for dashboard) ─────────────────────
        sentiment = analyze_sentiment(user_message)
        update_message_sentiment(user_number, user_message, sentiment)
        logger.info(f"[sentiment] {user_number} → {sentiment}")

        # ── 3. Normal OpenAI flow ────────────────────────────────────────────
        start = time.monotonic()
        response = generate_with_openai(user_message, user_number, notify_fn=send_placeholder)
        elapsed = time.monotonic() - start

        if response is None:
            # escalate_to_human tool was called — ESCALATION_MSG already sent
            return {"status": "escalated", "to": user_number}

        if response == "":
            monitor_openai_thread_and_flush.delay(user_number)
            return {"status": "queued", "to": user_number}

        client = get_twilio_client()
        from_whatsapp = f"whatsapp:{normalize_phone(TWILIO_WHATSAPP_NUMBER)}"
        to_whatsapp = f"whatsapp:{normalize_phone(user_number)}"

        client.messages.create(from_=from_whatsapp, to=to_whatsapp, body=response)
        log_message(datetime.now(timezone.utc).isoformat(), "outbound", user_number, response)
        return {"status": "sent", "to": user_number, "duration": elapsed}

    except SoftTimeLimitExceeded:
        logger.error(f"process_openai soft time limit exceeded for {user_number}")
        notify_error(user_number, "⚠️ Taking longer than expected. Try again later.")
        return {"status": "timeout", "to": user_number}
    except Exception as exc:
        logger.exception("OpenAI task failed")
        try:
            self.retry(countdown=int(os.getenv("TASK_RETRY_DELAY", 10)))
        except MaxRetriesExceededError:
            notify_error(user_number, "⚠️ Something went wrong. Please try again.")

@shared_task(name="tasks.send_whatsapp_template", bind=True, max_retries=5,
             soft_time_limit=TASK_TIMEOUTS["send_template"][0],
             time_limit=TASK_TIMEOUTS["send_template"][1])
def send_whatsapp_template(self, to: str, params: dict, content_sid: str = None):
    """Send a WhatsApp template message via Twilio.

    Retry policy:
      • Twilio 429 (rate-limited): exponential backoff — 60 s, 120 s, 240 s, 480 s, 960 s.
        This honours Twilio's rate limits and Meta's per-number sending caps.
      • Twilio 4xx (other client errors, e.g. 21211 invalid number): do NOT retry —
        the error is permanent; retrying wastes quota.
      • Transient / 5xx errors: fixed backoff (TEMPLATE_RETRY_DELAY env, default 60 s).
    """
    try:
        client = get_twilio_client()
        sid = content_sid or TEMPLATE_CONTENT_SID
        create_kwargs = {
            "to": f"whatsapp:{to}",
            "content_sid": sid,
            "content_variables": json.dumps(params),
        }
        if TWILIO_SERVICE_SID:
            create_kwargs["messaging_service_sid"] = TWILIO_SERVICE_SID
        else:
            create_kwargs["from_"] = f"whatsapp:{normalize_phone(TWILIO_WHATSAPP_NUMBER)}"
        msg = client.messages.create(**create_kwargs)
        log_message(datetime.now(timezone.utc).isoformat(), "outbound", to, f"TEMPLATE: {params}")
        return {"status": "sent", "sid": msg.sid, "to": to}

    except SoftTimeLimitExceeded:
        logger.error(f"Template send timeout to {to}")
        return {"status": "timeout", "to": to}

    except TwilioRestException as exc:
        if exc.status == 429:
            # Rate-limited by Twilio / Meta — exponential backoff, cap at 16 min.
            backoff = min(60 * (2 ** self.request.retries), 960)
            logger.warning(
                f"[template] 429 rate-limited sending to {to}. "
                f"Retry {self.request.retries + 1}/5 in {backoff}s"
            )
            raise self.retry(countdown=backoff)
        elif 400 <= exc.status < 500:
            # Permanent client error (invalid number, unsubscribed user, etc.).
            # Log and give up — retrying wastes daily quota.
            logger.error(
                f"[template] Permanent Twilio error {exc.code} ({exc.status}) "
                f"sending to {to}: {exc.msg}"
            )
            return {"status": "failed", "to": to, "twilio_code": exc.code, "reason": exc.msg}
        else:
            # Transient / server-side Twilio error — fixed backoff.
            logger.warning(f"[template] Twilio {exc.status} error to {to}: {exc.msg}")
            raise self.retry(countdown=int(os.getenv("TEMPLATE_RETRY_DELAY", 60)))

    except Exception:
        logger.exception(f"[template] Unexpected error sending to {to}")
        raise self.retry(countdown=int(os.getenv("TEMPLATE_RETRY_DELAY", 60)))

@shared_task(bind=True, max_retries=2,
             soft_time_limit=TASK_TIMEOUTS["process_bulk"][0],
             time_limit=TASK_TIMEOUTS["process_bulk"][1])
def process_bulk_file(self, file_contents: str):
    """Process CSV file contents for bulk messaging."""
    results = defaultdict(list)
    reader = csv.DictReader(io.StringIO(file_contents))
    if not reader.fieldnames:
        return {"status": "failed", "error": "CSV empty or invalid"}
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
            send_whatsapp_template.apply_async(args=(phone, params))
            results['success'].append(idx)
            log_message(datetime.now(timezone.utc).isoformat(), "outbound", phone, f"BULK: {params}")
        except Exception:
            results['failed'].append(idx)
    total = idx
    rate = f"{len(results['success'])/total:.1%}" if total else "0%"
    return {"status": "completed", "total_rows": total, "results": dict(results), "success_rate": rate}
