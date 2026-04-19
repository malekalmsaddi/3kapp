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
import ssl
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
    'DATABASE_URL', 'REDIS_URL', 'FLASK_SECRET_KEY',
    'JWT_SECRET_KEY', 'ENCRYPTION_KEY',
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
_redis_url = os.getenv('REDIS_URL')
_storage_options = {}
if _redis_url and _redis_url.startswith('rediss://'):
    _storage_options['ssl_cert_reqs'] = ssl.CERT_NONE

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_redis_url,
    storage_options=_storage_options,
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
app.register_blueprint(auth_bp,       url_prefix='/v1/auth', name='auth_v1_proxy')
app.register_blueprint(onboarding_bp, url_prefix='/api/v1/onboarding')
app.register_blueprint(onboarding_bp, url_prefix='/v1/onboarding', name='onboarding_v1_proxy')
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
# settings_bp is exempt (hosts /health) — no explicit limit applied
limiter.limit('5 per minute')(auth_bp)
limiter.limit('200 per minute')(dashboard_bp)
limiter.limit('20 per minute')(messaging_bp)
limiter.exempt(settings_bp)

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
