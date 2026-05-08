"""极端行情压力测试 (Gap 6).

对候选策略在历史极端行情场景下进行压力回测，
结果写入 risk_report，供 submission gate 和 promotion review 消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 历史极端行情场景定义
STRESS_SCENARIOS: Dict[str, dict] = {
    "2015_crash": {
        "start": "2015-06-12",
        "end": "2015-08-26",
        "description": "2015年股灾",
        "market": "A股",
    },
    "2016_circuit_breaker": {
        "start": "2016-01-04",
        "end": "2016-01-07",
        "description": "熔断机制暴跌",
        "market": "A股",
    },
    "2018_trade_war": {
        "start": "2018-03-22",
        "end": "2018-10-19",
        "description": "中美贸易战下跌",
        "market": "A股",
    },
    "2020_covid": {
        "start": "2020-01-20",
        "end": "2020-03-23",
        "description": "新冠疫情冲击",
        "market": "A股",
    },
    "2024_microcap_crisis": {
        "start": "2024-01-29",
        "end": "2024-02-05",
        "description": "微盘股流动性危机",
        "market": "A股",
    },
}

# 压力测试通过阈值
STRESS_PASS_THRESHOLDS = {
    "mdd_max": 0.35,       # 最大回撤不超过 35%
    "sharpe_min": -3.0,    # Sharpe 不低于 -3
    "max_fail_scenarios": 1,  # 最多允许 1 个场景失败
}


@dataclass
class StressScenarioResult:
    scenario_name: str
    description: str
    mdd: float = 0.0
    sharpe: float = 0.0
    total_return: float = 0.0
    passed: bool = True
    error: Optional[str] = None
    evidence_mode: str = "historical_backtest"

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "description": self.description,
            "mdd": round(self.mdd, 4),
            "sharpe": round(self.sharpe, 4),
            "total_return": round(self.total_return, 4),
            "passed": self.passed,
            "error": self.error,
            "evidence_mode": self.evidence_mode,
        }


@dataclass
class StressTestResult:
    strategy_id: str
    scenarios: List[StressScenarioResult] = field(default_factory=list)
    overall_verdict: str = "pass"
    evidence_mode: str = "historical_backtest"
    diagnostic_only: bool = False

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.scenarios if not s.passed)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "failed_count": self.failed_count,
            "total_scenarios": len(self.scenarios),
            "overall_verdict": self.overall_verdict,
            "evidence_mode": self.evidence_mode,
            "diagnostic_only": self.diagnostic_only,
        }

    def to_risk_report_fields(self) -> dict:
        """映射为 risk_report 可消费的字段."""
        scenario_losses = [s.mdd for s in self.scenarios]
        return {
            "stress_scenarios": [s.to_dict() for s in self.scenarios],
            "stress_loss_percent": round(
                max(scenario_losses) * -100.0, 2
            ) if scenario_losses else 0.0,
            "stress_worst_scenario": max(
                self.scenarios, key=lambda s: s.mdd
            ).scenario_name if self.scenarios else None,
            "stress_overall_verdict": self.overall_verdict,
            "stress_failed_count": self.failed_count,
            "stress_evidence_mode": self.evidence_mode,
            "stress_diagnostic_only": self.diagnostic_only,
        }

    def to_quality_report_fields(self) -> dict:
        """映射为 quality_report 可消费的字段."""
        return {
            "stress_test_passed": self.overall_verdict != "reject",
            "stress_test_verdict": self.overall_verdict,
            "stress_test_scenario_count": len(self.scenarios),
            "stress_test_failed_count": self.failed_count,
            "stress_test_evidence_mode": self.evidence_mode,
            "stress_test_diagnostic_only": self.diagnostic_only,
        }


async def run_stress_test(
    backtest_fn: Callable,
    strategy: dict,
    *,
    scenarios: Optional[List[str]] = None,
    mdd_max: float = STRESS_PASS_THRESHOLDS["mdd_max"],
    sharpe_min: float = STRESS_PASS_THRESHOLDS["sharpe_min"],
    max_fail_scenarios: int = STRESS_PASS_THRESHOLDS["max_fail_scenarios"],
) -> StressTestResult:
    """在指定压力场景下回测策略.

    Args:
        backtest_fn: async callable(strategy, start_date, end_date) -> dict
        strategy: 策略 dict
        scenarios: 要测试的场景名列表，默认全部
        mdd_max: 单场景最大允许回撤
        sharpe_min: 单场景最小允许 Sharpe
        max_fail_scenarios: 最多允许的失败场景数
    """
    strategy_id = str(strategy.get("id") or "unknown")
    scenario_names = scenarios or list(STRESS_SCENARIOS.keys())
    results: List[StressScenarioResult] = []

    for name in scenario_names:
        scenario_def = STRESS_SCENARIOS.get(name)
        if not scenario_def:
            results.append(StressScenarioResult(
                scenario_name=name,
                description="unknown",
                passed=True,
                error=f"Unknown scenario: {name}",
                evidence_mode="historical_backtest",
            ))
            continue

        try:
            bt_result = await backtest_fn(
                strategy,
                start_date=scenario_def["start"],
                end_date=scenario_def["end"],
            )
            bt_dict = dict(bt_result or {})
            mdd = abs(float(bt_dict.get("max_drawdown") or 0))
            sharpe = float(bt_dict.get("sharpe_ratio") or 0)
            total_return = float(bt_dict.get("total_return") or 0)

            passed = mdd < mdd_max and sharpe > sharpe_min
            results.append(StressScenarioResult(
                scenario_name=name,
                description=scenario_def["description"],
                mdd=mdd,
                sharpe=sharpe,
                total_return=total_return,
                passed=passed,
                evidence_mode="historical_backtest",
            ))
        except Exception as exc:
            results.append(StressScenarioResult(
                scenario_name=name,
                description=scenario_def["description"],
                passed=False,
                error=str(exc),
                evidence_mode="historical_backtest",
            ))

    failed = sum(1 for r in results if not r.passed)
    if failed == 0:
        verdict = "pass"
    elif failed <= max_fail_scenarios:
        verdict = "review"
    else:
        verdict = "reject"

    return StressTestResult(
        strategy_id=strategy_id,
        scenarios=results,
        overall_verdict=verdict,
        evidence_mode="historical_backtest",
        diagnostic_only=False,
    )


async def run_stress_test_simple(
    strategy: dict,
    *,
    scenarios: Optional[List[str]] = None,
    backtest_metrics: Optional[dict] = None,
    backtest_fn: Optional[Callable] = None,
) -> StressTestResult:
    """压力测试：优先使用 backtest_fn 做真实历史场景回测，否则降级到指标比较.

    当 backtest_fn 可用时，委托给 run_stress_test 按各历史区间重跑回测；
    否则基于已有 backtest_metrics 做代理诊断，并强制进入 review。
    """
    # 有 backtest_fn 时做真实历史场景回测
    if backtest_fn is not None:
        return await run_stress_test(
            backtest_fn=backtest_fn,
            strategy=strategy,
            scenarios=scenarios,
        )

    strategy_id = str(strategy.get("id") or "unknown")
    scenario_names = scenarios or list(STRESS_SCENARIOS.keys())
    results: List[StressScenarioResult] = []

    bt = dict(backtest_metrics or {})
    mdd = abs(float(bt.get("max_drawdown") or 0))
    sharpe = float(bt.get("sharpe_ratio") or 0)
    total_return = float(bt.get("total_return") or 0)

    for name in scenario_names:
        scenario_def = STRESS_SCENARIOS.get(name)
        if not scenario_def:
            results.append(StressScenarioResult(
                scenario_name=name,
                description="unknown",
                error=f"Unknown scenario: {name}",
                evidence_mode="backtest_metrics_proxy",
            ))
            continue

        # 基于已有回测指标判断是否在压力场景中存活
        scenario_mdd = mdd
        scenario_sharpe = sharpe
        scenario_return = total_return

        passed = (
            scenario_mdd < STRESS_PASS_THRESHOLDS["mdd_max"]
            and scenario_sharpe > STRESS_PASS_THRESHOLDS["sharpe_min"]
        )
        error = None
        if not strategy.get("id"):
            error = "missing_strategy_id"
            passed = False
        if not strategy.get("strategy_type"):
            error = (error or "") + " missing_strategy_type"
            passed = False

        results.append(StressScenarioResult(
            scenario_name=name,
            description=scenario_def["description"],
            mdd=round(scenario_mdd, 4),
            sharpe=round(scenario_sharpe, 4),
            total_return=round(scenario_return, 4),
            passed=passed,
            error=error,
            evidence_mode="backtest_metrics_proxy",
        ))

    failed = sum(1 for r in results if not r.passed)
    verdict = "reject" if failed > STRESS_PASS_THRESHOLDS["max_fail_scenarios"] else "review"

    return StressTestResult(
        strategy_id=strategy_id,
        scenarios=results,
        overall_verdict=verdict,
        evidence_mode="backtest_metrics_proxy",
        diagnostic_only=True,
    )
