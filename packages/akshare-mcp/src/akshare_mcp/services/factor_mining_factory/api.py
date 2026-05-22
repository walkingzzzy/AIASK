"""因子池对外 API — 供策略工厂通过 mcp_services.py 消费。

对齐现有 Gateway Protocol 模式（FactorResearchGateway / IncubationGateway）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FactorPoolGateway:
    """因子池 Gateway — 策略工厂消费因子池的标准接口。

    通过 strategy-factory/infrastructure/mcp_services.py 暴露：
        def get_factor_pool_gateway():
            return import_module(
                "akshare_mcp.services.factor_mining_factory.api"
            ).get_factor_pool_gateway()
    """

    def __init__(self):
        self._factory = None

    def _get_factory(self):
        if self._factory is None:
            from . import get_factor_mining_factory
            self._factory = get_factor_mining_factory()
        return self._factory

    async def get_active_factors(
        self,
        *,
        families: list[str] | None = None,
        min_grade: str = "B",
        limit: int = 50,
        include_quarantine: bool = False,
    ) -> list[dict[str, Any]]:
        """获取活跃因子列表。"""
        factory = self._get_factory()
        factory._ensure_initialized()
        try:
            db = await factory._get_db()
            await factory._ensure_persistent_pool(db)
            if include_quarantine:
                from .pool.storage import load_factor_pool_from_db

                rows = await load_factor_pool_from_db(
                    db,
                    statuses=("active", "quarantine"),
                    limit=limit,
                )
                if families:
                    rows = [
                        row for row in rows
                        if row.get("family") in set(families)
                    ]
                return rows[:limit]
        except Exception as exc:
            logger.debug("FactorPoolGateway: persistent pool load failed: %s", exc)
        return await factory._active_pool.get_active_factors(
            families=families,
            min_grade=min_grade,
            limit=limit,
        )

    async def get_factor_weights(
        self,
        factor_ids: list[str],
        method: str = "icir_weight",
    ) -> dict[str, float]:
        """获取因子组合权重。"""
        from .pool.portfolio_optimizer import FactorPortfolioOptimizer

        factory = self._get_factory()
        factory._ensure_initialized()

        # 构建 metrics
        metrics = {}
        for fid in factor_ids:
            record = factory._active_pool._factors.get(fid)
            if record:
                metrics[fid] = {
                    "ic_mean": record.get("fitness", 0.0) * 0.03,  # 近似
                    "ic_std": 0.02,
                    "ic_ir": record.get("fitness", 0.0) * 0.5,
                }

        optimizer = FactorPortfolioOptimizer()
        return optimizer.optimize(metrics, method=method)

    async def get_pool_status(self) -> dict[str, Any]:
        """获取因子池状态。"""
        factory = self._get_factory()
        factory._ensure_initialized()
        status = factory.status()
        try:
            from .pool.storage import load_factor_pool_from_db

            db = await factory._get_db()
            await factory._ensure_persistent_pool(db)
            rows = await load_factor_pool_from_db(
                db,
                statuses=("active", "quarantine", "retired"),
                limit=1000,
            )
            status["pool_health"] = self._summarize_pool_health(rows)
        except Exception as exc:
            logger.debug("FactorPoolGateway: pool health summary failed: %s", exc)
        return status

    @staticmethod
    def _summarize_pool_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
        from .quality import QUALITY_THRESHOLDS, safe_float, safe_int

        by_engine: dict[str, dict[str, Any]] = {}
        by_blueprint: dict[str, dict[str, Any]] = {}
        active_count = 0
        quarantine_count = 0
        retired_count = 0
        evidence_insufficient = 0
        ic_lengths: list[int] = []
        active_icirs: list[float] = []

        for row in rows or []:
            status = str(row.get("status") or "")
            validation_summary = dict(row.get("validation_summary") or {})
            quality_status = str(validation_summary.get("quality_status") or "")
            evidence = dict(validation_summary.get("evidence_summary") or {})
            persisted = dict(validation_summary.get("persisted_outputs") or {})
            ic_rows = max(
                safe_int(evidence.get("ic_history_rows")),
                safe_int(persisted.get("ic_history_rows")),
            )
            if status in {"active", "quarantine"}:
                ic_lengths.append(ic_rows)
                if ic_rows < int(QUALITY_THRESHOLDS["min_ic_history_rows"]):
                    evidence_insufficient += 1
            if status == "active" and quality_status == "promoted":
                active_count += 1
                active_icirs.append(safe_float(evidence.get("rank_ic_ir")))
            elif status == "quarantine":
                quarantine_count += 1
            elif status == "retired":
                retired_count += 1

            engine = str(row.get("generation_engine") or "unknown")
            bucket = by_engine.setdefault(
                engine,
                {
                    "active": 0,
                    "quarantine": 0,
                    "retired": 0,
                    "quality_score_sum": 0.0,
                    "count": 0,
                },
            )
            if status in {"active", "quarantine", "retired"}:
                bucket[status] += 1
            bucket["quality_score_sum"] += safe_float(
                validation_summary.get("quality_score"),
                safe_float(row.get("fitness")),
            )
            bucket["count"] += 1

            generation_trace = dict(row.get("generation_trace") or {})
            blueprint = str(
                validation_summary.get("blueprint_id")
                or generation_trace.get("blueprint_id")
                or "none"
            )
            bp_bucket = by_blueprint.setdefault(
                blueprint,
                {
                    "active": 0,
                    "quarantine": 0,
                    "retired": 0,
                    "quality_score_sum": 0.0,
                    "count": 0,
                    "redundant_reject_like": 0,
                },
            )
            if status in {"active", "quarantine", "retired"}:
                bp_bucket[status] += 1
            replacement = dict(validation_summary.get("replacement_decision") or {})
            if replacement.get("action") == "reject":
                bp_bucket["redundant_reject_like"] += 1
            bp_bucket["quality_score_sum"] += safe_float(
                validation_summary.get("quality_score"),
                safe_float(row.get("fitness")),
            )
            bp_bucket["count"] += 1

        for bucket in by_engine.values():
            count = max(1, int(bucket.pop("count", 0) or 0))
            score_sum = float(bucket.pop("quality_score_sum", 0.0) or 0.0)
            bucket["avg_quality_score"] = round(score_sum / count, 4)
        for bucket in by_blueprint.values():
            count = max(1, int(bucket.pop("count", 0) or 0))
            score_sum = float(bucket.pop("quality_score_sum", 0.0) or 0.0)
            bucket["avg_quality_score"] = round(score_sum / count, 4)

        return {
            "active_promoted_count": active_count,
            "quarantine_count": quarantine_count,
            "retired_count": retired_count,
            "quality_funnel": {
                "active_promoted": active_count,
                "quarantine": quarantine_count,
                "retired": retired_count,
                "evidence_insufficient": evidence_insufficient,
            },
            "avg_ic_history_length": round(sum(ic_lengths) / len(ic_lengths), 4)
            if ic_lengths
            else 0.0,
            "recent_60d_icir": round(sum(active_icirs) / len(active_icirs), 6)
            if active_icirs
            else 0.0,
            "evidence_insufficient_count": evidence_insufficient,
            "by_engine": by_engine,
            "by_blueprint": by_blueprint,
        }

    async def report_factor_performance(
        self,
        factor_id: str,
        strategy_id: str,
        metrics: dict[str, Any],
    ) -> None:
        """报告因子在策略中的实际表现（反馈通道）。"""
        from .feedback.performance_writer import FactorPerformanceFeedbackWriter
        from ...storage import get_db

        db = get_db()
        writer = FactorPerformanceFeedbackWriter()
        await writer.write_factor_performance(
            db,
            factor_id=factor_id,
            strategy_id=strategy_id,
            realized_ic=metrics.get("realized_ic", 0.0),
            realized_turnover=metrics.get("realized_turnover", 0.0),
            realized_cost=metrics.get("realized_cost", 0.0),
            period=metrics.get("period", ""),
        )

    async def trigger_mining_cycle(
        self,
        *,
        trigger: str = "api",
        engines: list[str] | None = None,
    ) -> dict[str, Any]:
        """手动触发一次挖掘周期。"""
        factory = self._get_factory()
        return await factory.run_mining_cycle(trigger=trigger, engines=engines)

    def status(self) -> dict[str, Any]:
        """Gateway 状态。"""
        factory = self._get_factory()
        return factory.status()


# 全局单例
_gateway: FactorPoolGateway | None = None


def get_factor_pool_gateway() -> FactorPoolGateway:
    """获取因子池 Gateway 单例。"""
    global _gateway
    if _gateway is None:
        _gateway = FactorPoolGateway()
    return _gateway
