"""P1-B S3 host re-export: PromotionGate + pipeline pure methods."""

from __future__ import annotations

from akshare_mcp.services.incubation_factory.promotion_gate import (
    PromotionGate as HostGate,
    PromotionGateVerdict as HostVerdict,
)
from akshare_mcp.services.promotion_pipeline import StrategyPromotionPipelineService
from strategy_factory.infrastructure.promotion.dsr_gate import (
    PromotionGate as SfGate,
    PromotionGateVerdict as SfVerdict,
)
from strategy_factory.infrastructure.promotion.review_outcome import (
    evaluate_promotion_review_outcome,
    score_promotion_review,
)


def test_promotion_gate_class_is_sf() -> None:
    assert HostGate is SfGate
    assert HostVerdict is SfVerdict
    assert HostGate.__module__ == "strategy_factory.infrastructure.promotion.dsr_gate"


def test_pipeline_delegates_outcome_and_score() -> None:
    overview = {
        "promotion_ready": True,
        "signal_quality_snapshot": {"status": "strong"},
        "execution_quality_snapshot": {"status": "passed"},
        "hard_gate_result": {"reasons": []},
        "blockers": [],
        "deprecation_risk": False,
    }
    assert StrategyPromotionPipelineService._resolve_review_outcome(overview) == (
        evaluate_promotion_review_outcome(overview)
    )
    assert StrategyPromotionPipelineService._score(overview, None) == score_promotion_review(
        overview, None
    )
