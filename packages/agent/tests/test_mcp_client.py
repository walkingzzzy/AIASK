from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from aiask_agent.mcp_client import MCPAggregator


class MethodNotFound(RuntimeError):
    pass


class FakePartialSession:
    async def list_tools(self):
        return SimpleNamespace(
            tools=[
                {
                    "name": "quote",
                    "description": "Read quote",
                    "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}},
                }
            ]
        )

    async def list_resources(self):
        raise MethodNotFound("Method not found: resources/list")

    async def list_prompts(self):
        raise MethodNotFound("Method not found: prompts/list")


class FakeBrokenToolsSession(FakePartialSession):
    async def list_tools(self):
        raise MethodNotFound("Method not found: tools/list")


def _write_config(path) -> None:
    path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "finance",
                        "domain": "financial",
                        "transport": "stdio",
                        "command": "dummy",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_discover_keeps_tools_when_resources_prompts_are_unsupported(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "mcp_servers.json"
    _write_config(config_path)
    mcp = MCPAggregator(config_path)

    async def fake_with_session(server, operation):
        return await operation(FakePartialSession())

    monkeypatch.setattr(mcp, "_with_session", fake_with_session)

    async def scenario():
        discovered = await mcp.discover("finance")
        updated = await mcp.discover_and_update("finance")
        return discovered, updated

    discovered, updated = asyncio.run(scenario())

    assert discovered["tools"][0]["name"] == "quote"
    assert discovered["resources"] == []
    assert discovered["prompts"] == []
    assert discovered["partial_success"] is True
    assert set(discovered["unsupported_methods"]) == {"resources/list", "prompts/list"}
    assert updated["tools_count"] == 1
    assert updated["resources_count"] == 0
    assert updated["prompts_count"] == 0
    assert updated["partial_success"] is True
    assert updated["registration"]["partial_success"] is True
    assert set(updated["registration"]["unsupported_methods"]) == {"resources/list", "prompts/list"}


def test_discover_fails_when_tools_list_is_unsupported(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "mcp_servers.json"
    _write_config(config_path)
    mcp = MCPAggregator(config_path)

    async def fake_with_session(server, operation):
        return await operation(FakeBrokenToolsSession())

    monkeypatch.setattr(mcp, "_with_session", fake_with_session)

    try:
        asyncio.run(mcp.discover("finance"))
    except MethodNotFound as exc:
        assert "tools/list" in str(exc)
    else:
        raise AssertionError("tools/list failure must fail server discovery")
