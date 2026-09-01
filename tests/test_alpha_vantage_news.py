from datetime import datetime, timezone

import alpha_vantage_news as avn


def test_filters_by_time_and_gold_causality(monkeypatch):
    monkeypatch.setattr(avn.env, "get", lambda key: "secret")
    class Response:
        status_code = 200
        def json(self):
            return {"feed": [
                {"time_published": "20230201T180000", "title": "Fed decision ahead",
                 "summary": "Gold traders watch Powell", "source": "wire"},
                {"time_published": "20230203T180000", "title": "Future article",
                 "summary": "gold", "source": "wire"},
                {"time_published": "20230201T170000", "title": "Celebrity news",
                 "summary": "movies", "source": "wire"},
            ]}
    monkeypatch.setattr(avn.requests, "get", lambda *args, **kwargs: Response())
    start = datetime(2023, 2, 1, tzinfo=timezone.utc)
    end = datetime(2023, 2, 2, tzinfo=timezone.utc)
    rows = avn.fetch_window(start, end)
    assert [row["title"] for row in rows] == ["Fed decision ahead"]


def test_api_error_is_sanitized(monkeypatch):
    monkeypatch.setattr(avn.env, "get", lambda key: "secret")
    class Response:
        status_code = 200
        def json(self): return {"Information": "rate limit"}
    monkeypatch.setattr(avn.requests, "get", lambda *args, **kwargs: Response())
    now = datetime(2023, 1, 1, tzinfo=timezone.utc)
    try:
        avn.fetch_window(now, now.replace(day=2))
    except RuntimeError as exc:
        assert "secret" not in str(exc)
        assert "rate limit" in str(exc)
    else:
        raise AssertionError("expected safe API error")
