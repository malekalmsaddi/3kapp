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


@pytest.fixture
def client():
    with app.test_client() as c:
        yield c


def test_dashboard_data_endpoint(monkeypatch, client, auth_headers):
    # Stub DB — dashboard_data wraps get_conn in try/except and returns zeros on failure
    monkeypatch.setattr('blueprints.dashboard.get_conn', lambda: (_ for _ in ()).throw(RuntimeError('no db')))

    res = client.get('/dashboard/data', headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert 'labels' in data
    assert 'inbound' in data
    assert 'outbound' in data
    assert len(data['labels']) == len(data['inbound']) == len(data['outbound'])
