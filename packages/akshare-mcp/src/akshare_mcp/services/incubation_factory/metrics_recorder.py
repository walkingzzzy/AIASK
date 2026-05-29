"""孵化工厂 · 指标记录模块。

负责将每日孵化验证结果写入 strategy_incubation_metrics 表。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MetricsRecorder:
    """每日孵化指标记录器。

    将前向验证结果和策略运行状态写入 strategy_incubation_metrics 表，
    供策略工厂的 IncubationBudgeter 读取作为反馈。
    """

    async def record(
        self,
        db: Any,
        strategy: dict[str, Any],
        verification: dict[str, Any],
        *,
        metric_date: Optional[date] = None,
    ) -> Optional[dict[str, Any]]:
        """
        记录策略的每日孵化指标。

        Args:
            db: 数据库连接
            strategy: 策略记录
            verification: ForwardVerifier 的验证结果
            metric_date: 指标日期（默认今天）

        Returns:
            保存的指标记录，或 None（如果保存失败）
        """
        sid = str(strategy.get("id") or "").strip()
        if not sid:
            return None

        today = metric_date or date.today()

        # 获取孵化账户信息
        account = None
        if hasattr(db, "get_strategy_incubation_account"):
            account = await db.get_strategy_incubation_account(sid)

        account_id = str((account or {}).get("account_id") or "").strip()

        # 获取 paper account 的 NAV 信息
        nav_info = await self._get_nav_info(db, account_id, today)

        # 构建指标
        metric = self._build_metric(
            strategy=strategy,
            verification=verification,
            nav_info=nav_info,
            account_id=account_id,
            metric_date=today,
        )

        # 保存到数据库
        if hasattr(db, "save_strategy_incubation_metric"):
            try:
                saved = await db.save_strategy_incubation_metric(
                    sid, today, metric
                )
                logger.debug(
                    "MetricsRecorder: saved metric for %s on %s",
                    sid,
                    today,
                )
                return saved
            except Exception as exc:
                logger.warning(
                    "MetricsRecorder: save failed for %s: %s", sid, exc
                )
                return None

        return metric

    async def record_batch(
        self,
        db: Any,
        strategies: list[dict[str, Any]],
        verifications: dict[str, dict[str, Any]],
        *,
        metric_date: Optional[date] = None,
    ) -> dict[str, Any]:
        """
        批量记录孵化指标。

        Args:
            db: 数据库连接
            strategies: 策略列表
            verifications: {strategy_id: verification_result} 映射
            metric_date: 指标日期

        Returns:
            批量记录结果摘要
        """
        recorded = 0
        failed = 0

        for strategy in strategies:
            sid = str(strategy.get("id") or "").strip()
            verification = verifications.get(sid, {})
            result = await self.record(
                db, strategy, verification, metric_date=metric_date
            )
            if result is not None:
                recorded += 1
            else:
                failed += 1

        return {
            "total": len(strategies),
            "recorded": recorded,
            "failed": failed,
            "metric_date": str(metric_date or date.today()),
        }

    def _build_metric(
        self,
        *,
        strategy: dict[str, Any],
        verification: dict[str, Any],
        nav_info: dict[str, Any],
        account_id: str,
        metric_date: date,
    ) -> dict[str, Any]:
        """构建孵化指标记录。"""
        # 从验证结果提取
        primary_hit_rate = float(verification.get("primary_hit_rate") or 0.0)
        primary_skill_lcb = float(verification.get("primary_skill_lcb") or 0.0)
        recent_primary_skill_lcb = float(
            verification.get("recent_primary_skill_lcb") or 0.0
        )
        secondary_hit_rate = float(verification.get("secondary_hit_rate") or 0.0)
        secondary_skill_lcb = float(verification.get("secondary_skill_lcb") or 0.0)
        stability_gap = float(verification.get("stability_gap") or 0.0)
        coverage_ratio = float(verification.get("coverage_ratio") or 0.0)
        forward_sharpe = float(verification.get("forward_sharpe") or 0.0)
        forward_ic = float(verification.get("forward_ic") or 0.0)
        recent_primary_hit_rate = float(
            verification.get("recent_primary_hit_rate")
            if verification.get("recent_primary_hit_rate") is not None
            else primary_hit_rate
        )
        primary_n = int(verification.get("primary_effective_n") or 0)
        secondary_n = int(verification.get("secondary_effective_n") or 0)
        total_signals = int(verification.get("total_signals") or primary_n)

        # 从 NAV 信息提取
        total_value = float(nav_info.get("total_value") or 0.0)
        cash = float(nav_info.get("cash") or 0.0)
        market_value = float(nav_info.get("market_value") or 0.0)
        nav = float(nav_info.get("nav") or 1.0)
        daily_return = float(nav_info.get("daily_return") or 0.0)
        max_drawdown = float(nav_info.get("max_drawdown") or 0.0)

        # 决策判定
        decision = self._derive_decision(
            primary_skill_lcb=primary_skill_lcb,
            recent_primary_skill_lcb=recent_primary_skill_lcb,
            stability_gap=stability_gap,
            coverage_ratio=coverage_ratio,
            primary_n=primary_n,
        )

        incubation_account = strategy.get("incubation_account")
        if not isinstance(incubation_account, dict):
            incubation_account = {}
        intake_stage = str(
            strategy.get("_intake_stage")
            or incubation_account.get("stage")
            or strategy.get("status")
            or "incubating"
        )
        diagnostic_observation = intake_stage == "diagnostic"

        return {
            "account_id": account_id,
            "stage": intake_stage,
            "total_value": total_value,
            "cash": cash,
            "market_value": market_value,
            "nav": nav,
            "daily_return": daily_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": forward_sharpe,
            "hit_rate_5d": primary_hit_rate,
            "hit_rate_lcb_5d": primary_skill_lcb,
            "skill_lcb_5d": primary_skill_lcb,
            "hit_rate_10d": secondary_hit_rate,
            "skill_lcb_10d": secondary_skill_lcb,
            "effective_n_5d": primary_n,
            "recent_hit_rate_5d": recent_primary_hit_rate,
            "recent_skill_lcb_5d": recent_primary_skill_lcb,
            "stability_gap_5d": stability_gap,
            "forward_ic_5d": forward_ic,
            "forward_sharpe_5d": forward_sharpe,
            "total_signals": total_signals,
            "coverage_ratio": coverage_ratio,
            "primary_effective_n": primary_n,
            "secondary_effective_n": secondary_n,
            "decision": decision,
            "total_orders": 0,
            "total_trades": 0,
            "metadata": {
                "source": "incubation_factory",
                "intake_stage": intake_stage,
                "diagnostic_observation": diagnostic_observation,
                "profile": verification.get("profile"),
                "primary_horizon": verification.get("primary_horizon"),
                "secondary_horizon": verification.get("secondary_horizon"),
                "coverage_ratio": coverage_ratio,
                "secondary_hit_rate": secondary_hit_rate,
                "secondary_skill_lcb": secondary_skill_lcb,
                "secondary_effective_n": secondary_n,
                "stability_gap": stability_gap,
                "forward_ic": forward_ic,
                "forward_sharpe": forward_sharpe,
                "min_days_remaining": verification.get("min_days_remaining"),
                "min_trades_remaining": verification.get("min_trades_remaining"),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _derive_decision(
        self,
        *,
        primary_skill_lcb: float,
        recent_primary_skill_lcb: float,
        stability_gap: float,
        coverage_ratio: float,
        primary_n: int,
    ) -> str:
        """
        根据指标判定当日决策。

        - promote: 表现优秀，推荐晋升
        - observe: 表现一般，继续观察
        - halt: 表现差，建议暂停
        """
        # 样本不足时继续观察
        if primary_n < 10:
            return "observe"

        # 技能下界为负 → 暂停
        if recent_primary_skill_lcb < -0.03:
            return "halt"

        # 稳定性差 → 暂停
        if stability_gap > 0.10:
            return "halt"

        # 覆盖率太低 → 观察
        if coverage_ratio < 0.25:
            return "observe"

        # 技能下界显著为正 + 稳定 → 推荐晋升
        if (
            primary_skill_lcb > 0.02
            and recent_primary_skill_lcb > 0.0
            and stability_gap <= 0.05
            and coverage_ratio >= 0.60
        ):
            return "promote"

        return "observe"

    async def _get_nav_info(
        self, db: Any, account_id: str, metric_date: date
    ) -> dict[str, Any]:
        """获取 paper account 的 NAV 信息。"""
        if not account_id:
            return {}

        try:
            account = None
            if hasattr(db, "get_paper_account"):
                account = await db.get_paper_account(account_id)
            nav_rows = []
            if hasattr(db, "get_paper_nav_rows"):
                nav_rows = await db.get_paper_nav_rows(account_id, limit=60)
            if nav_rows:
                latest = dict(nav_rows[0] or {})
                total_value = self._safe_float(latest.get("total_value"))
                cash = self._safe_float(latest.get("cash"))
                market_value = self._safe_float(latest.get("market_value"))
                daily_return = self._safe_float(latest.get("daily_return"), None)
                if daily_return is None and len(nav_rows) >= 2:
                    prev_total = self._safe_float(dict(nav_rows[1] or {}).get("total_value"), None)
                    if prev_total and prev_total > 0:
                        daily_return = (total_value - prev_total) / prev_total
                initial_capital = self._safe_float((account or {}).get("initial_capital"))
                if not initial_capital or initial_capital <= 0:
                    initial_capital = self._safe_float(dict(nav_rows[-1] or {}).get("total_value")) or 100000.0
                return {
                    "total_value": total_value,
                    "cash": cash,
                    "market_value": market_value,
                    "nav": total_value / max(initial_capital, 1.0),
                    "daily_return": daily_return or 0.0,
                    "max_drawdown": self._compute_max_drawdown(nav_rows),
                }

            if account:
                total_value = self._safe_float(account.get("total_value"))
                cash = self._safe_float(account.get("current_capital"))
                initial_capital = self._safe_float(account.get("initial_capital")) or 100000.0
                return {
                    "total_value": total_value,
                    "cash": cash,
                    "market_value": total_value - cash,
                    "nav": total_value / max(initial_capital, 1.0),
                    "daily_return": 0.0,
                    "max_drawdown": 0.0,
                }
        except Exception as exc:
            logger.debug("MetricsRecorder: get NAV failed for %s: %s", account_id, exc)

        return {}

    @staticmethod
    def _safe_float(value: Any, default: Any = 0.0) -> Any:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _compute_max_drawdown(cls, nav_rows: list[dict[str, Any]]) -> float:
        values = [
            cls._safe_float(dict(row or {}).get("total_value"))
            for row in reversed(list(nav_rows or []))
        ]
        values = [value for value in values if value > 0]
        if len(values) < 2:
            return 0.0
        peak = values[0]
        max_drawdown = 0.0
        for value in values:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - value) / peak)
        return max_drawdown
