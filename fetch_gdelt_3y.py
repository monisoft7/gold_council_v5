# -*- coding: utf-8 -*-
"""يجلب أرشيف أخبار الذهب من GDELT DOC 2.0 API (format=csv) لثلاث سنوات.
يغطي 2023-09-01 → 2026-08-29 بنوافذ أسبوعية ويحوّلها لصيغة المشروع:
time,title,source,section
"""
import csv, io, time, sys
import requests
from datetime import datetime, timedelta

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

# استعلامات مستهدفة بالإنجليزية (الأدق في GDELT للأخبار المالية)
QUERIES = [
    ("gold price", "أسعار الذهب"),
    ("XAUUSD OR \"gold futures\"", "تداول XAU/USD"),
    ("Federal Reserve interest rate", "الفيدرالي والفائدة"),
    ("US inflation CPI", "التضخم الأمريكي"),
    ("gold central banks buying", "البنوك المركزية"),
    ("gold safe haven war", "جيوسياسية"),
    ("gold mining OR bullion", "سوق السبائك"),
]

def fetch_window(query, section, start, end, retries=2):
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": 250,
        "format": "csv",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }
    for attempt in range(retries + 1):
        try:
            r = requests.get(BASE, params=params, headers=UA, timeout=90)
            if r.status_code != 200 or not r.text.strip():
                time.sleep(3 * (attempt + 1)); continue
            txt = r.text.lstrip("\ufeff")
            rows = list(csv.DictReader(io.StringIO(txt)))
            out = []
            for row in rows:
                title = (row.get("Title") or "").strip()
                url = (row.get("URL") or "").strip()
                date_s = (row.get("Date") or "").strip()
                if not title or not date_s:
                    continue
                try:
                    pub = datetime.strptime(date_s, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        pub = datetime.strptime(date_s[:10], "%Y-%m-%d")
                    except ValueError:
                        continue
                # المصدر من دومين الرابط
                try:
                    from urllib.parse import urlparse
                    src = urlparse(url).netloc.replace("www.", "") or "GDELT"
                except Exception:
                    src = "GDELT"
                out.append({"time": pub.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                            "title": title, "source": src, "section": section})
            return out
        except Exception as e:
            print(f"  retry {attempt+1} {query[:20]} {start.date()}: {e}", file=sys.stderr)
            time.sleep(4 * (attempt + 1))
    return []


def main():
    import os
    OUT = "/home/user/gold_council_v5/gold_news_gdelt_3y.csv" if os.path.isdir("/home/user/gold_council_v5") else "gold_news_gdelt_3y.csv"
    start_all = datetime(2023, 9, 1)
    end_all = datetime(2026, 8, 29)
    step = timedelta(days=14)   # نافذة أسبوعين — طلبات أقل، خنق أقل
    all_items, seen = [], set()
    # استئناف: لو الملف موجود نكمل من آخر تاريخ فيه
    resume_from = start_all
    if os.path.exists(OUT):
        try:
            old = csv.DictReader(open(OUT, encoding="utf-8"))
            for row in old:
                k = (row["title"].lower(), row["time"][:10])
                if k not in seen:
                    seen.add(k); all_items.append(row)
                if row["time"][:10] > resume_from.strftime("%Y-%m-%d"):
                    pass
            print(f"استئناف: {len(all_items)} خبر موجود مسبقاً")
        except Exception:
            pass
    cur = start_all
    win = 0
    while cur < end_all:
        nxt = min(cur + step, end_all)
        win += 1
        for q, sec in QUERIES:
            items = fetch_window(q, sec, cur, nxt)
            for it in items:
                k = (it["title"].lower(), it["time"][:10])
                if k not in seen:
                    seen.add(k); all_items.append(it)
        # حفظ تدريجي كل نافذة — لا تفقد شيئاً لو انقطع
        if win % 5 == 0:
            all_items.sort(key=lambda x: x["time"], reverse=True)
            with open(OUT, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["time", "title", "source", "section"])
                w.writeheader(); w.writerows(all_items)
            print(f"[{win}] {cur.date()} → محفوظ {len(all_items)}", flush=True)
        cur = nxt
        time.sleep(2.0)  # احترام خنق GDELT
    all_items.sort(key=lambda x: x["time"], reverse=True)
    out = OUT
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["time", "title", "source", "section"])
        w.writeheader(); w.writerows(all_items)
    print(f"DONE rows={len(all_items)} → {out}")

if __name__ == "__main__":
    main()
