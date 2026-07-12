"""Promotion evaluation infrastructure owned by Strategy Factory."""

from .dsr_gate import (
    PROMOTION_DSR_MIN_DEFAULT,
    PROMOTION_DSR_MIN_SAMPLE_SIZE,
    PromotionGate,
    PromotionGateVerdict,
    promotion_dsr_gate_enabled,
)
from .review_outcome import (
    evaluate_promotion_review_outcome,
    score_promotion_review,
)

__all__ = [
    "PROMOTION_DSR_MIN_DEFAULT",
    "PROMOTION_DSR_MIN_SAMPLE_SIZE",
    "PromotionGate",
    "PromotionGateVerdict",
    "evaluate_promotion_review_outcome",
    "promotion_dsr_gate_enabled",
    "score_promotion_review",
]
