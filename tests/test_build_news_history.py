from datetime import datetime, timezone

import build_news_history as bnh


def test_parse_and_dedup_key_are_stable():
    parsed = bnh._parse_date("2019-01-02 03:04:05")
    assert parsed == datetime(2019, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    one = {"time": "2019-01-02T03:04:05+00:00", "title": "Gold rises 2%!"}
    two = {"time": "2019-01-02T09:00:00+00:00", "title": "gold rises 2"}
    assert bnh._key(one) == bnh._key(two)


def test_fetch_rejects_articles_outside_window(monkeypatch):
    class Response:
        text = ("Date,Title,URL,Language\n"
                "2019-01-02 10:00:00,Gold rises,https://example.com/a,English\n"
                "2019-01-04 10:00:00,Future item,https://example.com/b,English\n")
        def raise_for_status(self):
            return None
    monkeypatch.setattr(bnh.requests, "get", lambda *args, **kwargs: Response())
    start = datetime(2019, 1, 1, tzinfo=timezone.utc)
    end = datetime(2019, 1, 3, tzinfo=timezone.utc)
    rows = bnh.fetch_window(start, end)
    assert [row["title"] for row in rows] == ["Gold rises"]


def test_completed_windows_are_not_downloaded_again(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        bnh, "fetch_window",
        lambda start, end: calls.append((start, end)) or [],
    )
    start = datetime(2019, 1, 1, tzinfo=timezone.utc)
    end = datetime(2019, 1, 15, tzinfo=timezone.utc)
    output = tmp_path / "news.csv"
    bnh.build(start, end, output, window_days=7, pause=0)
    bnh.build(start, end, output, window_days=7, pause=0)
    assert len(calls) == 2
