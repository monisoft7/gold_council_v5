import pandas as pd

from nfp_dataset_quality import audit_nfp_dataset


def _official():
    return pd.DataFrame([{
        "time": "2024-03-08T13:30:00Z", "title": "US Nonfarm Payrolls official release",
        "section": "NFP", "source": "test",
    }])


def _official_with_untrusted_duplicate():
    return pd.DataFrame([
        {
            "time": "2024-03-01T13:30:00Z",
            "title": "US Employment Situation — Nonfarm Payrolls",
            "section": "NFP", "source": "bls.gov",
        },
        {
            "time": "2024-03-08T13:30:00Z",
            "title": "US Nonfarm Payrolls official release",
            "section": "NFP", "source": "FRED/ALFRED+BLS",
        },
    ])


def test_rejects_empty_inputs_naive_time_and_future_outcome():
    data = pd.DataFrame([{
        "date": "2026-09-04 14:30:00", "nfp_actual": None,
        "nfp_forecast": None, "nfp_surprise": None,
        "xau_m5_range_pips": 4.49, "xau_h1_direction": "BEARISH",
    }])
    report = audit_nfp_dataset(data, as_of="2026-09-02T00:00:00Z",
                               official_events=_official(),
                               source_timezone="Asia/Jerusalem")
    assert report["usable_for_surprise_model"] is False
    assert report["future_outcome_cells"] == 2
    assert report["numeric_input_complete_pct"] == 0


def test_accepts_complete_causal_row_matching_official_schedule():
    data = pd.DataFrame([{
        "date": "2024-03-08T13:30:00Z", "nfp_actual": 275,
        "nfp_forecast": 198, "nfp_surprise": 77,
        "xau_m5_range_pips": 2.0, "xau_h1_direction": "BULLISH",
        "source": "test", "feature_available_at": "2024-03-08T13:30:00Z",
    }])
    report = audit_nfp_dataset(data, as_of="2024-03-09T00:00:00Z",
                               official_events=_official())
    assert report["usable_for_surprise_model"] is True
    assert report["official_schedule_match_pct"] == 100


def test_accepts_declared_jerusalem_time_and_matches_exact_release():
    data = pd.DataFrame([{
        "date": "2024-03-08 15:30:00", "nfp_actual": 275,
        "nfp_forecast": 198, "nfp_surprise": 77,
        "xau_m5_range_pips": 2.0, "xau_h1_direction": "BULLISH",
        "source": "test", "feature_available_at": "2024-03-08T13:30:00Z",
    }])
    report = audit_nfp_dataset(
        data, as_of="2024-03-09T00:00:00Z", official_events=_official(),
        source_timezone="Asia/Jerusalem",
    )
    assert report["usable_for_surprise_model"] is True
    assert report["start"] == "2024-03-08T13:30:00+00:00"
    assert report["maximum_schedule_delta_minutes"] == 0


def test_prefers_trusted_schedule_and_rejects_wrong_first_friday():
    data = pd.DataFrame([{
        "date": "2024-03-01T13:30:00Z", "nfp_actual": 275,
        "nfp_forecast": 198, "nfp_surprise": 77,
        "source": "test", "feature_available_at": "2024-03-01T13:30:00Z",
    }])
    report = audit_nfp_dataset(
        data, as_of="2024-03-09T00:00:00Z",
        official_events=_official_with_untrusted_duplicate(),
    )
    assert report["usable_for_surprise_model"] is False
    assert report["official_schedule_match_pct"] == 0
    assert report["mismatched_timestamps"] == ["2024-03-01T13:30:00+00:00"]
