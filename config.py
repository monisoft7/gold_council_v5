# -*- coding: utf-8 -*-
"""
إدارة المفاتيح والإعدادات — تقرأ من ملف .env بجانب app.py أو من متغيرات البيئة.

أنشئ ملفاً اسمه .env في مجلد المشروع وضع فيه مفاتيحك بهذا الشكل:

    TELEGRAM_BOT_TOKEN=1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxx
    TELEGRAM_CHAT_ID=123456789
    OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
    OPENAI_BASE_URL=https://api.deepseek.com/v1     (اختياري — للنماذج المتوافقة مع OpenAI)
    OPENAI_MODEL=deepseek-chat                       (اختياري)
"""
import os

ENV_KEYS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
            "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL",
            "GROQ_API_KEY", "GROQ_MODEL"]
ENV_KEYS += ["FRED_API_KEY", "BLS_API_KEY"]
ENV_KEYS += ["CONDUIT_API_KEY", "CONDUIT_BASE_URL", "CONDUIT_MODEL"]


def load_env(path=None):
    """يقرأ ملف .env إن وُجد ويضع قيمه في متغيرات البيئة (بدون الكتابة فوق الموجود)."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get(key, default=""):
    return os.environ.get(key, default).strip()
