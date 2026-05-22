"""孵化工厂 · 独立运行器。

孵化工厂的主循环，负责：
1. 自动识别和接纳策略工厂产出的新策略
2. 前向收益验证
3. 孵化流水线评估与阶段推进
4. 命中率报告生成
5. 反馈写入（供策略工厂读取）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from .intake import IncubationIntake
from .signal_generator import SignalGenerator
from .forward_verifier import ForwardVerifier
from .metrics_recorder import MetricsRecorder
from .hit_rate_reporter import HitRateReporter
from .feedback_writer import FeedbackWriter
from .accelerator import IncubationAccelerator
from .alert_monitor import AlertMonitor

logger = logging.getLogger(__name__)

# 默认运行时间：18:30（A 股 15:00 收盘 + 数据同步 ~2h + 缓冲）
DEFAULT_RUN_TIME = dt_time(18, 30)

# 单策略处理超时（秒）
STRATEGY_TIMEOUT_SEC = 30

# 批量处理超时（秒）
BATCH_TIMEOUT_SEC = 600

# 错误后等待时间（秒）
ERROR_BACKOFF_SEC = 300

# 健康检查间隔（秒）
HEARTBEAT_INTERVAL_SEC = 3600


class IncubationFactoryRunner:
    """孵化工厂独立运行器。

    支持两种运行模式：
    - run_once(): 单次执行完整孵化周期
    - run_daemon(): 守护进程模式，每日定时运行
    """

    def __init__(
        self,
        *,
        run_time: dt_time = DEFAULT_RUN_TIME,
        dry_run: bool = False,
        auto_apply_review: bool = True,
    ):
        self.run_time = run_time
        self.dry_run = dry_run
        self.auto_apply_review = auto_apply_review

        # 子模块
        self._intake = IncubationIntake()
        self._signal_generator = SignalGenerator()
        self._forward_verifier = ForwardVerifier()
        self._metrics_recorder = MetricsRecorder()
        self._reporter = HitRateReporter()
        self._feedback_writer = FeedbackWriter()
        self._accelerator = IncubationAccelerator()
        self._alert_monitor = AlertMonitor()

        # 运行状态
        self._last_run_at: Optional[datetime] = None
        self._last_result: Optional[dict[str, Any]] = None
        self._run_count: int = 0
        self._error_count: int = 0

    async def run_once(self) -> dict[str, Any]:
        """单次执行完整孵化周期。

        流程：
        1. 自动识别和接纳新策略
        2. 前向收益验证
        3. 指标记录
        4. 孵化流水线评估（复用已有实现）
        5. 命中率报告生成
        6. 反馈写入

        每个 phase 都被 ``_run_phase`` 包裹一层超时与错误捕获 — 单个
        phase 异常不再让整轮 failed，而是把错误聚合到
        ``result["phase_failures"]`` 并继续后续 phase。整轮以
        BATCH_TIMEOUT_SEC 为上限，超时也会被记录而不是冒出。
        """
        run_id = uuid4().hex[:12]
        start_time = datetime.now(timezone.utc)
        logger.info("IncubationFactory: starting run %s", run_id)
        phase_failures: list[dict[str, Any]] = []

        async def _run_phase(name: str, coro_factory, *, timeout: float = STRATEGY_TIMEOUT_SEC):
            """Run a single phase with a timeout + error capture.

            Returns the phase result, or None on failure (caller treats None
            as "skipped" and falls back to defaults). Records failures into
            the closed-over phase_failures list so the overall envelope can
            surface them as status='partial'.
            """
            try:
                return await asyncio.wait_for(coro_factory(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(
                    "IncubationFactory [%s] %s: timeout after %.0fs",
                    run_id, name, timeout,
                )
                phase_failures.append({"phase": name, "error": "timeout", "timeout_sec": timeout})
            except Exception as exc:
                logger.exception(
                    "IncubationFactory [%s] %s: failed: %s", run_id, name, exc,
                )
                phase_failures.append({"phase": name, "error": str(exc), "error_type": type(exc).__name__})
            return None

        db = await self._get_db()

        try:
            # Phase 1: 自动识别和接纳新策略
            logger.info("IncubationFactory [%s] Phase 1: Intake", run_id)
            intake_result = await _run_phase(
                "intake", lambda: self._intake.scan_and_accept(db),
                timeout=BATCH_TIMEOUT_SEC,
            ) or {}

            # Phase 2: 加载所有孵化中的策略 (cheap, no timeout)
            incubating = await self._list_incubating(db)
            logger.info(
                "IncubationFactory [%s] Phase 2: %d strategies to verify",
                run_id,
                len(incubating),
            )

            # Phase 3: 信号生成 + 前向收益验证 + 指标记录
            verifications: dict[str, dict[str, Any]] = {}
            metrics_recorded = 0
            verification_errors = 0
            signals_generated_total = 0

            for strategy in incubating:
                sid = str(strategy.get("id") or "").strip()
                if not sid:
                    continue
                try:
                    # 信号生成 — 单策略级超时
                    signal_result = await asyncio.wait_for(
                        self._signal_generator.generate(db, strategy),
                        timeout=STRATEGY_TIMEOUT_SEC,
                    )
                    signals_generated_total += int(
                        signal_result.get("signals_generated") or 0
                    )

                    # 前向验证 — 单策略级超时
                    verification = await asyncio.wait_for(
                        self._forward_verifier.verify(db, strategy),
                        timeout=STRATEGY_TIMEOUT_SEC,
                    )
                    verifications[sid] = verification

                    # 指标记录 — 单策略级超时
                    if not self.dry_run:
                        metric = await asyncio.wait_for(
                            self._metrics_recorder.record(db, strategy, verification),
                            timeout=STRATEGY_TIMEOUT_SEC,
                        )
                        if metric is not None:
                            metrics_recorded += 1
                except asyncio.TimeoutError:
                    verification_errors += 1
                    logger.warning(
                        "IncubationFactory [%s]: verify/record timeout for %s after %ss",
                        run_id, sid, STRATEGY_TIMEOUT_SEC,
                    )
                except Exception as exc:
                    verification_errors += 1
                    logger.warning(
                        "IncubationFactory [%s]: verify/record failed for %s: %s",
                        run_id, sid, exc,
                    )

            logger.info(
                "IncubationFactory [%s] Phase 3: signals=%d, verified=%d, recorded=%d, errors=%d",
                run_id,
                signals_generated_total,
                len(verifications),
                metrics_recorded,
                verification_errors,
            )

            # Phase 4: 孵化流水线评估（复用已有实现）
            logger.info("IncubationFactory [%s] Phase 4: Pipeline evaluation", run_id)
            pipeline_result = await _run_phase(
                "pipeline", lambda: self._run_pipeline(db),
                timeout=BATCH_TIMEOUT_SEC,
            ) or {}

            # Phase 5: 命中率报告
            logger.info("IncubationFactory [%s] Phase 5: Hit rate report", run_id)
            report = await _run_phase(
                "hit_rate_report",
                lambda: self._reporter.generate(db, incubating, verifications, pipeline_result),
                timeout=BATCH_TIMEOUT_SEC,
            ) or {}

            # Phase 6: 反馈写入
            feedback_result: dict[str, Any] = {}
            if not self.dry_run:
                logger.info("IncubationFactory [%s] Phase 6: Feedback write", run_id)
                feedback_result = await _run_phase(
                    "feedback_write",
                    lambda: self._feedback_writer.write(db, report),
                    timeout=BATCH_TIMEOUT_SEC,
                ) or {}

            # Phase 7: 加速孵化评估
            logger.info("IncubationFactory [%s] Phase 7: Acceleration check", run_id)
            acceleration_result = await _run_phase(
                "acceleration",
                lambda: self._accelerator.evaluate_batch(db, incubating, verifications),
                timeout=BATCH_TIMEOUT_SEC,
            ) or {}

            # Phase 8: 异常告警检查
            logger.info("IncubationFactory [%s] Phase 8: Alert check", run_id)
            alert_result = await _run_phase(
                "alert_check",
                lambda: self._alert_monitor.check(db, run_result={
                    "verification": {
                        "total": len(incubating),
                        "errors": verification_errors,
                    },
                }),
                timeout=STRATEGY_TIMEOUT_SEC,
            ) or {}

            # Phase 9: 健康检查心跳
            await _run_phase(
                "heartbeat",
                lambda: self._heartbeat(db, run_id),
                timeout=STRATEGY_TIMEOUT_SEC,
            )

            # 汇总结果
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            overall_status = "completed" if not phase_failures else "partial"
            result = {
                "run_id": run_id,
                "status": overall_status,
                "phase_failures": phase_failures,
                "dry_run": self.dry_run,
                "started_at": start_time.isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "intake": intake_result,
                "verification": {
                    "total": len(incubating),
                    "verified": len(verifications),
                    "metrics_recorded": metrics_recorded,
                    "errors": verification_errors,
                },
                "pipeline": {
                    "count": int(pipeline_result.get("count") or 0),
                    "auto_promoted": int(pipeline_result.get("auto_promoted") or 0),
                    "stage_counts": dict(pipeline_result.get("stage_counts") or {}),
                },
                "report": {
                    "overall_hit_rate": (
                        (report.get("hit_rate_dashboard") or {}).get("overall") or {}
                    ).get("hit_rate"),
                    "overall_skill_lcb": (
                        (report.get("hit_rate_dashboard") or {}).get("overall") or {}
                    ).get("avg_skill_lcb"),
                    "families_tracked": len(
                        (report.get("hit_rate_dashboard") or {}).get("by_family") or {}
                    ),
                },
                "feedback": feedback_result,
                "acceleration": {
                    "evaluated": int(acceleration_result.get("evaluated") or 0),
                    "accelerated": int(acceleration_result.get("accelerated_count") or 0),
                },
                "alerts": {
                    "count": int(alert_result.get("alert_count") or 0),
                    "items": list(alert_result.get("alerts") or []),
                },
            }

            self._last_run_at = start_time
            self._last_result = result
            self._run_count += 1

            logger.info(
                "IncubationFactory [%s]: %s in %.1fs "
                "(intake=%d, verified=%d, promoted=%d, hit_rate=%.2f%%, phase_failures=%d)",
                run_id,
                overall_status,
                elapsed,
                int(intake_result.get("accepted") or 0),
                len(verifications),
                int(pipeline_result.get("auto_promoted") or 0),
                float(
                    (
                        (report.get("hit_rate_dashboard") or {}).get("overall") or {}
                    ).get("hit_rate") or 0
                )
                * 100,
                len(phase_failures),
            )

            return result

        except Exception as exc:
            self._error_count += 1
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error(
                "IncubationFactory [%s]: failed after %.1fs: %s",
                run_id,
                elapsed,
                exc,
                exc_info=True,
            )
            return {
                "run_id": run_id,
                "status": "failed",
                "error": str(exc),
                "elapsed_seconds": round(elapsed, 2),
                "phase_failures": phase_failures,
            }
        finally:
            await self._close_db(db)

    async def run_daemon(self) -> None:
        """守护进程模式：每日定时运行。

        在指定时间（默认 18:30）执行孵化周期，
        失败后等待 5 分钟重试一次。
        """
        logger.info(
            "IncubationFactory: daemon started (run_time=%s, dry_run=%s)",
            self.run_time,
            self.dry_run,
        )

        while True:
            now = datetime.now()
            target = now.replace(
                hour=self.run_time.hour,
                minute=self.run_time.minute,
                second=0,
                microsecond=0,
            )
            if now >= target:
                target += timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            logger.info(
                "IncubationFactory: next run at %s (waiting %.0fs)",
                target.strftime("%Y-%m-%d %H:%M"),
                wait_seconds,
            )

            await asyncio.sleep(wait_seconds)

            # 执行孵化周期
            result = await self.run_once()

            # 如果失败，等待后重试一次
            if result.get("status") == "failed":
                logger.warning(
                    "IncubationFactory: run failed, retrying in %ds",
                    ERROR_BACKOFF_SEC,
                )
                await asyncio.sleep(ERROR_BACKOFF_SEC)
                retry_result = await self.run_once()
                if retry_result.get("status") == "failed":
                    logger.error(
                        "IncubationFactory: retry also failed: %s",
                        retry_result.get("error"),
                    )

    async def _list_incubating(self, db: Any) -> list[dict[str, Any]]:
        """加载所有孵化中的策略。"""
        if hasattr(db, "list_strategies"):
            return await db.list_strategies("incubating", limit=200)
        return []

    async def _run_pipeline(self, db: Any) -> dict[str, Any]:
        """运行孵化流水线评估（复用已有实现）。"""
        if self.dry_run:
            return {"count": 0, "auto_promoted": 0, "stage_counts": {}, "items": []}

        try:
            from ..incubation_pipeline import get_strategy_incubation_pipeline_service

            pipeline = get_strategy_incubation_pipeline_service()
            return await pipeline.run_batch(
                db,
                statuses=["incubating"],
                limit=200,
                source="incubation_factory",
                auto_apply_review=self.auto_apply_review,
            )
        except Exception as exc:
            logger.warning("IncubationFactory: pipeline run failed: %s", exc)
            return {"count": 0, "auto_promoted": 0, "stage_counts": {}, "items": []}

    async def _heartbeat(self, db: Any, run_id: str) -> None:
        """写入健康检查心跳。"""
        if not hasattr(db, "save_strategy_domain_event"):
            return
        try:
            await db.save_strategy_domain_event({
                "strategy_id": None,
                "aggregate_type": "incubation_factory",
                "aggregate_id": "heartbeat",
                "event_type": "incubation_factory.heartbeat",
                "source": "incubation_factory",
                "severity": "info",
                "payload": {
                    "run_id": run_id,
                    "run_count": self._run_count,
                    "error_count": self._error_count,
                    "last_run_at": (
                        self._last_run_at.isoformat() if self._last_run_at else None
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception as exc:
            logger.debug("IncubationFactory: heartbeat failed: %s", exc)

    async def _get_db(self) -> Any:
        """获取数据库连接。"""
        from akshare_mcp.storage import get_db

        db = get_db()
        await db.initialize()
        return db

    async def _close_db(self, db: Any) -> None:
        """关闭数据库连接。"""
        try:
            from akshare_mcp.storage import close_db
            await close_db()
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        """返回运行器状态。"""
        return {
            "run_time": str(self.run_time),
            "dry_run": self.dry_run,
            "run_count": self._run_count,
            "error_count": self._error_count,
            "last_run_at": (
                self._last_run_at.isoformat() if self._last_run_at else None
            ),
            "last_result_status": (
                self._last_result.get("status") if self._last_result else None
            ),
        }


# 单例
_runner: Optional[IncubationFactoryRunner] = None


def get_incubation_factory_runner() -> IncubationFactoryRunner:
    """获取孵化工厂运行器单例。"""
    global _runner
    if _runner is None:
        _runner = IncubationFactoryRunner()
    return _runner
