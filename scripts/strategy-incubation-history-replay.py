#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _has_sample_gap(payload: dict[str, Any]) -> bool:
    if bool(payload.get("has_sample_gap")):
        return True
    if "sample_gap" in _strings(payload.get("gap_categories")):
        return True
    for detail in _as_list(payload.get("blocker_details")):
        if isinstance(detail, dict) and str(detail.get("category") or "").strip() == "sample_gap":
            return True
    return False


def _load_strategy_ids_from_acceptance_report(report_path: Path, *, sample_gap_only: bool = False) -> list[str]:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    strategy_ids: list[str] = []
    seen: set[str] = set()
    for item in _as_list(report.get("strategy_results")):
        if not isinstance(item, dict):
            continue
        strategy_id = str(item.get("strategy_id") or "").strip()
        if not strategy_id or strategy_id in seen:
            continue
        if sample_gap_only and not _has_sample_gap(item):
            continue
        seen.add(strategy_id)
        strategy_ids.append(strategy_id)
    return strategy_ids


def _summarize_acceptance(payload: dict[str, Any]) -> dict[str, Any]:
    acceptance_matrix = dict(payload.get("acceptance_matrix") or {})
    trade_audit_summary = dict(payload.get("trade_audit_summary") or {})
    blockers = _strings(payload.get("blockers"))
    gap_categories = _strings(payload.get("gap_categories"))
    gate_status = (
        str(payload.get("execution_audit_gate_status") or "").strip()
        or str(trade_audit_summary.get("execution_audit_gate_status") or "").strip()
        or None
    )
    overall_ready = bool(acceptance_matrix.get("overall_ready")) if "overall_ready" in acceptance_matrix else str(payload.get("status") or "") == "ready"
    return {
        "overall_ready": overall_ready,
        "has_sample_gap": _has_sample_gap({**payload, "gap_categories": gap_categories}),
        "execution_audit_gate_status": gate_status,
        "realized_trade_count": int(trade_audit_summary.get("realized_trade_count") or 0),
        "blockers": blockers,
        "gap_categories": gap_categories,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select strategy ids from an execution audit acceptance report.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--sample-gap-only", action="store_true")
    args = parser.parse_args(argv)
    strategy_ids = _load_strategy_ids_from_acceptance_report(args.report, sample_gap_only=args.sample_gap_only)
    print(json.dumps({"strategy_ids": strategy_ids}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
