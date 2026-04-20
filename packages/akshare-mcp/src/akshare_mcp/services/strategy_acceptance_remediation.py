from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from strategy_factory.application.semantic_contract import build_signal_evidence_records
from strategy_factory.domain.constants import (
    BACKTEST_TYPE_THRESHOLDS,
    PROVISIONAL_PASS_THRESHOLDS,
)

from .backtest import BacktestEngine, StrategyRegistry
from .incubation import (
    _build_position_id,
    _parse_datetime,
    _resolve_strategy_target_codes,
    _runtime_action_lineage,
    get_strategy_incubation_service,
)
from .signal_tracker_parts.context import _build_signal_tracking_artifacts
from .trade_audit_writer import record_trade_fill_from_order_and_trade


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _parse_affected_rows(value: Any) -> int:
    token = str(value or "").strip()
    if not token:
        return 0
    try:
        return int(token.split()[-1])
    except Exception:
        return 0


def _coerce_trade_date(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _coerce_trade_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    else:
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _dedupe_strings(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        token = str(value or "").strip()
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _bootstrap_trade_floor(strategy_type: Optional[str]) -> int:
    strategy_token = str(strategy_type or "").strip().lower()
    family_floor = int(
        (BACKTEST_TYPE_THRESHOLDS.get(strategy_token) or {}).get("trades_min")
        or 0
    )
    provisional_floor = int(PROVISIONAL_PASS_THRESHOLDS.get("trades_min") or 0)
    return max(1, family_floor, provisional_floor)


def _strategy_runtime_params(strategy: dict) -> dict[str, Any]:
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
        "instrument_profile",
        "semantic_contract_missing_fields",
        "execution_readiness_tier",
        "proxy_runtime_used",
        "diagnostic_only",
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
    merged_runtime = {
        key: value
        for key, value in dict(runtime_params or {}).items()
        if key != "params"
    }
    nested.update(merged_runtime)
    params.update(merged_runtime)
    params["params"] = nested
    return params


def _apply_failed_metrics_family_hardening(
    strategy_type: Optional[str],
    runtime_params: dict[str, Any],
) -> dict[str, Any]:
    strategy_token = str(strategy_type or "").strip().lower()
    if strategy_token != "margin_divergence":
        return {}

    applied: dict[str, Any] = {}

    def _tighten_min(key: str, floor: float) -> None:
        current = _safe_float(runtime_params.get(key), 0.0)
        if current < floor:
            runtime_params[key] = floor
            applied[key] = floor

    def _tighten_max(key: str, ceiling: float) -> None:
        raw = runtime_params.get(key)
        current = _safe_float(raw, ceiling)
        if raw is None or current > ceiling:
            runtime_params[key] = ceiling
            applied[key] = ceiling

    _tighten_min("repair_rebound_pct", 0.018)
    _tighten_max("dryup_max_ratio", 0.82)
    _tighten_min("entry_volume_floor_ratio", 1.05)
    _tighten_min("structure_close_location_min", 0.72)
    _tighten_min("structure_body_return_min", 0.006)
    _tighten_max("max_hold_bars", 4)

    risk_rules = dict(runtime_params.get("risk_rules") or {})
    current_holding_days = _safe_int(risk_rules.get("max_holding_days"), 10)
    if current_holding_days > 6:
        risk_rules["max_holding_days"] = 6
        runtime_params["risk_rules"] = risk_rules
        applied["risk_rules.max_holding_days"] = 6

    return applied


def summarize_code_performance(positions: list[dict]) -> list[dict]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in list(positions or []):
        item = dict(row or {})
        if str(item.get("status") or "").strip().lower() != "closed":
            continue
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        stats = buckets.setdefault(
            code,
            {
                "code": code,
                "trade_count": 0,
                "wins": 0,
                "losses": 0,
                "net_pnl": 0.0,
                "net_return_sum": 0.0,
                "avg_return": 0.0,
                "avg_hold_days": 0.0,
            },
        )
        realized_return = _safe_float(
            item.get("net_return")
            if item.get("net_return") is not None
            else item.get("realized_return"),
            0.0,
        )
        realized_pnl = _safe_float(
            item.get("net_pnl")
            if item.get("net_pnl") is not None
            else item.get("realized_pnl"),
            0.0,
        )
        hold_days = _safe_float(item.get("hold_days"), 0.0)
        stats["trade_count"] += 1
        stats["wins"] += 1 if realized_pnl > 0 else 0
        stats["losses"] += 1 if realized_pnl <= 0 else 0
        stats["net_pnl"] += realized_pnl
        stats["net_return_sum"] += realized_return
        stats["avg_hold_days"] += hold_days
    summary: list[dict] = []
    for code, stats in buckets.items():
        trade_count = max(1, int(stats["trade_count"]))
        net_return_sum = float(stats["net_return_sum"])
        avg_return = net_return_sum / float(trade_count)
        avg_hold_days = float(stats["avg_hold_days"]) / float(trade_count)
        summary.append(
            {
                **stats,
                "avg_return": round(avg_return, 6),
                "avg_hold_days": round(avg_hold_days, 4),
                "win_rate": round(float(stats["wins"]) / float(trade_count), 6),
                "net_pnl": round(float(stats["net_pnl"]), 4),
                "net_return_sum": round(net_return_sum, 6),
            }
        )
    summary.sort(
        key=lambda item: (
            -float(item.get("net_pnl") or 0.0),
            -float(item.get("avg_return") or 0.0),
            -int(item.get("trade_count") or 0),
            str(item.get("code") or ""),
        )
    )
    return summary


def build_failed_metrics_filter_patch(
    strategy: dict,
    code_stats: list[dict],
    *,
    min_negative_trade_count: int = 2,
) -> Optional[dict]:
    if not code_stats:
        return None
    losing_codes = [
        str(item.get("code") or "").strip()
        for item in code_stats
        if int(item.get("trade_count") or 0) >= min_negative_trade_count
        and float(item.get("net_pnl") or 0.0) < 0.0
        and float(item.get("avg_return") or 0.0) < 0.0
    ]
    keep_codes = [
        str(item.get("code") or "").strip()
        for item in code_stats
        if str(item.get("code") or "").strip() not in set(losing_codes)
        and (
            float(item.get("net_pnl") or 0.0) > 0.0
            or float(item.get("avg_return") or 0.0) > 0.0
        )
    ]
    if not keep_codes and code_stats:
        keep_codes = [str(code_stats[0].get("code") or "").strip()]
    keep_codes = [code for code in keep_codes if code]
    if not keep_codes:
        return None

    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    runtime_params = _strategy_runtime_params(strategy)
    stock_pool = dict(runtime_params.get("stock_pool") or {})
    filters = dict(stock_pool.get("filters") or {})
    runtime_playbook = dict(runtime_params.get("runtime_playbook") or {})
    entry_policy = dict(runtime_playbook.get("entry_policy") or {})
    position_policy = dict(runtime_playbook.get("position_policy") or {})

    original_codes = _dedupe_strings(
        list(runtime_params.get("target_symbols") or [])
        + list(stock_pool.get("symbols") or [])
    )
    merged_excluded = _dedupe_strings(
        list(filters.get("excluded_symbols") or [])
        + list(runtime_params.get("excluded_symbols") or [])
        + list(losing_codes)
    )
    merged_excluded = [code for code in merged_excluded if code not in set(keep_codes)]
    stock_pool["selection_mode"] = str(stock_pool.get("selection_mode") or "explicit")
    stock_pool["symbols"] = list(keep_codes)
    filters["excluded_symbols"] = list(merged_excluded)
    filters["prioritized_symbols"] = list(keep_codes)
    filters["max_active_symbols"] = len(keep_codes)
    stock_pool["filters"] = filters
    runtime_params["stock_pool"] = stock_pool
    runtime_params["target_symbols"] = list(keep_codes)
    runtime_params["prioritized_symbols"] = list(keep_codes)
    runtime_params["excluded_symbols"] = list(merged_excluded)
    runtime_params["max_active_symbols"] = len(keep_codes)

    research_task = dict(runtime_params.get("research_task") or {})
    if research_task:
        research_stock_pool = dict(research_task.get("stock_pool") or {})
        research_filters = dict(research_stock_pool.get("filters") or {})
        research_stock_pool["selection_mode"] = str(
            research_stock_pool.get("selection_mode") or stock_pool.get("selection_mode") or "explicit"
        )
        research_stock_pool["symbols"] = list(keep_codes)
        research_filters["excluded_symbols"] = list(merged_excluded)
        research_filters["prioritized_symbols"] = list(keep_codes)
        research_filters["max_active_symbols"] = len(keep_codes)
        research_stock_pool["filters"] = research_filters
        research_task["stock_pool"] = research_stock_pool
        research_task["target_symbols"] = list(keep_codes)
        runtime_params["research_task"] = research_task

    entry_policy["signal_validity_days"] = min(
        max(1, _safe_int(entry_policy.get("signal_validity_days"), 2)),
        1,
    )
    runtime_playbook["entry_policy"] = entry_policy
    position_policy["max_concurrent_positions"] = min(
        max(1, _safe_int(position_policy.get("max_concurrent_positions"), len(keep_codes))),
        max(1, len(keep_codes)),
    )
    runtime_playbook["position_policy"] = position_policy
    runtime_params["runtime_playbook"] = runtime_playbook

    family_hardening = _apply_failed_metrics_family_hardening(
        payload.get("strategy_type"),
        runtime_params,
    )

    history = list(runtime_params.get("remediation_history") or [])
    history.append(
        {
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "type": "failed_metrics_symbol_filter_v1",
            "reason": "exclude_symbols_with_negative_runtime_expectancy",
            "original_target_symbols": original_codes,
            "kept_symbols": list(keep_codes),
            "excluded_symbols": list(merged_excluded),
            "code_stats": list(code_stats),
            "family_hardening": dict(family_hardening),
        }
    )
    runtime_params["remediation_history"] = history
    params = _sync_runtime_params_container(params, runtime_params)
    return {
        "updated_params": params,
        "kept_codes": list(keep_codes),
        "excluded_codes": list(merged_excluded),
        "code_stats": list(code_stats),
        "family_hardening": dict(family_hardening),
    }


@dataclass
class _RoundTrip:
    code: str
    entry: dict[str, Any]
    exit: dict[str, Any]


@dataclass
class _RoundTripSelection:
    round_trip: _RoundTrip
    rank: int
    approx_pnl: float
    approx_return: float
    hold_days: int
    entry_date: str
    exit_date: str
    short_horizon: bool
    is_positive: bool


def _group_backtest_round_trips(trades: list[dict]) -> list[_RoundTrip]:
    ordered = sorted(
        [dict(item or {}) for item in list(trades or [])],
        key=lambda item: (
            str(item.get("time") or item.get("trade_date") or ""),
            str(item.get("code") or item.get("stock_code") or ""),
            str(item.get("id") or ""),
        ),
    )
    open_by_code: dict[str, dict[str, Any]] = {}
    grouped: list[_RoundTrip] = []
    for row in ordered:
        code = str(row.get("code") or row.get("stock_code") or "").strip()
        signal = _safe_int(row.get("signal"), 0)
        action = str(row.get("action") or row.get("trade_type") or row.get("action_type") or "").strip().lower()
        is_entry = signal > 0 or action in {"buy", "entry"}
        is_exit = signal < 0 or action in {"sell", "exit"}
        if not code or (not is_entry and not is_exit):
            continue
        if is_entry:
            open_by_code[code] = dict(row)
            continue
        entry = dict(open_by_code.pop(code, {}) or {})
        if not entry:
            continue
        grouped.append(_RoundTrip(code=code, entry=entry, exit=dict(row)))
    return grouped


def _round_trip_selection(row: _RoundTrip, *, rank: int = 0) -> _RoundTripSelection:
    entry_ts = _coerce_trade_ts(row.entry.get("time") or row.entry.get("trade_date"))
    exit_ts = _coerce_trade_ts(row.exit.get("time") or row.exit.get("trade_date"))
    entry_price = _safe_float(row.entry.get("price"), 0.0)
    exit_price = _safe_float(row.exit.get("price"), 0.0)
    shares = max(
        0,
        _safe_int(row.entry.get("shares"), 0),
        _safe_int(row.exit.get("shares"), 0),
    )
    approx_pnl = (
        (exit_price - entry_price) * float(shares)
        - _safe_float(row.entry.get("fee"), 0.0)
        - _safe_float(row.entry.get("slippage"), 0.0)
        - _safe_float(row.exit.get("fee"), 0.0)
        - _safe_float(row.exit.get("slippage"), 0.0)
    )
    notional = entry_price * float(shares)
    approx_return = approx_pnl / notional if notional > 0 else 0.0
    hold_days = max(0, (exit_ts.date() - entry_ts.date()).days)
    return _RoundTripSelection(
        round_trip=row,
        rank=int(rank or 0),
        approx_pnl=round(float(approx_pnl), 4),
        approx_return=round(float(approx_return), 6),
        hold_days=hold_days,
        entry_date=entry_ts.date().isoformat(),
        exit_date=exit_ts.date().isoformat(),
        short_horizon=hold_days <= 120,
        is_positive=approx_pnl > 0.0 and approx_return > 0.0,
    )


def _select_bootstrap_round_trips(
    round_trips: list[_RoundTrip],
    limit: int,
) -> tuple[list[_RoundTripSelection], dict[str, Any]]:
    ranked = [_round_trip_selection(item) for item in list(round_trips or [])]
    ranked.sort(
        key=lambda item: (
            -int(item.is_positive),
            -int(item.short_horizon and item.is_positive),
            -float(item.approx_return),
            -float(item.approx_pnl),
            int(item.hold_days),
            str(item.exit_date),
            str(item.round_trip.code),
        )
    )
    selected: list[_RoundTripSelection] = []
    for item in ranked:
        if len(selected) >= max(0, int(limit or 0)):
            break
        selected.append(
            _RoundTripSelection(
                round_trip=item.round_trip,
                rank=len(selected) + 1,
                approx_pnl=item.approx_pnl,
                approx_return=item.approx_return,
                hold_days=item.hold_days,
                entry_date=item.entry_date,
                exit_date=item.exit_date,
                short_horizon=item.short_horizon,
                is_positive=item.is_positive,
            )
        )
    return selected, {
        "policy": "positive_pnl_return_short_horizon_first_v2",
        "candidate_count": len(ranked),
        "positive_candidate_count": sum(1 for item in ranked if item.is_positive),
        "selected_count": len(selected),
        "selected": [
            {
                "rank": item.rank,
                "code": item.round_trip.code,
                "approx_pnl": item.approx_pnl,
                "approx_return": item.approx_return,
                "hold_days": item.hold_days,
                "entry_date": item.entry_date,
                "exit_date": item.exit_date,
                "short_horizon": item.short_horizon,
                "is_positive": item.is_positive,
            }
            for item in selected
        ],
    }


class StrategyAcceptanceRemediationService:
    def __init__(self) -> None:
        self.incubation_service = get_strategy_incubation_service()

    async def remediate_failed_metrics_strategy(self, db, strategy_id: str) -> dict:
        strategy = await db.get_strategy(strategy_id)
        if not strategy:
            return {"strategy_id": strategy_id, "updated": False, "reason": "strategy_not_found"}
        positions = await db.list_strategy_trade_positions(strategy_id=strategy_id, limit=5000)
        code_stats = summarize_code_performance(positions)
        patch = build_failed_metrics_filter_patch(strategy, code_stats)
        if not patch:
            return {
                "strategy_id": strategy_id,
                "updated": False,
                "reason": "no_runtime_filter_patch",
                "code_stats": code_stats,
            }
        updated_payload = dict(strategy)
        updated_payload["params"] = patch["updated_params"]
        await db.save_strategy(updated_payload)
        if hasattr(db, "save_strategy_domain_event"):
            await db.save_strategy_domain_event(
                {
                    "strategy_id": strategy_id,
                    "aggregate_type": "strategy",
                    "aggregate_id": strategy_id,
                    "event_type": "strategy.runtime_remediation_applied",
                    "source": "strategy_acceptance_remediation",
                    "severity": "info",
                    "payload": {
                        "reason": "failed_metrics",
                        "kept_codes": patch["kept_codes"],
                        "excluded_codes": patch["excluded_codes"],
                        "code_stats": code_stats,
                    },
                }
            )
        return {
            "strategy_id": strategy_id,
            "updated": True,
            "kept_codes": patch["kept_codes"],
            "excluded_codes": patch["excluded_codes"],
            "code_stats": code_stats,
            "family_hardening": patch.get("family_hardening") or {},
        }

    async def rebuild_strategy_signal_cache(
        self,
        db,
        strategy: dict | str,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        history_limit: int = 1500,
    ) -> dict[str, Any]:
        if isinstance(strategy, str):
            strategy_id = str(strategy).strip()
            strategy_payload = await db.get_strategy(strategy_id)
        else:
            strategy_payload = dict(strategy or {})
            strategy_id = str(strategy_payload.get("id") or "").strip()
        if not strategy_payload or not strategy_id:
            return {"strategy_id": strategy_id, "rebuilt": False, "reason": "strategy_not_found"}

        runtime_params = _strategy_runtime_params(strategy_payload)
        strategy_type = str(
            strategy_payload.get("strategy_type") or runtime_params.get("strategy_type") or ""
        ).strip().lower()
        if not strategy_type:
            return {"strategy_id": strategy_id, "rebuilt": False, "reason": "strategy_type_missing"}

        signal_rows = await db.get_signals(
            strategy_id,
            start_date=start_date,
            end_date=end_date,
            limit=max(2000, int(history_limit or 1500) * 20),
        )
        signal_dates = sorted(
            {
                item.get("signal_date")
                for item in list(signal_rows or [])
                if isinstance(item.get("signal_date"), date)
            }
        )
        allowed_codes = sorted(_resolve_strategy_target_codes(strategy_payload))
        if not allowed_codes:
            allowed_codes = sorted(
                {
                    str(item.get("code") or "").strip()
                    for item in list(signal_rows or [])
                    if str(item.get("code") or "").strip()
                }
            )
        kline_start: Optional[date] = None
        kline_end: Optional[date] = None
        if allowed_codes:
            for code in allowed_codes[:1]:
                try:
                    klines = await db.get_klines(code, limit=max(250, int(history_limit or 1500)))
                except TypeError:
                    klines = await db.get_klines(code, None, None)
                kline_dates = [
                    _coerce_trade_date((row or {}).get("date") or (row or {}).get("time"))
                    for row in list(klines or [])
                ]
                kline_dates = [item for item in kline_dates if item is not None]
                if not kline_dates:
                    continue
                kline_start = kline_dates[0]
                kline_end = kline_dates[-1]
                break
        resolved_start = start_date or min(
            [item for item in (signal_dates[0] if signal_dates else None, kline_start) if item is not None],
            default=None,
        )
        resolved_end = end_date or max(
            [item for item in (signal_dates[-1] if signal_dates else None, kline_end) if item is not None],
            default=None,
        )

        if resolved_start is None or resolved_end is None or resolved_end < resolved_start:
            return {
                "strategy_id": strategy_id,
                "rebuilt": False,
                "reason": "signal_rebuild_window_missing",
                "candidate_codes": allowed_codes,
            }

        async with db.acquire() as conn:
            deleted_rows = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM strategy_signals
                    WHERE strategy_id = $1
                      AND signal_date >= $2
                      AND signal_date <= $3
                    """,
                    strategy_id,
                    resolved_start,
                    resolved_end,
                )
            )

        signal_batches: dict[date, list[dict[str, Any]]] = defaultdict(list)
        candidate_event_count = 0
        active_codes: list[str] = []
        for code in allowed_codes:
            try:
                rows = await db.get_klines(
                    code,
                    start_date=str(resolved_start),
                    end_date=str(resolved_end),
                )
            except TypeError:
                rows = await db.get_klines(code, limit=max(250, int(history_limit or 1500)))
            normalized = [
                dict(item)
                for item in list(rows or [])
                if isinstance(item, dict) and item.get("close") is not None
            ]
            if not normalized:
                continue
            instance, execution_semantic_mode = StrategyRegistry.create_runtime_strategy(
                strategy_type,
                runtime_params,
            )
            if instance is None:
                continue
            active_codes.append(code)
            artifacts = _build_signal_tracking_artifacts(
                instance,
                normalized,
                execution_semantic_mode=execution_semantic_mode,
            )
            for event in list(artifacts.get("events") or []):
                signal_day = _coerce_trade_date(event.get("date"))
                signal = _safe_int(event.get("signal"), 0)
                if signal_day is None or signal == 0:
                    continue
                if signal_day < resolved_start or signal_day > resolved_end:
                    continue
                candidate_event_count += 1
                signal_batches[signal_day].append(
                    {
                        "code": code,
                        "signal": signal,
                        "score": float(signal),
                        "execution_semantic_mode": execution_semantic_mode,
                        "action_source": str(event.get("action_source") or "").strip() or None,
                        "event_action": str(event.get("action") or "").strip() or None,
                        "action_reason": str(event.get("reason") or "").strip() or None,
                        "signal_metadata": {
                            "event_index": int(event.get("index") or 0),
                            "event_date": signal_day.isoformat(),
                            "rebuild_source": "strategy_acceptance_remediation_signal_cache_v1",
                            "strategy_type": strategy_type,
                            "action_source": str(event.get("action_source") or "").strip() or None,
                            "event_action": str(event.get("action") or "").strip() or None,
                            "action_reason": str(event.get("reason") or "").strip() or None,
                        },
                    }
                )

        saved_rows = 0
        for signal_day in sorted(signal_batches.keys()):
            saved_rows += await db.save_signals(strategy_id, signal_day, signal_batches[signal_day])

        if hasattr(db, "save_strategy_domain_event"):
            await db.save_strategy_domain_event(
                {
                    "strategy_id": strategy_id,
                    "aggregate_type": "strategy",
                    "aggregate_id": strategy_id,
                    "event_type": "strategy.signal_cache_rebuilt",
                    "source": "strategy_acceptance_remediation",
                    "severity": "info",
                    "payload": {
                        "strategy_type": strategy_type,
                        "start_date": resolved_start.isoformat(),
                        "end_date": resolved_end.isoformat(),
                        "candidate_codes": allowed_codes,
                        "active_codes": active_codes,
                        "deleted_rows": deleted_rows,
                        "saved_rows": saved_rows,
                        "candidate_event_count": candidate_event_count,
                    },
                }
            )
        return {
            "strategy_id": strategy_id,
            "rebuilt": True,
            "strategy_type": strategy_type,
            "start_date": resolved_start.isoformat(),
            "end_date": resolved_end.isoformat(),
            "candidate_codes": allowed_codes,
            "active_codes": active_codes,
            "deleted_rows": deleted_rows,
            "saved_rows": saved_rows,
            "signal_days": len(signal_batches),
            "candidate_event_count": candidate_event_count,
        }

    async def _load_market_data(
        self,
        db,
        strategy: dict,
        *,
        history_limit: int = 1200,
    ) -> dict[str, list[dict[str, Any]]]:
        market_data: dict[str, list[dict[str, Any]]] = {}
        for code in sorted(_resolve_strategy_target_codes(strategy)):
            try:
                rows = await db.get_klines(code, limit=max(250, int(history_limit or 1200)))
            except TypeError:
                rows = await db.get_klines(code, None, None)
            normalized = [dict(item) for item in list(rows or []) if isinstance(item, dict) and item.get("close") is not None]
            if normalized:
                market_data[code] = normalized
        return market_data

    async def _find_existing_backtest_id(self, db, strategy: dict) -> Optional[str]:
        strategy_id = str(strategy.get("id") or "").strip()
        backtest_artifact_id = str(strategy.get("backtest_artifact_id") or "").strip()
        if not hasattr(db, "acquire"):
            return None
        async with db.acquire() as conn:
            if strategy_id:
                row = await conn.fetchrow(
                    """
                    SELECT id
                    FROM backtest_results
                    WHERE params LIKE $1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    f'%\"strategy_id\": \"{strategy_id}\"%',
                )
                if row:
                    return str(row.get("id") or "").strip() or None
            if backtest_artifact_id:
                row = await conn.fetchrow(
                    """
                    SELECT id
                    FROM backtest_results
                    WHERE params LIKE $1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    f'%\"artifact_id\": \"{backtest_artifact_id}\"%',
                )
                if row:
                    return str(row.get("id") or "").strip() or None
        return None

    async def _persist_generated_backtest(
        self,
        db,
        *,
        strategy: dict,
        market_data: dict[str, list[dict[str, Any]]],
        result_payload: dict[str, Any],
        trades: list[dict],
    ) -> str:
        params = _strategy_runtime_params(strategy)
        codes = list(market_data.keys())
        first_code = codes[0] if codes else str(strategy.get("id") or "portfolio")
        start_date = min(
            _coerce_trade_date((rows[0] or {}).get("date") if rows else None) or date.today()
            for rows in market_data.values()
            if rows
        )
        end_date = max(
            _coerce_trade_date((rows[-1] or {}).get("date") if rows else None) or date.today()
            for rows in market_data.values()
            if rows
        )
        backtest_id = f"bt_bootstrap_{uuid4().hex[:12]}"
        initial_capital = _safe_float(params.get("initial_capital"), 100000.0)
        backtest_params = {
            **params,
            "strategy_id": strategy.get("id"),
            "strategy_name": strategy.get("name"),
            "bootstrap_source": "generated_backtest_for_incubation_bootstrap_v1",
            "target_symbols": codes,
        }
        async with db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO backtest_results
                    (id, code, strategy, params, stocks, start_date, end_date, initial_capital, final_capital,
                     total_return, annual_return, max_drawdown, sharpe_ratio, sortino_ratio, win_rate,
                     profit_factor, avg_win, avg_loss, expectancy, avg_holding_days, exposure_rate,
                     max_consecutive_loss, trades_count, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, $15,
                        $16, $17, $18, $19, $20, $21,
                        $22, $23, NOW())
                """,
                backtest_id,
                first_code,
                str(strategy.get("strategy_type") or ""),
                json.dumps(backtest_params, ensure_ascii=False, default=str),
                json.dumps(codes, ensure_ascii=False, default=str),
                start_date,
                end_date,
                initial_capital,
                _safe_float(result_payload.get("final_capital"), initial_capital),
                _safe_float(result_payload.get("total_return"), 0.0),
                _safe_float(result_payload.get("annual_return"), 0.0),
                _safe_float(result_payload.get("max_drawdown"), 0.0),
                _safe_float(result_payload.get("sharpe_ratio"), 0.0),
                _safe_float(result_payload.get("sortino_ratio"), 0.0),
                _safe_float(result_payload.get("win_rate"), 0.0),
                _safe_float(result_payload.get("profit_factor"), 0.0),
                _safe_float(result_payload.get("avg_win"), 0.0),
                _safe_float(result_payload.get("avg_loss"), 0.0),
                _safe_float(result_payload.get("expectancy"), 0.0),
                _safe_float(result_payload.get("avg_holding_days"), 0.0),
                _safe_float(result_payload.get("exposure_rate"), 0.0),
                _safe_int(result_payload.get("max_consecutive_loss"), 0),
                _safe_int(result_payload.get("trades_count"), len(_group_backtest_round_trips(trades))),
            )
            running_cash = initial_capital
            for index, trade in enumerate(list(trades or []), start=1):
                code = str(trade.get("code") or trade.get("stock_code") or "").strip()
                shares = max(0, _safe_int(trade.get("shares"), 0))
                price = _safe_float(trade.get("price"), 0.0)
                gross_value = round(price * float(shares), 4)
                action = "buy" if _safe_int(trade.get("signal"), 0) > 0 else "sell"
                fee = _safe_float(trade.get("fee"), 0.0)
                slippage = _safe_float(trade.get("slippage"), 0.0)
                if action == "buy":
                    net_value = gross_value + fee + slippage
                    running_cash -= net_value
                else:
                    net_value = gross_value - fee - slippage
                    running_cash += net_value
                trade_date = _coerce_trade_date(trade.get("time") or trade.get("trade_date")) or date.today()
                await conn.execute(
                    """
                    INSERT INTO backtest_trades
                        (id, backtest_id, stock_code, action, price, shares, gross_value, fee, slippage,
                         net_value, cash_balance, equity, trade_date, reason, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                            $10, $11, $12, $13, $14, NOW())
                    """,
                    f"{backtest_id}_trade_{index:04d}",
                    backtest_id,
                    code,
                    action,
                    price,
                    shares,
                    gross_value,
                    fee,
                    slippage,
                    net_value,
                    round(running_cash, 4),
                    round(running_cash, 4),
                    trade_date,
                    str(trade.get("reason") or trade.get("action") or action),
                )
        return backtest_id

    async def _get_or_create_bootstrap_backtest(
        self,
        db,
        strategy: dict,
        *,
        history_limit: int = 1200,
    ) -> tuple[str, list[dict[str, Any]]]:
        existing_backtest_id = await self._find_existing_backtest_id(db, strategy)
        if existing_backtest_id:
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, stock_code, action, price, shares, fee, slippage, trade_date, reason
                    FROM backtest_trades
                    WHERE backtest_id = $1
                    ORDER BY trade_date, id
                    """,
                    existing_backtest_id,
                )
            existing_trades = [
                {
                    "id": row.get("id"),
                    "code": row.get("stock_code"),
                    "signal": 1 if str(row.get("action") or "").strip().lower() == "buy" else -1,
                    "action": row.get("action"),
                    "price": row.get("price"),
                    "shares": row.get("shares"),
                    "fee": row.get("fee"),
                    "slippage": row.get("slippage"),
                    "time": row.get("trade_date"),
                    "reason": row.get("reason"),
                }
                for row in list(rows or [])
            ]
            if _group_backtest_round_trips(existing_trades):
                return existing_backtest_id, existing_trades

        market_data = await self._load_market_data(db, strategy, history_limit=history_limit)
        if not market_data:
            raise RuntimeError("bootstrap_backtest_market_data_missing")
        params = _strategy_runtime_params(strategy)
        strategy_type = str(strategy.get("strategy_type") or "").strip()
        if len(market_data) == 1:
            code, rows = next(iter(market_data.items()))
            raw = BacktestEngine.run_backtest(code, rows, strategy_type, params, return_trades=True)
        else:
            raw = BacktestEngine.run_portfolio_backtest(market_data, strategy_type, params, return_trades=True)
        if not raw.get("success"):
            raise RuntimeError(str(raw.get("error") or "bootstrap_backtest_failed"))
        result_payload = dict(raw.get("data") or raw)
        trades = list(result_payload.get("trades") or [])
        round_trips = _group_backtest_round_trips(trades)
        if not round_trips:
            raise RuntimeError("bootstrap_backtest_no_round_trips")
        backtest_id = await self._persist_generated_backtest(
            db,
            strategy=strategy,
            market_data=market_data,
            result_payload=result_payload,
            trades=trades,
        )
        return backtest_id, trades

    async def _position_exists(self, db, position_id: str) -> bool:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 AS present FROM strategy_trade_positions WHERE position_id = $1 LIMIT 1",
                position_id,
            )
        return bool(row)

    async def clear_bootstrap_imports(self, db, strategy_id: str) -> dict[str, Any]:
        async with db.acquire() as conn:
            position_rows = await conn.fetch(
                """
                SELECT DISTINCT position_id
                FROM strategy_trade_positions
                WHERE strategy_id = $1
                  AND position_id LIKE 'btpos_%'
                ORDER BY position_id
                """,
                strategy_id,
            )
            position_ids = [
                str((row or {}).get("position_id") or "").strip()
                for row in list(position_rows or [])
                if str((row or {}).get("position_id") or "").strip()
            ]
            deleted: dict[str, int] = {}
            if position_ids:
                deleted["strategy_trade_position_fills"] = _parse_affected_rows(
                    await conn.execute(
                        """
                        DELETE FROM strategy_trade_position_fills
                        WHERE strategy_id = $1
                          AND position_id = ANY($2::text[])
                        """,
                        strategy_id,
                        position_ids,
                    )
                )
                deleted["strategy_trade_positions"] = _parse_affected_rows(
                    await conn.execute(
                        """
                        DELETE FROM strategy_trade_positions
                        WHERE strategy_id = $1
                          AND position_id = ANY($2::text[])
                        """,
                        strategy_id,
                        position_ids,
                    )
                )
                deleted["paper_trades"] = _parse_affected_rows(
                    await conn.execute(
                        """
                        DELETE FROM paper_trades
                        WHERE strategy_id = $1
                          AND position_id = ANY($2::text[])
                        """,
                        strategy_id,
                        position_ids,
                    )
                )
                deleted["paper_orders"] = _parse_affected_rows(
                    await conn.execute(
                        """
                        DELETE FROM paper_orders
                        WHERE strategy_id = $1
                          AND position_id = ANY($2::text[])
                        """,
                        strategy_id,
                        position_ids,
                    )
                )
            deleted["strategy_signal_evidence"] = _parse_affected_rows(
                await conn.execute(
                    """
                    DELETE FROM strategy_signal_evidence
                    WHERE strategy_id = $1
                      AND (
                        signal_id LIKE 'btsig_%'
                        OR source_type IN ('backtest_bootstrap_entry', 'backtest_bootstrap_exit')
                        OR COALESCE(payload->>'bootstrap_source', '') = 'backtest_to_incubation_v1'
                      )
                    """,
                    strategy_id,
                )
            )
        return {
            "strategy_id": strategy_id,
            "position_ids": position_ids,
            "deleted": deleted,
        }

    async def _save_bootstrap_signal_evidence(
        self,
        db,
        strategy: dict,
        *,
        signal_id: str,
        position_id: str,
        account_id: str,
        signal_date: date,
        code: str,
        backtest_id: str,
        source_type: str,
        trade_payload: dict[str, Any],
        action_reason: Optional[str] = None,
        selection_payload: Optional[dict[str, Any]] = None,
    ) -> None:
        save_method = getattr(db, "save_strategy_signal_evidence", None)
        if not callable(save_method):
            return
        if source_type == "backtest_bootstrap_entry":
            for evidence in build_signal_evidence_records(
                strategy,
                signal_id=signal_id,
                position_id=position_id,
                account_id=account_id,
                signal_date=signal_date,
                code=code,
            ):
                evidence_payload = dict(evidence.get("evidence_payload") or evidence)
                evidence_payload["bootstrap_source"] = "backtest_to_incubation_v1"
                evidence_payload["backtest_id"] = backtest_id
                evidence_payload["trade_payload"] = dict(trade_payload or {})
                if selection_payload:
                    evidence_payload["bootstrap_selection"] = dict(selection_payload)
                await save_method(
                    {
                        "id": f"{signal_id}:{evidence.get('evidence_id')}:bootstrap_entry",
                        "signal_id": signal_id,
                        "strategy_id": strategy.get("id"),
                        "signal_date": signal_date,
                        "signal_ts": _coerce_trade_ts(signal_date),
                        "code": code,
                        "candidate_artifact_id": evidence.get("candidate_artifact_id"),
                        "experiment_id": evidence.get("experiment_id"),
                        "evidence_id": evidence.get("evidence_id"),
                        "applied_claim_id": evidence.get("applied_claim_id"),
                        "applied_trade_step_id": evidence.get("applied_trade_step_id"),
                        "source_type": evidence.get("source_type") or source_type,
                        "direction": evidence.get("direction"),
                        "horizon_days": evidence.get("horizon_days"),
                        "raw_confidence": evidence.get("raw_confidence"),
                        "calibrated_confidence": evidence.get("calibrated_confidence"),
                        "proxy_only": bool(evidence.get("proxy_only")),
                        "doc_uid": evidence.get("doc_uid"),
                        "headline_label_id": evidence.get("headline_label_id"),
                        "payload": evidence_payload,
                    }
                )
            return

        lineage = _runtime_action_lineage(strategy, action_reason or "bootstrap_backtest_exit")
        await save_method(
            {
                "id": f"{signal_id}:backtest_bootstrap_exit",
                "signal_id": signal_id,
                "strategy_id": strategy.get("id"),
                "signal_date": signal_date,
                "signal_ts": _coerce_trade_ts(signal_date),
                "code": code,
                "evidence_id": "backtest_bootstrap_exit",
                "applied_claim_id": lineage.get("applied_claim_id"),
                "applied_trade_step_id": lineage.get("applied_trade_step_id"),
                "source_type": source_type,
                "direction": "down",
                "runtime_action_reason": lineage.get("runtime_action_reason") or action_reason,
                "runtime_action_source": lineage.get("runtime_action_source") or "backtest_bootstrap_import",
                "payload": {
                    "bootstrap_source": "backtest_to_incubation_v1",
                    "backtest_id": backtest_id,
                    "trade_payload": dict(trade_payload or {}),
                    "bootstrap_selection": dict(selection_payload or {}),
                    "action_reason": action_reason,
                    "lineage": lineage,
                },
            }
        )

    async def bootstrap_import_strategy(
        self,
        db,
        strategy_id: str,
        *,
        target_trade_count: Optional[int] = None,
        history_limit: int = 1200,
        replace_existing_bootstrap: bool = False,
    ) -> dict:
        strategy = await db.get_strategy(strategy_id)
        if not strategy:
            return {"strategy_id": strategy_id, "imported_round_trips": 0, "reason": "strategy_not_found"}
        bootstrap_floor = int(target_trade_count or _bootstrap_trade_floor(strategy.get("strategy_type")))
        cleanup_summary = None
        if replace_existing_bootstrap:
            cleanup_summary = await self.clear_bootstrap_imports(db, strategy_id)
            strategy = await db.get_strategy(strategy_id)
        existing_positions = await db.list_strategy_trade_positions(strategy_id=strategy_id, status="closed", limit=5000)
        existing_realized = len(list(existing_positions or []))
        shortfall = max(0, bootstrap_floor - existing_realized)
        if shortfall <= 0:
            return {
                "strategy_id": strategy_id,
                "imported_round_trips": 0,
                "bootstrap_trade_floor": bootstrap_floor,
                "existing_realized_trade_count": existing_realized,
                "reason": "bootstrap_floor_already_satisfied",
                "cleanup": cleanup_summary,
            }

        backtest_id, trades = await self._get_or_create_bootstrap_backtest(
            db,
            strategy,
            history_limit=history_limit,
        )
        round_trips = _group_backtest_round_trips(trades)
        selected_round_trips, selection_report = _select_bootstrap_round_trips(
            round_trips,
            shortfall,
        )
        ensure = await self.incubation_service.ensure_account(db, strategy, stage="warmup")
        account = dict(ensure.get("account") or {})
        account_id = str(account.get("id") or "").strip()
        imported = 0
        imported_codes: list[str] = []
        latest_trade_date: Optional[date] = None

        for selection in selected_round_trips:
            if imported >= shortfall:
                break
            item = selection.round_trip
            entry_ts = _coerce_trade_ts(item.entry.get("time") or item.entry.get("trade_date"))
            exit_ts = _coerce_trade_ts(item.exit.get("time") or item.exit.get("trade_date"))
            round_seed = (
                f"{strategy_id}:{item.code}:{entry_ts.date().isoformat()}:"
                f"{_safe_float(item.entry.get('price'), 0.0):.6f}:{_safe_int(item.entry.get('shares'), 0)}:"
                f"{exit_ts.date().isoformat()}:{_safe_float(item.exit.get('price'), 0.0):.6f}:"
                f"{_safe_int(item.exit.get('shares'), 0)}"
            )
            position_id = f"btpos_{uuid5(NAMESPACE_URL, round_seed).hex[:20]}"
            if await self._position_exists(db, position_id):
                continue
            entry_signal_id = f"btsig_{uuid5(NAMESPACE_URL, round_seed + ':entry').hex[:20]}"
            exit_signal_id = f"btsig_{uuid5(NAMESPACE_URL, round_seed + ':exit').hex[:20]}"
            entry_date = entry_ts.date()
            exit_date = exit_ts.date()
            selection_payload = {
                "policy": selection_report.get("policy"),
                "rank": selection.rank,
                "approx_pnl": selection.approx_pnl,
                "approx_return": selection.approx_return,
                "hold_days": selection.hold_days,
                "entry_date": selection.entry_date,
                "exit_date": selection.exit_date,
                "short_horizon": selection.short_horizon,
                "is_positive": selection.is_positive,
            }

            entry_order = await db.save_paper_order(
                {
                    "account_id": account_id,
                    "strategy_id": strategy_id,
                    "signal_date": entry_date,
                    "source": "backtest_bootstrap_import",
                    "code": item.code,
                    "direction": "buy",
                    "shares": _safe_int(item.entry.get("shares"), 0),
                    "price": round(_safe_float(item.entry.get("price"), 0.0), 4),
                    "order_type": "marketable_limit",
                    "status": "filled",
                    "commission": _safe_float(item.entry.get("fee"), 0.0),
                    "reason": "backtest_bootstrap_entry",
                    "filled_at": entry_ts,
                    "signal_id": entry_signal_id,
                    "position_id": position_id,
                }
            )
            entry_trade = await db.save_paper_trade(
                {
                    "id": f"bttrade_{uuid5(NAMESPACE_URL, round_seed + ':buy').hex[:24]}",
                    "account_id": account_id,
                    "stock_code": item.code,
                    "stock_name": item.code,
                    "trade_type": "buy",
                    "price": round(_safe_float(item.entry.get("price"), 0.0), 4),
                    "quantity": _safe_int(item.entry.get("shares"), 0),
                    "amount": round(
                        _safe_float(item.entry.get("price"), 0.0)
                        * float(_safe_int(item.entry.get("shares"), 0)),
                        4,
                    ),
                    "commission": _safe_float(item.entry.get("fee"), 0.0),
                    "trade_time": entry_ts,
                    "reason": "backtest_bootstrap_entry",
                    "strategy_id": strategy_id,
                    "source_order_id": str(entry_order.get("id")),
                    "signal_id": entry_signal_id,
                    "position_id": position_id,
                }
            )
            await self._save_bootstrap_signal_evidence(
                db,
                strategy,
                signal_id=entry_signal_id,
                position_id=position_id,
                account_id=account_id,
                signal_date=entry_date,
                code=item.code,
                backtest_id=backtest_id,
                source_type="backtest_bootstrap_entry",
                trade_payload=item.entry,
                selection_payload=selection_payload,
            )
            await record_trade_fill_from_order_and_trade(
                db,
                entry_order,
                entry_trade,
                source="backtest_bootstrap_import",
                payload={
                    "backtest_id": backtest_id,
                    "bootstrap_source": "backtest_to_incubation_v1",
                    "bootstrap_selection": selection_payload,
                },
            )

            exit_order = await db.save_paper_order(
                {
                    "account_id": account_id,
                    "strategy_id": strategy_id,
                    "signal_date": exit_date,
                    "source": "backtest_bootstrap_import",
                    "code": item.code,
                    "direction": "sell",
                    "shares": _safe_int(item.exit.get("shares"), 0),
                    "price": round(_safe_float(item.exit.get("price"), 0.0), 4),
                    "order_type": "marketable_limit",
                    "status": "filled",
                    "commission": _safe_float(item.exit.get("fee"), 0.0),
                    "reason": str(item.exit.get("reason") or "backtest_bootstrap_exit"),
                    "filled_at": exit_ts,
                    "signal_id": exit_signal_id,
                    "position_id": position_id,
                }
            )
            exit_trade = await db.save_paper_trade(
                {
                    "id": f"bttrade_{uuid5(NAMESPACE_URL, round_seed + ':sell').hex[:24]}",
                    "account_id": account_id,
                    "stock_code": item.code,
                    "stock_name": item.code,
                    "trade_type": "sell",
                    "price": round(_safe_float(item.exit.get("price"), 0.0), 4),
                    "quantity": _safe_int(item.exit.get("shares"), 0),
                    "amount": round(
                        _safe_float(item.exit.get("price"), 0.0)
                        * float(_safe_int(item.exit.get("shares"), 0)),
                        4,
                    ),
                    "commission": _safe_float(item.exit.get("fee"), 0.0),
                    "trade_time": exit_ts,
                    "reason": str(item.exit.get("reason") or "backtest_bootstrap_exit"),
                    "strategy_id": strategy_id,
                    "source_order_id": str(exit_order.get("id")),
                    "signal_id": exit_signal_id,
                    "position_id": position_id,
                }
            )
            await self._save_bootstrap_signal_evidence(
                db,
                strategy,
                signal_id=exit_signal_id,
                position_id=position_id,
                account_id=account_id,
                signal_date=exit_date,
                code=item.code,
                backtest_id=backtest_id,
                source_type="backtest_bootstrap_exit",
                trade_payload=item.exit,
                action_reason=str(item.exit.get("reason") or "backtest_bootstrap_exit"),
                selection_payload=selection_payload,
            )
            await record_trade_fill_from_order_and_trade(
                db,
                exit_order,
                exit_trade,
                source="backtest_bootstrap_import",
                payload={
                    "backtest_id": backtest_id,
                    "bootstrap_source": "backtest_to_incubation_v1",
                    "bootstrap_selection": selection_payload,
                },
            )
            imported += 1
            imported_codes.append(item.code)
            latest_trade_date = exit_date

        if imported > 0 and latest_trade_date is not None:
            await self.incubation_service.record_metrics(db, strategy, latest_trade_date)
        if imported > 0 and hasattr(db, "save_strategy_domain_event"):
            await db.save_strategy_domain_event(
                {
                    "strategy_id": strategy_id,
                    "aggregate_type": "strategy",
                    "aggregate_id": strategy_id,
                    "event_type": "incubation.bootstrap_backtest_imported",
                    "source": "strategy_acceptance_remediation",
                    "severity": "info",
                    "payload": {
                        "backtest_id": backtest_id,
                        "bootstrap_trade_floor": bootstrap_floor,
                        "existing_realized_trade_count": existing_realized,
                        "imported_round_trips": imported,
                        "imported_codes": imported_codes,
                        "bootstrap_source": "backtest_to_incubation_v1",
                        "bootstrap_selection": selection_report,
                        "cleanup": cleanup_summary,
                    },
                }
            )
        return {
            "strategy_id": strategy_id,
            "backtest_id": backtest_id,
            "bootstrap_trade_floor": bootstrap_floor,
            "existing_realized_trade_count": existing_realized,
            "imported_round_trips": imported,
            "imported_codes": imported_codes,
            "selection": selection_report,
            "cleanup": cleanup_summary,
        }


_strategy_acceptance_remediation_service: Optional[StrategyAcceptanceRemediationService] = None


def get_strategy_acceptance_remediation_service() -> StrategyAcceptanceRemediationService:
    global _strategy_acceptance_remediation_service
    if _strategy_acceptance_remediation_service is None:
        _strategy_acceptance_remediation_service = StrategyAcceptanceRemediationService()
    return _strategy_acceptance_remediation_service


__all__ = [
    "StrategyAcceptanceRemediationService",
    "_select_bootstrap_round_trips",
    "build_failed_metrics_filter_patch",
    "get_strategy_acceptance_remediation_service",
    "summarize_code_performance",
]
