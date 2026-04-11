#!/usr/bin/env python3
"""Run real strategy factory acceptance cycles and verify submit-stage entry."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from akshare_mcp.env_loader import load_mcp_env
from akshare_mcp.storage import close_db, drain_cleanup_callbacks, get_db
from akshare_mcp.tools.managers.strategy_mgr_lifecycle import (
    handle_factory_run_detail,
    handle_factory_run_once,
)

async def _load_persisted_run_detail(
    db,
    run_id: str,
    *,
    retries: int = 8,
    delay_seconds: float = 0.5,
) -> dict[str, Any]:
    for attempt in range(max(1, retries)):
        detail_resp = await handle_factory_run_detail(db, {"run_id": run_id})
        detail_payload = dict(detail_resp.get("data") or {})
        if detail_payload:
            return detail_payload
        if attempt + 1 < max(1, retries):
            await asyncio.sleep(delay_seconds)
    return {}


async def _run_acceptance(runs: int, recent_limit: int) -> dict[str, Any]:
    load_mcp_env(override=False)
    db = get_db()
    run_results: list[dict[str, Any]] = []
    try:
        for index in range(1, runs + 1):
            run_resp = await handle_factory_run_once(db, {})
            run_payload = dict(run_resp.get("data") or {})
            run_id = str(run_payload.get("run_id") or run_payload.get("id") or "").strip()
            latest = await _load_persisted_run_detail(
                db,
                run_id,
                retries=max(1, int(recent_limit)),
            )
            latest_summary = dict(latest.get("summary") or {})
            latest_stages = dict(latest.get("stages") or {})
            submit_stage = dict(latest_stages.get("submit") or {})
            submit_stage_status = str(
                submit_stage.get("status")
                or latest.get("submit_stage_status")
                or ""
            ).strip()
            submitted = int(
                latest.get("submitted")
                or latest_summary.get("submitted")
                or dict(run_payload.get("summary") or {}).get("submitted")
                or 0
            )
            submit_stage_entered = bool(submit_stage) or bool(latest.get("submit_stage_entered")) or submitted > 0
            summary = {
                "index": index,
                "run_id": run_id or str(latest.get("run_id") or "").strip(),
                "status": str(latest.get("status") or run_payload.get("status") or "").strip(),
                "readiness_decision": str(
                    latest.get("readiness_decision")
                    or latest_summary.get("factory_readiness_decision")
                    or dict(run_payload.get("summary") or {}).get("factory_readiness_decision")
                    or ""
                ).strip(),
                "readiness_score": latest.get("readiness_score")
                or latest_summary.get("factory_readiness_score")
                or dict(run_payload.get("summary") or {}).get("factory_readiness_score"),
                "submit_stage_entered": submit_stage_entered,
                "submit_stage_status": submit_stage_status or None,
                "submitted": submitted,
                "blocking_reason_codes": list(
                    latest.get("blocking_reason_codes")
                    or latest_summary.get("factory_readiness_blocking_reason_codes")
                    or []
                ),
                "warning_reason_codes": list(
                    latest.get("warning_reason_codes")
                    or latest_summary.get("factory_readiness_warning_reason_codes")
                    or []
                ),
                "failed_stages": [
                    stage_name
                    for stage_name, stage_payload in latest_stages.items()
                    if str(dict(stage_payload or {}).get("status") or "").strip() == "failed"
                ],
                "partial_stages": [
                    stage_name
                    for stage_name, stage_payload in latest_stages.items()
                    if str(dict(stage_payload or {}).get("status") or "").strip() == "partial"
                ],
            }
            summary["accepted"] = bool(
                summary["readiness_decision"] == "proceed"
                and summary["submit_stage_entered"]
                and summary["submit_stage_status"] == "completed"
                and summary["submitted"] > 0
            )
            run_results.append(summary)
        accepted_count = sum(1 for item in run_results if bool(item.get("accepted")))
        return {
            "runs": run_results,
            "acceptance": {
                "expected_runs": runs,
                "accepted_runs": accepted_count,
                "all_passed": accepted_count == runs,
                "criteria": {
                    "readiness_decision": "proceed",
                    "submit_stage_entered": True,
                    "submit_stage_status": "completed",
                    "submitted_gt": 0,
                },
            },
        }
    finally:
        await close_db()
        await drain_cleanup_callbacks()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real factory_run_once cycles and verify submit-stage acceptance."
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of real runs to execute.")
    parser.add_argument(
        "--recent-limit",
        type=int,
        default=10,
        help="How many persisted-detail lookup attempts to make after each execution.",
    )
    args = parser.parse_args()

    payload = asyncio.run(
        _run_acceptance(
            runs=max(1, int(args.runs)),
            recent_limit=max(1, int(args.recent_limit)),
        )
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["acceptance"]["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
