"""
crypto.py — Fernet symmetric encryption for sensitive config fields.

Used to encrypt API keys, auth tokens, and credentials stored in
tenant_configs and assistant_configs at rest in PostgreSQL.

The encryption key is loaded from ENCRYPTION_KEY env var.
Generate one with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from cryptography.fernet import Fernet, InvalidToken
from logati import logger

_ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
_fernet = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is not None:
        return _fernet
    if not _ENCRYPTION_KEY:
        logger.warning('⚠️ ENCRYPTION_KEY not set — secrets stored in plaintext')
        return None
    _fernet = Fernet(_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns the ciphertext as a string.
    If ENCRYPTION_KEY is not configured, returns the value unchanged."""
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        return value
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a ciphertext string. Returns the plaintext.
    If the value doesn't look encrypted (not a valid Fernet token), returns it as-is.
    This provides backward compatibility with pre-encryption plaintext values."""
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        # Value is not encrypted (plaintext from before encryption was enabled)
        return value


def encrypt_dict_fields(data: dict, fields: list[str]) -> dict:
    """Return a copy of data with specified fields encrypted."""
    result = dict(data)
    for field in fields:
        if field in result and result[field]:
            result[field] = encrypt(result[field])
    return result


def decrypt_dict_fields(data: dict, fields: list[str]) -> dict:
    """Return a copy of data with specified fields decrypted."""
    result = dict(data)
    for field in fields:
        if field in result and result[field]:
            result[field] = decrypt(result[field])
    return result


# Fields that should be encrypted/decrypted when stored/loaded
TENANT_CONFIG_ENCRYPTED_FIELDS = [
    'twilio_account_sid',
    'twilio_auth_token',
    'sendgrid_api_key',
    'calendar_credentials',
]

ASSISTANT_CONFIG_ENCRYPTED_FIELDS = [
    'openai_api_key',
]
