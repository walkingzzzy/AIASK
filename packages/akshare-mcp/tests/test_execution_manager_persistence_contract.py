"""P2 contract tests for execution_manager persistence and recovery."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "strategy-factory" / "src"))

from akshare_mcp.server import mcp
from akshare_mcp.tools.managers import execution_manager as execution_mod


def _normalize_result(result):
    if isinstance(result, str):
        return json.loads(result)
    return result


@pytest.fixture(autouse=True)
def _stub_execution_artifact_persistence(monkeypatch):
    artifact_store: dict[str, dict] = {}

    async def _fake_register_artifact_async(artifact: dict):
        artifact_store[str(artifact.get("artifact_id") or "")] = deepcopy(artifact)
        return deepcopy(artifact)

    async def _fake_get_artifact_async(artifact_id: str):
        item = artifact_store.get(str(artifact_id or ""))
        return deepcopy(item) if item is not None else None

    async def _fake_list_artifacts_async(limit: int = 20):
        items = list(artifact_store.values())
        items.sort(
            key=lambda item: str(
                ((item.get("payload") or {}).get("task") or {}).get("updated_at")
                or (item.get("payload") or {}).get("updated_at")
                or item.get("updated_at")
                or ""
            ),
            reverse=True,
        )
        return [
            {
                "artifact_id": item.get("artifact_id"),
                "strategy": item.get("strategy"),
                "code": item.get("code"),
                "updated_at": str(
                    ((item.get("payload") or {}).get("task") or {}).get("updated_at")
                    or (item.get("payload") or {}).get("updated_at")
                    or item.get("updated_at")
                    or ""
                ),
            }
            for item in items[: max(1, int(limit or 20))]
        ]

    monkeypatch.setattr(execution_mod, "register_artifact_async", _fake_register_artifact_async)
    monkeypatch.setattr(execution_mod, "get_artifact_async", _fake_get_artifact_async)
    monkeypatch.setattr(execution_mod, "list_artifacts_async", _fake_list_artifacts_async)
    monkeypatch.setattr(
        execution_mod,
        "_build_cost_model",
        lambda kwargs, total_shares: {
            "estimated": {
                "notional": float(total_shares) * float(kwargs.get("reference_price", 100.0) or 100.0),
                "total": 12.5,
            }
        },
    )
    monkeypatch.setattr(execution_mod, "_enrich_kwargs_with_realtime", lambda code, kwargs: kwargs)
    monkeypatch.setattr(
        execution_mod,
        "evaluate_order_compliance",
        lambda code, direction, total_shares, price_raw: {
            "warnings": [],
            "violations": [],
            "checks": {"mock": True},
            "order_amount": float(total_shares) * float(price_raw or 0.0),
        },
    )
    monkeypatch.setattr(execution_mod, "audit_event", lambda **kwargs: None)

    execution_mod._EXECUTION_TASKS.clear()
    execution_mod._SOFT_GATE_RUNTIME_CONFIG.clear()
    execution_mod._SOFT_GATE_RUNTIME_CONFIG.update(
        {
            "default_profile": "balanced",
            "default_threshold_overrides": {},
            "code_profiles": {},
        }
    )
    execution_mod._RUNTIME_CONFIG_LOADED = False

    yield artifact_store

    execution_mod._EXECUTION_TASKS.clear()
    execution_mod._SOFT_GATE_RUNTIME_CONFIG.clear()
    execution_mod._SOFT_GATE_RUNTIME_CONFIG.update(
        {
            "default_profile": "balanced",
            "default_threshold_overrides": {},
            "code_profiles": {},
        }
    )
    execution_mod._RUNTIME_CONFIG_LOADED = False


@pytest.mark.asyncio
async def test_execution_manager_should_recover_task_from_persisted_artifact(_stub_execution_artifact_persistence):
    tool = mcp._tool_manager._tools["execution_manager"]

    created = _normalize_result(
        await tool.run(
            {
                "action": "twap",
                "params": {
                    "code": "600519",
                    "total_shares": 1200,
                    "duration": 20,
                    "reference_price": 1800.0,
                },
            }
        )
    )
    assert created["success"] is True
    task_id = created["data"]["task_id"]

    assert task_id in _stub_execution_artifact_persistence

    execution_mod._EXECUTION_TASKS.clear()

    listed = _normalize_result(await tool.run({"action": "list"}))
    assert listed["success"] is True
    assert any(item["task_id"] == task_id for item in listed["data"]["tasks"])

    summary = _normalize_result(
        await tool.run({"action": "summary", "params": {"task_id": task_id}})
    )
    assert summary["success"] is True
    assert summary["data"]["task"]["task_id"] == task_id
    assert summary["data"]["task"]["code"] == "600519"


@pytest.mark.asyncio
async def test_execution_manager_should_persist_runtime_config(_stub_execution_artifact_persistence):
    tool = mcp._tool_manager._tools["execution_manager"]

    updated = _normalize_result(
        await tool.run(
            {
                "action": "set_config",
                "params": {
                    "default_profile": "conservative",
                    "code_profiles": {"600519": "aggressive"},
                },
            }
        )
    )
    assert updated["success"] is True
    assert execution_mod._EXECUTION_CONFIG_ARTIFACT_ID in _stub_execution_artifact_persistence

    execution_mod._SOFT_GATE_RUNTIME_CONFIG.clear()
    execution_mod._SOFT_GATE_RUNTIME_CONFIG.update(
        {
            "default_profile": "balanced",
            "default_threshold_overrides": {},
            "code_profiles": {},
        }
    )
    execution_mod._RUNTIME_CONFIG_LOADED = False

    loaded = _normalize_result(await tool.run({"action": "get_config"}))
    assert loaded["success"] is True
    assert loaded["data"]["soft_gate_config"]["default_profile"] == "conservative"
    assert loaded["data"]["soft_gate_config"]["code_profiles"]["600519"] == "aggressive"
