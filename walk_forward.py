# -*- coding: utf-8 -*-
"""التحقق المتدحرج Walk-Forward — الفجوة 3 (بديل LOO للعينات الأكبر).

يقسّم features_v5.csv زمنياً (مرتّباً بعمود day إن وُجد) إلى نوافذ:
  [train_min صف تدريب] → [test_size صف اختبار خارج العينة] → إزاحة step
ثم يجمع مقاييس OOS فقط — وهي الأرقام الوحيدة الجديرة بالثقة.

تشغيل:
  python walk_forward.py --features features_v5.csv --out walk_forward_report.json
"""
import argparse
import json
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

warnings.filterwarnings("ignore")


def run(features_csv: str, train_min: int = 20, test_size: int = 6,
        step: int = 6, out: str = "walk_forward_report.json",
        purge_days: int = 7, embargo_days: int = 1) -> dict:
    from ml_trainer import pick_model, DROP_COLS

    df = pd.read_csv(features_csv).drop_duplicates().fillna(0)
    if "day" not in df.columns:
        report = {"status": "missing_time_axis", "rows": int(len(df)),
                  "hint": "أعد توليد الميزات؛ يلزم عمود day لمنع التسرب الزمني"}
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return report
    df["day"] = pd.to_datetime(df["day"], utc=True, errors="coerce")
    df = df.dropna(subset=["day"]).sort_values("day").reset_index(drop=True)
    n = len(df)
    needed = train_min + purge_days + embargo_days + 1 + test_size
    if n < needed:
        report = {"status": "insufficient_data", "rows": int(n), "needed": needed,
                  "hint": "شغّل backtester.py بفاصل --step 2 ومدة أطول لتوليد صفقات أكثر"}
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return report

    y_all = df["win"].astype(int).values
    cols = [c for c in df.columns if c not in DROP_COLS]
    X = df[cols].astype(float).values

    folds = []
    test_start = train_min + purge_days + embargo_days + 1
    effective_step = max(step, test_size)  # لا نقيّم الصف نفسه مرتين
    while test_start + test_size <= n:
        test_idx = np.arange(test_start, test_start + test_size)
        test_first_day = df.loc[test_start, "day"]
        horizons = pd.to_numeric(df.get("exit_window_days", purge_days), errors="coerce")
        if not isinstance(horizons, pd.Series):
            horizons = pd.Series([horizons] * n)
        horizons = horizons.fillna(purge_days).clip(lower=purge_days)
        label_end = df["day"] + pd.to_timedelta(horizons, unit="D")
        cutoff = test_first_day - pd.Timedelta(days=embargo_days)
        train_idx = np.where((np.arange(n) < test_start) & (label_end < cutoff))[0]
        if len(train_idx) < train_min or len(set(y_all[train_idx])) < 2:
            test_start += effective_step
            continue
        name, model = pick_model(int(len(train_idx)))
        model.fit(X[train_idx], y_all[train_idx])
        pred = model.predict(X[test_idx])
        acc = float(accuracy_score(y_all[test_idx], pred))
        f1 = float(f1_score(y_all[test_idx], pred, zero_division=0))
        try:
            prob = model.predict_proba(X[test_idx])[:, 1]
            auc = float(roc_auc_score(y_all[test_idx], prob)) if len(set(y_all[test_idx])) > 1 else None
        except Exception:
            auc = None
        folds.append({
            "train_rows": int(len(train_idx)),
            "train_last_day": str(df.loc[train_idx[-1], "day"]),
            "test_rows": [int(test_start), int(test_start + test_size)],
            "oos_acc": round(acc, 3), "oos_f1": round(f1, 3),
            "oos_auc": round(auc, 3) if auc is not None else None,
            "test_win_rate_actual": round(float(y_all[test_idx].mean()), 3),
            "model": name,
        })
        test_start += effective_step

    if not folds:
        report = {"status": "no_valid_folds", "rows": int(n)}
    else:
        accs = [f["oos_acc"] for f in folds]
        f1s = [f["oos_f1"] for f in folds]
        report = {
            "status": "ok",
            "rows": int(n),
            "config": {"train_min": train_min, "test_size": test_size,
                       "step": effective_step, "purge_days": purge_days,
                       "embargo_days": embargo_days},
            "folds": folds,
            "oos_summary": {
                "n_folds": len(folds),
                "acc_mean": round(float(np.mean(accs)), 3),
                "acc_min": round(float(np.min(accs)), 3),
                "f1_mean": round(float(np.mean(f1s)), 3),
                "verdict": ("✅ إشارة قابلة للتعميم خارج العينة"
                            if np.mean(accs) >= 0.6 else
                            "⚠ الأداء خارج العينة ضعيف — النموذج يحفظ لا يتعلّم"),
            },
        }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True)
    ap.add_argument("--train-min", type=int, default=20)
    ap.add_argument("--test-size", type=int, default=6)
    ap.add_argument("--step", type=int, default=6)
    ap.add_argument("--purge-days", type=int, default=7)
    ap.add_argument("--embargo-days", type=int, default=1)
    ap.add_argument("--out", default="walk_forward_report.json")
    args = ap.parse_args()
    rep = run(args.features, args.train_min, args.test_size, args.step, args.out,
              args.purge_days, args.embargo_days)
    print(json.dumps(rep, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        sys.exit(1)
