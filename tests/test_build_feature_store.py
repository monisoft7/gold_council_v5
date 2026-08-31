import pandas as pd

from build_feature_store import build


def test_store_never_uses_future_release(tmp_path):
    facts = pd.DataFrame({
        "observed_at": ["2026-01-01"], "released_at": ["2026-01-10"],
        "available_at": ["2026-01-11"], "value": [2.0],
    })
    facts.to_csv(tmp_path / "fred_real_yield_10y.csv", index=False)
    decisions = pd.DataFrame({"decision_at": ["2026-01-10", "2026-01-12"]})
    out = build(decisions, tmp_path)
    assert pd.isna(out.iloc[0]["real_yield_10y_value"])
    assert out.iloc[1]["real_yield_10y_value"] == 2.0
