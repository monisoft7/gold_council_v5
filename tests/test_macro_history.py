import pandas as pd

from macro_history import assemble


def test_macro_series_are_aligned_by_session_and_lagged():
    dxy = pd.DataFrame({
        "observed_at": ["2026-01-01T20:00:00Z", "2026-01-02T20:00:00Z"],
        "close": [100.0, 101.0],
    })
    vix = pd.DataFrame({
        "observed_at": ["2026-01-02T21:00:00Z"], "close": [18.0],
    })
    out = assemble({"dxy": dxy, "vix": vix})
    assert len(out) == 2
    assert out.iloc[1]["dxy"] == 101.0
    assert out.iloc[1]["vix"] == 18.0
    assert out.iloc[1]["available_at"] > out.iloc[1]["observed_at"]
