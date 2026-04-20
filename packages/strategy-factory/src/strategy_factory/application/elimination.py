"""策略工厂上架策略淘汰检查。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import List

from .utils import _update_strategy_status as _local_update_strategy_status
from ..domain.constants import ELIMINATION_CONCURRENCY

logger = logging.getLogger(__name__)

async def _update_strategy_status(*args, **kwargs):
    return await _local_update_strategy_status(*args, **kwargs)


class EliminationChecker:
    """检查已上架策略是否应该淘汰。"""

    _REGIME_MAP = {
        "momentum": ("greed", "extreme_greed"),
        "growth_factor": ("greed", "extreme_greed", "neutral"),
        "value_factor": ("fear", "extreme_fear", "neutral"),
        "rsi": ("fear", "extreme_fear"),
        "macro_timing": ("fear", "extreme_fear", "neutral"),
        "ma_cross": ("neutral", "greed", "extreme_greed"),
        "quality_factor": ("neutral", "greed", "extreme_greed"),
        "multi_factor": ("neutral", "fear", "greed", "extreme_fear", "extreme_greed"),
    }

    async def check(self, db, current_fg_level: str = "neutral") -> List[dict]:
        eliminated: List[dict] = []
        try:
            listed = await db.list_strategies("listed", limit=500)
        except Exception:
            return eliminated

        sem = asyncio.Semaphore(ELIMINATION_CONCURRENCY)

        async def _check_one(strategy: dict) -> dict | None:
            async with sem:
                return await self._check_strategy(db, strategy, current_fg_level)

        results = await asyncio.gather(*[_check_one(strategy) for strategy in list(listed or [])], return_exceptions=True)
        for item in results:
            if isinstance(item, BaseException):
                logger.debug("EliminationChecker: task failed: %s", item)
                continue
            if item:
                eliminated.append(item)
        return eliminated

    async def _check_strategy(self, db, strategy: dict, current_fg_level: str) -> dict | None:
        try:
            red_flags: List[str] = []
            metrics_list = await db.get_strategy_metrics(strategy["id"])
            period_priority = {"all": 0, "backtest": 1}
            period_candidates = [row for row in metrics_list if row.get("period") in period_priority]
            period_candidates.sort(key=lambda row: period_priority.get(row.get("period"), 99))
            backtest_metrics = period_candidates[0] if period_candidates else {}
            validation_metrics = next((row for row in metrics_list if row.get("period") == "validation"), {})
            risk_metrics = next((row for row in metrics_list if row.get("period") == "risk"), {})
            quality_report = None
            get_quality_report = getattr(db, "get_strategy_quality_report", None)
            if callable(get_quality_report):
                try:
                    quality_report = await get_quality_report(strategy["id"])
                except TypeError:
                    quality_report = None
            if quality_report:
                validation_metrics = quality_report.get("validation_report") or validation_metrics
                risk_metrics = quality_report.get("risk_report") or risk_metrics

            max_drawdown = abs(float(backtest_metrics.get("max_drawdown") or 0))
            sharpe_ratio = float(backtest_metrics.get("sharpe_ratio") or 0)
            win_rate = float(backtest_metrics.get("win_rate") or 0)
            validation_grade = validation_metrics.get("grade") or validation_metrics.get("rating", {}).get("grade")
            var_percent = float(risk_metrics.get("var_percent") or 0)
            cvar_percent = float(risk_metrics.get("cvar_percent") or 0)
            stress_loss_percent = float(risk_metrics.get("stress_loss_percent") or 0)

            if max_drawdown > 0.30:
                red_flags.append(f"回撤{max_drawdown:.1%}>30%")
            if sharpe_ratio < 0:
                red_flags.append(f"Sharpe {sharpe_ratio:.2f}<0")
            if 0 < win_rate < 0.30:
                red_flags.append(f"胜率{win_rate:.1%}<30%")
            if validation_grade == "D":
                red_flags.append("验证评级为D")
            if var_percent > 4.0:
                red_flags.append(f"VaR {var_percent:.2f}%>4%")
            if cvar_percent > 6.0:
                red_flags.append(f"CVaR {cvar_percent:.2f}%>6%")
            if stress_loss_percent <= -25.0:
                red_flags.append(f"压力测试损失{stress_loss_percent:.1f}%")

            try:
                signal_stats = await db.get_signal_stats(strategy["id"])
                hit_rates = signal_stats.get("hit_rate", {})
                total_signals = signal_stats.get("total_signals", 0)
                if total_signals >= 10:
                    hit_rate_5d = hit_rates.get(5, hit_rates.get("5", None))
                    if hit_rate_5d is not None and float(hit_rate_5d) < 0.30:
                        red_flags.append(f"5日信号命中率{float(hit_rate_5d):.1%}<30%")
            except Exception:
                pass

            strategy_type = strategy.get("strategy_type", "")
            suitable_regimes = self._REGIME_MAP.get(strategy_type)
            if suitable_regimes and current_fg_level and current_fg_level not in suitable_regimes:
                red_flags.append(f"{strategy_type}策略不适合当前{current_fg_level}环境")

            fatal = max_drawdown > 0.30
            should_eliminate = fatal or (len(red_flags) >= 2)

            if should_eliminate and red_flags:
                reason = "淘汰: " + "; ".join(red_flags)
                await _update_strategy_status(
                    db,
                    strategy["id"],
                    "deprecated",
                    actor_id="elimination_checker",
                    reason="elimination_checker_triggered",
                    metadata={"red_flags": red_flags, "fg_level": current_fg_level},
                )
                try:
                    await db.save_elimination_log(strategy["id"], date.today(), red_flags, reason)
                except Exception:
                    pass
                return {"id": strategy["id"], "red_flags": red_flags, "reason": reason}
        except Exception as exc:
            logger.debug("EliminationChecker: error checking %s: %s", strategy.get("id"), exc)
        return None
