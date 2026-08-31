# -*- coding: utf-8 -*-
"""تدريب مصنّف على نتائج الباك-تست V5:
- إذا الصفوف ≥30: TimeSeriesSplit(5) + XGBoost إذا متوفر، وإلا GradientBoosting
- إذا الصفوف ≥15: LeaveOneOut + GradientBoosting (يعمل بأمان)
- معايرة احتمالات عند توفر الصفوف الكافية
- حفظ model.pkl و feat_names.json
"""
import argparse, json, os, sys, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit, LeaveOneOut
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score
import joblib

warnings.filterwarnings("ignore")

# --- قوائم الأعمدة التي لا تُستخدم كأرقامية ---
DROP_COLS = {"win", "pnl_pct", "day", "decision", "exit_window_days"}


def load_features(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "win" not in df.columns:
        raise ValueError("features CSV must contain 'win' column")
    df = df.fillna(0)
    return df


def pick_model(rows: int):
    try:
        import xgboost as xgb
        base = xgb.XGBClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.07,
            subsample=0.9, colsample_bytree=0.8,
            eval_metric="logloss", random_state=42, n_jobs=1)
        return "xgboost", base
    except Exception:
        base = GradientBoostingClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.07, random_state=42)
        return "sklearn_gb", base


def train(df: pd.DataFrame, model_out: str, names_out: str) -> dict:
    # التكرارات الناتجة من تشغيل نفس الفترة أكثر من مرة تضخم المقاييس كذباً.
    df = df.drop_duplicates().reset_index(drop=True)
    y = df["win"].astype(int).values
    feat_cols = [c for c in df.columns if c not in DROP_COLS]
    X = df[feat_cols].astype(float).values
    n = len(df)

    if n < 100:
        return {"status": "error",
                "msg": (f"عدد الصفقات المستقلة قليل جداً ({n}). الحد الأدنى "
                        "المهني المؤقت: 100 صف بعد إزالة التكرار.")}

    model_name, model = pick_model(n)
    print(f"[INFO] rows={n} features={len(feat_cols)} model={model_name}")

    metrics = {"rows": int(n), "features": len(feat_cols),
               "model": model_name, "folds": []}

    if n >= 30:
        # TimeSeriesSplit مع k ديناميكي بحسب حجم العينة
        k = min(5, max(2, n // 10))
        tss = TimeSeriesSplit(n_splits=k)
        for fold, (tr, vl) in enumerate(tss.split(X), 1):
            m = pick_model(n)[1]
            m.fit(X[tr], y[tr])
            try:
                p = m.predict_proba(X[vl])[:, 1]
            except Exception:
                p = m.predict(X[vl]).astype(float)
            auc = roc_auc_score(y[vl], p) if len(set(y[vl])) > 1 else None
            f1 = f1_score(y[vl], m.predict(X[vl]), zero_division=0)
            acc = accuracy_score(y[vl], m.predict(X[vl]))
            metrics["folds"].append({"fold": fold, "auc": auc,
                                     "f1": f1, "acc": acc})
            print(f"[FOLD {fold}] AUC={auc}  F1={f1:.3f}  ACC={acc:.3f}")

        # إعادة تدريب على كامل البيانات للمعايرة + الحفظ
        model.fit(X, y)
        if k >= 3:
            try:
                cal = CalibratedClassifierCV(pick_model(n)[1], cv=3, method="isotonic")
                cal.fit(X, y)
                model_to_save = cal
            except Exception as e:
                print(f"[WARN] calibration failed: {e}")
                model_to_save = model
        else:
            model_to_save = model
    else:
        # LeaveOneOut لعينة صغيرة (15-29 صف)
        loo = LeaveOneOut()
        yp, ys = [], []
        for tr, vl in loo.split(X):
            m = pick_model(n)[1]
            m.fit(X[tr], y[tr])
            yp.append(int(m.predict(X[vl])[0]))
            ys.append(int(y[vl][0]))
        acc = accuracy_score(ys, yp)
        f1 = f1_score(ys, yp, zero_division=0)
        metrics["folds"].append({"fold": "LOO", "auc": None,
                                 "f1": f1, "acc": acc})
        print(f"[LOO] F1={f1:.3f}  ACC={acc:.3f}")
        # حفظ النموذج المُدرَّب على كامل البيانات
        model.fit(X, y)
        model_to_save = model

    joblib.dump({"model": model_to_save, "feat_cols": feat_cols}, model_out)
    with open(names_out, "w", encoding="utf-8") as f:
        json.dump({"feat_cols": feat_cols, "rows": n, "model": model_name,
                   "metrics": metrics}, f, ensure_ascii=False, indent=2)

    metrics["model_path"] = model_out
    metrics["names_path"] = names_out
    metrics["status"] = "ok"
    print(f"[OK] saved: {model_out} | {names_out}")
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", required=True)
    ap.add_argument("--model-out", default="model.pkl")
    ap.add_argument("--features-out", default="feat_names.json")
    args = ap.parse_args()

    df = load_features(args.features)
    metrics = train(df, args.model_out, args.features_out)
    print("\n=== METRICS ===")
    print(json.dumps(metrics, ensure_ascii=False, indent=2,
                     default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        sys.exit(1)
