from ._test_factor_memory_p2_support import *


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_lists_validated_candidates(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod

    registry_codes = ["RG001", "RG002", "RG003", "RG004"]
    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    validation = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "candidate": _build_candidate("momentum_20d", name="registry_factor"),
            "codes": registry_codes,
            "output_artifact_id": "factor_validation_registry_case",
            "write_memory": False,
        },
    )

    assert validation["success"] is True

    registry_list = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "list", "codes": registry_codes, "limit": 10},
    )

    assert registry_list["success"] is True
    assert registry_list["data"]["count"] >= 1
    item = next(item for item in registry_list["data"]["items"] if item["artifact_id"] == "factor_validation_registry_case")
    assert item["registry_stage"] == "governed"
    assert item["source_validation_artifact_id"] == "factor_validation_registry_case"
    assert item["latest_validation_at"] is not None

    registry_summary = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "summary", "codes": registry_codes, "limit": 20},
    )
    assert registry_summary["success"] is True
    assert registry_summary["data"]["summary"]["count"] >= 1
    assert registry_summary["data"]["summary"]["registry_stage_counts"]["governed"] >= 1

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20},
    )
    assert active_pool["success"] is True
    assert active_pool["data"]["active_pool"]["count"] >= 1
    assert any(item["family"] == "momentum" for item in active_pool["data"]["active_pool"]["family_summary"])
    top_item = next(item for item in active_pool["data"]["active_pool"]["top_candidates"] if item["artifact_id"] == "factor_validation_registry_case")
    assert top_item["registry_stage"] == "governed"
    assert top_item["source_validation_artifact_id"] == "factor_validation_registry_case"
    assert top_item["expected_holding_period"] == 10
    assert top_item["lineage"]["validation_artifact_id"] == "factor_validation_registry_case"


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_active_pool_can_filter_non_market_codes(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    invalid_validation = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "candidate": _build_candidate("momentum_20d", name="registry_invalid_market_code"),
            "codes": ["RG001", "RG002", "RG003", "RG004"],
            "output_artifact_id": "factor_validation_registry_non_market_only",
            "write_memory": False,
        },
    )
    assert invalid_validation["success"] is True

    valid_validation = await mcp.quant_manager(
        action="validate_factor_candidate",
        kwargs={
            "candidate": _build_candidate("momentum_20d", name="registry_valid_market_code"),
            "codes": ["600519", "000858", "000333", "601318"],
            "output_artifact_id": "factor_validation_registry_market_only",
            "write_memory": False,
        },
    )
    assert valid_validation["success"] is True

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "market_codes_only": True, "limit": 50},
    )

    assert active_pool["success"] is True
    top_artifact_ids = [str(item.get("artifact_id") or "") for item in active_pool["data"]["active_pool"]["top_candidates"]]
    assert "factor_validation_registry_non_market_only" not in top_artifact_ids
    assert "factor_validation_registry_market_only" in top_artifact_ids


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_active_pool_blocks_high_risk_candidates(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["991111", "991112", "991113", "991114"]
    _register_validation_artifact(
        "factor_validation_registry_governed_safe",
        registry_codes,
        name="governed_safe",
        recommendation="promote",
        total_score=92.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )
    _register_validation_artifact(
        "factor_validation_registry_governed_lookahead_high",
        registry_codes,
        name="governed_lookahead_high",
        recommendation="promote",
        total_score=95.0,
        lookahead_risk="high",
        multiple_testing_risk="low",
    )
    _register_validation_artifact(
        "factor_validation_registry_governed_multiple_high",
        registry_codes,
        name="governed_multiple_high",
        recommendation="review",
        total_score=89.0,
        lookahead_risk="low",
        multiple_testing_risk="high",
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    registry_summary = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "summary", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )

    assert registry_summary["success"] is True
    summary = registry_summary["data"]["summary"]
    assert summary["count"] >= 3
    assert summary["lookahead_risk_counts"]["high"] >= 1
    assert summary["multiple_testing_risk_counts"]["high"] >= 1
    assert summary["blocked_count"] >= 2
    assert summary["governed_active_count"] >= 1

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )

    assert active_pool["success"] is True
    pool = active_pool["data"]["active_pool"]
    top_artifact_ids = [str(item.get("artifact_id") or "") for item in pool["top_candidates"]]
    assert "factor_validation_registry_governed_safe" in top_artifact_ids
    assert "factor_validation_registry_governed_lookahead_high" not in top_artifact_ids
    assert "factor_validation_registry_governed_multiple_high" not in top_artifact_ids
    assert pool["count"] == 1
    assert pool["excluded_count"] >= 2
    assert pool["top_candidates"][0]["registry_stage"] == "governed"
    assert pool["exclusion_reason_counts"]["lookahead_risk_high"] >= 1
    assert pool["exclusion_reason_counts"]["multiple_testing_risk_high"] >= 1

    excluded = {str(item.get("artifact_id") or ""): item for item in pool["excluded_candidates"]}
    assert "lookahead_risk_high" in excluded["factor_validation_registry_governed_lookahead_high"]["reasons"]
    assert "multiple_testing_risk_high" in excluded["factor_validation_registry_governed_multiple_high"]["reasons"]
    assert excluded["factor_validation_registry_governed_lookahead_high"]["registry_stage"] == "validated"
    assert excluded["factor_validation_registry_governed_lookahead_high"]["admission_blocked"] is True
    assert excluded["factor_validation_registry_governed_multiple_high"]["admission_blocked"] is True


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_active_pool_falls_back_to_provisional_validated_watch(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["601551", "601552", "601553", "601554"]
    _register_validation_artifact(
        "factor_validation_registry_watch_candidate",
        registry_codes,
        name="watch_candidate",
        recommendation="watch",
        total_score=49.5,
    )
    _register_validation_artifact(
        "factor_validation_registry_reject_candidate",
        registry_codes,
        name="reject_candidate",
        recommendation="reject",
        total_score=38.0,
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )

    assert active_pool["success"] is True
    assert active_pool["data"]["summary"]["governed_active_count"] == 0
    pool = active_pool["data"]["active_pool"]
    assert pool["active_pool_mode"] == "provisional_validated_watch"
    assert pool["strict_count"] == 0
    assert pool["provisional_count"] == 1
    assert pool["count"] == 1
    assert pool["provisional_spillover_policy"]["status"] == "provisional_pool_only"
    assert pool["provisional_spillover_policy"]["decision"] == "provisional_only"
    assert pool["pending_excluded_count"] == 0
    assert pool["ineligible_excluded_count"] == 1
    assert pool["ineligible_exclusion_reason_counts"]["recommendation_reject"] == 1
    assert pool["ineligible_exclusion_reason_counts"]["score_below_provisional_threshold"] == 1
    assert pool["top_candidates"][0]["artifact_id"] == "factor_validation_registry_watch_candidate"
    assert pool["top_candidates"][0]["registry_stage"] == "validated"
    assert pool["top_candidates"][0]["pool_entry_mode"] == "provisional_validated_watch"

    excluded = {str(item.get("artifact_id") or ""): item for item in pool["excluded_candidates"]}
    assert "recommendation_reject" in excluded["factor_validation_registry_reject_candidate"]["reasons"]
    assert excluded["factor_validation_registry_reject_candidate"]["exclusion_bucket"] == "ineligible"


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_active_pool_adds_provisional_spillover_when_strict_pool_thin(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["601661", "601662", "601663", "601664"]
    _register_validation_artifact(
        "factor_validation_registry_strict_candidate",
        registry_codes,
        name="strict_candidate",
        recommendation="review",
        total_score=71.5,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )
    _register_validation_artifact(
        "factor_validation_registry_spillover_watch",
        registry_codes,
        name="spillover_watch",
        recommendation="watch",
        total_score=58.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )

    assert active_pool["success"] is True
    pool = active_pool["data"]["active_pool"]
    assert pool["active_pool_mode"] == "strict_governed"
    assert pool["strict_count"] == 1
    assert pool["provisional_count"] == 1
    assert pool["provisional_spillover_count"] == 1
    assert pool["provisional_spillover_enabled"] is True
    assert pool["provisional_spillover_policy"]["status"] == "spillover_applied"
    assert pool["provisional_spillover_policy"]["decision"] == "spillover_applied"
    assert pool["provisional_spillover_policy"]["strict_shortfall_count"] == 5
    assert pool["provisional_spillover_policy"]["pending_provisional_count"] == 0
    assert pool["count"] == 2

    top_candidates = {str(item.get("artifact_id") or ""): item for item in pool["top_candidates"]}
    assert top_candidates["factor_validation_registry_strict_candidate"]["pool_entry_mode"] == "strict_governed"
    assert top_candidates["factor_validation_registry_spillover_watch"]["pool_entry_mode"] == "provisional_validated_watch"
    assert pool["provisional_spillover_artifact_ids"] == ["factor_validation_registry_spillover_watch"]
    assert pool["pending_excluded_count"] == 0


@pytest.mark.asyncio
async def test_quant_manager_factor_candidate_registry_active_pool_counts_only_unselected_provisional_candidates_as_pending(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["601771", "601772", "601773", "601774"]
    _register_validation_artifact(
        "factor_validation_registry_pending_strict",
        registry_codes,
        name="pending_strict",
        recommendation="review",
        total_score=70.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )
    for idx, score in enumerate([59.0, 57.5, 56.0, 55.5], start=1):
        _register_validation_artifact(
            f"factor_validation_registry_pending_watch_{idx}",
            registry_codes,
            name=f"pending_watch_{idx}",
            recommendation="watch",
            total_score=score,
            lookahead_risk="low",
            multiple_testing_risk="low",
        )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )

    assert active_pool["success"] is True
    pool = active_pool["data"]["active_pool"]
    assert pool["active_pool_mode"] == "strict_governed"
    assert pool["strict_count"] == 1
    assert pool["provisional_count"] == 4
    assert pool["provisional_spillover_count"] == 3
    assert pool["count"] == 4
    assert pool["pending_excluded_count"] == 1
    assert pool["provisional_spillover_policy"]["status"] == "spillover_capacity_exhausted"
    assert pool["provisional_spillover_policy"]["decision"] == "spillover_capped"
    assert pool["provisional_spillover_policy"]["strict_shortfall_count"] == 5
    assert pool["provisional_spillover_policy"]["pending_provisional_count"] == 1
    assert pool["provisional_spillover_policy"]["pending_reason_code"] == "spillover_capacity_exhausted"
    assert pool["pending_exclusion_reason_counts"] == {"spillover_capacity_exhausted": 1}
    assert pool["ineligible_excluded_count"] == 0

    excluded = {str(item.get("artifact_id") or ""): item for item in pool["excluded_candidates"]}
    assert excluded["factor_validation_registry_pending_watch_4"]["exclusion_bucket"] == "pending"
    assert excluded["factor_validation_registry_pending_watch_4"]["reasons"] == ["spillover_capacity_exhausted"]


@pytest.mark.asyncio
async def test_quant_manager_model_registry_and_champion_challenger_review(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["301901", "301902", "301903", "301904"]
    _register_validation_artifact(
        "factor_validation_registry_cc_champion",
        registry_codes,
        name="cc_champion",
        recommendation="promote",
        total_score=94.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )
    _register_validation_artifact(
        "factor_validation_registry_cc_challenger",
        registry_codes,
        name="cc_challenger",
        recommendation="review",
        total_score=88.0,
        lookahead_risk="low",
        multiple_testing_risk="low",
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    review = await mcp.quant_manager(
        action="champion_challenger",
        kwargs={
            "op": "review",
            "codes": registry_codes,
            "limit": 20,
            "persist_artifact": False,
            "update_registry": True,
            "market_codes_only": True,
        },
    )

    assert review["success"] is True
    data = review["data"]
    assert data["champion"]["artifact_id"] == "factor_validation_registry_cc_champion"
    assert data["challengers"][0]["artifact_id"] == "factor_validation_registry_cc_challenger"
    assert data["registered_models"][0]["deployment_stage"] == "champion"
    assert data["registered_models"][1]["deployment_stage"] == "challenger"

    registry_list = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "list", "family": "momentum", "limit": 20},
    )
    assert registry_list["success"] is True
    items = registry_list["data"]["items"]
    assert len(items) >= 2
    assert any(item["deployment_stage"] == "champion" for item in items)
    assert any(item["deployment_stage"] == "challenger" for item in items)

    registry_summary = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "summary", "family": "momentum", "limit": 20},
    )
    assert registry_summary["success"] is True
    summary = registry_summary["data"]["summary"]
    assert summary["champion_count"] >= 1
    assert summary["challenger_count"] >= 1

    active_pool = await mcp.quant_manager(
        action="factor_candidate_registry",
        kwargs={"op": "active_pool", "codes": registry_codes, "limit": 20, "market_codes_only": True},
    )
    assert active_pool["success"] is True
    pool_items = {item["artifact_id"]: item for item in active_pool["data"]["active_pool"]["top_candidates"]}
    assert pool_items["factor_validation_registry_cc_champion"]["registry_stage"] == "champion"
    assert pool_items["factor_validation_registry_cc_challenger"]["registry_stage"] == "challenger"
    assert pool_items["factor_validation_registry_cc_champion"]["expected_holding_period"] == 10


@pytest.mark.asyncio
async def test_quant_manager_model_registry_lifecycle_scan_and_retrain_plan(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["302101", "302102", "302103", "302104"]
    generation_artifact_id = "factor_llm_episode_lifecycle_case"
    register_artifact(
        {
            "artifact_id": generation_artifact_id,
            "strategy": "quant_llm_factor_mining",
            "strategy_version": "p0.v1",
            "code": ",".join(registry_codes),
            "payload": {
                "artifact_id": generation_artifact_id,
                "action": "llm_factor_mining",
                "codes": list(registry_codes),
                "candidate_count": 1,
                "candidates": [_build_candidate("momentum_20d", name="lifecycle_model")],
            },
        }
    )
    _register_validation_artifact(
        "factor_validation_registry_lifecycle_champion",
        registry_codes,
        name="lifecycle_champion",
        recommendation="promote",
        total_score=84.0,
        source_generation_artifact_id=generation_artifact_id,
        wf_stability=0.18,
        kf_stability=0.24,
        wf_degradation=0.17,
        kf_degradation=0.15,
    )
    _register_validation_artifact(
        "factor_validation_registry_lifecycle_challenger",
        registry_codes,
        name="lifecycle_challenger",
        recommendation="review",
        total_score=83.2,
        source_generation_artifact_id=generation_artifact_id,
        wf_stability=0.42,
        kf_stability=0.39,
        wf_degradation=0.05,
        kf_degradation=0.04,
    )
    register_artifact(
        {
            "artifact_id": "factor_episode_lifecycle_replay",
            "strategy": "quant_factor_episode_replay",
            "strategy_version": "p2.v2",
            "code": ",".join(registry_codes),
            "payload": {
                "artifact_id": "factor_episode_lifecycle_replay",
                "action": "replay_factor_episode",
                "source_artifact_id": generation_artifact_id,
                "codes": list(registry_codes),
                "episode_summary": {
                    "validated_count": 0,
                    "failed_count": 3,
                },
            },
        }
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    review = await mcp.quant_manager(
        action="champion_challenger",
        kwargs={
            "op": "review",
            "codes": registry_codes,
            "limit": 20,
            "persist_artifact": True,
            "update_registry": True,
            "market_codes_only": True,
        },
    )
    assert review["success"] is True
    assert review["data"]["review_status"] == "tight_race"

    lifecycle = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "lifecycle_scan",
            "family": "momentum",
            "limit": 20,
            "persist_artifact": False,
            "stability_floor": 0.35,
            "degradation_ceiling": 0.08,
            "tight_race_gap": 5.0,
            "replay_success_floor": 0.6,
        },
    )
    assert lifecycle["success"] is True
    scan_items = lifecycle["data"]["items"]
    champion_item = next(item for item in scan_items if item["deployment_stage"] == "champion")
    assert "high_degradation" in champion_item["flags"]
    assert "low_stability" in champion_item["flags"]
    assert "challenger_pressure" in champion_item["flags"]
    assert "replay_decay" in champion_item["flags"]
    assert champion_item["recommended_action"] == "schedule_retrain"
    assert lifecycle["data"]["summary"]["retrain_recommended_count"] >= 1

    retrain_plan = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "schedule_retrain",
            "artifact_id": champion_item["artifact_id"],
            "family": "momentum",
            "only_flagged": True,
        },
    )
    assert retrain_plan["success"] is True
    plan = retrain_plan["data"]["plan"]
    assert plan["target_model_count"] >= 1
    assert generation_artifact_id in plan["target_generation_artifact_ids"]
    assert "high_degradation" in plan["reason_codes"]
    assert plan["next_action"] == "replay_factor_episode"

    retrain_list = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_list", "family": "momentum", "limit": 20},
    )
    assert retrain_list["success"] is True
    assert retrain_list["data"]["count"] >= 1

    retrain_summary = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_summary", "family": "momentum", "limit": 20},
    )
    assert retrain_summary["success"] is True
    assert retrain_summary["data"]["summary"]["count"] >= 1

__all__ = [name for name in globals() if name.startswith("test_")]
