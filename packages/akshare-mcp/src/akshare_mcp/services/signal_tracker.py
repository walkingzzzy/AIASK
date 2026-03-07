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
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

FORWARD_DAYS = [1, 5, 10, 20]


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
        self._task = asyncio.ensure_future(self._loop())
        logger.info("SignalTracker started, daily run at %s", self.run_time)

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
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
        results = {"signals_generated": 0, "forward_returns_computed": 0, "incubation_orders": 0, "incubation_metrics": 0, "risk_events": 0, "risk_actions": 0, "transitions": 0, "vector_registry_updates": 0, "task_run_id": task_run.get('id'), "errors": []}

        strategies = []

        # Phase A: Generate signals for listed/incubating strategies
        try:
            for status in ("listed", "incubating"):
                rows = await db.list_strategies(status, limit=200)
                strategies.extend(rows)

            for s in strategies:
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

        # Phase B: Compute forward returns for past signals
        try:
            for fd in FORWARD_DAYS:
                pending = await db.get_pending_forward_returns(fd)
                for rec in pending:
                    try:
                        code = rec["code"]
                        signal_date = rec["signal_date"]
                        klines = await self._get_klines_with_fallback(db, code, limit=fd + 5)
                        if not klines:
                            continue
                        # Find the close on signal_date and fd days later
                        by_date = {}
                        for k in klines:
                            kd = k.get("date")
                            if isinstance(kd, str):
                                kd = date.fromisoformat(kd[:10])
                            elif isinstance(kd, datetime):
                                kd = kd.date()
                            if kd:
                                by_date[kd] = float(k.get("close", 0))

                        if signal_date not in by_date:
                            continue
                        base_close = by_date[signal_date]
                        if base_close <= 0:
                            continue
                        # Find the close fd trading days after signal_date
                        sorted_dates = sorted(d for d in by_date if d > signal_date)
                        if len(sorted_dates) < fd:
                            continue
                        future_close = by_date[sorted_dates[fd - 1]]
                        actual_return = (future_close - base_close) / base_close
                        await db.save_forward_returns(rec["id"], fd, actual_return)
                        results["forward_returns_computed"] += 1
                    except Exception as e:
                        results["errors"].append(f"Fwd return {rec.get('id')}: {e}")
        except Exception as e:
            results["errors"].append(f"Phase B: {e}")

        # Phase C: Sync incubation orders and metrics
        try:
            from .incubation import get_strategy_incubation_service
            incubation_result = await get_strategy_incubation_service().process_strategies(db, strategies, signal_date=today)
            results["incubation_orders"] = int(incubation_result.get("orders_created") or 0)
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

        # Phase E: Lifecycle scan
        try:
            from ..tools.managers.strategy_manager import _lifecycle_scan
            scan_result = await _lifecycle_scan(db)
            results["transitions"] = len(scan_result.get("transitions", []))
        except Exception as e:
            results["errors"].append(f"Phase E: {e}")

        # Phase F: 向量索引注册表校准
        try:
            from .vector_governance import get_strategy_vector_governance_service
            vector_result = await get_strategy_vector_governance_service().reconcile_registry(db, index_name='strategy_behavior', profile_type='behavior')
            results["vector_registry_updates"] = int(vector_result.get("registry_updated") or 0)
        except Exception as e:
            results["errors"].append(f"Phase F: {e}")

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
            "SignalTracker: completed in %.1fs — %d signals, %d fwd returns, %d incubation orders, %d risk events, %d risk actions, %d transitions, %d errors",
            elapsed, results["signals_generated"], results["forward_returns_computed"],
            results["incubation_orders"], results["risk_events"], results["risk_actions"], results["transitions"], len(results["errors"]),
        )
        return self.last_result

    async def _get_klines_with_fallback(self, db, code: str, limit: int = 200) -> list:
        """从DB获取K线，数据不足时回退到数据源"""
        klines = await db.get_klines(code, limit=limit)
        if klines and len(klines) >= 20:
            return klines
        try:
            from ..data_source import data_source
            raw = data_source.get_kline(code, period="daily", limit=limit)
            if raw and len(raw) >= 20:
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
