from __future__ import annotations


def _healthy_snapshot() -> dict:
    return {
        "degraded": False,
        "completeness": {"completion_ratio": 1.0},
        "sources": {"event_driven": {"status": "success"}},
        "event_driven": {"tasks_ready_count": 1},
    }


def _missing_governed_pool_factor_research() -> dict:
    return {
        "summary": {
            "factor_source_mode": "seed_fallback",
            "active_candidate_count": 0,
            "governed_source_candidate_count": 0,
        },
        "freshness_repair": {
            "auto_refresh_enabled": False,
            "refresh_attempted": False,
            "refresh_status": "disabled",
        },
    }


def test_soft_readiness_allows_missing_governed_pool_with_observability(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "0")

    from strategy_factory.application.services.readiness_service import ReadinessService

    readiness = ReadinessService().evaluate(
        _healthy_snapshot(),
        _missing_governed_pool_factor_research(),
    )

    assert readiness["hard_block_enabled"] is False
    assert readiness["can_proceed"] is True
    assert "governed_candidate_pool_required" in readiness["blockers"]
    assert "governed_candidate_pool_unavailable_after_refresh" in readiness["blockers"]
    assert readiness["critical_blockers"] == []
    assert readiness["authority"]["decision"] == "proceed"


def test_hard_readiness_blocks_missing_governed_pool(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    from strategy_factory.application.services.readiness_service import ReadinessService

    readiness = ReadinessService().evaluate(
        _healthy_snapshot(),
        _missing_governed_pool_factor_research(),
    )

    assert readiness["hard_block_enabled"] is True
    assert readiness["can_proceed"] is False
    assert "governed_candidate_pool_required" in readiness["critical_blockers"]
    assert "governed_candidate_pool_unavailable_after_refresh" in readiness["critical_blockers"]
    assert readiness["authority"]["decision"] == "blocked"



# --- P0-3 fix: cohort_zero_signal / promotion_ready_complete_failure regression locks ---


def _healthy_factor_research_with_active_cohort(
    *,
    strategy_count: int,
    promotion_ready_count: int = 0,
    zero_signal_ratio: float = 1.0,
) -> dict:
    """构建一个 governed_pool 健康但 cohort 实际产出垃圾的 factor_research summary。

    用于 P0-3 测试:模拟诊断报告 §2.3 描述的"143 strategies 全 D 级"场景。
    """
    promotion_ready_ratio = (
        round(promotion_ready_count / strategy_count, 4) if strategy_count else 1.0
    )
    return {
        "summary": {
            "factor_source_mode": "governed_pool",
            "active_candidate_count": strategy_count,
            "governed_source_candidate_count": strategy_count,
            "governed_candidate_pool_active": True,
            "governed_freshness_days": 1.0,
            "stale": False,
            "degraded": False,
            "budget_feedback_strategy_count": strategy_count,
            "budget_feedback_promotion_ready_count": promotion_ready_count,
            "budget_feedback_promotion_ready_ratio": promotion_ready_ratio,
            "budget_feedback_zero_signal_strategy_count": int(strategy_count * zero_signal_ratio),
            "budget_feedback_zero_signal_ratio": zero_signal_ratio,
            "budget_feedback_forward_window_coverage_ratio": 1.0,
            "budget_feedback_promotion_review_count": 0,
            "budget_feedback_promotion_review_coverage_ratio": 0.0,
            "budget_feedback_evidence_debt_ratio": 0.0,
        },
        "freshness_repair": {
            "auto_refresh_enabled": True,
            "refresh_attempted": False,
            "refresh_status": "not_needed",
        },
    }


def test_p0_3_cohort_promotion_ready_complete_failure_blocks_readiness(monkeypatch):
    """P0-3 regression: 诊断报告 §2.3 — 143 strategies submitted 但 promotion_ready=0,
    旧逻辑下 readiness_score=0.7-0.84 显示健康可继续 proceed,误导 AI Agent。
    修复后必须:
      1. emit warning 'cohort_promotion_ready_complete_failure'
      2. 加入 blockers 列表
      3. score 重度降级
      4. hard_block 模式下 → critical_blocker → can_proceed=False
    """
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    from strategy_factory.application.services.readiness_service import ReadinessService

    readiness = ReadinessService().evaluate(
        _healthy_snapshot(),
        _healthy_factor_research_with_active_cohort(
            strategy_count=143,
            promotion_ready_count=0,
            zero_signal_ratio=1.0,
        ),
    )

    # P0-3 核心断言:cohort 全失败必须被识别为 critical
    warnings = readiness.get("warnings") or []
    blockers = readiness.get("blockers") or []
    critical = readiness.get("critical_blockers") or []

    assert "cohort_promotion_ready_complete_failure" in warnings, (
        f"P0-3 BUG: cohort=143/promotion_ready=0 should emit warning. warnings={warnings}"
    )
    assert "cohort_promotion_ready_complete_failure" in blockers, (
        f"P0-3 BUG: should be blocking. blockers={blockers}"
    )
    assert "cohort_promotion_ready_complete_failure" in critical, (
        f"P0-3 BUG: hard_block=on => must be critical. critical={critical}"
    )
    assert "cohort_zero_signal_pervasive" in warnings
    assert "cohort_zero_signal_pervasive" in critical

    # readiness_score 必须重度降级 (0.7 → < 0.4 — 老 baseline 1.0,扣 0.40+0.30 = 0.70 = 0.30)
    assert readiness["readiness_score"] < 0.5, (
        f"P0-3 BUG: cohort full-failure but readiness_score={readiness['readiness_score']} too high"
    )

    # hard_block 模式下 must NOT proceed
    assert readiness["can_proceed"] is False
    assert readiness["authority"]["decision"] == "blocked"


def test_p0_3_small_cohort_promotion_failure_does_not_trigger_critical_blocker(monkeypatch):
    """逆向验证:小 cohort (< 50) 的 promotion_ready=0 是常见状态,不应触发 cohort 级 critical_blocker。
    保留原有的 incubating_promotion_ready_gap_high warning 即可。
    """
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    from strategy_factory.application.services.readiness_service import ReadinessService

    readiness = ReadinessService().evaluate(
        _healthy_snapshot(),
        _healthy_factor_research_with_active_cohort(
            strategy_count=10,  # 小 cohort
            promotion_ready_count=0,
            zero_signal_ratio=0.5,
        ),
    )

    warnings = readiness.get("warnings") or []
    critical = readiness.get("critical_blockers") or []

    # 不应触发 P0-3 新的 critical
    assert "cohort_promotion_ready_complete_failure" not in critical
    assert "cohort_zero_signal_pervasive" not in critical
    # 但小 cohort 的 promotion_ready=0 仍然 emit 现有的 incubating gap warning(回归保护)
    assert "incubating_promotion_ready_gap_high" in warnings


def test_p0_3_healthy_large_cohort_passes(monkeypatch):
    """正向验证:cohort=100 + promotion_ready=20(20%)是健康状态,不应触发 P0-3 critical。"""
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    from strategy_factory.application.services.readiness_service import ReadinessService

    readiness = ReadinessService().evaluate(
        _healthy_snapshot(),
        _healthy_factor_research_with_active_cohort(
            strategy_count=100,
            promotion_ready_count=20,  # 健康 20%
            zero_signal_ratio=0.05,
        ),
    )

    critical = readiness.get("critical_blockers") or []
    assert "cohort_promotion_ready_complete_failure" not in critical
    assert "cohort_zero_signal_pervasive" not in critical
    # 健康 cohort 必须能 proceed
    assert readiness["can_proceed"] is True
