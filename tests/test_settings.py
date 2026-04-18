import os
import pytest
import sys
from pathlib import Path

os.environ.setdefault('TWILIO_ACCOUNT_SID', 'test')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test')
os.environ.setdefault('TWILIO_WHATSAPP_NUMBER', 'test')
os.environ.setdefault('OPENAI_API_KEY', 'test')
os.environ.setdefault('ASSISTANT_ID', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('FLASK_SECRET_KEY', 'secret')
os.environ.setdefault('ADMIN_USERNAME', 'admin')
os.environ.setdefault('ADMIN_PASSWORD_HASH', 'hash')

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app import app, limiter

app.config['RATELIMIT_ENABLED'] = False
limiter.enabled = False
app.config['WTF_CSRF_ENABLED'] = False


@pytest.fixture
def client():
    with app.test_client() as c:
        yield c


def test_settings_toggle(client, auth_headers):
    # Default notify is True
    res = client.get('/settings', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['notify'] is True

    # POST with no notify key → False
    res = client.post('/settings', json={}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['notify'] is False

    # POST with notify=True → True
    res = client.post('/settings', json={'notify': True}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['notify'] is True
