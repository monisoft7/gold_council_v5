# -*- coding: utf-8 -*-
"""اختبارات Walk-Forward — بيانات تركيبية حتمية."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import walk_forward


def _make_csv(path, n, seed=42):
    import numpy as np
    rng = np.random.RandomState(seed)
    df = pd.DataFrame({
        "day": pd.date_range("2026-01-01", periods=n).strftime("%Y-%m-%d"),
        "decision": "شراء",
        "win": (rng.rand(n) > 0.4).astype(int),
        "pnl_pct": rng.randn(n),
        "score": rng.rand(n) * 100,
        "confidence": rng.rand(n) * 100,
        "rsi": rng.rand(n) * 100,
        "war": (rng.rand(n) > 0.8).astype(int),
        "rate": (rng.rand(n) > 0.8).astype(int),
    })
    df.to_csv(path, index=False)
    return path


def test_insufficient_data_is_honest(tmp_path):
    csv = _make_csv(str(tmp_path / "f.csv"), 10)
    rep = walk_forward.run(csv, out=str(tmp_path / "rep.json"))
    assert rep["status"] == "insufficient_data"
    assert rep["rows"] == 10


def test_folds_computed_and_oos_reported(tmp_path):
    csv = _make_csv(str(tmp_path / "f.csv"), 60)
    rep = walk_forward.run(csv, train_min=20, test_size=6, step=6,
                           out=str(tmp_path / "rep.json"))
    assert rep["status"] == "ok"
    assert rep["oos_summary"]["n_folds"] >= 5
    assert 0.0 <= rep["oos_summary"]["acc_mean"] <= 1.0
    # التقرير كُتب فعلاً
    saved = json.loads((tmp_path / "rep.json").read_text(encoding="utf-8"))
    assert saved["status"] == "ok"
