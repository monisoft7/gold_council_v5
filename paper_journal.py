# -*- coding: utf-8 -*-
"""سجل append-only لكل اجتماع ورقي، بما في ذلك قرارات الانتظار."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


DEFAULT_PATH = Path(__file__).resolve().parent / "data_cache" / "paper_trading_journal.jsonl"


def build_record(result: dict) -> dict:
    decision = result["dec"]
    reports = result.get("reports") or []
    news = result.get("news") or []
    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "decision_at": decision.get("decision_at"),
        "last_price": result.get("last_price"),
        "signal": decision.get("signal", 0),
        "decision": decision.get("decision"),
        "final_score": decision.get("final_score"),
        "confidence": decision.get("confidence"),
        "agreement": decision.get("agreement"),
        "quality_passed": decision.get("quality_passed", False),
        "vetoed": decision.get("vetoed"),
        "risk_multiplier": decision.get("risk_multiplier"),
        "exposure_pct": decision.get("exposure_pct"),
        "base_position_oz": decision.get("base_position_oz"),
        "position_oz": decision.get("position_oz"),
        "risk_budget_usd": decision.get("risk_budget_usd"),
        "levels": decision.get("levels"),
        "supporting_families": decision.get("supporting_families", []),
        "research_only": decision.get("research_only", True),
        "pipeline_warnings": decision.get("pipeline_warnings", []),
        "agents": [
            {
                "key": report.key,
                "score": report.score,
                "confidence": report.confidence,
                "verdict": report.verdict,
                "flags": report.flags,
            }
            for report in reports
        ],
        "headlines": [
            {"title": item.get("title"), "source": item.get("source")}
            for item in news[:10]
        ],
    }


def append_record(result: dict, path: str | Path = DEFAULT_PATH) -> dict:
    """يضيف سجلاً واحداً دون تعديل السجلات السابقة."""
    record = build_record(result)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()
    return record
