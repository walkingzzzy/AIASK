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
        results = {"signals_generated": 0, "forward_returns_computed": 0, "incubation_orders": 0, "incubation_metrics": 0, "risk_events": 0, "risk_actions": 0, "transitions": 0, "vector_registry_updates": 0, "projection_snapshots": 0, "skipped_runtime_controls": 0, "task_run_id": task_run.get('id'), "errors": []}

        strategies = []
        executable_strategies = []

        # Phase A: Generate signals for listed/incubating strategies
        try:
            for status in ("listed", "incubating"):
                rows = await db.list_strategies(status, limit=200)
                strategies.extend(rows)

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
                    klass = StrategyRegistry.get(stype)
                    if klass is None:
                        continue
                    instance = klass()
                    instance.set_parameters(s.get("params") or {})

                    signals_batch = []
                    for code in DEFAULT_UNIVERSE:
                        klines = await self._get_klines_with_fallback(db, code, limit=200)
                        if not klines or len(klines) < 20:
                            continue
                        closes = np.array([float(k.get("close", 0)) for k in klines])
                        volumes = np.array([float(k.get("volume", 0) or 0) for k in klines])
                        try:
                            sig_arr = instance.generate_signals(closes, volumes)
                        except TypeError:
                            sig_arr = instance.generate_signals(closes)
                        latest_signal = int(sig_arr[-1]) if len(sig_arr) > 0 else 0
                        if latest_signal != 0:
                            signals_batch.append({"code": code, "signal": latest_signal, "score": float(sig_arr[-1])})

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
            pipeline_result = await get_strategy_incubation_pipeline_service().run_batch(
                db,
                statuses=['incubating'],
                limit=200,
                source='signal_tracker',
                auto_apply_review=True,
            )
            results["incubation_pipeline_snapshots"] = int(pipeline_result.get("count") or 0)
            results["incubation_auto_promotions"] = int(pipeline_result.get("auto_promoted") or 0)
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
            "SignalTracker: completed in %.1fs — %d signals, %d fwd returns, %d incubation orders, %d pipeline snapshots, %d auto promotions, %d risk events, %d risk actions, %d transitions, %d errors",
            elapsed, results["signals_generated"], results["forward_returns_computed"],
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
