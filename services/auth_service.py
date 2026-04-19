"""
auth_service.py — JWT token generation, refresh, and revocation.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from redis_client import redis_connection
from logati import logger

JWT_SECRET    = os.getenv('JWT_SECRET_KEY', os.getenv('FLASK_SECRET_KEY', ''))
JWT_ALGORITHM = 'HS256'

ACCESS_TOKEN_EXPIRY  = timedelta(hours=24)
REFRESH_TOKEN_EXPIRY = timedelta(days=7)


def create_access_token(user: dict) -> str:
    """Create a signed JWT access token from a user record dict."""
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        'sub':   str(user['id']),
        'tid':   str(user['tenant_id']) if user.get('tenant_id') else None,
        'tslug': user.get('tenant_slug'),
        'role':  user['role'],
        'email': user['email'],
        'jti':   jti,
        'iat':   now,
        'exp':   now + ACCESS_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user: dict) -> str:
    """Create a signed JWT refresh token and store its JTI in Redis."""
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user['id']),
        'jti': jti,
        'exp': now + REFRESH_TOKEN_EXPIRY,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    # Store refresh JTI for validation and revocation
    try:
        redis_connection.setex(
            f'refresh_jti:{jti}',
            int(REFRESH_TOKEN_EXPIRY.total_seconds()),
            str(user['id']),
        )
    except Exception as e:
        logger.error(f'Failed to store refresh JTI in Redis: {e}')
        raise RuntimeError('Authentication service unavailable') from e
    return token


def decode_token(token: str) -> dict | None:
    """Decode a JWT token, returning the payload or None on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def validate_refresh_token(token: str) -> str | None:
    """Validate a refresh token. Returns user_id if valid, None otherwise."""
    payload = decode_token(token)
    if not payload:
        return None
    jti = payload.get('jti')
    if not jti:
        return None
    # Check that the JTI exists in Redis (hasn't been revoked)
    stored = redis_connection.get(f'refresh_jti:{jti}')
    if not stored:
        return None
    return payload.get('sub')


def revoke_token(jti: str, ttl_seconds: int = 86400) -> None:
    """Revoke a specific token by storing its JTI in the blocklist."""
    try:
        redis_connection.setex(f'revoked_jti:{jti}', ttl_seconds, '1')
    except Exception as e:
        logger.error(f'Failed to revoke token {jti}: {e}')


def revoke_refresh_token(token: str) -> None:
    """Revoke a refresh token by removing its JTI from Redis."""
    payload = decode_token(token)
    if payload and payload.get('jti'):
        redis_connection.delete(f'refresh_jti:{payload["jti"]}')
