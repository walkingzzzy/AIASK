"""策略工厂分级门禁兼容导出。"""

from strategy_factory.application.quality_gates import (
    GateResult,
    build_completed_gate_3_report,
    build_legacy_gate_report,
    build_pending_gate_3_report,
    finalize_gate_report,
    gate_0_structural,
    gate_1_fast_screen,
    run_gated_filter,
    run_gated_submission_pipeline,
)
from strategy_factory.domain.constants import (
    BACKTEST_CONCURRENCY,
    GATE1_PASS_RATIO,
    GATE1_REPRESENTATIVE_COUNT,
    GATE1_SHARPE_MIN,
    REPRESENTATIVE_STOCKS,
)

__all__ = [
    "GateResult",
    "gate_0_structural",
    "gate_1_fast_screen",
    "build_pending_gate_3_report",
    "build_completed_gate_3_report",
    "run_gated_filter",
    "run_gated_submission_pipeline",
    "build_legacy_gate_report",
    "finalize_gate_report",
    "BACKTEST_CONCURRENCY",
    "GATE1_PASS_RATIO",
    "GATE1_REPRESENTATIVE_COUNT",
    "GATE1_SHARPE_MIN",
    "REPRESENTATIVE_STOCKS",
]
