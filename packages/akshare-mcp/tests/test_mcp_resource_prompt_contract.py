"""Runtime contract tests for MCP resources and prompts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "strategy-factory" / "src"))

from akshare_mcp.server import mcp
from akshare_mcp.prompts import analysis as prompt_mod
from akshare_mcp.resources import lineage as lineage_resource_mod
from akshare_mcp.resources import stock_and_watchlist as stock_resource_mod
from akshare_mcp.resources import strategy as strategy_resource_mod


class _FakeAcquire:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDb:
    def acquire(self):
        return _FakeAcquire(self)

    async def fetch(self, query: str, *args):
        if "FROM watchlist_groups" in query:
            return [
                {
                    "id": "default",
                    "name": "我的自选",
                    "user_id": args[0],
                    "color": "#334155",
                    "sort_order": 0,
                    "created_at": "2026-03-30T00:00:00+00:00",
                }
            ]
        if "FROM watchlist" in query:
            return [
                {
                    "id": "w1",
                    "user_id": args[0],
                    "code": "600519",
                    "name": "贵州茅台",
                    "group_id": "default",
                    "sort_order": 0,
                    "note": "核心观察",
                    "added_at": "2026-03-30T00:00:00+00:00",
                }
            ]
        return []

    async def get_stock_info(self, code: str):
        return {
            "code": code,
            "name": "贵州茅台",
            "industry": "白酒",
            "market": "SH",
            "market_cap": 2.5e12,
            "pe_ratio": 28.4,
            "pb_ratio": 8.2,
            "list_date": "2001-08-27",
        }

    async def get_strategy(self, strategy_id: str):
        return {
            "id": strategy_id,
            "name": "Quality Momentum",
            "status": "listed",
            "strategy_type": "quant",
        }

    async def get_latest_strategy_projection_snapshot(self, strategy_id: str):
        return {
            "id": 1,
            "strategy_id": strategy_id,
            "projection": {
                "strategy_id": strategy_id,
                "current_status": "listed",
                "open_risk_count": 1,
                "runtime_control_mode": "monitor",
            },
        }

    async def get_latest_strategy_promotion_review(self, strategy_id: str):
        return {
            "strategy_id": strategy_id,
            "status": "approved",
            "recommendation": "promote",
        }

    async def get_strategy_runtime_control(self, strategy_id: str):
        return {
            "strategy_id": strategy_id,
            "control_mode": "monitor",
            "status": "active",
        }

    async def list_strategy_runtime_risk_events(self, strategy_id: str, status: str = "open", limit: int = 20):
        return [
            {
                "strategy_id": strategy_id,
                "status": status,
                "severity": "medium",
                "message": "turnover spike",
            }
        ]

    async def list_strategy_task_runs(self, strategy_id: str, limit: int = 10):
        return [
            {
                "strategy_id": strategy_id,
                "task_name": "strategy_runtime_cycle",
                "status": "completed",
            }
        ]

    async def get_strategy_factory_run(self, run_id: str):
        return {
            "run_id": run_id,
            "status": "completed",
            "elapsed_seconds": 12.5,
            "started_at": "2026-03-30T00:00:00+00:00",
            "completed_at": "2026-03-30T00:00:12+00:00",
        }


def _normalize_result(result):
    if isinstance(result, str):
        return json.loads(result)
    return result


def _message_text(message) -> str:
    content = getattr(message, "content", None)
    if isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, dict):
        return str(content.get("text") or "")
    return str(getattr(content, "text", "") or "")


@pytest.fixture(autouse=True)
def _stub_resource_and_prompt_dependencies(monkeypatch):
    fake_db = _FakeDb()

    async def _fake_build_stock_profile_payload(db, code: str, **kwargs):
        return {
            "profile_type": "both",
            "version": "resource_v1",
            "vector_dim": 16,
            "metadata": {
                "summary_text": f"{code} profile summary",
                "feature_coverage": ["valuation", "momentum"],
                "raw_features": {
                    "pe_ratio": 28.4,
                    "pb_ratio": 8.2,
                    "momentum_20d": 0.11,
                },
            },
        }

    async def _fake_factor_prompt(db, codes: list[str], **kwargs):
        return SimpleNamespace(
            system_prompt="你是一名资深量化研究员。",
            user_prompt=f"请围绕 {','.join(codes)} 生成候选因子。",
            context_summary={"codes": codes},
            request_payload={"codes": codes},
            source_chain=["tests.fake_factor_prompt"],
            schema_path="",
        )

    async def _fake_strategy_review_payload(strategy_id: str):
        return {
            "found": True,
            "strategy_id": strategy_id,
            "strategy": {
                "id": strategy_id,
                "name": "Quality Momentum",
                "status": "listed",
            },
            "projection": {
                "current_status": "listed",
                "open_risk_count": 1,
                "runtime_control_mode": "monitor",
            },
            "latest_promotion_review": {
                "status": "approved",
                "recommendation": "promote",
            },
            "runtime_control": {
                "control_mode": "monitor",
                "status": "active",
            },
            "open_risks": [{"severity": "medium", "message": "turnover spike"}],
            "summary": {
                "current_status": "listed",
                "open_risk_count": 1,
                "runtime_control_mode": "monitor",
                "latest_promotion_status": "approved",
                "latest_promotion_recommendation": "promote",
            },
        }

    monkeypatch.setattr(stock_resource_mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(strategy_resource_mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(lineage_resource_mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(prompt_mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(stock_resource_mod, "build_stock_profile_payload", _fake_build_stock_profile_payload)
    monkeypatch.setattr(
        stock_resource_mod,
        "get_stock_info",
        lambda code: {"success": True, "data": {"code": code, "name": "贵州茅台", "industry": "白酒"}},
    )
    monkeypatch.setattr(
        stock_resource_mod,
        "get_realtime_quote",
        lambda code: {"success": True, "data": {"price": 1800.5, "pct_chg": 1.2, "volume": 12345}},
    )
    monkeypatch.setattr(prompt_mod, "build_factor_mining_prompt", _fake_factor_prompt)
    monkeypatch.setattr(prompt_mod, "build_strategy_review_payload", _fake_strategy_review_payload)
    monkeypatch.setattr(prompt_mod, "get_financials", lambda code: {"success": True, "data": {"reportDate": "2025-Q4", "roe": 0.21}})

    async def _fake_decision_summary(**kwargs):
        return {"success": True, "data": {"action": "hold", "confidence": 0.66}}

    monkeypatch.setattr(prompt_mod, "get_unified_decision_summary", _fake_decision_summary)


@pytest.mark.asyncio
async def test_runtime_should_expose_resources_and_prompts():
    resources = await mcp.list_resources()
    templates = await mcp.list_resource_templates()
    prompts = await mcp.list_prompts()

    resource_uris = {str(item.uri) for item in resources}
    template_uris = {str(item.uriTemplate) for item in templates}
    prompt_names = {item.name for item in prompts}

    assert "resource://server/capabilities" in resource_uris
    assert "resource://server/tool-catalog" in resource_uris
    assert "resource://stock/{code}/profile" in template_uris
    assert "resource://watchlist/{user_id}/snapshot" in template_uris
    assert "resource://strategy/{id}/review" in template_uris
    assert "resource://workflow/{name}/guide" in template_uris
    assert "resource://run/{run_id}" in template_uris
    assert "resource://dataset/{dataset_id}/quality" in template_uris
    assert {"factor-mining", "strategy-review", "stock-analysis", "prediction-diagnosis", "factor-registry-review", "strategy-promotion-review"} <= prompt_names


@pytest.mark.asyncio
async def test_runtime_should_read_resources_and_render_prompts():
    capabilities = await mcp.read_resource("resource://server/capabilities")
    tool_catalog = await mcp.read_resource("resource://server/tool-catalog")
    stock_profile = await mcp.read_resource("resource://stock/600519/profile")
    watchlist = await mcp.read_resource("resource://watchlist/default/snapshot")
    strategy_review = await mcp.read_resource("resource://strategy/strat_demo/review")
    workflow_guide = await mcp.read_resource("resource://workflow/stock-analysis/guide")
    run_snapshot = await mcp.read_resource("resource://run/factory_run_demo")
    dataset_quality = await mcp.read_resource("resource://dataset/dataset_demo/quality")
    factor_prompt = await mcp.get_prompt("factor-mining", {"codes": "600519,000001"})
    review_prompt = await mcp.get_prompt("strategy-review", {"strategy_id": "strat_demo"})
    stock_prompt = await mcp.get_prompt("stock-analysis", {"code": "600519"})
    prediction_prompt = await mcp.get_prompt("prediction-diagnosis", {"probabilities": "[0.2,0.8]", "labels": "[0,1]"})
    promotion_prompt = await mcp.get_prompt("strategy-promotion-review", {"strategy_id": "strat_demo"})

    capabilities_payload = json.loads(capabilities[0].content)
    tool_catalog_payload = json.loads(tool_catalog[0].content)
    stock_payload = json.loads(stock_profile[0].content)
    watchlist_payload = json.loads(watchlist[0].content)
    strategy_payload = json.loads(strategy_review[0].content)
    workflow_payload = json.loads(workflow_guide[0].content)
    run_payload = json.loads(run_snapshot[0].content)
    dataset_payload = json.loads(dataset_quality[0].content)

    assert capabilities_payload["resources"]["count"] >= 1
    assert capabilities_payload["ai_catalog"]["tool_contract_count"] >= 1
    assert tool_catalog_payload["count"] >= 1
    assert stock_payload["code"] == "600519"
    assert stock_payload["profile"]["profile_type"] == "both"
    assert watchlist_payload["summary"]["item_count"] == 1
    assert strategy_payload["summary"]["current_status"] == "listed"
    assert workflow_payload["name"] == "stock-analysis"
    assert run_payload["found"] is True
    assert dataset_payload["found"] is False
    assert len(factor_prompt.messages) == 2
    assert len(review_prompt.messages) == 2
    assert len(stock_prompt.messages) == 2
    assert len(prediction_prompt.messages) == 2
    assert len(promotion_prompt.messages) == 2
    assert "600519" in _message_text(factor_prompt.messages[1])
    assert "Quality Momentum" in _message_text(review_prompt.messages[1])
