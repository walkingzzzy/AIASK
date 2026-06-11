from __future__ import annotations

import argparse
import asyncio
import importlib.util
import ipaddress
import json
import os
import shutil
import sys
import time
from contextlib import asynccontextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .approvals import ApprovalStore
from .acp import ACPManager
from .capabilities import HERMES_BASELINE, parity_summary
from .env_config import load_project_env, project_env_status
from .gateway import ADAPTERS, DeliveryRouter, GatewayChannelDirectoryStore, GatewayConfigStore, GatewayMessageStore, GatewayRuntime, adapter_for, normalize_platform
from .financial_readiness import financial_system_readiness
from .json_utils import dumps_json_bytes
from .learning_loop import LearningLoop
from .intents import ActionIntentStore, IntentExecutor
from .mcp_client import MCPAggregator
from .memory_providers import MemoryProviderManager
from .model_client import MockModelClient, _openai_compatible_api_base
from .model_providers import ModelProviderRegistry, ProviderUsageStore
from .plugin_runtime import NativePluginManager
from .process_registry import ProcessRegistry
from .quant_research import QuantResearchStore
from .rl_atropos import RLAtroposManager
from .security import SecurityScanner
from .runtime import AgentRuntime
from .routes.tools_catalog import build_tool_catalog_payload
from .session_store import AgentSessionStore
from .skill_packs import SkillPackManager
from .native_capabilities import SkillStore
from .terminal_backends import list_backends, sessions as terminal_backend_sessions
from .tui import status as tui_status_payload
from .tool_registry import SAFE_TOOL_CATALOG, build_default_tool_registry
from .tool_risk import metadata_is_read_only
from .tools.policy import GENERAL_FULL_TOOLSET, ToolPolicy, ToolPolicyEngine
from .webhooks import WebhookStore
from .paths import aiask_agent_home, default_intent_db_path, default_quant_research_db_path
from .adapters import quant as quant_adapter
from .adapters.desktop_ops import factor_factory_status


def _load_local_env_file() -> None:
    """Load a repo-local .env for CLI/dev launches without overriding the process env."""
    load_project_env()


def _json_dumps(payload: Any) -> bytes:
    return dumps_json_bytes(payload, ensure_ascii=False, sort_keys=True)


def _query_bool(query: dict[str, list[str]], key: str, *, default: bool = False) -> bool:
    values = query.get(key)
    if not values:
        return default
    value = str(values[-1] or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _exception_messages(exc: BaseException) -> list[str]:
    messages = [str(exc)] if str(exc) else [exc.__class__.__name__]
    nested = getattr(exc, "exceptions", None)
    if isinstance(nested, (list, tuple)):
        for item in nested:
            if isinstance(item, BaseException):
                messages.extend(_exception_messages(item))
            else:
                messages.append(str(item))
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, BaseException):
        messages.extend(_exception_messages(cause))
    return [message for index, message in enumerate(messages) if message and message not in messages[:index]]


def _classify_mcp_error(exc: BaseException) -> tuple[str, str]:
    messages = _exception_messages(exc)
    detail = "; ".join(messages)
    lowered = detail.lower()
    if (
        "401" in lowered
        or "unauthorized" in lowered
        or "authentication required" in lowered
        or "invalid_token" in lowered
        or "bearer token env" in lowered
    ):
        return "MCP_DISCOVERY_AUTH_REQUIRED", detail
    if "oauth" in lowered:
        return "MCP_DISCOVERY_OAUTH_REQUIRED", detail
    if "connection" in lowered or "connect" in lowered or "refused" in lowered:
        return "MCP_DISCOVERY_CONNECTION_FAILED", detail
    return "MCP_DISCOVERY_FAILED", detail


def _mcp_action_error_payload(*, action: str, server_name: str, exc: BaseException) -> dict[str, Any]:
    error_code, detail = _classify_mcp_error(exc)
    auth: dict[str, Any] = {}
    if server_name:
        try:
            auth = MCPAggregator().auth_readiness(server_name)
        except Exception:
            auth = {}
    return {
        "object": f"mcp.{action}",
        "success": False,
        "data": {
            "server": server_name or None,
            "configured": False,
            "status": "failed",
            "detail": detail,
            **auth,
        },
        "error": detail,
        "error_code": error_code,
    }


def _plugin_tools(plugin: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in list(plugin.get("tools") or []) if isinstance(item, dict) and item.get("name")]


def _plugin_self_test_payload(plugin: dict[str, Any], name: str) -> dict[str, Any]:
    tools = _plugin_tools(plugin)
    commands = [dict(item) for item in list(plugin.get("commands") or []) if isinstance(item, dict) and item.get("name")]
    return {
        "object": "plugin.tool_test",
        "success": True,
        "data": {
            "plugin": str(plugin.get("name") or name),
            "test_type": "manifest",
            "enabled": bool(plugin.get("enabled")),
            "manifest_valid": True,
            "tools_count": len(tools),
            "commands_count": len(commands),
            "hooks_count": len(list(plugin.get("hooks") or [])),
            "available_tools": [str(item.get("name") or "") for item in tools],
            "available_commands": [str(item.get("name") or "") for item in commands],
            "note": "plugin manifest is readable; no executable tool runner is required for this self-test",
        },
        "error": None,
    }


def _redact_required_env(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            redacted[key] = ["redacted"] if key == "required_env" and isinstance(value, list) else _redact_required_env(value)
        return redacted
    if isinstance(payload, list):
        return [_redact_required_env(item) for item in payload]
    return payload


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid JSON request body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON request body must be an object")
    return parsed


def _extract_bearer_token(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _header_token(handler: BaseHTTPRequestHandler, *names: str) -> str | None:
    for name in names:
        value = _extract_bearer_token(handler.headers.get(name))
        if value:
            return value
    return _extract_bearer_token(handler.headers.get("Authorization"))


def _is_loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except Exception:
        return value in {"localhost", "testclient"}


def _cors_origins() -> set[str]:
    configured = str(os.getenv("AIASK_AGENT_CORS_ORIGINS", "")).strip()
    defaults = {
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "tauri://localhost",
    }
    values = defaults if not configured else set()
    for item in configured.split(","):
        origin = item.strip().rstrip("/")
        if origin and origin != "*":
            values.add(origin)
    return values


def _is_read_only_desktop_tool(name: str) -> bool:
    if name == "agent_tool_catalog":
        return True
    for item in SAFE_TOOL_CATALOG:
        if item.get("name") == name:
            return item.get("side_effect") == "read_only"
    return False


def _metadata_allows_read_only_desktop_call(metadata: dict[str, Any], tool_name: str) -> bool:
    return metadata_is_read_only(metadata, target=tool_name)


def _messages_from_responses_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("messages"), list):
        return [dict(item) for item in payload["messages"] if isinstance(item, dict)]
    raw_input = payload.get("input", "")
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    if isinstance(raw_input, list):
        messages: list[dict[str, Any]] = []
        for item in raw_input:
            if isinstance(item, dict) and item.get("role"):
                messages.append({"role": item.get("role"), "content": item.get("content", "")})
            elif isinstance(item, str):
                messages.append({"role": "user", "content": item})
        return messages
    return []


def _chat_completion_payload(result: Any, *, model: str) -> dict[str, Any]:
    return {
        "id": result.response_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": result.usage,
        "aiask": {
            "session_id": result.session_id,
            "run_id": result.run_id,
            "tool_calls": result.tool_calls,
            "audit_events": result.audit_events,
            "events": result.events,
            "context_summary_id": result.context_summary_id,
            "planner_steps": result.planner_steps,
            "subruns": result.subruns,
        },
    }


def _responses_payload(result: Any, *, model: str) -> dict[str, Any]:
    return {
        "id": result.response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output_text": result.content,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": result.content}],
            }
        ],
        "usage": result.usage,
        "metadata": {
            "session_id": result.session_id,
            "run_id": result.run_id,
            "tool_calls": result.tool_calls,
            "audit_events": result.audit_events,
            "events": result.events,
            "context_summary_id": result.context_summary_id,
            "planner_steps": result.planner_steps,
            "subruns": result.subruns,
        },
    }


def _local_profile_path() -> Path:
    return aiask_agent_home() / "local_profile.json"


def _default_local_profile() -> dict[str, Any]:
    return {
        "object": "aiask.local_profile",
        "user_id": "local",
        "profile_name": "Local Operator",
        "storage": "local_file",
        "path": str(_local_profile_path()),
        "updated_at": None,
        "secrets_redacted": True,
    }


def local_profile_payload() -> dict[str, Any]:
    profile = _default_local_profile()
    path = _local_profile_path()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in ("user_id", "profile_name", "updated_at"):
                    if loaded.get(key):
                        profile[key] = str(loaded[key])
    except Exception as exc:
        profile["status"] = "degraded"
        profile["error"] = str(exc)
    profile.setdefault("status", "ready")
    return profile


def save_local_profile(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    current = local_profile_payload()
    update = dict(payload or {})
    user_id = str(update.get("user_id") or current.get("user_id") or "local").strip() or "local"
    profile_name = str(update.get("profile_name") or current.get("profile_name") or "Local Operator").strip() or "Local Operator"
    saved = {
        "object": "aiask.local_profile",
        "user_id": user_id,
        "profile_name": profile_name,
        "storage": "local_file",
        "path": str(_local_profile_path()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "secrets_redacted": True,
        "status": "ready",
    }
    path = _local_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    return saved


def _hermes_full_enabled() -> bool:
    return str(os.getenv("AIASK_AGENT_ENABLE_HERMES_FULL", "")).strip().lower() in {"1", "true", "yes", "on"}


def _build_runtime_and_executor() -> tuple[AgentRuntime, IntentExecutor]:
    session_store = AgentSessionStore()
    intent_store = ActionIntentStore()
    registry = build_default_tool_registry(intent_store, session_store=session_store)
    return AgentRuntime(session_store=session_store, tool_registry=registry), IntentExecutor(intent_store)


def _mode_error_status(reason: str | None) -> int:
    return 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401


def _control_token_configured() -> bool:
    return bool(
        str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
        or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
    )


def _agent_endpoint(default: str = "http://127.0.0.1:8767") -> str:
    host = str(os.getenv("AIASK_AGENT_HOST", "")).strip()
    port = str(os.getenv("AIASK_AGENT_PORT", "")).strip()
    if host and port:
        return f"http://{host}:{port}"
    return default


def _ai_status_payload_for_runtime(runtime: AgentRuntime) -> dict[str, Any]:
    load_project_env()
    provider_registry = ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path))
    provider_payload = provider_registry.status()
    active_provider = str(provider_payload.get("active_provider") or "").strip().lower()
    providers = list(provider_registry.providers())
    active_spec = next((item for item in providers if item.name == active_provider), None)
    provider = str(os.getenv("AIASK_AGENT_MODEL_PROVIDER", "")).strip().lower()
    api_key_configured = bool(
        str(os.getenv("OPENAI_API_KEY", "")).strip()
        or str(os.getenv("OPENAI_API_KEYS", "")).strip()
        or (active_spec is not None and active_spec.provider_type != "mock" and active_spec.configured)
    )
    base_url = str(os.getenv("OPENAI_BASE_URL", "")).strip()
    model = str(provider_payload.get("default_model") or os.getenv("AIASK_AGENT_MODEL", runtime.model)).strip() or runtime.model
    runtime_client = runtime.model_client
    runtime_client_name = runtime_client.__class__.__name__
    effective_provider = provider or active_provider or ("openai" if api_key_configured else "mock")
    is_mock = effective_provider == "mock" or (not provider and isinstance(runtime_client, MockModelClient))
    configured = bool(active_spec.configured if active_spec is not None else is_mock or api_key_configured)
    return {
        "object": "aiask.ai_status",
        "provider": effective_provider,
        "model": model,
        "base_url_configured": bool(base_url),
        "base_url": base_url if base_url else None,
        "api_key_configured": api_key_configured,
        "mock": is_mock,
        "configured": configured,
        "runtime_client": runtime_client_name,
        "config_source": project_env_status(),
        "secrets_redacted": True,
    }


def _ai_error_payload(exc: BaseException, *, configured: bool = True) -> dict[str, Any]:
    name = exc.__class__.__name__
    message = str(exc)
    lowered = message.lower()
    if "401" in message or "unauthorized" in lowered or "api key" in lowered:
        code = "AUTH_FAILED"
    elif "timeout" in lowered:
        code = "TIMEOUT"
    elif "connection" in lowered or "connect" in lowered or "refused" in lowered:
        code = "NETWORK_ERROR"
    else:
        code = "AI_SMOKE_FAILED"
    return {
        "object": "aiask.ai_smoke",
        "configured": configured,
        "success": False,
        "error_code": code,
        "error": f"{name}: {message}",
        "secrets_redacted": True,
    }


async def _ai_smoke_payload_for_runtime(runtime: AgentRuntime, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    status = _ai_status_payload_for_runtime(runtime)
    if not status["configured"]:
        return {
            "object": "aiask.ai_smoke",
            "configured": False,
            "success": False,
            "model": status["model"],
            "provider": status["provider"],
            "error_code": "AI_MODEL_UNCONFIGURED",
            "error": "No mock provider or OpenAI-compatible API key is configured.",
            "secrets_redacted": True,
        }
    request_payload = dict(payload or {})
    prompt = str(request_payload.get("prompt") or "Reply with AIASK model smoke ok.").strip()
    model = str(request_payload.get("model") or status["model"] or runtime.model).strip()
    started = time.perf_counter()
    try:
        response = await runtime.model_client.complete(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            model=model,
        )
    except Exception as exc:
        result = _ai_error_payload(exc, configured=bool(status["configured"]))
        result.update({"model": model, "provider": status["provider"], "latency_ms": int((time.perf_counter() - started) * 1000)})
        return result
    return {
        "object": "aiask.ai_smoke",
        "configured": True,
        "success": True,
        "provider": status["provider"],
        "mock": status["mock"],
        "model": model,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "response_preview": str(response.content or "")[:300],
        "usage": response.usage,
        "tool_call_count": len(response.tool_calls),
        "secrets_redacted": True,
    }


async def _ai_models_payload_for_runtime(runtime: AgentRuntime) -> dict[str, Any]:
    load_project_env()
    status = _ai_status_payload_for_runtime(runtime)

    def fallback_model_list(error_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "object": "list",
            "configured": True,
            "provider": status["provider"],
            "unsupported": True,
            "data": [
                {
                    "id": status["model"],
                    "owned_by": status["provider"],
                    "fallback": True,
                }
            ],
            "warning_code": error_payload.get("error_code"),
            "warning": error_payload.get("error"),
            "message": "Provider model listing is not standard; showing the configured runtime model.",
            "secrets_redacted": True,
        }

    if status["mock"]:
        return {
            "object": "list",
            "configured": True,
            "provider": "mock",
            "unsupported": True,
            "data": [{"id": status["model"], "owned_by": "aiask_mock"}],
            "message": "Mock provider exposes the configured runtime model only.",
        }
    if not status["api_key_configured"]:
        return {
            "object": "list",
            "configured": False,
            "provider": status["provider"],
            "unsupported": False,
            "data": [],
            "error_code": "AI_MODEL_UNCONFIGURED",
            "error": "OPENAI_API_KEY is not configured.",
        }
    if str(status.get("provider") or "").strip().lower() in {"anthropic", "anthropic_messages"}:
        try:
            import httpx

            base_url = str(os.getenv("OPENAI_BASE_URL", "")).strip().rstrip("/")
            if not base_url:
                base_url = "https://api.anthropic.com/v1"
            elif base_url.lower().endswith("/messages"):
                base_url = base_url.rsplit("/", 1)[0]
            elif not base_url.lower().endswith("/v1") and not base_url.lower().endswith("/models"):
                base_url = f"{base_url}/v1"
            url = base_url if base_url.lower().endswith("/models") else f"{base_url}/models"
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {str(os.getenv('OPENAI_API_KEY', '')).strip()}"})
                response.raise_for_status()
                body = response.json()
            data = list((body or {}).get("data") or []) if isinstance(body, dict) else []
            return {"object": "list", "configured": True, "provider": status["provider"], "unsupported": False, "data": data}
        except Exception as exc:
            result = _ai_error_payload(exc, configured=True)
            return fallback_model_list(result)
    client = None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=str(os.getenv("OPENAI_API_KEY", "")).strip(),
            base_url=_openai_compatible_api_base(str(os.getenv("OPENAI_BASE_URL", "")).strip() or None),
        )
        response = await client.models.list()
        data = []
        for item in list(getattr(response, "data", []) or []):
            if hasattr(item, "model_dump"):
                data.append(item.model_dump())
            elif isinstance(item, dict):
                data.append(dict(item))
            else:
                data.append({"id": str(getattr(item, "id", item))})
        return {"object": "list", "configured": True, "provider": status["provider"], "unsupported": False, "data": data}
    except Exception as exc:
        result = _ai_error_payload(exc, configured=True)
        return fallback_model_list(result)
    finally:
        if client is not None:
            closer = getattr(client, "close", None)
            if callable(closer):
                closed = closer()
                if hasattr(closed, "__await__"):
                    await closed


def _desktop_settings_status_payload_for_runtime(
    runtime: AgentRuntime,
    *,
    endpoint: str | None = None,
    control_authorized: bool = False,
    control_reason: str | None = None,
) -> dict[str, Any]:
    quant_db = quant_adapter.database_status()
    return {
        "object": "aiask.desktop_settings_status",
        "agent": {
            "endpoint": endpoint or _agent_endpoint(),
            "api_token_configured": bool(str(os.getenv("AIASK_AGENT_API_TOKEN", "")).strip()),
            "control_token_configured": _control_token_configured(),
            "control_authorized": bool(control_authorized),
            "control_reason": None if control_authorized else control_reason,
            "toolset": runtime.tool_registry.policy_engine.toolset,
            "model": runtime.model,
            "max_iterations": runtime.max_iterations,
        },
        "llm": {
            "ai_status": _ai_status_payload_for_runtime(runtime),
            "providers": ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path)).status(),
        },
        "memory": MemoryProviderManager(path=runtime.session_store.path).status(),
        "databases": {
            "agent_state": {
                "backend": "sqlite",
                "path": str(runtime.session_store.path),
                "configured": True,
                "writable": True,
            },
            "intent_state": {
                "backend": "sqlite",
                "path": str(default_intent_db_path()),
                "configured": True,
            },
            "quant_research": {
                "backend": "sqlite",
                "path": str(default_quant_research_db_path()),
                "configured": True,
            },
            "akshare": quant_db,
        },
        "profile": local_profile_payload(),
        "secrets_redacted": True,
    }


async def _desktop_data_status_payload_for_runtime(
    runtime: AgentRuntime,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(arguments or {})
    presets = quant_adapter.quant_presets()
    templates = list(presets.get("templates") or [])
    default_codes = list((templates[0] if templates else {}).get("universe") or [])
    if "codes" in payload:
        raw_codes = payload.get("codes")
    elif "universe" in payload:
        raw_codes = payload.get("universe")
    else:
        raw_codes = default_codes
    if isinstance(raw_codes, str):
        codes = [item.strip() for item in raw_codes.replace("\n", ",").split(",") if item.strip()]
    else:
        codes = [str(item).strip() for item in list(raw_codes or []) if str(item).strip()]
    max_stale_days = int(payload.get("max_stale_days") or 5)
    gate = await runtime.tool_registry.call_tool("agent_quant_data_gate", {"codes": codes, "max_stale_days": max_stale_days})
    gate_data = gate.get("data") if isinstance(gate.get("data"), dict) else {}
    coverage = dict(gate_data.get("coverage") or {})
    return {
        "object": "aiask.desktop_data_status",
        "status": "ready" if gate_data.get("ready") else "blocked",
        "database": quant_adapter.database_status(),
        "presets": presets,
        "quality_gate": gate,
        "data_validation": None,
        "freshness": gate_data.get("freshness"),
        "codes": codes,
        "max_stale_days": max_stale_days,
        "missing_count": int(coverage.get("missing_count") or 0),
        "stale_count": int(coverage.get("stale_count") or 0),
        "secrets_redacted": True,
    }


async def _desktop_data_sync_plan_payload_for_runtime(
    runtime: AgentRuntime,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(arguments or {})
    data_status = await _desktop_data_status_payload_for_runtime(runtime, payload)
    codes = data_status.get("codes") or []
    task_type = str(payload.get("task_type") or payload.get("type") or "kline").strip() or "kline"
    period = str(payload.get("period") or "daily").strip() or "daily"
    no_code_task_types = {
        "core_market",
        "factor_context",
        "market_temperature_snapshot_cache",
        "market_text_source_ingest",
        "vector_backfill_market_docs",
        "vector_backfill_kline_patterns",
        "vector_backfill_stock_profiles",
        "vector_backfill_factor_candidates",
        "factor_external_research_ingest",
        "vector_build_snapshot",
        "vector_benchmark_collection",
        "vector_optimize_bootstrap",
        "factor_validation_bootstrap",
    }
    intent_params = {
        "task_type": task_type,
        "codes": codes,
        "period": period,
        "priority": payload.get("priority") or "normal",
        "force": bool(payload.get("force", False)),
    }
    if task_type == "market_temperature_snapshot_cache":
        intent_params.update(
            {
                "limit": max(1, min(int(payload.get("limit") or 1000), 1000)),
                "top_n": max(0, min(int(payload.get("top_n") or 20), 50)),
                "min_bars": max(2, min(int(payload.get("min_bars") or 20), 120)),
            }
        )
        if payload.get("as_of"):
            intent_params["as_of"] = str(payload.get("as_of")).strip()
    plan_ready = bool(codes) or task_type in no_code_task_types
    rationale = (
        f"Sync {task_type} data from Desktop."
        if task_type in no_code_task_types and not codes
        else f"Sync {task_type} data for {len(codes)} codes from Desktop."
    )
    return {
        "object": "aiask.desktop_data_sync_plan",
        "status": "ready" if plan_ready else "needs_codes",
        "data_status": data_status,
        "intent_request": {
            "action": "data_sync.sync",
            "params": intent_params,
            "rationale": rationale,
        },
        "commands": [
            {"label": "Create approval intent", "method": "POST", "path": "/intents"},
            {"label": "Confirm after review", "method": "POST", "path": "/intents/{intent_id}/confirm"},
        ],
        "side_effect": {"level": "stateful", "confirmation_required": True, "target": "data_sync.sync"},
        "secrets_redacted": True,
    }


FINANCIAL_MANAGER_GROUPS: tuple[dict[str, str], ...] = (
    {"id": "overview", "label": "Overview", "description": "Readiness, manager coverage, and recent operating context."},
    {"id": "market-research", "label": "Market & Research", "description": "Stock analysis, research, sector, sentiment, technical, options, and trading-data reads."},
    {"id": "portfolio-watchlist", "label": "Portfolio & Watchlist", "description": "Portfolio, holdings, and watchlist reads plus intent-only mutations."},
    {"id": "risk-performance", "label": "Risk & Performance", "description": "Portfolio risk, VaR, exposure, stress, attribution, and benchmark comparison."},
    {"id": "quant-backtest", "label": "Quant & Backtest", "description": "Quant research, data gates, and backtest suite operations."},
    {"id": "paper-execution", "label": "Paper & Execution Planning", "description": "Paper trading and execution plan reads plus intent-only task changes."},
    {"id": "broker-readonly", "label": "Broker Read-only", "description": "THS/QMT account, position, order, and deal queries without live order placement."},
)

FINANCIAL_MANAGER_ACTIONS: tuple[dict[str, Any], ...] = (
    {"capability_id": "stock-analysis", "action_id": "analyze_stock", "group": "market-research", "label": "Analyze stock", "mode": "read_only", "tool": "agent_analyze_stock", "default_params": {"code": "600519", "include_decision": False}},
    {"capability_id": "research", "action_id": "reports", "group": "market-research", "label": "Research reports", "mode": "read_only", "mcp_tool": "research_manager", "mcp_action": "get_reports", "default_params": {"code": "600519", "limit": 5}},
    {"capability_id": "sector", "action_id": "sector_performance", "group": "market-research", "label": "Sector performance", "mode": "read_only", "mcp_tool": "sector_manager", "mcp_action": "sector_performance", "default_params": {"limit": 10}},
    {"capability_id": "sentiment", "action_id": "market_sentiment", "group": "market-research", "label": "Market sentiment", "mode": "read_only", "mcp_tool": "sentiment_manager", "mcp_action": "market_sentiment", "default_params": {}},
    {"capability_id": "technical", "action_id": "calculate", "group": "market-research", "label": "Technical indicators", "mode": "read_only", "mcp_tool": "technical_analysis_manager", "mcp_action": "calculate", "default_params": {"code": "600519", "indicators": ["ma", "rsi"]}},
    {"capability_id": "options", "action_id": "calculate_greeks", "group": "market-research", "label": "Option Greeks", "mode": "read_only", "mcp_tool": "options_manager", "mcp_action": "calculate_greeks", "default_params": {}},
    {"capability_id": "trading-data", "action_id": "dragon_tiger", "group": "market-research", "label": "Dragon tiger list", "mode": "read_only", "mcp_tool": "trading_data_manager", "mcp_action": "dragon_tiger", "default_params": {"limit": 20}},
    {"capability_id": "screener", "action_id": "screen", "group": "market-research", "label": "Stock screener", "mode": "read_only", "mcp_tool": "screener_manager", "mcp_action": "screen", "default_params": {"limit": 20}},
    {"capability_id": "portfolio", "action_id": "risk", "group": "risk-performance", "label": "Portfolio risk", "mode": "read_only", "tool": "agent_portfolio_risk", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "portfolio", "action_id": "list", "group": "portfolio-watchlist", "label": "Portfolio list", "mode": "read_only", "mcp_tool": "portfolio_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "portfolio", "action_id": "get_holdings", "group": "portfolio-watchlist", "label": "Portfolio holdings", "mode": "read_only", "mcp_tool": "portfolio_manager", "mcp_action": "get_holdings", "default_params": {"portfolio_id": 1}},
    {"capability_id": "portfolio", "action_id": "create", "group": "portfolio-watchlist", "label": "Create portfolio intent", "mode": "stateful_intent", "intent_action": "portfolio_manager.create", "default_params": {"name": "Desktop portfolio"}},
    {"capability_id": "portfolio", "action_id": "add_holding", "group": "portfolio-watchlist", "label": "Add holding intent", "mode": "stateful_intent", "intent_action": "portfolio_manager.add_holding", "default_params": {"portfolio_id": 1, "code": "600519", "shares": 100, "cost_price": 1800}},
    {"capability_id": "watchlist", "action_id": "list", "group": "portfolio-watchlist", "label": "Watchlist groups", "mode": "read_only", "mcp_tool": "watchlist_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "watchlist", "action_id": "add", "group": "portfolio-watchlist", "label": "Add watchlist stock intent", "mode": "stateful_intent", "intent_action": "watchlist_manager.add", "default_params": {"group": "default", "code": "600519"}},
    {"capability_id": "watchlist", "action_id": "remove", "group": "portfolio-watchlist", "label": "Remove watchlist stock intent", "mode": "stateful_intent", "intent_action": "watchlist_manager.remove", "default_params": {"group": "default", "code": "600519"}},
    {"capability_id": "risk", "action_id": "var", "group": "risk-performance", "label": "Risk VaR", "mode": "read_only", "mcp_tool": "risk_manager", "mcp_action": "var", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "risk", "action_id": "exposure", "group": "risk-performance", "label": "Risk exposure", "mode": "read_only", "mcp_tool": "risk_manager", "mcp_action": "exposure", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "performance", "action_id": "calculate_metrics", "group": "risk-performance", "label": "Performance metrics", "mode": "read_only", "mcp_tool": "performance_manager", "mcp_action": "calculate_metrics", "default_params": {"portfolio_id": 1}},
    {"capability_id": "decision", "action_id": "portfolio_advice", "group": "risk-performance", "label": "Portfolio advice", "mode": "read_only", "mcp_tool": "decision_manager", "mcp_action": "portfolio_advice", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "quant", "action_id": "data_gate", "group": "quant-backtest", "label": "Quant data gate", "mode": "read_only", "tool": "agent_quant_data_gate", "default_params": {"codes": ["600519", "000001"], "max_stale_days": 5}},
    {"capability_id": "quant", "action_id": "research_run", "group": "quant-backtest", "label": "Quant research run", "mode": "read_only", "tool": "agent_quant_research_run", "default_params": {"universe": ["600519", "000001"], "factors": ["momentum"], "benchmark": "000300"}},
    {"capability_id": "backtest", "action_id": "suite", "group": "quant-backtest", "label": "Backtest suite", "mode": "read_only", "tool": "agent_backtest_suite", "default_params": {"codes": ["600519", "000001"], "strategy": "ma_cross"}},
    {"capability_id": "backtest", "action_id": "list", "group": "quant-backtest", "label": "Saved backtests", "mode": "read_only", "mcp_tool": "backtest_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "paper", "action_id": "status", "group": "paper-execution", "label": "Paper trading status", "mode": "read_only", "mcp_tool": "paper_trading_manager", "mcp_action": "summary", "default_params": {}},
    {"capability_id": "paper", "action_id": "orders", "group": "paper-execution", "label": "Paper orders", "mode": "read_only", "mcp_tool": "paper_trading_manager", "mcp_action": "orders", "default_params": {"limit": 20}},
    {"capability_id": "paper", "action_id": "submit_order", "group": "paper-execution", "label": "Paper order intent", "mode": "stateful_intent", "intent_action": "paper_trading_manager.submit_order", "default_params": {"code": "600519", "side": "buy", "quantity": 100, "dry_run": True}},
    {"capability_id": "execution", "action_id": "plan", "group": "paper-execution", "label": "Execution tasks", "mode": "read_only", "mcp_tool": "execution_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "execution", "action_id": "create_plan", "group": "paper-execution", "label": "Create execution plan intent", "mode": "stateful_intent", "intent_action": "execution_manager.create_plan", "default_params": {"code": "600519", "side": "buy", "quantity": 1000, "dry_run": True}},
    {"capability_id": "broker-ths", "action_id": "positions", "group": "broker-readonly", "label": "THS positions", "mode": "read_only", "mcp_tool": "ths_query_position", "default_params": {}},
    {"capability_id": "broker-ths", "action_id": "orders", "group": "broker-readonly", "label": "THS orders", "mode": "read_only", "mcp_tool": "ths_query_orders", "default_params": {}},
    {"capability_id": "broker-qmt", "action_id": "account", "group": "broker-readonly", "label": "QMT account", "mode": "read_only", "mcp_tool": "qmt_query_account", "default_params": {}},
    {"capability_id": "broker-qmt", "action_id": "positions", "group": "broker-readonly", "label": "QMT positions", "mode": "read_only", "mcp_tool": "qmt_query_position", "default_params": {}},
    {"capability_id": "broker-live", "action_id": "place_order", "group": "broker-readonly", "label": "Live place order", "mode": "blocked", "blocked_reason": "Live broker order placement is disabled in Financial Manager V1."},
    {"capability_id": "broker-live", "action_id": "cancel_order", "group": "broker-readonly", "label": "Live cancel order", "mode": "blocked", "blocked_reason": "Live broker cancellation is disabled in Financial Manager V1."},
)

FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE: dict[str, dict[str, Any]] = {
    "watchlist_manager.add": {"execution_mode": "confirmed_execute"},
    "watchlist_manager.remove": {"execution_mode": "confirmed_execute"},
    "portfolio_manager.create": {"execution_mode": "confirmed_execute"},
    "portfolio_manager.add_holding": {"execution_mode": "confirmed_execute"},
    "execution_manager.create_plan": {
        "execution_mode": "confirmed_execute_dry_run_only",
        "dry_run_required": True,
    },
    "paper_trading_manager.submit_order": {
        "execution_mode": "confirmed_execute_dry_run_only",
        "dry_run_required": True,
    },
}

FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS: tuple[str, ...] = tuple(
    action_name
    for action_name, policy in FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.items()
    if bool(policy.get("dry_run_required"))
)


def _financial_action_key(capability_id: str, action_id: str) -> str:
    return f"{str(capability_id or '').strip()}::{str(action_id or '').strip()}"


def _financial_action_map() -> dict[str, dict[str, Any]]:
    return {
        _financial_action_key(str(item.get("capability_id") or ""), str(item.get("action_id") or "")): dict(item)
        for item in FINANCIAL_MANAGER_ACTIONS
    }


def _financial_execution_mode(action: dict[str, Any]) -> str:
    mode = str(action.get("mode") or "read_only")
    if mode == "blocked":
        return "blocked"
    if mode == "read_only":
        return "read_only"
    intent_action = str(action.get("intent_action") or "").strip()
    if intent_action and intent_action in FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE:
        return str(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE[intent_action]["execution_mode"])
    return "intent_only"


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "token", "api_key", "apikey", "password", "credential")):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = _redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _wrapped_mcp_lookup(runtime: AgentRuntime) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for name in runtime.tool_registry.names():
        if not name.startswith("agent_mcp_"):
            continue
        tool = runtime.tool_registry.get(name)
        metadata = dict(getattr(tool, "metadata", {}) or {}) if tool else {}
        side_effect = metadata.get("side_effect") if isinstance(metadata.get("side_effect"), dict) else {}
        target = str(side_effect.get("target") or "")
        for candidate in {name, target, target.split(".")[0]}:
            if candidate:
                lookup.setdefault(candidate, {"wrapped_name": name, "metadata": metadata})
        lowered = name.lower()
        for action in FINANCIAL_MANAGER_ACTIONS:
            raw_tool = str(action.get("mcp_tool") or "").lower()
            if raw_tool and lowered.endswith(raw_tool):
                lookup.setdefault(str(action.get("mcp_tool")), {"wrapped_name": name, "metadata": metadata})
    return lookup


def _financial_mcp_availability_detail(
    runtime: AgentRuntime,
    action: dict[str, Any],
    mcp_lookup: dict[str, dict[str, Any]],
    *,
    mcp_tools: list[dict[str, Any]] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    required = str(action.get("mcp_tool") or "").strip()
    if not required:
        return {}
    names = set(runtime.tool_registry.names())
    match = mcp_lookup.get(required)
    tools = list(mcp_tools or MCPAggregator().tools_summary(include_all=True))
    servers = list(mcp_servers or MCPAggregator().servers_summary(include_all=True))
    matching_tools = [
        {
            "server": item.get("server"),
            "name": item.get("name"),
            "wrapped_name": item.get("wrapped_name"),
            "domain": item.get("domain"),
        }
        for item in tools
        if str(item.get("name") or "") == required or str(item.get("wrapped_name") or "") == required
    ]
    financial_servers = [
        {
            "name": item.get("name"),
            "domain": item.get("domain"),
            "transport": item.get("transport"),
            "tools_count": len(list(item.get("tools") or [])),
        }
        for item in servers
        if str(item.get("domain") or "").lower() == "financial"
    ]
    reason_code = "agent_mcp_wrapped_tool_ready"
    if not match:
        if matching_tools:
            reason_code = "mcp_tool_discovered_but_agent_registry_not_refreshed"
        elif not financial_servers:
            reason_code = "no_financial_mcp_server_registered"
        else:
            reason_code = "mcp_tool_not_discovered"
    wrapped_name = str((match or {}).get("wrapped_name") or "")
    return {
        "required_mcp_tool": required,
        "required_mcp_action": action.get("mcp_action"),
        "reason_code": reason_code,
        "agent_registry_has_wrapped_tool": bool(wrapped_name and wrapped_name in names),
        "wrapped_tool": wrapped_name or None,
        "matching_configured_tools": matching_tools,
        "financial_servers": financial_servers,
    }


def _financial_tool_availability_detail(runtime: AgentRuntime, action: dict[str, Any]) -> dict[str, Any]:
    required = str(action.get("tool") or "").strip()
    if not required:
        return {}
    names = set(runtime.tool_registry.names())
    return {
        "required_tool": required,
        "reason_code": "agent_tool_ready" if required in names else "agent_tool_missing",
        "agent_registry_has_tool": required in names,
    }


def _financial_catalog_payload(runtime: AgentRuntime) -> dict[str, Any]:
    names = set(runtime.tool_registry.names())
    mcp_lookup = _wrapped_mcp_lookup(runtime)
    mcp = MCPAggregator()
    mcp_tools = mcp.tools_summary(include_all=True)
    mcp_servers = mcp.servers_summary(include_all=True)
    actions: list[dict[str, Any]] = []
    for raw in FINANCIAL_MANAGER_ACTIONS:
        item = dict(raw)
        mode = str(item.get("mode") or "read_only")
        item["execution_mode"] = _financial_execution_mode(item)
        item["available"] = False
        item["status"] = "unavailable"
        item["side_effect"] = {
            "level": "read_only" if mode == "read_only" else "stateful" if mode == "stateful_intent" else "trade_risk",
            "target": item.get("intent_action") or item.get("tool") or item.get("mcp_tool") or item.get("action_id"),
            "confirmation_required": mode != "read_only",
            "idempotent": mode == "read_only",
        }
        if mode == "blocked":
            item["status"] = "blocked"
            item["availability"] = {"reason_code": "blocked", "blocked_reason": item.get("blocked_reason")}
        elif item.get("tool"):
            item["available"] = str(item["tool"]) in names
            item["status"] = "ready" if item["available"] else "missing_tool"
            item["availability"] = _financial_tool_availability_detail(runtime, item)
        elif item.get("mcp_tool"):
            mcp = mcp_lookup.get(str(item["mcp_tool"]))
            item["available"] = bool(mcp)
            item["status"] = "ready" if mcp else "missing_mcp_tool"
            item["availability"] = _financial_mcp_availability_detail(
                runtime,
                item,
                mcp_lookup,
                mcp_tools=mcp_tools,
                mcp_servers=mcp_servers,
            )
            if mcp:
                item["wrapped_tool"] = mcp.get("wrapped_name")
        elif item.get("intent_action"):
            item["available"] = "agent_action_intent_create" in names
            item["status"] = "intent_ready" if item["available"] else "missing_intent_tool"
            item["availability"] = {
                "required_tool": "agent_action_intent_create",
                "reason_code": "action_intent_ready" if item["available"] else "action_intent_tool_missing",
                "agent_registry_has_tool": item["available"],
            }
        actions.append(item)
    summary: dict[str, int] = {}
    for item in actions:
        status = str(item.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return {
        "object": "aiask.desktop.financial_manager.catalog",
        "groups": list(FINANCIAL_MANAGER_GROUPS),
        "actions": actions,
        "summary": summary,
        "safety": {
            "mode": "read_only_plus_intents",
            "live_trading_enabled": False,
            "stateful_execution": "allowlisted_confirmed_actions",
            "confirmed_action_scope": list(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.keys()),
            "dry_run_only_actions": list(FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS),
            "secrets_redacted": True,
        },
        "stateful_execution": "allowlisted_confirmed_actions",
        "confirmed_action_scope": list(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.keys()),
        "dry_run_only_actions": list(FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS),
        "secrets_redacted": True,
    }


async def _financial_status_payload(runtime: AgentRuntime) -> dict[str, Any]:
    catalog = _financial_catalog_payload(runtime)
    readiness = await financial_system_readiness(
        runtime,
        full_runtime=None,
        full_mode_enabled=_hermes_full_enabled(),
        control_token_configured=_control_token_configured(),
        ai_status=_ai_status_payload_for_runtime(runtime),
    )
    mcp = MCPAggregator()
    return {
        "object": "aiask.desktop.financial_manager.status",
        "status": readiness.get("status") or "unknown",
        "readiness": _redact_secrets(readiness),
        "catalog_summary": catalog.get("summary") or {},
        "mcp": {
            "registration": _redact_secrets(mcp.registration_diagnostics()),
            "servers": _redact_secrets(mcp.servers_summary(include_all=False)),
        },
        "stateful_execution": "allowlisted_confirmed_actions",
        "confirmed_action_scope": list(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.keys()),
        "dry_run_only_actions": list(FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS),
        "broker": {
            "live_trading_enabled": False,
            "read_only_surfaces": ["ths_query_position", "ths_query_orders", "ths_query_deals", "qmt_query_account", "qmt_query_position", "qmt_query_orders"],
            "blocked_actions": ["ths_place_order", "ths_cancel_order", "qmt_place_order", "qmt_cancel_order"],
        },
        "recent_intents": [],
        "secrets_redacted": True,
    }


def _run_event_kind(event_type: str, payload: dict[str, Any]) -> str:
    name = str(event_type or "").strip().lower()
    if "approval" in name or "intent" in name:
        return "approval"
    if "gateway" in name or str(payload.get("platform") or "").strip():
        return "gateway"
    if "mcp" in name:
        return "mcp"
    if "failed" in name or "error" in name:
        return "error"
    if "tool" in name:
        return "tool"
    return "system"


def _run_event_severity(event_type: str, payload: dict[str, Any]) -> str:
    name = str(event_type or "").strip().lower()
    if "failed" in name or "error" in name:
        return "error"
    if "blocked" in name or "retry" in name or "cancel" in name:
        return "warning"
    if "completed" in name:
        return "success"
    return str(payload.get("severity") or "info")


def _run_event_title(event_type: str, payload: dict[str, Any]) -> str:
    name = str(event_type or "").strip()
    if payload.get("title"):
        return str(payload.get("title"))
    if payload.get("tool"):
        return f"{name}: {payload.get('tool')}"
    if payload.get("instruction"):
        return f"{name}: steer"
    if payload.get("error"):
        return f"{name}: error"
    return name or "run.event"


def _run_event_jump_target(kind: str, severity: str) -> str:
    if kind == "approval":
        return "tools-intents-approvals"
    if kind == "gateway":
        return "gateway"
    if kind == "mcp":
        return "mcp-connectors"
    if severity == "error":
        return "readiness-health"
    if kind == "tool":
        return "tools-intents-approvals"
    return "runs-events"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _normalize_run_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event.get("data") or {})
    event_type = str(event.get("event") or "")
    kind = _run_event_kind(event_type, payload)
    severity = _run_event_severity(event_type, payload)
    normalized = dict(event)
    normalized["kind"] = kind
    normalized["title"] = _run_event_title(event_type, payload)
    normalized["severity"] = severity
    normalized["jump_target"] = _run_event_jump_target(kind, severity)
    normalized["data"] = payload
    normalized["event_type"] = event_type
    normalized["status"] = _first_present(normalized.get("status"), payload.get("status"), severity)
    normalized["tool_name"] = _first_present(payload.get("tool_name"), payload.get("tool"), payload.get("name"))
    normalized["error_message"] = _first_present(payload.get("error_message"), payload.get("error"), payload.get("detail"))
    return normalized


def _run_summary(item: dict[str, Any], session_store: AgentSessionStore) -> dict[str, Any]:
    payload = dict(item.get("payload") or {})
    run_id = str(item.get("run_id") or "")
    events = session_store.list_run_events(run_id, limit=1000)
    normalized_events = [_normalize_run_event(event) for event in events]
    last_event = normalized_events[-1] if normalized_events else None
    tool_count = sum(1 for event in normalized_events if event.get("kind") == "tool")
    approval_count = sum(1 for event in normalized_events if event.get("kind") == "approval")
    error_count = sum(1 for event in normalized_events if str(event.get("severity") or "") == "error")
    return {
        "run_id": run_id,
        "session_id": item.get("session_id"),
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "event_count": len(normalized_events),
        "tool_call_count": int(payload.get("tool_call_count") or tool_count),
        "approval_count": approval_count,
        "error_count": error_count,
        "response_id": payload.get("response_id"),
        "last_event": last_event,
        "has_errors": error_count > 0,
        "has_pending_approval": any(
            event.get("kind") == "approval" and str(event.get("status") or "").lower() in {"pending", "awaiting_confirmation", "warning", "info"}
            for event in normalized_events
        ),
    }


def _session_summary(
    session: dict[str, Any],
    *,
    session_store: AgentSessionStore,
    intent_store: ActionIntentStore | None = None,
    approval_store: ApprovalStore | None = None,
) -> dict[str, Any]:
    session_id = str(session.get("session_id") or "").strip()
    latest_run = next(iter(session_store.list_runs(session_id=session_id, limit=1)), None) if session_id else None
    latest_run_summary = _run_summary(latest_run, session_store) if latest_run else None
    message_count = session_store.count_session_messages(session_id) if session_id else 0
    last_message_at = session_store.latest_message_at(session_id) if session_id else None
    last_event = latest_run_summary.get("last_event") if latest_run_summary else None
    pending_intents = list((intent_store or ActionIntentStore()).list(status="awaiting_confirmation", limit=500))
    pending_approvals = list((approval_store or ApprovalStore(session_store.path)).list(status="pending", limit=500))
    session_pending_intents = [
        item
        for item in pending_intents
        if str((item.get("params") or {}).get("session_id") or item.get("session_id") or "") == session_id
    ]
    session_pending_approvals = [
        item
        for item in pending_approvals
        if str((item.get("arguments") or {}).get("session_id") or item.get("session_id") or "") == session_id
    ]
    has_errors = bool((latest_run_summary or {}).get("has_errors"))
    status = str((latest_run_summary or {}).get("status") or session.get("status") or "idle")
    return {
        "session_id": session.get("session_id"),
        "title": session.get("title") or session.get("session_id"),
        "user_id": session.get("user_id"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "last_message_at": last_message_at or session.get("updated_at") or session.get("created_at"),
        "last_run_id": (latest_run_summary or {}).get("run_id"),
        "last_run_summary": latest_run_summary,
        "last_event": last_event,
        "message_count": message_count,
        "has_errors": has_errors,
        "has_pending_approval": bool(session_pending_intents or session_pending_approvals or (latest_run_summary or {}).get("has_pending_approval")),
        "status": "error" if has_errors else status,
        "metadata": session.get("metadata") or {},
    }


def _session_summary_payload(
    runtime: AgentRuntime,
    *,
    intent_store: ActionIntentStore | None = None,
    user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    approval_store = ApprovalStore(runtime.session_store.path)
    return [
        _session_summary(
            session,
            session_store=runtime.session_store,
            intent_store=intent_store,
            approval_store=approval_store,
        )
        for session in runtime.session_store.list_sessions(user_id=user_id, limit=limit)
    ]


def _workbench_summary_payload(
    runtime: AgentRuntime,
    *,
    intent_store: ActionIntentStore | None = None,
    user_id: str | None = None,
    session_limit: int = 8,
    run_limit: int = 8,
) -> dict[str, Any]:
    store = intent_store or ActionIntentStore()
    recent_sessions = _session_summary_payload(
        runtime,
        intent_store=store,
        user_id=user_id,
        limit=max(1, min(int(session_limit or 8), 20)),
    )
    runs = runtime.session_store.list_runs(limit=max(1, min(int(run_limit or 8), 50)))
    run_summaries = [_run_summary(item, runtime.session_store) for item in runs]
    pending_intents = len(store.list(status="awaiting_confirmation", limit=500))
    pending_approvals = len(ApprovalStore(runtime.session_store.path).list(status="pending", limit=500))
    gateway_messages = GatewayMessageStore(runtime.session_store.path).list(limit=500)
    gateway_failed = sum(1 for item in gateway_messages if str(item.get("status") or "").lower() in {"failed", "error"})
    mcp_servers = MCPAggregator().servers_summary(include_all=True)
    mcp_degraded = sum(1 for item in mcp_servers if item.get("configured") is False or item.get("status") == "failed")
    return {
        "object": "aiask.desktop.workbench.summary",
        "recent_sessions": recent_sessions,
        "recent_runs": run_summaries,
        "queues": {
            "pending_intents": pending_intents,
            "pending_approvals": pending_approvals,
            "gateway_failed": gateway_failed,
            "mcp_degraded": mcp_degraded,
        },
        "access": {
            "full_mode_active": bool(_hermes_full_enabled()),
            "control_token_configured": _control_token_configured(),
            "sessions_admin_available": bool(_hermes_full_enabled() and _control_token_configured()),
        },
    }


def _desktop_runs_payload(
    runtime: AgentRuntime,
    *,
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    runs = runtime.session_store.list_runs(session_id=session_id, status=status, limit=limit)
    return {
        "object": "list",
        "data": [_run_summary(item, runtime.session_store) for item in runs],
    }


def _manager_arguments(action: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    mcp_action = str(action.get("mcp_action") or "").strip()
    if not mcp_action:
        return dict(params)
    return {"action": mcp_action, "params": dict(params), **dict(params)}


async def _financial_query_payload(runtime: AgentRuntime, payload: dict[str, Any]) -> dict[str, Any]:
    action = _financial_action_map().get(_financial_action_key(str(payload.get("capability_id") or ""), str(payload.get("action_id") or "")))
    if not action:
        return {"object": "aiask.desktop.financial_manager.query", "success": False, "data": None, "error": "financial manager action is not registered", "error_code": "FINANCIAL_ACTION_NOT_FOUND", "secrets_redacted": True}
    if action.get("mode") == "blocked":
        return {"object": "aiask.desktop.financial_manager.query", "success": False, "data": {"action": action, "reason": action.get("blocked_reason")}, "error": str(action.get("blocked_reason") or "action is blocked"), "error_code": "FINANCIAL_ACTION_BLOCKED", "secrets_redacted": True}
    if action.get("mode") != "read_only":
        return {"object": "aiask.desktop.financial_manager.query", "success": False, "data": {"action": action, "required_endpoint": "/v1/desktop/financial-manager/intent"}, "error": "stateful financial actions must be created as ActionIntent", "error_code": "FINANCIAL_ACTION_REQUIRES_INTENT", "secrets_redacted": True}
    params = dict(action.get("default_params") or {})
    params.update(dict(payload.get("params") or {}))
    tool_name = str(action.get("tool") or "")
    if not tool_name and action.get("mcp_tool"):
        mcp_lookup = _wrapped_mcp_lookup(runtime)
        match = mcp_lookup.get(str(action.get("mcp_tool")))
        tool_name = str((match or {}).get("wrapped_name") or "")
        params = _manager_arguments(action, params)
    if not tool_name:
        availability = (
            _financial_mcp_availability_detail(runtime, action, _wrapped_mcp_lookup(runtime))
            if action.get("mcp_tool")
            else _financial_tool_availability_detail(runtime, action)
        )
        return {
            "object": "aiask.desktop.financial_manager.query",
            "success": False,
            "data": {"action": action, "availability": _redact_secrets(availability)},
            "error": "financial manager tool is not available",
            "error_code": "FINANCIAL_TOOL_UNAVAILABLE",
            "secrets_redacted": True,
        }
    result = await runtime.tool_registry.call_tool(tool_name, params)
    return {
        "object": "aiask.desktop.financial_manager.query",
        "capability_id": action.get("capability_id"),
        "action_id": action.get("action_id"),
        "tool": tool_name,
        "success": bool(result.get("success")),
        "data": _redact_secrets(result.get("data")),
        "error": result.get("error"),
        "error_code": result.get("error_code"),
        "meta": _redact_secrets(result.get("meta")),
        "secrets_redacted": True,
    }


async def _financial_intent_payload(runtime: AgentRuntime, payload: dict[str, Any]) -> dict[str, Any]:
    action = _financial_action_map().get(_financial_action_key(str(payload.get("capability_id") or ""), str(payload.get("action_id") or "")))
    if not action:
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": None, "error": "financial manager action is not registered", "error_code": "FINANCIAL_ACTION_NOT_FOUND", "secrets_redacted": True}
    if action.get("mode") == "blocked":
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": {"action": action, "reason": action.get("blocked_reason")}, "error": str(action.get("blocked_reason") or "action is blocked"), "error_code": "FINANCIAL_ACTION_BLOCKED", "secrets_redacted": True}
    if action.get("mode") != "stateful_intent":
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": {"action": action}, "error": "read-only financial actions do not create intents", "error_code": "FINANCIAL_ACTION_READ_ONLY", "secrets_redacted": True}
    params = dict(action.get("default_params") or {})
    params.update(dict(payload.get("params") or {}))
    result = await runtime.tool_registry.call_tool(
        "agent_action_intent_create",
        {
            "action": str(action.get("intent_action") or ""),
            "params": params,
            "rationale": payload.get("rationale") or f"Financial Manager V1 intent for {action.get('label') or action.get('action_id')}",
            "user_id": payload.get("user_id"),
        },
    )
    return {
        "object": "aiask.desktop.financial_manager.intent",
        "capability_id": action.get("capability_id"),
        "action_id": action.get("action_id"),
        "success": bool(result.get("success")),
        "data": _redact_secrets(result.get("data")),
        "error": result.get("error"),
        "error_code": result.get("error_code"),
        "meta": _redact_secrets(result.get("meta")),
        "secrets_redacted": True,
    }


def create_app(
    *,
    runtime: AgentRuntime | None = None,
    intent_executor: IntentExecutor | None = None,
) -> FastAPI:
    load_project_env()
    if runtime is None:
        runtime, default_executor = _build_runtime_and_executor()
        intent_executor = intent_executor or default_executor
    if intent_executor is None:
        intent_executor = IntentExecutor(ActionIntentStore())
    full_runtime: AgentRuntime | None = None
    quant_store = QuantResearchStore(runtime.session_store.path)

    def _control_snapshot() -> tuple[bool, str | None]:
        expected = (
            str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
            or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
        )
        if not expected:
            return False, "control token is not configured"
        return False, "control token required"

    def _desktop_settings_status_payload() -> dict[str, Any]:
        control_ok, control_reason = _control_snapshot()
        return _desktop_settings_status_payload_for_runtime(
            runtime,
            endpoint=_agent_endpoint(),
            control_authorized=control_ok,
            control_reason=control_reason,
        )

    async def _desktop_data_status_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_status_payload_for_runtime(runtime, arguments)

    async def _desktop_data_sync_plan_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_sync_plan_payload_for_runtime(runtime, arguments)

    def build_full_runtime() -> AgentRuntime:
        nonlocal full_runtime
        if full_runtime is not None:
            return full_runtime
        policy = ToolPolicy(
            toolset=GENERAL_FULL_TOOLSET,
            general_tools_enabled=True,
            workspace_roots=runtime.tool_registry.policy_engine.policy.workspace_roots,
        )
        full_runtime = AgentRuntime(
            model_client=runtime.model_client,
            session_store=runtime.session_store,
            tool_registry=build_default_tool_registry(
                session_store=runtime.session_store,
                policy_engine=ToolPolicyEngine(policy),
            ),
            model=runtime.model,
            max_iterations=runtime.max_iterations,
            model_timeout_seconds=runtime.model_timeout_seconds,
            tool_timeout_seconds=runtime.tool_timeout_seconds,
            retry_attempts=runtime.retry_attempts,
        )
        return full_runtime

    def api_authorized(request: Request) -> bool:
        client_host = request.client.host if request.client else "127.0.0.1"
        if _is_loopback(client_host):
            return True
        expected = str(os.getenv("AIASK_AGENT_API_TOKEN", "")).strip()
        return bool(expected and _extract_bearer_token(request.headers.get("authorization")) == expected)

    def control_authorized(request: Request) -> tuple[bool, str | None]:
        client_host = request.client.host if request.client else "127.0.0.1"
        if not _is_loopback(client_host):
            return False, "control endpoint is loopback only"
        expected = (
            str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
            or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
        )
        if not expected:
            return False, "control token is not configured"
        token = (
            _extract_bearer_token(request.headers.get("x-aiask-agent-control-token"))
            or _extract_bearer_token(request.headers.get("x-aiask-local-control-token"))
            or _extract_bearer_token(request.headers.get("authorization"))
        )
        if token != expected:
            return False, "invalid control token"
        return True, None

    def full_authorized(request: Request) -> tuple[bool, str | None]:
        if not _hermes_full_enabled():
            return False, "AIASK native Hermes full mode is not enabled"
        return control_authorized(request)

    def select_runtime(payload: dict[str, Any], request: Request) -> tuple[AgentRuntime, str]:
        mode = str(payload.get("mode") or "finance_safe").strip() or "finance_safe"
        if mode == "finance_safe":
            return runtime, mode
        if mode == "hermes_full":
            ok, reason = full_authorized(request)
            if not ok:
                raise HTTPException(_mode_error_status(reason), detail=reason or "unauthorized")
            return build_full_runtime(), mode
        raise HTTPException(400, detail=f"unsupported mode: {mode}")

    def require_api(request: Request) -> None:
        if not api_authorized(request):
            raise HTTPException(401, detail="unauthorized")

    def require_full(request: Request) -> AgentRuntime:
        ok, reason = full_authorized(request)
        if not ok:
            raise HTTPException(_mode_error_status(reason), detail=reason or "unauthorized")
        return build_full_runtime()

    def tool_catalog_payload(selected: AgentRuntime, *, implementation: str | None = None) -> dict[str, Any]:
        return build_tool_catalog_payload(selected, implementation=implementation)

    async def full_tool_call(request: Request, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        full = require_full(request)
        result = await full.tool_registry.call_tool(tool_name, dict(arguments or {}))
        if not result.get("success"):
            raise HTTPException(400, detail=result.get("error") or "tool failed")
        return result

    def full_surface_status() -> dict[str, Any]:
        gateway = GatewayRuntime(messages=GatewayMessageStore(runtime.session_store.path))
        learning = LearningLoop(session_store=runtime.session_store, state_path=runtime.session_store.path)
        rl = RLAtroposManager(runtime.session_store.path)
        mcp = MCPAggregator()
        skills = SkillStore()
        return {
            "full_scope": "hermes_full_runtime",
            "platform_gateway": gateway.status(),
            "terminal_backends": list_backends(),
            "learning_loop": learning.status(),
            "rl_training": rl.current_config(),
            "tui": tui_status_payload(),
            "providers": ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path)).status(),
            "memory": MemoryProviderManager(path=runtime.session_store.path).status(),
            "acp": ACPManager(mcp=mcp).status(),
            "security": SecurityScanner(policy=runtime.tool_registry.policy_engine.policy).status(),
            "skill_packs": SkillPackManager(skill_store=skills).status(),
        }

    def hermes_readiness_payload() -> dict[str, Any]:
        gateway = GatewayRuntime(messages=GatewayMessageStore(runtime.session_store.path))
        rl = RLAtroposManager(runtime.session_store.path)
        terminal_items = list_backends()
        plugin_manager = NativePluginManager()
        plugins = plugin_manager.list()
        mcp = MCPAggregator()
        provider_registry = ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path))
        memory_manager = MemoryProviderManager(path=runtime.session_store.path)
        acp_manager = ACPManager(mcp=mcp)
        security = SecurityScanner(policy=runtime.tool_registry.policy_engine.policy)
        skill_packs = SkillPackManager(skill_store=SkillStore())
        selected_names = build_full_runtime().tool_registry.names() if _hermes_full_enabled() else runtime.tool_registry.names()
        parity = parity_summary(selected_names, env=dict(os.environ), gateway_adapters=ADAPTERS.keys())
        dependency = {
            "docker": bool(shutil.which("docker") or importlib.util.find_spec("docker")),
            "ssh": bool(shutil.which("ssh") or importlib.util.find_spec("asyncssh")),
            "apptainer_or_singularity": bool(shutil.which("apptainer") or shutil.which("singularity")),
            "modal": bool(shutil.which("modal") or importlib.util.find_spec("modal") or os.getenv("AIASK_MODAL_TERMINAL_COMMAND")),
            "daytona": bool(shutil.which("daytona") or importlib.util.find_spec("daytona") or os.getenv("AIASK_DAYTONA_TERMINAL_COMMAND")),
            "textual": bool(importlib.util.find_spec("textual")),
            "atroposlib": bool(importlib.util.find_spec("atroposlib")),
            "tinker_atropos": bool(importlib.util.find_spec("tinker_atropos")),
        }
        credentials = {
            "homeassistant": bool(os.getenv("HASS_URL") and os.getenv("HASS_TOKEN")),
            "rl": bool(os.getenv("TINKER_API_KEY") and os.getenv("WANDB_API_KEY")),
            "feishu": bool((os.getenv("FEISHU_APP_ID") and os.getenv("FEISHU_APP_SECRET")) or os.getenv("FEISHU_BOT_WEBHOOK")),
            "discord": bool(os.getenv("DISCORD_BOT_TOKEN")),
            "gateway_webhook": bool(os.getenv("AIASK_GATEWAY_WEBHOOK_URL") or os.getenv("AIASK_GATEWAY_WEBHOOK_SECRET")),
        }
        return {
            "object": "aiask.hermes_readiness",
            "implementation": "aiask_native",
            "embedded_vendor_runtime": False,
            "dependencies": dependency,
            "credentials": credentials,
            "terminal_backends": terminal_items,
            "gateway": gateway.status(),
            "mcp": mcp.registration_diagnostics(),
            "providers": provider_registry.status(),
            "memory": memory_manager.status(),
            "acp": acp_manager.readiness(),
            "security": security.status(),
            "skill_packs": skill_packs.status(),
            "rl": rl.readiness(),
            "plugins": {
                "count": len(plugins),
                "enabled_count": sum(1 for item in plugins if item.get("enabled")),
                "readiness": plugin_manager.readiness(),
                "runners": [
                    {
                        "name": item.get("name"),
                        "enabled": item.get("enabled"),
                        "runner": item.get("runner"),
                        "tools": [tool.get("name") for tool in list(item.get("tools") or []) if isinstance(tool, dict)],
                        "commands": [command.get("name") for command in list(item.get("commands") or []) if isinstance(command, dict)],
                    }
                    for item in plugins
                ],
            },
            "feature_mapping": parity.get("feature_mapping", []),
            "missing_features": parity.get("missing_features", []),
            "implemented_features_count": parity.get("implemented_features_count", 0),
            "network": {
                "live_tests_enabled": bool(os.getenv("AIASK_RUN_LIVE_HERMES_TESTS")),
                "proxy_configured": bool(os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")),
            },
            "permissions": {
                "control_token_configured": bool(os.getenv("AIASK_AGENT_CONTROL_TOKEN") or os.getenv("AIASK_LOCAL_CONTROL_TOKEN")),
                "workspace_roots": list(runtime.tool_registry.policy_engine.policy.workspace_roots),
            },
        }

    def ai_status_payload() -> dict[str, Any]:
        return _ai_status_payload_for_runtime(runtime)

    async def ai_smoke_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _ai_smoke_payload_for_runtime(runtime, payload)

    async def ai_models_payload() -> dict[str, Any]:
        return await _ai_models_payload_for_runtime(runtime)

    def desktop_settings_status_payload(request: Request | None = None) -> dict[str, Any]:
        control_ok = False
        control_reason = None
        if request is not None:
            control_ok, control_reason = control_authorized(request)
        return _desktop_settings_status_payload_for_runtime(
            runtime,
            endpoint=_agent_endpoint(),
            control_authorized=control_ok,
            control_reason=control_reason,
        )

    async def desktop_data_status_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_status_payload_for_runtime(runtime, arguments)

    async def desktop_data_sync_plan_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_sync_plan_payload_for_runtime(runtime, arguments)

    def _capability_counts(*groups: Any) -> dict[str, int]:
        counts = {"implemented": 0, "live_unverified": 0, "unconfigured": 0, "failed": 0, "missing": 0, "gated": 0}
        for group in groups:
            for item in list(group or []):
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or item.get("live_status") or "unconfigured")
                if status == "implemented":
                    counts["implemented"] += 1
                elif status in {"live_unverified", "skipped_missing_credentials", "partial"}:
                    counts["live_unverified"] += 1
                elif status in {"missing", "planned"}:
                    counts["missing"] += 1
                elif status in {"failed", "blocked"}:
                    counts["failed"] += 1
                else:
                    counts["unconfigured"] += 1
        return counts

    async def desktop_capabilities_payload(request: Request) -> dict[str, Any]:
        selected_names = build_full_runtime().tool_registry.names() if _hermes_full_enabled() else runtime.tool_registry.names()
        parity = parity_summary(selected_names, env=dict(os.environ), gateway_adapters=ADAPTERS.keys())
        readiness = hermes_readiness_payload()
        full_ok, full_reason = full_authorized(request)
        control_ok, control_reason = control_authorized(request)
        full_mode_enabled = _hermes_full_enabled()
        control_token_configured = bool(
            str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
            or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
        )
        mcp = MCPAggregator()
        mcp_registration = mcp.registration_diagnostics()

        async def read_only_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            try:
                return await runtime.tool_registry.call_tool(name, arguments)
            except Exception as exc:
                return {"success": False, "data": {"configured": False, "tool": name}, "error": str(exc), "error_code": "DESKTOP_TOOL_UNAVAILABLE"}

        db_env_snapshot = {key: os.environ.get(key) for key in quant_adapter.DATABASE_ENV_KEYS}
        if full_ok:
            factory_status, factory_runs, review_snapshot = await asyncio.gather(
                read_only_tool("agent_factory_status", {"recent_run_limit": 5, "_timeout_seconds": 5}),
                read_only_tool("agent_factory_runs", {"limit": 10, "_timeout_seconds": 5}),
                read_only_tool("agent_strategy_review_snapshot", {"limit": 20}),
            )
        else:
            factory_status = {
                "success": False,
                "data": {"configured": False, "gated": True, "tool": "agent_factory_status"},
                "error": full_reason or "control token required",
                "error_code": "CONTROL_TOKEN_REQUIRED",
            }
            factory_runs = {
                "success": False,
                "data": {"configured": False, "gated": True, "tool": "agent_factory_runs", "runs": []},
                "error": full_reason or "control token required",
                "error_code": "CONTROL_TOKEN_REQUIRED",
            }
            review_snapshot = {
                "success": False,
                "data": {"configured": False, "gated": True, "tool": "agent_strategy_review_snapshot"},
                "error": full_reason or "control token required",
                "error_code": "CONTROL_TOKEN_REQUIRED",
            }
        for key, value in db_env_snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        quant_presets = quant_adapter.quant_presets()
        recent_quant_runs = quant_store.list(limit=5)

        gated = {"gated": True, "reason": full_reason or "control token required"}
        skills_payload: Any = gated
        plugins_payload: Any = gated
        mcp_payload: dict[str, Any] = {
            "gated": not full_ok,
            "reason": None if full_ok else full_reason,
            "registration_status": mcp_registration["registration_status"],
            "discovery_status": mcp_registration["discovery_status"],
            "discovered_counts": mcp_registration["discovered_counts"],
            "configured": mcp_registration["configured"],
            "config_path": mcp_registration["config_path"],
            "config_exists": mcp_registration["config_exists"],
            "detected_service_port": mcp_registration["detected_service_port"],
            "detected_service_url": mcp_registration["detected_service_url"],
            "suggested_registration_url": mcp_registration["suggested_registration_url"],
            "auth_configured": mcp_registration["auth_configured"],
            "auth_env_vars": mcp_registration["auth_env_vars"],
            "missing_auth_env_vars": mcp_registration["missing_auth_env_vars"],
            "partial_success": mcp_registration.get("partial_success"),
            "warnings": mcp_registration.get("warnings") or [],
            "unsupported_methods": mcp_registration.get("unsupported_methods") or [],
            "error_code": mcp_registration["error_code"],
            "detail": mcp_registration["detail"],
            "servers": mcp.servers_summary(include_all=full_ok),
            "tools": [],
            "resources": [],
            "prompts": [],
            "oauth": [],
        }
        if full_ok:
            full = build_full_runtime()
            skills_result = await full.tool_registry.call_tool("agent_skill_manage", {"action": "snapshot"})
            skills_payload = dict(skills_result.get("data") or {})
            plugins_payload = NativePluginManager().list()
            mcp_payload.update(
                {
                    "tools": mcp.tools_summary(include_all=True),
                    "resources": mcp.resources_summary(include_all=True),
                    "prompts": mcp.prompts_summary(include_all=True),
                    "oauth": mcp.oauth_status(include_all=True),
                }
            )

        provider_payload = ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path)).status()
        memory_payload = MemoryProviderManager(path=runtime.session_store.path).status()
        acp_payload = ACPManager(mcp=mcp).status()
        security_payload = SecurityScanner(policy=runtime.tool_registry.policy_engine.policy).status()
        skill_pack_payload = SkillPackManager(skill_store=SkillStore()).status()

        counts = _capability_counts(
            parity.get("hermes_tool_mapping"),
            parity.get("gateway_platform_mapping"),
            parity.get("feature_mapping"),
        )
        issues = [
            *list(parity.get("missing_hermes_tools") or []),
            *list(parity.get("missing_gateway_platforms") or []),
            *list(parity.get("missing_features") or []),
        ]
        return {
            "object": "aiask.desktop_capabilities",
            "summary": {
                "status": parity.get("strict_status") or parity.get("status"),
                "source": "live_backend" if full_ok else "gated",
                "counts": counts,
                "issue_count": len(issues),
                "control": {
                    "authorized": full_ok,
                    "reason": None if full_ok else full_reason,
                    "full_mode_enabled": full_mode_enabled,
                    "control_token_configured": control_token_configured,
                    "control_authorized": control_ok,
                    "control_reason": None if control_ok else control_reason,
                    "gated_reason": None if full_ok else full_reason,
                },
                "refreshed_at": int(time.time()),
            },
            "hermes": {
                "status": {
                    "implementation": "aiask_native",
                    "baseline": parity.get("baseline"),
                    "embedded_vendor_runtime": False,
                    "full_mode_enabled": _hermes_full_enabled(),
                    "full_mode_active": full_ok,
                },
                "parity": parity,
                "readiness": readiness,
                "tool_mapping": parity.get("hermes_tool_mapping", []),
                "platform_mapping": parity.get("gateway_platform_mapping", []),
                "feature_mapping": parity.get("feature_mapping", []),
                "issues": issues,
                "providers": provider_payload,
                "memory": memory_payload,
                "acp": acp_payload,
                "security": security_payload,
                "skill_packs": skill_pack_payload,
            },
            "mcp": mcp_payload,
            "strategy_factory": {
                "status": factory_status,
                "runs": factory_runs,
                "review_snapshot": review_snapshot,
            },
            "quant": {
                "presets": quant_presets,
                "recent_runs": recent_quant_runs,
                "data_status": quant_presets.get("data_status", {}),
                "status": "ready" if quant_presets.get("data_status", {}).get("status") == "ready" else "unconfigured",
            },
            "financial_system": await financial_system_readiness(
                runtime,
                full_runtime=build_full_runtime() if _hermes_full_enabled() else full_runtime,
                full_mode_enabled=_hermes_full_enabled(),
                control_token_configured=control_token_configured,
                ai_status=ai_status_payload(),
            ),
            "skills": skills_payload,
            "skill_packs": skill_pack_payload,
            "plugins": plugins_payload,
            "providers": provider_payload,
            "memory": memory_payload,
            "acp": acp_payload,
            "security": security_payload,
            "ai": ai_status_payload(),
            "raw_refs": {
                "parity": "/v1/capabilities/parity",
                "readiness": "/v1/hermes/readiness",
                "mcp_servers": "/v1/mcp/servers",
                "skills": "/v1/skills",
                "ai_status": "/v1/ai/status",
                "quant_presets": "/v1/desktop/quant/presets",
                "quant_research_runs": "/v1/desktop/quant/research-runs",
                "financial_system_readiness": "/v1/financial-system/readiness",
            },
        }

    async def sse_events(events: list[dict[str, Any]]) -> AsyncIterator[bytes]:
        for raw_event in events:
            event = _normalize_run_event(raw_event)
            if event.get("id") is not None:
                yield f"id: {event['id']}\n".encode("utf-8")
            if event.get("event"):
                yield f"event: {event['event']}\n".encode("utf-8")
            yield b"data: "
            yield _json_dumps(event)
            yield b"\n\n"

    async def chat_completion_sse(result: Any, *, model: str) -> AsyncIterator[bytes]:
        created = int(time.time())
        chunks = [
            {
                "id": result.response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
            {
                "id": result.response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": result.content}, "finish_reason": None}],
                "aiask": {"session_id": result.session_id, "run_id": result.run_id},
            },
            {
                "id": result.response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
        ]
        for chunk in chunks:
            yield b"data: "
            yield _json_dumps(chunk)
            yield b"\n\n"
        yield b"data: [DONE]\n\n"

    async def response_sse(result: Any, *, model: str) -> AsyncIterator[bytes]:
        events = [
            {"event": "response.created", "data": {"id": result.response_id, "status": "in_progress", "model": model}},
            {"event": "response.output_text.delta", "data": {"id": result.response_id, "delta": result.content}},
            {"event": "response.completed", "data": {"id": result.response_id, "status": result.status, "run_id": result.run_id}},
        ]
        for event in events:
            yield f"event: {event['event']}\n".encode("utf-8")
            yield b"data: "
            yield _json_dumps(event["data"])
            yield b"\n\n"
        yield b"data: [DONE]\n\n"

    _daemon = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal _daemon
        # Start Gateway Daemon if enabled
        if os.getenv("AIASK_GATEWAY_DAEMON_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
            from .gateway_daemon import GatewayDaemon
            try:
                _daemon = GatewayDaemon(
                    runtime=runtime,
                    config=GatewayConfigStore(),
                    router=DeliveryRouter(),
                    messages=GatewayMessageStore(),
                )
                await _daemon.start()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Gateway daemon start failed: %s", exc)
                _daemon = None

        try:
            yield
        finally:
            if _daemon is not None:
                await _daemon.stop()
            if full_runtime is not None:
                await full_runtime.aclose()
            await runtime.aclose()

    app = FastAPI(title="AIASK Agent", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(_cors_origins()),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-AIASK-Agent-Token",
            "X-AIASK-Agent-Control-Token",
            "X-AIASK-Local-Control-Token",
            "X-AIASK-Session-Id",
            "X-AIASK-User-Id",
        ],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "service": "aiask-agent"}

    @app.get("/health/detailed")
    async def health_detailed() -> dict[str, Any]:
        parity_names = build_full_runtime().tool_registry.names() if _hermes_full_enabled() else runtime.tool_registry.names()
        return {
            "status": "ok",
            "service": "aiask-agent",
            "runtime": {
                "model": runtime.model,
                "max_iterations": runtime.max_iterations,
                "model_timeout_seconds": runtime.model_timeout_seconds,
                "tool_timeout_seconds": runtime.tool_timeout_seconds,
                "server": "fastapi_asgi",
            },
            "tools": {
                "count": len(runtime.tool_registry.names()),
                "names": runtime.tool_registry.names(),
                "toolset": runtime.tool_registry.policy_engine.toolset,
            },
            "hermes": {
                "mode": "aiask_native",
                "full_mode_enabled": _hermes_full_enabled(),
                "full_mode_active": full_runtime is not None,
                "parity": _redact_required_env(parity_summary(parity_names, env=dict(os.environ), gateway_adapters=ADAPTERS.keys())),
            },
            "control": {
                "loopback_only": True,
                "token_configured": bool(
                    str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
                    or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
                ),
            },
        }

    @app.get("/v1/capabilities/parity")
    async def capabilities_parity(request: Request) -> dict[str, Any]:
        require_api(request)
        selected = build_full_runtime() if _hermes_full_enabled() else runtime
        return parity_summary(selected.tool_registry.names(), env=dict(os.environ), gateway_adapters=ADAPTERS.keys())

    @app.get("/v1/tools")
    async def tools(request: Request) -> dict[str, Any]:
        require_api(request)
        return tool_catalog_payload(runtime)

    @app.get("/v1/desktop/capabilities")
    async def desktop_capabilities(request: Request) -> dict[str, Any]:
        require_api(request)
        return await desktop_capabilities_payload(request)

    @app.get("/v1/desktop/settings/status")
    async def desktop_settings_status(request: Request) -> dict[str, Any]:
        require_api(request)
        return desktop_settings_status_payload(request)

    @app.get("/v1/desktop/data/status")
    async def desktop_data_status(request: Request, codes: str = "", max_stale_days: int = 5) -> dict[str, Any]:
        require_api(request)
        code_list = [item.strip() for item in str(codes or "").replace("\n", ",").split(",") if item.strip()]
        return await desktop_data_status_payload({"codes": code_list, "max_stale_days": max_stale_days})

    @app.post("/v1/desktop/data/sync-plan")
    async def desktop_data_sync_plan(request: Request) -> dict[str, Any]:
        require_api(request)
        return await desktop_data_sync_plan_payload(dict(await request.json() or {}))

    @app.get("/v1/desktop/users/local-profile")
    async def desktop_local_profile_get(request: Request) -> dict[str, Any]:
        require_api(request)
        return local_profile_payload()

    @app.post("/v1/desktop/users/local-profile")
    async def desktop_local_profile_post(request: Request) -> dict[str, Any]:
        require_api(request)
        return save_local_profile(dict(await request.json() or {}))

    @app.patch("/v1/desktop/users/local-profile")
    async def desktop_local_profile_patch(request: Request) -> dict[str, Any]:
        require_api(request)
        return save_local_profile(dict(await request.json() or {}))

    @app.get("/v1/desktop/factor-factory/status")
    async def desktop_factor_factory_status(request: Request, limit: int = 50) -> dict[str, Any]:
        require_api(request)
        return await factor_factory_status(limit=limit)

    @app.get("/v1/desktop/trade-predictions/status")
    async def desktop_trade_predictions_status(
        request: Request,
        strategy_id: str | None = None,
        stock_code: str | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        require_api(request)
        return await runtime.tool_registry.call_tool(
            "agent_trade_prediction_status",
            {"strategy_id": strategy_id, "stock_code": stock_code, "limit": limit},
        )

    @app.get("/v1/desktop/trade-predictions/outcomes")
    async def desktop_trade_predictions_outcomes(
        request: Request,
        prediction_id: str | None = None,
        strategy_id: str | None = None,
        stock_code: str | None = None,
        score_version: str | None = None,
        score_status: str | None = None,
        data_quality_status: str | None = None,
        actual_trading_date_lte: str | None = None,
        actual_trading_date_gte: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        require_api(request)
        return await runtime.tool_registry.call_tool(
            "agent_trade_prediction_outcomes",
            {
                "prediction_id": prediction_id,
                "strategy_id": strategy_id,
                "stock_code": stock_code,
                "score_version": score_version,
                "score_status": score_status,
                "data_quality_status": data_quality_status,
                "actual_trading_date_lte": actual_trading_date_lte,
                "actual_trading_date_gte": actual_trading_date_gte,
                "limit": limit,
            },
        )

    @app.get("/v1/desktop/trade-predictions/matrix")
    async def desktop_trade_predictions_matrix(
        request: Request,
        strategy_id: str | None = None,
        stock_code: str | None = None,
        score_version: str | None = None,
        dimensions: str = "",
        limit: int = 1000,
    ) -> dict[str, Any]:
        require_api(request)
        dimension_list = [item.strip() for item in str(dimensions or "").split(",") if item.strip()]
        return await runtime.tool_registry.call_tool(
            "agent_trade_prediction_matrix",
            {
                "strategy_id": strategy_id,
                "stock_code": stock_code,
                "score_version": score_version,
                "dimensions": dimension_list,
                "limit": limit,
            },
        )

    @app.get("/v1/desktop/stock-radar/status")
    async def desktop_stock_radar_status(request: Request, run_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        require_api(request)
        return await runtime.tool_registry.call_tool(
            "agent_stock_radar_status",
            {"run_id": run_id, "limit": limit},
        )

    @app.get("/v1/desktop/stock-radar/candidates")
    async def desktop_stock_radar_candidates(
        request: Request,
        run_id: str | None = None,
        tier: str | None = None,
        symbol: str | None = None,
        min_score: float | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        require_api(request)
        return await runtime.tool_registry.call_tool(
            "agent_stock_radar_candidates",
            {
                "run_id": run_id,
                "tier": tier,
                "symbol": symbol,
                "min_score": min_score,
                "limit": limit,
            },
        )

    @app.get("/v1/desktop/stock-radar/digest")
    async def desktop_stock_radar_digest(
        request: Request,
        run_id: str | None = None,
        limit: int = 20,
        channels: str = "wecom,telegram",
    ) -> dict[str, Any]:
        require_api(request)
        return await runtime.tool_registry.call_tool(
            "agent_stock_radar_digest",
            {"run_id": run_id, "limit": limit, "channels": [item.strip() for item in channels.split(",") if item.strip()]},
        )

    @app.get("/v1/desktop/workbench/summary")
    async def desktop_workbench_summary(
        request: Request,
        user_id: str | None = None,
        session_limit: int = 8,
        run_limit: int = 8,
    ) -> dict[str, Any]:
        require_api(request)
        return _workbench_summary_payload(
            runtime,
            intent_store=intent_executor.store,
            user_id=user_id,
            session_limit=session_limit,
            run_limit=run_limit,
        )

    @app.get("/v1/desktop/runs")
    async def desktop_runs(
        request: Request,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        require_api(request)
        return _desktop_runs_payload(runtime, session_id=session_id, status=status, limit=limit)

    @app.get("/v1/ai/status")
    async def ai_status(request: Request) -> dict[str, Any]:
        require_api(request)
        return ai_status_payload()

    @app.post("/v1/ai/smoke")
    async def ai_smoke(request: Request) -> dict[str, Any]:
        require_api(request)
        return await ai_smoke_payload(dict(await request.json() or {}))

    @app.get("/v1/ai/models")
    async def ai_models(request: Request) -> dict[str, Any]:
        require_api(request)
        return await ai_models_payload()

    @app.get("/v1/desktop/quant/presets")
    async def desktop_quant_presets(request: Request) -> dict[str, Any]:
        require_api(request)
        return quant_adapter.quant_presets()

    @app.post("/v1/desktop/quant/research-runs")
    async def desktop_quant_research_create(request: Request) -> dict[str, Any]:
        require_api(request)
        payload = dict(await request.json() or {})
        return await runtime.tool_registry.call_tool("agent_quant_research_run", payload)

    @app.get("/v1/desktop/quant/research-runs/{research_id}")
    async def desktop_quant_research_get(request: Request, research_id: str) -> dict[str, Any]:
        require_api(request)
        item = quant_store.get(research_id)
        if item is None:
            raise HTTPException(404, detail=f"quant research run not found: {research_id}")
        return {"object": "aiask.quant_research_run", **item}

    @app.get("/v1/desktop/quant/research-runs/{research_id}/report")
    async def desktop_quant_research_report(request: Request, research_id: str) -> dict[str, Any]:
        require_api(request)
        report = quant_store.report(research_id)
        if report is None:
            raise HTTPException(404, detail=f"quant research report not found: {research_id}")
        return report

    @app.post("/v1/tools/{tool_name}")
    async def tool_call_read_only(request: Request, tool_name: str) -> dict[str, Any]:
        require_api(request)
        payload = await request.json()
        tool = runtime.tool_registry.get(tool_name)
        metadata = dict(getattr(tool, "metadata", {}) or {}) if tool else {}
        if not _metadata_allows_read_only_desktop_call(metadata, tool_name) and not _is_read_only_desktop_tool(tool_name):
            raise HTTPException(403, detail=f"tool is not available through the read-only desktop API: {tool_name}")
        result = await runtime.tool_registry.call_tool(tool_name, dict(payload or {}))
        return result

    @app.get("/v1/hermes/status")
    async def hermes_status(request: Request) -> dict[str, Any]:
        require_api(request)
        selected_names = build_full_runtime().tool_registry.names() if _hermes_full_enabled() else runtime.tool_registry.names()
        return {
            "object": "aiask.hermes_status",
            "implementation": "aiask_native",
            "baseline": HERMES_BASELINE,
            "embedded_vendor_runtime": False,
            "full_mode_enabled": _hermes_full_enabled(),
            "full_mode_active": full_runtime is not None,
            "evaluated_toolset": GENERAL_FULL_TOOLSET if _hermes_full_enabled() else runtime.tool_registry.policy_engine.toolset,
            "parity": parity_summary(selected_names, env=dict(os.environ), gateway_adapters=ADAPTERS.keys()),
            **full_surface_status(),
        }

    @app.get("/v1/hermes/readiness")
    async def hermes_readiness(request: Request) -> dict[str, Any]:
        require_api(request)
        return hermes_readiness_payload()

    @app.get("/v1/financial-system/readiness")
    async def financial_readiness(request: Request) -> dict[str, Any]:
        require_api(request)
        return await financial_system_readiness(
            runtime,
            full_runtime=build_full_runtime() if _hermes_full_enabled() else full_runtime,
            full_mode_enabled=_hermes_full_enabled(),
            control_token_configured=bool(
                str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
                or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
            ),
            ai_status=ai_status_payload(),
        )

    @app.get("/v1/desktop/financial-manager/catalog")
    async def desktop_financial_manager_catalog(request: Request) -> dict[str, Any]:
        require_api(request)
        return _financial_catalog_payload(runtime)

    @app.get("/v1/desktop/financial-manager/status")
    async def desktop_financial_manager_status(request: Request) -> dict[str, Any]:
        require_api(request)
        return await _financial_status_payload(runtime)

    @app.post("/v1/desktop/financial-manager/query")
    async def desktop_financial_manager_query(request: Request) -> dict[str, Any]:
        require_api(request)
        return await _financial_query_payload(runtime, dict(await request.json() or {}))

    @app.post("/v1/desktop/financial-manager/intent")
    async def desktop_financial_manager_intent(request: Request) -> dict[str, Any]:
        ok, reason = control_authorized(request)
        if not ok:
            raise HTTPException(503 if reason == "control token is not configured" else 401, detail=reason)
        return await _financial_intent_payload(runtime, dict(await request.json() or {}))

    @app.get("/v1/hermes/toolsets")
    async def hermes_toolsets(request: Request) -> dict[str, Any]:
        require_api(request)
        return {
            "object": "list",
            "active": "finance_safe",
            "data": [
                {"name": "finance_safe", "implementation": "aiask_native", "default": True},
                {"name": "hermes_full", "implementation": "aiask_native", "enabled": _hermes_full_enabled(), "toolset": GENERAL_FULL_TOOLSET},
            ],
        }

    @app.get("/v1/hermes/tools")
    async def hermes_tools(request: Request) -> dict[str, Any]:
        return tool_catalog_payload(require_full(request), implementation="aiask_native")

    @app.get("/v1/hermes/config")
    async def hermes_config(request: Request) -> dict[str, Any]:
        full = require_full(request)
        return {
            "object": "aiask.hermes_config",
            "home": os.getenv("AIASK_AGENT_HOME", ""),
            "toolset": full.tool_registry.policy_engine.toolset,
            "workspace_roots": list(full.tool_registry.policy_engine.policy.workspace_roots),
            "secrets_redacted": True,
        }

    @app.get("/v1/hermes/sessions")
    async def hermes_sessions(request: Request, user_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {
            "object": "list",
            "implementation": "aiask_native",
            "data": _session_summary_payload(runtime, intent_store=intent_executor.store, user_id=user_id, limit=limit),
        }

    @app.post("/v1/responses")
    async def responses(request: Request) -> Any:
        require_api(request)
        payload = await request.json()
        selected, mode = select_runtime(dict(payload or {}), request)
        result = await selected.run(
            _messages_from_responses_payload(dict(payload or {})),
            session_id=payload.get("session_id") or request.headers.get("X-AIASK-Session-Id"),
            user_id=payload.get("user_id") or request.headers.get("X-AIASK-User-Id"),
            stream=bool(payload.get("stream", False)),
        )
        response_payload = _responses_payload(result, model=str(payload.get("model") or selected.model))
        response_payload["metadata"]["mode"] = mode
        if bool(payload.get("stream", False)):
            return StreamingResponse(response_sse(result, model=str(payload.get("model") or selected.model)), media_type="text/event-stream")
        return response_payload

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Any:
        require_api(request)
        payload = await request.json()
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise HTTPException(400, detail="messages must be an array")
        selected, mode = select_runtime(dict(payload or {}), request)
        result = await selected.run(
            [dict(item) for item in messages if isinstance(item, dict)],
            session_id=payload.get("session_id") or request.headers.get("X-AIASK-Session-Id"),
            user_id=payload.get("user_id") or request.headers.get("X-AIASK-User-Id"),
            stream=bool(payload.get("stream", False)),
        )
        response_payload = _chat_completion_payload(result, model=str(payload.get("model") or selected.model))
        response_payload["aiask"]["mode"] = mode
        if bool(payload.get("stream", False)):
            return StreamingResponse(chat_completion_sse(result, model=str(payload.get("model") or selected.model)), media_type="text/event-stream")
        return response_payload

    @app.get("/v1/responses/{response_id}")
    async def response_get(request: Request, response_id: str) -> dict[str, Any]:
        require_api(request)
        payload = runtime.session_store.get_response(response_id)
        if payload is None:
            raise HTTPException(404, detail=f"response not found: {response_id}")
        return {"object": "response", **payload}

    @app.delete("/v1/responses/{response_id}")
    async def response_delete(request: Request, response_id: str) -> dict[str, Any]:
        require_api(request)
        return {"id": response_id, "object": "response.deleted", "deleted": runtime.session_store.delete_response(response_id)}

    @app.get("/v1/runs/{run_id}/events")
    async def run_events(request: Request, run_id: str, after: int = 0) -> StreamingResponse:
        require_api(request)
        events = runtime.session_store.list_run_events(run_id, after_event_id=after)
        return StreamingResponse(sse_events([_normalize_run_event(event) for event in events]), media_type="text/event-stream")

    @app.get("/v1/runs/{run_id}/events/stream")
    async def run_events_stream(request: Request, run_id: str, after: int = 0) -> StreamingResponse:
        return await run_events(request, run_id, after=after)

    @app.get("/v1/runs/{run_id}")
    async def run_get(request: Request, run_id: str) -> dict[str, Any]:
        require_api(request)
        item = runtime.session_store.get_run(run_id)
        if item is None:
            raise HTTPException(404, detail=f"run not found: {run_id}")
        return {"object": "run", **item}

    @app.post("/v1/runs/{run_id}/cancel")
    async def run_cancel(request: Request, run_id: str) -> dict[str, Any]:
        require_api(request)
        item = runtime.session_store.get_run(run_id)
        if item is None:
            raise HTTPException(404, detail=f"run not found: {run_id}")
        payload = dict(item.get("payload") or {})
        payload["cancelled_at"] = int(time.time())
        runtime.session_store.update_run(run_id, status="cancelled", payload=payload)
        event = runtime.session_store.append_run_event(run_id, "run.cancelled", {"reason": "api_request"})
        return {"object": "run", "run_id": run_id, "status": "cancelled", "event": event}

    @app.post("/v1/runs/{run_id}/stop")
    async def run_stop(request: Request, run_id: str) -> dict[str, Any]:
        return await run_cancel(request, run_id)

    @app.post("/v1/runs/{run_id}/steer")
    async def run_steer(request: Request, run_id: str) -> dict[str, Any]:
        require_api(request)
        item = runtime.session_store.get_run(run_id)
        if item is None:
            raise HTTPException(404, detail=f"run not found: {run_id}")
        payload = await request.json()
        instruction = str(dict(payload or {}).get("instruction") or "").strip()
        if not instruction:
            raise HTTPException(400, detail="instruction is required")
        event = runtime.session_store.append_run_event(run_id, "run.steer", {"instruction": instruction})
        return {"object": "run.steer", "run_id": run_id, "event": event}

    @app.get("/v1/search")
    async def search(request: Request, query: str = "", q: str = "", session_id: str | None = None, user_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        require_api(request)
        return {
            "object": "list",
            "data": runtime.session_store.search(query=query or q, session_id=session_id, user_id=user_id, limit=limit),
        }

    @app.get("/v1/sessions/{session_id}/messages")
    async def session_messages(request: Request, session_id: str, limit: int = 200) -> dict[str, Any]:
        require_api(request)
        return {"object": "list", "session_id": session_id, "data": runtime.session_store.list_session_messages(session_id, limit=limit)}

    @app.get("/intents")
    async def intent_list(request: Request, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_api(request)
        return {"object": "list", "data": intent_executor.store.list(status=status, limit=limit)}

    @app.get("/intents/{intent_id}")
    async def intent_get(request: Request, intent_id: str) -> dict[str, Any]:
        require_api(request)
        result = await runtime.tool_registry.call_tool("agent_action_intent_get", {"intent_id": intent_id})
        if not result.get("success"):
            raise HTTPException(404, detail=result.get("error"))
        return result

    @app.post("/intents")
    async def intent_create(request: Request) -> dict[str, Any]:
        ok, reason = control_authorized(request)
        if not ok:
            raise HTTPException(503 if reason == "control token is not configured" else 401, detail=reason)
        payload = dict(await request.json() or {})
        result = await runtime.tool_registry.call_tool("agent_action_intent_create", payload)
        if not result.get("success"):
            raise HTTPException(400, detail=result.get("error") or "intent create failed")
        return result

    @app.post("/intents/{intent_id}/confirm")
    async def intent_confirm(request: Request, intent_id: str) -> dict[str, Any]:
        ok, reason = control_authorized(request)
        if not ok:
            raise HTTPException(503 if reason == "control token is not configured" else 401, detail=reason)
        return await intent_executor.confirm(intent_id)

    @app.post("/intents/{intent_id}/deny")
    async def intent_deny(request: Request, intent_id: str) -> dict[str, Any]:
        ok, reason = control_authorized(request)
        if not ok:
            raise HTTPException(503 if reason == "control token is not configured" else 401, detail=reason)
        payload = await request.json()
        return await intent_executor.deny(intent_id, reason=payload.get("reason"))

    @app.post("/v1/hermes/admin/tools/{tool_name}")
    async def hermes_tool_call(request: Request, tool_name: str) -> dict[str, Any]:
        full = require_full(request)
        return await full.tool_registry.call_tool(tool_name, dict(await request.json()))

    @app.get("/v1/processes")
    async def processes(request: Request, session_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": ProcessRegistry(runtime.session_store.path).list(session_id=session_id, limit=limit)}

    @app.get("/v1/terminal/backends")
    async def terminal_backends_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": list_backends()}

    @app.get("/v1/terminal/sessions")
    async def terminal_sessions_api(request: Request, limit: int = 200) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": terminal_backend_sessions(state_path=runtime.session_store.path, limit=limit)}

    @app.get("/v1/terminal/backends/{name}/sessions")
    async def terminal_backend_sessions_api(request: Request, name: str, limit: int = 200) -> dict[str, Any]:
        require_full(request)
        backend = str(name or "local").strip().lower()
        data = [
            item
            for item in terminal_backend_sessions(state_path=runtime.session_store.path, limit=limit)
            if str(item.get("backend") or "local") == backend
        ]
        return {"object": "list", "backend": backend, "data": data}

    @app.get("/v1/browser/sessions")
    async def browser_sessions(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": [{"name": "default", "provider": "playwright", "persistent": True}]}

    @app.get("/v1/skills")
    async def skills(request: Request) -> dict[str, Any]:
        require_full(request)
        result = await build_full_runtime().tool_registry.call_tool("agent_skill_manage", {"action": "snapshot"})
        return {"object": "list", "data": dict(result.get("data") or {})}

    @app.post("/v1/skills")
    async def skill_create(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_skill_manage", {"action": "install", **dict(payload or {})})

    @app.patch("/v1/skills/{name}")
    async def skill_update(request: Request, name: str) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_skill_manage", {"action": "update", "name": name, **dict(payload or {})})

    @app.delete("/v1/skills/{name}")
    async def skill_delete(request: Request, name: str) -> dict[str, Any]:
        return await full_tool_call(request, "agent_skill_manage", {"action": "uninstall", "name": name})

    @app.get("/v1/plugins")
    async def plugins(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": NativePluginManager().list()}

    @app.get("/v1/gateway/status")
    async def gateway_status_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return GatewayRuntime(messages=GatewayMessageStore(runtime.session_store.path)).status()

    @app.get("/v1/gateway/platforms")
    async def gateway_platforms_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": GatewayRuntime(messages=GatewayMessageStore(runtime.session_store.path)).list_platforms()}

    @app.get("/v1/gateway/messages")
    async def gateway_messages_api(request: Request, platform: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": GatewayMessageStore(runtime.session_store.path).list(platform=platform, limit=limit)}

    @app.get("/v1/gateway/directory")
    async def gateway_directory_api(request: Request, platform: str | None = None, kind: str | None = None, limit: int = 200) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": GatewayChannelDirectoryStore(runtime.session_store.path).list(platform=platform, kind=kind, limit=limit)}

    @app.post("/v1/gateway/directory/refresh")
    async def gateway_directory_refresh_api(request: Request) -> dict[str, Any]:
        require_full(request)
        data = GatewayChannelDirectoryStore(runtime.session_store.path).refresh(config=GatewayConfigStore())
        return {"object": "gateway.directory_refresh", "data": data}

    @app.post("/v1/gateway/send")
    async def gateway_send_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        data = await DeliveryRouter(messages=GatewayMessageStore(runtime.session_store.path), directory=GatewayChannelDirectoryStore(runtime.session_store.path)).send(
            platform=str(payload.get("platform") or "local"),
            target=str(payload.get("target") or ""),
            message=str(payload.get("message") or ""),
            thread_id=payload.get("thread_id"),
            session_id=payload.get("session_id"),
            user_id=payload.get("user_id"),
            media_paths=[str(item) for item in list(payload.get("media_paths") or [])],
        )
        return {"object": "gateway.message", "data": data}

    @app.post("/v1/gateway/direct-deliver")
    async def gateway_direct_deliver_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        data = await DeliveryRouter(messages=GatewayMessageStore(runtime.session_store.path), directory=GatewayChannelDirectoryStore(runtime.session_store.path)).send(
            platform=str(payload.get("platform") or "local"),
            target=str(payload.get("target") or ""),
            message=str(payload.get("message") or ""),
            thread_id=payload.get("thread_id"),
            session_id=payload.get("session_id"),
            user_id=payload.get("user_id"),
            media_paths=[str(item) for item in list(payload.get("media_paths") or [])],
        )
        data["deliver_mode"] = "direct_platform"
        return {"object": "gateway.direct_delivery", "data": data}

    @app.post("/v1/gateway/messages/{message_id}/retry")
    async def gateway_retry_api(request: Request, message_id: str) -> dict[str, Any]:
        require_full(request)
        data = await DeliveryRouter(messages=GatewayMessageStore(runtime.session_store.path), directory=GatewayChannelDirectoryStore(runtime.session_store.path)).retry(message_id)
        return {"object": "gateway.retry", "data": data}

    @app.post("/v1/gateway/platforms/{platform}/start")
    async def gateway_platform_start_api(request: Request, platform: str) -> dict[str, Any]:
        require_full(request)
        status = GatewayConfigStore().platform_status(normalize_platform(platform))
        return {"object": "gateway.platform", "data": await adapter_for(status).start()}

    @app.post("/v1/gateway/platforms/{platform}/stop")
    async def gateway_platform_stop_api(request: Request, platform: str) -> dict[str, Any]:
        require_full(request)
        status = GatewayConfigStore().platform_status(normalize_platform(platform))
        return {"object": "gateway.platform", "data": await adapter_for(status).stop()}

    @app.get("/v1/gateway/platforms/{platform}/health")
    async def gateway_platform_health_api(request: Request, platform: str) -> dict[str, Any]:
        require_full(request)
        status = GatewayConfigStore().platform_status(normalize_platform(platform))
        data = await adapter_for(status).health()
        data["runtime"] = GatewayRuntime(messages=GatewayMessageStore(runtime.session_store.path)).runtime_status()
        recent = GatewayMessageStore(runtime.session_store.path).list(platform=platform, limit=20)
        data["last_inbound"] = next((item for item in recent if item.get("direction") == "inbound"), None)
        data["last_outbound"] = next((item for item in recent if item.get("direction") == "outbound"), None)
        return {"object": "gateway.platform_health", "data": data}

    @app.post("/v1/gateway/webhooks/{platform}")
    async def gateway_webhook_api(request: Request, platform: str) -> dict[str, Any]:
        require_api(request)
        raw_body = await request.body()
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        if not isinstance(payload, dict):
            raise HTTPException(400, detail="webhook payload must be a JSON object")
        signature = request.headers.get("X-AIASK-Gateway-Signature") or request.headers.get("X-Hub-Signature-256")
        status = GatewayConfigStore().platform_status(normalize_platform(platform))
        adapter_result = await adapter_for(status).handle_inbound(payload=payload, headers=dict(request.headers), body=raw_body)
        item = DeliveryRouter(messages=GatewayMessageStore(runtime.session_store.path)).record_inbound(
            platform=platform,
            payload=dict(adapter_result.get("payload") or payload),
            signature=signature,
            verified=bool(adapter_result.get("verified")),
            adapter_result=adapter_result,
        )
        return {"object": "gateway.inbound", "data": item}

    # ------------------------------------------------------------------
    # Connector Manager & Gateway Daemon endpoints
    # ------------------------------------------------------------------

    @app.get("/v1/connectors")
    async def connectors_list_api(request: Request, type: str | None = None, category: str | None = None) -> dict[str, Any]:
        require_full(request)
        from .connector_manager import ConnectorManager
        mgr = ConnectorManager(
            mcp_aggregator=getattr(runtime, "_mcp_aggregator", None),
            plugin_manager=getattr(runtime, "_plugin_manager", None),
            gateway_config=GatewayConfigStore(),
            gateway_daemon=getattr(app.state, "_daemon", None) if hasattr(app, "state") else None,
        )
        connectors = mgr.list_all()
        if type:
            connectors = [c for c in connectors if c.type == type]
        if category:
            connectors = [c for c in connectors if c.category == category]
        from dataclasses import asdict
        return {"object": "list", "data": [asdict(c) for c in connectors]}

    @app.get("/v1/connectors/summary")
    async def connectors_summary_api(request: Request) -> dict[str, Any]:
        require_full(request)
        from .connector_manager import ConnectorManager
        mgr = ConnectorManager(
            mcp_aggregator=getattr(runtime, "_mcp_aggregator", None),
            plugin_manager=getattr(runtime, "_plugin_manager", None),
            gateway_config=GatewayConfigStore(),
        )
        return {"object": "connector.summary", "data": mgr.summary()}

    @app.get("/v1/connectors/{connector_type}/{name}")
    async def connector_detail_api(request: Request, connector_type: str, name: str) -> dict[str, Any]:
        require_full(request)
        from dataclasses import asdict
        from .connector_manager import ConnectorManager
        mgr = ConnectorManager(
            mcp_aggregator=getattr(runtime, "_mcp_aggregator", None),
            plugin_manager=getattr(runtime, "_plugin_manager", None),
            gateway_config=GatewayConfigStore(),
        )
        connector = mgr.get(f"{connector_type}:{name}")
        if connector is None:
            raise HTTPException(status_code=404, detail=f"Connector not found: {connector_type}/{name}")
        return {"object": "connector.detail", "data": asdict(connector)}

    @app.post("/v1/connectors/{connector_type}/{name}/test")
    async def connector_test_api(request: Request, connector_type: str, name: str) -> dict[str, Any]:
        require_full(request)
        from .connector_manager import ConnectorManager
        mgr = ConnectorManager(
            mcp_aggregator=getattr(runtime, "_mcp_aggregator", None),
            plugin_manager=getattr(runtime, "_plugin_manager", None),
            gateway_config=GatewayConfigStore(),
        )
        connector = mgr.get(f"{connector_type}:{name}")
        if connector is None:
            raise HTTPException(status_code=404, detail=f"Connector not found: {connector_type}/{name}")
        # Basic test: check if configured
        result = {
            "connector_id": f"{connector_type}:{name}",
            "configured": connector.configured,
            "connected": connector.connected,
            "status": connector.status,
            "missing_env": connector.missing_env,
        }
        return {"object": "connector.test", "data": result}

    @app.get("/v1/gateway/daemon/status")
    async def gateway_daemon_status_api(request: Request) -> dict[str, Any]:
        require_full(request)
        from .gateway_daemon import daemon_enabled
        if _daemon is None:
            return {"object": "gateway.daemon", "data": {"enabled": daemon_enabled(), "running": False, "listeners": {}}}
        return {"object": "gateway.daemon", "data": _daemon.status()}

    @app.get("/v1/learning/status")
    async def learning_status_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return LearningLoop(session_store=runtime.session_store, state_path=runtime.session_store.path).status()

    @app.get("/v1/learning/review")
    async def learning_review_api(request: Request, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": LearningLoop(session_store=runtime.session_store, state_path=runtime.session_store.path).review(status=status, limit=limit)}

    @app.post("/v1/learning/apply")
    async def learning_apply_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        proposal = LearningLoop(session_store=runtime.session_store, state_path=runtime.session_store.path).apply(str(payload.get("proposal_id") or ""))
        return {"object": "learning.proposal", "data": proposal}

    @app.get("/v1/rl/environments")
    async def rl_environments_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": RLAtroposManager(runtime.session_store.path).list_environments()}

    @app.get("/v1/rl/config")
    async def rl_config_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.config", "data": RLAtroposManager(runtime.session_store.path).current_config()}

    @app.patch("/v1/rl/config")
    async def rl_config_patch_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        return {"object": "rl.config", "data": RLAtroposManager(runtime.session_store.path).edit_config(dict(payload.get("config") or payload.get("patch") or payload))}

    @app.get("/v1/rl/runs")
    async def rl_runs_api(request: Request, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": RLAtroposManager(runtime.session_store.path).list_runs(limit=limit)}

    @app.post("/v1/rl/runs")
    async def rl_run_create_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        data = RLAtroposManager(runtime.session_store.path).start_training(environment=payload.get("environment"), config_patch=dict(payload.get("config") or {}))
        return {"object": "rl.run", "data": data}

    @app.get("/v1/rl/runs/{run_id}")
    async def rl_run_get_api(request: Request, run_id: str) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.run", "data": RLAtroposManager(runtime.session_store.path).check_status(run_id)}

    @app.post("/v1/rl/runs/{run_id}/stop")
    async def rl_run_stop_api(request: Request, run_id: str) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.run", "data": RLAtroposManager(runtime.session_store.path).stop_training(run_id)}

    @app.get("/v1/rl/runs/{run_id}/results")
    async def rl_run_results_api(request: Request, run_id: str) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.results", "data": RLAtroposManager(runtime.session_store.path).results(run_id)}

    @app.get("/v1/rl/runs/{run_id}/logs")
    async def rl_run_logs_api(request: Request, run_id: str, max_bytes: int = 65536, tail: bool = True) -> dict[str, Any]:
        require_full(request)
        return {"object": "rl.logs", "data": RLAtroposManager(runtime.session_store.path).logs(run_id, max_bytes=max_bytes, tail=tail)}

    @app.post("/v1/plugins")
    async def plugin_upsert(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_plugin_manage", {"action": "upsert", **dict(payload or {})})

    @app.patch("/v1/plugins/{name}")
    async def plugin_toggle(request: Request, name: str) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        action = "enable" if bool(payload.get("enabled", True)) else "disable"
        return await full_tool_call(request, "agent_plugin_manage", {"action": action, "name": name, **payload})

    @app.post("/v1/plugins/{name}/tools/{tool}/test")
    async def plugin_tool_test(request: Request, name: str, tool: str) -> dict[str, Any]:
        require_full(request)
        manager = NativePluginManager()
        plugin = manager.get(name)
        if not plugin:
            raise HTTPException(404, detail=f"plugin not found: {name}")
        if str(tool or "").strip().lower() in {"", "__manifest__", "manifest", "self-test", "self_test"}:
            return _plugin_self_test_payload(plugin, name)
        plugin_name = str(plugin.get("name") or name).replace("-", "_")
        wrapped = f"agent_plugin_{plugin_name}_{str(tool).replace('-', '_')}"
        payload = dict(await request.json() or {})
        try:
            return {"object": "plugin.tool_test", "success": True, "data": await manager.call_tool(wrapped, payload), "error": None}
        except ValueError as exc:
            return {
                "object": "plugin.tool_test",
                "success": False,
                "data": {
                    "plugin": str(plugin.get("name") or name),
                    "tool": tool,
                    "available_tools": [str(item.get("name") or "") for item in _plugin_tools(plugin)],
                    "configured": False,
                },
                "error": str(exc),
                "error_code": "PLUGIN_TOOL_NOT_CONFIGURED",
            }

    @app.get("/v1/plugins/{name}/commands")
    async def plugin_commands(request: Request, name: str) -> dict[str, Any]:
        require_full(request)
        manager = NativePluginManager()
        if not manager.get(name):
            raise HTTPException(404, detail=f"plugin not found: {name}")
        return {"object": "list", "data": manager.list_commands(name)}

    @app.post("/v1/plugins/{name}/commands/{command}/test")
    async def plugin_command_test(request: Request, name: str, command: str) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        try:
            return {"object": "plugin.command_test", "success": True, "data": await NativePluginManager().call_command(name, command, payload), "error": None}
        except ValueError as exc:
            return {
                "object": "plugin.command_test",
                "success": False,
                "data": {"plugin": name, "command": command, "configured": False},
                "error": str(exc),
                "error_code": "PLUGIN_COMMAND_NOT_CONFIGURED",
            }

    @app.get("/v1/mcp/servers")
    async def mcp_servers(request: Request, all: bool = False) -> dict[str, Any]:
        require_api(request)
        return {"object": "list", "data": MCPAggregator().servers_summary(include_all=all)}

    @app.get("/v1/mcp/tools")
    async def mcp_tools(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": MCPAggregator().tools_summary(include_all=all)}

    @app.get("/v1/mcp/resources")
    async def mcp_resources(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": MCPAggregator().resources_summary(include_all=all)}

    @app.get("/v1/mcp/prompts")
    async def mcp_prompts(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": MCPAggregator().prompts_summary(include_all=all)}

    @app.get("/v1/mcp/oauth_status")
    async def mcp_oauth_status(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": MCPAggregator().oauth_status(include_all=all)}

    @app.post("/v1/mcp/register-local")
    async def mcp_register_local(request: Request) -> dict[str, Any]:
        nonlocal full_runtime
        require_full(request)
        payload = dict(await request.json() or {})
        data = MCPAggregator().register_local_server(
            name=payload.get("name"),
            url=payload.get("url"),
            transport=payload.get("transport"),
            domain=payload.get("domain"),
        )
        runtime.refresh_tool_registry()
        full_runtime = None
        return {"object": "mcp.registration", "success": True, "data": data}

    @app.post("/v1/mcp/discover")
    async def mcp_discover(request: Request) -> dict[str, Any]:
        nonlocal full_runtime
        require_full(request)
        payload = dict(await request.json() or {})
        server_name = str(payload.get("server") or "").strip()
        if not server_name:
            raise HTTPException(400, detail="server is required")
        try:
            mcp = MCPAggregator()
            data = await mcp.discover_and_update(server_name)
            runtime.refresh_tool_registry()
            full_runtime = None
            return {"object": "mcp.discovery", "success": True, "data": data}
        except Exception as exc:
            error_code, detail = _classify_mcp_error(exc)
            auth: dict[str, Any] = {}
            try:
                auth = MCPAggregator().auth_readiness(server_name)
            except Exception:
                auth = {}
            discovery_status = "auth_missing" if error_code == "MCP_DISCOVERY_AUTH_REQUIRED" else "discovery_failed"
            return {
                "object": "mcp.discovery",
                "success": False,
                "data": {"server": server_name, "configured": False, "discovery_status": discovery_status, "detail": detail, **auth},
                "error": detail,
                "error_code": error_code,
            }

    @app.post("/v1/mcp/oauth/start")
    async def mcp_oauth_start(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        require_full(request)
        return {"object": "mcp.oauth_start", "data": MCPAggregator().oauth_start(str(payload.get("server") or ""))}

    @app.post("/v1/mcp/oauth/callback")
    async def mcp_oauth_callback(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        result = await full_tool_call(request, "agent_mcp_manage", {"action": "oauth_callback", **payload})
        return {"object": "mcp.oauth_callback", "data": result.get("data")}

    @app.post("/v1/mcp/resources/read")
    async def mcp_resource_read(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        require_full(request)
        server_name = str(payload.get("server") or "")
        try:
            return {
                "object": "mcp.resource",
                "success": True,
                "data": await MCPAggregator().read_resource(server_name, str(payload.get("uri") or "")),
                "error": None,
            }
        except Exception as exc:
            return _mcp_action_error_payload(action="resource", server_name=server_name, exc=exc)

    @app.post("/v1/mcp/prompts/get")
    async def mcp_prompt_get(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        require_full(request)
        server_name = str(payload.get("server") or "")
        try:
            return {
                "object": "mcp.prompt",
                "success": True,
                "data": await MCPAggregator().get_prompt(
                    server_name,
                    str(payload.get("prompt") or payload.get("name") or ""),
                    dict(payload.get("arguments") or {}),
                ),
                "error": None,
            }
        except Exception as exc:
            return _mcp_action_error_payload(action="prompt", server_name=server_name, exc=exc)

    @app.get("/v1/webhooks")
    async def webhooks(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": WebhookStore(runtime.session_store.path).list()}

    @app.post("/v1/webhooks")
    async def webhook_subscribe(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_webhook", {"action": "subscribe", **dict(payload or {})})

    @app.delete("/v1/webhooks/{webhook_id}")
    async def webhook_delete(request: Request, webhook_id: str) -> dict[str, Any]:
        return await full_tool_call(request, "agent_webhook", {"action": "remove", "webhook_id": webhook_id})

    @app.post("/v1/webhooks/{webhook_id}/trigger")
    async def webhook_trigger(request: Request, webhook_id: str) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_webhook", {"action": "trigger", "webhook_id": webhook_id, **dict(payload or {})})

    @app.get("/v1/approvals")
    async def approvals(request: Request, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": ApprovalStore(runtime.session_store.path).list(status=status, limit=limit)}

    @app.post("/v1/approvals/{approval_id}/{decision}")
    async def approval_decide(request: Request, approval_id: str, decision: str) -> dict[str, Any]:
        require_full(request)
        payload = await request.json()
        item = ApprovalStore(runtime.session_store.path).decide(
            approval_id,
            approved=decision == "approve",
            reason=payload.get("reason"),
        )
        if item is None:
            raise HTTPException(404, detail=f"approval not found: {approval_id}")
        return {"object": "approval", **item}

    @app.get("/v1/jobs")
    async def jobs(request: Request) -> dict[str, Any]:
        require_api(request)
        return {"object": "list", "data": runtime.job_store.list()}

    @app.get("/v1/jobs/{job_id}/runs")
    async def job_runs(request: Request, job_id: str, limit: int = 100) -> dict[str, Any]:
        require_api(request)
        return {"object": "list", "job_id": job_id, "data": runtime.job_store.list_runs(job_id, limit=limit)}

    @app.post("/v1/jobs")
    async def job_create(request: Request) -> dict[str, Any]:
        require_api(request)
        payload = await request.json()
        try:
            job = runtime.job_store.create(
                name=str(payload.get("name") or ""),
                prompt=str(payload.get("prompt") or ""),
                schedule=payload.get("schedule"),
                interval_seconds=payload.get("interval_seconds"),
                toolset=str(payload.get("toolset") or "finance_safe"),
                enabled=bool(payload.get("enabled", True)),
                payload={k: payload.get(k) for k in ("script", "skills", "silent_pattern") if k in payload},
            )
        except Exception as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        return {"object": "job", **job}

    @app.patch("/v1/jobs/{job_id}")
    async def job_update(request: Request, job_id: str) -> dict[str, Any]:
        require_api(request)
        payload = await request.json()
        job = runtime.job_store.update(job_id, **dict(payload or {}))
        if not job:
            raise HTTPException(404, detail=f"job not found: {job_id}")
        return {"object": "job", **job}

    @app.delete("/v1/jobs/{job_id}")
    async def job_delete(request: Request, job_id: str) -> dict[str, Any]:
        require_api(request)
        return {"id": job_id, "object": "job.deleted", "deleted": runtime.job_store.delete(job_id)}

    @app.post("/v1/jobs/{job_id}/run")
    async def job_run(request: Request, job_id: str) -> dict[str, Any]:
        require_api(request)
        result = await runtime.scheduler.run_job(job_id)
        if not result.get("success"):
            raise HTTPException(404, detail=result.get("error"))
        return result

    return app


def build_server(
    host: str = "127.0.0.1",
    port: int = 8767,
    *,
    runtime: AgentRuntime | None = None,
    intent_executor: IntentExecutor | None = None,
) -> ThreadingHTTPServer:
    load_project_env()
    if runtime is None:
        default_runtime, default_executor = _build_runtime_and_executor()
        runtime = default_runtime
        intent_executor = intent_executor or default_executor
    if intent_executor is None:
        intent_executor = IntentExecutor(ActionIntentStore())
    full_runtime: AgentRuntime | None = None
    quant_store = QuantResearchStore(runtime.session_store.path)

    def _build_native_full_runtime() -> AgentRuntime:
        nonlocal full_runtime
        if full_runtime is not None:
            return full_runtime
        policy = ToolPolicy(
            toolset=GENERAL_FULL_TOOLSET,
            general_tools_enabled=True,
            workspace_roots=runtime.tool_registry.policy_engine.policy.workspace_roots,
        )
        registry = build_default_tool_registry(
            session_store=runtime.session_store,
            policy_engine=ToolPolicyEngine(policy),
        )
        full_runtime = AgentRuntime(
            model_client=runtime.model_client,
            session_store=runtime.session_store,
            tool_registry=registry,
            model=runtime.model,
            max_iterations=runtime.max_iterations,
            model_timeout_seconds=runtime.model_timeout_seconds,
            tool_timeout_seconds=runtime.tool_timeout_seconds,
            retry_attempts=runtime.retry_attempts,
        )
        return full_runtime

    class AIASKAgentHTTPServer(ThreadingHTTPServer):
        def server_close(self) -> None:
            try:
                if full_runtime is not None:
                    full_runtime.close()
                runtime.close()
            finally:
                super().server_close()

    class AIASKAgentHandler(BaseHTTPRequestHandler):
        server_version = "AIASKAgent/0.1"

        def log_message(self, format: str, *args: Any) -> None:
            if os.getenv("AIASK_AGENT_HTTP_LOGS", "").strip() == "1":
                super().log_message(format, *args)

        def _send_json(self, status: int, payload: Any) -> None:
            body = _json_dumps(payload)
            self.send_response(status)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_sse(self, events: list[dict[str, Any]]) -> None:
            chunks: list[bytes] = []
            for raw_event in events:
                event = _normalize_run_event(raw_event)
                if event.get("id") is not None:
                    chunks.append(f"id: {event['id']}\n".encode("utf-8"))
                if event.get("event"):
                    chunks.append(f"event: {event['event']}\n".encode("utf-8"))
                chunks.append(b"data: ")
                chunks.append(_json_dumps(event))
                chunks.append(b"\n\n")
            body = b"".join(chunks)
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

        def _send_chat_completion_sse(self, result: Any, *, model: str) -> None:
            created = int(time.time())
            events = [
                {
                    "data": {
                        "id": result.response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                    }
                },
                {
                    "data": {
                        "id": result.response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": result.content}, "finish_reason": None}],
                        "aiask": {"session_id": result.session_id, "run_id": result.run_id},
                    }
                },
                {
                    "data": {
                        "id": result.response_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                },
                {"data": "[DONE]"},
            ]
            chunks: list[bytes] = []
            for event in events:
                chunks.append(b"data: ")
                data = event["data"]
                chunks.append(b"[DONE]" if data == "[DONE]" else _json_dumps(data))
                chunks.append(b"\n\n")
            body = b"".join(chunks)
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

        def _send_response_sse(self, result: Any, *, model: str) -> None:
            events = [
                {
                    "event": "response.created",
                    "data": {"id": result.response_id, "status": "in_progress", "model": model},
                },
                {
                    "event": "response.output_text.delta",
                    "data": {"id": result.response_id, "delta": result.content},
                },
                {
                    "event": "response.completed",
                    "data": {"id": result.response_id, "status": result.status, "run_id": result.run_id},
                },
                {"data": "[DONE]"},
            ]
            chunks: list[bytes] = []
            for event in events:
                if event.get("event"):
                    chunks.append(f"event: {event['event']}\n".encode("utf-8"))
                chunks.append(b"data: ")
                data = event["data"]
                chunks.append(b"[DONE]" if data == "[DONE]" else _json_dumps(data))
                chunks.append(b"\n\n")
            body = b"".join(chunks)
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True

        def _send_cors_headers(self) -> None:
            origin = str(self.headers.get("Origin") or "").strip().rstrip("/")
            if origin and origin in _cors_origins():
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    ", ".join(
                        [
                            "Authorization",
                            "Content-Type",
                            "X-AIASK-Agent-Token",
                            "X-AIASK-Agent-Control-Token",
                            "X-AIASK-Local-Control-Token",
                            "X-AIASK-Session-Id",
                            "X-AIASK-User-Id",
                        ]
                    ),
                )

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send_error_json(self, status: int, message: str, *, code: str | None = None) -> None:
            payload = {"error": {"message": message, "type": code or HTTPStatus(status).phrase}}
            self._send_json(status, payload)

        def _api_authorized(self) -> bool:
            bind_host = str(self.server.server_address[0])
            if _is_loopback(bind_host):
                return True
            expected = str(os.getenv("AIASK_AGENT_API_TOKEN", "")).strip()
            if not expected:
                return False
            return _header_token(self, "X-AIASK-Agent-Token") == expected

        def _control_authorized(self) -> tuple[bool, str | None]:
            client_host = str(self.client_address[0])
            bind_host = str(self.server.server_address[0])
            if not _is_loopback(client_host) or not _is_loopback(bind_host):
                return False, "control endpoint is loopback only"
            expected = (
                str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
                or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
            )
            if not expected:
                return False, "control token is not configured"
            token = _header_token(self, "X-AIASK-Agent-Control-Token", "X-AIASK-Local-Control-Token")
            if token != expected:
                return False, "invalid control token"
            return True, None

        def _hermes_full_authorized(self) -> tuple[bool, str | None]:
            if not _hermes_full_enabled():
                return False, "AIASK native Hermes full mode is not enabled"
            return self._control_authorized()

        def _mode_runtime(self, payload: dict[str, Any]) -> tuple[AgentRuntime | None, str, tuple[bool, str | None]]:
            mode = str(payload.get("mode") or "finance_safe").strip() or "finance_safe"
            if mode == "finance_safe":
                return runtime, mode, (True, None)
            if mode == "hermes_full":
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    return None, mode, (False, reason)
                return _build_native_full_runtime(), mode, (True, None)
            return None, mode, (False, f"unsupported mode: {mode}")

        def do_GET(self) -> None:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query = parse_qs(parsed_url.query)
            if path == "/health":
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "service": "aiask-agent",
                        "host": self.server.server_address[0],
                        "port": self.server.server_address[1],
                    },
                )
                return
            if path == "/health/detailed":
                parity_names = (
                    _build_native_full_runtime().tool_registry.names()
                    if _hermes_full_enabled()
                    else runtime.tool_registry.names()
                )
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "service": "aiask-agent",
                        "host": self.server.server_address[0],
                        "port": self.server.server_address[1],
                        "runtime": {
                            "model": runtime.model,
                            "max_iterations": runtime.max_iterations,
                            "model_timeout_seconds": runtime.model_timeout_seconds,
                            "tool_timeout_seconds": runtime.tool_timeout_seconds,
                        },
                        "tools": {
                            "count": len(runtime.tool_registry.names()),
                            "names": runtime.tool_registry.names(),
                            "toolset": runtime.tool_registry.policy_engine.toolset,
                        },
                        "hermes": {
                            "mode": "aiask_native",
                            "full_mode_enabled": _hermes_full_enabled(),
                            "full_mode_active": full_runtime is not None,
                            "parity": _redact_required_env(parity_summary(parity_names, env=dict(os.environ), gateway_adapters=ADAPTERS.keys())),
                        },
                        "control": {
                            "loopback_only": True,
                            "token_configured": bool(
                                str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
                                or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
                            ),
                        },
                    },
                )
                return
            if path == "/v1/hermes/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    {
                        "object": "aiask.hermes_status",
                        "implementation": "aiask_native",
                        "baseline": HERMES_BASELINE,
                        "embedded_vendor_runtime": False,
                        "full_mode_enabled": _hermes_full_enabled(),
                        "full_mode_active": full_runtime is not None,
                        "parity": parity_summary(
                            full_runtime.tool_registry.names() if full_runtime is not None else runtime.tool_registry.names(),
                            env=dict(os.environ),
                            gateway_adapters=ADAPTERS.keys(),
                        ),
                        "providers": ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path)).status(),
                        "memory": MemoryProviderManager(path=runtime.session_store.path).status(),
                        "acp": ACPManager(mcp=MCPAggregator()).status(),
                        "security": SecurityScanner(policy=runtime.tool_registry.policy_engine.policy).status(),
                        "skill_packs": SkillPackManager(skill_store=SkillStore()).status(),
                    },
                )
                return
            if path == "/v1/capabilities/parity":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                selected = _build_native_full_runtime() if _hermes_full_enabled() else runtime
                self._send_json(200, parity_summary(selected.tool_registry.names(), env=dict(os.environ), gateway_adapters=ADAPTERS.keys()))
                return
            if path == "/v1/hermes/toolsets":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    {
                        "object": "list",
                        "active": "finance_safe",
                        "data": [
                            {"name": "finance_safe", "implementation": "aiask_native", "default": True},
                            {
                                "name": "hermes_full",
                                "implementation": "aiask_native",
                                "enabled": _hermes_full_enabled(),
                                "toolset": GENERAL_FULL_TOOLSET,
                            },
                        ],
                    },
                )
                return
            if path == "/v1/hermes/config":
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                full = _build_native_full_runtime()
                self._send_json(
                    200,
                    {
                        "object": "aiask.hermes_config",
                        "home": os.getenv("AIASK_AGENT_HOME", ""),
                        "toolset": full.tool_registry.policy_engine.toolset,
                        "workspace_roots": list(full.tool_registry.policy_engine.policy.workspace_roots),
                        "secrets_redacted": True,
                    },
                )
                return
            if path == "/v1/hermes/tools":
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                full = _build_native_full_runtime()
                self._send_json(200, build_tool_catalog_payload(full, implementation="aiask_native"))
                return
            if path == "/v1/hermes/sessions":
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                self._send_json(
                    200,
                    {
                        "object": "list",
                        "implementation": "aiask_native",
                        "data": _session_summary_payload(
                            runtime,
                            intent_store=intent_executor.store,
                            user_id=(query.get("user_id") or [None])[0],
                            limit=int((query.get("limit") or ["100"])[0]),
                        ),
                    },
                )
                return
            if path == "/v1/tools":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, build_tool_catalog_payload(runtime))
                return
            if path == "/v1/desktop/settings/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                control_ok, control_reason = self._control_authorized()
                payload = _desktop_settings_status_payload_for_runtime(
                    runtime,
                    endpoint=f"http://{self.server.server_address[0]}:{self.server.server_address[1]}",
                    control_authorized=control_ok,
                    control_reason=control_reason,
                )
                self._send_json(200, payload)
                return
            if path == "/v1/desktop/data/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                codes = (query.get("codes") or [""])[0]
                payload = asyncio.run(
                    _desktop_data_status_payload_for_runtime(
                        runtime,
                        {
                            "codes": [item.strip() for item in str(codes or "").replace("\n", ",").split(",") if item.strip()],
                            "max_stale_days": int((query.get("max_stale_days") or ["5"])[0]),
                        }
                    )
                )
                self._send_json(200, payload)
                return
            if path == "/v1/desktop/users/local-profile":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, local_profile_payload())
                return
            if path == "/v1/desktop/factor-factory/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, asyncio.run(factor_factory_status(limit=int((query.get("limit") or ["50"])[0]))))
                return
            if path == "/v1/desktop/trade-predictions/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    asyncio.run(
                        runtime.tool_registry.call_tool(
                            "agent_trade_prediction_status",
                            {
                                "strategy_id": (query.get("strategy_id") or [None])[0],
                                "stock_code": (query.get("stock_code") or [None])[0],
                                "limit": int((query.get("limit") or ["1000"])[0]),
                            },
                        )
                    ),
                )
                return
            if path == "/v1/desktop/trade-predictions/outcomes":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    asyncio.run(
                        runtime.tool_registry.call_tool(
                            "agent_trade_prediction_outcomes",
                            {
                                "prediction_id": (query.get("prediction_id") or [None])[0],
                                "strategy_id": (query.get("strategy_id") or [None])[0],
                                "stock_code": (query.get("stock_code") or [None])[0],
                                "score_version": (query.get("score_version") or [None])[0],
                                "score_status": (query.get("score_status") or [None])[0],
                                "data_quality_status": (query.get("data_quality_status") or [None])[0],
                                "actual_trading_date_lte": (query.get("actual_trading_date_lte") or [None])[0],
                                "actual_trading_date_gte": (query.get("actual_trading_date_gte") or [None])[0],
                                "limit": int((query.get("limit") or ["100"])[0]),
                            },
                        )
                    ),
                )
                return
            if path == "/v1/desktop/trade-predictions/matrix":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                dimensions = [
                    item.strip()
                    for item in str((query.get("dimensions") or [""])[0] or "").split(",")
                    if item.strip()
                ]
                self._send_json(
                    200,
                    asyncio.run(
                        runtime.tool_registry.call_tool(
                            "agent_trade_prediction_matrix",
                            {
                                "strategy_id": (query.get("strategy_id") or [None])[0],
                                "stock_code": (query.get("stock_code") or [None])[0],
                                "score_version": (query.get("score_version") or [None])[0],
                                "dimensions": dimensions,
                                "limit": int((query.get("limit") or ["1000"])[0]),
                            },
                        )
                    ),
                )
                return
            if path == "/v1/desktop/stock-radar/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    asyncio.run(
                        runtime.tool_registry.call_tool(
                            "agent_stock_radar_status",
                            {
                                "run_id": (query.get("run_id") or [None])[0],
                                "limit": int((query.get("limit") or ["20"])[0]),
                            },
                        )
                    ),
                )
                return
            if path == "/v1/desktop/stock-radar/candidates":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                min_score_raw = (query.get("min_score") or [None])[0]
                self._send_json(
                    200,
                    asyncio.run(
                        runtime.tool_registry.call_tool(
                            "agent_stock_radar_candidates",
                            {
                                "run_id": (query.get("run_id") or [None])[0],
                                "tier": (query.get("tier") or [None])[0],
                                "symbol": (query.get("symbol") or [None])[0],
                                "min_score": float(min_score_raw) if min_score_raw not in {None, ""} else None,
                                "limit": int((query.get("limit") or ["100"])[0]),
                            },
                        )
                    ),
                )
                return
            if path == "/v1/desktop/stock-radar/digest":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                channels = [
                    item.strip()
                    for item in str((query.get("channels") or ["wecom,telegram"])[0]).split(",")
                    if item.strip()
                ]
                self._send_json(
                    200,
                    asyncio.run(
                        runtime.tool_registry.call_tool(
                            "agent_stock_radar_digest",
                            {
                                "run_id": (query.get("run_id") or [None])[0],
                                "limit": int((query.get("limit") or ["20"])[0]),
                                "channels": channels,
                            },
                        )
                    ),
                )
                return
            if path == "/v1/desktop/workbench/summary":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    _workbench_summary_payload(
                        runtime,
                        intent_store=intent_executor.store,
                        user_id=(query.get("user_id") or [None])[0],
                        session_limit=int((query.get("session_limit") or ["8"])[0]),
                        run_limit=int((query.get("run_limit") or ["8"])[0]),
                    ),
                )
                return
            if path == "/v1/desktop/runs":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    _desktop_runs_payload(
                        runtime,
                        session_id=(query.get("session_id") or [None])[0],
                        status=(query.get("status") or [None])[0],
                        limit=int((query.get("limit") or ["100"])[0]),
                    ),
                )
                return
            if path == "/v1/ai/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, _ai_status_payload_for_runtime(runtime))
                return
            if path == "/v1/ai/models":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, asyncio.run(_ai_models_payload_for_runtime(runtime)))
                return
            if path == "/v1/desktop/quant/presets":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, quant_adapter.quant_presets())
                return
            if path == "/v1/desktop/financial-manager/catalog":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, _financial_catalog_payload(runtime))
                return
            if path == "/v1/desktop/financial-manager/status":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, asyncio.run(_financial_status_payload(runtime)))
                return
            if path.startswith("/v1/desktop/quant/research-runs/"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                parts = path.strip("/").split("/")
                research_id = parts[4] if len(parts) >= 5 else ""
                if path.endswith("/report"):
                    report = quant_store.report(research_id)
                    if report is None:
                        self._send_error_json(404, f"quant research report not found: {research_id}", code="not_found")
                        return
                    self._send_json(200, report)
                    return
                item = quant_store.get(research_id)
                if item is None:
                    self._send_error_json(404, f"quant research run not found: {research_id}", code="not_found")
                    return
                self._send_json(200, {"object": "aiask.quant_research_run", **item})
                return
            if path == "/v1/toolsets":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                current = runtime.tool_registry.policy_engine.policy
                self._send_json(
                    200,
                    {
                        "object": "list",
                        "active": current.toolset,
                        "general_tools_enabled": current.general_tools_enabled,
                        "workspace_roots": list(current.workspace_roots),
                        "data": [
                            {"name": "finance_safe", "default": current.toolset == "finance_safe"},
                            {
                                "name": GENERAL_FULL_TOOLSET,
                                "enabled": current.toolset == GENERAL_FULL_TOOLSET and current.general_tools_enabled,
                            },
                        ],
                    },
                )
                return
            if path == "/v1/mcp/servers":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                include_all = _query_bool(query, "all")
                self._send_json(200, {"object": "list", "data": MCPAggregator().servers_summary(include_all=include_all)})
                return
            if path in {"/v1/mcp/tools", "/v1/mcp/resources", "/v1/mcp/prompts", "/v1/mcp/oauth_status"}:
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                include_all = _query_bool(query, "all")
                mcp = MCPAggregator()
                if path == "/v1/mcp/tools":
                    data = mcp.tools_summary(include_all=include_all)
                elif path == "/v1/mcp/resources":
                    data = mcp.resources_summary(include_all=include_all)
                elif path == "/v1/mcp/prompts":
                    data = mcp.prompts_summary(include_all=include_all)
                else:
                    data = mcp.oauth_status(include_all=include_all)
                self._send_json(200, {"object": "list", "data": data})
                return
            if path == "/v1/search":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                q = (query.get("query") or query.get("q") or [""])[0]
                self._send_json(
                    200,
                    {
                        "object": "list",
                        "data": runtime.session_store.search(
                            query=q,
                            session_id=(query.get("session_id") or [None])[0],
                            user_id=(query.get("user_id") or [None])[0],
                            limit=int((query.get("limit") or ["20"])[0]),
                        ),
                    },
                )
                return
            if path.startswith("/v1/sessions/") and path.endswith("/messages"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                parts = path.strip("/").split("/")
                session_id = parts[2] if len(parts) >= 3 else ""
                self._send_json(
                    200,
                    {
                        "object": "list",
                        "session_id": session_id,
                        "data": runtime.session_store.list_session_messages(
                            session_id,
                            limit=int((query.get("limit") or ["200"])[0]),
                        ),
                    },
                )
                return
            if path.startswith("/v1/runs/") and (path.endswith("/events") or path.endswith("/events/stream")):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                run_id = path.strip("/").split("/")[2]
                last_id = int(self.headers.get("Last-Event-ID") or (query.get("after") or ["0"])[0] or 0)
                events = runtime.session_store.list_run_events(run_id, after_event_id=last_id)
                self._send_sse(events)
                return
            if path.startswith("/v1/runs/"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                run_id = path.rsplit("/", 1)[-1].strip()
                item = runtime.session_store.get_run(run_id)
                if item is None:
                    self._send_error_json(404, f"run not found: {run_id}", code="not_found")
                    return
                self._send_json(200, {"object": "run", **item})
                return
            if path == "/v1/jobs":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, {"object": "list", "data": runtime.job_store.list()})
                return
            if path.startswith("/v1/jobs/") and path.endswith("/runs"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                job_id = path.strip("/").split("/")[2]
                limit = int((query.get("limit") or ["100"])[0])
                self._send_json(200, {"object": "list", "job_id": job_id, "data": runtime.job_store.list_runs(job_id, limit=limit)})
                return
            if path == "/intents":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(
                    200,
                    {
                        "object": "list",
                        "data": intent_executor.store.list(
                            status=(query.get("status") or [None])[0],
                            limit=int((query.get("limit") or ["100"])[0]),
                        ),
                    },
                )
                return
            if path.startswith("/intents/"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                intent_id = path.split("/")[2] if len(path.split("/")) > 2 else ""
                result = asyncio.run(
                    runtime.tool_registry.call_tool("agent_action_intent_get", {"intent_id": intent_id})
                )
                self._send_json(200 if result.get("success") else 404, result)
                return
            if path.startswith("/v1/responses/"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                response_id = path.rsplit("/", 1)[-1].strip()
                payload = runtime.session_store.get_response(response_id)
                if payload is None:
                    self._send_error_json(404, f"response not found: {response_id}", code="not_found")
                    return
                self._send_json(200, {"object": "response", **payload})
                return
            self._send_error_json(404, "not found", code="not_found")

        def do_DELETE(self) -> None:
            path = urlparse(self.path).path
            if not self._api_authorized():
                self._send_error_json(401, "unauthorized", code="unauthorized")
                return
            if path.startswith("/v1/responses/"):
                response_id = path.rsplit("/", 1)[-1].strip()
                deleted = runtime.session_store.delete_response(response_id)
                self._send_json(200, {"id": response_id, "object": "response.deleted", "deleted": deleted})
                return
            if path.startswith("/v1/jobs/"):
                job_id = path.rsplit("/", 1)[-1].strip()
                deleted = runtime.job_store.delete(job_id)
                self._send_json(200, {"id": job_id, "object": "job.deleted", "deleted": deleted})
                return
            self._send_error_json(404, "not found", code="not_found")

        def do_PATCH(self) -> None:
            path = urlparse(self.path).path
            try:
                payload = _read_json(self)
            except ValueError as exc:
                self._send_error_json(400, str(exc), code="invalid_request")
                return
            if not self._api_authorized():
                self._send_error_json(401, "unauthorized", code="unauthorized")
                return
            if path.startswith("/v1/jobs/"):
                job_id = path.rsplit("/", 1)[-1].strip()
                job = runtime.job_store.update(job_id, **payload)
                if not job:
                    self._send_error_json(404, f"job not found: {job_id}", code="not_found")
                    return
                self._send_json(200, {"object": "job", **job})
                return
            if path == "/v1/desktop/users/local-profile":
                profile = save_local_profile(payload)
                self._send_json(200, profile)
                return
            self._send_error_json(404, "not found", code="not_found")

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                payload = _read_json(self)
            except ValueError as exc:
                self._send_error_json(400, str(exc), code="invalid_request")
                return

            if path == "/v1/chat/completions":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                messages = payload.get("messages")
                if not isinstance(messages, list):
                    self._send_error_json(400, "messages must be an array", code="invalid_request")
                    return
                selected_runtime, mode, auth = self._mode_runtime(payload)
                if not auth[0] or selected_runtime is None:
                    status = 503 if auth[1] in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, auth[1] or "unauthorized", code="mode_unauthorized")
                    return
                model = str(payload.get("model") or selected_runtime.model)
                try:
                    result = asyncio.run(
                        selected_runtime.run(
                            [dict(item) for item in messages if isinstance(item, dict)],
                            session_id=payload.get("session_id") or self.headers.get("X-AIASK-Session-Id"),
                            user_id=payload.get("user_id") or self.headers.get("X-AIASK-User-Id"),
                            stream=bool(payload.get("stream", False)),
                        )
                    )
                except Exception as exc:
                    self._send_error_json(500, str(exc), code="agent_error")
                    return
                if bool(payload.get("stream", False)):
                    self._send_chat_completion_sse(result, model=model)
                    return
                response_payload = _chat_completion_payload(result, model=model)
                response_payload["aiask"]["mode"] = mode
                self._send_json(200, response_payload)
                return

            if path == "/v1/responses":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                messages = _messages_from_responses_payload(payload)
                selected_runtime, mode, auth = self._mode_runtime(payload)
                if not auth[0] or selected_runtime is None:
                    status = 503 if auth[1] in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, auth[1] or "unauthorized", code="mode_unauthorized")
                    return
                model = str(payload.get("model") or selected_runtime.model)
                try:
                    result = asyncio.run(
                        selected_runtime.run(
                            messages,
                            session_id=payload.get("session_id") or self.headers.get("X-AIASK-Session-Id"),
                            user_id=payload.get("user_id") or self.headers.get("X-AIASK-User-Id"),
                            stream=bool(payload.get("stream", False)),
                        )
                    )
                except Exception as exc:
                    self._send_error_json(500, str(exc), code="agent_error")
                    return
                if bool(payload.get("stream", False)):
                    self._send_response_sse(result, model=model)
                    return
                response_payload = _responses_payload(result, model=model)
                response_payload["metadata"]["mode"] = mode
                self._send_json(200, response_payload)
                return

            if path.startswith("/v1/tools/"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                tool_name = path.rsplit("/", 1)[-1].strip()
                tool = runtime.tool_registry.get(tool_name)
                metadata = dict(getattr(tool, "metadata", {}) or {}) if tool else {}
                if not _metadata_allows_read_only_desktop_call(metadata, tool_name) and not _is_read_only_desktop_tool(tool_name):
                    self._send_error_json(
                        403,
                        f"tool is not available through the read-only desktop API: {tool_name}",
                        code="tool_forbidden",
                    )
                    return
                result = asyncio.run(runtime.tool_registry.call_tool(tool_name, payload))
                self._send_json(200, result)
                return

            if path == "/v1/desktop/quant/research-runs":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                result = asyncio.run(runtime.tool_registry.call_tool("agent_quant_research_run", payload))
                self._send_json(200, result)
                return

            if path == "/v1/desktop/financial-manager/query":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, asyncio.run(_financial_query_payload(runtime, payload)))
                return

            if path == "/v1/desktop/financial-manager/intent":
                ok, reason = self._control_authorized()
                if not ok:
                    status = 503 if reason == "control token is not configured" else 401
                    self._send_error_json(status, reason or "unauthorized", code="control_unauthorized")
                    return
                self._send_json(200, asyncio.run(_financial_intent_payload(runtime, payload)))
                return

            if path == "/v1/desktop/data/sync-plan":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, asyncio.run(_desktop_data_sync_plan_payload_for_runtime(runtime, payload)))
                return

            if path == "/v1/ai/smoke":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, asyncio.run(_ai_smoke_payload_for_runtime(runtime, payload)))
                return

            if path == "/v1/desktop/users/local-profile":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                self._send_json(200, save_local_profile(payload))
                return

            if path == "/v1/jobs":
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                try:
                    job = runtime.job_store.create(
                        name=str(payload.get("name") or ""),
                        prompt=str(payload.get("prompt") or ""),
                        schedule=payload.get("schedule"),
                        interval_seconds=payload.get("interval_seconds"),
                        toolset=str(payload.get("toolset") or "finance_safe"),
                        enabled=bool(payload.get("enabled", True)),
                    )
                except Exception as exc:
                    self._send_error_json(400, str(exc), code="invalid_request")
                    return
                self._send_json(201, {"object": "job", **job})
                return

            if path == "/intents":
                ok, reason = self._control_authorized()
                if not ok:
                    status = 503 if reason == "control token is not configured" else 401
                    self._send_error_json(status, reason or "unauthorized", code="control_unauthorized")
                    return
                result = asyncio.run(runtime.tool_registry.call_tool("agent_action_intent_create", payload))
                self._send_json(200 if result.get("success") else 400, result)
                return

            if path.startswith("/v1/hermes/admin/tools/"):
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                tool_name = path.rsplit("/", 1)[-1].strip()
                result = asyncio.run(_build_native_full_runtime().tool_registry.call_tool(tool_name, payload))
                self._send_json(200 if result.get("success") else 400, result)
                return

            if path.startswith("/v1/jobs/") and path.endswith("/run"):
                if not self._api_authorized():
                    self._send_error_json(401, "unauthorized", code="unauthorized")
                    return
                job_id = path.strip("/").split("/")[2]
                result = asyncio.run(runtime.scheduler.run_job(job_id))
                self._send_json(200 if result.get("success") else 404, result)
                return

            if path.startswith("/v1/plugins/") and path.endswith("/test"):
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                parts = path.strip("/").split("/")
                if len(parts) >= 6 and parts[3] == "tools":
                    name = parts[2]
                    tool = parts[4]
                    manager = NativePluginManager()
                    plugin = manager.get(name)
                    if not plugin:
                        self._send_error_json(404, f"plugin not found: {name}", code="not_found")
                        return
                    if str(tool or "").strip().lower() in {"", "__manifest__", "manifest", "self-test", "self_test"}:
                        self._send_json(200, _plugin_self_test_payload(plugin, name))
                        return
                    plugin_name = str(plugin.get("name") or name).replace("-", "_")
                    wrapped = f"agent_plugin_{plugin_name}_{str(tool).replace('-', '_')}"
                    try:
                        self._send_json(200, {"object": "plugin.tool_test", "success": True, "data": asyncio.run(manager.call_tool(wrapped, payload)), "error": None})
                    except ValueError as exc:
                        self._send_json(
                            200,
                            {
                                "object": "plugin.tool_test",
                                "success": False,
                                "data": {
                                    "plugin": str(plugin.get("name") or name),
                                    "tool": tool,
                                    "available_tools": [str(item.get("name") or "") for item in _plugin_tools(plugin)],
                                    "configured": False,
                                },
                                "error": str(exc),
                                "error_code": "PLUGIN_TOOL_NOT_CONFIGURED",
                            },
                        )
                    return
                if len(parts) >= 6 and parts[3] == "commands":
                    name = parts[2]
                    command = parts[4]
                    try:
                        self._send_json(200, {"object": "plugin.command_test", "success": True, "data": asyncio.run(NativePluginManager().call_command(name, command, payload)), "error": None})
                    except ValueError as exc:
                        self._send_json(
                            200,
                            {
                                "object": "plugin.command_test",
                                "success": False,
                                "data": {"plugin": name, "command": command, "configured": False},
                                "error": str(exc),
                                "error_code": "PLUGIN_COMMAND_NOT_CONFIGURED",
                            },
                        )
                    return

            if path == "/v1/mcp/resources/read":
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                server_name = str(payload.get("server") or "")
                try:
                    self._send_json(
                        200,
                        {
                            "object": "mcp.resource",
                            "success": True,
                            "data": asyncio.run(MCPAggregator().read_resource(server_name, str(payload.get("uri") or ""))),
                            "error": None,
                        },
                    )
                except Exception as exc:
                    self._send_json(200, _mcp_action_error_payload(action="resource", server_name=server_name, exc=exc))
                return

            if path == "/v1/mcp/prompts/get":
                ok, reason = self._hermes_full_authorized()
                if not ok:
                    status = 503 if reason in {"control token is not configured", "AIASK native Hermes full mode is not enabled"} else 401
                    self._send_error_json(status, reason or "unauthorized", code="hermes_full_unauthorized")
                    return
                server_name = str(payload.get("server") or "")
                try:
                    self._send_json(
                        200,
                        {
                            "object": "mcp.prompt",
                            "success": True,
                            "data": asyncio.run(
                                MCPAggregator().get_prompt(
                                    server_name,
                                    str(payload.get("prompt") or payload.get("name") or ""),
                                    dict(payload.get("arguments") or {}),
                                )
                            ),
                            "error": None,
                        },
                    )
                except Exception as exc:
                    self._send_json(200, _mcp_action_error_payload(action="prompt", server_name=server_name, exc=exc))
                return

            if path.startswith("/intents/") and path.endswith("/confirm"):
                ok, reason = self._control_authorized()
                if not ok:
                    status = 503 if reason == "control token is not configured" else 401
                    self._send_error_json(status, reason or "unauthorized", code="control_unauthorized")
                    return
                intent_id = path.split("/")[2]
                result = asyncio.run(intent_executor.confirm(intent_id))
                self._send_json(200 if result.get("success") else 409, result)
                return

            if path.startswith("/intents/") and path.endswith("/deny"):
                ok, reason = self._control_authorized()
                if not ok:
                    status = 503 if reason == "control token is not configured" else 401
                    self._send_error_json(status, reason or "unauthorized", code="control_unauthorized")
                    return
                intent_id = path.split("/")[2]
                result = asyncio.run(intent_executor.deny(intent_id, reason=payload.get("reason")))
                self._send_json(200 if result.get("success") else 409, result)
                return

            self._send_error_json(404, "not found", code="not_found")

    return AIASKAgentHTTPServer((host, int(port)), AIASKAgentHandler)


def main(argv: list[str] | None = None) -> None:
    _load_local_env_file()
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "tui":
        from .tui import run as run_tui

        run_tui()
        return
    if args_list and args_list[0] == "gateway":
        command = args_list[1] if len(args_list) > 1 else "status"
        gateway = GatewayRuntime()
        if command == "status":
            print(json.dumps(gateway.status(), ensure_ascii=False, indent=2, sort_keys=True))
            return
        if command == "setup":
            store = GatewayConfigStore()
            for platform in ("feishu", "dingtalk", "wecom", "weixin", "email", "webhook", "api_server", "local"):
                store.save_platform(platform, {"enabled": True})
            print(json.dumps(gateway.status(), ensure_ascii=False, indent=2, sort_keys=True))
            return
        if command in {"start", "stop"}:
            state = "running" if command == "start" else "stopped"
            print(json.dumps({"object": "aiask.gateway_command", "command": command, "status": gateway.write_runtime_status(state=state)}, ensure_ascii=False))
            return
        raise SystemExit(f"unsupported gateway command: {command}")
    if args_list and args_list[0] == "doctor":
        full_native = "--full-hermes-native" in args_list
        if full_native:
            temp_store = AgentSessionStore()
            temp_runtime = AgentRuntime(
                session_store=temp_store,
                tool_registry=build_default_tool_registry(
                    session_store=temp_store,
                    policy_engine=ToolPolicyEngine(ToolPolicy(GENERAL_FULL_TOOLSET, True, (os.getcwd(),))),
                ),
            )
            gateway = GatewayRuntime(messages=GatewayMessageStore(temp_runtime.session_store.path))
            rl = RLAtroposManager(temp_runtime.session_store.path)
            parity = parity_summary(temp_runtime.tool_registry.names(), env=dict(os.environ), gateway_adapters=ADAPTERS.keys())
            payload = {
                "object": "aiask.doctor",
                "mode": "full-hermes-native",
                "embedded_vendor_runtime": False,
                "dependencies": {
                    "docker": bool(shutil.which("docker") or importlib.util.find_spec("docker")),
                    "ssh": bool(shutil.which("ssh") or importlib.util.find_spec("asyncssh")),
                    "textual": bool(importlib.util.find_spec("textual")),
                    "atroposlib": bool(importlib.util.find_spec("atroposlib")),
                    "tinker_atropos": bool(importlib.util.find_spec("tinker_atropos")),
                },
                "terminal_backends": list_backends(),
                "gateway": gateway.status(),
                "mcp": MCPAggregator().registration_diagnostics(),
                "rl": rl.readiness(),
                "plugins": NativePluginManager().readiness(),
                "feature_mapping": parity.get("feature_mapping", []),
                "missing_features": parity.get("missing_features", []),
                "implemented_features_count": parity.get("implemented_features_count", 0),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return
        raise SystemExit("unsupported doctor command; use: aiask-agent doctor --full-hermes-native")
    parser = argparse.ArgumentParser(description="Run the AIASK Agent HTTP server.")
    parser.add_argument("--host", default=os.getenv("AIASK_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AIASK_AGENT_PORT", "8767")))
    parser.add_argument("--legacy-http", action="store_true", help="Run the compatibility ThreadingHTTPServer instead of ASGI.")
    args = parser.parse_args(args_list)

    if not _is_loopback(args.host) and not os.getenv("AIASK_AGENT_API_TOKEN"):
        raise SystemExit("AIASK_AGENT_API_TOKEN is required when binding aiask-agent to a non-loopback host")

    if args.legacy_http:
        server = build_server(args.host, args.port)
        print(f"aiask-agent listening on http://{args.host}:{args.port} (legacy-http)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return

    import uvicorn

    print(f"aiask-agent listening on http://{args.host}:{args.port} (fastapi-asgi)", flush=True)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level=os.getenv("AIASK_AGENT_UVICORN_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
