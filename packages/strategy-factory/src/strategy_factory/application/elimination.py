"""策略工厂上架策略淘汰检查。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from .utils import _update_strategy_status as _local_update_strategy_status
from ..domain.constants import (
    ELIMINATION_CONCURRENCY,
    ELIMINATION_DEFAULT_THRESHOLDS,
    ELIMINATION_THRESHOLDS_BY_STRATEGY_TYPE,
)

logger = logging.getLogger(__name__)


async def _update_strategy_status(*args, **kwargs):
    return await _local_update_strategy_status(*args, **kwargs)


def _resolve_elimination_thresholds(strategy_type: str) -> dict:
    """按策略类型解析淘汰阈值，缺失类型时回退到 default."""
    strategy_type = str(strategy_type or "").strip().lower()
    base = dict(ELIMINATION_DEFAULT_THRESHOLDS)
    overrides = ELIMINATION_THRESHOLDS_BY_STRATEGY_TYPE.get(strategy_type, {})
    base.update(overrides)
    return base


class EliminationDecision:
    """渐进式淘汰决策 — 映射到 runtime control 而非新增策略生命周期状态."""

    ACTIVE = "active"
    WARNING = "warning"
    OBSERVE_ONLY = "observe_only"
    EXIT_ONLY = "exit_only"
    RETIRED = "retired"

    _SEVERITY_ORDER = [ACTIVE, WARNING, OBSERVE_ONLY, EXIT_ONLY, RETIRED]

    @classmethod
    def most_severe(cls, *decisions: str) -> str:
        idx = max(
            (cls._SEVERITY_ORDER.index(d) if d in cls._SEVERITY_ORDER else 0)
            for d in decisions
        )
        return cls._SEVERITY_ORDER[idx]

    @classmethod
    def to_runtime_control(cls, decision: str) -> Optional[str]:
        """将淘汰决策映射到 runtime control 模式."""
        return {
            cls.ACTIVE: None,
            cls.WARNING: None,
            cls.OBSERVE_ONLY: "throttled",
            cls.EXIT_ONLY: "halted",
            cls.RETIRED: "manual_stop",
        }.get(decision)


class EliminationChecker:
    """检查已上架策略是否应该淘汰。"""

    # 策略类型 → 适用恐贪环境（保留原 tuple 语义）
    _REGIME_MAP: Dict[str, tuple] = {
        # ── 原有 9 种 ──
        "momentum": ("greed", "extreme_greed"),
        "growth_factor": ("greed", "extreme_greed", "neutral"),
        "value_factor": ("fear", "extreme_fear", "neutral"),
        "rsi": ("fear", "extreme_fear"),
        "macro_timing": ("fear", "extreme_fear", "neutral"),
        "ma_cross": ("neutral", "greed", "extreme_greed"),
        "quality_factor": ("neutral", "greed", "extreme_greed"),
        "multi_factor": ("neutral", "fear", "greed", "extreme_fear", "extreme_greed"),
        # ── 补全 6 种缺失映射 (Gap 4) ──
        "volatility_breakout": ("neutral", "greed", "extreme_greed"),
        "event_structure_breakout": ("neutral", "greed", "extreme_greed"),
        "gap_fill": ("fear", "extreme_fear", "neutral"),
        "mean_reversion_short": ("fear", "extreme_fear", "neutral"),
        "sector_rotation": ("neutral", "greed"),
        "north_capital_track": ("neutral", "greed"),
        "margin_divergence": ("fear", "neutral"),
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

        results = await asyncio.gather(
            *[_check_one(strategy) for strategy in list(listed or [])],
            return_exceptions=True,
        )
        for item in results:
            if isinstance(item, BaseException):
                logger.debug("EliminationChecker: task failed: %s", item)
                continue
            if item:
                eliminated.append(item)
        return eliminated

    async def _check_strategy(
        self, db, strategy: dict, current_fg_level: str
    ) -> Optional[dict]:
        try:
            strategy_type = str(strategy.get("strategy_type", "")).strip().lower()
            thresholds = _resolve_elimination_thresholds(strategy_type)

            red_flags: List[str] = []
            metrics_list = await db.get_strategy_metrics(strategy["id"])
            period_priority = {"all": 0, "backtest": 1}
            period_candidates = [
                row for row in metrics_list if row.get("period") in period_priority
            ]
            period_candidates.sort(
                key=lambda row: period_priority.get(row.get("period"), 99)
            )
            backtest_metrics = period_candidates[0] if period_candidates else {}
            validation_metrics = next(
                (row for row in metrics_list if row.get("period") == "validation"), {}
            )
            risk_metrics = next(
                (row for row in metrics_list if row.get("period") == "risk"), {}
            )
            quality_report = None
            get_quality_report = getattr(db, "get_strategy_quality_report", None)
            if callable(get_quality_report):
                try:
                    quality_report = await get_quality_report(strategy["id"])
                except TypeError:
                    quality_report = None
            if quality_report:
                validation_metrics = (
                    quality_report.get("validation_report") or validation_metrics
                )
                risk_metrics = quality_report.get("risk_report") or risk_metrics

            max_drawdown = abs(float(backtest_metrics.get("max_drawdown") or 0))
            sharpe_ratio = float(backtest_metrics.get("sharpe_ratio") or 0)
            win_rate = float(backtest_metrics.get("win_rate") or 0)
            validation_grade = (
                validation_metrics.get("grade")
                or validation_metrics.get("rating", {}).get("grade")
            )
            var_percent = float(risk_metrics.get("var_percent") or 0)
            cvar_percent = float(risk_metrics.get("cvar_percent") or 0)
            stress_loss_percent = float(
                risk_metrics.get("stress_loss_percent") or 0
            )

            # ── 渐进式淘汰判定（使用常量阈值）────────────────────────
            decision = EliminationDecision.ACTIVE

            if max_drawdown > thresholds["max_drawdown_max"]:
                red_flags.append(
                    f"回撤{max_drawdown:.1%}>{thresholds['max_drawdown_max']:.0%}"
                )
            if sharpe_ratio < thresholds["sharpe_min"]:
                red_flags.append(f"Sharpe {sharpe_ratio:.2f}<{thresholds['sharpe_min']}")
            if 0 < win_rate < thresholds["win_rate_min"]:
                red_flags.append(
                    f"胜率{win_rate:.1%}<{thresholds['win_rate_min']:.0%}"
                )
                decision = EliminationDecision.WARNING
            if validation_grade == "D":
                red_flags.append("验证评级为D")
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.WARNING
                )
            if var_percent > thresholds["var_percent_max"]:
                red_flags.append(
                    f"VaR {var_percent:.2f}%>{thresholds['var_percent_max']}%"
                )
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.WARNING
                )
            if cvar_percent > thresholds["cvar_percent_max"]:
                red_flags.append(
                    f"CVaR {cvar_percent:.2f}%>{thresholds['cvar_percent_max']}%"
                )
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.WARNING
                )
            if stress_loss_percent <= thresholds["stress_loss_percent_min"]:
                red_flags.append(
                    f"压力测试损失{stress_loss_percent:.1f}%"
                )
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.WARNING
                )

            # ── VaR/CVaR 严重超标升级 ─────────────────────────────
            if var_percent > thresholds["var_percent_max"] * 2.0:
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.OBSERVE_ONLY
                )
            if cvar_percent > thresholds["cvar_percent_max"] * 2.0:
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.OBSERVE_ONLY
                )

            if max_drawdown > thresholds["max_drawdown_max"]:
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.OBSERVE_ONLY
                )
            if sharpe_ratio < thresholds["sharpe_min"] and max_drawdown > thresholds[
                "max_drawdown_max"
            ]:
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.EXIT_ONLY
                )
            if (
                max_drawdown > thresholds["max_drawdown_max"] * 1.5
                or win_rate < thresholds["win_rate_min"] * 0.5
            ):
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.RETIRED
                )

            try:
                signal_stats = await db.get_signal_stats(strategy["id"])
                hit_rates = signal_stats.get("hit_rate", {})
                total_signals = signal_stats.get("total_signals", 0)
                if total_signals >= 10:
                    hit_rate_5d = hit_rates.get(5, hit_rates.get("5", None))
                    if hit_rate_5d is not None and float(hit_rate_5d) < thresholds[
                        "hit_rate_5d_min"
                    ]:
                        red_flags.append(
                            f"5日信号命中率{float(hit_rate_5d):.1%}<{thresholds['hit_rate_5d_min']:.0%}"
                        )
                        decision = EliminationDecision.most_severe(
                            decision, EliminationDecision.WARNING
                        )
            except Exception:
                pass

            # ── 恐贪环境不匹配检查 ──────────────────────────────────
            suitable_regimes = self._REGIME_MAP.get(strategy_type)
            if (
                suitable_regimes
                and current_fg_level
                and current_fg_level not in suitable_regimes
            ):
                red_flags.append(
                    f"{strategy_type}策略不适合当前{current_fg_level}环境"
                )
                decision = EliminationDecision.most_severe(
                    decision, EliminationDecision.WARNING
                )

            # ── 渐进式动作执行 ──────────────────────────────────────
            if decision == EliminationDecision.ACTIVE and not red_flags:
                return None

            if decision == EliminationDecision.RETIRED:
                return await self._execute_retirement(
                    db, strategy, red_flags, current_fg_level
                )
            elif decision == EliminationDecision.EXIT_ONLY:
                return await self._apply_runtime_control(
                    db,
                    strategy,
                    decision,
                    red_flags,
                    current_fg_level,
                    strategy_status="suspended",
                )
            elif decision == EliminationDecision.OBSERVE_ONLY:
                return await self._apply_runtime_control(
                    db,
                    strategy,
                    decision,
                    red_flags,
                    current_fg_level,
                    strategy_status=None,
                )
            elif decision == EliminationDecision.WARNING:
                return await self._record_warning(
                    db, strategy, red_flags, current_fg_level
                )

            return None

        except Exception as exc:
            logger.debug(
                "EliminationChecker: error checking %s: %s", strategy.get("id"), exc
            )
        return None

    async def _execute_retirement(
        self,
        db,
        strategy: dict,
        red_flags: List[str],
        current_fg_level: str,
    ) -> dict:
        """执行完全退役：状态 → deprecated."""
        reason = "淘汰: " + "; ".join(red_flags)
        await _update_strategy_status(
            db,
            strategy["id"],
            "deprecated",
            actor_id="elimination_checker",
            reason="elimination_checker_triggered",
            metadata={"red_flags": red_flags, "fg_level": current_fg_level},
        )
        await self._save_elimination_log(db, strategy["id"], red_flags, reason)
        return {"id": strategy["id"], "red_flags": red_flags, "reason": reason, "decision": "retired"}

    async def _apply_runtime_control(
        self,
        db,
        strategy: dict,
        decision: str,
        red_flags: List[str],
        current_fg_level: str,
        *,
        strategy_status: Optional[str] = None,
    ) -> dict:
        """渐进降级：通过 runtime control 限制交易，不直接 deprecated."""
        reason = "; ".join(red_flags)
        control_mode = EliminationDecision.to_runtime_control(decision)

        # 写入 domain event 供 governance monitor 消费
        if hasattr(db, "save_strategy_domain_event"):
            try:
                await db.save_strategy_domain_event({
                    "strategy_id": strategy["id"],
                    "aggregate_type": "strategy_elimination",
                    "aggregate_id": strategy["id"],
                    "event_type": f"elimination.{decision}",
                    "source": "elimination_checker",
                    "severity": "warning" if decision != "retired" else "critical",
                    "payload": {
                        "decision": decision,
                        "red_flags": red_flags,
                        "fg_level": current_fg_level,
                        "runtime_control_mode": control_mode,
                    },
                })
            except Exception:
                pass

        # 更新 runtime control（如果 DB 支持）
        if control_mode and hasattr(db, "save_strategy_runtime_control"):
            try:
                # throttled/halted/manual_stop 使用 'engaged' 与系统控制面语义一致
                control_status = "engaged"
                await db.save_strategy_runtime_control({
                    "strategy_id": str(strategy["id"]),
                    "control_mode": control_mode,
                    "status": control_status,
                    "source": "elimination_checker",
                    "trigger_event_type": f"elimination.{decision}",
                    "reason": f"elimination_checker:{decision}",
                    "metadata": {"red_flags": red_flags, "decision": decision},
                })
            except Exception:
                pass

        # 仅在需要时变更策略状态
        if strategy_status:
            await _update_strategy_status(
                db,
                strategy["id"],
                strategy_status,
                actor_id="elimination_checker",
                reason=f"elimination_checker_{decision}",
                metadata={"red_flags": red_flags, "fg_level": current_fg_level},
            )

        await self._save_elimination_log(db, strategy["id"], red_flags, reason)
        return {
            "id": strategy["id"],
            "red_flags": red_flags,
            "reason": reason,
            "decision": decision,
        }

    async def _record_warning(
        self,
        db,
        strategy: dict,
        red_flags: List[str],
        current_fg_level: str,
    ) -> Optional[dict]:
        """记录黄牌警告，不改变策略状态或 runtime control."""
        reason = "警告: " + "; ".join(red_flags)
        if hasattr(db, "save_strategy_domain_event"):
            try:
                await db.save_strategy_domain_event({
                    "strategy_id": strategy["id"],
                    "aggregate_type": "strategy_elimination",
                    "aggregate_id": strategy["id"],
                    "event_type": "elimination.warning",
                    "source": "elimination_checker",
                    "severity": "warning",
                    "payload": {
                        "decision": "warning",
                        "red_flags": red_flags,
                        "fg_level": current_fg_level,
                    },
                })
            except Exception:
                pass
        await self._save_elimination_log(db, strategy["id"], red_flags, reason)
        return {
            "id": strategy["id"],
            "red_flags": red_flags,
            "reason": reason,
            "decision": "warning",
        }

    async def _save_elimination_log(
        self, db, strategy_id: str, red_flags: List[str], reason: str
    ) -> None:
        try:
            await db.save_elimination_log(
                strategy_id, date.today(), red_flags, reason
            )
        except Exception:
            pass
