"""质量门报告工具兼容导出。"""

from strategy_factory.application.quality_reporting import (
    PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED,
    build_quality_report,
    has_only_statistical_gate_failures,
    is_factory_ai_prototype_strategy,
    maybe_grant_provisional_incubation,
    normalize_quality_gate_result,
    quality_gate_reason_code,
    safe_metric_value,
)

__all__ = [
    "PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED",
    "quality_gate_reason_code",
    "normalize_quality_gate_result",
    "is_factory_ai_prototype_strategy",
    "has_only_statistical_gate_failures",
    "safe_metric_value",
    "maybe_grant_provisional_incubation",
    "build_quality_report",
]
