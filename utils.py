import os
import re
import time
import threading
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Content, Email, Mail, To
from twilio.rest import Client
from logati import logger

# Load environment variables
load_dotenv()

# Constants
PHONE_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")  # E.164 format
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "974")
WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
TWILIO_SERVICE_SID = os.getenv("TWILIO_SERVICE_SID")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "no-reply@example.com")

# Lazy singletons for SendGrid and Twilio (initialized once on first use)
_sg_client: Optional[SendGridAPIClient] = None
_sg_lock = threading.Lock()
_twilio_client: Optional[Client] = None
_twilio_lock = threading.Lock()


def _get_sg_client() -> SendGridAPIClient:
    global _sg_client
    if _sg_client is None:
        with _sg_lock:
            if _sg_client is None:
                _sg_client = SendGridAPIClient(SENDGRID_API_KEY)
    return _sg_client


def _get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        with _twilio_lock:
            if _twilio_client is None:
                _twilio_client = Client(
                    os.getenv("TWILIO_ACCOUNT_SID"),
                    os.getenv("TWILIO_AUTH_TOKEN"),
                )
    return _twilio_client

def normalize_phone(number: str) -> Optional[str]:
    """
    Normalize and validate an international phone number.
    - Strips whitespace and 'whatsapp:' prefix
    - Removes non-digit chars
    - Treats 8-digit numbers as local (prepends DEFAULT_COUNTRY_CODE)
    - Returns E.164 formatted number or None if invalid
    """
    if not number:
        return None

    cleaned = number.strip().lower().replace("whatsapp:", "").replace(" ", "")
    digits = re.sub(r"[^0-9]", "", cleaned)
    # Remove leading international prefix
    digits = re.sub(r"^00", "", digits)

    if len(digits) == 8:
        digits = DEFAULT_COUNTRY_CODE + digits

    normalized = f"+{digits}"
    if PHONE_REGEX.match(normalized):
        return normalized

    logger.warning(f"Invalid phone number after normalization: {number}")
    return None


def validate_phone(number: str) -> bool:
    """Return True if the phone number is valid E.164 (using normalize_phone)."""
    return normalize_phone(number) is not None


def has_active_run(thread_id: str, r, client) -> bool:
    """
    Check Redis cache for an active OpenAI run on the given thread.
    Falls back to querying OpenAI for recent runs and caches status in Redis.
    """
    key = f"active_run:thread:{thread_id}"
    if r.get(key):
        return True

    if client is None:
        logger.warning("OpenAI client not available for active run check")
        return False
    try:
        runs = client.beta.threads.runs.list(
            thread_id=thread_id,
            limit=5,
            order="desc",
            extra_headers={"OpenAI-Beta": "assistants=v2"}
        )
        for run in runs.data:
            if run.status in {"queued", "in_progress"}:
                r.setex(key, int(os.getenv("RUN_CACHE_TTL", "90")), run.id)
                return True

    except Exception as exc:
        logger.error(f"Failed to check active run for thread {thread_id}: {exc}")
    return False


def send_email(
    to_emails: Union[str, List[str]],
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> Dict[str, Any]:
    """Send email(s) via SendGrid and log durations."""
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY is not set")

    recipients = [to_emails] if isinstance(to_emails, str) else to_emails
    sg = _get_sg_client()
    success: List[str] = []
    failed: Dict[str, str] = {}

    start_total = time.monotonic()
    logger.info(f"📤 Starting send_email to {len(recipients)} recipient(s)")

    for recipient in recipients:
        start_recipient = time.monotonic()
        message = Mail(
            from_email=Email(SENDER_EMAIL),
            to_emails=To(recipient),
            subject=subject,
            plain_text_content=Content("text/plain", body),
        )
        if html:
            message.add_content(Content("text/html", html))

        try:
            response = sg.send(message)
            elapsed = time.monotonic() - start_recipient
            code = response.status_code
            logger.info(
                f"✅ Email to {recipient} sent (status {code}) in {elapsed:.2f}s"
            )
            success.append(recipient)
        except Exception as exc:
            elapsed = time.monotonic() - start_recipient
            err = getattr(exc, "body", str(exc))
            logger.error(
                f"⚠️ Failed to send email to {recipient} in {elapsed:.2f}s: {err}"
            )
            failed[recipient] = str(err)

    total_elapsed = time.monotonic() - start_total
    logger.info(
        f"📥 send_email completed in {total_elapsed:.2f}s: {len(success)} sent, {len(failed)} failed"
    )

    if failed and not success:
        status = "error"
    elif failed and success:
        status = "partial"
    else:
        status = "success"

    return {
        "status": status,
        "sent": success,
        "failed": failed,
        "duration": total_elapsed,
    }


def send_whatsapp(to: str, message: str):
    """
    Send a WhatsApp text message via Twilio.
    Raises ValueError on invalid number and logs on failure.
    """
    to_norm = normalize_phone(to)
    if not to_norm:
        raise ValueError(f"Invalid recipient phone: {to}")

    client = _get_twilio_client()
    create_kwargs = {
        "to": f"whatsapp:{to_norm}",
        "body": message,
    }

    if TWILIO_SERVICE_SID:
        create_kwargs["messaging_service_sid"] = TWILIO_SERVICE_SID
    else:
        from_norm = normalize_phone(WHATSAPP_NUMBER)
        if not from_norm:
            raise ValueError(f"Invalid sender phone: {WHATSAPP_NUMBER}")
        create_kwargs["from_"] = f"whatsapp:{from_norm}"

    try:
        client.messages.create(**create_kwargs)
    except Exception as exc:
        logger.error(f"WhatsApp send failed to {to_norm}: {exc}")
        raise
