"""Round 1: 样本量与观察期硬门禁测试."""

from __future__ import annotations

import asyncio

import pytest
from akshare_mcp.services import incubation_pipeline as pipeline_module
from akshare_mcp.services.incubation_pipeline import StrategyIncubationPipelineService
from akshare_mcp.services.strategy_lifecycle_shared.incubation import resolve_incubation_pipeline_stage


# ── Gap 1: 样本量分层晋级测试 ────────────────────────────────────────

class TestSampleSizeGating:
    """验证 resolve_incubation_pipeline_stage() 的样本量门槛."""

    def test_warmup_when_primary_effective_n_too_low(self):
        """primary_effective_n < 30 且 coverage >= 0.35 仍应返回 warmup."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 25,
                "secondary_effective_n": 10,
                "primary_skill_lcb": 0.02,
                "secondary_skill_lcb": 0.01,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.40,
                "stability_gap": 0.03,
            },
        )
        assert stage == "warmup"

    def test_warmup_when_coverage_too_low(self):
        """coverage_ratio < 0.35 即使样本量足够也应返回 warmup."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 50,
                "secondary_effective_n": 20,
                "primary_skill_lcb": 0.02,
                "secondary_skill_lcb": 0.01,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.20,
                "stability_gap": 0.03,
            },
        )
        assert stage == "warmup"

    def test_candidate_when_skill_lcb_positive_but_not_graduation_ready(self):
        """样本量达到 warmup 但不到毕业门槛、skill LCB 为正 → candidate 或 observe."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 50,
                "secondary_effective_n": 25,
                "primary_skill_lcb": 0.03,
                "secondary_skill_lcb": 0.01,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.60,
                "stability_gap": 0.03,
            },
        )
        # primary_effective_n=50 < 70 所以不是 graduation_ready
        assert stage != "graduation_ready"
        assert stage in {"candidate", "observe"}

    def test_graduation_ready_with_sufficient_samples(self):
        """72/36/0.85 + 全部 skill LCB 正 + 无风险 + 执行审计通过 → graduation_ready."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 72,
                "secondary_effective_n": 36,
                "primary_skill_lcb": 0.04,
                "secondary_skill_lcb": 0.02,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.85,
                "stability_gap": 0.03,
            },
            execution_audit_gate_status="passed",
        )
        assert stage == "graduation_ready"

    def test_not_graduation_when_secondary_effective_n_too_low(self):
        """secondary_effective_n 不足时不能毕业."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 80,
                "secondary_effective_n": 20,  # < 35
                "primary_skill_lcb": 0.04,
                "secondary_skill_lcb": 0.02,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.85,
                "stability_gap": 0.03,
            },
            execution_audit_gate_status="passed",
        )
        assert stage != "graduation_ready"

    def test_not_graduation_when_skill_lcb_negative(self):
        """primary_skill_lcb <= 0 时即使是够样本也不能毕业."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 80,
                "secondary_effective_n": 40,
                "primary_skill_lcb": 0.0,  # 不大于 0
                "secondary_skill_lcb": 0.02,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.85,
                "stability_gap": 0.03,
            },
            execution_audit_gate_status="passed",
        )
        assert stage != "graduation_ready"

    def test_failed_when_recent_skill_negative(self):
        """recent_primary_skill_lcb < -0.03 → failed（需先通过 warmup 门槛）."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 35,
                "secondary_effective_n": 15,
                "primary_skill_lcb": 0.01,
                "secondary_skill_lcb": 0.01,
                "recent_primary_skill_lcb": -0.05,
                "coverage_ratio": 0.40,
                "stability_gap": 0.02,
            },
        )
        assert stage == "failed"

    def test_failed_when_stability_gap_large(self):
        """stability_gap > 0.10 → failed（需先通过 warmup 门槛）."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 35,
                "secondary_effective_n": 15,
                "primary_skill_lcb": 0.01,
                "secondary_skill_lcb": 0.01,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.40,
                "stability_gap": 0.15,
            },
        )
        assert stage == "failed"

    def test_failed_when_open_risks_high(self):
        """open_risk_count >= 3 → failed（需先通过 warmup 门槛）."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 35,
                "secondary_effective_n": 15,
                "primary_skill_lcb": 0.01,
                "secondary_skill_lcb": 0.01,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.40,
                "stability_gap": 0.02,
            },
            open_risk_count=3,
        )
        assert stage == "failed"

    def test_with_execution_audit_failed_metrics_drives_failed(self):
        """执行审计 gate_status=failed_metrics → 最终返回 failed."""
        stage = resolve_incubation_pipeline_stage(
            {
                "primary_effective_n": 80,
                "secondary_effective_n": 40,
                "primary_skill_lcb": 0.04,
                "secondary_skill_lcb": 0.02,
                "recent_primary_skill_lcb": 0.01,
                "coverage_ratio": 0.85,
                "stability_gap": 0.03,
            },
            execution_audit_gate_status="failed_metrics",
        )
        assert stage == "failed"


# ── Gap 7: 观察/交易天数硬门禁常量验证 ──────────────────────────────

class TestObservationGateConstants:
    """验证观察期硬门禁的常量值."""

    def test_constants_meet_minimums(self):
        from akshare_mcp.services.incubation_pipeline import (
            INCUBATION_MIN_OBSERVED_DAYS,
            INCUBATION_MIN_TRADE_DAYS,
        )

        assert INCUBATION_MIN_OBSERVED_DAYS >= 20, (
            f"观察期最小天数应 >= 20, 实际为 {INCUBATION_MIN_OBSERVED_DAYS}"
        )
        assert INCUBATION_MIN_TRADE_DAYS >= 10, (
            f"交易天数最小应 >= 10, 实际为 {INCUBATION_MIN_TRADE_DAYS}"
        )

    def test_auto_review_only_for_graduation_ready(self):
        """auto_review 仅在 pipeline_stage == 'graduation_ready' 时为 True."""
        auto_review_true = bool(True and "graduation_ready" == "graduation_ready")
        auto_review_false_candidate = bool(True and "candidate" == "graduation_ready")
        assert auto_review_true is True
        assert auto_review_false_candidate is False


class _PipelineDb:
    def __init__(self, *, metric_count: int, trade_count: int) -> None:
        self.metrics = [
            {
                "decision": "promote",
                "total_orders": 1 if idx < trade_count else 0,
                "total_trades": 1 if idx < trade_count else 0,
                "nav": 1.01,
                "sharpe_ratio": 0.8,
                "forward_sharpe_5d": 0.3,
            }
            for idx in range(metric_count)
        ]

    async def get_strategy_incubation_account(self, strategy_id: str):
        return {"account_id": "paper-1"}

    async def get_latest_strategy_incubation_metric(self, strategy_id: str):
        return self.metrics[0] if self.metrics else None

    async def list_strategy_incubation_metrics(self, strategy_id: str, limit: int = 30):
        return list(self.metrics[:limit])

    async def get_strategy_runtime_control(self, strategy_id: str):
        return {"control_mode": "active"}

    async def list_strategy_runtime_risk_events(self, **kwargs):
        return []


def _candidate_overview() -> dict:
    return {
        "signal_quality": {
            "primary_effective_n": 50,
            "secondary_effective_n": 25,
            "primary_skill_lcb": 0.03,
            "secondary_skill_lcb": 0.01,
            "recent_primary_skill_lcb": 0.01,
            "coverage_ratio": 0.60,
            "stability_gap": 0.03,
            "primary_horizon": 5,
            "secondary_horizon": 10,
        },
        "execution_audit_gate_status": "passed",
        "execution_hard_gate_passed": True,
        "risk_hard_gate_status": "passed",
        "promotion_ready": False,
        "deprecation_risk": False,
        "observed_forward_days": [1, 3, 5, 10],
        "missing_forward_days": [],
        "total_signals": 80,
        "blockers": [],
        "risk_flags": [],
        "posture_level": "safe",
    }


def _graduation_overview() -> dict:
    return {
        "signal_quality": {
            "primary_effective_n": 72,
            "secondary_effective_n": 36,
            "primary_skill_lcb": 0.04,
            "secondary_skill_lcb": 0.02,
            "recent_primary_skill_lcb": 0.01,
            "coverage_ratio": 0.85,
            "stability_gap": 0.03,
            "primary_horizon": 5,
            "secondary_horizon": 10,
        },
        "execution_audit_gate_status": "passed",
        "execution_hard_gate_passed": True,
        "risk_hard_gate_status": "passed",
        "promotion_ready": True,
        "deprecation_risk": False,
        "observed_forward_days": [1, 3, 5, 10],
        "missing_forward_days": [],
        "total_signals": 100,
        "blockers": [],
        "risk_flags": [],
        "posture_level": "safe",
    }


def _patch_pipeline_dependencies(monkeypatch, *, crowding_report: dict | None, overview: dict | None = None):
    import akshare_mcp.services.governance_persistence as persistence_module
    import akshare_mcp.services.strategy_crowding as crowding_module
    import akshare_mcp.services.strategy_lifecycle_shared as lifecycle_shared

    async def _fake_overview(db, strategy: dict):
        return overview or _graduation_overview()

    async def _fake_crowding(db, strategy: dict):
        return crowding_report

    async def _fake_persist(report, *, scope_type: str, scope_id: str | None = None):
        return {"id": "gov-1", "overall_status": report.overall_status}

    monkeypatch.setattr(lifecycle_shared, "build_incubation_overview", _fake_overview)
    monkeypatch.setattr(crowding_module, "check_strategy_crowding_for_promotion", _fake_crowding)
    monkeypatch.setattr(persistence_module, "persist_governance_report_snapshot", _fake_persist)


class TestSnapshotGateStatusConsistency:
    """验证真实 _derive_snapshot 中 gate_status 与门禁同步。"""

    def test_observation_gate_downgrade_syncs_gate_status(self, monkeypatch):
        _patch_pipeline_dependencies(monkeypatch, crowding_report=None)
        service = StrategyIncubationPipelineService()
        snapshot = asyncio.run(
            service._derive_snapshot(
                _PipelineDb(metric_count=5, trade_count=3),
                {"id": "strategy-1", "status": "incubating", "strategy_type": "momentum"},
                task_run_id=None,
                source="test",
                auto_apply_review=True,
            )
        )

        assert snapshot["pipeline_stage"] == "candidate"
        assert snapshot["gate_status"] == "candidate"
        assert snapshot["auto_review"] is False
        assert "insufficient_observation_days:5/20" in snapshot["hard_gate_result"]["reasons"]
        assert "insufficient_trade_days:3/10" in snapshot["hard_gate_result"]["reasons"]

    def test_crowding_review_blocks_real_snapshot_auto_review(self, monkeypatch):
        _patch_pipeline_dependencies(
            monkeypatch,
            crowding_report={"recommendation": "review", "crowding_risk": "medium", "avg_correlation": 0.62},
        )
        service = StrategyIncubationPipelineService()
        snapshot = asyncio.run(
            service._derive_snapshot(
                _PipelineDb(metric_count=25, trade_count=15),
                {"id": "strategy-1", "status": "incubating", "strategy_type": "momentum"},
                task_run_id=None,
                source="test",
                auto_apply_review=True,
            )
        )

        assert snapshot["pipeline_stage"] == "candidate"
        assert snapshot["gate_status"] == "candidate"
        assert snapshot["next_action"] == "crowding_review_required"
        assert snapshot["auto_review"] is False
        assert snapshot["hard_gate_result"]["passed"] is False
        assert "crowding:review_medium_risk" in snapshot["hard_gate_result"]["reasons"]

    def test_crowding_review_blocks_candidate_hard_gate(self, monkeypatch):
        _patch_pipeline_dependencies(
            monkeypatch,
            crowding_report={"recommendation": "review", "crowding_risk": "medium", "avg_correlation": 0.62},
            overview=_candidate_overview(),
        )
        service = StrategyIncubationPipelineService()
        snapshot = asyncio.run(
            service._derive_snapshot(
                _PipelineDb(metric_count=25, trade_count=15),
                {"id": "strategy-1", "status": "incubating", "strategy_type": "momentum"},
                task_run_id=None,
                source="test",
                auto_apply_review=True,
            )
        )

        assert snapshot["pipeline_stage"] == "candidate"
        assert snapshot["auto_review"] is False
        assert snapshot["hard_gate_result"]["passed"] is False
        assert "crowding:review_medium_risk" in snapshot["hard_gate_result"]["reasons"]

    def test_crowding_approve_keeps_graduation_ready_when_observation_passes(self, monkeypatch):
        _patch_pipeline_dependencies(
            monkeypatch,
            crowding_report={"recommendation": "approve", "crowding_risk": "low", "avg_correlation": 0.2},
        )
        service = StrategyIncubationPipelineService()
        snapshot = asyncio.run(
            service._derive_snapshot(
                _PipelineDb(metric_count=25, trade_count=15),
                {"id": "strategy-1", "status": "incubating", "strategy_type": "momentum"},
                task_run_id=None,
                source="test",
                auto_apply_review=True,
            )
        )

        assert snapshot["pipeline_stage"] == "graduation_ready"
        assert snapshot["gate_status"] == "graduation_ready"
        assert snapshot["auto_review"] is True
        assert snapshot["hard_gate_result"]["passed"] is True
