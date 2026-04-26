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


ACCEPTANCE_REPORT_TYPE = "execution_audit_acceptance"
ACCEPTANCE_REPORT_SCHEMA_VERSION = "execution_audit_acceptance.v2"
REPLAY_REPORT_TYPE = "strategy_incubation_history_replay"
REPLAY_REPORT_SCHEMA_VERSION = "strategy_incubation_history_replay.v2"
SAMPLE_GAP_CATEGORY = "sample_gap"
SAMPLE_GAP_BLOCKERS = {
    "realized_trade_evidence_insufficient",
    "bootstrap_pending",
    "insufficient_samples",
    "promotion_hard_gate_pending",
}
SAMPLE_GAP_GATE_STATUSES = {
    "bootstrap_pending",
    "insufficient_samples",
    "bootstrap_ready",
}
DEFAULT_TARGET_REALIZED_TRADES = 20
LOW_SAMPLE_RUNTIME_PATCH_VERSION = "production_sample_top_up_v1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _normalize_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _unique_tokens(values) -> list[str]:
    tokens: list[str] = []
    for item in list(values or []):
        token = str(item or "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _acceptance_blockers(row: dict[str, Any]) -> list[str]:
    payload = _acceptance_payload(row)
    details = [dict(item) for item in list(payload.get("blocker_details") or []) if isinstance(item, dict)]
    return _unique_tokens([*_unique_tokens(payload.get("blockers")), *_unique_tokens(item.get("blocker") for item in details)])


def _acceptance_gap_categories(row: dict[str, Any]) -> list[str]:
    payload = _acceptance_payload(row)
    details = [dict(item) for item in list(payload.get("blocker_details") or []) if isinstance(item, dict)]
    categories = _unique_tokens(
        [
            *_unique_tokens(payload.get("gap_categories")),
            *_unique_tokens(item.get("category") for item in details),
        ]
    )
    if categories:
        return categories
    blockers = set(_acceptance_blockers(row))
    if not blockers.isdisjoint(SAMPLE_GAP_BLOCKERS):
        return [SAMPLE_GAP_CATEGORY]
    gate_status = str(
        dict(row.get("trade_audit_summary") or {}).get("execution_audit_gate_status") or ""
    ).strip()
    if gate_status in SAMPLE_GAP_GATE_STATUSES:
        return [SAMPLE_GAP_CATEGORY]
    return []


def _acceptance_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(row or {})
    result = dict(payload.get("result") or {})
    if not result:
        return payload
    return {**result, **payload}


def _acceptance_has_sample_gap(row: dict[str, Any]) -> bool:
    payload = _acceptance_payload(row)
    marker = payload.get("has_sample_gap")
    if marker is not None:
        return bool(marker)
    return SAMPLE_GAP_CATEGORY in _acceptance_gap_categories(payload)


def _acceptance_required_trade_count(row: dict[str, Any], *, target: int) -> int:
    payload = _acceptance_payload(row)
    trade_audit_summary = dict(payload.get("trade_audit_summary") or {})
    hard_gate_metrics = dict(trade_audit_summary.get("hard_gate_metrics") or {})
    required = max(
        _safe_int(trade_audit_summary.get("required_trade_count"), 0),
        _safe_int(hard_gate_metrics.get("required_trade_count"), 0),
        _safe_int(target, DEFAULT_TARGET_REALIZED_TRADES),
    )
    return max(required, DEFAULT_TARGET_REALIZED_TRADES)


def _acceptance_realized_trade_count(row: dict[str, Any]) -> int:
    payload = _acceptance_payload(row)
    trade_audit_summary = dict(payload.get("trade_audit_summary") or {})
    hard_gate_metrics = dict(trade_audit_summary.get("hard_gate_metrics") or {})
    return max(
        _safe_int(trade_audit_summary.get("realized_trade_count"), 0),
        _safe_int(hard_gate_metrics.get("realized_trade_count"), 0),
    )


def _acceptance_sample_shortfall(row: dict[str, Any], *, target: int) -> int:
    required = _acceptance_required_trade_count(row, target=target)
    realized = _acceptance_realized_trade_count(row)
    return max(required - realized, 0)


def _validate_acceptance_report_payload(payload: dict[str, Any], *, path: Path) -> list[dict[str, Any]]:
    report_type = str(payload.get("report_type") or "").strip()
    if report_type and report_type != ACCEPTANCE_REPORT_TYPE:
        raise ValueError(
            f"{path} is not an {ACCEPTANCE_REPORT_TYPE} report (report_type={report_type})"
        )
    strategy_rows = payload.get("strategy_results")
    if not isinstance(strategy_rows, list):
        raise ValueError(f"{path} missing strategy_results[] in acceptance report")
    normalized_rows = [dict(item) for item in strategy_rows if isinstance(item, dict)]
    if len(normalized_rows) != len(strategy_rows):
        raise ValueError(f"{path} contains non-object strategy_results rows")
    return normalized_rows


def _load_strategy_ids_from_acceptance_report(path: Path, *, sample_gap_only: bool) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = _validate_acceptance_report_payload(payload, path=path)
    strategy_ids: list[str] = []
    for row in rows:
        if sample_gap_only and not _acceptance_has_sample_gap(row):
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


def _summarize_acceptance(
    acceptance: dict[str, Any] | None,
    *,
    target_realized_trades: int = DEFAULT_TARGET_REALIZED_TRADES,
) -> dict[str, Any]:
    payload = _acceptance_payload(acceptance)
    gap_categories = _acceptance_gap_categories(payload)
    blockers = _acceptance_blockers(payload)
    trade_audit_summary = dict(payload.get("trade_audit_summary") or {})
    acceptance_matrix = dict(payload.get("acceptance_matrix") or {})
    required_trade_count = _acceptance_required_trade_count(
        payload,
        target=max(DEFAULT_TARGET_REALIZED_TRADES, int(target_realized_trades or DEFAULT_TARGET_REALIZED_TRADES)),
    )
    realized_trade_count = _acceptance_realized_trade_count(payload)
    sample_shortfall = max(required_trade_count - realized_trade_count, 0)
    return {
        "status": str(payload.get("status") or "").strip() or None,
        "overall_ready": bool(acceptance_matrix.get("overall_ready")),
        "blockers": blockers,
        "gap_categories": gap_categories,
        "has_sample_gap": _acceptance_has_sample_gap(payload),
        "execution_audit_gate_status": str(
            trade_audit_summary.get("execution_audit_gate_status") or ""
        ).strip()
        or None,
        "realized_trade_count": realized_trade_count,
        "required_trade_count": required_trade_count,
        "bootstrap_trade_floor": _safe_int(trade_audit_summary.get("bootstrap_trade_floor"), 0),
        "sample_shortfall": sample_shortfall,
        "production_sample_ready": sample_shortfall == 0,
    }


def _build_acceptance_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    target_realized_trades: int,
) -> dict[str, Any]:
    before_summary = _summarize_acceptance(before, target_realized_trades=target_realized_trades)
    after_summary = _summarize_acceptance(after, target_realized_trades=target_realized_trades)
    return {
        "realized_before": before_summary["realized_trade_count"],
        "realized_after": after_summary["realized_trade_count"],
        "realized_delta": int(after_summary["realized_trade_count"]) - int(before_summary["realized_trade_count"]),
        "required_trade_count": max(
            int(before_summary["required_trade_count"]),
            int(after_summary["required_trade_count"]),
            int(target_realized_trades or DEFAULT_TARGET_REALIZED_TRADES),
        ),
        "shortfall_before": before_summary["sample_shortfall"],
        "shortfall_after": after_summary["sample_shortfall"],
        "shortfall_delta": int(before_summary["sample_shortfall"]) - int(after_summary["sample_shortfall"]),
        "gate_before": before_summary["execution_audit_gate_status"],
        "gate_after": after_summary["execution_audit_gate_status"],
        "ready_before": before_summary["overall_ready"],
        "ready_after": after_summary["overall_ready"],
        "blockers_before": before_summary["blockers"],
        "blockers_after": after_summary["blockers"],
    }


def _production_sample_failure_reasons(
    item: dict[str, Any],
    *,
    acceptance_summary: dict[str, Any],
    runtime_counts: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if item.get("error"):
        reasons.append(f"replay_error:{item.get('error')}")
    if int(acceptance_summary.get("sample_shortfall") or 0) <= 0:
        return reasons
    if int(runtime_counts.get("signal_days") or 0) <= 0:
        reasons.append("no_signal_days")
    if int(runtime_counts.get("signal_rows") or 0) <= 0:
        reasons.append("no_signal_rows")
    if int(runtime_counts.get("paper_orders") or 0) <= 0:
        reasons.append("no_paper_orders")
    if int(runtime_counts.get("filled_orders") or 0) <= 0:
        reasons.append("no_filled_orders")
    if int(runtime_counts.get("closed_positions") or 0) < int(acceptance_summary.get("required_trade_count") or 0):
        reasons.append("closed_round_trips_below_required")
    if int(runtime_counts.get("open_positions") or 0) > 0:
        reasons.append("open_positions_remaining")
    if acceptance_summary.get("execution_audit_gate_status") == "bootstrap_ready":
        reasons.append("bootstrap_ready_not_production_ready")
    return _unique_tokens(reasons)


def _annotate_replay_items(
    items,
    *,
    target_realized_trades: int = DEFAULT_TARGET_REALIZED_TRADES,
    acceptance_before_by_id: dict[str, dict[str, Any]] | None = None,
    runtime_counts_by_id: dict[str, dict[str, Any]] | None = None,
    remediation_by_id: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    ready_count = 0
    sample_gap_remaining_count = 0
    production_shortfall_count = 0
    production_shortfall_total = 0
    realized_trade_total = 0
    blocker_counts: dict[str, int] = {}
    for raw_item in list(items or []):
        item = dict(raw_item or {})
        strategy_id = str(item.get("strategy_id") or "").strip()
        acceptance_summary = _summarize_acceptance(
            item.get("acceptance"),
            target_realized_trades=target_realized_trades,
        )
        if acceptance_summary["overall_ready"]:
            ready_count += 1
        if acceptance_summary["has_sample_gap"]:
            sample_gap_remaining_count += 1
        if int(acceptance_summary["sample_shortfall"] or 0) > 0:
            production_shortfall_count += 1
            production_shortfall_total += int(acceptance_summary["sample_shortfall"] or 0)
        realized_trade_total += int(acceptance_summary["realized_trade_count"] or 0)
        for blocker in acceptance_summary["blockers"]:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        item["acceptance_summary"] = acceptance_summary
        item["runtime_counts"] = dict((runtime_counts_by_id or {}).get(strategy_id) or {})
        item["remediation"] = dict((remediation_by_id or {}).get(strategy_id) or {})
        item["failure_reasons"] = _production_sample_failure_reasons(
            item,
            acceptance_summary=acceptance_summary,
            runtime_counts=item["runtime_counts"],
        )
        before_acceptance = dict((acceptance_before_by_id or {}).get(strategy_id) or {})
        if before_acceptance or item.get("acceptance"):
            item["acceptance_delta"] = _build_acceptance_delta(
                before_acceptance,
                item.get("acceptance"),
                target_realized_trades=target_realized_trades,
            )
        annotated.append(item)
    post_acceptance = {
        "ready_count": ready_count,
        "pending_count": len(annotated) - ready_count,
        "sample_gap_remaining_count": sample_gap_remaining_count,
        "production_shortfall_count": production_shortfall_count,
        "production_shortfall_total": production_shortfall_total,
        "realized_trade_total": realized_trade_total,
        "top_blockers": [
            {"blocker": blocker, "count": count}
            for blocker, count in sorted(
                blocker_counts.items(),
                key=lambda pair: (-pair[1], pair[0]),
            )[:10]
        ],
    }
    return annotated, post_acceptance


async def _capture_acceptance_by_strategy(
    db,
    strategies: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    captured: dict[str, dict[str, Any]] = {}
    if not hasattr(db, "run_execution_audit_acceptance"):
        return captured
    for strategy in list(strategies or []):
        strategy_id = str((strategy or {}).get("id") or "").strip()
        if not strategy_id:
            continue
        try:
            acceptance = await db.run_execution_audit_acceptance(
                strategy_id=strategy_id,
                backfill=True,
            )
            captured[strategy_id] = dict(acceptance or {})
        except Exception as exc:
            captured[strategy_id] = {
                "strategy_id": strategy_id,
                "status": "acceptance_capture_failed",
                "blockers": [f"acceptance_capture_failed:{exc}"],
            }
    return captured


async def _load_runtime_counts_by_strategy(
    db,
    strategy_ids: list[str],
) -> dict[str, dict[str, Any]]:
    ids = [str(item or "").strip() for item in list(strategy_ids or []) if str(item or "").strip()]
    if not ids:
        return {}
    results = {
        strategy_id: {
            "signal_days": 0,
            "signal_rows": 0,
            "signal_codes": 0,
            "closed_positions": 0,
            "open_positions": 0,
            "audit_eligible_closed_positions": 0,
            "paper_orders": 0,
            "filled_orders": 0,
            "paper_trades": 0,
            "latest_signal_date": None,
            "latest_closed_at": None,
        }
        for strategy_id in ids
    }
    async with db.acquire() as conn:
        signal_rows = await conn.fetch(
            """
            SELECT
                strategy_id,
                COUNT(*)::int AS signal_rows,
                COUNT(DISTINCT signal_date)::int AS signal_days,
                COUNT(DISTINCT code)::int AS signal_codes,
                ARRAY_REMOVE(ARRAY_AGG(DISTINCT code), NULL)::text[] AS observed_signal_codes,
                MAX(signal_date)::text AS latest_signal_date
            FROM strategy_signals
            WHERE strategy_id = ANY($1::text[])
            GROUP BY strategy_id
            """,
            ids,
        )
        for row in list(signal_rows or []):
            strategy_id = str((row or {}).get("strategy_id") or "").strip()
            if strategy_id in results:
                results[strategy_id].update(
                    {
                        "signal_rows": _safe_int((row or {}).get("signal_rows"), 0),
                        "signal_days": _safe_int((row or {}).get("signal_days"), 0),
                        "signal_codes": _safe_int((row or {}).get("signal_codes"), 0),
                        "observed_signal_codes": _unique_tokens((row or {}).get("observed_signal_codes") or []),
                        "latest_signal_date": (row or {}).get("latest_signal_date"),
                    }
                )

        position_rows = await conn.fetch(
            """
            SELECT
                strategy_id,
                COUNT(*) FILTER (WHERE status = 'closed')::int AS closed_positions,
                COUNT(*) FILTER (WHERE status <> 'closed' OR status IS NULL)::int AS open_positions,
                COUNT(*) FILTER (WHERE status = 'closed' AND COALESCE(audit_eligible, false))::int AS audit_eligible_closed_positions,
                MAX(closed_at)::text AS latest_closed_at
            FROM strategy_trade_positions
            WHERE strategy_id = ANY($1::text[])
            GROUP BY strategy_id
            """,
            ids,
        )
        for row in list(position_rows or []):
            strategy_id = str((row or {}).get("strategy_id") or "").strip()
            if strategy_id in results:
                results[strategy_id].update(
                    {
                        "closed_positions": _safe_int((row or {}).get("closed_positions"), 0),
                        "open_positions": _safe_int((row or {}).get("open_positions"), 0),
                        "audit_eligible_closed_positions": _safe_int(
                            (row or {}).get("audit_eligible_closed_positions"),
                            0,
                        ),
                        "latest_closed_at": (row or {}).get("latest_closed_at"),
                    }
                )

        order_rows = await conn.fetch(
            """
            SELECT
                strategy_id,
                COUNT(*)::int AS paper_orders,
                COUNT(*) FILTER (WHERE status = 'filled')::int AS filled_orders
            FROM paper_orders
            WHERE strategy_id = ANY($1::text[])
            GROUP BY strategy_id
            """,
            ids,
        )
        for row in list(order_rows or []):
            strategy_id = str((row or {}).get("strategy_id") or "").strip()
            if strategy_id in results:
                results[strategy_id].update(
                    {
                        "paper_orders": _safe_int((row or {}).get("paper_orders"), 0),
                        "filled_orders": _safe_int((row or {}).get("filled_orders"), 0),
                    }
                )

        trade_rows = await conn.fetch(
            """
            SELECT strategy_id, COUNT(*)::int AS paper_trades
            FROM paper_trades
            WHERE strategy_id = ANY($1::text[])
            GROUP BY strategy_id
            """,
            ids,
        )
        for row in list(trade_rows or []):
            strategy_id = str((row or {}).get("strategy_id") or "").strip()
            if strategy_id in results:
                results[strategy_id]["paper_trades"] = _safe_int((row or {}).get("paper_trades"), 0)
    return results


def _strategy_runtime_params(strategy: dict[str, Any]) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    nested = dict(params.get("params") or {})
    runtime_params = dict(nested)
    runtime_params.update({key: value for key, value in params.items() if key != "params"})
    for key in (
        "strategy_type",
        "target_symbols",
        "runtime_playbook",
        "risk_rules",
        "stock_pool",
        "max_holding_days",
        "time_stop_days",
        "target_symbols",
    ):
        if payload.get(key) is not None and runtime_params.get(key) is None:
            runtime_params[key] = payload.get(key)
    return runtime_params


def _sync_runtime_params_container(
    params_container: dict[str, Any],
    runtime_params: dict[str, Any],
) -> dict[str, Any]:
    params = dict(params_container or {})
    nested = dict(params.get("params") or {})
    merged_runtime = {key: value for key, value in dict(runtime_params or {}).items() if key != "params"}
    nested.update(merged_runtime)
    params.update(merged_runtime)
    params["params"] = nested
    return params


def _extract_target_symbols(strategy: dict[str, Any], runtime_counts: dict[str, Any] | None = None) -> list[str]:
    runtime_params = _strategy_runtime_params(strategy)
    stock_pool = dict(runtime_params.get("stock_pool") or {})
    symbols = _unique_tokens(
        [
            *list(runtime_params.get("target_symbols") or []),
            *list(stock_pool.get("symbols") or []),
            *list(runtime_params.get("prioritized_symbols") or []),
        ]
    )
    observed_codes = list(dict(runtime_counts or {}).get("observed_signal_codes") or [])
    return _unique_tokens([*symbols, *observed_codes])


async def _apply_low_sample_runtime_remediation(
    db,
    strategy: dict[str, Any],
    *,
    start_date: date | None,
    end_date: date | None,
    history_limit: int,
    runtime_counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    strategy_id = str((strategy or {}).get("id") or "").strip()
    if not strategy_id:
        return {"strategy_id": strategy_id, "updated": False, "reason": "strategy_id_missing"}

    actions: list[str] = []
    failures: list[str] = []
    signal_cache: dict[str, Any] | None = None
    try:
        from akshare_mcp.services.strategy_acceptance_remediation import (
            get_strategy_acceptance_remediation_service,
        )

        remediation_service = get_strategy_acceptance_remediation_service()
        signal_cache = await remediation_service.rebuild_strategy_signal_cache(
            db,
            strategy,
            start_date=start_date,
            end_date=end_date,
            history_limit=max(250, int(history_limit or 1500)),
        )
        actions.append("signal_cache_rebuild")
    except Exception as exc:
        failures.append(f"signal_cache_rebuild_failed:{exc}")

    runtime_params = _strategy_runtime_params(strategy)
    params_before = dict(strategy.get("params") or {})
    runtime_playbook = dict(runtime_params.get("runtime_playbook") or {})
    risk_rules = dict(runtime_params.get("risk_rules") or {})
    exit_policy = dict(runtime_playbook.get("exit_policy") or {})
    position_policy = dict(runtime_playbook.get("position_policy") or {})
    entry_policy = dict(runtime_playbook.get("entry_policy") or {})
    stock_pool = dict(runtime_params.get("stock_pool") or {})
    stock_filters = dict(stock_pool.get("filters") or {})

    target_symbols = _extract_target_symbols(strategy, runtime_counts=runtime_counts)
    signal_codes = _unique_tokens(list((runtime_counts or {}).get("observed_signal_codes") or []))
    expanded_symbols = _unique_tokens([*target_symbols, *signal_codes])
    if expanded_symbols and len(expanded_symbols) > len(target_symbols):
        stock_pool["selection_mode"] = str(stock_pool.get("selection_mode") or "explicit")
        stock_pool["symbols"] = expanded_symbols
        stock_filters["prioritized_symbols"] = expanded_symbols
        stock_filters["max_active_symbols"] = max(_safe_int(stock_filters.get("max_active_symbols"), 0), len(expanded_symbols))
        runtime_params["target_symbols"] = expanded_symbols
        runtime_params["prioritized_symbols"] = expanded_symbols
        runtime_params["max_active_symbols"] = max(_safe_int(runtime_params.get("max_active_symbols"), 0), len(expanded_symbols))
        actions.append("target_pool_expanded_from_signal_codes")
    elif not expanded_symbols:
        failures.append("target_pool_expansion_unavailable")

    existing_time_stop = _safe_int(
        exit_policy.get("time_stop_days")
        or risk_rules.get("time_stop_days")
        or runtime_params.get("time_stop_days"),
        0,
    )
    if existing_time_stop <= 0 or existing_time_stop > 5:
        exit_policy["time_stop_days"] = 5
        risk_rules["time_stop_days"] = 5
        runtime_params["time_stop_days"] = 5
        actions.append("time_stop_days_shortened")

    existing_max_holding = _safe_int(
        risk_rules.get("max_holding_days")
        or runtime_params.get("max_holding_days")
        or exit_policy.get("max_holding_days"),
        0,
    )
    if existing_max_holding <= 0 or existing_max_holding > 7:
        risk_rules["max_holding_days"] = 7
        exit_policy["max_holding_days"] = 7
        runtime_params["max_holding_days"] = 7
        actions.append("max_holding_days_shortened")

    position_policy["max_concurrent_positions"] = max(
        _safe_int(position_policy.get("max_concurrent_positions"), 1),
        min(max(len(expanded_symbols), 1), 5),
    )
    entry_policy["signal_validity_days"] = min(
        max(_safe_int(entry_policy.get("signal_validity_days"), 1), 1),
        2,
    )
    stock_pool["filters"] = stock_filters
    runtime_params["stock_pool"] = stock_pool
    runtime_playbook["exit_policy"] = exit_policy
    runtime_playbook["position_policy"] = position_policy
    runtime_playbook["entry_policy"] = entry_policy
    runtime_params["runtime_playbook"] = runtime_playbook
    runtime_params["risk_rules"] = risk_rules
    runtime_params["production_sample_top_up"] = {
        "version": LOW_SAMPLE_RUNTIME_PATCH_VERSION,
        "updated_at": _now_iso(),
        "actions": actions,
        "failures": failures,
    }

    params_after = _sync_runtime_params_container(params_before, runtime_params)
    changed = json.dumps(params_after, sort_keys=True, default=str) != json.dumps(
        params_before,
        sort_keys=True,
        default=str,
    )
    if changed:
        updated_payload = dict(strategy)
        updated_payload["params"] = params_after
        await db.save_strategy(updated_payload)
        if hasattr(db, "save_strategy_domain_event"):
            await db.save_strategy_domain_event(
                {
                    "strategy_id": strategy_id,
                    "aggregate_type": "strategy",
                    "aggregate_id": strategy_id,
                    "event_type": "strategy.production_sample_remediation_applied",
                    "source": "strategy_incubation_history_replay",
                    "severity": "info",
                    "payload": {
                        "version": LOW_SAMPLE_RUNTIME_PATCH_VERSION,
                        "actions": actions,
                        "failures": failures,
                        "signal_cache": signal_cache or {},
                        "target_symbols": expanded_symbols,
                    },
                }
            )

    return {
        "strategy_id": strategy_id,
        "updated": changed,
        "actions": actions,
        "failures": failures,
        "signal_cache": signal_cache or {},
        "target_symbols": expanded_symbols,
    }


async def _degrade_unresolved_strategy(
    db,
    strategy: dict[str, Any],
    *,
    acceptance_summary: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    strategy_id = str((strategy or {}).get("id") or "").strip()
    if not strategy_id:
        return {"strategy_id": strategy_id, "degraded": False, "reason": "strategy_id_missing"}
    metadata = {
        "source": "strategy_incubation_history_replay",
        "reason": reason,
        "acceptance_summary": acceptance_summary,
    }
    if hasattr(db, "update_strategy_status"):
        await db.update_strategy_status(
            strategy_id,
            "rejected",
            actor_id="strategy_incubation_history_replay",
            reason=reason,
            metadata=metadata,
        )
    else:
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE strategies SET status = 'rejected', updated_at = NOW() WHERE id = $1",
                strategy_id,
            )
    if hasattr(db, "save_strategy_domain_event"):
        await db.save_strategy_domain_event(
            {
                "strategy_id": strategy_id,
                "aggregate_type": "strategy",
                "aggregate_id": strategy_id,
                "event_type": "strategy.production_sample_degraded",
                "source": "strategy_incubation_history_replay",
                "severity": "warning",
                "payload": metadata,
            }
        )
    return {
        "strategy_id": strategy_id,
        "degraded": True,
        "status": "rejected",
        "reason": reason,
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = dict(report.get("summary") or {})
    lines = [
        "# Strategy Incubation History Replay",
        "",
        f"- Generated at: {report.get('finished_at') or _now_iso()}",
        f"- Report schema: {report.get('schema_version') or REPLAY_REPORT_SCHEMA_VERSION}",
        f"- Strategy count: {summary.get('strategy_count', 0)}",
        f"- Replayed days: {summary.get('replayed_days', 0)}",
        f"- Non-empty days: {summary.get('non_empty_days', 0)}",
        f"- Orders created: {summary.get('orders_created', 0)}",
        f"- Orders filled: {summary.get('orders_filled', 0)}",
        f"- Rejected orders: {summary.get('rejected_orders', 0)}",
        f"- Post-acceptance ready: {dict(summary.get('post_acceptance') or {}).get('ready_count', 0)}",
        f"- Sample-gap remaining: {dict(summary.get('post_acceptance') or {}).get('sample_gap_remaining_count', 0)}",
        f"- Production shortfall strategies: {dict(summary.get('post_acceptance') or {}).get('production_shortfall_count', 0)}",
        f"- Production shortfall total: {dict(summary.get('post_acceptance') or {}).get('production_shortfall_total', 0)}",
        "",
        "## Strategies",
        "",
        "| Strategy | Replayed Days | Non-empty Days | Orders Filled | Realized / Required | Shortfall | Signal Days | Closed / Open | Acceptance Status | Acceptance Blockers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    items = list(report.get("items") or [])
    for item in items:
        acceptance_summary = dict(item.get("acceptance_summary") or {})
        runtime_counts = dict(item.get("runtime_counts") or {})
        blockers = ", ".join(list(acceptance_summary.get("blockers") or [])) or "-"
        lines.append(
            f"| {item.get('strategy_id') or '-'} | {int(item.get('replayed_days') or 0)} | "
            f"{int(item.get('non_empty_days') or 0)} | {int(item.get('orders_filled') or 0)} | "
            f"{int(acceptance_summary.get('realized_trade_count') or 0)} / {int(acceptance_summary.get('required_trade_count') or 0)} | "
            f"{int(acceptance_summary.get('sample_shortfall') or 0)} | "
            f"{int(runtime_counts.get('signal_days') or 0)} | "
            f"{int(runtime_counts.get('closed_positions') or 0)} / {int(runtime_counts.get('open_positions') or 0)} | "
            f"{acceptance_summary.get('status') or '-'} | {blockers} |"
        )
    if not items:
        lines.append("| - | - | - | - | - | - | - | - | - | - |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _async_main(args: argparse.Namespace) -> int:
    started_at = _now_iso()
    env_path = load_mcp_env(override=False)
    db = get_db()
    service = get_strategy_incubation_service()
    acceptance_report_path = (
        str(Path(args.from_acceptance_report).resolve())
        if args.from_acceptance_report
        else None
    )

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
    strategies_by_id = {
        str((strategy or {}).get("id") or "").strip(): strategy
        for strategy in strategies
        if str((strategy or {}).get("id") or "").strip()
    }
    target_realized_trades = max(
        DEFAULT_TARGET_REALIZED_TRADES,
        int(args.target_realized_trades or DEFAULT_TARGET_REALIZED_TRADES),
    )

    resets: list[dict[str, Any]] = []
    if args.reset_state:
        for strategy in strategies:
            resets.append(
                await _reset_strategy_runtime_state(
                    db,
                    str(strategy.get("id") or "").strip(),
                )
            )

    acceptance_before_by_id: dict[str, dict[str, Any]] = {}
    if args.from_acceptance_report:
        source_path = Path(args.from_acceptance_report).resolve()
        source_payload = json.loads(source_path.read_text(encoding="utf-8"))
        for row in _validate_acceptance_report_payload(source_payload, path=source_path):
            strategy_id = str(row.get("strategy_id") or "").strip()
            if strategy_id:
                acceptance_before_by_id[strategy_id] = dict(row)
    if not acceptance_before_by_id and not args.skip_acceptance and not args.no_acceptance_delta:
        acceptance_before_by_id = await _capture_acceptance_by_strategy(db, strategies)

    runtime_counts_before = await _load_runtime_counts_by_strategy(
        db,
        [str((strategy or {}).get("id") or "").strip() for strategy in strategies],
    )
    remediation_by_id: dict[str, dict[str, Any]] = {}
    if args.auto_remediate_low_sample:
        start_date = _coerce_date(args.start_date) if args.start_date else None
        end_date = _coerce_date(args.end_date) if args.end_date else None
        for strategy in strategies:
            strategy_id = str((strategy or {}).get("id") or "").strip()
            before_summary = _summarize_acceptance(
                acceptance_before_by_id.get(strategy_id),
                target_realized_trades=target_realized_trades,
            )
            if int(before_summary.get("sample_shortfall") or target_realized_trades) <= 0:
                continue
            remediation_by_id[strategy_id] = await _apply_low_sample_runtime_remediation(
                db,
                strategy,
                start_date=start_date,
                end_date=end_date,
                history_limit=max(1, int(args.max_dates or 1500)),
                runtime_counts=runtime_counts_before.get(strategy_id),
            )
            if remediation_by_id[strategy_id].get("updated"):
                refreshed = await db.get_strategy(strategy_id)
                if refreshed:
                    strategies_by_id[strategy_id] = refreshed
        strategies = [strategies_by_id[strategy_id] for strategy_id in strategies_by_id]

    latest_items_by_id: dict[str, dict[str, Any]] = {}
    replay_rounds: list[dict[str, Any]] = []
    cumulative_result = {
        "count": len(strategies),
        "replayed_days": 0,
        "non_empty_days": 0,
        "orders_created": 0,
        "orders_filled": 0,
        "rejected_orders": 0,
        "metrics_recorded": 0,
    }
    if args.degrade_only:
        for strategy in strategies:
            strategy_id = str((strategy or {}).get("id") or "").strip()
            latest_items_by_id[strategy_id] = {
                "strategy_id": strategy_id,
                "replayed_days": 0,
                "non_empty_days": 0,
                "orders_created": 0,
                "orders_filled": 0,
                "rejected_orders": 0,
                "metrics_recorded": 0,
                "acceptance": acceptance_before_by_id.get(strategy_id),
            }
    else:
        remaining_strategies = list(strategies)
        max_rounds = max(1, int(args.top_up_rounds or 1))
        for round_index in range(max_rounds):
            if not remaining_strategies:
                break
            result = await service.replay_strategies_history(
                db,
                remaining_strategies,
                start_date=_coerce_date(args.start_date) if args.start_date else None,
                end_date=_coerce_date(args.end_date) if args.end_date else None,
                include_market_days=not bool(args.signal_dates_only),
                max_dates=max(1, int(args.max_dates or 1500)),
                force_close_open_positions=bool(args.force_close_open_positions),
                run_acceptance=not bool(args.skip_acceptance),
            )
            for key in ("replayed_days", "non_empty_days", "orders_created", "orders_filled", "rejected_orders", "metrics_recorded"):
                cumulative_result[key] += int(result.get(key) or 0)
            round_items = [dict(item or {}) for item in list(result.get("items") or [])]
            for item in round_items:
                strategy_id = str(item.get("strategy_id") or "").strip()
                if strategy_id:
                    latest_items_by_id[strategy_id] = item
            round_shortfalls: list[dict[str, Any]] = []
            next_remaining_ids: list[str] = []
            for item in round_items:
                strategy_id = str(item.get("strategy_id") or "").strip()
                acceptance_summary = _summarize_acceptance(
                    item.get("acceptance"),
                    target_realized_trades=target_realized_trades,
                )
                shortfall = int(acceptance_summary.get("sample_shortfall") or 0)
                round_shortfalls.append(
                    {
                        "strategy_id": strategy_id,
                        "realized_trade_count": acceptance_summary.get("realized_trade_count"),
                        "required_trade_count": acceptance_summary.get("required_trade_count"),
                        "shortfall": shortfall,
                        "gate_status": acceptance_summary.get("execution_audit_gate_status"),
                        "overall_ready": acceptance_summary.get("overall_ready"),
                    }
                )
                if shortfall > 0:
                    next_remaining_ids.append(strategy_id)
            replay_rounds.append(
                {
                    "round": round_index + 1,
                    "strategy_count": int(result.get("count") or 0),
                    "replayed_days": int(result.get("replayed_days") or 0),
                    "orders_filled": int(result.get("orders_filled") or 0),
                    "shortfalls": round_shortfalls,
                }
            )
            if args.skip_acceptance or not next_remaining_ids:
                break
            remaining_strategies = [
                refreshed
                for strategy_id in next_remaining_ids
                if (refreshed := await db.get_strategy(strategy_id))
            ]

    for strategy in strategies:
        strategy_id = str((strategy or {}).get("id") or "").strip()
        latest_items_by_id.setdefault(
            strategy_id,
            {
                "strategy_id": strategy_id,
                "replayed_days": 0,
                "non_empty_days": 0,
                "orders_created": 0,
                "orders_filled": 0,
                "rejected_orders": 0,
                "metrics_recorded": 0,
                "acceptance": acceptance_before_by_id.get(strategy_id),
            },
        )

    runtime_counts_after = await _load_runtime_counts_by_strategy(
        db,
        [str((strategy or {}).get("id") or "").strip() for strategy in strategies],
    )
    ordered_items = [
        latest_items_by_id[strategy_id]
        for strategy_id in strategy_ids
        if strategy_id in latest_items_by_id
    ]
    items, post_acceptance = _annotate_replay_items(
        ordered_items,
        target_realized_trades=target_realized_trades,
        acceptance_before_by_id=acceptance_before_by_id if not args.no_acceptance_delta else {},
        runtime_counts_by_id=runtime_counts_after,
        remediation_by_id=remediation_by_id,
    )

    degraded: list[dict[str, Any]] = []
    if args.degrade_unresolved:
        for item in items:
            acceptance_summary = dict(item.get("acceptance_summary") or {})
            if int(acceptance_summary.get("sample_shortfall") or 0) <= 0:
                continue
            strategy_id = str(item.get("strategy_id") or "").strip()
            strategy = strategies_by_id.get(strategy_id) or await db.get_strategy(strategy_id)
            if not strategy:
                continue
            degraded_item = await _degrade_unresolved_strategy(
                db,
                strategy,
                acceptance_summary=acceptance_summary,
                reason="production_sample_shortfall_unresolved",
            )
            degraded.append(degraded_item)
            item["degradation"] = degraded_item

    unresolved_shortfall_count = sum(
        1
        for item in items
        if int(dict(item.get("acceptance_summary") or {}).get("sample_shortfall") or 0) > 0
        and not dict(item.get("degradation") or {}).get("degraded")
    )

    report = {
        "report_type": REPLAY_REPORT_TYPE,
        "schema_version": REPLAY_REPORT_SCHEMA_VERSION,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "env_source": str(env_path) if env_path else None,
        "source_acceptance_report": acceptance_report_path,
        "arguments": _json_safe(vars(args)),
        "summary": {
            "strategy_count": int(cumulative_result.get("count") or 0),
            "target_realized_trades": target_realized_trades,
            "top_up_round_count": len(replay_rounds),
            "replayed_days": int(cumulative_result.get("replayed_days") or 0),
            "non_empty_days": int(cumulative_result.get("non_empty_days") or 0),
            "orders_created": int(cumulative_result.get("orders_created") or 0),
            "orders_filled": int(cumulative_result.get("orders_filled") or 0),
            "rejected_orders": int(cumulative_result.get("rejected_orders") or 0),
            "metrics_recorded": int(cumulative_result.get("metrics_recorded") or 0),
            "reset_count": len(resets),
            "degraded_count": len(degraded),
            "unresolved_shortfall_count": unresolved_shortfall_count,
            "post_acceptance": post_acceptance,
        },
        "runtime_counts_before": _json_safe(runtime_counts_before),
        "runtime_counts_after": _json_safe(runtime_counts_after),
        "replay_rounds": _json_safe(replay_rounds),
        "degraded": _json_safe(degraded),
        "reset_state": _json_safe(resets),
        "items": _json_safe(items),
    }

    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    version_tag = args.version_tag or _now().strftime("incubation_replay_%Y%m%d_%H%M%S")
    json_path = report_dir / f"strategy_incubation_history_replay_{version_tag}.json"
    md_path = report_dir / f"strategy_incubation_history_replay_{version_tag}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(report, md_path)

    print(f"strategy_count: {report['summary']['strategy_count']}")
    print(f"target_realized_trades: {report['summary']['target_realized_trades']}")
    print(f"replayed_days: {report['summary']['replayed_days']}")
    print(f"orders_filled: {report['summary']['orders_filled']}")
    print(f"production_shortfall_count: {dict(report['summary'].get('post_acceptance') or {}).get('production_shortfall_count', 0)}")
    print(f"unresolved_shortfall_count: {report['summary']['unresolved_shortfall_count']}")
    print(f"degraded_count: {report['summary']['degraded_count']}")
    print(f"report_json: {json_path}")
    print(f"report_md: {md_path}")
    for item in report["items"]:
        acceptance_summary = dict(item.get("acceptance_summary") or {})
        print(
            f"{item.get('strategy_id')}: replayed_days={item.get('replayed_days')} "
            f"filled={item.get('orders_filled')} realized={acceptance_summary.get('realized_trade_count')}/"
            f"{acceptance_summary.get('required_trade_count')} shortfall={acceptance_summary.get('sample_shortfall')} "
            f"blockers={len(list(acceptance_summary.get('blockers') or []))}"
        )
    if args.fail_on_shortfall and unresolved_shortfall_count > 0:
        return 2
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
    parser.add_argument("--target-realized-trades", type=int, default=DEFAULT_TARGET_REALIZED_TRADES, help="Production hard-gate target for closed round-trip trades.")
    parser.add_argument("--top-up-rounds", type=int, default=1, help="Repeat replay for strategies that still have a production sample shortfall.")
    parser.add_argument("--auto-remediate-low-sample", action="store_true", help="Rebuild signal cache and apply conservative runtime patches before replaying low-sample strategies.")
    parser.add_argument("--degrade-unresolved", action="store_true", help="Mark strategies that still miss production sample requirements as rejected after replay.")
    parser.add_argument("--degrade-only", action="store_true", help="Do not replay; degrade unresolved sample-gap strategies from the acceptance report.")
    parser.add_argument("--no-acceptance-delta", action="store_true", help="Do not capture before/after execution-audit acceptance deltas.")
    parser.add_argument("--fail-on-shortfall", action="store_true", help="Exit non-zero if any non-degraded strategy still has a production sample shortfall.")
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
