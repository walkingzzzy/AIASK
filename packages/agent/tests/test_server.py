from __future__ import annotations

import asyncio
import json
import sys
import threading
import types
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from aiask_agent.intents import ActionIntentStore, IntentExecutor
from aiask_agent.model_client import MockModelClient, ModelResponse
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import _json_dumps, build_server
from aiask_agent.session_store import AgentSessionStore
from aiask_agent.tool_registry import AgentToolRegistry, aiask_envelope, build_default_tool_registry

HTTP_TEST_TIMEOUT_SECONDS = 30


class EmptyModelClient:
    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ModelResponse:
        return ModelResponse(content="", tool_calls=[], usage={})


def _request(method: str, url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json", **dict(headers or {})})
    with urlopen(req, timeout=HTTP_TEST_TIMEOUT_SECONDS) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _raw_request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json", **dict(headers or {})})
    with urlopen(req, timeout=HTTP_TEST_TIMEOUT_SECONDS) as response:
        return response.status, dict(response.headers), response.read()


def test_http_json_encoder_sanitizes_non_finite_numbers() -> None:
    body = _json_dumps({"value": float("nan"), "nested": [float("inf"), -float("inf"), 1.25]})
    text = body.decode("utf-8")

    assert "NaN" not in text
    assert "Infinity" not in text
    assert json.loads(text) == {"nested": [None, None, 1.25], "value": None}
    json.dumps(json.loads(text), allow_nan=False)


def test_http_health_chat_and_control_endpoints(tmp_path, monkeypatch) -> None:
    registry = AgentToolRegistry()

    async def analyze(arguments: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={"code": arguments.get("code"), "rating": "mock"},
            error=None,
            tool_name="agent_analyze_stock",
            source_chain=["test"],
        )

    registry.register(
        "agent_analyze_stock",
        description="mock stock analysis",
        parameters={"type": "object", "properties": {"code": {"type": "string"}}},
        handler=analyze,
    )
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=registry,
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=3,
    )
    intent_store = ActionIntentStore(tmp_path / "intents.sqlite3")
    executor = IntentExecutor(intent_store)
    server = build_server("127.0.0.1", 0, runtime=runtime, intent_executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, health = _request("GET", f"{base_url}/health")
        assert status == 200
        assert health["status"] == "ok"

        status, chat = _request(
            "POST",
            f"{base_url}/v1/chat/completions",
            {"messages": [{"role": "user", "content": 'tool:agent_analyze_stock {"code":"600519"}'}]},
        )
        assert status == 200
        assert chat["object"] == "chat.completion"
        assert chat["aiask"]["tool_calls"][0]["name"] == "agent_analyze_stock"
        assert chat["aiask"]["tool_calls"][0]["result"]["data"]["code"] == "600519"

        intent = intent_store.create(action="factory_run_once", params={"execution_mode": "dry_run"})
        try:
            _request("POST", f"{base_url}/intents/{intent['intent_id']}/deny", {"reason": "missing token"})
            raise AssertionError("deny without token should fail")
        except HTTPError as exc:
            assert exc.code == 503

        monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
        status, denied = _request(
            "POST",
            f"{base_url}/intents/{intent['intent_id']}/deny",
            {"reason": "test"},
            headers={"Authorization": "Bearer secret"},
        )
        assert status == 200
        assert denied["success"] is True

        fake_module = types.ModuleType("akshare_mcp.tools.managers.strategy_manager")

        async def fake_strategy_manager(action: str, kwargs: object = "{}", params: object = None) -> dict:
            return {"success": True, "data": {"action": action, "params": params}, "error": None}

        fake_module.strategy_manager = fake_strategy_manager
        monkeypatch.setitem(sys.modules, "akshare_mcp.tools.managers.strategy_manager", fake_module)
        intent2 = intent_store.create(action="factory_run_once", params={"execution_mode": "dry_run"})
        status, confirmed = _request(
            "POST",
            f"{base_url}/intents/{intent2['intent_id']}/confirm",
            {},
            headers={"X-AIASK-Agent-Control-Token": "secret"},
        )
        assert status == 200
        assert confirmed["success"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_tools_payload_includes_optional_contract_metadata(tmp_path) -> None:
    registry = AgentToolRegistry()

    async def quote(arguments: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={"code": arguments.get("code"), "price": 10.5},
            error=None,
            tool_name="agent_quote",
            source_chain=["test"],
        )

    registry.register(
        "agent_quote",
        description="mock quote",
        parameters={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        handler=quote,
        metadata={
            "category": "financial_read",
            "side_effect": "read_only",
            "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            "output_schema": {"type": "object", "properties": {"price": {"type": "number"}}},
            "freshness": {"expectation": "intraday_or_latest_quote_snapshot"},
            "source_policy": {"priority": ["tdx_local", "akshare"]},
            "examples": [{"arguments": {"code": "600519"}}],
            "contract_version": "ai_tool_contract_v1",
            "contract_source": "akshare_mcp.tool_catalog",
            "standard_model": "EquityQuote",
            "provider_choices": [{"rank": 1, "source": "tdx_local", "provider": "tdx_local"}],
            "provider_status": {"providers": [{"provider": "tdx_local", "available": True}]},
            "quality_gate": {"mode": "report_only", "status": "passed"},
            "reconciliation": {"enabled": True, "mode": "sampled_report_only"},
            "form_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        },
    )
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=registry,
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=3,
    )
    server = build_server("127.0.0.1", 0, runtime=runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, tools = _request("GET", f"{base_url}/v1/tools")
        assert status == 200
        item = next(row for row in tools["data"] if row["name"] == "agent_quote")
        assert item["parameters"]["required"] == ["code"]
        assert item["input_schema"]["required"] == ["code"]
        assert item["freshness"]["expectation"] == "intraday_or_latest_quote_snapshot"
        assert item["source_policy"]["priority"] == ["tdx_local", "akshare"]
        assert item["contract_version"] == "ai_tool_contract_v1"
        assert item["contract_source"] == "akshare_mcp.tool_catalog"
        assert item["standard_model"] == "EquityQuote"
        assert item["provider_choices"][0]["provider"] == "tdx_local"
        assert item["provider_status"]["providers"][0]["available"] is True
        assert item["quality_gate"]["mode"] == "report_only"
        assert item["reconciliation"]["enabled"] is True
        assert item["form_schema"]["required"] == ["code"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_runtime_explicit_tool_directive_runs_when_model_returns_empty(tmp_path) -> None:
    registry = AgentToolRegistry()

    async def analyze(arguments: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={"code": arguments.get("code"), "rating": "mock"},
            error=None,
            tool_name="agent_analyze_stock",
            source_chain=["test"],
        )

    registry.register(
        "agent_analyze_stock",
        description="mock stock analysis",
        parameters={"type": "object", "properties": {"code": {"type": "string"}}},
        handler=analyze,
        metadata={"category": "financial_read", "side_effect": "read_only"},
    )
    runtime = AgentRuntime(
        model_client=EmptyModelClient(),
        tool_registry=registry,
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=3,
    )

    result = asyncio.run(
        runtime.run([{"role": "user", "content": '请调用工具 agent_analyze_stock {"code":"600519"}'}])
    )

    assert result.content == "工具调用完成: agent_analyze_stock"
    assert result.tool_calls[0]["name"] == "agent_analyze_stock"
    assert result.tool_calls[0]["arguments"] == {"code": "600519"}
    assert {event["event"] for event in result.audit_events} >= {
        "tool.directive_detected",
        "tool.completed",
        "model.empty_response",
        "response.fallback",
    }


def test_desktop_http_surface_and_read_only_tool_api(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_CORS_ORIGINS", "http://localhost:1420")
    intent_store = ActionIntentStore(tmp_path / "intents.sqlite3")
    registry = build_default_tool_registry(intent_store)
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=registry,
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=3,
    )
    executor = IntentExecutor(intent_store)
    server = build_server("127.0.0.1", 0, runtime=runtime, intent_executor=executor)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, headers, _ = _raw_request(
            "OPTIONS",
            f"{base_url}/v1/tools",
            headers={
                "Origin": "http://localhost:1420",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert status == 204
        assert headers["Access-Control-Allow-Origin"] == "http://localhost:1420"
        assert "Authorization" in headers["Access-Control-Allow-Headers"]

        status, detailed = _request("GET", f"{base_url}/health/detailed")
        assert status == 200
        assert detailed["service"] == "aiask-agent"
        assert detailed["tools"]["count"] >= 1
        assert detailed["control"]["token_configured"] is False
        assert "secret" not in json.dumps(detailed).lower()

        status, tools = _request("GET", f"{base_url}/v1/tools")
        assert status == 200
        names = {item["name"] for item in tools["data"]}
        assert "agent_tool_catalog" in names
        assert "agent_analyze_stock" in names
        assert "agent_action_intent_create" in names

        status, catalog = _request("POST", f"{base_url}/v1/tools/agent_tool_catalog", {})
        assert status == 200
        assert catalog["success"] is True
        assert catalog["meta"]["side_effect"]["level"] == "read_only"

        try:
            _request(
                "POST",
                f"{base_url}/v1/tools/agent_action_intent_create",
                {"action": "factory_run_once"},
            )
            raise AssertionError("stateful tool should not be callable through read-only API")
        except HTTPError as exc:
            assert exc.code == 403

        intent = intent_store.create(action="factory_run_once", params={"execution_mode": "dry_run"})
        status, fetched = _request("GET", f"{base_url}/intents/{intent['intent_id']}")
        assert status == 200
        assert fetched["success"] is True
        assert fetched["data"]["intent"]["status"] == "awaiting_confirmation"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_native_hermes_full_mode_is_control_gated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=AgentToolRegistry(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )
    server = build_server("127.0.0.1", 0, runtime=runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, status_body = _request("GET", f"{base_url}/v1/hermes/status")
        assert status == 200
        assert status_body["implementation"] == "aiask_native"
        assert status_body["embedded_vendor_runtime"] is False

        try:
            _request("GET", f"{base_url}/v1/hermes/tools")
            raise AssertionError("hermes full tools require control token")
        except HTTPError as exc:
            assert exc.code == 401

        status, tools = _request("GET", f"{base_url}/v1/hermes/tools", headers={"Authorization": "Bearer secret"})
        assert status == 200
        names = {item["name"] for item in tools["data"]}
        assert {"agent_web_search", "agent_skill_list", "agent_terminal", "agent_message_send"} <= names
        assert not any(name in names for name in {"web_search", "terminal", "delegate_task"})

        try:
            _request(
                "POST",
                f"{base_url}/v1/responses",
                {"mode": "hermes_full", "input": 'tool:agent_clarify {"question":"Need universe?"}'},
            )
            raise AssertionError("hermes_full mode should require control token")
        except HTTPError as exc:
            assert exc.code == 401

        status, response = _request(
            "POST",
            f"{base_url}/v1/responses",
            {"mode": "hermes_full", "input": 'tool:agent_clarify {"question":"Need universe?"}'},
            headers={"Authorization": "Bearer secret"},
        )
        assert status == 200
        assert response["metadata"]["mode"] == "hermes_full"
        assert response["metadata"]["tool_calls"][0]["name"] == "agent_clarify"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_legacy_http_mcp_inventory_honors_all_query_and_full_gate(tmp_path, monkeypatch) -> None:
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
                        "tools": [{"name": "quote", "description": "quote tool"}],
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
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=AgentToolRegistry(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )
    server = build_server("127.0.0.1", 0, runtime=runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, financial_servers = _request("GET", f"{base_url}/v1/mcp/servers")
        assert status == 200
        assert {item["name"] for item in financial_servers["data"]} == {"finance-demo"}

        status, all_servers = _request("GET", f"{base_url}/v1/mcp/servers?all=true")
        assert status == 200
        assert {item["name"] for item in all_servers["data"]} == {"finance-demo", "general-demo"}

        try:
            _request("GET", f"{base_url}/v1/mcp/tools?all=true")
            raise AssertionError("MCP tools inventory should require full-mode control token")
        except HTTPError as exc:
            assert exc.code == 401

        headers = {"Authorization": "Bearer secret"}
        status, financial_tools = _request("GET", f"{base_url}/v1/mcp/tools", headers=headers)
        assert status == 200
        assert {item["name"] for item in financial_tools["data"]} == {"quote"}

        status, all_tools = _request("GET", f"{base_url}/v1/mcp/tools?all=true", headers=headers)
        assert status == 200
        assert {item["name"] for item in all_tools["data"]} == {"quote", "browser"}

        status, resources = _request("GET", f"{base_url}/v1/mcp/resources?all=true", headers=headers)
        assert status == 200
        assert resources["data"][0]["uri"] == "aiask://quotes"

        status, prompts = _request("GET", f"{base_url}/v1/mcp/prompts?all=true", headers=headers)
        assert status == 200
        assert prompts["data"][0]["name"] == "risk-review"

        status, oauth = _request("GET", f"{base_url}/v1/mcp/oauth_status?all=true", headers=headers)
        assert status == 200
        assert {item["server"] for item in oauth["data"]} == {"finance-demo", "general-demo"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
