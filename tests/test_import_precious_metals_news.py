from pathlib import Path

import pandas as pd

import import_precious_metals_news as importer


def test_only_causal_headlines_and_next_day_availability(tmp_path):
    source = tmp_path / "raw.csv"
    pd.DataFrame([{
        "timestamp": "2019-01-02", "headlines":
        "Celebrity Story / Fed Signals Rate Pause / Gold Hits High",
    }]).to_csv(source, sep=";", index=False)
    output = tmp_path / "news.csv"
    rows = importer.convert(source, output, start="2019-01-01", end="2019-02-01")
    assert [row["title"] for row in rows] == ["Fed Signals Rate Pause", "Gold Hits High"]
    assert all(row["time"].startswith("2019-01-03T00:00:00") for row in rows)
    assert all(row["timing_precision"] == "next_day_conservative" for row in rows)
