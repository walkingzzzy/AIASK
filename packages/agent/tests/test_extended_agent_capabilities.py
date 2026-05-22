from __future__ import annotations

import asyncio
import base64
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.request import Request, urlopen

import pytest

from aiask_agent.context import ContextManager
from aiask_agent.mcp_client import MCPAggregator, MCPTokenStore, MCPOAuthRequired
from aiask_agent.model_client import ModelResponse, MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.session_store import AgentSessionStore
from aiask_agent.tool_registry import AgentToolRegistry, build_default_tool_registry
from aiask_agent.tools.policy import ToolPolicy, ToolPolicyEngine


def _request(method: str, url: str, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json", **dict(headers or {})})
    with urlopen(req, timeout=5) as response:
        body = response.read().decode("utf-8")
        return response.status, dict(response.headers), body


class FlakyModel:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]], model: str) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("temporary timeout")
        return ModelResponse(content="ok after retry", usage={"total_tokens": 1})


def test_toolsets_gate_general_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AIASK_AGENT_ENABLE_GENERAL_TOOLS", raising=False)
    monkeypatch.setenv("AIASK_AGENT_WORKSPACE_ROOTS", str(tmp_path))
    finance = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "finance.sqlite3"),
        policy_engine=ToolPolicyEngine(ToolPolicy("finance_safe", False, (str(tmp_path),))),
    )
    assert "agent_terminal" not in finance.names()
    assert "agent_file_read" not in finance.names()

    general = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "general.sqlite3"),
        policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
    )
    names = set(general.names())
    assert {
        "agent_terminal",
        "agent_file_read",
        "agent_execute_python",
        "agent_browser_snapshot",
        "agent_web_search",
        "agent_web_extract",
        "agent_skill_list",
        "agent_plugin_list",
        "agent_clarify",
        "agent_todo_set",
        "agent_vision_analyze",
        "agent_image_generate",
        "agent_text_to_speech",
        "agent_message_send",
        "agent_model_manage",
        "agent_memory_manage",
        "agent_acp_manage",
        "agent_security_scan",
        "agent_skill_pack_manage",
    } <= names


def test_general_file_terminal_and_code_tools_are_workspace_scoped(tmp_path) -> None:
    registry = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
    )
    written = asyncio.run(
        registry.call_tool(
            "agent_file_write",
            {"path": "notes/demo.txt", "content": "alpha beta", "create_parent_dirs": True},
        )
    )
    assert written["success"] is True
    read = asyncio.run(registry.call_tool("agent_file_read", {"path": "notes/demo.txt"}))
    assert read["data"]["content"] == "alpha beta"
    terminal = asyncio.run(registry.call_tool("agent_terminal", {"command": "pwd", "cwd": "."}))
    assert terminal["success"] is True
    assert terminal["data"]["returncode"] == 0
    code = asyncio.run(registry.call_tool("agent_execute_python", {"code": "print(2 + 3)"}))
    assert code["success"] is True
    assert "5" in code["data"]["stdout"]
    denied = asyncio.run(registry.call_tool("agent_file_read", {"path": str(Path.home() / ".ssh" / "config")}))
    assert denied["success"] is False


def test_terminal_background_process_lifecycle(tmp_path) -> None:
    registry = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
    )

    async def scenario() -> None:
        started = await registry.call_tool(
            "agent_terminal",
            {
                "command": "python -c 'import time; time.sleep(30)'",
                "cwd": ".",
                "background": True,
                "session_id": "s1",
            },
        )
        assert started["success"] is True
        process_id = started["data"]["process_id"]
        listed = await registry.call_tool("agent_process", {"action": "list", "session_id": "s1"})
        assert any(item["process_id"] == process_id and item["status"] in {"running", "detached_running"} for item in listed["data"]["items"])
        killed = await registry.call_tool("agent_process", {"action": "kill", "process_id": process_id})
        assert killed["success"] is True
        assert killed["data"]["killed"] is True

    asyncio.run(scenario())


def test_background_process_recovers_as_detached_after_registry_rebuild(tmp_path) -> None:
    store = AgentSessionStore(tmp_path / "state.sqlite3")

    async def scenario() -> None:
        registry = build_default_tool_registry(
            session_store=store,
            policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
        )
        started = await registry.call_tool(
            "agent_terminal",
            {
                "command": "python -c 'import time; print(\"ready\", flush=True); time.sleep(30)'",
                "cwd": ".",
                "background": True,
                "session_id": "recover",
            },
        )
        assert started["success"] is True
        process_id = started["data"]["process_id"]
        await asyncio.sleep(0.2)

        rebuilt = build_default_tool_registry(
            session_store=store,
            policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
        )
        listed = await rebuilt.call_tool("agent_process", {"action": "list", "session_id": "recover"})
        recovered = next(item for item in listed["data"]["items"] if item["process_id"] == process_id)
        assert recovered["status"] in {"running", "detached_running"}
        assert recovered["metadata"]["recovered"] is True

        read = await rebuilt.call_tool("agent_process", {"action": "read", "process_id": process_id, "max_output_bytes": 1000})
        assert read["success"] is True
        assert "ready" in read["data"]["stdout"]

        killed = await rebuilt.call_tool("agent_process", {"action": "kill", "process_id": process_id})
        assert killed["success"] is True
        assert killed["data"]["killed"] is True
        await asyncio.sleep(0.1)

    asyncio.run(scenario())


def test_execute_python_can_call_enabled_aiask_tools_via_rpc(tmp_path) -> None:
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=build_default_tool_registry(
            session_store=store,
            policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
        ),
        session_store=store,
        max_iterations=1,
    )
    result = asyncio.run(
        runtime.tool_registry.call_tool(
            "agent_execute_python",
            {
                "code": (
                    "from aiask_tools import agent_file_write, agent_file_read\n"
                    "agent_file_write(path='rpc-note.txt', content='native rpc ok')\n"
                    "result = agent_file_read(path='rpc-note.txt')\n"
                    "print(result['data']['content'])\n"
                ),
                "cwd": ".",
            },
        )
    )
    assert result["success"] is True
    assert "native rpc ok" in result["data"]["stdout"]
    assert [item["tool"] for item in result["data"]["tool_calls"]] == ["agent_file_write", "agent_file_read"]


def test_runtime_events_context_compaction_planner_and_retry(tmp_path) -> None:
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(
        model_client=FlakyModel(),
        tool_registry=AgentToolRegistry(),
        session_store=store,
        context_manager=ContextManager(max_tokens=30, head_messages=1, tail_messages=4),
        max_iterations=1,
        retry_attempts=2,
    )
    long_message = "股票、策略、治理、风险、估值、因子 " + ("very long context " * 80)
    result = asyncio.run(runtime.run([{"role": "user", "content": long_message}], user_id="u1", stream=True))
    event_names = [item["event"] for item in store.list_run_events(result.run_id)]
    assert result.content == "ok after retry"
    assert result.context_summary_id
    assert result.planner_steps
    assert "context.compacted" in event_names
    assert "planner.plan_created" in event_names
    assert "model.retry" in event_names
    assert "run.completed" in event_names


def test_runtime_subagent_and_job_execution(tmp_path) -> None:
    policy = ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),)))
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    registry = build_default_tool_registry(session_store=store, policy_engine=policy)
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=registry,
        session_store=store,
        max_iterations=2,
    )
    delegated = asyncio.run(
        runtime.tool_registry.call_tool("agent_delegate_task", {"task": "hello child", "toolset": "finance_safe"})
    )
    assert delegated["success"] is True
    assert delegated["data"]["subrun"]["run_id"].startswith("run_")

    job = runtime.job_store.create(name="daily review", prompt="job prompt", interval_seconds=3600)
    ran = asyncio.run(runtime.tool_registry.call_tool("agent_job_run", {"job_id": job["job_id"]}))
    assert ran["success"] is True
    assert ran["data"]["job"]["last_run_at"]
    cron_job = runtime.job_store.create(name="cron review", prompt="cron prompt", schedule="*/5 * * * *")
    assert cron_job["next_run_at"]


def test_native_hermes_class_tools_are_aiask_owned(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    policy = ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),)))
    registry = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=policy,
    )

    clarified = asyncio.run(
        registry.call_tool(
            "agent_clarify",
            {"question": "Which universe?", "options": ["A-shares", "HK"]},
        )
    )
    assert clarified["success"] is True
    assert clarified["data"]["requires_user_input"] is True

    saved_skill = asyncio.run(
        registry.call_tool(
            "agent_skill_save",
            {"name": "risk-review", "description": "Risk review workflow", "content": "# Risk Review\nCheck drawdown."},
        )
    )
    assert saved_skill["success"] is True
    listed_skills = asyncio.run(registry.call_tool("agent_skill_list", {}))
    assert listed_skills["data"]["skills"][0]["name"] == "risk-review"

    plugin = asyncio.run(
        registry.call_tool(
            "agent_plugin_set_enabled",
            {"name": "audit-export", "enabled": True, "description": "Audit export plugin"},
        )
    )
    assert plugin["success"] is True
    plugins = asyncio.run(registry.call_tool("agent_plugin_list", {}))
    assert plugins["data"]["plugins"][0]["enabled"] is True

    todos = asyncio.run(
        registry.call_tool(
            "agent_todo_set",
            {"session_id": "s1", "items": [{"id": "1", "content": "collect evidence", "status": "pending"}]},
        )
    )
    assert todos["success"] is True
    listed_todos = asyncio.run(registry.call_tool("agent_todo_list", {"session_id": "s1"}))
    assert listed_todos["data"]["items"][0]["content"] == "collect evidence"


def test_search_and_mcp_financial_allowlist(tmp_path) -> None:
    state = AgentSessionStore(tmp_path / "state.sqlite3")
    sid = state.create_session(user_id="u1")
    state.append_message(sid, {"role": "user", "content": "maotai margin quality"})
    assert state.search(query="maotai", user_id="u1")

    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "finance-demo",
                        "domain": "financial",
                        "command": "python",
                        "tools": [
                            {"name": "quote", "description": "quote tool", "parameters": {"type": "object"}},
                            {"name": "terminal", "description": "shell tool"},
                            {"name": "available_tools", "description": "legacy catalog"},
                            {"name": "get_tool_contract", "description": "legacy contract lookup"},
                            {"name": "strategy_manager", "description": "direct strategy manager"},
                        ],
                    },
                    {
                        "name": "general-demo",
                        "domain": "general",
                        "command": "python",
                        "tools": [{"name": "terminal", "description": "terminal"}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    aggregator = MCPAggregator(config_path)
    tools = aggregator.financial_tools()
    assert [item["wrapped_name"] for item in tools] == ["agent_mcp_finance_demo_quote"]
    assert {item["name"] for item in tools}.isdisjoint({"available_tools", "get_tool_contract", "strategy_manager"})
    assert aggregator.servers_summary()[0]["resources_enabled"] is False


def test_mcp_remote_transports_and_oauth_token_store(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "sse-fin",
                        "domain": "financial",
                        "transport": "sse",
                        "url": "https://mcp.example.test/sse",
                        "auth": "oauth",
                        "oauth": {"authorization_url": "https://auth.example.test/authorize", "client_id": "client-1", "scope": "quotes"},
                        "tools": [{"name": "quote", "description": "quote", "parameters": {"type": "object"}}],
                    },
                    {
                        "name": "http-fin",
                        "domain": "financial",
                        "transport": "streamable_http",
                        "url": "https://mcp.example.test/mcp",
                        "tools": [{"name": "risk", "description": "risk", "parameters": {"type": "object"}}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIASK_AGENT_MCP_TOKEN_DIR", str(tmp_path / "tokens"))

    calls: list[dict[str, Any]] = []

    class FakeSession:
        def __init__(self, *_: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def initialize(self) -> None:
            return None

        async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
            return {"called": name, "arguments": arguments or {}}

        async def list_tools(self) -> SimpleNamespace:
            return SimpleNamespace(tools=[{"name": "risk"}])

        async def list_resources(self) -> SimpleNamespace:
            return SimpleNamespace(resources=[{"uri": "aiask://risk"}])

        async def read_resource(self, uri: str) -> dict[str, Any]:
            return {"uri": uri, "text": "resource text"}

        async def list_prompts(self) -> SimpleNamespace:
            return SimpleNamespace(prompts=[{"name": "review"}])

        async def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> dict[str, Any]:
            return {"name": name, "arguments": arguments or {}, "messages": []}

    @asynccontextmanager
    async def fake_sse_client(url: str, **kwargs: Any):
        calls.append({"transport": "sse", "url": url, "auth": kwargs.get("auth")})
        yield object(), object()

    @asynccontextmanager
    async def fake_streamable_client(url: str, **kwargs: Any):
        calls.append({"transport": "streamable_http", "url": url, "auth": kwargs.get("auth")})
        yield object(), object(), lambda: "session-1"

    import mcp
    import mcp.client.sse
    import mcp.client.streamable_http

    monkeypatch.setattr(mcp, "ClientSession", FakeSession)
    monkeypatch.setattr(mcp.client.sse, "sse_client", fake_sse_client)
    monkeypatch.setattr(mcp.client.streamable_http, "streamablehttp_client", fake_streamable_client)

    aggregator = MCPAggregator(config_path)
    start = aggregator.oauth_start("sse-fin")
    assert start["status"] == "oauth_required"
    assert "client_id=client-1" in start["authorization_url"]
    assert MCPTokenStore("sse-fin").summary(configured=True)["token_available"] is False

    with pytest.raises(MCPOAuthRequired):
        asyncio.run(aggregator.call("agent_mcp_sse_fin_quote", {"symbol": "600519"}))

    stored = aggregator.oauth_callback("sse-fin", {"access_token": "token-1", "scope": "quotes"})
    assert stored["token_available"] is True
    called = asyncio.run(aggregator.call("agent_mcp_sse_fin_quote", {"symbol": "600519"}))
    assert called["called"] == "quote"
    assert calls[-1]["transport"] == "sse"
    assert calls[-1]["auth"] is not None

    discovered = asyncio.run(aggregator.discover("http-fin"))
    assert discovered["transport"] == "streamable_http"
    assert discovered["resources"][0]["uri"] == "aiask://risk"
    resource = asyncio.run(aggregator.read_resource("http-fin", "aiask://risk"))
    assert resource["result"]["text"] == "resource text"
    prompt = asyncio.run(aggregator.get_prompt("http-fin", "review", {"ticker": "600519"}))
    assert prompt["result"]["arguments"] == {"ticker": "600519"}


def test_provider_backed_vision_tts_and_stt_are_real_calls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AIASK_AGENT_VISION_MODEL", "vision-model")
    calls: list[dict[str, Any]] = []

    class FakeResponses:
        async def create(self, **kwargs: Any) -> SimpleNamespace:
            calls.append({"api": "responses.create", **kwargs})
            return SimpleNamespace(output_text="visible chart evidence")

    class FakeSpeech:
        async def create(self, **kwargs: Any) -> SimpleNamespace:
            calls.append({"api": "audio.speech.create", **kwargs})
            return SimpleNamespace(content=b"audio-bytes")

    class FakeTranscriptions:
        async def create(self, **kwargs: Any) -> SimpleNamespace:
            calls.append({"api": "audio.transcriptions.create", **{k: v for k, v in kwargs.items() if k != "file"}})
            return SimpleNamespace(text="transcribed words")

    class FakeAudio:
        def __init__(self) -> None:
            self.speech = FakeSpeech()
            self.transcriptions = FakeTranscriptions()

    class FakeOpenAI:
        def __init__(self, **_: Any) -> None:
            self.responses = FakeResponses()
            self.audio = FakeAudio()

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeOpenAI)
    registry = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
    )
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="))
    audio_path = tmp_path / "speech.wav"
    audio_path.write_bytes(b"RIFF0000WAVEfmt ")

    async def scenario() -> None:
        vision = await registry.call_tool("agent_vision_analyze", {"image_path": str(image_path), "prompt": "read chart"})
        assert vision["success"] is True
        assert vision["data"]["analysis"] == "visible chart evidence"
        vision_input = calls[-1]["input"][0]["content"]
        assert vision_input[1]["image_url"].startswith("data:image/png;base64,")

        tts = await registry.call_tool(
            "agent_text_to_speech",
            {"text": "hello", "voice": "alloy", "format": "mp3", "speed": 1.2},
        )
        assert tts["success"] is True
        assert Path(tts["data"]["path"]).read_bytes() == b"audio-bytes"
        assert calls[-1]["api"] == "audio.speech.create"
        assert calls[-1]["speed"] == 1.2

        stt = await registry.call_tool(
            "agent_transcribe_audio",
            {"audio_path": str(audio_path), "language": "en", "prompt": "finance call"},
        )
        assert stt["success"] is True
        assert stt["data"]["text"] == "transcribed words"
        assert calls[-1]["api"] == "audio.transcriptions.create"
        assert calls[-1]["language"] == "en"

    asyncio.run(scenario())


def test_provider_tools_report_unconfigured_without_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AIASK_AGENT_VISION_MODEL", raising=False)
    registry = build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),))),
    )
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"not really an image")

    async def scenario() -> None:
        vision = await registry.call_tool("agent_vision_analyze", {"image_path": str(image_path)})
        assert vision["success"] is False
        assert vision["data"]["configured"] is False
        tts = await registry.call_tool("agent_text_to_speech", {"text": "hello"})
        assert tts["success"] is False
        assert tts["data"]["configured"] is False
        stt = await registry.call_tool("agent_transcribe_audio", {"audio_path": str(tmp_path / "missing.wav")})
        assert stt["success"] is False
        assert stt["data"]["configured"] is False

    asyncio.run(scenario())


def test_http_sse_run_events_toolsets_and_jobs(tmp_path) -> None:
    from aiask_agent.server import build_server

    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        tool_registry=AgentToolRegistry(),
        session_store=store,
        max_iterations=1,
    )
    server = build_server("127.0.0.1", 0, runtime=runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, _, body = _request("GET", f"{base_url}/v1/toolsets")
        assert status == 200
        assert json.loads(body)["active"] == "finance_safe"

        status, headers, body = _request(
            "POST",
            f"{base_url}/v1/chat/completions",
            {"stream": True, "messages": [{"role": "user", "content": "hello"}]},
        )
        assert status == 200
        assert headers["Content-Type"].startswith("text/event-stream")
        assert "[DONE]" in body

        first_json_line = next(line for line in body.splitlines() if line.startswith("data: {"))
        response_id = json.loads(first_json_line.removeprefix("data: "))["id"]
        run_id = store.get_response(response_id)["run_id"]
        status, headers, events_body = _request("GET", f"{base_url}/v1/runs/{run_id}/events")
        assert status == 200
        assert headers["Content-Type"].startswith("text/event-stream")
        assert "run.completed" in events_body

        status, _, job_body = _request(
            "POST",
            f"{base_url}/v1/jobs",
            {"name": "smoke", "prompt": "hello job", "interval_seconds": 3600},
        )
        assert status == 201
        job_id = json.loads(job_body)["job_id"]
        status, _, list_body = _request("GET", f"{base_url}/v1/jobs")
        assert status == 200
        assert job_id in list_body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
