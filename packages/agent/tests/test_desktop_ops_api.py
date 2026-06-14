from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from aiask_agent.moa import aggregator_model, reference_models
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
    monkeypatch.setenv("AIASK_AGENT_ENABLE_GENERAL_TOOLS", "1")
    monkeypatch.setenv("AIASK_AGENT_TOOLSET", "general_full")
    monkeypatch.setenv("AIASK_AGENT_CONTROL_TOKEN", "secret")
    monkeypatch.setenv("AIASK_STOCK_DATA_SOURCES_FILE", str(tmp_path / "stock_data_sources.json"))
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


def test_desktop_settings_status_project_env_llm_overrides_process_env(tmp_path, monkeypatch) -> None:
    project_env = tmp_path / ".env"
    project_env.write_text(
        "\n".join(
            [
                "AIASK_AGENT_MODEL_PROVIDER=openai",
                "AIASK_AGENT_MODEL=file-api-model",
                "AIASK_AGENT_VISION_MODEL=file-vision-model",
                "AIASK_AGENT_VISION_PROVIDER=openai",
                "AIASK_MOA_REFERENCE_MODELS=file-ref-a,file-ref-b",
                "AIASK_MOA_AGGREGATOR_MODEL=file-agg-model",
                "OPENAI_BASE_URL=https://file-api.example.test/v1",
                "OPENAI_API_KEY=sk-file-project-secret",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIASK_AGENT_LOAD_PROJECT_ENV", "1")
    monkeypatch.setenv("AIASK_AGENT_ENV_FILE", str(project_env))
    monkeypatch.setenv("AIASK_AGENT_MODEL_PROVIDER", "mock")
    monkeypatch.setenv("AIASK_AGENT_MODEL", "process-model")
    monkeypatch.setenv("AIASK_AGENT_VISION_MODEL", "process-vision-model")
    monkeypatch.setenv("AIASK_AGENT_VISION_PROVIDER", "mock")
    monkeypatch.setenv("AIASK_MOA_REFERENCE_MODELS", "process-ref")
    monkeypatch.setenv("AIASK_MOA_AGGREGATOR_MODEL", "process-agg-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://process.example.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-process-secret")

    client = _client(tmp_path, monkeypatch)
    response = client.get("/v1/desktop/settings/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    payload = response.json()
    raw = json.dumps(payload)
    ai_status = payload["llm"]["ai_status"]
    provider_status = payload["llm"]["providers"]
    assert ai_status["provider"] == "openai"
    assert ai_status["model"] == "file-api-model"
    assert provider_status["default_model"] == "file-api-model"
    assert reference_models() == ["file-ref-a", "file-ref-b"]
    assert aggregator_model("default-agg") == "file-agg-model"
    assert os.environ["AIASK_AGENT_VISION_MODEL"] == "file-vision-model"
    assert os.environ["AIASK_AGENT_VISION_PROVIDER"] == "openai"
    assert ai_status["config_source"]["source"] == "explicit"
    assert "sk-file-project-secret" not in raw
    assert "sk-process-secret" not in raw


def test_ai_config_can_be_saved_from_desktop_and_redacts_secret(tmp_path, monkeypatch) -> None:
    project_env = tmp_path / ".env"
    project_env.write_text("AIASK_AGENT_MODEL_PROVIDER=mock\nAIASK_AGENT_MODEL=mock-local\n", encoding="utf-8")
    monkeypatch.setenv("AIASK_AGENT_LOAD_PROJECT_ENV", "1")
    monkeypatch.setenv("AIASK_AGENT_ENV_FILE", str(project_env))
    client = _client(tmp_path, monkeypatch)

    config = client.get("/v1/ai/config", headers={"Authorization": "Bearer secret"})
    assert config.status_code == 200
    assert {item["id"] for item in config.json()["presets"]} >= {"openai", "deepseek", "dashscope-qwen-cn", "anthropic", "mock"}

    saved = client.patch(
        "/v1/ai/config",
        headers={"Authorization": "Bearer secret"},
        json={
            "preset": "deepseek",
            "model": "deepseek-chat",
            "api_key": "sk-desktop-config-secret",
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    raw = json.dumps(payload)
    assert payload["saved"] is True
    assert payload["provider"] == "openai"
    assert payload["model"] == "deepseek-chat"
    assert payload["base_url_configured"] is True
    assert payload["api_key_configured"] is True
    assert "OPENAI_API_KEY" in payload["updated_keys"]
    assert "sk-desktop-config-secret" not in raw

    status = client.get("/v1/ai/status")
    assert status.json()["provider"] == "openai"
    assert status.json()["model"] == "deepseek-chat"
    env_text = project_env.read_text(encoding="utf-8")
    assert "AIASK_AGENT_MODEL_PROVIDER=openai" in env_text
    assert "AIASK_AGENT_MODEL=deepseek-chat" in env_text
    assert "OPENAI_BASE_URL=https://api.deepseek.com" in env_text


def test_ai_config_save_requires_control_token(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.patch("/v1/ai/config", json={"preset": "mock"})

    assert response.status_code == 401


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


def test_desktop_data_sync_plan_supports_market_temperature_cache_without_codes(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/v1/desktop/data/sync-plan",
        json={"codes": [], "task_type": "market_temperature_snapshot_cache"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["intent_request"]["action"] == "data_sync.sync"
    assert payload["intent_request"]["params"]["codes"] == []
    assert payload["intent_request"]["params"]["task_type"] == "market_temperature_snapshot_cache"
    assert payload["intent_request"]["params"]["limit"] == 1000
    assert payload["intent_request"]["params"]["top_n"] == 20
    assert payload["intent_request"]["params"]["min_bars"] == 20
    assert payload["side_effect"]["confirmation_required"] is True


def test_desktop_stock_data_sources_can_save_test_and_redact_search_keys(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    status = client.get("/v1/desktop/stock-data-sources", headers={"Authorization": "Bearer secret"})
    assert status.status_code == 200
    providers = {item["provider"] for item in status.json()["presets"]}
    assert {"duckduckgo", "tavily", "brave_search", "serpapi", "exa", "akshare"} <= providers

    saved = client.post(
        "/v1/desktop/stock-data-sources",
        headers={"Authorization": "Bearer secret"},
        json={
            "provider": "tavily",
            "name": "Tavily Desktop",
            "base_url": "https://api.tavily.com",
            "api_key": "tvly-desktop-secret",
            "priority": 10,
            "enabled": True,
        },
    )
    assert saved.status_code == 200
    saved_payload = saved.json()
    raw = json.dumps(saved_payload)
    assert saved_payload["source"]["provider"] == "tavily"
    assert saved_payload["source"]["api_key"] == "[redacted]"
    assert "tvly-desktop-secret" not in raw

    seen_tavily_bodies = []

    def fake_tavily_test(url, *, method="GET", body=None, headers=None, timeout=8.0):
        assert method == "POST"
        assert url == "https://api.tavily.com/search"
        assert headers == {"Authorization": "Bearer tvly-desktop-secret"}
        assert body["query"] == "AIASK data source smoke test"
        seen_tavily_bodies.append(body)
        return 200, {"results": [{"title": "ok", "url": "https://example.com"}]}

    monkeypatch.setattr("aiask_agent.stock_data_sources._http_json", fake_tavily_test)

    smoke = client.post(
        "/v1/desktop/stock-data-sources/test",
        headers={"Authorization": "Bearer secret"},
        json={"provider": "tavily", "mode": "connectivity"},
    )
    assert smoke.status_code == 200
    assert smoke.json()["success"] is True
    assert "tvly-desktop-secret" not in json.dumps(smoke.json())

    draft_smoke = client.post(
        "/v1/desktop/stock-data-sources/test",
        headers={"Authorization": "Bearer secret"},
        json={
            "id": saved_payload["source"]["id"],
            "provider": "tavily",
            "mode": "connectivity",
            "source": {
                "id": saved_payload["source"]["id"],
                "provider": "tavily",
                "name": "Tavily Desktop",
                "base_url": "https://api.tavily.com",
                "search_depth": "advanced",
            },
        },
    )
    assert draft_smoke.status_code == 200
    assert draft_smoke.json()["success"] is True
    assert seen_tavily_bodies[-1]["search_depth"] == "advanced"
    assert "tvly-desktop-secret" not in json.dumps(draft_smoke.json())


def test_agent_web_search_uses_configured_search_source(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/v1/desktop/stock-data-sources",
        headers={"Authorization": "Bearer secret"},
        json={
            "provider": "tavily",
            "name": "Tavily Desktop",
            "base_url": "https://api.tavily.com",
            "api_key": "tvly-desktop-secret",
            "priority": 1,
            "enabled": True,
        },
    )

    def fake_json_request(method, url, payload=None, *, headers=None, timeout=30.0):
        assert method == "POST"
        assert url == "https://api.tavily.com/search"
        assert headers == {"Authorization": "Bearer tvly-desktop-secret"}
        assert payload["query"] == "AIASK search"
        return {
            "ok": True,
            "status_code": 200,
            "body": {
                "answer": "ok",
                "results": [{"title": "AIASK result", "url": "https://example.com/aiask", "content": "result snippet"}],
            },
        }

    monkeypatch.setattr("aiask_agent.native_capabilities._json_request", fake_json_request)
    result = client.post(
        "/v1/tools/agent_web_search",
        headers={"Authorization": "Bearer secret"},
        json={"query": "AIASK search", "provider": "tavily", "limit": 1},
    )

    assert result.status_code == 200
    payload = result.json()
    raw = json.dumps(payload)
    assert payload["success"] is True
    assert payload["data"]["provider"] == "tavily"
    assert payload["data"]["results"][0]["url"] == "https://example.com/aiask"
    assert "tvly-desktop-secret" not in raw


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


def test_desktop_trade_prediction_routes_use_agent_read_facades(tmp_path, monkeypatch) -> None:
    async def fake_call_db_facade(loader, params=None):
        loader_name = getattr(loader, "__name__", "")
        if loader_name == "_load_trade_prediction_status_handler":
            return {
                "success": True,
                "data": {"object": "trade_prediction.status", "sample_n": 2, "status": "ready"},
                "error": None,
                "meta": {"side_effect": {"level": "read_only"}},
            }
        if loader_name == "_load_trade_prediction_outcomes_handler":
            return {
                "success": True,
                "data": {
                    "object": "trade_prediction.outcomes",
                    "items": [{"prediction_id": "tp_1", "score_version": "trade_prediction_score_v2"}],
                    "count": 1,
                },
                "error": None,
                "meta": {"side_effect": {"level": "read_only"}},
            }
        if loader_name == "_load_trade_prediction_matrix_handler":
            return {
                "success": True,
                "data": {
                    "object": "trade_prediction.matrix",
                    "rows": [{"dimension": "family", "value": "momentum", "sample_n": 2}],
                    "row_count": 1,
                },
                "error": None,
                "meta": {"side_effect": {"level": "read_only"}},
            }
        raise AssertionError(loader_name)

    monkeypatch.setattr("aiask_agent.adapters.strategy_factory._call_db_facade", fake_call_db_facade)
    client = _client(tmp_path, monkeypatch)

    status = client.get("/v1/desktop/trade-predictions/status?strategy_id=s1")
    outcomes = client.get("/v1/desktop/trade-predictions/outcomes?score_version=trade_prediction_score_v2")
    matrix = client.get("/v1/desktop/trade-predictions/matrix?dimensions=family")

    assert status.status_code == 200
    assert status.json()["success"] is True
    assert status.json()["data"]["object"] == "trade_prediction.status"
    assert outcomes.status_code == 200
    assert outcomes.json()["data"]["items"][0]["score_version"] == "trade_prediction_score_v2"
    assert matrix.status_code == 200
    assert matrix.json()["data"]["rows"][0]["dimension"] == "family"


def test_desktop_stock_radar_routes_use_agent_read_facades(tmp_path, monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_stock_radar_facade(loader, params=None):
        payload = dict(params or {})
        loader_name = getattr(loader, "__name__", "")
        calls.append((loader_name, payload))
        if loader_name == "_load_status_handler":
            return {
                "success": True,
                "data": {"object": "stock_radar.status", "status": "completed", "latest_run": {"run_id": payload.get("run_id")}},
                "error": None,
                "meta": {"side_effect": {"level": "read_only"}},
            }
        if loader_name == "_load_candidates_handler":
            return {
                "success": True,
                "data": {
                    "object": "stock_radar.candidates",
                    "candidates": [{"symbol": payload.get("symbol"), "tier": payload.get("tier")}],
                    "count": 1,
                },
                "error": None,
                "meta": {"side_effect": {"level": "read_only"}},
            }
        if loader_name == "_load_digest_handler":
            return {
                "success": True,
                "data": {"object": "stock_radar.digest", "channels": payload.get("channels"), "digest_preview": "preview"},
                "error": None,
                "meta": {"side_effect": {"level": "read_only"}},
            }
        raise AssertionError(loader_name)

    monkeypatch.setattr("aiask_agent.adapters.stock_radar._call_db_handler", fake_stock_radar_facade)
    client = _client(tmp_path, monkeypatch)

    status = client.get("/v1/desktop/stock-radar/status?run_id=radar_1&limit=5")
    candidates = client.get("/v1/desktop/stock-radar/candidates?run_id=radar_1&tier=alert&symbol=600000&min_score=80&limit=3")
    digest = client.get("/v1/desktop/stock-radar/digest?run_id=radar_1&channels=wecom,telegram")

    assert status.status_code == 200
    assert status.json()["success"] is True
    assert candidates.status_code == 200
    assert candidates.json()["data"]["candidates"] == [{"symbol": "600000", "tier": "alert"}]
    assert digest.status_code == 200
    assert digest.json()["data"]["channels"] == ["wecom", "telegram"]
    assert calls == [
        ("_load_status_handler", {"run_id": "radar_1", "limit": 5}),
        ("_load_candidates_handler", {"run_id": "radar_1", "tier": "alert", "symbol": "600000", "min_score": 80.0, "limit": 3}),
        ("_load_digest_handler", {"run_id": "radar_1", "limit": 20, "channels": ["wecom", "telegram"]}),
    ]
