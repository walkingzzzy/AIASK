"""Smoke tests for StrategySpawner."""

from __future__ import annotations


def test_spawner_instantiation():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    assert spawner is not None


def test_spawner_spawn_returns_list():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 50,
        "fg_level": "neutral",
        "listed_count": 10,
        "incubating_count": 2,
        "factor_research": {},
        "event_driven": {},
        "sources": {},
    }
    candidates = spawner.spawn(snapshot)
    assert isinstance(candidates, list)


def test_spawner_spawn_with_factor_research():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 65,
        "fg_level": "greed",
        "listed_count": 15,
        "incubating_count": 3,
        "factor_research": {
            "summary": {
                "active_factor_count": 3,
                "top_factor_names": ["momentum", "value"],
                "preferred_strategy_types": ["momentum", "value_factor"],
            }
        },
        "event_driven": {},
        "sources": {},
    }
    candidates = spawner.spawn(snapshot)
    assert isinstance(candidates, list)
    # Should produce at least some candidates given factor research input
    for c in candidates:
        assert "strategy_type" in c
        assert "params" in c


def test_spawner_injects_factor_pool_candidates():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 50,
        "fg_level": "neutral",
        "factor_research": {
            "factory_pool_payload": {
                "available": True,
                "factors": [
                    {
                        "factor_id": "factor-1",
                        "name": "value_quality_blend",
                        "family": "value",
                        "expression_dsl": "rank(pe_ttm) * -1 + rank(roe)",
                        "fitness": 1.2,
                        "admission_grade": "A",
                        "generation_engine": "rule_seed",
                    }
                ],
            }
        },
        "event_driven": {},
        "sources": {},
    }

    candidates = spawner.spawn(snapshot)
    factor_pool_candidates = [
        item for item in candidates if item.get("factor_pool_factor_id") == "factor-1"
    ]

    assert factor_pool_candidates
    assert factor_pool_candidates[0]["params"]["factor_pool_factor_id"] == "factor-1"
    assert factor_pool_candidates[0]["params"]["factor_dsl"] == "rank(pe_ttm) * -1 + rank(roe)"
    assert factor_pool_candidates[0]["params"]["fitness"] == 1.2
    assert factor_pool_candidates[0]["params"]["grade"] == "A"
    assert factor_pool_candidates[0]["params"]["engine"] == "rule_seed"
    assert factor_pool_candidates[0]["metadata"]["factor_pool_factor_id"] == "factor-1"


# ALPHA-WIRING-V1 (P-A)：泛因子 IC 接入 —— 把已挖出（gp_*/rl_*）但被经典分支忽略的
# 因子接回 _from_factor_ic 生成链，每个候选带合成的 prediction_contract + evidence_chain。
def _factor_ic_snapshot() -> dict:
    return {
        "fear_greed_index": 55,
        "fg_level": "neutral",
        "factor_research": {
            "ranked_factors": [
                {"factor_name": "momentum", "ic_value": 0.05, "trend": "rising"},
                {"factor_name": "gp_factor_6", "ic_value": 0.108, "trend": "rising"},
                {"factor_name": "rl_factor_1", "ic_value": 0.105, "trend": "rising"},
                {"factor_name": "rl_factor_2", "ic_value": -0.057, "trend": "falling"},
                {"factor_name": "gp_factor_2", "ic_value": 0.006, "trend": "flat"},
            ]
        },
        "event_driven": {},
        "sources": {},
    }


def _reload_spawner():
    import importlib

    import strategy_factory.domain.constants as constants
    import strategy_factory.domain.spawner as spawner_mod

    importlib.reload(constants)
    importlib.reload(spawner_mod)
    return spawner_mod.StrategySpawner


def _generic_factor_ic_candidates(candidates: list) -> list:
    return [
        item
        for item in candidates
        if str((item.get("params") or {}).get("factor_name") or "").lower().startswith(("gp_", "rl_"))
    ]


def test_factor_ic_generic_intake_off_is_zero_change(monkeypatch):
    """默认 OFF：泛因子不进入生成链，行为与历史一致。"""
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED", "0")
    spawner = _reload_spawner()()
    candidates = spawner._from_factor_ic(_factor_ic_snapshot())
    assert _generic_factor_ic_candidates(candidates) == []


def test_factor_ic_generic_intake_on_emits_contract_candidates(monkeypatch):
    """ON：IC 过阈值的 gp_/rl_ 因子产出带完整语义契约的候选，方向随 IC 符号。"""
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_MIN_ABS_IC", "0.03")
    spawner = _reload_spawner()()
    candidates = spawner._from_factor_ic(_factor_ic_snapshot())
    generic = _generic_factor_ic_candidates(candidates)

    # gp_factor_6 / rl_factor_1 / rl_factor_2 过阈值；gp_factor_2 (0.006) 被过滤
    names = {(item.get("params") or {}).get("factor_name") for item in generic}
    assert names == {"gp_factor_6", "rl_factor_1", "rl_factor_2"}

    by_name = {(item.get("params") or {}).get("factor_name"): item for item in generic}
    for item in generic:
        evidence_chain = item.get("evidence_chain") or (item.get("params") or {}).get("evidence_chain")
        prediction_contract = item.get("prediction_contract") or (item.get("params") or {}).get(
            "prediction_contract"
        )
        assert evidence_chain and evidence_chain.get("evidences")
        assert prediction_contract and prediction_contract.get("claims")

    # 方向随 IC 符号：正 IC -> up，负 IC -> down
    up_pc = by_name["gp_factor_6"]["prediction_contract"]
    down_pc = by_name["rl_factor_2"]["prediction_contract"]
    assert up_pc["claims"][0]["expected_move"] == "up"
    assert down_pc["claims"][0]["expected_move"] == "down"


def test_factor_ic_generic_intake_respects_max_factors(monkeypatch):
    """配额上限：MAX_FACTORS 限制单轮泛因子候选数量，按 |IC| 取强者。"""
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_MIN_ABS_IC", "0.03")
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_MAX_FACTORS", "1")
    spawner = _reload_spawner()()
    candidates = spawner._from_factor_ic(_factor_ic_snapshot())
    generic = _generic_factor_ic_candidates(candidates)
    assert len(generic) == 1
    # |IC| 最大的 gp_factor_6 (0.108) 胜出
    assert (generic[0].get("params") or {}).get("factor_name") == "gp_factor_6"


# ALPHA-WIRING-V1 (P-D)：经典分支 IC 裸阈值改 env 可配（默认 0.03，零变化）。
def _classic_factor_ic_snapshot():
    return {
        "fear_greed_index": 55,
        "fg_level": "neutral",
        "factor_research": {
            "ranked_factors": [
                # value IC=0.04 > 默认 0.03 阈值 -> 默认放行；提高阈值到 0.05 -> 被挡
                {"factor_name": "value", "ic_value": 0.04, "trend": "rising"},
                {"factor_name": "quality", "ic_value": 0.10, "trend": "rising"},
            ]
        },
        "event_driven": {},
        "sources": {},
    }


def _classic_candidate_names(candidates: list) -> set:
    # 经典分支候选的 strategy_type（value->value_factor, quality->quality_factor）
    return {item.get("strategy_type") for item in candidates}


def test_factor_ic_classic_threshold_default_zero_change(monkeypatch):
    monkeypatch.delenv("STRATEGY_FACTORY_FACTOR_IC_CLASSIC_MIN_IC", raising=False)
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED", "0")
    spawner = _reload_spawner()()
    candidates = spawner._from_factor_ic(_classic_factor_ic_snapshot())
    types = _classic_candidate_names(candidates)
    # 默认阈值 0.03：value(0.04) 与 quality(0.10) 都放行
    assert "value_factor" in types
    assert "quality_factor" in types


def test_factor_ic_classic_threshold_configurable_tighten(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_CLASSIC_MIN_IC", "0.05")
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_IC_GENERIC_INTAKE_ENABLED", "0")
    spawner = _reload_spawner()()
    candidates = spawner._from_factor_ic(_classic_factor_ic_snapshot())
    types = _classic_candidate_names(candidates)
    # 阈值收紧到 0.05：value(0.04) 被挡，quality(0.10) 仍放行
    assert "value_factor" not in types
    assert "quality_factor" in types


# ALPHA-WIRING-V1 (P-D a)：factor_pool OOS/鲁棒证据门（默认 OFF，零变化）。
def _factor_pool_snapshot():
    def _f(fid, evidence):
        rec = {
            "factor_id": fid,
            "name": fid,
            "family": "momentum",
            "expression_dsl": "ts_mean(close, 5)",
            "fitness": 1.0,
        }
        if evidence is not None:
            rec["validation_summary"] = {"evidence_summary": evidence}
        return rec

    return {
        "fear_greed_index": 50,
        "fg_level": "neutral",
        "factor_research": {
            "factory_pool_payload": {
                "available": True,
                "factors": [
                    # 通过：sample_dates 充足、IR 达标、无前视
                    _f("gp_ok", {"sample_dates": 120, "rank_ic_ir": 0.5, "lookahead_risk": "low"}),
                    # 不过：样本期不足
                    _f("gp_short", {"sample_dates": 20, "rank_ic_ir": 0.5, "lookahead_risk": "low"}),
                    # 不过：IR 太低
                    _f("gp_lowir", {"sample_dates": 120, "rank_ic_ir": 0.1, "lookahead_risk": "low"}),
                    # 不过：前视风险高
                    _f("gp_look", {"sample_dates": 120, "rank_ic_ir": 0.5, "lookahead_risk": "high"}),
                    # 不过：无 evidence_summary
                    _f("gp_noev", None),
                ],
            }
        },
        "event_driven": {},
        "sources": {},
    }


def _pool_factor_ids(candidates: list) -> set:
    return {c.get("factor_pool_factor_id") for c in candidates if c.get("factor_pool_factor_id")}


def test_factor_pool_oos_gate_off_is_zero_change(monkeypatch):
    monkeypatch.delenv("STRATEGY_FACTORY_FACTOR_POOL_OOS_GATE_ENABLED", raising=False)
    spawner = _reload_spawner()()
    candidates = spawner._from_factor_pool(_factor_pool_snapshot())
    # OFF：全部 5 个因子都出货（含 evidence 缺失的）
    assert _pool_factor_ids(candidates) == {"gp_ok", "gp_short", "gp_lowir", "gp_look", "gp_noev"}


def test_factor_pool_oos_gate_on_filters_failures(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_POOL_OOS_GATE_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_POOL_OOS_MIN_SAMPLE_DATES", "60")
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_POOL_OOS_MIN_RANK_IC_IR", "0.3")
    spawner = _reload_spawner()()
    candidates = spawner._from_factor_pool(_factor_pool_snapshot())
    # ON：只有 gp_ok 通过
    assert _pool_factor_ids(candidates) == {"gp_ok"}
