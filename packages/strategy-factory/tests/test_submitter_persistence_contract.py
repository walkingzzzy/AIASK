from strategy_factory.application.submitter import StrategySubmitter


def test_build_strategy_data_persists_extended_strategy_contract():
    submitter = StrategySubmitter()

    data = submitter._build_strategy_data(
        "sid_contract",
        "合同策略",
        {
            "strategy_type": "dsl_rule",
            "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"], "rationale": "只做任务标的"},
            "research_task": {
                "task_id": "task_evt_1",
                "task_source": "event_driven",
                "target_symbols": ["600519"],
                "event_id": "evt_1",
                "theme_code": "ai",
            },
            "hypothesis": "事件驱动顺势",
            "holding_horizon": {"max_days": 10},
            "trade_plan": {"entry_bias": "event_follow_through"},
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            "position_sizing": {"mode": "single_name"},
            "execution_notes": "仅在流动性良好时段执行",
            "rebalance_rule": {"mode": "event_driven_hold"},
            "portfolio_spec": {"position_assumption": "single_name_full_notional"},
            "execution_assumptions": {"slippage_bps": 8, "tradability_filter": True},
            "validation_profile": {"profile": "event_trade_validation", "validation_focus": "event_target_only"},
            "targeting_policy": {"target_symbol_policy": "strict_intersection"},
            "constraint_check": {"intersection_ratio": 1.0},
            "source_candidate_artifact_id": "candidate_001",
            "source_generation_artifact_id": "llm_episode_001",
            "source_validation_artifact_id": "candidate_validation_001",
            "memory_record_id": "memory_001",
            "candidate_family": "sentiment",
            "candidate_registry_stage": "governed",
            "validation_score": 83.5,
            "expected_regime": ["trend", "event"],
            "expected_holding_period": 10,
            "latest_validation_at": "2026-03-20T08:30:00+08:00",
            "latest_validation_age_days": 1,
            "admission_block_reasons": [],
            "candidate_evidence_status": {
                "required_audits_complete": True,
                "lookahead_available": True,
                "multiple_testing_available": True,
                "overall_risk_level": "low",
                "blocked": False,
            },
        },
        {},
    )

    params = data["params"]

    assert params["hypothesis"] == "事件驱动顺势"
    assert params["holding_horizon"]["max_days"] == 10
    assert params["trade_plan"]["entry_bias"] == "event_follow_through"
    assert params["risk_rules"]["stop_loss_pct"] == 0.08
    assert params["position_sizing"]["mode"] == "single_name"
    assert params["execution_notes"] == "仅在流动性良好时段执行"
    assert params["validation_profile"]["profile"] == "event_trade_validation"
    assert params["targeting_policy"]["target_symbol_policy"] == "strict_intersection"
    assert params["task_signature"].startswith("event_driven|evt_1|ai|")
    assert params["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_001"
    assert params["candidate_provenance"]["source_generation_artifact_id"] == "llm_episode_001"
    assert params["candidate_provenance"]["source_validation_artifact_id"] == "candidate_validation_001"
    assert params["candidate_provenance"]["memory_record_id"] == "memory_001"
    assert params["candidate_provenance"]["candidate_family"] == "sentiment"
    assert params["candidate_provenance"]["candidate_registry_stage"] == "governed"
    assert params["candidate_provenance"]["validation_score"] == 83.5
    assert params["candidate_provenance"]["expected_regime"] == ["trend", "event"]
    assert params["candidate_provenance"]["expected_holding_period"] == 10
    assert params["candidate_provenance"]["latest_validation_age_days"] == 1
    assert params["source_candidate_artifact_id"] == "candidate_001"
    assert params["source_generation_artifact_id"] == "llm_episode_001"
    assert params["source_validation_artifact_id"] == "candidate_validation_001"
    assert params["candidate_memory_record_id"] == "memory_001"
    assert params["candidate_family"] == "sentiment"
    assert params["candidate_registry_stage"] == "governed"
    assert params["candidate_validation_score"] == 83.5
    assert params["expected_regime"] == ["trend", "event"]
    assert params["expected_holding_period"] == 10
    assert params["candidate_latest_validation_age_days"] == 1
    assert params["candidate_contract_hash"]
    assert params["tested_object_hash"]
    assert params["candidate_identity_signature"]
    assert params["candidate_contract_snapshot"]["targeting"]["target_pool_id"] == "ai"
    assert params["candidate_contract_snapshot"]["targeting"]["target_symbols"] == ["600519"]
    assert params["candidate_contract_snapshot"]["validation_profile"]["profile"] == "event_trade_validation"
    assert params["candidate_lineage_contract"]["task_signature"].startswith("event_driven|evt_1|ai|")


def test_candidate_report_params_merges_target_universe_contract():
    submitter = StrategySubmitter()

    report_params = submitter._candidate_report_params(
        {
            "strategy_type": "volatility_breakout",
            "params": {"lookback": 20, "threshold": 0.025},
            "target_symbols": ["002415", "300750"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["002415", "300750"]},
            "research_task": {"task_id": "task_chip", "task_source": "event_driven"},
            "event_context": {"event_id": "evt_chip"},
            "validation_profile": {"profile": "event_trade_validation"},
            "execution_assumptions": {"tradability_filter": True},
        }
    )

    assert report_params["lookback"] == 20
    assert report_params["threshold"] == 0.025
    assert report_params["target_symbols"] == ["002415", "300750"]
    assert report_params["stock_pool"]["symbols"] == ["002415", "300750"]
    assert report_params["research_task"]["task_id"] == "task_chip"
    assert report_params["event_context"]["event_id"] == "evt_chip"
    assert report_params["validation_profile"]["profile"] == "event_trade_validation"


def test_candidate_report_params_backfills_governance_contract_fields_from_research_task():
    submitter = StrategySubmitter()

    report_params = submitter._candidate_report_params(
        {
            "strategy_type": "ma_cross",
            "target_symbols": ["600519"],
            "research_task": {
                "task_source": "event_driven",
                "target_symbols": ["600519"],
            },
            "constraint_check": {
                "coverage_ratio": 1.0,
                "intersection_ratio": 1.0,
            },
        }
    )

    assert report_params["validation_profile"]["profile"] == "event_trade_validation"
    assert report_params["validation_profile"]["validation_focus"] == "event_target_only"
    assert report_params["targeting_policy"]["target_symbol_policy"] == "strict_intersection"
    assert report_params["targeting_policy"]["universe_expansion_policy"] == "allow_same_theme_only"


def test_submitter_resolves_live_ready_candidates_to_live_review_lane():
    submitter = StrategySubmitter()

    submission_lane, final_status = submitter._resolve_submission_lane(
        {
            "passed": True,
            "live_candidate_ready": True,
        },
        refresh_existing=False,
        existing_status="draft",
        incubation_budget_track="formal_incubation",
    )

    assert submission_lane == "live_ready_review"
    assert final_status == "submitted"
