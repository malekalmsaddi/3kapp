import pytest

from tasks import process_bulk_file


class DummyTask:
    def apply_async(self, *args, **kwargs):
        return None


DUMMY_TENANT = '00000000-0000-0000-0000-000000000001'


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr('tasks.send_whatsapp_template', DummyTask())
    monkeypatch.setattr('tasks.log_message', Mock())
    monkeypatch.setattr('tasks.log_usage_event', Mock())
    yield


def test_process_bulk_file_empty():
    res = process_bulk_file.run(DUMMY_TENANT, '')
    assert res['status'] == 'failed'
    assert 'error' in res


def test_process_bulk_file_invalid_phone():
    csv_content = 'to,param1\nnotaphone,foo\n'
    res = process_bulk_file.run(DUMMY_TENANT, csv_content)
    assert res['status'] == 'completed'
    assert res['total_rows'] == 1
    assert res['results']['invalid_phone'] == [1]
