from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from aiask_agent import gateway as gateway_module
from aiask_agent import platform_apis
from aiask_agent.capabilities import parity_summary
from aiask_agent.gateway import ADAPTERS, GatewayConfigStore
from aiask_agent.model_client import MockModelClient
from aiask_agent.platform_apis import DiscordServerClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore
from aiask_agent.tool_registry import build_default_tool_registry
from aiask_agent.tools.policy import ToolPolicy, ToolPolicyEngine
from aiask_agent.tui import TUIController


def _full_policy(tmp_path) -> ToolPolicyEngine:
    return ToolPolicyEngine(ToolPolicy("general_full", True, (str(tmp_path),)))


def _full_registry(tmp_path):
    return build_default_tool_registry(
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        policy_engine=_full_policy(tmp_path),
    )


def test_modal_wrapper_terminal_backend_executes_real_command(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_MODAL_TERMINAL_COMMAND", f"{sys.executable} -c \"print('modal-wrapper-ok')\"")
    registry = _full_registry(tmp_path)
    result = asyncio.run(registry.call_tool("agent_terminal", {"backend": "modal", "command": "ignored"}))
    assert result["success"] is True
    assert "modal-wrapper-ok" in result["data"]["stdout"]
    assert result["data"]["backend"] == "modal"


def test_plugin_python_module_and_subprocess_runners_execute(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AIASK_AGENT_HOME", str(home))
    plugin_dir = home / "plugins" / "demo"
    plugin_dir.mkdir(parents=True)
    plugin_dir.joinpath("demo_mod.py").write_text(
        "def run(payload):\n"
        "    return {'seen_tool': payload['tool'], 'value': payload['arguments'].get('value')}\n",
        encoding="utf-8",
    )
    plugin_dir.joinpath("runner.py").write_text(
        "import json, sys\n"
        "payload=json.loads(sys.stdin.read())\n"
        "print(json.dumps({'subprocess_tool': payload['tool'], 'value': payload['arguments'].get('value')}))\n",
        encoding="utf-8",
    )
    plugin_dir.joinpath("plugin.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "enabled": True,
                "tools": [
                    {"name": "py", "runner": {"type": "python_module", "module": "demo_mod", "function": "run"}},
                    {"name": "sub", "runner": {"type": "subprocess", "command": [sys.executable, "runner.py"]}},
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = _full_registry(tmp_path)
    py_result = asyncio.run(registry.call_tool("agent_plugin_demo_py", {"value": 7}))
    sub_result = asyncio.run(registry.call_tool("agent_plugin_demo_sub", {"value": 9}))
    assert py_result["success"] is True
    assert py_result["data"]["result"] == {"seen_tool": "py", "value": 7}
    assert sub_result["success"] is True
    assert sub_result["data"]["result"] == {"subprocess_tool": "sub", "value": 9}


def test_gateway_webhook_adapter_delivers_and_records(tmp_path, monkeypatch) -> None:
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            received.append(json.loads(self.rfile.read(length).decode("utf-8")))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *_args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("AIASK_GATEWAY_WEBHOOK_URL", f"http://127.0.0.1:{server.server_port}/hook")
        GatewayConfigStore().save_platform("webhook", {"enabled": True})
        registry = _full_registry(tmp_path)
        result = asyncio.run(registry.call_tool("agent_gateway_send_message", {"platform": "webhook", "target": "default", "message": "hello"}))
        assert result["success"] is True
        assert result["data"]["message"]["status"] == "delivered"
        assert received[0]["text"] == "hello"
    finally:
        server.shutdown()


def test_rl_fake_atropos_launch_records_logs(tmp_path, monkeypatch) -> None:
    env_dir = tmp_path / "envs"
    env_dir.mkdir()
    env_dir.joinpath("demo_env.py").write_text("class DemoEnv(BaseEnv):\n    name = 'demo'\n", encoding="utf-8")
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_RL_ENV_PATHS", str(env_dir))
    monkeypatch.setenv("TINKER_API_KEY", "test")
    monkeypatch.setenv("WANDB_API_KEY", "test")
    monkeypatch.setenv("AIASK_ATROPOS_LAUNCH_COMMAND", f"{sys.executable} -c \"import os; print('train '+os.environ['AIASK_RL_ENVIRONMENT'])\"")
    registry = _full_registry(tmp_path)
    started = asyncio.run(registry.call_tool("agent_rl_start_training", {"environment": "demo"}))
    assert started["success"] is True
    run_id = started["data"]["run_id"]
    logs = {}
    for _ in range(20):
        logs = asyncio.run(registry.call_tool("agent_rl_get_results", {"run_id": run_id}))
        if "train demo" in str(logs.get("data", {}).get("log_tail") or ""):
            break
        time.sleep(0.05)
    assert logs["success"] is True
    assert "train demo" in logs["data"]["log_tail"]


def test_hermes_readiness_endpoint_reports_native_surfaces(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )
    client = TestClient(create_app(runtime=runtime))
    response = client.get("/v1/hermes/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["embedded_vendor_runtime"] is False
    assert "terminal_backends" in payload
    assert "gateway" in payload
    assert "rl" in payload


def test_strict_parity_has_no_code_gaps_in_full_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        tool_registry=_full_registry(tmp_path),
        max_iterations=2,
    )
    payload = parity_summary(runtime.tool_registry.names(), env={}, gateway_adapters=ADAPTERS.keys())
    assert payload["baseline"] == "Hermes v0.16.0 full runtime capability reference"
    assert payload["baseline_version"] == "0.16.0"
    assert payload["baseline_release_tag"] == "v2026.6.5"
    assert payload["strict_hermes_tool_count"] == 58
    assert payload["strict_gateway_platform_count"] == 22
    assert payload["core_missing_hermes_tools"] == []
    assert payload["core_missing_gateway_platforms"] == []
    assert payload["core_code_status"] == "present"
    assert payload["code_status"] == "present"
    assert payload["v014_delta"]["missing_count"] == 0
    assert payload["v016_delta"]["baseline"] == "Hermes v0.16.0 Surface Release capability reference"
    assert payload["v016_delta"]["release_tag"] == "v2026.6.5"
    assert payload["v016_delta"]["missing_count"] == 0
    assert payload["v016_delta"]["total"] == 19
    assert payload["missing_hermes_tools"] == []
    assert payload["missing_gateway_platforms"] == []
    delta_rows = [
        *payload["v014_delta"]["implemented"],
        *payload["v014_delta"]["partial"],
    ]
    assert {"computer_use", "video_generate", "x_search"} <= {item.get("hermes_tool") for item in delta_rows}
    assert {"line", "simplex", "teams"} <= {item.get("platform") for item in delta_rows}
    assert payload["strict_status"] == "in_progress"


def test_feishu_comment_replies_tool_calls_drive_api(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    seen: list[tuple[str, str]] = []

    def fake_json_request(method, url, payload=None, *, headers=None):
        seen.append((method, url))
        if "tenant_access_token" in url:
            return {"ok": True, "body": {"tenant_access_token": "tenant"}}
        assert "/comments/comment_1/replies" in url
        assert "page_size=100" in url
        assert "file_type=docx" in url
        return {"ok": True, "body": {"data": {"items": [{"reply_id": "reply_1"}], "has_more": False}}}

    monkeypatch.setattr(platform_apis, "_json_request", fake_json_request)
    registry = _full_registry(tmp_path)
    result = asyncio.run(
        registry.call_tool(
            "agent_feishu_drive_list_comment_replies",
            {"file_token": "file_1", "comment_id": "comment_1", "page_size": 500},
        )
    )
    assert result["success"] is True
    assert result["data"]["replies"]["items"][0]["reply_id"] == "reply_1"
    assert seen[0][0] == "POST"


def test_discord_server_actions_and_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    assert DiscordServerClient(token="").call(action="list_guilds")["configured"] is False
    unknown = DiscordServerClient(token="token").call(action="unknown")
    assert unknown["ok"] is False
    assert "available_actions" in unknown
    missing = DiscordServerClient(token="token").call(action="server_info")
    assert missing["missing"] == ["guild_id"]

    def fake_json_request(method, url, payload=None, *, headers=None):
        assert method == "GET"
        assert url.endswith("/guilds/guild_1/channels")
        assert headers["Authorization"] == "Bot token"
        return {"ok": True, "body": [{"id": "chan_1", "name": "general"}]}

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    monkeypatch.setattr(platform_apis, "_json_request", fake_json_request)
    registry = _full_registry(tmp_path)
    listed = asyncio.run(registry.call_tool("agent_discord_server", {"action": "list_channels", "guild_id": "guild_1"}))
    assert listed["success"] is True
    assert listed["data"]["channels"][0]["id"] == "chan_1"

    admin = asyncio.run(
        registry.call_tool(
            "agent_discord_server",
            {"action": "pin_message", "channel_id": "chan_1", "message_id": "msg_1"},
        )
    )
    assert admin["success"] is False
    assert admin["error_code"] == "APPROVAL_REQUIRED"


def test_gateway_strict_adapters_signal_qqbot_and_inbound(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    signal_cli = tmp_path / "signal-cli"
    signal_cli.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('signal-send:' + ' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    signal_cli.chmod(0o755)
    monkeypatch.setenv("SIGNAL_CLI_PATH", str(signal_cli))
    GatewayConfigStore().save_platform("signal", {"enabled": True})
    registry = _full_registry(tmp_path)
    signal_result = asyncio.run(registry.call_tool("agent_gateway_send_message", {"platform": "signal", "target": "+15551234567", "message": "hello"}))
    assert signal_result["success"] is True
    assert signal_result["data"]["adapter"]["status"] == "delivered"
    assert "signal-send:" in signal_result["data"]["adapter"]["stdout"]

    monkeypatch.setenv("QQBOT_APP_ID", "app")
    monkeypatch.setenv("QQBOT_TOKEN", "token")
    GatewayConfigStore().save_platform("qqbot", {"enabled": True})

    def fake_gateway_json_request(method, url, payload=None, *, headers=None, timeout=20.0):
        assert method == "POST"
        assert url.endswith("/channels/channel_1/messages")
        assert headers["Authorization"] == "Bot app.token"
        assert payload["content"] == "hello"
        return {"ok": True, "body": {"id": "msg_1"}}

    monkeypatch.setattr(gateway_module, "_json_request", fake_gateway_json_request)
    qq_result = asyncio.run(registry.call_tool("agent_gateway_send_message", {"platform": "qqbot", "target": "channel_1", "message": "hello"}))
    assert qq_result["success"] is True
    assert qq_result["data"]["message"]["status"] == "delivered"

    assert {"api_server", "signal", "wecom_callback", "qqbot"} <= set(ADAPTERS)
    assert hasattr(ADAPTERS["qqbot"](GatewayConfigStore().platform_status("qqbot")), "upload_media")


def test_v014_gateway_adapters_line_simplex_and_teams(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    registry = _full_registry(tmp_path)
    names = {item["name"] for item in asyncio.run(registry.call_tool("agent_gateway_platforms", {}))["data"]["platforms"]}
    assert {"line", "simplex", "teams"} <= names

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "line-token")
    GatewayConfigStore().save_platform("line", {"enabled": True})
    line_calls: list[tuple[str, str, object]] = []

    def fake_gateway_json_request(method, url, payload=None, *, headers=None, timeout=20.0):
        line_calls.append((method, url, payload))
        assert headers["Authorization"] == "Bearer line-token"
        return {"ok": True, "body": {"sentMessages": [{"id": "line_msg"}]}}

    monkeypatch.setattr(gateway_module, "_json_request", fake_gateway_json_request)
    line = asyncio.run(registry.call_tool("agent_gateway_send_message", {"platform": "line", "target": "user_1", "message": "hello"}))
    assert line["success"] is True
    assert line["data"]["message"]["status"] == "delivered"
    assert line_calls[0][1].endswith("/v2/bot/message/push")

    cli = tmp_path / "simplex-cli"
    cli.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('simplex:' + ' '.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    monkeypatch.setenv("SIMPLEX_CLI_PATH", str(cli))
    GatewayConfigStore().save_platform("simplex", {"enabled": True})
    simplex = asyncio.run(registry.call_tool("agent_gateway_send_message", {"platform": "simplex", "target": "contact_1", "message": "hello"}))
    assert simplex["success"] is True
    assert "simplex:send contact_1 hello" in simplex["data"]["adapter"]["stdout"]

    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://teams.example/webhook")
    GatewayConfigStore().save_platform("teams", {"enabled": True})
    teams_calls: list[tuple[str, str, object]] = []

    def fake_teams_request(method, url, payload=None, *, headers=None, timeout=20.0):
        teams_calls.append((method, url, payload))
        return {"ok": True, "body": {"id": "teams_msg"}}

    monkeypatch.setattr(gateway_module, "_json_request", fake_teams_request)
    teams = asyncio.run(registry.call_tool("agent_gateway_send_message", {"platform": "teams", "target": "unused", "message": "hello"}))
    assert teams["success"] is True
    assert teams_calls[0] == ("POST", "https://teams.example/webhook", {"text": "hello"})


def test_gateway_send_message_parses_hermes_target_and_media_tags(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    GatewayConfigStore().save_platform("discord", {"enabled": True})
    media = tmp_path / "report.txt"
    media.write_text("attachment", encoding="utf-8")
    calls: list[tuple[str, str, object]] = []

    def fake_json_request(method, url, payload=None, *, headers=None, timeout=20.0):
        calls.append((method, url, payload))
        assert headers["Authorization"] == "Bot token"
        return {"ok": True, "body": {"id": "text_msg"}}

    def fake_multipart_request(method, url, *, fields=None, files=None, headers=None, timeout=30.0):
        calls.append((method, url, {"fields": fields, "files": sorted((files or {}).keys())}))
        assert headers["Authorization"] == "Bot token"
        assert "files[0]" in files
        return {"ok": True, "body": {"id": "media_msg"}}

    monkeypatch.setattr(gateway_module, "_json_request", fake_json_request)
    monkeypatch.setattr(gateway_module, "_multipart_request", fake_multipart_request)
    registry = _full_registry(tmp_path)
    result = asyncio.run(
        registry.call_tool(
            "agent_message_send",
            {
                "target": f"discord:123456789:987654321",
                "message": f"hello\nMEDIA:{media}",
            },
        )
    )
    assert result["success"] is True
    assert result["data"]["message"]["target"] == "123456789"
    assert result["data"]["message"]["thread_id"] == "987654321"
    assert result["data"]["message"]["metadata"]["cleaned_content"] == "hello"
    assert result["data"]["message"]["metadata"]["media"][0]["path"] == str(media)
    assert result["data"]["adapter"]["media"][0]["status"] == "delivered"
    assert calls[0][1].endswith("/channels/987654321/messages")
    assert calls[1][1].endswith("/channels/987654321/messages")


def test_message_send_list_action_reports_gateway_platforms(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    registry = _full_registry(tmp_path)
    result = asyncio.run(registry.call_tool("agent_message_send", {"action": "list"}))
    assert result["success"] is True
    names = {item["name"] for item in result["data"]["platforms"]}
    assert {"feishu", "discord", "signal", "qqbot", "api_server"} <= names


def test_gateway_inbound_uses_platform_adapter_signature_and_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.setenv("FEISHU_APP_ID", "app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    GatewayConfigStore().save_platform("feishu", {"enabled": True})
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )
    client = TestClient(create_app(runtime=runtime))
    payload = {
        "event": {
            "event_id": "evt_1",
            "message": {"message_id": "msg_1", "chat_id": "chat_1", "content": "/approve abc"},
            "sender": {"sender_id": {"open_id": "user_1"}},
        }
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    response = client.post(
        "/v1/gateway/webhooks/feishu",
        headers={"X-Lark-Signature": signature},
        content=raw,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "received"
    assert data["target"] == "chat_1"
    assert data["content"] == "/approve abc"
    assert data["metadata"]["signature_verified"] is True
    assert data["metadata"]["slash_command"] == {"command": "approve", "arguments": "abc"}
    assert data["metadata"]["adapter"]["verified"] is True
    assert data["metadata"]["approval_callback"] == {"approval_id": "abc", "action": "approve"}
    assert data["metadata"]["routing"]["enqueue_agent"] is False


def test_feature_ledger_has_no_mock_gaps_for_full_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        tool_registry=_full_registry(tmp_path),
        max_iterations=2,
    )
    payload = parity_summary(runtime.tool_registry.names(), env={}, gateway_adapters=ADAPTERS.keys())
    assert payload["core_missing_features"] == []
    assert payload["v014_delta"]["missing_count"] == 0
    assert payload["v016_delta"]["missing_count"] == 0
    assert {item["feature"] for item in payload["feature_mapping"]} >= {
        "gateway_channel_directory",
        "gateway_direct_delivery",
        "plugin_commands",
        "tui_controller",
        "terminal_watch_notify",
        "rl_native_scaffold_runner",
        "openai_compatible_local_proxy",
        "write_time_lsp_diagnostics",
        "computer_use_backend",
        "per_turn_file_mutation_verifier",
        "live_session_handoff",
        "subgoal_control",
        "desktop_native_self_update",
        "remote_gateway_connection_profiles",
        "model_picker_profiles_and_fallback",
        "undo_last_turns",
        "checkpoint_and_rollback",
    }


def test_gateway_directory_and_direct_delivery_resolve_alias(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    registry = _full_registry(tmp_path)
    upsert = asyncio.run(
        registry.call_tool(
            "agent_gateway_directory",
            {"action": "upsert", "platform": "local", "name": "ops", "target": "desktop", "thread_id": "thread_1"},
        )
    )
    assert upsert["success"] is True
    delivered = asyncio.run(
        registry.call_tool(
            "agent_gateway_direct_deliver",
            {"platform": "local", "target": "ops", "message": "directory hello"},
        )
    )
    assert delivered["success"] is True
    assert delivered["data"]["deliver_mode"] == "direct_platform"
    assert delivered["data"]["message"]["target"] == "desktop"
    assert delivered["data"]["message"]["thread_id"] == "thread_1"
    assert delivered["data"]["message"]["metadata"]["channel_resolution"]["name"] == "ops"


def test_plugin_commands_and_extended_hooks_execute(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AIASK_AGENT_HOME", str(home))
    plugin_dir = home / "plugins" / "command-hook"
    plugin_dir.mkdir(parents=True)
    plugin_dir.joinpath("runner.py").write_text(
        "import json, sys\n"
        "payload=json.loads(sys.stdin.read())\n"
        "tool=payload['tool']\n"
        "args=payload['arguments']\n"
        "if tool == 'ship':\n"
        "    print(json.dumps({'result': {'shipped': args.get('name')}}))\n"
        "elif tool == 'transform_terminal_output':\n"
        "    print(json.dumps({'terminal_output': 'hooked-terminal'}))\n"
        "else:\n"
        "    print(json.dumps({'context': tool, 'result': {'ok': True}}))\n",
        encoding="utf-8",
    )
    plugin_dir.joinpath("plugin.json").write_text(
        json.dumps(
            {
                "name": "command-hook",
                "enabled": True,
                "commands": [{"name": "ship", "runner": {"command": [sys.executable, "runner.py"]}}],
                "hooks": [
                    {"name": "post_tool_call", "command": [sys.executable, "runner.py"]},
                    {"name": "post_llm_call", "command": [sys.executable, "runner.py"]},
                    {"name": "on_session_start", "command": [sys.executable, "runner.py"]},
                    {"name": "on_session_end", "command": [sys.executable, "runner.py"]},
                    {"name": "transform_terminal_output", "command": [sys.executable, "runner.py"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    store = AgentSessionStore(tmp_path / "state.sqlite3")
    runtime = AgentRuntime(
        model_client=MockModelClient(),
        session_store=store,
        tool_registry=build_default_tool_registry(session_store=store, policy_engine=_full_policy(tmp_path)),
        max_iterations=2,
    )
    command_result = asyncio.run(runtime.tool_registry.call_tool("agent_plugin_command_hook_command_ship", {"name": "release"}))
    assert command_result["success"] is True
    assert command_result["data"]["kind"] == "command"
    assert command_result["data"]["result"] == {"result": {"shipped": "release"}}

    terminal = asyncio.run(runtime.tool_registry.call_tool("agent_terminal", {"command": "echo original", "cwd": "."}))
    assert terminal["success"] is True
    assert terminal["data"]["stdout"] == "hooked-terminal"

    result = asyncio.run(runtime.run([{"role": "user", "content": "hello"}]))
    events = [item["data"] for item in store.list_run_events(result.run_id) if item["event"] == "plugin.hook"]
    hook_names = {item.get("hook") for item in events}
    assert {"on_session_start", "post_llm_call", "on_session_end"} <= hook_names


def test_tui_controller_parser_reducers_and_resume() -> None:
    controller = TUIController()
    parsed = controller.parse_slash_command("/resume sess_1")
    assert parsed is not None
    assert parsed.command == "/resume"
    assert controller.apply_local_command(parsed)["session_id"] == "sess_1"
    assert controller.session_id == "sess_1"
    assert "/steer" in controller.autocomplete("/st")
    assert "/undo" in controller.autocomplete("/un")
    undo = controller.parse_slash_command("/undo 2")
    assert undo is not None
    undo_plan = controller.apply_local_command(undo)
    assert undo_plan["status"] == "pending_remote_undo"
    assert undo_plan["turns"] == 2
    assert undo_plan["session_id"] == "sess_1"
    assert "/rollback" in controller.autocomplete("/ro")
    rollback = controller.parse_slash_command("/rollback fchk_demo")
    assert rollback is not None
    rollback_plan = controller.apply_local_command(rollback)
    assert rollback_plan == {"checkpoint_id": "fchk_demo", "status": "pending_remote_rollback"}
    latest_rollback = controller.parse_slash_command("/rollback latest notes/demo.txt")
    assert latest_rollback is not None
    assert controller.apply_local_command(latest_rollback)["path"] == "notes/demo.txt"
    assert "/artifacts" in controller.autocomplete("/ar")
    assert "/sources" in controller.autocomplete("/so")
    assert controller.features()["artifact_browser"] is True
    assert controller.features()["source_browser"] is True
    reduced = controller.reduce_sse_event({"event": "approval.pending", "data": {"approval": {"approval_id": "app_1"}}})
    assert reduced["event"] == "approval.pending"
    assert controller.approvals[-1]["approval"]["approval_id"] == "app_1"


def test_terminal_self_protection_and_watch_action(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    registry = _full_registry(tmp_path)
    protected = asyncio.run(registry.call_tool("agent_terminal", {"command": f"kill {os.getpid()}", "cwd": "."}))
    assert protected["success"] is False
    assert protected["error_code"] == "APPROVAL_REQUIRED"
    assert "AIASK" in protected["data"]["approval"]["reason"]

    started = asyncio.run(
        registry.call_tool(
            "agent_terminal",
            {"command": f"{sys.executable} -c \"print('watch-ok')\"", "cwd": ".", "background": True},
        )
    )
    assert started["success"] is True
    watched = asyncio.run(
        registry.call_tool(
            "agent_process",
            {"action": "watch", "process_id": started["data"]["process_id"], "timeout_seconds": 5, "max_output_bytes": 2000},
        )
    )
    assert watched["success"] is True
    assert watched["data"]["watch"] is True
    assert "watch-ok" in watched["data"]["output"]["stdout"]
