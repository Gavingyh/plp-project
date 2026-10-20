"""ingest/arctic_shift.py: a failing page is retried and reported, never read as the end of the data."""

import ingest.arctic_shift as arc


class _Resp:
    def __init__(self, status, data=None, text=""):
        self.status_code, self._data, self.text, self.headers = status, data, text, {}

    def json(self):
        return {"data": self._data}


def _fake_get(responses, calls):
    def get(url, params=None, timeout=None):
        calls.append(params.get("after"))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return get


def test_a_transient_failure_is_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(arc.time, "sleep", lambda s: None)
    monkeypatch.setattr(arc.requests, "get", _fake_get(
        [_Resp(503), _Resp(200, [{"created_utc": 10, "id": "a"}])], calls))
    assert arc._get("comments", after="1") == [{"created_utc": 10, "id": "a"}]
    assert len(calls) == 2


def test_a_page_that_keeps_failing_marks_the_window_incomplete(monkeypatch):
    calls = []
    monkeypatch.setattr(arc.time, "sleep", lambda s: None)
    monkeypatch.setattr(arc, "INCOMPLETE_WINDOWS", [])
    full_page = [{"created_utc": i, "id": str(i)} for i in range(arc.PAGE_LIMIT)]
    monkeypatch.setattr(arc.requests, "get", _fake_get(
        [_Resp(200, full_page)] + [_Resp(422, text="timeout")] * (len(arc.RETRY_WAITS) + 1), calls))
    rows = arc._harvest_window("comments", "singaporefi", "2025-03-01", "2025-04-01", "body,id")
    assert len(rows) == arc.PAGE_LIMIT                       # the page that worked is kept
    assert arc.INCOMPLETE_WINDOWS and "singaporefi comments" in arc.INCOMPLETE_WINDOWS[0]


def test_an_empty_page_is_the_end_of_the_window(monkeypatch):
    monkeypatch.setattr(arc.time, "sleep", lambda s: None)
    monkeypatch.setattr(arc, "INCOMPLETE_WINDOWS", [])
    monkeypatch.setattr(arc.requests, "get", _fake_get([_Resp(200, [])], []))
    assert arc._harvest_window("posts", "singaporefi", "2025-03-01", "2025-04-01", "title,id") == []
    assert arc.INCOMPLETE_WINDOWS == []


def test_invalid_reddit_payload_is_retried_and_reported(monkeypatch):
    import pytest
    class Invalid(_Resp):
        def json(self):
            return {'message': 'upstream unavailable'}
    monkeypatch.setattr(arc.time, 'sleep', lambda s: None)
    calls = []
    monkeypatch.setattr(arc.requests, 'get', _fake_get([Invalid(200)] * (len(arc.RETRY_WAITS) + 1), calls))
    with pytest.raises(arc.PageFailed, match='invalid archive response'):
        arc._get('comments', after='1')
    assert len(calls) == len(arc.RETRY_WAITS) + 1


def test_reddit_page_limit_is_visible_as_incomplete_coverage(monkeypatch):
    monkeypatch.setattr(arc.time, 'sleep', lambda s: None)
    monkeypatch.setattr(arc, 'INCOMPLETE_WINDOWS', [])
    monkeypatch.setattr(arc, 'MAX_PAGES_PER_WINDOW', 1)
    rows = [{'created_utc': i, 'id': str(i)} for i in range(arc.PAGE_LIMIT)]
    monkeypatch.setattr(arc, '_get', lambda *a, **k: rows)
    assert arc._harvest_window('comments', 'singaporefi', '2024-05-01', '2024-05-02', 'body,id') == rows
    assert 'page limit reached' in arc.INCOMPLETE_WINDOWS[0]


def test_reddit_cursor_that_does_not_advance_is_visible(monkeypatch):
    monkeypatch.setattr(arc.time, 'sleep', lambda s: None)
    monkeypatch.setattr(arc, 'INCOMPLETE_WINDOWS', [])
    rows = [{'created_utc': i, 'id': str(i)} for i in range(arc.PAGE_LIMIT)]
    monkeypatch.setattr(arc, '_get', lambda *a, **k: rows)
    assert arc._harvest_window('comments', 'singaporefi', '2024-05-01', '2024-05-02', 'body,id') == rows
    assert 'did not advance' in arc.INCOMPLETE_WINDOWS[0]
