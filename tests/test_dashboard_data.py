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


def test_dashboard_data_endpoint():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['logged_in'] = True

    res = client.get('/dashboard/data')
    assert res.status_code == 200
    data = res.get_json()
    assert 'labels' in data
    assert 'inbound' in data
    assert 'outbound' in data
    assert len(data['labels']) == len(data['inbound']) == len(data['outbound'])
