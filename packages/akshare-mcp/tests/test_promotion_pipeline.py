from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.promotion_pipeline import StrategyPromotionPipelineService


@pytest.mark.asyncio
async def test_promotion_pipeline_prefers_snapshots_and_trace_ledger_for_observe(monkeypatch):
    import akshare_mcp.services.strategy_lifecycle_shared as lifecycle_mod

    async def _fake_overview(_db, _strategy):
        return {
            "promotion_ready": True,
            "deprecation_risk": False,
            "signal_quality_snapshot": {"status": "strong"},
            "execution_quality_snapshot": {"status": "weak"},
            "prediction_trace_ledger": {
                "contract_version": "strategy_factory.prediction_trace_ledger.v2",
                "prediction_trace_id": "pred_trace_1",
                "evidence_gap_codes": ["missing_actual_fill", "missing_pnl_audit_summary"],
            },
            "hard_gate_result": {
                "passed": False,
                "reasons": ["execution_audit_gate:failed_metrics"],
            },
            "execution_hard_gate_passed": False,
            "execution_audit_gate_status": "failed_metrics",
            "blockers": ["legacy_blocker_should_not_drive_outcome"],
            "risk_flags": [],
            "validation_grade": "B",
            "strict_incubation_ready": True,
            "live_candidate_ready": True,
            "promotion_gate_status": "failed_metrics",
            "total_signals": 96,
            "observed_forward_days": [1, 5, 10, 20],
        }

    monkeypatch.setattr(lifecycle_mod, "build_incubation_overview", _fake_overview)

    async def _save_review(payload):
        return {"id": 1, **payload}

    db = MagicMock()
    db.get_latest_strategy_incubation_metric = AsyncMock(
        return_value={
            "stage": "incubating",
            "sharpe_ratio": 1.08,
            "hit_rate_5d": 0.61,
            "forward_sharpe_5d": 0.44,
        }
    )
    db.get_strategy_incubation_account = AsyncMock(return_value={"account_id": "acct_obs", "stage": "incubating"})
    db.save_strategy_promotion_review = AsyncMock(side_effect=_save_review)
    db.save_strategy_domain_event = AsyncMock()

    result = await StrategyPromotionPipelineService().review(
        db,
        {"id": "sid_obs", "status": "incubating"},
    )

    review = result["review"]
    assert review["status"] == "watch"
    assert review["recommendation"] == "observe"
    assert "execution_quality_snapshot:weak" in review["blockers"]
    assert "missing_actual_fill" in review["blockers"]
    assert review["summary"]["signal_quality_snapshot"]["status"] == "strong"
    assert review["summary"]["execution_quality_snapshot"]["status"] == "weak"
    assert review["summary"]["prediction_trace_ledger"]["prediction_trace_id"] == "pred_trace_1"
    assert "missing_actual_fill" in review["summary"]["evidence_gap_codes"]


@pytest.mark.asyncio
async def test_promotion_pipeline_promotes_when_snapshots_and_trace_ledger_are_ready(monkeypatch):
    import akshare_mcp.services.strategy_lifecycle_shared as lifecycle_mod

    async def _fake_overview(_db, _strategy):
        return {
            "promotion_ready": True,
            "deprecation_risk": False,
            "signal_quality_snapshot": {"status": "strong"},
            "execution_quality_snapshot": {"status": "strong"},
            "prediction_trace_ledger": {
                "contract_version": "strategy_factory.prediction_trace_ledger.v2",
                "prediction_trace_id": "pred_trace_ready",
                "evidence_gap_codes": [],
            },
            "hard_gate_result": {
                "passed": True,
                "reasons": [],
            },
            "execution_hard_gate_passed": True,
            "execution_audit_gate_status": "passed",
            "blockers": [],
            "risk_flags": [],
            "validation_grade": "B",
            "strict_incubation_ready": True,
            "live_candidate_ready": True,
            "promotion_gate_status": "passed",
            "total_signals": 128,
            "observed_forward_days": [1, 5, 10, 20],
        }

    monkeypatch.setattr(lifecycle_mod, "build_incubation_overview", _fake_overview)

    async def _save_review(payload):
        return {"id": 2, **payload}

    db = MagicMock()
    db.get_latest_strategy_incubation_metric = AsyncMock(
        return_value={
            "stage": "incubating",
            "sharpe_ratio": 1.18,
            "hit_rate_5d": 0.66,
            "forward_sharpe_5d": 0.72,
        }
    )
    db.get_strategy_incubation_account = AsyncMock(return_value={"account_id": "acct_ok", "stage": "incubating"})
    db.save_strategy_promotion_review = AsyncMock(side_effect=_save_review)
    db.save_strategy_domain_event = AsyncMock()

    result = await StrategyPromotionPipelineService().review(
        db,
        {"id": "sid_ok", "status": "incubating"},
    )

    review = result["review"]
    assert review["status"] == "approved"
    assert review["recommendation"] == "promote"
    assert review["summary"]["signal_quality_snapshot"]["status"] == "strong"
    assert review["summary"]["execution_quality_snapshot"]["status"] == "strong"
    assert review["summary"]["evidence_gap_codes"] == []
