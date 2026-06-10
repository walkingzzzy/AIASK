from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aiask_agent.model_client import ModelResponse, MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore


class RecordingModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]], model: str) -> ModelResponse:
        self.calls.append({"messages": messages, "tools": tools, "model": model})
        return ModelResponse(content=f"smoke-ok:{model}", usage={"total_tokens": 3})


def test_ai_status_reports_mock_runtime_without_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "mock")
    runtime = AgentRuntime(model_client=MockModelClient(), session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/v1/ai/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mock"
    assert payload["mock"] is True
    assert payload["configured"] is True
    assert payload["secrets_redacted"] is True
    assert "sk-" not in str(payload)


def test_ai_smoke_uses_runtime_model_client_and_model_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8317/v1")
    model = RecordingModel()
    runtime = AgentRuntime(model_client=model, model="default-model", session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))

    response = client.post("/v1/ai/smoke", json={"model": "custom-model", "prompt": "ping"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["configured"] is True
    assert payload["model"] == "custom-model"
    assert payload["response_preview"] == "smoke-ok:custom-model"
    assert model.calls[0]["messages"][0]["content"] == "ping"


def test_ai_smoke_returns_structured_error_for_model_failure(tmp_path, monkeypatch) -> None:
    class FailingModel:
        async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]], model: str) -> ModelResponse:
            raise TimeoutError("model timeout")

    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    runtime = AgentRuntime(model_client=FailingModel(), session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))

    response = client.post("/v1/ai/smoke", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "TIMEOUT"
    assert payload["secrets_redacted"] is True


def test_ai_models_lists_openai_compatible_models_with_fake_client(tmp_path, monkeypatch) -> None:
    class FakeModel:
        def __init__(self, model_id: str) -> None:
            self.id = model_id

        def model_dump(self) -> dict[str, str]:
            return {"id": self.id, "owned_by": "fake"}

    class FakeModels:
        async def list(self):
            return types.SimpleNamespace(data=[FakeModel("model-a"), {"id": "model-b"}])

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
            self.api_key = api_key
            self.base_url = base_url
            self.models = FakeModels()

        async def close(self) -> None:
            return None

    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8317/v1")
    runtime = AgentRuntime(model_client=MockModelClient(), session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/v1/ai/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert {item["id"] for item in payload["data"]} == {"model-a", "model-b"}


def test_ai_smoke_accepts_openai_compatible_string_response(tmp_path, monkeypatch) -> None:
    created_clients: list[dict[str, str | None]] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            return "AIASK_LIVE_OK"

    class FakeChat:
        def __init__(self) -> None:
            self.completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
            self.api_key = api_key
            self.base_url = base_url
            created_clients.append({"api_key": api_key, "base_url": str(base_url) if base_url is not None else None})
            self.chat = FakeChat()

        async def close(self) -> None:
            return None

    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("AIASK_AGENT_MODEL", "compat-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8317")
    runtime = AgentRuntime(session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))

    response = client.post("/v1/ai/smoke", json={"prompt": "ping"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["model"] == "compat-model"
    assert payload["response_preview"] == "AIASK_LIVE_OK"
    assert payload["secrets_redacted"] is True
    assert created_clients[0]["base_url"] == "http://localhost:8317/v1"


def test_ai_smoke_rejects_html_gateway_response(tmp_path, monkeypatch) -> None:
    class FakeCompletions:
        async def create(self, **kwargs):
            return "<!doctype html><html><title>Gateway</title></html>"

    class FakeChat:
        def __init__(self) -> None:
            self.completions = FakeCompletions()

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
            self.chat = FakeChat()

        async def close(self) -> None:
            return None

    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8317")
    runtime = AgentRuntime(session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))

    response = client.post("/v1/ai/smoke", json={"prompt": "ping"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_code"] == "AI_SMOKE_FAILED"
    assert "returned HTML" in payload["error"]
    assert payload["secrets_redacted"] is True


def test_ai_models_falls_back_to_configured_model_on_nonstandard_provider(tmp_path, monkeypatch) -> None:
    created_clients: list[dict[str, str | None]] = []

    class FakeModels:
        async def list(self):
            raise AttributeError("'str' object has no attribute '_set_private_attributes'")

    class FakeAsyncOpenAI:
        def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
            self.api_key = api_key
            self.base_url = base_url
            created_clients.append({"api_key": api_key, "base_url": str(base_url) if base_url is not None else None})
            self.models = FakeModels()

        async def close(self) -> None:
            return None

    fake_openai = types.ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("AIASK_AGENT_MODEL", "compat-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8317")
    runtime = AgentRuntime(model_client=MockModelClient(), session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/v1/ai/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["unsupported"] is True
    assert payload["data"] == [{"id": "compat-model", "owned_by": "openai", "fallback": True}]
    assert payload["warning_code"] == "AI_SMOKE_FAILED"
    assert "error" not in payload
    assert payload["secrets_redacted"] is True
    assert created_clients[0]["base_url"] == "http://localhost:8317/v1"


def test_live_ai_smoke_when_configured(tmp_path, request, monkeypatch) -> None:
    if not request.config.getoption("--run-live-ai"):
        pytest.skip("live AI smoke tests disabled")
    if not sys.modules.get("openai") and not __import__("importlib").util.find_spec("openai"):
        pytest.skip("openai package is not installed")
    if not __import__("os").getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not configured")
    runtime = AgentRuntime(session_store=AgentSessionStore(tmp_path / "state.sqlite3"))
    client = TestClient(create_app(runtime=runtime))
    response = client.post("/v1/ai/smoke", json={"prompt": "Reply with ok."})
    assert response.status_code == 200
    assert response.json()["configured"] is True
