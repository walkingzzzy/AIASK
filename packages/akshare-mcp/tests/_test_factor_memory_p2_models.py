from ._test_factor_memory_p2_support import *


@pytest.mark.asyncio
async def test_quant_manager_model_registry_lineage_links_candidate_model_and_retrain(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["304101", "304102", "304103", "304104"]
    generation_artifact_id = "factor_llm_episode_lineage_case"
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
                "candidates": [_build_candidate("momentum_20d", name="lineage_factor")],
                "research_episode": {"theme": "momentum_regime_lineage"},
            },
        }
    )
    _register_validation_artifact(
        "factor_validation_registry_lineage_champion",
        registry_codes,
        name="lineage_champion",
        recommendation="promote",
        total_score=93.0,
        source_generation_artifact_id=generation_artifact_id,
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
    champion_model_artifact_id = review["data"]["registered_models"][0]["artifact_id"]

    retrain_plan = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "schedule_retrain",
            "artifact_id": champion_model_artifact_id,
            "family": "momentum",
            "only_flagged": False,
        },
    )
    assert retrain_plan["success"] is True
    plan_id = retrain_plan["data"]["artifact_id"]

    register_artifact(
        {
            "artifact_id": "quant_retrain_run_lineage_case",
            "strategy": "quant_model_retrain_run",
            "strategy_version": "p2.v3",
            "code": ",".join(registry_codes),
            "payload": {
                "artifact_id": "quant_retrain_run_lineage_case",
                "action": "model_registry",
                "op": "execute_retrain",
                "plan_id": plan_id,
                "status": "partial",
                "validation_artifact_ids": ["factor_validation_registry_lineage_champion"],
                "registry_artifact_ids": [champion_model_artifact_id],
                "execution_summary": {"validation_run_count": 1},
            },
        }
    )

    lineage = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "lineage",
            "artifact_id": champion_model_artifact_id,
            "limit": 20,
            "market_codes_only": True,
        },
    )

    assert lineage["success"] is True
    data = lineage["data"]
    assert data["root"]["strategy"] == "quant_model_registry"
    assert data["summary"]["candidate_count"] >= 1
    assert data["summary"]["model_count"] >= 1
    assert data["summary"]["retrain_plan_count"] >= 1
    assert data["summary"]["retrain_run_count"] >= 1
    assert data["generation_artifacts"][0]["artifact_id"] == generation_artifact_id

    item = next(
        item
        for item in data["items"]
        if item["validation_artifact_id"] == "factor_validation_registry_lineage_champion"
    )
    assert item["source_generation_artifact_id"] == generation_artifact_id
    assert "champion" in item["deployment_stages"]
    assert item["expected_regime"] == ["trend"]
    assert item["expected_holding_period"] == 10
    assert item["validation_params"]["lookback_bars"] == 180
    assert item["validation_params"]["horizon_days"] == 5
    assert item["model_registry_items"][0]["artifact_id"] == champion_model_artifact_id
    assert item["model_registry_items"][0]["expected_regime"] == ["trend"]
    assert item["model_registry_items"][0]["expected_holding_period"] == 10
    assert item["retrain_plans"][0]["artifact_id"] == plan_id
    assert item["retrain_runs"][0]["artifact_id"] == "quant_retrain_run_lineage_case"
    assert item["latest_retrain_run"]["status"] == "partial"


@pytest.mark.asyncio
async def test_quant_manager_model_registry_feedback_sync_updates_model_registry(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod

    monkeypatch.setattr(quant_mod, "get_db", lambda: _FeedbackDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["305101", "305102", "305103", "305104"]
    _register_validation_artifact(
        "factor_validation_registry_feedback_champion",
        registry_codes,
        name="feedback_champion",
        recommendation="promote",
        total_score=92.0,
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
    model_artifact_id = review["data"]["registered_models"][0]["artifact_id"]

    feedback = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "feedback_sync",
            "strategy_id": "sid_feedback_case",
            "limit": 10,
        },
    )
    assert feedback["success"] is True
    assert feedback["data"]["summary"]["synced_count"] == 1
    assert feedback["data"]["summary"]["feedback_flagged_count"] == 1
    assert feedback["data"]["summary"]["schedule_retrain_count"] == 1
    synced = feedback["data"]["items"][0]
    assert synced["strategy_id"] == "sid_feedback_case"
    assert synced["recommended_action"] == "schedule_retrain"
    assert "feedback_decay" in synced["feedback_flags"]
    assert "feedback_regime_shift" in synced["feedback_flags"]
    assert "feedback_runtime_critical" in synced["feedback_flags"]

    model_item = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "get", "artifact_id": model_artifact_id},
    )
    assert model_item["success"] is True
    item = model_item["data"]["item"]
    assert item["last_feedback_strategy_id"] == "sid_feedback_case"
    assert item["feedback_recommended_action"] == "schedule_retrain"
    assert "feedback_decay" in item["feedback_flags"]
    assert item["feedback_summary"]["strategy_id"] == "sid_feedback_case"
    assert item["feedback_summary"]["decay_detected"] is True
    assert item["feedback_summary"]["regime_shift_detected"] is True

    registry_summary = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "summary", "family": "momentum", "limit": 20},
    )
    assert registry_summary["success"] is True
    assert registry_summary["data"]["summary"]["feedback_flagged_count"] >= 1
    assert registry_summary["data"]["summary"]["feedback_retrain_signal_count"] >= 1

    lifecycle = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "lifecycle_scan", "family": "momentum", "limit": 20},
    )
    assert lifecycle["success"] is True
    scanned = next(item for item in lifecycle["data"]["items"] if item["artifact_id"] == model_artifact_id)
    assert "feedback_decay" in scanned["flags"]
    assert scanned["recommended_action"] == "schedule_retrain"


@pytest.mark.asyncio
async def test_quant_manager_execute_retrain_and_retrain_status(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    registry_codes = ["303101", "303102", "303103", "303104"]
    generation_artifact_id = "factor_llm_episode_retrain_execute_case"
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
                "candidate_count": 2,
                "candidates": [
                    _build_candidate("momentum_20d", name="retrain_good"),
                    _build_candidate("foobar(close)", name="retrain_bad"),
                ],
            },
        }
    )
    _register_validation_artifact(
        "factor_validation_registry_retrain_execute_champion",
        registry_codes,
        name="retrain_execute_champion",
        recommendation="promote",
        total_score=91.0,
        source_generation_artifact_id=generation_artifact_id,
    )
    _register_validation_artifact(
        "factor_validation_registry_retrain_execute_challenger",
        registry_codes,
        name="retrain_execute_challenger",
        recommendation="review",
        total_score=86.0,
        source_generation_artifact_id=generation_artifact_id,
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

    registry_list = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "list",
            "deployment_stage": "champion",
            "family": "momentum",
            "limit": 20,
        },
    )
    assert registry_list["success"] is True
    champion_item = next(
        item
        for item in registry_list["data"]["items"]
        if item["deployment_stage"] == "champion"
        and item["source_generation_artifact_id"] == generation_artifact_id
    )

    retrain_plan = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "schedule_retrain",
            "artifact_id": champion_item["artifact_id"],
            "family": "momentum",
            "only_flagged": False,
            "codes": registry_codes,
        },
    )
    assert retrain_plan["success"] is True
    plan_id = retrain_plan["data"]["artifact_id"]

    retrain_execute = await mcp.quant_manager(
        action="model_registry",
        kwargs={
            "op": "execute_retrain",
            "artifact_id": plan_id,
            "codes": registry_codes,
            "lookback_bars": 180,
            "horizon_days": 10,
            "max_dates": 40,
            "write_memory": False,
            "update_registry": True,
        },
    )
    assert retrain_execute["success"] is True
    run = retrain_execute["data"]["run"]
    plan = retrain_execute["data"]["plan"]
    assert run["status"] == "completed"
    assert run["plan_id"] == plan_id
    assert run["execution_summary"]["target_model_count"] == 1
    assert run["execution_summary"]["replay_run_count"] == 1
    assert run["execution_summary"]["validation_run_count"] == 1
    assert run["execution_summary"]["registry_update_count"] == 1
    assert plan["last_run_artifact_id"] == run["artifact_id"]
    assert plan["last_run_status"] == "completed"
    assert plan["run_count"] == 1

    status_by_plan = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_status", "artifact_id": plan_id},
    )
    assert status_by_plan["success"] is True
    assert status_by_plan["data"]["latest_run"]["artifact_id"] == run["artifact_id"]
    assert status_by_plan["data"]["run_summary"]["count"] >= 1

    status_by_run = await mcp.quant_manager(
        action="model_registry",
        kwargs={"op": "retrain_status", "artifact_id": run["artifact_id"]},
    )
    assert status_by_run["success"] is True
    assert status_by_run["data"]["run"]["artifact_id"] == run["artifact_id"]
    assert status_by_run["data"]["plan"]["last_run_artifact_id"] == run["artifact_id"]


@pytest.mark.asyncio
async def test_quant_manager_replay_factor_episode_revalidates_candidate_batch(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    import akshare_mcp.services.artifact_registry as _ar_mod
    from akshare_mcp.services import register_artifact

    monkeypatch.setattr(quant_mod, "get_db", lambda: _ValidationDB())
    monkeypatch.setattr(_ar_mod, "_get_db", lambda: None)

    source_artifact_id = "factor_llm_episode_case"
    register_artifact(
        {
            "artifact_id": source_artifact_id,
            "strategy": "quant_llm_factor_mining",
            "strategy_version": "p0.v1",
            "code": "RG001,RG002,RG003,RG004",
            "payload": {
                "artifact_id": source_artifact_id,
                "action": "llm_factor_mining",
                "codes": ["RG001", "RG002", "RG003", "RG004"],
                "generation_mode": "llm_provider",
                "provider": "openai_compatible",
                "model": "test-model",
                "candidate_count": 2,
                "candidates": [
                    _build_candidate("momentum_20d", name="episode_good"),
                    _build_candidate("foobar(close)", name="episode_bad"),
                ],
                "params": {"lookback_bars": 200},
            },
        }
    )

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    replay = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={
            "artifact_id": source_artifact_id,
            "write_memory": False,
            "codes": ["RG001", "RG002", "RG003", "RG004"],
        },
    )

    assert replay["success"] is True
    assert replay["data"]["episode_summary"]["replayed_candidate_count"] == 2
    assert replay["data"]["episode_summary"]["validated_count"] == 1
    assert replay["data"]["episode_summary"]["failed_count"] == 1
    assert any(item["status"] == "validated" for item in replay["data"]["outcomes"])
    assert any(item["status"] == "failed" for item in replay["data"]["outcomes"])

    replay_list = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={"op": "list", "source_artifact_id": source_artifact_id, "limit": 10},
    )
    assert replay_list["success"] is True
    assert replay_list["data"]["count"] >= 1

    replay_get = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={"op": "get", "artifact_id": replay["data"]["artifact_id"]},
    )
    assert replay_get["success"] is True
    assert replay_get["data"]["item"]["source_artifact_id"] == source_artifact_id

    replay_summary = await mcp.quant_manager(
        action="replay_factor_episode",
        kwargs={"op": "summary", "source_artifact_id": source_artifact_id, "limit": 10},
    )
    assert replay_summary["success"] is True
    assert replay_summary["data"]["summary"]["count"] >= 1

__all__ = [name for name in globals() if name.startswith("test_")]
