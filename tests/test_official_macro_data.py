import official_macro_data as omd


class _Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


def test_fred_uses_initial_release_and_conservative_availability(monkeypatch):
    captured = {}
    payload = {"observations": [{
        "date": "2026-01-01", "realtime_start": "2026-02-10", "value": "3.2"
    }]}
    def get(url, params, timeout):
        captured.update(params); return _Response(payload)
    monkeypatch.setattr(omd.requests, "get", get)
    out = omd.fred_initial_release("CPIAUCSL", "2026-01-01", "2026-03-01",
                                   api_key="test")
    assert captured["output_type"] == 4
    assert out.iloc[0]["available_at"] > out.iloc[0]["released_at"]
    assert out.iloc[0]["value"] == 3.2


def test_daily_market_series_avoids_expensive_vintage_request(monkeypatch):
    captured = {}
    payload = {"observations": [{
        "date": "2026-01-02", "realtime_start": "2026-08-30", "value": "1.8"
    }]}
    def get(url, params, timeout):
        captured.update(params); return _Response(payload)
    monkeypatch.setattr(omd.requests, "get", get)
    out = omd.fred_initial_release("DFII10", "2026-01-01", "2026-02-01",
                                   api_key="test")
    assert captured["output_type"] == 1
    assert "realtime_start" not in captured
    assert str(out.iloc[0]["released_at"].date()) == "2026-01-02"


def test_bls_is_explicitly_not_point_in_time_safe(monkeypatch):
    payload = {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{
        "seriesID": "CUSR0000SA0", "data": [
            {"year": "2026", "period": "M01", "value": "320.1"},
            {"year": "2026", "period": "M13", "value": "999"},
        ]
    }]}}
    monkeypatch.setattr(omd.requests, "post", lambda *a, **k: _Response(payload))
    out = omd.bls_series(["CUSR0000SA0"], 2026, 2026, api_key="test")
    assert len(out) == 1
    assert not bool(out.iloc[0]["point_in_time_safe"])
