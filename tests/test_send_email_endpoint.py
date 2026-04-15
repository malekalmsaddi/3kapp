import os
import sys
from pathlib import Path

import pytest

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
from app import app, limiter  # noqa: E402

app.config['RATELIMIT_ENABLED'] = False
limiter.enabled = False
app.config['WTF_CSRF_ENABLED'] = False


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client


def test_send_email_success(monkeypatch, client):
    monkeypatch.setattr('app.send_email', lambda to, sub, body: {'status': 'success', 'sent': [to], 'failed': {}})
    res = client.post('/send_email', json={'to_email': 'a@b.com', 'subject': 'hi', 'body': 'msg'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'success'
    assert data['sent'] == ['a@b.com']


def test_send_email_failure(monkeypatch, client):
    monkeypatch.setattr('app.send_email', lambda to, sub, body: {'status': 'error', 'sent': [], 'failed': {to: 'err'}})
    res = client.post('/send_email', json={'to_email': 'a@b.com', 'subject': 'hi', 'body': 'msg'})
    assert res.status_code == 400
    data = res.get_json()
    assert data['status'] == 'error'
    assert data['failed'] == {'a@b.com': 'err'}
