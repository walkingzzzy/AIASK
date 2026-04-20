#!/usr/bin/env python3
"""Apply failed-metrics remediation and bootstrap import for execution-audit blockers."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
for relative in ("packages/akshare-mcp/src", "packages/strategy-factory/src"):
    path = ROOT_DIR / relative
    if path.exists():
        sys.path.insert(0, str(path))

from akshare_mcp.env_loader import load_mcp_env
from akshare_mcp.services.incubation import get_strategy_incubation_service
from akshare_mcp.services.strategy_acceptance_remediation import (
    get_strategy_acceptance_remediation_service,
)
from akshare_mcp.storage import get_db, run_with_db_cleanup


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def _load_strategy_ids(path: Path, blocker: str) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    strategy_ids: list[str] = []
    for row in list(payload.get("strategy_results") or []):
        blockers = {
            str(item).strip()
            for item in list(row.get("blockers") or [])
            if str(item).strip()
        }
        if blocker not in blockers:
            continue
        strategy_id = str(row.get("strategy_id") or "").strip()
        if strategy_id:
            strategy_ids.append(strategy_id)
    return list(dict.fromkeys(strategy_ids))


def _parse_affected_rows(execute_result: Any) -> int:
    token = str(execute_result or "").strip()
    if not token:
        return 0
    try:
        return int(token.split()[-1])
    except Exception:
        return 0


async def _reset_strategy_runtime_state(db, strategy_id: str) -> dict[str, Any]:
    async with db.acquire() as conn:
        account_rows = await conn.fetch(
            "SELECT id FROM paper_accounts WHERE strategy_id = $1 ORDER BY created_at",
            strategy_id,
        )
        account_ids = [
            str((row or {}).get("id") or "").strip()
            for row in list(account_rows or [])
            if str((row or {}).get("id") or "").strip()
        ]
        deleted: dict[str, int] = {}
        if account_ids:
            deleted["strategy_trade_position_fills"] = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM strategy_trade_position_fills
                    WHERE strategy_id = $1 OR account_id = ANY($2::text[])
                    """,
                    strategy_id,
                    account_ids,
                )
            )
            deleted["strategy_trade_positions"] = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM strategy_trade_positions
                    WHERE strategy_id = $1 OR account_id = ANY($2::text[])
                    """,
                    strategy_id,
                    account_ids,
                )
            )
            deleted["paper_nav"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM paper_nav WHERE account_id = ANY($1::text[])",
                    account_ids,
                )
            )
            deleted["paper_positions"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM paper_positions WHERE account_id = ANY($1::text[])",
                    account_ids,
                )
            )
            deleted["paper_trades"] = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM paper_trades
                    WHERE strategy_id = $1 OR account_id = ANY($2::text[])
                    """,
                    strategy_id,
                    account_ids,
                )
            )
            deleted["paper_orders"] = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM paper_orders
                    WHERE strategy_id = $1 OR account_id = ANY($2::text[])
                    """,
                    strategy_id,
                    account_ids,
                )
            )
            deleted["paper_accounts"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM paper_accounts WHERE id = ANY($1::text[])",
                    account_ids,
                )
            )
        deleted["strategy_incubation_metrics"] = _parse_affected_rows(
            await conn.execute(
                "DELETE FROM strategy_incubation_metrics WHERE strategy_id = $1",
                strategy_id,
            )
        )
        deleted["strategy_incubation_accounts"] = _parse_affected_rows(
            await conn.execute(
                "DELETE FROM strategy_incubation_accounts WHERE strategy_id = $1",
                strategy_id,
            )
        )
    return {"strategy_id": strategy_id, "account_ids": account_ids, "deleted": deleted}


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Strategy Acceptance Remediation",
        "",
        f"- Generated at: {_now_iso()}",
        f"- Failed-metrics remediated: {len(list(report.get('failed_metrics') or []))}",
        f"- Signal caches rebuilt: {len(list(report.get('signal_rebuilds') or []))}",
        f"- Bootstrap imported: {len(list(report.get('bootstrap_imports') or []))}",
        "",
        "## Failed Metrics",
        "",
        "| Strategy | Updated | Kept | Excluded |",
        "| --- | --- | --- | --- |",
    ]
    failed = list(report.get("failed_metrics") or [])
    if failed:
        for item in failed:
            lines.append(
                f"| {item.get('strategy_id') or '-'} | {bool(item.get('updated'))} | "
                f"{', '.join(list(item.get('kept_codes') or [])) or '-'} | "
                f"{', '.join(list(item.get('excluded_codes') or [])) or '-'} |"
            )
    else:
        lines.append("| - | - | - | - |")

    lines.extend(
        [
            "",
            "## Signal Rebuilds",
            "",
            "| Strategy | Rebuilt | Deleted Signals | Saved Signals | Signal Days |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    rebuilds = list(report.get("signal_rebuilds") or [])
    if rebuilds:
        for item in rebuilds:
            lines.append(
                f"| {item.get('strategy_id') or '-'} | {bool(item.get('rebuilt'))} | "
                f"{int(item.get('deleted_rows') or 0)} | {int(item.get('saved_rows') or 0)} | "
                f"{int(item.get('signal_days') or 0)} |"
            )
    else:
        lines.append("| - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## Bootstrap Imports",
            "",
            "| Strategy | Imported Round Trips | Bootstrap Floor | Backtest ID |",
            "| --- | --- | --- | --- |",
        ]
    )
    imports = list(report.get("bootstrap_imports") or [])
    if imports:
        for item in imports:
            lines.append(
                f"| {item.get('strategy_id') or '-'} | {int(item.get('imported_round_trips') or 0)} | "
                f"{int(item.get('bootstrap_trade_floor') or 0)} | {item.get('backtest_id') or '-'} |"
            )
    else:
        lines.append("| - | - | - | - |")

    lines.extend(
        [
            "",
            "## Acceptance",
            "",
            "| Strategy | Blockers | Gate Status | Realized Trades |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in list(report.get("acceptance") or []):
        audit = dict(item.get("trade_audit_summary") or {})
        lines.append(
            f"| {item.get('strategy_id') or '-'} | {', '.join(list(item.get('blockers') or [])) or '-'} | "
            f"{audit.get('execution_audit_gate_status') or '-'} | {int(audit.get('realized_trade_count') or 0)} |"
        )
    if not list(report.get("acceptance") or []):
        lines.append("| - | - | - | - |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _async_main(args: argparse.Namespace) -> int:
    load_mcp_env(override=False)
    db = get_db()
    incubation_service = get_strategy_incubation_service()
    remediation_service = get_strategy_acceptance_remediation_service()

    report_path = Path(args.from_acceptance_report).resolve()
    failed_metric_ids = _load_strategy_ids(report_path, "failed_metrics")
    insufficient_sample_ids = _load_strategy_ids(report_path, "insufficient_samples")

    if args.failed_strategy_ids:
        failed_metric_ids = list(dict.fromkeys(_normalize_csv(args.failed_strategy_ids)))
    if args.bootstrap_strategy_ids:
        insufficient_sample_ids = list(dict.fromkeys(_normalize_csv(args.bootstrap_strategy_ids)))

    failed_results: list[dict[str, Any]] = []
    signal_rebuild_results: list[dict[str, Any]] = []
    replay_results: list[dict[str, Any]] = []
    for strategy_id in failed_metric_ids:
        failed_result = await remediation_service.remediate_failed_metrics_strategy(db, strategy_id)
        failed_results.append(_json_safe(failed_result))
        if not failed_result.get("updated"):
            continue
        strategy = await db.get_strategy(strategy_id)
        if not strategy:
            continue
        rebuild = await remediation_service.rebuild_strategy_signal_cache(db, strategy)
        signal_rebuild_results.append(_json_safe(rebuild))
        reset = await _reset_strategy_runtime_state(db, strategy_id)
        strategy = await db.get_strategy(strategy_id)
        replay = await incubation_service.replay_strategy_history(
            db,
            strategy,
            include_market_days=True,
            force_close_open_positions=True,
            run_acceptance=True,
        )
        replay_results.append(
            {
                "strategy_id": strategy_id,
                "reset": _json_safe(reset),
                "replay": _json_safe(replay),
            }
        )

    bootstrap_results: list[dict[str, Any]] = []
    for strategy_id in insufficient_sample_ids:
        bootstrap = await remediation_service.bootstrap_import_strategy(
            db,
            strategy_id,
            replace_existing_bootstrap=True,
        )
        bootstrap_results.append(_json_safe(bootstrap))

    acceptance: list[dict[str, Any]] = []
    touched_ids = list(
        dict.fromkeys(
            [*failed_metric_ids, *insufficient_sample_ids]
        )
    )
    for strategy_id in touched_ids:
        result = await db.run_execution_audit_acceptance(strategy_id=strategy_id, backfill=True)
        acceptance.append(_json_safe(result))

    version_tag = str(args.version_tag or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    output_dir = Path(args.report_dir or (ROOT_DIR / "reports" / "acceptance-remediation")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": _now_iso(),
        "source_report": str(report_path),
        "failed_metrics": failed_results,
        "signal_rebuilds": signal_rebuild_results,
        "replays": replay_results,
        "bootstrap_imports": bootstrap_results,
        "acceptance": acceptance,
    }
    json_path = output_dir / f"strategy_acceptance_remediation_{version_tag}.json"
    md_path = output_dir / f"strategy_acceptance_remediation_{version_tag}.md"
    json_path.write_text(json.dumps(_json_safe(report), ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report, md_path)
    print(json.dumps({"json_report": str(json_path), "markdown_report": str(md_path)}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Remediate failed-metrics strategies and bootstrap low-sample strategies.")
    parser.add_argument("--from-acceptance-report", required=True, help="Path to an existing execution audit acceptance JSON report.")
    parser.add_argument("--failed-strategy-ids", default="", help="Optional comma-separated strategy ids to override failed_metrics selection.")
    parser.add_argument("--bootstrap-strategy-ids", default="", help="Optional comma-separated strategy ids to override insufficient_samples selection.")
    parser.add_argument("--report-dir", default="", help="Directory to write remediation reports.")
    parser.add_argument("--version-tag", default="", help="Optional suffix for generated report files.")
    args = parser.parse_args()
    return run_with_db_cleanup(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
