"""
app.py — Flask application factory with blueprint registration.

All route logic lives in blueprints/. This file handles:
  - App creation and configuration
  - Blueprint registration (with versioned + legacy URL prefixes)
  - Rate limiting
  - JWT middleware initialization
  - DB initialization
"""
import os
import threading
import time

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

from logati import logger

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Required env vars
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_ENV = [
    'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_NUMBER',
    'OPENAI_API_KEY', 'ASSISTANT_ID', 'REDIS_URL', 'FLASK_SECRET_KEY',
]
missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
if missing:
    raise RuntimeError(f'Missing required environment variables: {missing}')

# ─────────────────────────────────────────────────────────────────────────────
# Create the Flask app
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
app.config.update(
    SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV', 'production') == 'production',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,   # 5 MB upload limit
)

# ─────────────────────────────────────────────────────────────────────────────
# Database initialization
# ─────────────────────────────────────────────────────────────────────────────
try:
    from db import init_db
    init_db()
except Exception as e:
    app.logger.warning(f'Database initialization failed: {e}')

# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter
# ─────────────────────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv('REDIS_URL'),
    default_limits=['200 per day', '50 per hour'],
)
limiter.init_app(app)

# ─────────────────────────────────────────────────────────────────────────────
# JWT middleware (decodes access_token cookie → flask.g)
# ─────────────────────────────────────────────────────────────────────────────
from middleware.jwt_middleware import init_jwt_middleware
init_jwt_middleware(app)

# ─────────────────────────────────────────────────────────────────────────────
# Register blueprints
# ─────────────────────────────────────────────────────────────────────────────
from blueprints.auth       import auth_bp
from blueprints.webhook    import webhook_bp
from blueprints.dashboard  import dashboard_bp
from blueprints.messaging  import messaging_bp
from blueprints.admin      import admin_bp
from blueprints.settings   import settings_bp
from blueprints.platform   import platform_bp
from blueprints.onboarding import onboarding_bp

# ── Versioned API routes (new) ──────────────────────────────────────────────
app.register_blueprint(auth_bp,       url_prefix='/api/v1/auth')
app.register_blueprint(onboarding_bp, url_prefix='/api/v1/onboarding')
app.register_blueprint(platform_bp,   url_prefix='/platform')

# ── Webhook routes (no prefix — /whatsapp/<slug> must be at root) ───────────
app.register_blueprint(webhook_bp)

# ── Legacy routes (same paths as the old monolithic app.py) ─────────────────
# These are registered WITHOUT a prefix so the frontend continues to work
# with /api/dashboard, /api/send_template, etc. via the Next.js rewrite.
app.register_blueprint(dashboard_bp)
app.register_blueprint(messaging_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(settings_bp)

# ── Also mount under /api/v1 for forward-looking API consumers ──────────────
app.register_blueprint(dashboard_bp, url_prefix='/api/v1', name='dashboard_v1')
app.register_blueprint(messaging_bp, url_prefix='/api/v1', name='messaging_v1')
app.register_blueprint(admin_bp,     url_prefix='/api/v1/admin', name='admin_v1')
app.register_blueprint(settings_bp,  url_prefix='/api/v1', name='settings_v1')

# ── Apply rate limits to specific blueprints ────────────────────────────────
limiter.limit('5 per minute')(auth_bp)
limiter.limit('200 per minute')(dashboard_bp)
limiter.limit('50 per minute')(settings_bp)
limiter.limit('20 per minute')(messaging_bp)

# Exempt health check from rate limiting
limiter.exempt(settings_bp)  # /health lives here and needs to be exempt

# ─────────────────────────────────────────────────────────────────────────────
# Legacy login/logout routes (backward compat for existing frontend)
# These map the old form-encoded /login and /logout to the new auth blueprint.
# ─────────────────────────────────────────────────────────────────────────────
from flask import request as flask_request, session, jsonify as flask_jsonify
import bcrypt
from db import get_admin


@app.route('/login', methods=['POST'])
@limiter.limit('5 per minute')
def legacy_login():
    """Legacy login endpoint for backward compatibility."""
    user = flask_request.form.get('username', '').strip()
    pw   = flask_request.form.get('password', '').strip()

    valid = False
    try:
        admin = get_admin(user)
        if admin:
            valid = bcrypt.checkpw(pw.encode(), admin['password_hash'].encode())
    except Exception as e:
        logger.error(f'❌ Login error: {e}')

    if valid:
        session['logged_in'] = True
        # Also try to issue JWT if user exists in new users table
        from db import get_user_by_email
        db_user = get_user_by_email(user)
        if db_user:
            from services.auth_service import create_access_token, create_refresh_token
            access  = create_access_token(db_user)
            refresh = create_refresh_token(db_user)
            resp = flask_jsonify({'status': 'ok'})
            secure = os.getenv('FLASK_ENV', 'production') == 'production'
            resp.set_cookie('access_token', access,
                            httponly=True, secure=secure, samesite='Lax', max_age=86400)
            resp.set_cookie('refresh_token', refresh,
                            httponly=True, secure=secure, samesite='Strict',
                            max_age=604800, path='/api/v1/auth/refresh')
            return resp
        return flask_jsonify({'status': 'ok'}), 200
    return flask_jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401


@app.route('/logout', methods=['POST'])
def legacy_logout():
    session.clear()
    resp = flask_jsonify({'status': 'ok'})
    resp.delete_cookie('access_token')
    resp.delete_cookie('refresh_token', path='/api/v1/auth/refresh')
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat thread
# ─────────────────────────────────────────────────────────────────────────────
def _heartbeat():
    while True:
        logger.info('💓 Heartbeat - Flask is alive')
        time.sleep(600)

threading.Thread(target=_heartbeat, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=False)
