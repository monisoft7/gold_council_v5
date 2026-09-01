# -*- coding: utf-8 -*-
"""وكيل تجريبي لنموذج Chronos-Bolt الجاهز؛ لا يصوت قبل تحقق OOS.

التبعيات ثقيلة واختيارية، لذلك تُحمّل عند الاستدعاء فقط. يمكن حقن pipeline
في الاختبارات أو تشغيل النموذج المحلي بعد تثبيت requirements-ml.txt.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from agents import AgentReport


DEFAULT_MODEL = "amazon/chronos-bolt-tiny"


def _array(value):
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value, dtype=float)


def _unavailable(reason):
    return AgentReport(
        key="foundation_forecast", name="وكيل Chronos التأسيسي", icon="🧬",
        role="تنبؤ احتمالي زمني جاهز، معزول عن التصويت حتى نجاح اختبار مستقل",
        score=0, confidence=0, verdict="غير متاح",
        summary=reason, bullets=[reason], weight=0.0,
        flags={"experimental": True, "vote_eligible": False,
               "model": DEFAULT_MODEL, "available": False},
    )


def chronos_foundation_agent(history: pd.DataFrame, *, pipeline=None,
                             model_id=DEFAULT_MODEL, horizon=5):
    close = pd.to_numeric(history.get("close"), errors="coerce").dropna()
    if len(close) < 64:
        return _unavailable(f"يلزم 64 إغلاقاً على الأقل؛ المتاح {len(close)}")
    try:
        if pipeline is None:
            from chronos import BaseChronosPipeline
            pipeline = BaseChronosPipeline.from_pretrained(
                model_id, device_map="cpu"
            )
        values = close.tail(512).to_numpy(dtype=np.float32)
        try:
            import torch
            model_inputs = [torch.tensor(values, dtype=torch.float32)]
        except (ImportError, ModuleNotFoundError):
            # يسمح بحقن pipeline خفيف في الاختبارات دون تثبيت PyTorch.
            model_inputs = [values]
        quantiles, median = pipeline.predict_quantiles(
            model_inputs,
            prediction_length=int(horizon),
            quantile_levels=[0.1, 0.5, 0.9],
        )
        q = _array(quantiles)
        m = _array(median)
        # Chronos-Bolt: quantiles=(batch,horizon,3), median=(batch,horizon).
        q10, q50, q90 = (float(q[0, -1, i]) for i in range(3))
        median_end = float(m[0, -1]) if m.size else q50
        last = float(close.iloc[-1])
        expected_return = median_end / last - 1.0
        interval_return = max((q90 - q10) / last, 0.002)
        signal_to_noise = expected_return / (interval_return / 2.0)
        score = float(np.clip(100 * math.tanh(signal_to_noise), -100, 100))
        confidence = float(np.clip(100 * (1 - interval_return / 0.12), 5, 80))
        verdict = ("صاعد تجريبياً" if score > 10 else
                   "هابط تجريبياً" if score < -10 else "محايد تجريبياً")
        return AgentReport(
            key="foundation_forecast", name="وكيل Chronos التأسيسي", icon="🧬",
            role="تنبؤ احتمالي زمني جاهز، معزول عن التصويت حتى نجاح اختبار مستقل",
            score=round(score, 1), confidence=round(confidence, 0), verdict=verdict,
            summary=(f"توقع {horizon} جلسات: {expected_return:+.2%}؛ "
                     f"نطاق 10–90% بعرض {interval_return:.2%}."),
            bullets=[
                f"الوسيط المتوقع: {median_end:.2f} مقابل آخر إغلاق {last:.2f}",
                f"النطاق الاحتمالي النهائي: {q10:.2f} — {q90:.2f}",
                "تجريبي فقط: لا يملك وزناً في المجلس قبل تحقق زمني مستقل",
            ], weight=0.0,
            flags={"experimental": True, "vote_eligible": False,
                   "model": model_id, "available": True,
                   "forecast_horizon": int(horizon),
                   "expected_return": expected_return,
                   "interval_return": interval_return},
        )
    except (ImportError, ModuleNotFoundError):
        return _unavailable("Chronos غير مثبت؛ استخدم بيئة Python 3.12 وrequirements-ml.txt")
    except Exception as exc:
        return _unavailable(f"تعذر تشغيل Chronos بأمان: {type(exc).__name__}")
