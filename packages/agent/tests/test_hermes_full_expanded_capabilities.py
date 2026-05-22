from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from aiask_agent.model_client import MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore
from aiask_agent.tool_registry import build_default_tool_registry
from aiask_agent.tools.policy import ToolPolicy, ToolPolicyEngine


def _control_headers() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


def _full_policy(tmp_path) -> ToolPolicyEngine:
    return ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),)))


def test_expanded_hermes_tools_are_full_mode_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    finance = build_default_tool_registry(session_store=AgentSessionStore(tmp_path / "finance.sqlite3"))
    assert "agent_gateway_status" not in finance.names()
    assert "agent_rl_list_environments" not in finance.names()
    assert "agent_ha_list_entities" not in finance.names()

    full = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "full.sqlite3"),
        policy_engine=_full_policy(tmp_path),
    )
    names = set(full.names())
    assert {
        "agent_tui_status",
        "agent_terminal_backends",
        "agent_computer_use",
        "agent_file_mutation_verify",
        "agent_x_search",
        "agent_video_generate",
        "agent_session_handoff",
        "agent_subgoal",
        "agent_gateway_status",
        "agent_gateway_send_message",
        "agent_learning_status",
        "agent_ha_list_entities",
        "agent_ha_call_service",
        "agent_rl_list_environments",
        "agent_rl_start_training",
    } <= names

    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "runtime.sqlite3"),
        tool_registry=full,
        max_iterations=2,
    )
    assert "agent_moa" in runtime.tool_registry.names()


def test_expanded_full_mode_api_surfaces(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(model_client=MockModelClient(), session_store=store, max_iterations=2)
    client = TestClient(create_app(runtime=runtime))

    status = client.get("/v1/hermes/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["embedded_vendor_runtime"] is False
    assert payload["full_scope"] == "hermes_full_runtime"
    assert payload["platform_gateway"]["implementation"] == "aiask_native"
    assert payload["providers"]["object"] == "aiask.model_provider_status"
    assert payload["memory"]["default_provider"] == "sqlite"
    assert payload["security"]["status"] == "implemented"
    assert payload["skill_packs"]["vendor_text_copied"] is False
    assert any(item["name"] == "local" for item in payload["terminal_backends"])

    for path in (
        "/v1/gateway/status",
        "/v1/gateway/platforms",
        "/v1/gateway/messages",
        "/v1/terminal/backends",
        "/v1/terminal/sessions",
        "/v1/learning/status",
        "/v1/learning/review",
        "/v1/rl/environments",
        "/v1/rl/config",
        "/v1/rl/runs",
    ):
        response = client.get(path, headers=_control_headers())
        assert response.status_code == 200, path

    sent = client.post(
        "/v1/gateway/send",
        headers=_control_headers(),
        json={"platform": "local", "target": "desktop", "message": "hello"},
    )
    assert sent.status_code == 200
    assert sent.json()["data"]["adapter"]["ok"] is True


def test_expanded_tools_report_configured_false_without_external_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    full = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=_full_policy(tmp_path),
    )

    rl_start = asyncio.run(full.call_tool("agent_rl_start_training", {"environment": "demo"}))
    assert rl_start["success"] is False
    assert rl_start["data"]["configured"] is False

    ha_entities = asyncio.run(full.call_tool("agent_ha_list_entities", {}))
    assert ha_entities["success"] is False
    assert ha_entities["data"]["configured"] is False

    ha_call = asyncio.run(full.call_tool("agent_ha_call_service", {"domain": "light", "service": "turn_on", "entity_id": "light.desk"}))
    assert ha_call["success"] is False
    assert ha_call["error_code"] == "APPROVAL_REQUIRED"

    docker = asyncio.run(full.call_tool("agent_terminal", {"command": "pwd", "backend": "daytona"}))
    assert docker["success"] is False
    assert docker["data"]["backend"]["configured"] is False

    gateway = asyncio.run(full.call_tool("agent_gateway_send_message", {"platform": "feishu", "target": "chat", "message": "hello"}))
    assert gateway["success"] is False
    assert gateway["data"]["adapter"]["configured"] is False

    x_search = asyncio.run(full.call_tool("agent_x_search", {"query": "AIASK"}))
    assert x_search["success"] is False
    assert x_search["data"]["configured"] is False

    video = asyncio.run(full.call_tool("agent_video_generate", {"action": "create", "prompt": "market brief"}))
    assert video["success"] is False
    assert video["data"]["configured"] is False

    computer = asyncio.run(full.call_tool("agent_computer_use", {"action": "status"}))
    assert computer["success"] is True
    assert computer["data"]["configured"] is False
    assert computer["data"]["os_desktop_control"] is False


def test_v014_native_session_file_and_subgoal_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    full = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=_full_policy(tmp_path),
    )

    write = asyncio.run(full.call_tool("agent_file_write", {"path": "demo.py", "content": "x = 1\n"}))
    assert write["success"] is True
    assert write["data"]["mutation_verification"]["exists"] is True
    assert write["data"]["mutation_verification"]["sha256"]
    assert write["data"]["diagnostics"][0]["status"] == "passed"

    verify = asyncio.run(full.call_tool("agent_file_mutation_verify", {"path": "demo.py"}))
    assert verify["success"] is True
    assert verify["data"]["allowed_workspace"] is True
    assert verify["data"]["sha256"] == write["data"]["mutation_verification"]["sha256"]

    subgoal = asyncio.run(
        full.call_tool(
            "agent_subgoal",
            {"action": "add", "session_id": "s1", "title": "collect evidence", "criteria": ["tests pass"]},
        )
    )
    assert subgoal["success"] is True
    assert subgoal["data"]["subgoal"]["criteria"] == ["tests pass"]
    status = asyncio.run(full.call_tool("agent_subgoal", {"action": "status", "session_id": "s1"}))
    assert status["data"]["by_status"]["pending"] == 1

    handoff = asyncio.run(
        full.call_tool(
            "agent_session_handoff",
            {"action": "request", "session_id": "s1", "target": "ops", "reason": "continue review"},
        )
    )
    assert handoff["success"] is True
    handoff_id = handoff["data"]["handoff"]["handoff_id"]
    done = asyncio.run(full.call_tool("agent_session_handoff", {"action": "complete", "handoff_id": handoff_id}))
    assert done["success"] is True
    assert done["data"]["handoff"]["status"] == "completed"


def test_moa_runtime_tool_uses_aiask_model_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=store,
        tool_registry=build_default_tool_registry(session_store=store, policy_engine=_full_policy(tmp_path)),
        max_iterations=2,
    )
    result = asyncio.run(runtime.tool_registry.call_tool("agent_moa", {"user_prompt": "Summarize AIASK"}))
    assert result["success"] is True
    assert result["data"]["configured"] is True
    assert result["data"]["aggregator_model"] == runtime.model


def test_dynamic_plugin_tools_are_wrapped_as_agent_tools(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AIASK_AGENT_HOME", str(home))
    plugin_dir = home / "plugins" / "demo-plugin"
    plugin_dir.mkdir(parents=True)
    plugin_dir.joinpath("plugin.json").write_text(
        json.dumps(
            {
                "name": "demo-plugin",
                "enabled": True,
                "tools": [{"name": "summarize", "description": "Summarize text", "parameters": {"type": "object"}}],
            }
        ),
        encoding="utf-8",
    )
    full = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=_full_policy(tmp_path),
    )
    wrapped = "agent_plugin_demo_plugin_summarize"
    assert wrapped in full.names()
    result = asyncio.run(full.call_tool(wrapped, {"text": "hello"}))
    assert result["success"] is True
    assert result["data"]["configured"] is False
