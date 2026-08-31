# -*- coding: utf-8 -*-
"""
وكيل جلب البيانات الخام:
- السعر الفوري للذهب (Spot XAU/USD) من gold-api.com — مجاني بدون مفتاح
- البيانات التاريخية واللحظية لعقود الذهب (GC=F) من Yahoo Finance
- الأخبار العالمية من Google News RSS بعدة لغات واستعلامات متخصصة
"""
import time
from datetime import datetime, timezone

import requests
import pandas as pd
import feedparser

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
}

# ---------------------------------------------------------------- أسعار الذهب
def get_spot_price():
    """السعر الفوري لأونصة الذهب (تحديث كل ثوانٍ تقريباً)."""
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=12)
        d = r.json()
        return {
            "price": float(d["price"]),
            "updated": d.get("updatedAtReadable", ""),
            "source": "gold-api.com — Spot XAU/USD",
        }
    except Exception as e:
        return {"price": None, "updated": "", "source": f"تعذر الجلب: {e}"}


def get_ohlc(range_="6mo", interval="1d"):
    """شموع عقود الذهب الآجلة GC=F من Yahoo Finance."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
           f"?interval={interval}&range={range_}")
    r = requests.get(url, headers=UA, timeout=20)
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "time": pd.to_datetime(res["timestamp"], unit="s"),
        "open": q["open"], "high": q["high"],
        "low": q["low"], "close": q["close"],
        "volume": q.get("volume"),
    }).dropna(subset=["close"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------- الأخبار
NEWS_QUERIES = {
    "أسعار الذهب":        ("gold price", "en-US", "US", "en"),
    "تداول XAU/USD":      ("XAUUSD gold trading", "en-US", "US", "en"),
    "الفيدرالي والفائدة": ("Federal Reserve interest rate decision", "en-US", "US", "en"),
    "التضخم الأمريكي":    ("US inflation CPI economy", "en-US", "US", "en"),
    "جيوسياسية وحروب":    ("geopolitics war escalation markets", "en-US", "US", "en"),
    "البنوك المركزية":    ("central banks gold buying reserves", "en-US", "US", "en"),
    "الدولار والسندات":   ("US dollar treasury yields", "en-US", "US", "en"),
    "أخبار عربية":        ("سعر الذهب", "ar", "EG", "ar"),
}


def get_news(per_feed=12):
    """يجمع الأخبار من كل الاستعلامات، يزيل التكرار، ويرتب بالأحدث."""
    items, seen = [], set()
    for section, (q, hl, gl, ceid) in NEWS_QUERIES.items():
        url = (f"https://news.google.com/rss/search?q={requests.utils.quote(q)}"
               f"&hl={hl}&gl={gl}&ceid={ceid}:{'ar' if hl == 'ar' else 'en'}")
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for e in feed.entries[:per_feed]:
            title = e.get("title", "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            pub = None
            if e.get("published_parsed"):
                pub = datetime.fromtimestamp(
                    time.mktime(e.published_parsed), tz=timezone.utc)
            items.append({
                "section": section,
                "title": title,
                "source": (e.get("source") or {}).get("title", ""),
                "link": e.get("link", ""),
                "published": pub,
            })
    items.sort(key=lambda x: x["published"] or datetime(1970, 1, 1, tzinfo=timezone.utc),
               reverse=True)
    return items


# ------------------------------------------------------------- ساعة لحظية
def get_intraday(range_="1d", interval="60m"):
    """شموع لحظية بفواصل ساعة لآخر يوم."""
    try:
        return get_ohlc(range_=range_, interval=interval)
    except Exception as e:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])


def _change_pct(spot, daily):
    if not daily.empty and spot and spot["price"]:
        try:
            prev = float(daily.iloc[-1]["close"])
            return (spot["price"] - prev) / prev * 100
        except Exception:
            return 0.0
    return 0.0


# ------------------------------------------------------------- المُجمِّع
def collect_all():
    """الجلب الموحَّد الذي يستدعيه app_v2.

    يعيد (spot, daily, intraday, news) مع تقصير آمن في حال فشل أحد المصادر
    بدلاً من إرجاع AttributeError.
    """
    try:
        spot = get_spot_price()
    except Exception:
        spot = {"price": None, "updated": "", "source": ""}
    try:
        # بوابة الاتجاه المنهجية تحتاج 252 جلسة مكتملة؛ سنتان توفران هامشاً
        # للعطل والإجازات من دون أي تكلفة API إضافية جوهرية.
        daily = get_ohlc(range_="2y", interval="1d")
    except Exception:
        daily = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    try:
        intraday = get_intraday(range_="5d", interval="60m")
    except Exception:
        intraday = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    try:
        news = get_news(per_feed=12)
    except Exception:
        news = []
    spot["change_pct"] = _change_pct(spot, daily)
    return spot, daily, intraday, news
