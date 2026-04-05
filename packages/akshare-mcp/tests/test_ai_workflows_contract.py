from __future__ import annotations

import pytest

from akshare_mcp.resources import stock_and_watchlist as stock_resource_mod
from akshare_mcp.resources import strategy as strategy_resource_mod
from akshare_mcp.tools import ai_workflows


class _DummyMCP:
    def tool(self, *args, **kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def _register_workflows():
    mcp = _DummyMCP()
    ai_workflows.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_analyze_stock_workflow_should_return_ai_friendly_meta(monkeypatch):
    mcp = _register_workflows()

    async def _fake_profile(code: str):
        return {
            "found": True,
            "code": code,
            "realtime_quote": {"price": 1820.5},
        }

    async def _fake_kline(**kwargs):
        return {"success": True, "data": {"rows": [{"close": 1820.5}]}}

    async def _fake_financials(stock_code: str):
        return {"success": True, "data": {"reportDate": "2025-Q4", "roe": 0.22}}

    async def _fake_decision_summary(**kwargs):
        return {"success": True, "data": {"action": "hold", "confidence": 0.7}}

    monkeypatch.setattr(stock_resource_mod, "build_stock_profile_resource_payload", _fake_profile)
    monkeypatch.setattr(ai_workflows, "get_kline", _fake_kline)
    monkeypatch.setattr(ai_workflows, "get_financials", _fake_financials)
    monkeypatch.setattr(ai_workflows, "get_unified_decision_summary", _fake_decision_summary)

    response = await mcp.analyze_stock_workflow(code="600519")

    assert response["success"] is True
    assert response["data"]["code"] == "600519"
    assert response["meta"]["side_effect"]["level"] == "read_only"
    assert response["meta"]["lineage"]["security_code"] == "600519"
    assert response["meta"]["quality"]["workflow"] == "analyze_stock_workflow"


@pytest.mark.asyncio
async def test_factor_candidate_workflow_should_capture_lineage_and_stateful_meta(monkeypatch):
    mcp = _register_workflows()
    calls: list[dict[str, object]] = []

    async def _fake_quant_manager(action: str, code=None, kwargs=None, params=None):
        calls.append({"action": action, "params": params or {}})
        if action == "llm_factor_mining":
            return {"success": True, "data": {"artifact_id": "factor_gen_001", "fallback_used": False, "generation_mode": "llm_provider"}}
        if action == "validate_factor_candidate":
            return {"success": True, "data": {"artifact_id": "factor_val_001"}}
        return {"success": True, "data": {"status": "ok"}}

    monkeypatch.setattr(ai_workflows, "quant_manager", _fake_quant_manager)

    response = await mcp.factor_candidate_workflow(
        task="pipeline",
        codes=["600519"],
        lookback_bars=240,
        horizon_days=12,
        max_dates=48,
        allow_fallback=False,
        persist_artifact=True,
        write_memory=True,
    )

    assert response["success"] is True
    assert response["meta"]["side_effect"]["level"] == "stateful"
    assert response["meta"]["lineage"]["generation_artifact_id"] == "factor_gen_001"
    assert response["meta"]["lineage"]["validation_artifact_id"] == "factor_val_001"
    llm_call = next(item for item in calls if item["action"] == "llm_factor_mining")
    validation_call = next(item for item in calls if item["action"] == "validate_factor_candidate")
    assert llm_call["params"]["lookback_bars"] == 240
    assert llm_call["params"]["allow_fallback"] is False
    assert validation_call["params"]["lookback_bars"] == 240
    assert validation_call["params"]["horizon_days"] == 12
    assert validation_call["params"]["max_dates"] == 48


@pytest.mark.asyncio
async def test_factor_candidate_workflow_should_derive_registry_and_decay_enrichment(monkeypatch):
    mcp = _register_workflows()
    calls: list[dict[str, object]] = []

    async def _fake_quant_manager(action: str, code=None, kwargs=None, params=None):
        payload = params or {}
        calls.append({"action": action, "params": payload})
        if action == "llm_factor_mining":
            return {
                "success": True,
                "data": {
                    "artifact_id": "factor_gen_001",
                    "expression": "pct_change(close, 5)",
                    "hypothesis": "短期动量延续",
                    "category": "momentum",
                    "fallback_used": False,
                    "generation_mode": "llm_provider",
                },
            }
        if action == "validate_factor_candidate":
            return {
                "success": True,
                "data": {
                    "artifact_id": "factor_val_001",
                    "registry_stage": "validated",
                    "factor_validation_report": {
                        "cross_section": {
                            "dates": [
                                {"date": "2026-01-01", "rank_ic": 0.08},
                                {"date": "2026-01-08", "rank_ic": 0.07},
                                {"date": "2026-01-15", "rank_ic": 0.03},
                                {"date": "2026-01-22", "rank_ic": 0.01},
                            ],
                        },
                    },
                    "memory_record": {
                        "artifact_id": "factor_memory_001",
                        "status": "degraded",
                        "runtime_feedback": [
                            {"decay_detected": True, "recommended_action": "deprecate"},
                        ],
                    },
                    "rating": {
                        "grade": "B",
                        "recommendation": "review",
                    },
                },
            }
        if action == "factor_candidate_registry":
            op = payload.get("op")
            if op == "active_pool":
                return {
                    "success": True,
                    "data": {
                        "active_pool": {
                            "count": 1,
                            "top_candidates": [
                                {"artifact_id": "factor_val_legacy", "name": "动量五日", "family": "momentum"},
                            ],
                        },
                    },
                }
            if op == "list":
                return {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "artifact_id": "factor_val_legacy",
                                "candidate": {
                                    "name": "动量五日",
                                    "family": "momentum",
                                    "expression_dsl": "pct_change(close, 10)",
                                },
                                "registry_stage": "governed",
                            },
                        ],
                    },
                }
            if op == "get":
                return {
                    "success": True,
                    "data": {
                        "item": {
                            "artifact_id": "factor_val_001",
                            "registry_stage": "challenger",
                            "memory_record_id": "factor_memory_001",
                            "lineage": {"memory_record_id": "factor_memory_001"},
                            "candidate": {
                                "name": "短期动量",
                                "family": "momentum",
                                "expression_dsl": "pct_change(close, 5)",
                            },
                        },
                    },
                }
        if action == "factor_research_memory":
            op = payload.get("op")
            if op == "stats":
                return {"success": True, "data": {"stats": {"total_records": 12}}}
            if op == "get":
                return {
                    "success": True,
                    "data": {
                        "item": {
                            "artifact_id": "factor_memory_001",
                            "status": "degraded",
                            "last_feedback_recommended_action": "deprecate",
                            "runtime_feedback": [
                                {"decay_detected": True, "recommended_action": "deprecate"},
                            ],
                        },
                    },
                }
        return {"success": True, "data": {"status": "ok"}}

    monkeypatch.setattr(ai_workflows, "quant_manager", _fake_quant_manager)

    response = await mcp.factor_candidate_workflow(
        task="pipeline",
        codes=["600519", "000001", "000002", "000003"],
        write_memory=True,
        persist_artifact=True,
    )

    assert response["success"] is True
    enrichment = response["data"]["factor_enrichment"]
    assert enrichment["registry_status"] == "active"
    assert enrichment["decay_monitor_status"] == "decayed"
    assert enrichment["originality"]["score"] < 1.0
    assert response["data"]["summary"]["artifact_id"] == "factor_val_001"
    assert any(
        item["action"] == "factor_candidate_registry" and item["params"].get("op") == "get"
        for item in calls
    )
    assert any(
        item["action"] == "factor_research_memory" and item["params"].get("op") == "get"
        for item in calls
    )


@pytest.mark.asyncio
async def test_strategy_review_workflow_should_return_resource_and_runtime_context(monkeypatch):
    mcp = _register_workflows()

    async def _fake_strategy_review_payload(strategy_id: str):
        return {
            "found": True,
            "strategy_id": strategy_id,
            "summary": {"current_status": "listed", "open_risk_count": 1},
        }

    async def _fake_strategy_manager(action: str, kwargs="{}", params=None):
        return {"success": True, "data": {"action": action, "status": "ok"}}

    monkeypatch.setattr(strategy_resource_mod, "build_strategy_review_payload", _fake_strategy_review_payload)
    monkeypatch.setattr(ai_workflows, "strategy_manager", _fake_strategy_manager)

    response = await mcp.strategy_review_workflow(strategy_id="strat_demo")

    assert response["success"] is True
    assert response["data"]["strategy_id"] == "strat_demo"
    assert response["meta"]["side_effect"]["level"] == "read_only"
    assert response["meta"]["lineage"]["strategy_id"] == "strat_demo"


@pytest.mark.asyncio
async def test_prediction_and_data_quality_workflows_should_support_artifact_hooks(monkeypatch):
    mcp = _register_workflows()
    persisted: list[dict] = []

    async def _fake_register_artifact_async(payload: dict):
        persisted.append(dict(payload))
        return payload

    monkeypatch.setattr(ai_workflows, "register_artifact_async", _fake_register_artifact_async)

    prediction = await mcp.prediction_diagnosis_workflow(
        probabilities=[0.2, 0.8, 0.7],
        labels=[0, 1, 1],
        method="raw",
        dataset_id="pred_ds",
        run_id="pred_run_001",
        persist_artifact=True,
        output_artifact_id="pred_artifact_001",
    )
    quality = await mcp.data_quality_workflow(
        dataset_id="dataset_demo",
        records=[{"code": "600519", "date": "2026-04-01"}, {"code": "000001"}],
        required_fields=["code", "date"],
        persist_artifact=True,
        output_artifact_id="dq_artifact_001",
    )

    assert prediction["success"] is True
    assert prediction["meta"]["lineage"]["artifact_id"] == "pred_artifact_001"
    assert prediction["meta"]["side_effect"]["level"] == "stateful"
    assert quality["success"] is True
    assert quality["meta"]["lineage"]["artifact_id"] == "dq_artifact_001"
    assert quality["meta"]["quality"]["minimum_quality_passed"] is False
    assert {item["artifact_id"] for item in persisted} == {"pred_artifact_001", "dq_artifact_001"}
