import os
import sys
import time
from pathlib import Path
import pytest
import jwt as _jwt

# Ensure project root is on the path for all test files
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Set all test env vars at module level — conftest runs before any test file
# imports app.py, so these values are seen before load_dotenv() can override them.
_TEST_SECRET = 'test-secret-key'
os.environ['JWT_SECRET_KEY'] = _TEST_SECRET
os.environ.setdefault('FLASK_SECRET_KEY', _TEST_SECRET)
os.environ.setdefault('ENCRYPTION_KEY', 'Fxr1Ql3E1V39OT0IvR3s9jR3VBr8iFTqFe-s8dXfp_s=')
os.environ.setdefault('TWILIO_ACCOUNT_SID', 'test')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test')
os.environ.setdefault('TWILIO_WHATSAPP_NUMBER', '+1234567890')
os.environ.setdefault('OPENAI_API_KEY', 'test')
os.environ.setdefault('ASSISTANT_ID', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('ADMIN_USERNAME', 'admin')
os.environ.setdefault('ADMIN_PASSWORD_HASH', 'hash')


def _mint():
    now = int(time.time())
    # Omit 'jti' so the middleware's `if jti and redis_connection.get(...)`
    # short-circuits to False — no Redis connection needed in tests.
    return _jwt.encode({
        'sub': 'test-user',
        'tid': '00000000-0000-0000-0000-000000000001',
        'tslug': 'moeen',
        'role': 'tenant',
        'email': 'test@example.com',
        'iat': now,
        'exp': now + 3600,
    }, _TEST_SECRET, algorithm='HS256')


@pytest.fixture
def auth_headers():
    """Bearer JWT Authorization header for Flask endpoint tests."""
    return {'Authorization': f'Bearer {_mint()}'}
