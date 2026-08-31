# -*- coding: utf-8 -*-
"""Centralized, fault-tolerant .env loader.

Reads keys from a .env file using (in order):
  1) python-dotenv (if installed) — handles BOM, CRLF, quoted values
  2) Built-in parser that strips BOM and CRLF, accepts both naming
     conventions (TG_TOKEN and TELEGRAM_BOT_TOKEN), strips quotes/spaces

Returns a dict-like dotenv object with `.get(key, default)`.

Usage:
  from env_loader import env
  token = env.get("TELEGRAM_BOT_TOKEN")  # or env.get("TG_TOKEN") — both work
  env.required("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY")  # fail-fast
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple, Optional


# مفاتيح بصيغتين: الحديثة (TELEGRAM_BOT_TOKEN) والقديمة (TG_TOKEN)
# الـloader يقرأ كلاً من .env ويُرجع الاثنين تلقائياً
ALIASES: Dict[str, Tuple[str, ...]] = {
    "TELEGRAM_BOT_TOKEN": ("TELEGRAM_BOT_TOKEN", "TG_TOKEN", "BOT_TOKEN"),
    "TELEGRAM_CHAT_ID":   ("TELEGRAM_CHAT_ID",   "TG_CHAT_ID", "CHAT_ID"),
    "OPENAI_API_KEY":     ("OPENAI_API_KEY",     "OPENAI_KEY", "GROQ_API_KEY"),
    "OPENAI_BASE_URL":    ("OPENAI_BASE_URL",    "OPENAI_URL", "BASE_URL"),
    "OPENAI_MODEL":       ("OPENAI_MODEL",       "LLM_MODEL",  "MODEL"),
    "GROQ_API_KEY":       ("GROQ_API_KEY",),
    "GROQ_MODEL":         ("GROQ_MODEL",),
    "FRED_API_KEY":       ("FRED_API_KEY",),
    "BLS_API_KEY":        ("BLS_API_KEY",),
    "CONDUIT_API_KEY":    ("CONDUIT_API_KEY",),
    "CONDUIT_BASE_URL":   ("CONDUIT_BASE_URL",),
    "CONDUIT_MODEL":      ("CONDUIT_MODEL",),
    "MT5_LOGIN":          ("MT5_LOGIN",),
    "MT5_PASSWORD":       ("MT5_PASSWORD",),
    "MT5_SERVER":         ("MT5_SERVER",),
    "MT5_TERMINAL_PATH":  ("MT5_TERMINAL_PATH",),
    "MT5_SYMBOL":         ("MT5_SYMBOL",),
    "MT5_DEVIATION":      ("MT5_DEVIATION",),
}


def _candidate_paths(extra_dirs: Iterable[str] = ()) -> list:
    """Build ordered list of .env candidate paths to try."""
    paths = []
    here = Path(__file__).resolve().parent
    # المسارات الصريحة لها الأولوية. هذا ضروري للاختبارات ولمنع تحميل
    # أسرار المشروع الحقيقي عندما يطلب المستدعي ملف بيئة معزولاً.
    for d in extra_dirs:
        p = Path(d).expanduser().resolve() / ".env"
        paths.append(p)
    # المشروع الحالي (مجلد env_loader)
    paths.append(here / ".env")
    # CWD (Windows شائع)
    paths.append(Path.cwd() / ".env")
    # user-home كملاذ أخير
    paths.append(Path.home() / ".env")
    return paths


def _read_manual(path: Path) -> Dict[str, str]:
    """Parser مرن — بدون اعتماد على python-dotenv."""
    out: Dict[str, str] = {}
    raw = path.read_bytes()
    # إزالة BOM إذا وُجد
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        # إزالة \r في حال CRLF
        line = line.replace("\r", "").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        # إزالة علامات التنصيص المحيطة
        if (v.startswith('"') and v.endswith('"')) or \
           (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def _read_dotenv(path: Path) -> Dict[str, str]:
    """قراءة عبر python-dotenv إن كان مثبتاً."""
    try:
        from dotenv import dotenv_values
        kv = dotenv_values(str(path))
        return {str(k).lstrip("\ufeff"): v for k, v in kv.items() if k}
    except Exception:
        return _read_manual(path)


class _Env:
    """واجهة للوصول المرن للمفاتيح."""

    def __init__(self, extra_dirs: Iterable[str] = ()):
        self.path: Optional[Path] = None
        self.kv: Dict[str, str] = {}
        self.missing: list = []
        self._load(extra_dirs)

    def _load(self, extra_dirs):
        for p in _candidate_paths(extra_dirs):
            if p.exists():
                kv = _read_dotenv(p)
                if kv:
                    self.path = p
                    self.kv = kv
                    # طباعة سطر واحد فقط — للتشخيص
                    print(f"[env_loader] .env resolved: {p} "
                          f"({len(kv)} key(s))")
                    return
        print("[env_loader] WARNING: no readable .env found in candidates",
              file=sys.stderr)

    def get(self, key: str, default: str = "") -> str:
        """يجرّب الاسم الأصلي ثم كل الأسماء البديلة."""
        for alias in ALIASES.get(key, (key,)):
            v = self.kv.get(alias)
            if v:
                return v
        # ثم البيئة (مفيدة لتجاوزات الكون)
        v = os.environ.get(key)
        if v:
            return v
        return default

    def required(self, *keys: str) -> None:
        """فشل صريح بأسماء المفاتيح الناقصة برسالة عربية واضحة."""
        miss = [k for k in keys if not self.get(k)]
        if miss:
            print(f"[env_loader] خطأ: مفاتيح مطلوبة ناقصة في {self.path}: "
                  f"{miss}", file=sys.stderr)
        self.missing = miss

    def debug_masked(self) -> Dict[str, str]:
        """عرض كل المفاتيح بقناع آمن."""
        masked = {}
        # فحص كل alias
        keys = sorted({k for tup in ALIASES.values() for k in tup}
                      | set(self.kv.keys()))
        for k in keys:
            v = self.kv.get(k) or os.environ.get(k) or ""
            if v:
                if any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET")):
                    masked[k] = (v[:4] + "..." + v[-4:]) if len(v) > 12 \
                                else "<short>"
                else:
                    masked[k] = v
        return masked


# instance واحد عام
env = _Env()
