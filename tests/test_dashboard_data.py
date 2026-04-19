import pytest

from app import app, limiter

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
