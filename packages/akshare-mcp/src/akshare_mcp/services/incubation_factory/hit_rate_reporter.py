"""孵化工厂 · 命中率报告模块。

负责生成孵化工厂的命中率报告，体现 AI 生成策略的真实胜率。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HitRateReporter:
    """命中率报告生成器。

    聚合所有孵化中策略的命中率数据，生成：
    - 整体命中率
    - 按 family 分组的命中率
    - 按孵化阶段分组的命中率
    - 趋势分析（命中率是否在改善）
    """

    async def generate(
        self,
        db: Any,
        strategies: list[dict[str, Any]],
        verifications: dict[str, dict[str, Any]],
        pipeline_result: dict[str, Any],
        *,
        report_date: Optional[date] = None,
    ) -> dict[str, Any]:
        """
        生成命中率报告。

        Args:
            db: 数据库连接
            strategies: 孵化中的策略列表
            verifications: {strategy_id: verification_result} 映射
            pipeline_result: 孵化流水线批量运行结果
            report_date: 报告日期

        Returns:
            完整的命中率报告
        """
        today = report_date or date.today()

        # 聚合整体命中率
        overall = self._aggregate_overall(verifications)

        # 按 family 分组
        by_family = self._aggregate_by_family(strategies, verifications)

        # 按阶段分组
        by_stage = self._aggregate_by_stage(strategies, verifications, pipeline_result)

        # 趋势分析
        trend = await self._compute_trend(db, strategies)

        # 反馈建议
        feedback_actions = self._derive_feedback_actions(by_family)

        report = {
            "report_date": str(today),
            "run_source": "incubation_factory",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_incubating": len(strategies),
                "total_with_signals": sum(
                    1
                    for v in verifications.values()
                    if int(v.get("primary_effective_n") or 0) > 0
                ),
                "auto_promoted": int(pipeline_result.get("auto_promoted") or 0),
                "stage_counts": dict(pipeline_result.get("stage_counts") or {}),
            },
            "hit_rate_dashboard": {
                "overall": overall,
                "by_family": by_family,
                "by_stage": by_stage,
                "trend": trend,
            },
            "feedback_actions": feedback_actions,
        }

        # 持久化报告
        await self._persist_report(db, report)

        return report

    def _aggregate_overall(
        self, verifications: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """聚合整体命中率。"""
        total_signals = 0
        total_hits = 0
        all_skill_lcbs: list[float] = []
        all_sharpes: list[float] = []

        for v in verifications.values():
            n = int(v.get("primary_effective_n") or 0)
            hit_rate = float(v.get("primary_hit_rate") or 0.0)
            skill_lcb = float(v.get("primary_skill_lcb") or 0.0)
            forward_sharpe = float(v.get("forward_sharpe") or 0.0)

            if n > 0:
                total_signals += n
                total_hits += int(round(hit_rate * n))
                all_skill_lcbs.append(skill_lcb)
                all_sharpes.append(forward_sharpe)

        overall_hit_rate = total_hits / total_signals if total_signals > 0 else 0.0
        avg_skill_lcb = (
            sum(all_skill_lcbs) / len(all_skill_lcbs) if all_skill_lcbs else 0.0
        )
        avg_sharpe = (
            sum(all_sharpes) / len(all_sharpes) if all_sharpes else 0.0
        )

        return {
            "total_signals": total_signals,
            "hit_count": total_hits,
            "hit_rate": round(overall_hit_rate, 4),
            "avg_skill_lcb": round(avg_skill_lcb, 4),
            "avg_forward_sharpe": round(avg_sharpe, 4),
            "strategy_count": len(
                [v for v in verifications.values() if int(v.get("primary_effective_n") or 0) > 0]
            ),
        }

    def _aggregate_by_family(
        self,
        strategies: list[dict[str, Any]],
        verifications: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """按策略 family 分组聚合命中率。"""
        family_data: dict[str, dict[str, list]] = defaultdict(
            lambda: {"hit_rates": [], "skill_lcbs": [], "ns": [], "sharpes": []}
        )

        for strategy in strategies:
            sid = str(strategy.get("id") or "").strip()
            family = str(
                strategy.get("strategy_type") or strategy.get("candidate_family") or "unknown"
            ).strip().lower()
            v = verifications.get(sid, {})
            n = int(v.get("primary_effective_n") or 0)
            if n > 0:
                family_data[family]["hit_rates"].append(
                    float(v.get("primary_hit_rate") or 0.0)
                )
                family_data[family]["skill_lcbs"].append(
                    float(v.get("primary_skill_lcb") or 0.0)
                )
                family_data[family]["ns"].append(n)
                family_data[family]["sharpes"].append(
                    float(v.get("forward_sharpe") or 0.0)
                )

        result = {}
        for family, data in sorted(family_data.items()):
            if not data["hit_rates"]:
                continue
            total_n = sum(data["ns"])
            # 加权平均命中率
            weighted_hit_rate = sum(
                hr * n for hr, n in zip(data["hit_rates"], data["ns"])
            ) / total_n if total_n > 0 else 0.0

            result[family] = {
                "hit_rate": round(weighted_hit_rate, 4),
                "avg_skill_lcb": round(
                    sum(data["skill_lcbs"]) / len(data["skill_lcbs"]), 4
                ),
                "avg_forward_sharpe": round(
                    sum(data["sharpes"]) / len(data["sharpes"]), 4
                ),
                "total_n": total_n,
                "strategy_count": len(data["hit_rates"]),
            }

        return result

    def _aggregate_by_stage(
        self,
        strategies: list[dict[str, Any]],
        verifications: dict[str, dict[str, Any]],
        pipeline_result: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """按孵化阶段分组聚合命中率。"""
        # 从 pipeline_result 中提取每个策略的阶段
        stage_map: dict[str, str] = {}
        for item in list(pipeline_result.get("items") or []):
            sid = str(item.get("strategy_id") or "").strip()
            snapshot = dict(item.get("snapshot") or {})
            stage = str(snapshot.get("pipeline_stage") or "unknown")
            if sid:
                stage_map[sid] = stage

        stage_data: dict[str, dict[str, list]] = defaultdict(
            lambda: {"hit_rates": [], "skill_lcbs": []}
        )

        for strategy in strategies:
            sid = str(strategy.get("id") or "").strip()
            stage = stage_map.get(sid, "unknown")
            v = verifications.get(sid, {})
            n = int(v.get("primary_effective_n") or 0)
            if n > 0:
                stage_data[stage]["hit_rates"].append(
                    float(v.get("primary_hit_rate") or 0.0)
                )
                stage_data[stage]["skill_lcbs"].append(
                    float(v.get("primary_skill_lcb") or 0.0)
                )

        result = {}
        for stage, data in sorted(stage_data.items()):
            if not data["hit_rates"]:
                continue
            result[stage] = {
                "avg_hit_rate": round(
                    sum(data["hit_rates"]) / len(data["hit_rates"]), 4
                ),
                "avg_skill_lcb": round(
                    sum(data["skill_lcbs"]) / len(data["skill_lcbs"]), 4
                ),
                "strategy_count": len(data["hit_rates"]),
            }

        return result

    async def _compute_trend(
        self, db: Any, strategies: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """计算命中率趋势（最近 7 天 vs 之前）。"""
        if not hasattr(db, "list_strategy_incubation_metrics"):
            return {"available": False}

        recent_skill_lcbs: list[float] = []
        older_skill_lcbs: list[float] = []

        for strategy in strategies[:50]:  # 限制查询量
            sid = str(strategy.get("id") or "").strip()
            if not sid:
                continue
            try:
                metrics = await db.list_strategy_incubation_metrics(sid, limit=14)
                if len(metrics) >= 7:
                    recent = metrics[:7]
                    older = metrics[7:]
                    for m in recent:
                        lcb = m.get("skill_lcb_5d")
                        if lcb is not None:
                            recent_skill_lcbs.append(float(lcb))
                    for m in older:
                        lcb = m.get("skill_lcb_5d")
                        if lcb is not None:
                            older_skill_lcbs.append(float(lcb))
            except Exception:
                continue

        if not recent_skill_lcbs or not older_skill_lcbs:
            return {"available": False}

        recent_avg = sum(recent_skill_lcbs) / len(recent_skill_lcbs)
        older_avg = sum(older_skill_lcbs) / len(older_skill_lcbs)
        improvement = recent_avg - older_avg

        return {
            "available": True,
            "recent_7d_avg_skill_lcb": round(recent_avg, 4),
            "prior_7d_avg_skill_lcb": round(older_avg, 4),
            "improvement": round(improvement, 4),
            "direction": "improving" if improvement > 0.005 else (
                "declining" if improvement < -0.005 else "stable"
            ),
        }

    def _derive_feedback_actions(
        self, by_family: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """根据命中率数据推导反馈动作。"""
        families_to_boost: list[str] = []
        families_to_cooldown: list[str] = []
        families_to_freeze: list[str] = []

        for family, data in by_family.items():
            skill_lcb = float(data.get("avg_skill_lcb") or 0.0)
            hit_rate = float(data.get("hit_rate") or 0.0)
            n = int(data.get("total_n") or 0)

            # 样本不足时不做判断
            if n < 15:
                continue

            # 技能下界显著为正 → 增加配额
            if skill_lcb > 0.03 and hit_rate > 0.55:
                families_to_boost.append(family)
            # 技能下界为负 → 冷却
            elif skill_lcb < -0.02:
                families_to_cooldown.append(family)
            # 技能下界严重为负 → 冻结
            elif skill_lcb < -0.05:
                families_to_freeze.append(family)

        return {
            "families_to_boost": families_to_boost,
            "families_to_cooldown": families_to_cooldown,
            "families_to_freeze": families_to_freeze,
        }

    async def _persist_report(self, db: Any, report: dict[str, Any]) -> None:
        """持久化命中率报告。"""
        if not hasattr(db, "save_strategy_domain_event"):
            return
        try:
            await db.save_strategy_domain_event({
                "strategy_id": None,
                "aggregate_type": "incubation_factory",
                "aggregate_id": f"hit_rate_report_{report['report_date']}",
                "event_type": "incubation_factory.hit_rate_report_generated",
                "source": "incubation_factory",
                "severity": "info",
                "payload": report,
            })
        except Exception as exc:
            logger.debug("HitRateReporter: persist report failed: %s", exc)
