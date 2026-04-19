import pytest

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
