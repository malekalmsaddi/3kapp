"""
blueprints/auth.py — Authentication endpoints.

  POST /api/v1/auth/login       — email + password → JWT cookies
  POST /api/v1/auth/signup      — create new tenant + owner
  POST /api/v1/auth/logout      — revoke tokens, clear cookies
  POST /api/v1/auth/refresh     — rotate access token
  GET  /api/v1/auth/verify-email — verify email with token
  GET  /api/v1/auth/me          — return current user info
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from flask import Blueprint, request, jsonify, g, session

from db import (
    get_user_by_email, create_tenant, update_user_last_login,
    get_user_by_id, get_admin, log_audit, LEGACY_TENANT_ID,
)
from services.auth_service import (
    create_access_token, create_refresh_token,
    validate_refresh_token, revoke_refresh_token,
)
from logati import logger

auth_bp = Blueprint('auth', __name__)

SECURE_COOKIES = os.getenv('FLASK_ENV', 'production') == 'production'


@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate with email+password and receive JWT cookies."""
    data = request.get_json() or {}
    # Support both JSON and form-encoded (backward compat with old /login)
    email    = (data.get('email') or data.get('username') or
                request.form.get('email') or request.form.get('username', '')).strip()
    password = (data.get('password') or request.form.get('password', '')).strip()

    if not email or not password:
        return jsonify({'status': 'error', 'message': 'Email and password required'}), 400

    # Try new users table first
    user = get_user_by_email(email)

    if not user:
        # Fall back to legacy admins table for Phase 1 backward compat
        admin = get_admin(email)
        if admin and bcrypt.checkpw(password.encode(), admin['password_hash'].encode()):
            # Legacy admin login — set Flask session for backward compat
            session['logged_in'] = True
            return jsonify({'status': 'ok'}), 200
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    # Validate password
    if not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

    if not user.get('is_active', True):
        return jsonify({'status': 'error', 'message': 'Account suspended'}), 403

    # Check tenant status
    if user.get('tenant_status') and user['tenant_status'] in ('suspended', 'cancelled'):
        return jsonify({'status': 'error', 'message': 'Organization is suspended'}), 403

    # Issue tokens
    access_token  = create_access_token(user)
    refresh_token = create_refresh_token(user)
    update_user_last_login(str(user['id']))

    log_audit(
        tenant_id=str(user.get('tenant_id')) if user.get('tenant_id') else None,
        actor_user_id=str(user['id']),
        action='user.login',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
    )

    resp = jsonify({
        'status': 'ok',
        'role': user['role'],
        'tenant_slug': user.get('tenant_slug'),
        'brand_name': user.get('brand_name'),
    })
    resp.set_cookie(
        'access_token', access_token,
        httponly=True, secure=SECURE_COOKIES,
        samesite='Lax', max_age=86400,
    )
    resp.set_cookie(
        'refresh_token', refresh_token,
        httponly=True, secure=SECURE_COOKIES,
        samesite='Strict', max_age=604800,
        path='/api/v1/auth/refresh',
    )
    # Also set legacy session for backward compat
    session['logged_in'] = True
    return resp


@auth_bp.route('/signup', methods=['POST'])
def signup():
    """Create a new tenant and owner account."""
    data = request.get_json() or {}
    company_name = data.get('company_name', '').strip()
    email        = data.get('email', '').strip().lower()
    password     = data.get('password', '').strip()
    plan_name    = data.get('plan', 'free')
    tz           = data.get('timezone', 'UTC')

    if not company_name or not email or not password:
        return jsonify({'status': 'error',
                        'message': 'company_name, email, and password are required'}), 400

    if len(password) < 8:
        return jsonify({'status': 'error',
                        'message': 'Password must be at least 8 characters'}), 400

    # Check if email already exists
    existing = get_user_by_email(email)
    if existing:
        return jsonify({'status': 'error', 'message': 'Email already registered'}), 409

    # Generate slug from company name
    slug = company_name.lower().replace(' ', '-')
    # Remove non-alphanumeric chars except hyphens
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')[:63]
    if not slug:
        slug = str(uuid.uuid4())[:8]

    # Hash password
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        result = create_tenant(
            slug=slug,
            name=company_name,
            plan_name=plan_name,
            owner_email=email,
            owner_password_hash=password_hash,
            timezone=tz,
        )
    except ValueError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
    except Exception as e:
        logger.error(f'Signup failed: {e}')
        return jsonify({'status': 'error', 'message': 'Could not create account'}), 500

    tenant = result['tenant']
    user   = result['user']

    # For now, auto-verify email (email verification flow will be added in Phase 3)
    from db import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE users SET email_verified = TRUE WHERE id = %s',
                (str(user['id']),),
            )

    # Build the user dict needed for token creation
    user['tenant_slug'] = tenant['slug']
    user['brand_name']  = tenant.get('brand_name')

    access_token  = create_access_token(user)
    refresh_token = create_refresh_token(user)

    log_audit(
        tenant_id=str(tenant['id']),
        actor_user_id=str(user['id']),
        action='tenant.create',
        resource_type='tenant',
        resource_id=str(tenant['id']),
        payload={'slug': tenant['slug'], 'plan': plan_name},
        ip_address=request.remote_addr,
    )

    resp = jsonify({
        'status': 'ok',
        'tenant_slug': tenant['slug'],
        'tenant_id': str(tenant['id']),
        'role': user['role'],
    })
    resp.set_cookie(
        'access_token', access_token,
        httponly=True, secure=SECURE_COOKIES,
        samesite='Lax', max_age=86400,
    )
    resp.set_cookie(
        'refresh_token', refresh_token,
        httponly=True, secure=SECURE_COOKIES,
        samesite='Strict', max_age=604800,
        path='/api/v1/auth/refresh',
    )
    return resp, 201


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Revoke the refresh token and clear cookies."""
    refresh_token = request.cookies.get('refresh_token')
    if refresh_token:
        revoke_refresh_token(refresh_token)

    session.clear()

    resp = jsonify({'status': 'ok'})
    resp.delete_cookie('access_token')
    resp.delete_cookie('refresh_token', path='/api/v1/auth/refresh')
    return resp


@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    """Rotate the access token using a valid refresh token."""
    refresh_token = request.cookies.get('refresh_token')
    if not refresh_token:
        return jsonify({'status': 'error', 'message': 'No refresh token'}), 401

    user_id = validate_refresh_token(refresh_token)
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Invalid or expired refresh token'}), 401

    user = get_user_by_id(user_id)
    if not user or not user.get('is_active', True):
        return jsonify({'status': 'error', 'message': 'User not found'}), 401

    new_access = create_access_token(user)

    resp = jsonify({'status': 'ok'})
    resp.set_cookie(
        'access_token', new_access,
        httponly=True, secure=SECURE_COOKIES,
        samesite='Lax', max_age=86400,
    )
    return resp


@auth_bp.route('/me', methods=['GET'])
def me():
    """Return the current authenticated user's info."""
    if not g.authenticated:
        return jsonify({'status': 'error', 'message': 'Not authenticated'}), 401

    user_info = {
        'user_id': g.user_id,
        'tenant_id': g.tenant_id,
        'tenant_slug': g.tenant_slug,
        'role': g.role,
        'email': g.email,
    }

    # Enrich with tenant info if available
    if g.tenant_id:
        from db import get_tenant_by_id
        tenant = get_tenant_by_id(g.tenant_id)
        if tenant:
            user_info['brand_name']           = tenant.get('brand_name')
            user_info['brand_color_primary']   = tenant.get('brand_color_primary')
            user_info['brand_color_secondary'] = tenant.get('brand_color_secondary')
            user_info['brand_logo_url']        = tenant.get('brand_logo_url')
            user_info['plan_name']             = tenant.get('plan_name')
            user_info['tenant_status']         = tenant.get('status')
            user_info['timezone']              = tenant.get('timezone')

    return jsonify(user_info)
