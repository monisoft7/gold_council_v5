# -*- coding: utf-8 -*-
"""بوابة اتجاه منهجية مستقلة: شراء تدريجي أو سيولة، بلا بيع."""
from __future__ import annotations

import numpy as np
import pandas as pd

from agents import AgentReport


HORIZONS = (20, 60, 120, 252)


def systematic_regime_agent(history: pd.DataFrame) -> AgentReport:
    close = pd.to_numeric(history.get("close"), errors="coerce").dropna()
    if len(close) <= max(HORIZONS):
        return AgentReport(
            key="systematic_gate", name="بوابة الاتجاه المنهجي", icon="🧭",
            role="تحدد شراء/سيولة من زخم متعدد الآفاق؛ لا تصوت بالاتجاه",
            score=0, confidence=20, verdict="بيانات غير كافية",
            summary=f"يلزم {max(HORIZONS)+1} إغلاقاً؛ المتاح {len(close)}",
            bullets=[], weight=0.0,
            flags={"block_long": True, "block_short": True,
                   "risk_multiplier": 0.0, "systematic_available": False})
    votes, bullets = [], []
    for horizon in HORIZONS:
        move = float(close.iloc[-1] / close.iloc[-1-horizon] - 1)
        vote = float(np.sign(move))
        votes.append(vote)
        bullets.append(f"{horizon} جلسة: {move:+.2%} ({'صاعد' if vote > 0 else 'هابط' if vote < 0 else 'محايد'})")
    exposure = max(0.0, float(np.mean(votes)))
    score = float(np.mean(votes) * 100)
    allowed = exposure > 0
    return AgentReport(
        key="systematic_gate", name="بوابة الاتجاه المنهجي", icon="🧭",
        role="طبقة مستقلة شراء/سيولة بزخم 20/60/120/252 جلسة",
        score=0, confidence=75, verdict=("شراء مسموح" if allowed else "سيولة"),
        summary=f"تعرض منهجي {exposure:.0%}؛ درجة النظام الخام {score:+.0f}",
        bullets=bullets, weight=0.0,
        flags={"block_long": not allowed, "block_short": True,
               "risk_multiplier": exposure, "systematic_available": True,
               "systematic_score": score})
