"""
JWT middleware for Flask.

Decodes the access_token HttpOnly cookie (or Authorization: Bearer header)
on every request and populates flask.g with:
  - g.user_id       (str)   user UUID
  - g.tenant_id     (str)   tenant UUID (None for super_admin)
  - g.tenant_slug   (str)   tenant slug
  - g.role          (str)   'super_admin' | 'tenant'
  - g.email         (str)   user email
  - g.authenticated (bool)  True if a valid JWT was decoded

Public routes skip JWT decoding entirely.
"""
import os
import uuid
from functools import wraps

import jwt
from flask import request, g, abort
from logati import logger
from redis_client import redis_connection

JWT_SECRET    = os.getenv('JWT_SECRET_KEY', os.getenv('FLASK_SECRET_KEY', ''))
JWT_ALGORITHM = 'HS256'

# Routes that never require authentication
PUBLIC_PREFIXES = (
    '/health',
    '/whatsapp/',           # Twilio webhook — authenticated via signature
    '/api/v1/auth/login',
    '/api/v1/auth/signup',
    '/api/v1/auth/verify-email',
    '/api/v1/auth/refresh',
    '/v1/auth/login',       # Same routes via Next.js proxy (strips /api)
    '/v1/auth/signup',
    '/v1/auth/verify-email',
    '/v1/auth/refresh',
)


def init_jwt_middleware(app):
    """Register the JWT decoding before_request hook."""

    @app.before_request
    def decode_jwt():
        # Assign correlation ID first
        request.correlation_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())

        # Defaults
        g.user_id       = None
        g.tenant_id     = None
        g.tenant_slug   = None
        g.role          = None
        g.email         = None
        g.authenticated = False

        path = request.path

        # Skip public routes
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return

        # Try JWT from cookie or Authorization header
        token = request.cookies.get('access_token')
        if not token:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]

        if token:
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            except jwt.ExpiredSignatureError:
                abort(401)
            except jwt.InvalidTokenError:
                abort(401)

            # Check if token has been revoked; fail open if Redis is unavailable
            # (JWT signature + expiry still provide security; revocation is best-effort)
            jti = payload.get('jti')
            try:
                if jti and redis_connection.get(f'revoked_jti:{jti}'):
                    abort(401)
            except Exception:
                logger.warning('Redis unavailable for JWT revocation check — proceeding without revocation check')

            g.user_id       = payload.get('sub')
            g.tenant_id     = payload.get('tid')
            g.tenant_slug   = payload.get('tslug')
            g.role          = payload.get('role')
            g.email         = payload.get('email')
            g.authenticated = True
            return

        # No token, not a public route
        abort(401)

    @app.after_request
    def add_correlation_header(response):
        if hasattr(request, 'correlation_id'):
            response.headers['X-Correlation-ID'] = request.correlation_id
        return response


# ─────────────────────────────────────────────────────────────────────────────
# Role-based decorators
# ─────────────────────────────────────────────────────────────────────────────

def require_auth(fn):
    """Require any authenticated user."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.authenticated:
            abort(401)
        return fn(*args, **kwargs)
    return wrapper


def require_tenant(fn):
    """Require tenant or super_admin role."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.authenticated:
            abort(401)
        if g.role not in ('tenant', 'super_admin'):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def require_super_admin(fn):
    """Require super_admin role."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.authenticated:
            abort(401)
        if g.role != 'super_admin':
            abort(403)
        return fn(*args, **kwargs)
    return wrapper
