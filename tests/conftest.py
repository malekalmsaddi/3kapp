import os
import time
import pytest
import jwt as _jwt

# Set JWT_SECRET_KEY at module level — conftest runs before test files import
# app.py, so load_dotenv() (called inside app) will see this value already
# in the environment and not override it with the .env production secret.
_TEST_SECRET = 'test-secret-key'
os.environ['JWT_SECRET_KEY'] = _TEST_SECRET
os.environ.setdefault('FLASK_SECRET_KEY', _TEST_SECRET)


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
