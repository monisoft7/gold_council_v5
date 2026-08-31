# -*- coding: utf-8 -*-
"""اختبارات env_loader — بدون شبكة."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from env_loader import _Env


def test_bom_crlf_quoted_and_aliases(tmp_path):
    p = tmp_path / ".env"
    # BOM + CRLF + قيمة مُقتبَسة + اسم قديم TG_TOKEN
    p.write_bytes(
        b'\xef\xbb\xbfTG_TOKEN=123456:ABC-DEF\r\n'
        b'TG_CHAT_ID="-1009876543210"\r\n'
        b'OPENAI_API_KEY=gsk_test_key\r\n'
    )
    e = _Env(extra_dirs=[str(tmp_path)])
    assert e.get("TELEGRAM_BOT_TOKEN") == "123456:ABC-DEF"
    assert e.get("TELEGRAM_CHAT_ID") == "-1009876543210"
    assert e.get("OPENAI_API_KEY") == "gsk_test_key"
    # الأسماء القديمة أيضاً
    assert e.get("TG_TOKEN") == "123456:ABC-DEF"


def test_required_and_masked(tmp_path):
    p = tmp_path / ".env"
    p.write_text("TG_TOKEN=abcdef1234567890\n", encoding="utf-8")
    e = _Env(extra_dirs=[str(tmp_path)])
    e.required("TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY")
    assert e.missing == ["OPENAI_API_KEY"]
    masked = e.debug_masked()
    assert masked["TG_TOKEN"].startswith("abcd")
    assert "1234567890" not in masked["TG_TOKEN"]
