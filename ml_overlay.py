# -*- coding: utf-8 -*-
"""بوابة التعلم العميق فوق المجلس — الفجوة: ربط model.pkl بالقرار اللحظي.

الفكرة: المجلس يخرج توصية، والبوابة تجيب: "ما احتمال نجاحها تاريخياً؟"
إذا كان الاحتمال دون العتبة → يُخفَّض القرار إلى محايد بدلاً من إلغائه،
فتبقى السلطة النهائية للمجلس لكن بفلتر إحصائي مُعايَر.
"""
import os
from typing import Optional

import joblib


class MLGate:
    def __init__(self, model_path: str = "model.pkl", threshold: float = 0.55):
        self.threshold = threshold
        self.model = None
        self.cols = []
        self.model_path = model_path
        if os.path.exists(model_path):
            try:
                d = joblib.load(model_path)
                self.model = d["model"]
                self.cols = list(d.get("feat_cols", []))
            except Exception:
                self.model = None
                self.cols = []

    def available(self) -> bool:
        return self.model is not None and len(self.cols) > 0

    def probability(self, features: dict) -> Optional[float]:
        """احتمال الفوز المُعايَر (0..1) أو None إذا لم يوجد نموذج."""
        if not self.available():
            return None
        row = [[float(features.get(c, 0.0)) for c in self.cols]]
        try:
            return float(self.model.predict_proba(row)[0][1])
        except Exception:
            try:
                return float(self.model.predict(row)[0])
            except Exception:
                return None

    def gate(self, features: dict, council_decision: str) -> dict:
        """يقرر: هل نمرّر توصية المجلس كما هي أم نخفضها؟"""
        p = self.probability(features)
        if p is None:
            return {"prob_win": None, "passed": True, "adjusted": council_decision,
                    "note": "لا يوجد model.pkl — القرار بيد المجلس وحده"}
        strong = ("قوي" in council_decision)
        if p >= self.threshold:
            return {"prob_win": round(p, 3), "passed": True,
                    "adjusted": council_decision,
                    "note": f"النموذج يؤيد (احتمال {p:.0%})"}
        adjusted = "محايد" if strong else council_decision
        if "شراء" in council_decision or "بيع" in council_decision:
            adjusted = "محايد"
        return {"prob_win": round(p, 3), "passed": False,
                "adjusted": adjusted,
                "note": f"⚠ النموذج متشكك (احتمال {p:.0%} < {self.threshold:.0%}) — خُفِّضت التوصية"}
