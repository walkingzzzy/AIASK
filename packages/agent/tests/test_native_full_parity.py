from __future__ import annotations

import asyncio
import json
import sys

from fastapi.testclient import TestClient

from aiask_agent.adapters import quant
from aiask_agent.model_client import MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore
from aiask_agent.tool_registry import build_default_tool_registry
from aiask_agent.tools.policy import ToolPolicy, ToolPolicyEngine


def _control_headers() -> dict[str, str]:
    return {"Authorization": "Bearer secret"}


def test_fastapi_native_full_management_surface(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    mcp_config = tmp_path / "mcp_servers.json"
    mcp_config.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "finance-demo",
                        "domain": "financial",
                        "transport": "stdio",
                        "command": "python",
                        "tools": [
                            {"name": "quote", "description": "quote tool", "parameters": {"type": "object"}},
                            {"name": "terminal", "description": "shell tool"},
                        ],
                        "resources": [{"uri": "aiask://quotes"}],
                        "prompts": [{"name": "risk-review"}],
                        "auth": "oauth",
                    },
                    {
                        "name": "general-demo",
                        "domain": "general",
                        "transport": "http",
                        "url": "http://localhost:9999/mcp",
                        "tools": [{"name": "browser", "description": "browser tool"}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIASK_AGENT_MCP_CONFIG", str(mcp_config))

    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=store,
        max_iterations=2,
    )
    client = TestClient(create_app(runtime=runtime))

    status = client.get("/v1/hermes/status")
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["implementation"] == "aiask_native"
    assert status_payload["embedded_vendor_runtime"] is False
    assert status_payload["parity"]["status"] == "in_progress"

    denied = client.get("/v1/hermes/tools")
    assert denied.status_code == 401
    tools = client.get("/v1/hermes/tools", headers=_control_headers())
    assert tools.status_code == 200
    names = {item["name"] for item in tools.json()["data"]}
    assert {"agent_terminal", "agent_webhook", "agent_mcp_manage", "agent_cronjob"} <= names
    assert not any(not name.startswith("agent_") for name in names)

    mcp_tools = client.get("/v1/mcp/tools?all=true", headers=_control_headers())
    assert mcp_tools.status_code == 200
    assert {item["name"] for item in mcp_tools.json()["data"]} == {"quote", "terminal", "browser"}
    resources = client.get("/v1/mcp/resources", headers=_control_headers())
    assert resources.json()["data"][0]["uri"] == "aiask://quotes"
    prompts = client.get("/v1/mcp/prompts", headers=_control_headers())
    assert prompts.json()["data"][0]["name"] == "risk-review"
    oauth = client.get("/v1/mcp/oauth_status", headers=_control_headers())
    assert oauth.json()["data"][0]["configured"] is True
    resource_read = client.post(
        "/v1/mcp/resources/read",
        headers={**_control_headers(), "Origin": "http://127.0.0.1:1420"},
        json={"server": "missing-demo", "uri": "aiask://quotes"},
    )
    assert resource_read.status_code == 200
    assert resource_read.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert resource_read.json()["success"] is False
    assert resource_read.json()["error_code"] in {"MCP_DISCOVERY_FAILED", "MCP_DISCOVERY_CONNECTION_FAILED"}
    prompt_get = client.post(
        "/v1/mcp/prompts/get",
        headers={**_control_headers(), "Origin": "http://127.0.0.1:1420"},
        json={"server": "missing-demo", "name": "risk-review"},
    )
    assert prompt_get.status_code == 200
    assert prompt_get.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert prompt_get.json()["success"] is False

    created_skill = client.post(
        "/v1/skills",
        headers=_control_headers(),
        json={"name": "risk-review", "description": "Risk review", "content": "# Risk Review\n"},
    )
    assert created_skill.status_code == 200
    skills = client.get("/v1/skills", headers=_control_headers())
    assert any(item["name"] == "risk-review" for item in skills.json()["data"]["skills"])

    plugin = client.post(
        "/v1/plugins",
        headers=_control_headers(),
        json={"name": "audit-plugin", "manifest": {"description": "Audit", "enabled": False}},
    )
    assert plugin.status_code == 200
    enabled = client.patch("/v1/plugins/audit-plugin", headers=_control_headers(), json={"enabled": True})
    assert enabled.status_code == 200
    plugins = client.get("/v1/plugins", headers=_control_headers())
    assert any(item["name"] == "audit-plugin" and item["enabled"] for item in plugins.json()["data"])
    self_test = client.post("/v1/plugins/audit-plugin/tools/__manifest__/test", headers=_control_headers(), json={})
    assert self_test.status_code == 200
    assert self_test.json()["success"] is True
    assert self_test.json()["data"]["test_type"] == "manifest"
    missing_tool = client.post("/v1/plugins/audit-plugin/tools/missing/test", headers=_control_headers(), json={})
    assert missing_tool.status_code == 200
    assert missing_tool.json()["success"] is False
    assert missing_tool.json()["error_code"] == "PLUGIN_TOOL_NOT_CONFIGURED"

    webhook = client.post(
        "/v1/webhooks",
        headers=_control_headers(),
        json={"name": "factory-alerts", "events": ["factory.done"], "prompt": "Handle {event}: {payload}"},
    )
    assert webhook.status_code == 200
    webhook_id = webhook.json()["data"]["webhook"]["webhook_id"]
    trigger = client.post(
        f"/v1/webhooks/{webhook_id}/trigger",
        headers=_control_headers(),
        json={"event": "factory.done", "payload": {"run_id": "run_demo"}},
    )
    assert trigger.status_code == 200
    assert "factory.done" in trigger.json()["data"]["prompt"]
    deleted = client.delete(f"/v1/webhooks/{webhook_id}", headers=_control_headers())
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True

    session_id = store.create_session(user_id="u1")
    run_id = store.create_run(session_id, {"source": "test"})
    steer = client.post(f"/v1/runs/{run_id}/steer", json={"instruction": "stop after current tool"})
    assert steer.status_code == 200
    cancel = client.post(f"/v1/runs/{run_id}/cancel")
    assert cancel.status_code == 200
    events = [item["event"] for item in store.list_run_events(run_id)]
    assert "run.steer" in events
    assert "run.cancelled" in events


def test_runtime_emits_approval_and_plugin_hook_events(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    plugin_dir = tmp_path / "home" / "plugins" / "audit-hook"
    plugin_dir.mkdir(parents=True)
    plugin_dir.joinpath("plugin.json").write_text(
        json.dumps(
            {
                "name": "audit-hook",
                "enabled": True,
                "hooks": [{"name": "transform_tool_result", "prefix": "audited"}],
            }
        ),
        encoding="utf-8",
    )
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    policy = ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),)))
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=store,
        tool_registry=build_default_tool_registry(session_store=store, policy_engine=policy),
        max_iterations=2,
    )

    result = asyncio.run(
        runtime.run(
            [
                {
                    "role": "user",
                    "content": 'tool:agent_terminal {"command":"rm -rf ./danger", "cwd":"."}',
                }
            ]
        )
    )
    event_names = [item["event"] for item in store.list_run_events(result.run_id)]
    assert "approval.pending" in event_names
    assert "plugin.hook" in event_names
    tool_result = result.tool_calls[0]["result"]
    assert tool_result["error_code"] == "APPROVAL_REQUIRED"
    assert tool_result["data"]["plugin_prefix"] == "audited"


def test_shell_style_pre_tool_call_hook_can_block_tool(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AIASK_AGENT_HOME", str(home))
    plugin_dir = home / "plugins" / "guard-hook"
    plugin_dir.mkdir(parents=True)
    plugin_dir.joinpath("guard.py").write_text(
        "import json, sys\n"
        "payload=json.loads(sys.stdin.read())\n"
        "print(json.dumps({'decision':'block','reason':'blocked '+payload['arguments']['tool_name']}))\n",
        encoding="utf-8",
    )
    plugin_dir.joinpath("plugin.json").write_text(
        json.dumps(
            {
                "name": "guard-hook",
                "enabled": True,
                "hooks": [
                    {
                        "name": "pre_tool_call",
                        "tool": "agent_terminal",
                        "command": [sys.executable, "guard.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=store,
        tool_registry=build_default_tool_registry(
            session_store=store,
            policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
        ),
        max_iterations=2,
    )
    result = asyncio.run(runtime.run([{"role": "user", "content": 'tool:agent_terminal {"command":"pwd","cwd":"."}'}]))
    assert result.tool_calls[0]["result"]["error_code"] == "PLUGIN_HOOK_BLOCKED"
    events = [item["event"] for item in store.list_run_events(result.run_id)]
    assert "tool.blocked" in events
    assert "tool.started" not in events


def test_financial_system_readiness_gate_reports_required_blockers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.delenv("AIASK_AGENT_CONTROL_TOKEN", raising=False)
    monkeypatch.delenv("AIASK_LOCAL_CONTROL_TOKEN", raising=False)
    for key in (
        "AIASK_AGENT_MODEL_PROVIDER",
        "AIASK_AGENT_MODEL_PROVIDERS",
        "OPENAI_API_KEY",
        "OPENAI_API_KEYS",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    for key in quant.DATABASE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AKSHARE_MCP_SQLITE_PATH", "/dev/null/akshare_mcp.sqlite3")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/v1/financial-system/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "aiask.financial_system_readiness"
    assert payload["status"] == "blocked"
    assert payload["production_ready"] is False
    gates = {item["name"]: item for item in payload["required_gates"]}
    assert gates["ai_model"]["status"] == "degraded"
    assert gates["control_plane"]["status"] == "blocked"
    assert gates["database"]["status"] == "blocked"
    assert gates["semantic_search"]["status"] == "ready"
    assert gates["semantic_search"]["evidence"]["memory_probe_success"] is True
    assert gates["semantic_search"]["evidence"]["session_probe_success"] is True
    assert gates["hermes_code_parity"]["status"] == "ready"
    optional_gates = {item["name"]: item for item in payload["optional_gates"]}
    assert optional_gates["vector_provider"]["status"] == "degraded"
    assert optional_gates["vector_provider"]["evidence"]["required_env"] == ["AIASK_VECTOR_MEMORY_URL"]
    assert payload["parity"]["core_code_status"] == "present"
    assert payload["parity"]["code_status"] == "present"
    assert payload["parity"]["v014_delta"]["missing_count"] == 0
    assert payload["parity"]["v016_delta"]["missing_count"] == 0
    assert payload["parity"]["v016_delta"]["release_tag"] == "v2026.6.5"
    actions = {item["action_id"]: item for item in payload["next_actions"]}
    assert actions["set_control_token"]["priority"] == "critical"
    assert actions["configure_writable_database"]["target_page"] == "data"
    assert payload["live_smoke"]["script"] == "scripts/ops/live_readiness_smoke.py"
    assert payload["live_smoke"]["status"] == "blocked"
    assert payload["live_smoke"]["working_directory"] == "packages/agent"
    assert payload["live_smoke"]["self_test_command"].startswith("uv run python")
    assert "--self-test --pretty" in payload["live_smoke"]["self_test_command"]
    assert "--endpoint http://127.0.0.1:8767 --pretty" in payload["live_smoke"]["live_command"]
    assert "packages/agent" in payload["live_smoke"]["environment_note"]
    smoke_checks = {item["name"] for item in payload["live_smoke"]["checks"]}
    assert {
        "workbench_summary",
        "memory_status",
        "session_search",
        "memory_search",
        "factory_status",
        "market_temperature_cache",
        "market_temperature_forward_validation",
    } <= smoke_checks
    assert len(payload["live_smoke"]["checks"]) == 16
    smoke_check_details = {item["name"]: item for item in payload["live_smoke"]["checks"]}
    assert smoke_check_details["workbench_summary"]["path"] == "/v1/desktop/workbench/summary?session_limit=5&run_limit=5"
    assert "runtime_enabled" in smoke_check_details["factory_status"]["observes"]
    assert "daily_run_count" in smoke_check_details["factory_status"]["observes"]
    assert "warnings" in smoke_check_details["market_temperature_cache"]["observes"]
    assert "quality_status" in smoke_check_details["market_temperature_forward_validation"]["observes"]


def test_financial_system_readiness_can_reach_ready_with_core_runtime_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AKSHARE_MCP_SQLITE_PATH", str(tmp_path / "akshare_mcp.sqlite3"))

    async def fake_strategy_manager(action: str, params: object = None, **_: object) -> dict:
        if action == "factory_status":
            return {"success": True, "data": {"status": "ready"}, "error": None}
        if action == "factory_runs":
            return {"success": True, "data": {"runs": []}, "error": None}
        if action == "promotion_reviews":
            return {"success": True, "data": {"reviews": []}, "error": None}
        return {"success": True, "data": {"action": action, "params": params}, "error": None}

    import types

    fake_module = types.ModuleType("akshare_mcp.tools.managers.strategy_manager")
    fake_module.strategy_manager = fake_strategy_manager
    monkeypatch.setitem(sys.modules, "akshare_mcp.tools.managers.strategy_manager", fake_module)

    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/v1/financial-system/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["production_ready"] is True
    gates = {item["name"]: item for item in payload["required_gates"]}
    assert all(item["status"] == "ready" for item in gates.values())
    optional_gates = {item["name"]: item for item in payload["optional_gates"]}
    assert optional_gates["vector_provider"]["status"] == "degraded"
    assert payload["summary"]["required_blocked"] == 0
    actions = {item["action_id"]: item for item in payload["next_actions"]}
    assert "run_live_financial_workflow" in actions
    assert actions["run_live_financial_workflow"]["target_page"] == "financial-manager"
    assert payload["live_smoke"]["status"] == "ready"
    assert len(payload["live_smoke"]["checks"]) == 16
