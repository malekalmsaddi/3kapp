from unittest.mock import Mock

import pytest

from tasks import monitor_openai_thread_and_flush

_UNSET = object()


class DummyRedis:
    def __init__(self, active_run_iters=0):
        self._active_run_counter = active_run_iters

    def get(self, key):
        if 'active_run' in key and self._active_run_counter > 0:
            self._active_run_counter -= 1
            return b'run_id'
        return None

    def delete(self, _):
        return None


class DummyRun:
    id = 'run123'


class MockProvider:
    def __init__(self, flush_result=_UNSET, poll_result=_UNSET, fetch_result='reply text'):
        self._flush_result = DummyRun() if flush_result is _UNSET else flush_result
        self._poll_result = DummyRun() if poll_result is _UNSET else poll_result
        self._fetch_result = fetch_result
        self.polled = False

    def get_or_create_thread(self, _):
        return 'thread123'

    def flush_queue(self, *_):
        return self._flush_result

    def _poll(self, *_):
        self.polled = True
        return self._poll_result

    def _fetch_response(self, *_):
        return self._fetch_result


def _make_loader(provider, redis=None):
    r = redis or DummyRedis()
    return lambda _: (provider, {}, r)


@pytest.fixture
def patch_dependencies(monkeypatch):
    """Patch _load_ai_provider and all side-effecting callables the task uses."""
    calls = {'send_whatsapp': [], 'notify_error': []}

    monkeypatch.setattr('tasks._load_ai_provider', lambda _: (MockProvider(), {}, DummyRedis()))
    monkeypatch.setattr('tasks.send_whatsapp',
                        lambda to, msg: calls['send_whatsapp'].append((to, msg)))
    monkeypatch.setattr('tasks.log_message', Mock())
    monkeypatch.setattr('tasks.log_usage_event', Mock())
    monkeypatch.setattr('tasks.notify_error',
                        lambda num, msg: calls['notify_error'].append((num, msg)))
    return calls


def test_happy_path(monkeypatch, patch_dependencies):
    provider = MockProvider(fetch_result='hello')
    monkeypatch.setattr('tasks._load_ai_provider', _make_loader(provider))

    monitor_openai_thread_and_flush.run('tenant-1', '+97412345678')

    assert provider.polled
    assert patch_dependencies['send_whatsapp'] == [('+97412345678', 'hello')]


def test_flush_returns_none(monkeypatch, patch_dependencies):
    provider = MockProvider(flush_result=None)
    monkeypatch.setattr('tasks._load_ai_provider', _make_loader(provider))

    monitor_openai_thread_and_flush.run('tenant-1', '+97412345678')

    assert not provider.polled
    assert patch_dependencies['send_whatsapp'] == []


def test_poll_raises_calls_notify_error(monkeypatch, patch_dependencies):
    class RaisingProvider(MockProvider):
        def _poll(self, *_):
            raise RuntimeError('OpenAI error')

    provider = RaisingProvider()
    monkeypatch.setattr('tasks._load_ai_provider', _make_loader(provider))

    monitor_openai_thread_and_flush.run('tenant-1', '+97412345678')

    assert patch_dependencies['notify_error']
    assert patch_dependencies['send_whatsapp'] == []


def test_fetch_none_skips_send(monkeypatch, patch_dependencies):
    provider = MockProvider(fetch_result=None)
    monkeypatch.setattr('tasks._load_ai_provider', _make_loader(provider))

    monitor_openai_thread_and_flush.run('tenant-1', '+97412345678')

    assert provider.polled
    assert patch_dependencies['send_whatsapp'] == []


def test_active_run_waits_then_proceeds(monkeypatch, patch_dependencies):
    provider = MockProvider(fetch_result='done')
    monkeypatch.setattr('tasks._load_ai_provider', _make_loader(provider, DummyRedis(active_run_iters=2)))
    monkeypatch.setattr('tasks.time.sleep', lambda _: None)

    monitor_openai_thread_and_flush.run('tenant-1', '+97412345678')

    assert provider.polled
    assert patch_dependencies['send_whatsapp'] == [('+97412345678', 'done')]
