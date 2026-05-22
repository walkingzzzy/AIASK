from __future__ import annotations

import asyncio
import json
from typing import Any

from aiask_agent.model_client import ModelResponse
from aiask_agent.runtime import AgentRuntime
from aiask_agent.session_store import AgentSessionStore
from aiask_agent.tool_registry import AgentToolRegistry, aiask_envelope


class ToolCallingModel:
    def __init__(self) -> None:
        self.calls = 0
        self.saw_tool_result = False

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                tool_calls=[
                    {
                        "id": "call_test",
                        "type": "function",
                        "function": {
                            "name": "agent_test_tool",
                            "arguments": json.dumps({"value": 3}),
                        },
                    }
                ],
                usage={"total_tokens": 1},
            )
        self.saw_tool_result = any(msg.get("role") == "tool" for msg in messages)
        return ModelResponse(content="done", usage={"total_tokens": 2})


class ClosableModel:
    def __init__(self) -> None:
        self.closed = False

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> ModelResponse:
        return ModelResponse(content="ok")

    async def aclose(self) -> None:
        self.closed = True


def test_runtime_executes_tool_call_and_feeds_result_back(tmp_path) -> None:
    registry = AgentToolRegistry()

    async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        return aiask_envelope(
            True,
            data={"value": arguments["value"] + 1},
            error=None,
            tool_name="agent_test_tool",
            source_chain=["test"],
        )

    registry.register(
        "agent_test_tool",
        description="test tool",
        parameters={"type": "object", "properties": {"value": {"type": "integer"}}},
        handler=handler,
    )
    model = ToolCallingModel()
    runtime = AgentRuntime(
        model_client=model,
        tool_registry=registry,
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=3,
    )

    result = asyncio.run(runtime.run([{"role": "user", "content": "call tool"}], user_id="u1"))
    assert result.content == "done"
    assert model.saw_tool_result is True
    assert result.tool_calls[0]["name"] == "agent_test_tool"
    assert result.tool_calls[0]["result"]["data"]["value"] == 4
    saved = runtime.session_store.get_response(result.response_id)
    assert saved is not None
    assert saved["session_id"] == result.session_id


def test_runtime_close_releases_model_client(tmp_path) -> None:
    model = ClosableModel()
    runtime = AgentRuntime(
        model_client=model,
        tool_registry=AgentToolRegistry(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
    )

    runtime.close()
    runtime.close()
    assert model.closed is True
