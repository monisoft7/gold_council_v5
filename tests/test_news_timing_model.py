import pandas as pd

import news_timing_model as ntm


def test_prepare_frame_removes_bad_dates_and_duplicates(tmp_path):
    path = tmp_path / "labels.csv"
    pd.DataFrame([
        {"Dates": "01-01-2019", "News": "gold may rise", "Future Information": 1},
        {"Dates": "01-01-2019", "News": "gold may rise", "Future Information": 1},
        {"Dates": "01-01-0201", "News": "bad date", "Future Information": 0},
    ]).to_csv(path, index=False)
    frame = ntm.prepare_frame(path)
    assert frame["text"].tolist() == ["gold may rise"]
    assert frame["target_future"].tolist() == [1]
