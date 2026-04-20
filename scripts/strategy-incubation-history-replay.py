#!/usr/bin/env python3
"""Replay historical incubation dates to accumulate real paper-trading samples."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
for relative in ("packages/akshare-mcp/src", "packages/strategy-factory/src"):
    path = ROOT_DIR / relative
    if path.exists():
        sys.path.insert(0, str(path))

from akshare_mcp.env_loader import load_mcp_env
from akshare_mcp.services.incubation import get_strategy_incubation_service
from akshare_mcp.storage import get_db, run_with_db_cleanup


SAMPLE_GAP_BLOCKERS = {
    "realized_trade_evidence_insufficient",
    "bootstrap_pending",
    "insufficient_samples",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _normalize_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _coerce_date(value: str) -> date | None:
    token = str(value or "").strip()
    if not token:
        return None
    return date.fromisoformat(token[:10])


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_affected_rows(execute_result: Any) -> int:
    token = str(execute_result or "").strip()
    if not token:
        return 0
    parts = token.split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except Exception:
        return 0


def _load_strategy_ids_from_acceptance_report(path: Path, *, sample_gap_only: bool) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    strategy_ids: list[str] = []
    for row in list(payload.get("strategy_results") or []):
        blockers = {
            str(item).strip()
            for item in list(row.get("blockers") or [])
            if str(item).strip()
        }
        if sample_gap_only and blockers.isdisjoint(SAMPLE_GAP_BLOCKERS):
            continue
        strategy_id = str(row.get("strategy_id") or "").strip()
        if strategy_id:
            strategy_ids.append(strategy_id)
    return list(dict.fromkeys(strategy_ids))


async def _reset_strategy_runtime_state(
    db,
    strategy_id: str,
) -> dict[str, Any]:
    strategy_token = str(strategy_id or "").strip()
    if not strategy_token:
        return {"strategy_id": strategy_token, "account_ids": [], "deleted": {}}

    async with db.acquire() as conn:
        account_rows = await conn.fetch(
            "SELECT id FROM paper_accounts WHERE strategy_id = $1 ORDER BY created_at",
            strategy_token,
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
                    strategy_token,
                    account_ids,
                )
            )
            deleted["strategy_trade_positions"] = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM strategy_trade_positions
                    WHERE strategy_id = $1 OR account_id = ANY($2::text[])
                    """,
                    strategy_token,
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
                    strategy_token,
                    account_ids,
                )
            )
            deleted["paper_orders"] = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM paper_orders
                    WHERE strategy_id = $1 OR account_id = ANY($2::text[])
                    """,
                    strategy_token,
                    account_ids,
                )
            )
            deleted["paper_accounts"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM paper_accounts WHERE id = ANY($1::text[])",
                    account_ids,
                )
            )
        else:
            deleted["strategy_trade_position_fills"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM strategy_trade_position_fills WHERE strategy_id = $1",
                    strategy_token,
                )
            )
            deleted["strategy_trade_positions"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM strategy_trade_positions WHERE strategy_id = $1",
                    strategy_token,
                )
            )
            deleted["paper_trades"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM paper_trades WHERE strategy_id = $1",
                    strategy_token,
                )
            )
            deleted["paper_orders"] = _parse_affected_rows(
                await conn.execute(
                    "DELETE FROM paper_orders WHERE strategy_id = $1",
                    strategy_token,
                )
            )
            deleted["paper_accounts"] = 0
            deleted["paper_positions"] = 0
            deleted["paper_nav"] = 0

        deleted["strategy_incubation_metrics"] = _parse_affected_rows(
            await conn.execute(
                "DELETE FROM strategy_incubation_metrics WHERE strategy_id = $1",
                strategy_token,
            )
        )
        deleted["strategy_incubation_accounts"] = _parse_affected_rows(
            await conn.execute(
                "DELETE FROM strategy_incubation_accounts WHERE strategy_id = $1",
                strategy_token,
            )
        )

    return {
        "strategy_id": strategy_token,
        "account_ids": account_ids,
        "deleted": deleted,
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = dict(report.get("summary") or {})
    lines = [
        "# Strategy Incubation History Replay",
        "",
        f"- Generated at: {_now_iso()}",
        f"- Strategy count: {summary.get('strategy_count', 0)}",
        f"- Replayed days: {summary.get('replayed_days', 0)}",
        f"- Non-empty days: {summary.get('non_empty_days', 0)}",
        f"- Orders created: {summary.get('orders_created', 0)}",
        f"- Orders filled: {summary.get('orders_filled', 0)}",
        f"- Rejected orders: {summary.get('rejected_orders', 0)}",
        "",
        "## Strategies",
        "",
        "| Strategy | Replayed Days | Non-empty Days | Orders Filled | Acceptance Blockers |",
        "| --- | --- | --- | --- | --- |",
    ]
    items = list(report.get("items") or [])
    for item in items:
        blockers = ", ".join(
            list(((item.get("acceptance") or {}).get("blockers") or []))
        ) or "-"
        lines.append(
            f"| {item.get('strategy_id') or '-'} | {int(item.get('replayed_days') or 0)} | "
            f"{int(item.get('non_empty_days') or 0)} | {int(item.get('orders_filled') or 0)} | {blockers} |"
        )
    if not items:
        lines.append("| - | - | - | - | - |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _async_main(args: argparse.Namespace) -> int:
    started_at = _now_iso()
    env_path = load_mcp_env(override=False)
    db = get_db()
    service = get_strategy_incubation_service()

    strategy_ids = _normalize_csv(args.strategy_ids)
    if not strategy_ids and args.from_acceptance_report:
        strategy_ids = _load_strategy_ids_from_acceptance_report(
            Path(args.from_acceptance_report).resolve(),
            sample_gap_only=bool(args.sample_gap_only),
        )
    if not strategy_ids:
        statuses = _normalize_csv(args.statuses) or ["submitted", "incubating", "listed", "rejected"]
        rows = await db.list_strategies(status=statuses, limit=max(1, int(args.limit or 50)), offset=0)
        strategy_ids = [
            str(item.get("id") or "").strip()
            for item in rows
            if str(item.get("id") or "").strip()
        ]

    strategies = []
    for strategy_id in strategy_ids:
        strategy = await db.get_strategy(strategy_id)
        if strategy:
            strategies.append(strategy)

    resets: list[dict[str, Any]] = []
    if args.reset_state:
        for strategy in strategies:
            resets.append(
                await _reset_strategy_runtime_state(
                    db,
                    str(strategy.get("id") or "").strip(),
                )
            )

    result = await service.replay_strategies_history(
        db,
        strategies,
        start_date=_coerce_date(args.start_date) if args.start_date else None,
        end_date=_coerce_date(args.end_date) if args.end_date else None,
        include_market_days=not bool(args.signal_dates_only),
        max_dates=max(1, int(args.max_dates or 1500)),
        force_close_open_positions=bool(args.force_close_open_positions),
        run_acceptance=not bool(args.skip_acceptance),
    )

    report = {
        "started_at": started_at,
        "finished_at": _now_iso(),
        "env_source": str(env_path) if env_path else None,
        "arguments": _json_safe(vars(args)),
        "summary": {
            "strategy_count": int(result.get("count") or 0),
            "replayed_days": int(result.get("replayed_days") or 0),
            "non_empty_days": int(result.get("non_empty_days") or 0),
            "orders_created": int(result.get("orders_created") or 0),
            "orders_filled": int(result.get("orders_filled") or 0),
            "rejected_orders": int(result.get("rejected_orders") or 0),
            "metrics_recorded": int(result.get("metrics_recorded") or 0),
            "reset_count": len(resets),
        },
        "reset_state": _json_safe(resets),
        "items": _json_safe(result.get("items") or []),
    }

    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    version_tag = args.version_tag or _now().strftime("incubation_replay_%Y%m%d_%H%M%S")
    json_path = report_dir / f"strategy_incubation_history_replay_{version_tag}.json"
    md_path = report_dir / f"strategy_incubation_history_replay_{version_tag}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(report, md_path)

    print(f"strategy_count: {report['summary']['strategy_count']}")
    print(f"replayed_days: {report['summary']['replayed_days']}")
    print(f"orders_filled: {report['summary']['orders_filled']}")
    print(f"report_json: {json_path}")
    print(f"report_md: {md_path}")
    for item in report["items"]:
        acceptance = dict(item.get("acceptance") or {})
        print(
            f"{item.get('strategy_id')}: replayed_days={item.get('replayed_days')} "
            f"filled={item.get('orders_filled')} blockers={len(list(acceptance.get('blockers') or []))}"
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay historical incubation dates to accumulate paper-trading samples."
    )
    parser.add_argument("--strategy-ids", default="", help="Comma-separated strategy IDs.")
    parser.add_argument("--from-acceptance-report", default="", help="Optional execution-audit acceptance JSON path.")
    parser.add_argument("--sample-gap-only", action="store_true", help="When loading from acceptance report, only include sample-gap blockers.")
    parser.add_argument("--statuses", default="submitted,incubating,listed,rejected", help="Statuses used when strategy IDs are omitted.")
    parser.add_argument("--limit", type=int, default=50, help="Selection limit when loading by status.")
    parser.add_argument("--start-date", default="", help="Optional replay start date YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Optional replay end date YYYY-MM-DD.")
    parser.add_argument("--max-dates", type=int, default=1500, help="Max replay dates per strategy.")
    parser.add_argument("--signal-dates-only", action="store_true", help="Only replay signal dates; skip extra K-line trading dates.")
    parser.add_argument("--force-close-open-positions", action="store_true", help="After replay reaches the last available date, force-close remaining open positions.")
    parser.add_argument("--reset-state", action="store_true", help="Delete existing incubation/paper-trading runtime state for selected strategies before replay.")
    parser.add_argument("--skip-acceptance", action="store_true", help="Skip execution-audit acceptance after replay.")
    parser.add_argument(
        "--report-dir",
        default=str(ROOT_DIR / "reports" / "incubation-history-replay"),
        help="Directory for replay reports.",
    )
    parser.add_argument("--version-tag", default="", help="Optional report version tag.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return run_with_db_cleanup(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
