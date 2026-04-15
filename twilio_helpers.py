import os
import threading

from twilio.rest import Client

from utils import normalize_phone

_twilio_client: Client | None = None
_twilio_lock = threading.Lock()


def get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        with _twilio_lock:
            if _twilio_client is None:
                _twilio_client = Client(
                    os.getenv("TWILIO_ACCOUNT_SID"),
                    os.getenv("TWILIO_AUTH_TOKEN"),
                )
    return _twilio_client


def _send_whatsapp(user_number: str, body: str) -> None:
    client = get_twilio_client()
    from_whatsapp = normalize_phone(os.getenv("TWILIO_WHATSAPP_NUMBER"))
    to_whatsapp = normalize_phone(user_number)
    if not from_whatsapp or not to_whatsapp:
        return
    client.messages.create(
        from_=f"whatsapp:{from_whatsapp}",
        to=f"whatsapp:{to_whatsapp}",
        body=body,
    )


def send_placeholder(user_number: str) -> None:
    _send_whatsapp(user_number, "💭 Processing your message... يرجى الإنتظار")


def notify_error(user_number: str, msg: str) -> None:
    _send_whatsapp(user_number, msg)
