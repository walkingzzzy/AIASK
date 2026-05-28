from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiask_agent.model_client import MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore


def _runtime(tmp_path) -> AgentRuntime:
    return AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    return TestClient(create_app(runtime=_runtime(tmp_path)))


def test_financial_manager_catalog_and_status_redact_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-financial-manager-secret")
    client = _client(tmp_path, monkeypatch)

    catalog = client.get("/v1/desktop/financial-manager/catalog")
    status = client.get("/v1/desktop/financial-manager/status")

    assert catalog.status_code == 200
    assert status.status_code == 200
    catalog_payload = catalog.json()
    status_payload = status.json()
    assert catalog_payload["safety"]["live_trading_enabled"] is False
    assert any(item["mode"] == "blocked" for item in catalog_payload["actions"])
    assert "broker" in status_payload
    raw = json.dumps({"catalog": catalog_payload, "status": status_payload})
    assert "sk-financial-manager-secret" not in raw


def test_financial_manager_read_only_query_dispatches_agent_tool(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/desktop/financial-manager/query",
        json={
            "capability_id": "portfolio",
            "action_id": "risk",
            "params": {"codes": ["600519", "000001"], "weights": [0.6, 0.4]},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "aiask.desktop.financial_manager.query"
    assert payload["tool"] == "agent_portfolio_risk"
    assert payload["success"] is True
    assert payload["meta"]["side_effect"]["level"] == "read_only"


def test_financial_manager_stateful_query_requires_intent_and_intent_is_control_gated(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    body = {
        "capability_id": "portfolio",
        "action_id": "create",
        "params": {"name": "Desk book"},
        "rationale": "create from test",
    }

    query = client.post("/v1/desktop/financial-manager/query", json=body)
    denied = client.post("/v1/desktop/financial-manager/intent", json=body)
    created = client.post("/v1/desktop/financial-manager/intent", headers={"Authorization": "Bearer secret"}, json=body)

    assert query.status_code == 200
    assert query.json()["error_code"] == "FINANCIAL_ACTION_REQUIRES_INTENT"
    assert denied.status_code == 401
    assert created.status_code == 200
    payload = created.json()
    assert payload["success"] is True
    assert payload["data"]["intent"]["action"] == "portfolio_manager.create"
    assert payload["data"]["intent"]["status"] == "awaiting_confirmation"


def test_financial_manager_live_trade_actions_are_blocked(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    query = client.post(
        "/v1/desktop/financial-manager/query",
        json={"capability_id": "broker-live", "action_id": "place_order", "params": {"broker_token": "should-not-leak"}},
    )
    intent = client.post(
        "/v1/desktop/financial-manager/intent",
        headers={"Authorization": "Bearer secret"},
        json={"capability_id": "broker-live", "action_id": "cancel_order", "params": {"broker_token": "should-not-leak"}},
    )

    assert query.status_code == 200
    assert intent.status_code == 200
    assert query.json()["error_code"] == "FINANCIAL_ACTION_BLOCKED"
    assert intent.json()["error_code"] == "FINANCIAL_ACTION_BLOCKED"
    assert "should-not-leak" not in json.dumps({"query": query.json(), "intent": intent.json()})
