"""Asyncio-based signal tracker — daily forward signal generation & verification.

Runs daily at 18:30 CST (after FactorScheduler at 18:00):
- Phase A: Generate signals for all listed/incubating strategies
- Phase B: Compute forward returns for past signals (1/5/10/20 day)
- Phase C: Run lifecycle scan (auto-promote/demote strategies)

Usage:
    from .signal_tracker import get_signal_tracker
    tracker = get_signal_tracker()
    tracker.start()
"""

import asyncio
import logging
from contextlib import suppress
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

FORWARD_DAYS = [1, 5, 10, 20]
FORWARD_RETURN_BATCH_LIMIT = 2000
FORWARD_RETURN_MAX_ROUNDS = 100
RECENT_SIGNAL_EVENT_LIMIT = 8


def _signal_series_from_events(length: int, events: list[dict[str, Any]] | None) -> np.ndarray:
    signals = np.zeros(max(0, int(length)), dtype=np.int8)
    for event in list(events or []):
        idx = int(event.get("index") or 0)
        signal = int(event.get("signal") or 0)
        if 0 <= idx < len(signals) and signal != 0:
            signals[idx] = 1 if signal > 0 else -1
    return signals


def _signal_series_from_masks(entry_mask: np.ndarray, exit_mask: np.ndarray) -> np.ndarray:
    entry = np.asarray(entry_mask, dtype=bool)
    exit_ = np.asarray(exit_mask, dtype=bool)
    size = max(len(entry), len(exit_))
    signals = np.zeros(size, dtype=np.int8)
    if len(entry):
        signals[: len(entry)][entry] = 1
    if len(exit_):
        exit_slice = signals[: len(exit_)]
        exit_slice[np.asarray(exit_, dtype=bool) & (exit_slice == 0)] = -1
    return signals


def _coerce_event_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized).date()
    except Exception:
        pass
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _default_event_action(signal: int) -> str:
    return "enter" if int(signal or 0) > 0 else ("exit" if int(signal or 0) < 0 else "hold")


def _classify_action_source(
    *,
    execution_semantic_mode: str,
    signal: int,
    action: Optional[str],
    reason: Optional[str],
) -> str:
    normalized_mode = str(execution_semantic_mode or "").strip().lower()
    normalized_action = str(action or "").strip().lower()
    normalized_reason = str(reason or "").strip().lower()
    if normalized_mode != "compiled_dsl":
        return "builtin_legacy_signal"
    if normalized_action == "enter" or int(signal or 0) > 0:
        return "dsl_entry"
    if normalized_action == "reduce":
        return "runtime_playbook_reduce"
    if normalized_action in {"freeze_reentry", "stop"}:
        return "runtime_playbook_stop"
    runtime_stop_tokens = (
        "stop",
        "take_profit",
        "trailing",
        "time_stop",
        "freeze",
        "band",
    )
    if any(token in normalized_reason for token in runtime_stop_tokens):
        return "runtime_playbook_stop"
    return "dsl_exit"


def _normalize_signal_events(
    klines: list[dict[str, Any]],
    events: list[dict[str, Any]] | None,
    *,
    execution_semantic_mode: str,
) -> list[dict[str, Any]]:
    ordered = list(klines or [])
    normalized: list[dict[str, Any]] = []
    max_length = len(ordered)
    for sequence, raw_event in enumerate(list(events or [])):
        try:
            index = int(raw_event.get("index") or 0)
        except Exception:
            continue
        if index < 0 or index >= max_length:
            continue
        raw_signal = int(raw_event.get("signal") or 0)
        signal = 1 if raw_signal > 0 else (-1 if raw_signal < 0 else 0)
        action = str(raw_event.get("action") or _default_event_action(signal)).strip().lower() or _default_event_action(signal)
        reason = str(raw_event.get("reason") or "").strip() or None
        units = _coerce_optional_float(raw_event.get("units"))
        remaining_units = _coerce_optional_float(raw_event.get("remaining_units"))
        bar = ordered[index] if 0 <= index < len(ordered) else {}
        event_date = _coerce_event_date(bar.get("date") or bar.get("time"))
        action_source = _classify_action_source(
            execution_semantic_mode=execution_semantic_mode,
            signal=signal,
            action=action,
            reason=reason,
        )
        normalized.append(
            {
                "sequence": sequence,
                "index": index,
                "date": event_date.isoformat() if event_date else None,
                "signal": signal,
                "action": action,
                "action_source": action_source,
                "reason": reason,
                "units": units,
                "remaining_units": remaining_units,
            }
        )
    return normalized


def _synthesize_events_from_masks(
    klines: list[dict[str, Any]],
    entry_mask: np.ndarray,
    exit_mask: np.ndarray,
    *,
    execution_semantic_mode: str,
) -> list[dict[str, Any]]:
    entry = np.asarray(entry_mask, dtype=bool)
    exit_ = np.asarray(exit_mask, dtype=bool)
    size = max(len(entry), len(exit_))
    events: list[dict[str, Any]] = []
    for index in range(size):
        if index < len(entry) and bool(entry[index]):
            events.append(
                {
                    "index": index,
                    "signal": 1,
                    "action": "enter",
                    "reason": "legacy_entry_mask",
                }
            )
        if index < len(exit_) and bool(exit_[index]):
            events.append(
                {
                    "index": index,
                    "signal": -1,
                    "action": "exit",
                    "reason": "legacy_exit_mask",
                }
            )
    return _normalize_signal_events(
        klines,
        events,
        execution_semantic_mode=execution_semantic_mode,
    )


def _synthesize_events_from_signal_series(
    klines: list[dict[str, Any]],
    signal_series: np.ndarray,
    *,
    execution_semantic_mode: str,
) -> list[dict[str, Any]]:
    signals = np.asarray(signal_series, dtype=np.int8)
    events: list[dict[str, Any]] = []
    last_nonzero_signal = 0
    for index, raw_signal in enumerate(signals):
        signal = 1 if int(raw_signal) > 0 else (-1 if int(raw_signal) < 0 else 0)
        if signal == 0 or signal == last_nonzero_signal:
            continue
        events.append(
            {
                "index": index,
                "signal": signal,
                "action": _default_event_action(signal),
                "reason": "legacy_signal_series",
            }
        )
        last_nonzero_signal = signal
    return _normalize_signal_events(
        klines,
        events,
        execution_semantic_mode=execution_semantic_mode,
    )


def _build_signal_tracking_artifacts(
    instance: Any,
    klines: list[dict[str, Any]],
    *,
    execution_semantic_mode: str,
) -> dict[str, Any]:
    ordered = list(klines or [])
    if not ordered:
        return {
            "signal_series": np.zeros(0, dtype=np.int8),
            "events": [],
            "latest_bar_signal": 0,
            "latest_bar_date": None,
            "signal_row": None,
            "snapshot": None,
        }

    signal_series: Optional[np.ndarray] = None
    normalized_events: list[dict[str, Any]] = []
    if hasattr(instance, "generate_signal_events_from_klines"):
        events = instance.generate_signal_events_from_klines(ordered)
        if events is not None:
            normalized_events = _normalize_signal_events(
                ordered,
                events,
                execution_semantic_mode=execution_semantic_mode,
            )
            signal_series = _signal_series_from_events(len(ordered), normalized_events)
    if signal_series is None and hasattr(instance, "generate_entry_exit_masks_from_klines"):
        entry_mask, exit_mask = instance.generate_entry_exit_masks_from_klines(ordered)
        signal_series = _signal_series_from_masks(entry_mask, exit_mask)
        normalized_events = _synthesize_events_from_masks(
            ordered,
            entry_mask,
            exit_mask,
            execution_semantic_mode=execution_semantic_mode,
        )
    if signal_series is None:
        closes = np.array([float(k.get("close", 0) or 0.0) for k in ordered], dtype=float)
        volumes = np.array([float(k.get("volume", 0) or 0.0) for k in ordered], dtype=float)
        try:
            signal_series = np.asarray(instance.generate_signals(closes, volumes), dtype=np.int8)
        except TypeError:
            signal_series = np.asarray(instance.generate_signals(closes), dtype=np.int8)
        normalized_events = _synthesize_events_from_signal_series(
            ordered,
            signal_series,
            execution_semantic_mode=execution_semantic_mode,
        )

    latest_bar_signal = int(signal_series[-1]) if len(signal_series) > 0 else 0
    latest_bar_date = _coerce_event_date((ordered[-1] or {}).get("date") or (ordered[-1] or {}).get("time"))
    latest_bar_index = len(signal_series) - 1
    latest_bar_event = next(
        (event for event in reversed(normalized_events) if int(event.get("index") or -1) == latest_bar_index),
        None,
    )
    latest_event = normalized_events[-1] if normalized_events else None
    latest_entry = next((event for event in reversed(normalized_events) if str(event.get("action") or "") == "enter"), None)
    latest_exit = next((event for event in reversed(normalized_events) if str(event.get("action") or "") == "exit"), None)
    nonzero_indexes = np.flatnonzero(np.asarray(signal_series, dtype=np.int8) != 0)
    latest_nonzero_index = int(nonzero_indexes[-1]) if len(nonzero_indexes) > 0 else None
    latest_nonzero_date = None
    latest_nonzero_signal = None
    if latest_nonzero_index is not None and 0 <= latest_nonzero_index < len(ordered):
        latest_nonzero_date = _coerce_event_date(
            (ordered[latest_nonzero_index] or {}).get("date") or (ordered[latest_nonzero_index] or {}).get("time")
        )
        latest_nonzero_signal = int(signal_series[latest_nonzero_index])

    default_action_source = _classify_action_source(
        execution_semantic_mode=execution_semantic_mode,
        signal=latest_bar_signal,
        action=_default_event_action(latest_bar_signal) if latest_bar_signal != 0 else None,
        reason=None,
    ) if latest_bar_signal != 0 else None
    signal_row = None
    if latest_bar_signal != 0:
        signal_row = {
            "signal": latest_bar_signal,
            "score": float(latest_bar_signal),
            "execution_semantic_mode": execution_semantic_mode,
            "action_source": (
                str(latest_bar_event.get("action_source") or "").strip() or default_action_source
                if latest_bar_event
                else default_action_source
            ),
            "event_action": (
                str(latest_bar_event.get("action") or "").strip() or _default_event_action(latest_bar_signal)
                if latest_bar_event
                else _default_event_action(latest_bar_signal)
            ),
            "action_reason": (
                str(latest_bar_event.get("reason") or "").strip() or None
                if latest_bar_event
                else None
            ),
            "signal_metadata": {
                "latest_bar_date": latest_bar_date.isoformat() if latest_bar_date else None,
                "latest_event_index": latest_event.get("index") if latest_event else None,
                "latest_event_date": latest_event.get("date") if latest_event else None,
                "latest_nonzero_signal_index": latest_nonzero_index,
                "latest_nonzero_signal_date": latest_nonzero_date.isoformat() if latest_nonzero_date else None,
                "latest_nonzero_signal": latest_nonzero_signal,
                "event_count": len(normalized_events),
                "latest_bar_has_event": latest_bar_event is not None,
                "execution_semantic_mode": execution_semantic_mode,
                "action_source": (
                    str(latest_bar_event.get("action_source") or "").strip() or default_action_source
                    if latest_bar_event
                    else default_action_source
                ),
                "event_action": (
                    str(latest_bar_event.get("action") or "").strip() or _default_event_action(latest_bar_signal)
                    if latest_bar_event
                    else _default_event_action(latest_bar_signal)
                ),
                "action_reason": (
                    str(latest_bar_event.get("reason") or "").strip() or None
                    if latest_bar_event
                    else None
                ),
            },
        }

    recent_events = []
    for event in normalized_events[-RECENT_SIGNAL_EVENT_LIMIT:]:
        recent_events.append(
            {
                "index": int(event.get("index") or 0),
                "date": event.get("date"),
                "signal": int(event.get("signal") or 0),
                "action": event.get("action"),
                "action_source": event.get("action_source"),
                "reason": event.get("reason"),
                "units": event.get("units"),
                "remaining_units": event.get("remaining_units"),
            }
        )

    snapshot = {
        "latest_bar_date": latest_bar_date,
        "latest_bar_signal": latest_bar_signal,
        "execution_semantic_mode": execution_semantic_mode,
        "latest_event_index": latest_event.get("index") if latest_event else None,
        "latest_event_date": latest_event.get("date") if latest_event else None,
        "latest_event_signal": latest_event.get("signal") if latest_event else None,
        "latest_event_action": latest_event.get("action") if latest_event else None,
        "latest_event_action_source": latest_event.get("action_source") if latest_event else None,
        "latest_event_reason": latest_event.get("reason") if latest_event else None,
        "latest_event_units": latest_event.get("units") if latest_event else None,
        "latest_entry_date": latest_entry.get("date") if latest_entry else None,
        "latest_exit_date": latest_exit.get("date") if latest_exit else None,
        "event_count": len(normalized_events),
        "recent_events": recent_events,
        "metadata": {
            "latest_bar_has_event": latest_bar_event is not None,
            "recent_event_window": RECENT_SIGNAL_EVENT_LIMIT,
            "latest_nonzero_signal_index": latest_nonzero_index,
            "latest_nonzero_signal_date": latest_nonzero_date.isoformat() if latest_nonzero_date else None,
            "latest_nonzero_signal": latest_nonzero_signal,
        },
    }
    return {
        "signal_series": signal_series,
        "events": normalized_events,
        "latest_bar_signal": latest_bar_signal,
        "latest_bar_date": latest_bar_date,
        "signal_row": signal_row,
        "snapshot": snapshot,
    }


class SignalTracker:
    """Asyncio-based daily signal tracking scheduler."""

    def __init__(self, run_time: time = time(18, 30)):
        self.run_time = run_time
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None

    def start(self):
        if self._running:
            logger.warning("SignalTracker already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="signal-tracker")
        logger.info("SignalTracker started, daily run at %s", self.run_time)

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("SignalTracker stopped")

    async def shutdown(self, grace_sec: float = 5.0):
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            logger.info("SignalTracker stopped")
            return
        if not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, grace_sec))
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        else:
            with suppress(asyncio.CancelledError):
                await task
        logger.info("SignalTracker stopped")

    async def _loop(self):
        while self._running:
            try:
                now = datetime.now()
                target = datetime.combine(now.date(), self.run_time)
                if target <= now:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info("SignalTracker: next run in %.0f seconds at %s", wait_seconds, target)
                await asyncio.sleep(wait_seconds)

                if self._running:
                    await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("SignalTracker loop error: %s", e, exc_info=True)
                await asyncio.sleep(60)

    @staticmethod
    def _merge_unique_strategies(*groups: list[dict]) -> list[dict]:
        merged: list[dict] = []
        seen: set[str] = set()
        for group in groups:
            for strategy in list(group or []):
                strategy_id = str((strategy or {}).get("id") or "").strip()
                if not strategy_id or strategy_id in seen:
                    continue
                seen.add(strategy_id)
                merged.append(strategy)
        return merged

    async def _load_runtime_submitted_strategies(self, db, *, limit: int = 200) -> list[dict]:
        if not hasattr(db, "list_strategies"):
            return []
        rows = await db.list_strategies("submitted", limit=limit)
        if not rows:
            return []
        get_quality_report = getattr(db, "get_strategy_quality_report", None)
        eligible: list[dict] = []
        for row in list(rows or []):
            if await self._is_runtime_submitted_strategy(
                db,
                row,
                get_quality_report=get_quality_report,
            ):
                eligible.append(row)
        return eligible

    async def _is_runtime_submitted_strategy(self, db, strategy: dict, *, get_quality_report=None) -> bool:
        strategy_id = str((strategy or {}).get("id") or "").strip()
        if not strategy_id:
            return False
        report = None
        if callable(get_quality_report):
            try:
                report = await get_quality_report(strategy_id, "submission")
            except Exception:
                report = None
        summary = dict((report or {}).get("summary") or {})
        lane = str(
            summary.get("submission_lane")
            or (report or {}).get("submission_lane")
            or ""
        ).strip().lower()
        if lane in {"observe_incubation", "live_ready_review"}:
            return True
        for field_name in (
            "paper_lane_ready",
            "live_review_ready",
            "paper_account_id",
            "live_review_account_id",
        ):
            if summary.get(field_name) or (report or {}).get(field_name):
                return True
        params = dict((strategy or {}).get("params") or {})
        incubation_budget = dict(params.get("incubation_budget") or {})
        return str(incubation_budget.get("track") or "").strip().lower() in {
            "observe_incubation",
            "live_ready_review",
        }

    @staticmethod
    def _resolve_strategy_universe(strategy: dict, default_universe: list[str]) -> list[str]:
        payload = dict(strategy or {})
        params = dict(payload.get("params") or {})
        ordered: list[str] = []
        seen: set[str] = set()

        def _push(value: Any) -> None:
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    _push(item)
                return
            if isinstance(value, dict):
                for key in ("symbols", "target_symbols", "symbol", "stock_code", "code"):
                    if key in value:
                        _push(value.get(key))
                return
            text = str(value or "").strip()
            if not text or text in seen:
                return
            seen.add(text)
            ordered.append(text)

        for candidate in (
            payload.get("target_symbols"),
            payload.get("stock_pool"),
            payload.get("research_task"),
            params.get("target_symbols"),
            params.get("stock_pool"),
            params.get("research_task"),
            dict(params.get("dsl") or {}).get("metadata"),
        ):
            _push(candidate)
        return ordered or list(default_universe or [])

    async def run_once(self):
        """Execute a single signal tracking cycle."""
        from ..storage import get_db
        from .backtest.strategy_registry import StrategyRegistry
        from .factor_scheduler import DEFAULT_UNIVERSE

        logger.info("SignalTracker: starting daily cycle")
        start = datetime.now()
        db = get_db()
        today = date.today()
        task_run = await db.save_strategy_task_run({
            'task_name': 'strategy_runtime_cycle',
            'task_scope': 'signal_tracker',
            'task_key': str(today),
            'status': 'running',
            'trace_id': uuid4().hex[:12],
            'payload': {'signal_date': str(today)},
        }) if hasattr(db, 'save_strategy_task_run') else {'id': None, 'trace_id': None}
        results = {
            "signals_generated": 0,
            "signal_event_snapshots": 0,
            "forward_returns_computed": 0,
            "incubation_orders": 0,
            "incubation_metrics": 0,
            "risk_events": 0,
            "risk_actions": 0,
            "transitions": 0,
            "vector_registry_updates": 0,
            "projection_snapshots": 0,
            "skipped_runtime_controls": 0,
            "task_run_id": task_run.get('id'),
            "errors": [],
        }

        strategies = []
        executable_strategies = []
        submitted_runtime_strategies = []

        # Phase A: Generate signals for listed/incubating strategies
        try:
            active_strategies = []
            for status in ("listed", "incubating"):
                rows = await db.list_strategies(status, limit=200)
                active_strategies.extend(rows)
            submitted_runtime_strategies = await self._load_runtime_submitted_strategies(
                db,
                limit=200,
            )
            strategies = self._merge_unique_strategies(
                active_strategies,
                submitted_runtime_strategies,
            )

            from .runtime_control import get_strategy_runtime_control_service
            control_service = get_strategy_runtime_control_service()
            for s in strategies:
                control = await db.get_strategy_runtime_control(s['id']) if hasattr(db, 'get_strategy_runtime_control') else None
                if control_service.is_blocking_mode((control or {}).get('control_mode')):
                    results['skipped_runtime_controls'] += 1
                    continue
                executable_strategies.append(s)

            for s in executable_strategies:
                try:
                    stype = s.get("strategy_type", "")
                    instance, execution_semantic_mode = StrategyRegistry.create_runtime_strategy(
                        stype,
                        s.get("params") or {},
                    )
                    if instance is None:
                        continue

                    signals_batch = []
                    for code in self._resolve_strategy_universe(s, DEFAULT_UNIVERSE):
                        klines = await self._get_klines_with_fallback(db, code, limit=200)
                        if not klines or len(klines) < 20:
                            continue
                        artifacts = _build_signal_tracking_artifacts(
                            instance,
                            klines,
                            execution_semantic_mode=execution_semantic_mode,
                        )
                        snapshot_payload = dict(artifacts.get("snapshot") or {})
                        if snapshot_payload and hasattr(db, "save_strategy_signal_event_snapshot"):
                            snapshot_metadata = dict(snapshot_payload.get("metadata") or {})
                            snapshot_metadata["runtime_cycle_seen_today"] = True
                            snapshot_payload["metadata"] = snapshot_metadata
                            snapshot_payload.update(
                                {
                                    "strategy_id": s["id"],
                                    "code": code,
                                    "as_of_date": today,
                                    "execution_semantic_mode": execution_semantic_mode,
                                }
                            )
                            await db.save_strategy_signal_event_snapshot(snapshot_payload)
                            results["signal_event_snapshots"] += 1

                        signal_row = dict(artifacts.get("signal_row") or {})
                        latest_signal = int(signal_row.get("signal") or 0)
                        if latest_signal != 0:
                            signal_row["code"] = code
                            signals_batch.append(signal_row)

                    if signals_batch:
                        count = await db.save_signals(s["id"], today, signals_batch)
                        results["signals_generated"] += count
                except Exception as e:
                    results["errors"].append(f"Signal gen {s.get('id')}: {e}")
        except Exception as e:
            results["errors"].append(f"Phase A: {e}")

        # Phase B: Compute forward returns for past signals and historical backlog
        try:
            backfill_result = await self.backfill_forward_returns(
                db,
                forward_days_list=FORWARD_DAYS,
                batch_limit=FORWARD_RETURN_BATCH_LIMIT,
                max_rounds=FORWARD_RETURN_MAX_ROUNDS,
            )
            results["forward_returns_computed"] = int(backfill_result.get("computed") or 0)
            results["forward_returns_backfill"] = backfill_result
        except Exception as e:
            results["errors"].append(f"Phase B: {e}")

        # Phase C: Sync incubation orders and metrics
        try:
            from .incubation import get_strategy_incubation_service
            incubation_result = await get_strategy_incubation_service().process_strategies(db, executable_strategies, signal_date=today)
            results["incubation_orders"] = int(incubation_result.get("orders_created") or 0)
            results["incubation_orders_filled"] = int(incubation_result.get("orders_filled") or 0)
            results["incubation_nav_snapshots"] = int(incubation_result.get("nav_snapshots") or 0)
            results["incubation_metrics"] = int(incubation_result.get("metrics_recorded") or 0)
        except Exception as e:
            results["errors"].append(f"Phase C: {e}")

        # Phase D: Runtime risk scan
        try:
            from .runtime_risk import get_strategy_runtime_risk_service
            risk_result = await get_strategy_runtime_risk_service().scan(db, strategies, enforce_actions=True)
            results["risk_events"] = int(risk_result.get("event_count") or 0)
            results["risk_actions"] = int(risk_result.get("action_count") or 0)
        except Exception as e:
            results["errors"].append(f"Phase D: {e}")

        # Phase E: 孵化流水线推进与自动晋级
        try:
            from .incubation_pipeline import get_strategy_incubation_pipeline_service
            pipeline_service = get_strategy_incubation_pipeline_service()
            pipeline_result = await pipeline_service.run_batch(
                db,
                statuses=['incubating'],
                limit=200,
                source='signal_tracker',
                auto_apply_review=True,
            )
            submitted_pipeline_snapshots = 0
            for strategy in submitted_runtime_strategies:
                try:
                    await pipeline_service.run_strategy(
                        db,
                        strategy,
                        source='signal_tracker_submitted',
                        auto_apply_review=False,
                    )
                    submitted_pipeline_snapshots += 1
                except Exception as exc:
                    results["errors"].append(f"Phase E submitted {strategy.get('id')}: {exc}")
            results["incubation_pipeline_snapshots"] = int(pipeline_result.get("count") or 0)
            results["incubation_pipeline_snapshots"] += submitted_pipeline_snapshots
            results["incubation_auto_promotions"] = int(pipeline_result.get("auto_promoted") or 0)
            results["submitted_runtime_pipeline_snapshots"] = submitted_pipeline_snapshots
        except Exception as e:
            results["errors"].append(f"Phase E: {e}")

        # Phase F: Lifecycle scan
        try:
            from ..tools.managers.strategy_manager import _lifecycle_scan
            scan_result = await _lifecycle_scan(db)
            results["transitions"] = len(scan_result.get("transitions", []))
        except Exception as e:
            results["errors"].append(f"Phase F: {e}")

        # Phase G: 向量索引注册表校准
        try:
            from .vector_governance import get_strategy_vector_governance_service
            vector_result = await get_strategy_vector_governance_service().reconcile_registry(db, index_name='strategy_behavior', profile_type='behavior')
            results["vector_registry_updates"] = int(vector_result.get("registry_updated") or 0)
        except Exception as e:
            results["errors"].append(f"Phase F: {e}")

        # Phase H: 事件投影快照重建
        try:
            from .domain_projection import get_strategy_domain_projection_service
            projection_result = await get_strategy_domain_projection_service().rebuild_batch(
                db,
                statuses=['incubating', 'listed', 'suspended', 'deprecated'],
                limit=200,
                source='signal_tracker',
            )
            results["projection_snapshots"] = int(projection_result.get("count") or 0)
        except Exception as e:
            results["errors"].append(f"Phase H: {e}")

        elapsed = (datetime.now() - start).total_seconds()
        self.last_run = datetime.now()
        self.last_result = {**results, "elapsed_seconds": round(elapsed, 1)}
        if task_run.get('id') is not None and hasattr(db, 'update_strategy_task_run'):
            await db.update_strategy_task_run(task_run['id'], status='completed', result=self.last_result, completed_at=datetime.now().isoformat())
        if hasattr(db, 'save_strategy_domain_event'):
            await db.save_strategy_domain_event({
                'strategy_id': None,
                'aggregate_type': 'runtime_cycle',
                'aggregate_id': str(task_run.get('id') or today),
                'event_type': 'runtime_cycle.completed',
                'source': 'signal_tracker',
                'severity': 'info',
                'correlation_id': task_run.get('trace_id'),
                'payload': self.last_result,
            })
        logger.info(
            "SignalTracker: completed in %.1fs — %d signals, %d event snapshots, %d fwd returns, %d incubation orders, %d pipeline snapshots, %d auto promotions, %d risk events, %d risk actions, %d transitions, %d errors",
            elapsed, results["signals_generated"], results["signal_event_snapshots"], results["forward_returns_computed"],
            results["incubation_orders"], results["incubation_pipeline_snapshots"], results["incubation_auto_promotions"], results["risk_events"], results["risk_actions"], results["transitions"], len(results["errors"]),
        )
        return self.last_result

    async def backfill_forward_returns(
        self,
        db=None,
        *,
        forward_days_list: Optional[List[int]] = None,
        batch_limit: int = FORWARD_RETURN_BATCH_LIMIT,
        max_rounds: int = FORWARD_RETURN_MAX_ROUNDS,
    ) -> dict:
        """批量回填历史前向收益，支持在日常 Phase B 中复用。"""
        from ..storage import get_db

        database = db or get_db()
        windows = [int(item) for item in list(forward_days_list or FORWARD_DAYS) if int(item) > 0]
        per_window: dict[str, Any] = {}
        total_computed = 0

        for forward_days in windows:
            window_key = f"{forward_days}D"
            rounds = 0
            computed = 0
            pending_seen = 0
            cursor_signal_date: Optional[date] = None
            cursor_id = 0
            truncated = False

            while rounds < max(1, int(max_rounds or 1)):
                rounds += 1
                pending = await database.get_pending_forward_returns(
                    forward_days,
                    limit=batch_limit,
                    after_signal_date=cursor_signal_date,
                    after_id=cursor_id,
                )
                if not pending:
                    break
                pending_seen += len(pending)
                saved = await self._compute_forward_returns_batch(
                    database,
                    pending,
                    forward_days=forward_days,
                )
                computed += saved
                total_computed += saved
                last_record = dict(pending[-1] or {})
                cursor_signal_date = self._coerce_trade_date(last_record.get("signal_date"))
                cursor_id = int(last_record.get("id") or 0)
            else:
                truncated = True
                logger.warning(
                    "SignalTracker: forward-return backfill truncated for %s after %d rounds",
                    window_key,
                    rounds,
                )

            per_window[window_key] = {
                "rounds": rounds,
                "pending_seen": pending_seen,
                "computed": computed,
                "stalled": truncated,
            }

        return {
            "computed": total_computed,
            "batch_limit": max(1, int(batch_limit or FORWARD_RETURN_BATCH_LIMIT)),
            "max_rounds": max(1, int(max_rounds or FORWARD_RETURN_MAX_ROUNDS)),
            "windows": per_window,
        }

    async def _compute_forward_returns_batch(
        self,
        db,
        pending: List[dict],
        *,
        forward_days: int,
    ) -> int:
        if not pending:
            return 0

        pending_by_code: Dict[str, List[dict]] = {}
        for record in list(pending or []):
            code = str(record.get("code") or "").strip()
            if not code:
                continue
            pending_by_code.setdefault(code, []).append(record)

        rows_to_save: list[dict[str, Any]] = []
        for code, records in pending_by_code.items():
            signal_dates = [self._coerce_trade_date(item.get("signal_date")) for item in records]
            signal_dates = [item for item in signal_dates if item is not None]
            if not signal_dates:
                continue
            earliest_signal_date = min(signal_dates)
            klines = await self._get_klines_with_fallback(
                db,
                code,
                start_date=earliest_signal_date,
                limit=None,
                allow_data_source_fallback=False,
            )
            close_series = self._build_close_series(klines)
            if not close_series:
                continue
            index_by_date = {trade_date: idx for idx, (trade_date, _close) in enumerate(close_series)}
            closes = [close for _trade_date, close in close_series]
            for record in records:
                signal_date = self._coerce_trade_date(record.get("signal_date"))
                if signal_date is None:
                    continue
                base_index = index_by_date.get(signal_date)
                if base_index is None:
                    continue
                future_index = base_index + int(forward_days)
                if future_index >= len(closes):
                    continue
                base_close = float(closes[base_index] or 0.0)
                future_close = float(closes[future_index] or 0.0)
                if base_close <= 0:
                    continue
                rows_to_save.append(
                    {
                        "signal_id": int(record["id"]),
                        "forward_days": int(forward_days),
                        "actual_return": (future_close - base_close) / base_close,
                    }
                )

        if not rows_to_save:
            return 0

        if hasattr(db, "save_forward_returns_batch"):
            return int(await db.save_forward_returns_batch(rows_to_save) or 0)

        saved = 0
        for row in rows_to_save:
            await db.save_forward_returns(
                row["signal_id"],
                row["forward_days"],
                row["actual_return"],
            )
            saved += 1
        return saved

    @staticmethod
    def _coerce_trade_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except Exception:
            return None

    def _build_close_series(self, klines: List[dict]) -> List[tuple[date, float]]:
        close_by_date: dict[date, float] = {}
        for kline in list(klines or []):
            trade_date = self._coerce_trade_date(kline.get("date") or kline.get("time"))
            if trade_date is None:
                continue
            try:
                close = float(kline.get("close") or 0.0)
            except Exception:
                continue
            if close <= 0:
                continue
            close_by_date[trade_date] = close
        return sorted(close_by_date.items(), key=lambda item: item[0])

    async def _get_klines_with_fallback(
        self,
        db,
        code: str,
        limit: Optional[int] = 200,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        allow_data_source_fallback: bool = True,
    ) -> list:
        """从DB获取K线，数据不足时回退到数据源。"""
        kwargs: dict[str, Any] = {}
        if start_date is not None:
            kwargs["start_date"] = start_date.isoformat()
        if end_date is not None:
            kwargs["end_date"] = end_date.isoformat()
        if limit is not None:
            kwargs["limit"] = limit

        klines = await db.get_klines(code, **kwargs)
        minimum_bars = 1 if start_date is not None or end_date is not None else 20
        if klines and len(klines) >= minimum_bars:
            return klines
        if not allow_data_source_fallback:
            return klines or []
        try:
            from ..data_source import data_source
            fallback_limit = limit if limit is not None else 2000
            raw = data_source.get_kline(code, period="daily", limit=fallback_limit)
            if raw and (start_date is not None or end_date is not None):
                raw = [
                    item for item in list(raw or [])
                    if (
                        (start_date is None or (self._coerce_trade_date(item.get("date")) or date.min) >= start_date)
                        and (end_date is None or (self._coerce_trade_date(item.get("date")) or date.max) <= end_date)
                    )
                ]
            if raw and len(raw) >= minimum_bars:
                logger.info("SignalTracker: fallback to data_source for %s (%d bars)", code, len(raw))
                return raw
        except Exception as e:
            logger.debug("SignalTracker: data_source fallback failed for %s: %s", code, e)
        return klines or []

    def status(self) -> dict:
        return {
            "running": self._running,
            "run_time": str(self.run_time),
            "last_run": str(self.last_run) if self.last_run else None,
            "last_result": self.last_result,
        }


_tracker: Optional[SignalTracker] = None


def get_signal_tracker() -> SignalTracker:
    global _tracker
    if _tracker is None:
        _tracker = SignalTracker()
    return _tracker
