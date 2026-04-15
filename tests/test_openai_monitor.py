import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault('TWILIO_ACCOUNT_SID', 'test')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test')
os.environ.setdefault('TWILIO_WHATSAPP_NUMBER', '+1234567890')
os.environ.setdefault('OPENAI_API_KEY', 'test')
os.environ.setdefault('ASSISTANT_ID', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('FLASK_SECRET_KEY', 'secret')
os.environ.setdefault('ADMIN_USERNAME', 'admin')
os.environ.setdefault('ADMIN_PASSWORD_HASH', 'hash')

sys.path.append(str(Path(__file__).resolve().parents[1]))
from tasks import monitor_openai_thread_and_flush  # noqa: E402
import utils  # noqa: E402
import redis_client  # noqa: E402
import llm_utils  # noqa: E402


class DummyRedis:
    def get(self, key):
        return None

    def delete(self, key):
        return None


class DummyRun:
    id = 'run123'


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    monkeypatch.setattr(redis_client, 'redis_connection', DummyRedis())
    monkeypatch.setattr(llm_utils, 'flush_queued_messages', lambda thread_id, user: DummyRun())
    monkeypatch.setattr(llm_utils, 'poll_with_backoff', lambda thread_id, run_id, user: None)
    monkeypatch.setattr(llm_utils, 'get_or_create_thread_id', lambda user: 'thread123')
    monkeypatch.setattr('tasks.notify_error', lambda *a, **k: None)
    monkeypatch.setattr(utils, 'openai_client', None)
    yield


def test_monitor_handles_missing_client():
    # Should not raise even if openai_client is None
    monitor_openai_thread_and_flush.run('123', 'hi')
