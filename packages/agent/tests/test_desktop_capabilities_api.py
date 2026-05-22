from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiask_agent.model_client import MockModelClient
from aiask_agent.adapters.strategy_factory import _unavailable_factory
from aiask_agent.mcp_client import MCPAggregator
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore


def _runtime(tmp_path) -> AgentRuntime:
    return AgentRuntime(model_client=MockModelClient(), session_store=AgentSessionStore(tmp_path / "state.sqlite3"), max_iterations=2)


def test_strategy_factory_database_error_is_classified(monkeypatch) -> None:
    monkeypatch.setenv("AKSHARE_MCP_SQLITE_PATH", "/tmp/aiask-test.sqlite3")
    payload = _unavailable_factory(RuntimeError("unable to open database file"))
    assert payload["error_code"] == "STRATEGY_FACTORY_DATABASE_UNAVAILABLE"
    assert payload["data"]["database_backend"] == "sqlite"
    assert payload["data"]["database_configured"] is True


def test_strategy_factory_db_env_and_recovery_are_classified(monkeypatch) -> None:
    monkeypatch.setenv("AKSHARE_MCP_SQLITE_PATH", "/tmp/aiask-test.sqlite3")

    payload = _unavailable_factory(RuntimeError("database is locked"))

    assert payload["error_code"] == "STRATEGY_FACTORY_DATABASE_RECOVERY"
    assert payload["data"]["database_configured"] is True
    assert "AKSHARE_MCP_SQLITE_PATH" in payload["data"]["database_config_sources"]


def test_desktop_capabilities_returns_public_subset_without_control_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.delenv("MCP_PORT", raising=False)
    runtime = _runtime(tmp_path)
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/v1/desktop/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "aiask.desktop_capabilities"
    assert payload["summary"]["control"]["authorized"] is False
    assert payload["summary"]["source"] == "gated"
    assert payload["summary"]["control"]["full_mode_enabled"] is True
    assert payload["summary"]["control"]["control_token_configured"] is True
    assert payload["summary"]["control"]["control_authorized"] is False
    assert payload["hermes"]["parity"]["baseline"] == "Hermes v0.14.0 full runtime capability reference"
    assert payload["hermes"]["parity"]["core_missing_hermes_tools"] == []
    assert payload["hermes"]["parity"]["v014_delta"]["missing_count"] == 0
    assert payload["mcp"]["gated"] is True
    assert payload["mcp"]["registration_status"] == "not_registered"
    assert payload["mcp"]["discovery_status"] == "not_registered"
    assert payload["skills"]["gated"] is True
    assert payload["providers"]["secrets_redacted"] is True
    assert payload["memory"]["default_provider"] == "sqlite"
    assert payload["security"]["status"] == "implemented"
    assert payload["skill_packs"]["vendor_text_copied"] is False
    assert payload["strategy_factory"]["status"]["success"] is False
    assert payload["ai"]["secrets_redacted"] is True


def test_desktop_capabilities_reports_mcp_port_without_aggregator_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.setenv("MCP_PORT", "3100")
    monkeypatch.delenv("AIASK_AGENT_MCP_CONFIG", raising=False)
    runtime = _runtime(tmp_path)
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/v1/desktop/capabilities", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["source"] == "live_backend"
    assert payload["mcp"]["registration_status"] == "MCP_SERVICE_RUNNING_BUT_NOT_REGISTERED"
    assert payload["mcp"]["discovery_status"] == "MCP_SERVICE_RUNNING_BUT_NOT_REGISTERED"
    assert payload["mcp"]["error_code"] == "MCP_SERVICE_RUNNING_BUT_NOT_REGISTERED"
    assert payload["mcp"]["detected_service_port"] == "3100"
    assert payload["mcp"]["suggested_registration_url"] == "http://127.0.0.1:3100/mcp"
    assert payload["mcp"]["auth_env_vars"] == []
    assert payload["mcp"]["missing_auth_env_vars"] == []
    assert "mcp" in payload["hermes"]["readiness"]
    assert payload["hermes"]["readiness"]["mcp"]["registration_status"] == "MCP_SERVICE_RUNNING_BUT_NOT_REGISTERED"


def test_desktop_capabilities_aggregates_controlled_surfaces(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.setenv("MCP_PORT", "3100")
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
                        "tools": [{"name": "quote", "description": "quote tool"}],
                        "resources": [{"uri": "aiask://quotes"}],
                        "prompts": [{"name": "risk-review"}],
                        "auth": "oauth",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIASK_AGENT_MCP_CONFIG", str(mcp_config))
    runtime = _runtime(tmp_path)
    client = TestClient(create_app(runtime=runtime))
    create_skill = client.post(
        "/v1/skills",
        headers={"Authorization": "Bearer secret"},
        json={"name": "risk-review", "description": "Risk review", "content": "# Risk Review\n"},
    )
    assert create_skill.status_code == 200

    response = client.get("/v1/desktop/capabilities", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["control"]["authorized"] is True
    assert payload["summary"]["source"] == "live_backend"
    assert payload["mcp"]["gated"] is False
    assert payload["mcp"]["registration_status"] == "registered"
    assert payload["mcp"]["discovery_status"] == "discovered"
    assert payload["mcp"]["config_path"] == str(mcp_config)
    assert payload["mcp"]["auth_configured"] is True
    assert payload["mcp"]["tools"][0]["name"] == "quote"
    assert payload["mcp"]["resources"][0]["uri"] == "aiask://quotes"
    assert any(item["name"] == "risk-review" for item in payload["skills"]["skills"])
    assert payload["hermes"]["providers"]["object"] == "aiask.model_provider_status"
    assert payload["hermes"]["acp"]["implemented"] is True
    assert payload["hermes"]["skill_packs"]["source"] == "aiask_native_rewrite"
    assert payload["hermes"]["status"]["full_mode_active"] is True
    assert "ai_status" in payload["raw_refs"]


def test_mcp_register_local_writes_non_secret_aggregator_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.setenv("MCP_PORT", "3100")
    runtime = _runtime(tmp_path)
    client = TestClient(create_app(runtime=runtime))

    response = client.post("/v1/mcp/register-local", headers={"Authorization": "Bearer secret"}, json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    server = payload["data"]["server"]
    assert server["name"] == "akshare-local"
    assert server["transport"] == "streamable_http"
    assert server["url"] == "http://127.0.0.1:3100/mcp"
    assert server["headers_from_env"]["Authorization"] == "AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"
    assert "token" not in json.dumps(server).lower()

    capabilities = client.get("/v1/desktop/capabilities", headers={"Authorization": "Bearer secret"}).json()
    assert capabilities["mcp"]["registration_status"] == "registered"
    assert capabilities["mcp"]["discovery_status"] == "auth_missing"
    assert capabilities["mcp"]["servers"][0]["name"] == "akshare-local"
    assert capabilities["mcp"]["auth_configured"] is False
    assert capabilities["mcp"]["auth_env_vars"] == ["AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"]
    assert capabilities["mcp"]["missing_auth_env_vars"] == ["AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"]


def test_mcp_env_auth_headers_are_loaded_from_environment(tmp_path, monkeypatch) -> None:
    mcp_config = tmp_path / "mcp_servers.json"
    mcp_config.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "finance-demo",
                        "domain": "financial",
                        "transport": "streamable_http",
                        "url": "http://127.0.0.1:3100/mcp",
                        "headers_from_env": {"Authorization": "AIASK_TEST_MCP_AUTH"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIASK_TEST_MCP_AUTH", "Bearer secret-value")

    mcp = MCPAggregator(config_path=mcp_config)
    server = mcp.servers_summary(include_all=True)[0]

    assert server["auth_configured"] is True
    assert server["auth_env_vars"] == ["AIASK_TEST_MCP_AUTH"]
    assert server["missing_auth_env_vars"] == []
    assert MCPAggregator._headers({"headers_from_env": {"Authorization": "AIASK_TEST_MCP_AUTH"}}) == {
        "Authorization": "Bearer secret-value"
    }
