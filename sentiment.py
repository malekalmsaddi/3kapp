import os

from openai import OpenAI
from redis_client import redis_connection as redis_client
from logati import logger

_openai_client = None

ESCALATION_MSG = (
    "We're connecting you with a member of our team. Please hold on. 🙏\n\n"
    "نقوم بتحويلك إلى أحد أعضاء فريقنا. يرجى الانتظار. 🙏"
)
HOLD_MSG = (
    "Your conversation is currently with our team. We'll get back to you shortly. ⏳\n\n"
    "محادثتك حاليًا مع فريقنا. سنعود إليك قريبًا. ⏳"
)


def _get_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def analyze_sentiment(text: str) -> str:
    """Return 'positive', 'neutral', or 'negative' via GPT-4o-mini. Falls back to 'neutral'."""
    try:
        resp = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Classify the sentiment of the following message as exactly one word: "
                        "positive, neutral, or negative. No explanation. Supports English and Arabic."
                    ),
                },
                {"role": "user", "content": text[:500]},
            ],
            max_tokens=5,
            temperature=0,
        )
        result = resp.choices[0].message.content.strip().lower()
        return result if result in ("positive", "neutral", "negative") else "neutral"
    except Exception as e:
        logger.warning(f"[sentiment] analyze_sentiment error: {e}")
        return "neutral"


def reset_neg_streak(user_number: str) -> None:
    """Delete any lingering negative-sentiment streak key for this user."""
    redis_client.delete(f"neg_streak:{user_number}")
