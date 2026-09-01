import pandas as pd

import official_event_news_sample as sample


def test_event_type_normalization():
    assert sample.normalize_event_type("CPI", "release") == "CPI"
    assert sample.normalize_event_type("الفيدرالي والفائدة", "meeting") == "FOMC"
    assert sample.normalize_event_type("jobs", "US Nonfarm Payrolls") == "NFP"


def test_sample_uses_same_source_day_and_future_availability():
    events = pd.DataFrame([{
        "time": "2023-02-01T19:00:00Z", "title": "FOMC Meeting",
        "section": "الفيدرالي والفائدة",
    }])
    news = pd.DataFrame([
        {"time": "2023-02-02T00:00:00Z", "source_date": "2023-02-01",
         "title": "Fed raises interest rate"},
        {"time": "2023-02-03T00:00:00Z", "source_date": "2023-02-02",
         "title": "Powell speaks later"},
    ])
    result = sample.build_sample(events, news, start="2023-01-01",
                                 end="2023-03-01", per_type=2)
    assert len(result) == 1
    assert result[0]["headlines"] == ["Fed raises interest rate"]
    assert result[0]["available_at"] == "2023-02-02T00:00:00+00:00"
