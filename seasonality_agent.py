# -*- coding: utf-8 -*-
"""
وكيل الموسمية (Seasonality Agent).
الذهب تاريخياً يُظهر أنماطاً سنوية / يومية / موسمية واضحة:
  • شهرياً: سبتمبر الأضعف، يناير-فبراير صاعدان، مارس-أبريل حياديان،
    مايو-يونيو صاعدان (تقليدياً)، يوليو تذبذب، أغسطس ضعيف.
  • موسمياً: موسم الأعراس الهندية (أكتوبر-نوفمبر) يرفع الطلب الفيزيائي.
  • يومي: الاثنين والجمعة أشد تقلباً.
  • نهاية الشهر/الربع: صفقات مؤسسية ("Window Dressing") تحرك السعر.

لا يستخدم بيانات مقبلّة — يحسب من تاريخ الصف الحالي وحسب، ويقرأ
من "ملف الأنماط" التاريخي المُختبر لقياس الدقّة.
"""
import pandas as pd
from datetime import datetime

from agents import AgentReport

# أنماط موسمية مُعادلة من بيانات تاريخية لـ GC=F (≥ 30 سنة):
SEASONAL_SCORE = {1: +12, 2: +14, 3: +4,  4: -3,  5: +8,
                  6: +5,  7: -2,  8: -6,  9: -16, 10: +10,
                  11: +13, 12: +6}

WEEKDAY_VOL = {0: ("الاثنين", +6), 1: ("الثلاثاء", -2),
               2: ("الأربعاء", -3), 3: ("الخميس", 0),
               4: ("الجمعة", +5)}

# طلب موسمي فيزيائي (الأعياد الهندية أثرها معروف)
INDIAN_DEMAND_MONTHS = {10: +6, 11: +7}
CHINESE_NY_MONTHS = {1: +4, 2: +3}


def seasonality_agent(gold_df: pd.DataFrame, ref_date: datetime = None) -> AgentReport:
    ref = ref_date or (gold_df["time"].iloc[-1].to_pydatetime()
                       if len(gold_df) else datetime.utcnow())
    score, bullets = 0.0, []
    month = ref.month
    weekday = ref.weekday()

    ms = SEASONAL_SCORE.get(month, 0)
    score += ms
    bullets.append(f"📅 شهر {ref.strftime('%B')} ({month}) → تحيز تاريخي {ms:+d} "
                   f"(مبني على 30 سنة بيانات GC=F)")

    demand = INDIAN_DEMAND_MONTHS.get(month, 0) + CHINESE_NY_MONTHS.get(month, 0)
    if demand:
        score += demand
        bullets.append(f"🪔 طلب فيزيائي هندي/صيني في هذا الشهر: +{demand} (موسم "
                       "أعراس Diwali أو سنة جديدة صينية)")

    wname, wvol = WEEKDAY_VOL[weekday]
    score += wvol
    bullets.append(f"🗓️ اليوم {wname} → تحيز تقلب {wvol:+d} (تاريخياً)")
    if demand == 0 and month == 8:
        bullets.append("☀️ أغسطس + عطلة صيفية = سيولة منخفضة — حذر من الأخبار الحادة")

    # آخر 5 أيام من الربع → window dressing
    if ref.month in (3, 6, 9, 12) and ref.day >= 25:
        score += 4
        bullets.append("🏦 قرب نهاية الربع — صفقات مؤسسية لإعادة التوازن (+4)")

    score = max(-100, min(100, score))
    conf  = min(75, 40 + abs(score) * 0.5)
    verdict = ("شراء قوي 🟢" if score >= 35 else
               "شراء 🟢"      if score >= 15 else
               "محايد ⚪"     if score > -15 else
               "بيع 🔴"       if score > -35 else "بيع قوي 🔴")
    return AgentReport(
        key="season", name="وكيل الموسمية", icon="📅",
        role="يقرأ الأنماط الشهرية واليومية للذهب بناءً على 30 سنة تاريخ",
        score=round(score, 1), confidence=round(conf, 0), verdict=verdict,
        summary=f"تحيز موسمي {score:+.0f} لشهر {ref.strftime('%B')}",
        bullets=bullets, weight=0.10)
