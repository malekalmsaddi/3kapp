import pytest

from app import app, limiter

app.config['RATELIMIT_ENABLED'] = False
limiter.enabled = False
app.config['WTF_CSRF_ENABLED'] = False


@pytest.fixture
def client():
    with app.test_client() as c:
        yield c


def test_send_email_success(monkeypatch, client, auth_headers):
    monkeypatch.setattr(
        'blueprints.settings.send_email',
        lambda to, sub, body: {'status': 'success', 'sent': [to], 'failed': {}},
    )
    res = client.post(
        '/send_email',
        json={'to_email': 'a@b.com', 'subject': 'hi', 'body': 'msg'},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'success'
    assert data['sent'] == ['a@b.com']


def test_send_email_failure(monkeypatch, client, auth_headers):
    monkeypatch.setattr(
        'blueprints.settings.send_email',
        lambda to, sub, body: {'status': 'error', 'sent': [], 'failed': {to: 'err'}},
    )
    res = client.post(
        '/send_email',
        json={'to_email': 'a@b.com', 'subject': 'hi', 'body': 'msg'},
        headers=auth_headers,
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data['status'] == 'error'
    assert data['failed'] == {'a@b.com': 'err'}
