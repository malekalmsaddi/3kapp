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


def test_settings_toggle():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['logged_in'] = True
    # Ensure page loads
    res = client.get('/settings')
    assert res.status_code == 200
    # Disable notifications
    res = client.post('/settings', data={})
    assert res.status_code == 302
    with client.session_transaction() as sess:
        assert sess['notify'] is False
    # Enable notifications
    res = client.post('/settings', data={'notify': 'on'})
    assert res.status_code == 302
    with client.session_transaction() as sess:
        assert sess['notify'] is True
