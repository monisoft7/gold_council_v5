# -*- coding: utf-8 -*-
"""Train a local past-vs-future headline filter on the annotated gold corpus.

This model is a research pre-filter only. It never predicts gold direction and is
not wired into council voting. Evaluation uses a chronological holdout and balanced
metrics because the future-information class is rare.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (balanced_accuracy_score, confusion_matrix,
                             precision_recall_fscore_support, roc_auc_score)
from sklearn.pipeline import Pipeline


def prepare_frame(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["Dates"], dayfirst=True, errors="coerce")
    frame["text"] = frame["News"].fillna("").astype(str).str.strip()
    frame["target_future"] = pd.to_numeric(
        frame["Future Information"], errors="coerce"
    )
    frame = frame[
        frame["date"].dt.year.between(2000, 2021) &
        frame["target_future"].isin([0, 1]) & frame["text"].ne("")
    ].copy()
    frame = frame.drop_duplicates(subset=["text"], keep="first")
    return frame.sort_values("date").reset_index(drop=True)


def train(frame: pd.DataFrame, *, train_fraction=0.8):
    dates = frame["date"].drop_duplicates().sort_values().tolist()
    if len(dates) < 10:
        raise ValueError("not enough distinct dates")
    cutoff = dates[max(1, int(len(dates) * train_fraction))]
    train_frame = frame[frame["date"] < cutoff]
    test_frame = frame[frame["date"] >= cutoff]
    if train_frame["target_future"].nunique() < 2 or test_frame["target_future"].nunique() < 2:
        raise ValueError("both chronological splits must contain both classes")
    model = Pipeline([
        ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=2,
                                  max_features=30000, sublinear_tf=True)),
        ("classifier", LogisticRegression(class_weight="balanced", max_iter=1200,
                                           random_state=42)),
    ])
    model.fit(train_frame["text"], train_frame["target_future"])
    probability = model.predict_proba(test_frame["text"])[:, 1]
    predicted = (probability >= 0.5).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        test_frame["target_future"], predicted, average="binary", zero_division=0
    )
    report = {
        "task": "future_information_vs_past_or_other",
        "cutoff": pd.Timestamp(cutoff).date().isoformat(),
        "train_rows": len(train_frame), "test_rows": len(test_frame),
        "train_future": int(train_frame["target_future"].sum()),
        "test_future": int(test_frame["target_future"].sum()),
        "balanced_accuracy": round(float(balanced_accuracy_score(
            test_frame["target_future"], predicted)), 4),
        "future_precision": round(float(precision), 4),
        "future_recall": round(float(recall), 4),
        "future_f1": round(float(f1), 4),
        "roc_auc": round(float(roc_auc_score(test_frame["target_future"], probability)), 4),
        "confusion_matrix": confusion_matrix(
            test_frame["target_future"], predicted, labels=[0, 1]
        ).tolist(),
        "thresholds": {},
        "voting_enabled": False,
    }
    for threshold in (0.5, 0.7, 0.8, 0.9):
        threshold_prediction = (probability >= threshold).astype(int)
        p, r, threshold_f1, _ = precision_recall_fscore_support(
            test_frame["target_future"], threshold_prediction,
            average="binary", zero_division=0,
        )
        report["thresholds"][str(threshold)] = {
            "precision": round(float(p), 4), "recall": round(float(r), 4),
            "f1": round(float(threshold_f1), 4),
            "selected": int(threshold_prediction.sum()),
        }
    return model, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data_cache/gold-dataset-sinha-khandait.csv")
    parser.add_argument("--model", default="data_cache/news_timing_model.joblib")
    parser.add_argument("--report", default="data_cache/news_timing_model_report.json")
    args = parser.parse_args()
    model, report = train(prepare_frame(args.data))
    model_path, report_path = Path(args.model), Path(args.report)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
