"""HTTP auth and transport-security contract tests."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "strategy-factory" / "src"))


HTTP_ENV_KEYS = [
    "MCP_TRANSPORT",
    "MCP_HOST",
    "MCP_PORT",
    "MCP_ALLOWED_ORIGINS",
    "MCP_ALLOWED_HOSTS",
    "MCP_AUTH_MODE",
    "MCP_AUTH_TOKEN",
    "MCP_AUTH_TOKENS_JSON",
    "MCP_AUTH_CLIENT_ID",
    "MCP_AUTH_REQUIRED_SCOPES",
    "MCP_AUTH_DEFAULT_SCOPES",
    "MCP_AUTH_ISSUER_URL",
    "MCP_RESOURCE_SERVER_URL",
    "MCP_PUBLIC_SCHEME",
    "MCP_PUBLIC_HOST",
    "MCP_PUBLIC_PORT",
    "MCP_API_KEY",
    "MCP_API_KEYS_JSON",
]


def _reload_server(monkeypatch: pytest.MonkeyPatch, **env_overrides):
    for key in HTTP_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, str(value))

    import akshare_mcp.server as server_mod

    return importlib.reload(server_mod)


def _request_headers(origin: str, *, authorization: str | None = None, api_key: str | None = None) -> dict[str, str]:
    headers = {
        "host": "127.0.0.1:8765",
        "origin": origin,
    }
    if authorization:
        headers["authorization"] = authorization
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def test_streamable_http_should_reject_requests_without_token(monkeypatch: pytest.MonkeyPatch):
    server_mod = _reload_server(
        monkeypatch,
        MCP_TRANSPORT="streamable-http",
        MCP_HOST="127.0.0.1",
        MCP_PORT="8765",
        MCP_ALLOWED_ORIGINS="http://localhost:3000",
        MCP_ALLOWED_HOSTS="127.0.0.1:8765,testserver",
        MCP_AUTH_MODE="bearer",
        MCP_AUTH_TOKEN="test-token",
        MCP_AUTH_CLIENT_ID="user_http",
        MCP_AUTH_REQUIRED_SCOPES="mcp",
        MCP_AUTH_DEFAULT_SCOPES="mcp",
    )
    app = server_mod._build_http_asgi_app("streamable-http", None)
    with TestClient(app) as client:
        response = client.post("/mcp", headers=_request_headers("http://localhost:3000"), json={})
    assert response.status_code == 401


def test_streamable_http_should_reject_disallowed_origin(monkeypatch: pytest.MonkeyPatch):
    server_mod = _reload_server(
        monkeypatch,
        MCP_TRANSPORT="streamable-http",
        MCP_HOST="127.0.0.1",
        MCP_PORT="8765",
        MCP_ALLOWED_ORIGINS="http://localhost:3000",
        MCP_ALLOWED_HOSTS="127.0.0.1:8765,testserver",
        MCP_AUTH_MODE="bearer",
        MCP_AUTH_TOKEN="test-token",
        MCP_AUTH_CLIENT_ID="user_http",
        MCP_AUTH_REQUIRED_SCOPES="mcp",
        MCP_AUTH_DEFAULT_SCOPES="mcp",
    )
    app = server_mod._build_http_asgi_app("streamable-http", None)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers=_request_headers("http://evil.example", authorization="Bearer test-token"),
            json={},
        )
    assert response.status_code == 403


def test_streamable_http_should_accept_valid_bearer_token(monkeypatch: pytest.MonkeyPatch):
    server_mod = _reload_server(
        monkeypatch,
        MCP_TRANSPORT="streamable-http",
        MCP_HOST="127.0.0.1",
        MCP_PORT="8765",
        MCP_ALLOWED_ORIGINS="http://localhost:3000",
        MCP_ALLOWED_HOSTS="127.0.0.1:8765,testserver",
        MCP_AUTH_MODE="bearer",
        MCP_AUTH_TOKEN="test-token",
        MCP_AUTH_CLIENT_ID="user_http",
        MCP_AUTH_REQUIRED_SCOPES="mcp",
        MCP_AUTH_DEFAULT_SCOPES="mcp",
    )
    app = server_mod._build_http_asgi_app("streamable-http", None)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers=_request_headers("http://localhost:3000", authorization="Bearer test-token"),
            json={},
        )
    assert response.status_code not in {401, 403, 421}


def test_streamable_http_should_accept_x_api_key_when_api_key_mode_enabled(monkeypatch: pytest.MonkeyPatch):
    server_mod = _reload_server(
        monkeypatch,
        MCP_TRANSPORT="streamable-http",
        MCP_HOST="127.0.0.1",
        MCP_PORT="8765",
        MCP_ALLOWED_ORIGINS="http://localhost:3000",
        MCP_ALLOWED_HOSTS="127.0.0.1:8765,testserver",
        MCP_AUTH_MODE="api-key",
        MCP_API_KEY="api-key-123",
        MCP_AUTH_CLIENT_ID="user_http",
        MCP_AUTH_REQUIRED_SCOPES="mcp",
        MCP_AUTH_DEFAULT_SCOPES="mcp",
    )
    app = server_mod._build_http_asgi_app("streamable-http", None)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers=_request_headers("http://localhost:3000", api_key="api-key-123"),
            json={},
        )
    assert response.status_code not in {401, 403, 421}
