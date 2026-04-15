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
from tasks import process_bulk_file  # noqa: E402


class DummyTask:
    def apply_async(self, *args, **kwargs):
        return None


def noop(*args, **kwargs):
    return None


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    monkeypatch.setattr('tasks.send_whatsapp_template', DummyTask())
    monkeypatch.setattr('tasks.log_message', noop)
    yield


def test_process_bulk_file_empty():
    res = process_bulk_file.run('')
    assert res['status'] == 'failed'
    assert 'error' in res


def test_process_bulk_file_invalid_phone():
    csv_content = 'to,param1\nnotaphone,foo\n'
    res = process_bulk_file.run(csv_content)
    assert res['status'] == 'completed'
    assert res['total_rows'] == 1
    assert res['results']['invalid_phone'] == [1]
