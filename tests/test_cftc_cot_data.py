import io
import zipfile

import pandas as pd

from cftc_cot_data import parse_archive


def _archive(csv_text):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("annual.txt", csv_text)
    return out.getvalue()


def test_cot_release_is_friday_not_report_tuesday():
    text = ("Market and Exchange Names,Report Date as YYYY-MM-DD,Open Interest (All),"
            "Noncommercial Positions-Long (All),Noncommercial Positions-Short (All),"
            "Commercial Positions-Long (All),Commercial Positions-Short (All)\n"
            "\"GOLD - COMMODITY EXCHANGE INC.\",2026-01-06,500000,200000,100000,90000,180000\n")
    out = parse_archive(_archive(text))
    assert out.iloc[0]["noncommercial_net"] == 100000
    assert (out.iloc[0]["available_at"] - out.iloc[0]["observed_at"]).days == 3
