from __future__ import annotations

import json

from fastapi.testclient import TestClient

from aiask_agent.model_client import MockModelClient
from aiask_agent.runtime import AgentRuntime
from aiask_agent.server import create_app
from aiask_agent.session_store import AgentSessionStore


def _runtime(tmp_path) -> AgentRuntime:
    return AgentRuntime(
        model_client=MockModelClient(),
        session_store=AgentSessionStore(tmp_path / "state.sqlite3"),
        max_iterations=2,
    )


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AIASK_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AIASK_AGENT_ENABLE_HERMES_FULL", "1")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    return TestClient(create_app(runtime=_runtime(tmp_path)))


def test_desktop_settings_status_redacts_secret_state_and_reports_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://models.example.test/v1")
    client = _client(tmp_path, monkeypatch)

    response = client.get("/v1/desktop/settings/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    raw = json.dumps(payload)
    assert payload["object"] == "aiask.desktop_settings_status"
    assert payload["secrets_redacted"] is True
    assert payload["agent"]["control_authorized"] is True
    assert payload["llm"]["ai_status"]["api_key_configured"] is True
    assert payload["llm"]["ai_status"]["secrets_redacted"] is True
    assert payload["profile"]["user_id"] == "local"
    assert "sk-test-secret-value" not in raw


def test_desktop_settings_status_uses_project_env_llm_config(tmp_path, monkeypatch) -> None:
    project_env = tmp_path / ".env"
    project_env.write_text(
        "\n".join(
            [
                "AIASK_AGENT_MODEL_PROVIDER=openai",
                "AIASK_AGENT_MODEL=root-api-model",
                "OPENAI_BASE_URL=https://root-api.example.test/v1",
                "OPENAI_API_KEY=sk-root-project-secret",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIASK_AGENT_LOAD_PROJECT_ENV", "1")
    monkeypatch.setenv("AIASK_AGENT_ENV_FILE", str(project_env))
    for key in ("AIASK_AGENT_MODEL_PROVIDER", "AIASK_AGENT_MODEL", "OPENAI_BASE_URL", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/v1/desktop/settings/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    raw = json.dumps(payload)
    ai_status = payload["llm"]["ai_status"]
    provider_status = payload["llm"]["providers"]
    assert ai_status["provider"] == "openai"
    assert ai_status["model"] == "root-api-model"
    assert ai_status["base_url_configured"] is True
    assert ai_status["api_key_configured"] is True
    assert ai_status["config_source"]["loaded"] is True
    assert ai_status["config_source"]["source"] == "explicit"
    assert provider_status["default_model"] == "root-api-model"
    assert provider_status["config_source"]["loaded"] is True
    assert "sk-root-project-secret" not in raw


def test_desktop_local_profile_can_be_saved_and_reloaded(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    saved = client.patch(
        "/v1/desktop/users/local-profile",
        json={"user_id": "desk-user", "profile_name": "Desktop Operator"},
    )
    fetched = client.get("/v1/desktop/users/local-profile")

    assert saved.status_code == 200
    assert saved.json()["user_id"] == "desk-user"
    assert fetched.status_code == 200
    assert fetched.json()["profile_name"] == "Desktop Operator"
    assert fetched.json()["storage"] == "local_file"
    assert fetched.json()["secrets_redacted"] is True


def test_desktop_data_sync_plan_creates_intent_request_without_executing(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/desktop/data/sync-plan",
        json={"codes": ["600519", "000001"], "task_type": "kline", "period": "daily"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "aiask.desktop_data_sync_plan"
    assert payload["intent_request"]["action"] == "data_sync.sync"
    assert payload["intent_request"]["params"]["codes"] == ["600519", "000001"]
    assert payload["commands"][0]["path"] == "/intents"
    assert payload["side_effect"]["confirmation_required"] is True
    assert payload["secrets_redacted"] is True


def test_desktop_intent_create_is_control_gated_and_returns_intent(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    payload = {
        "action": "factor_factory.run_once",
        "params": {"candidate_count": 1},
        "rationale": "test desktop intent",
    }

    denied = client.post("/intents", json=payload)
    created = client.post("/intents", headers={"Authorization": "Bearer secret"}, json=payload)

    assert denied.status_code == 401
    assert created.status_code == 200
    body = created.json()
    assert body["success"] is True
    assert body["data"]["intent"]["action"] == "factor_factory.run_once"
    assert body["data"]["intent"]["target_tool"] == "factor_factory"
    assert body["data"]["intent"]["status"] == "awaiting_confirmation"


def test_desktop_factor_factory_status_endpoint_uses_safe_facade(tmp_path, monkeypatch) -> None:
    async def fake_factor_status(limit: int = 50) -> dict:
        return {
            "object": "aiask.desktop.factor_factory_status",
            "status": "ready",
            "configured": True,
            "active_factors": [{"name": "alpha"}][:limit],
            "engine_health": {"search": "ready"},
            "pool_health": {"active": 1},
            "secrets_redacted": True,
        }

    monkeypatch.setattr("aiask_agent.server.factor_factory_status", fake_factor_status)
    client = _client(tmp_path, monkeypatch)

    response = client.get("/v1/desktop/factor-factory/status?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["active_factors"] == [{"name": "alpha"}]
    assert payload["secrets_redacted"] is True
