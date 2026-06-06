from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiask_agent.approvals import ApprovalStore
from aiask_agent.gateway import GatewayMessageStore
from aiask_agent.intents import ActionIntentStore, IntentExecutor
from aiask_agent.model_client import MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore


def _client_with_state(tmp_path, monkeypatch) -> tuple[TestClient, AgentSessionStore, ActionIntentStore]:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.delenv("AIASK_AGENT_MCP_CONFIG", raising=False)
    monkeypatch.delenv("MCP_PORT", raising=False)

    store = AgentSessionStore(tmp_path / "state.sqlite3")
    intent_store = ActionIntentStore(tmp_path / "intents.sqlite3")
    runtime = AgentRuntime(model_client=MockModelClient(), session_store=store, max_iterations=2)
    client = TestClient(create_app(runtime=runtime, intent_executor=IntentExecutor(intent_store)))
    return client, store, intent_store


def _seed_main_chain(store: AgentSessionStore, intent_store: ActionIntentStore) -> str:
    session_id = store.create_session(session_id="sess_contract", user_id="local", title="Contract session")
    store.append_message(session_id, {"role": "user", "content": "analyze 600519"})
    store.append_message(session_id, {"role": "assistant", "content": "analysis ready"})
    run_id = store.create_run(session_id, {"response_id": "resp_contract", "tool_call_count": 1})
    store.append_run_event(run_id, "tool.called", {"tool": "agent_analyze_stock", "status": "completed"})
    store.append_run_event(run_id, "approval.intent_created", {"intent_id": "intent_contract", "status": "pending"})
    store.append_run_event(run_id, "gateway.message_failed", {"platform": "desktop", "status": "failed", "error": "mock failed"})
    store.update_run(run_id, status="completed", payload={"response_id": "resp_contract", "tool_call_count": 1})
    intent_store.create(action="watchlist_manager.add", params={"session_id": session_id, "code": "600519"}, user_id="local")
    ApprovalStore(store.path).create(tool_name="agent_gateway_send", action="gateway.send", arguments={"session_id": session_id}, reason="contract")
    GatewayMessageStore(store.path).record(
        direction="outbound",
        platform="desktop",
        target="local",
        content="failed",
        status="failed",
        session_id=session_id,
        user_id="local",
    )
    return run_id


def test_desktop_workbench_summary_contract_includes_session_run_flags(tmp_path, monkeypatch) -> None:
    client, store, intent_store = _client_with_state(tmp_path, monkeypatch)
    run_id = _seed_main_chain(store, intent_store)

    response = client.get("/v1/desktop/workbench/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "aiask.desktop.workbench.summary"
    assert payload["queues"]["pending_intents"] == 1
    assert payload["queues"]["pending_approvals"] == 1
    assert payload["queues"]["gateway_failed"] == 1
    assert payload["access"]["full_mode_active"] is True
    assert payload["access"]["sessions_admin_available"] is True

    session = payload["recent_sessions"][0]
    assert session["session_id"] == "sess_contract"
    assert session["created_at"]
    assert session["message_count"] == 2
    assert session["has_pending_approval"] is True
    assert session["last_run_id"] == run_id
    assert session["last_run_summary"]["response_id"] == "resp_contract"
    assert session["last_event"]["kind"] == "gateway"

    run = payload["recent_runs"][0]
    assert run["run_id"] == run_id
    assert run["last_event"]["jump_target"] == "gateway"
    assert run["has_pending_approval"] is True
    assert run["has_errors"] is True


def test_desktop_runs_and_hermes_sessions_contracts_are_backward_compatible(tmp_path, monkeypatch) -> None:
    client, store, intent_store = _client_with_state(tmp_path, monkeypatch)
    run_id = _seed_main_chain(store, intent_store)

    runs_response = client.get("/v1/desktop/runs?limit=5")
    sessions_response = client.get("/v1/hermes/sessions", headers={"Authorization": "Bearer secret"})

    assert runs_response.status_code == 200
    run = runs_response.json()["data"][0]
    assert run["run_id"] == run_id
    assert run["event_count"] == 3
    assert run["last_event"]["event_type"] == "gateway.message_failed"
    assert run["last_event"]["error_message"] == "mock failed"

    assert sessions_response.status_code == 200
    session = sessions_response.json()["data"][0]
    assert session["session_id"] == "sess_contract"
    assert session["updated_at"]
    assert session["last_run_summary"]["last_event"]["kind"] == "gateway"
    assert session["metadata"] == {}


def test_run_events_sse_returns_normalized_event_payload(tmp_path, monkeypatch) -> None:
    client, store, intent_store = _client_with_state(tmp_path, monkeypatch)
    run_id = _seed_main_chain(store, intent_store)

    response = client.get(f"/v1/runs/{run_id}/events")

    assert response.status_code == 200
    chunks = [chunk for chunk in response.text.split("\n\n") if "data:" in chunk]
    events = [json.loads(chunk.split("data:", 1)[1].strip()) for chunk in chunks]
    assert [event["kind"] for event in events] == ["tool", "approval", "gateway"]
    assert events[0]["tool_name"] == "agent_analyze_stock"
    assert events[1]["jump_target"] == "tools-intents-approvals"
    assert events[2]["error_message"] == "mock failed"
