"""P1-B S3: promotion evaluation kernel ownership + fixture parity."""

from __future__ import annotations

from strategy_factory.infrastructure.promotion.dsr_gate import (
    PROMOTION_DSR_MIN_DEFAULT,
    PROMOTION_DSR_MIN_SAMPLE_SIZE,
    PromotionGate,
    PromotionGateVerdict,
    promotion_dsr_gate_enabled,
)
from strategy_factory.infrastructure.promotion.review_outcome import (
    evaluate_promotion_review_outcome,
    score_promotion_review,
)
from strategy_factory.infrastructure.matching.rules import get_limit_ratio, is_trading_time
from strategy_factory.runtime.incubation_phases import (
    INCUBATION_ONCE_PHASES,
    STRATEGY_TIMEOUT_SEC,
    incubation_phase_names,
    required_phase_names,
)
from datetime import datetime


def test_promotion_gate_owned_by_sf() -> None:
    assert PromotionGate.__module__ == "strategy_factory.infrastructure.promotion.dsr_gate"
    assert PROMOTION_DSR_MIN_DEFAULT == 0.60
    assert PROMOTION_DSR_MIN_SAMPLE_SIZE == 30


def _fake_dsr(dsr_value: float):
    def _fn(arr, *, n_trials=1, benchmark_sharpe=0.0, periods_per_year=252.0):
        return {
            "available": True,
            "dsr": dsr_value,
            "observed_sharpe": 1.2,
            "effective_trials": float(n_trials),
            "sample_size": int(len(arr)),
        }

    return _fn


def test_dsr_gate_matrix() -> None:
    gate = PromotionGate(min_sample_size=30)
    low = gate.evaluate([0.01] * 10, n_trials=5, dsr_fn=_fake_dsr(0.99))
    assert low.eligible is False
    assert isinstance(low, PromotionGateVerdict)
    ok = gate.evaluate([0.005] * 40, n_trials=10, dsr_fn=_fake_dsr(0.75))
    assert ok.passed is True and ok.eligible is True
    hold = gate.evaluate([0.001] * 40, n_trials=50, dsr_fn=_fake_dsr(0.40))
    assert hold.passed is False and hold.eligible is True


def test_review_outcome_promote_path() -> None:
    overview = {
        "promotion_ready": True,
        "signal_quality_snapshot": {"status": "strong"},
        "execution_quality_snapshot": {"status": "strong"},
        "hard_gate_result": {"reasons": []},
        "blockers": [],
        "deprecation_risk": False,
    }
    status, rec, blockers = evaluate_promotion_review_outcome(overview)
    assert status == "approved"
    assert rec == "promote"
    assert blockers == []


def test_review_outcome_deprecate_and_watch() -> None:
    dep = evaluate_promotion_review_outcome({"deprecation_risk": True, "blockers": []})
    assert dep[0] == "rejected" and dep[1] == "deprecate"
    watch = evaluate_promotion_review_outcome(
        {
            "promotion_ready": False,
            "signal_quality_snapshot": {"status": "candidate"},
            "execution_quality_snapshot": {"status": "candidate"},
        }
    )
    assert watch[0] == "watch" and watch[1] == "observe"
    assert "signal_quality_snapshot_not_strong" in watch[2]


def test_score_bounds() -> None:
    score = score_promotion_review(
        {
            "signal_quality_snapshot": {"status": "strong"},
            "execution_quality_snapshot": {"status": "strong"},
            "promotion_ready": True,
            "execution_hard_gate_passed": True,
            "blockers": [],
            "risk_flags": [],
            "hard_gate_result": {"reasons": []},
        },
        {"sharpe_ratio": 1.0, "hit_rate_5d": 0.55, "forward_sharpe_5d": 0.8},
    )
    assert 0.0 <= score <= 1.0


def test_matching_rules() -> None:
    assert get_limit_ratio("300001") == 0.20
    assert get_limit_ratio("sh600000") == 0.10
    # Monday 10:00
    assert is_trading_time(datetime(2026, 7, 6, 10, 0)) is True
    assert is_trading_time(datetime(2026, 7, 6, 12, 0)) is False


def test_incubation_phase_table() -> None:
    names = incubation_phase_names()
    assert names[0] == "intake"
    assert "exit_signal_paper_execution" in names
    assert "execution_audit_acceptance" in names
    assert "pipeline" in names
    assert STRATEGY_TIMEOUT_SEC == 30.0
    assert len(INCUBATION_ONCE_PHASES) >= 10
    assert "intake" in required_phase_names()
    from strategy_factory.runtime.incubation_phases import get_phase_timeout, BATCH_TIMEOUT_SEC
    assert get_phase_timeout("intake") == BATCH_TIMEOUT_SEC
    assert get_phase_timeout("alert_check") == STRATEGY_TIMEOUT_SEC


def test_dsr_toggle_default_off(monkeypatch) -> None:
    monkeypatch.delenv("STRATEGY_FACTORY_PROMOTION_DSR_ENABLED", raising=False)
    assert promotion_dsr_gate_enabled() is False
