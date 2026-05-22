from __future__ import annotations

import os
from typing import Any

from .capabilities import parity_summary
from .gateway import ADAPTERS
from .mcp_client import MCPAggregator
from .model_client import MockModelClient
from .runtime import AgentRuntime
from .adapters import quant as quant_adapter


def _env_configured(*keys: str) -> bool:
    return all(str(os.getenv(key, "")).strip() for key in keys)


def _gate(name: str, status: str, *, required: bool, detail: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "required": bool(required),
        "detail": detail,
        "evidence": dict(evidence or {}),
    }


async def financial_system_readiness(
    runtime: AgentRuntime,
    *,
    full_runtime: AgentRuntime | None = None,
    full_mode_enabled: bool = False,
    control_token_configured: bool = False,
    ai_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = full_runtime or runtime
    parity = parity_summary(selected.tool_registry.names(), env=dict(os.environ), gateway_adapters=ADAPTERS.keys())
    db_status = quant_adapter.database_status()
    db_ready = bool(db_status.get("configured") and db_status.get("writable"))
    ai = dict(ai_status or {})
    if not ai:
        provider = str(os.getenv("AIASK_AGENT_MODEL_PROVIDER", "")).strip().lower()
        api_key_configured = bool(str(os.getenv("OPENAI_API_KEY", "")).strip())
        is_mock = provider == "mock" or (not provider and isinstance(runtime.model_client, MockModelClient))
        ai = {
            "provider": provider or ("openai" if api_key_configured else "mock"),
            "configured": is_mock or api_key_configured,
            "mock": is_mock,
            "model": runtime.model,
        }

    mcp = MCPAggregator()
    mcp_diagnostics = mcp.registration_diagnostics()
    db_env_snapshot = {key: os.environ.get(key) for key in quant_adapter.DATABASE_ENV_KEYS}
    try:
        factory_status = await runtime.tool_registry.call_tool("agent_factory_status", {"recent_run_limit": 5, "_timeout_seconds": 5})
        factory_runs = await runtime.tool_registry.call_tool("agent_factory_runs", {"limit": 5, "_timeout_seconds": 5})
        review_snapshot = await runtime.tool_registry.call_tool("agent_strategy_review_snapshot", {"limit": 5, "_timeout_seconds": 5})
    finally:
        for key, value in db_env_snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    factory_errors = [
        item
        for item in (factory_status, factory_runs, review_snapshot)
        if item.get("success") is False and str(item.get("error_code") or "") not in {"STRATEGY_FACTORY_DATABASE_UNAVAILABLE", "STRATEGY_FACTORY_DATABASE_RECOVERY"}
    ]
    factory_partial = any(item.get("success") is False for item in (factory_status, factory_runs, review_snapshot))

    required_gates = [
        _gate(
            "ai_model",
            "ready" if ai.get("configured") and not ai.get("mock") else "degraded" if ai.get("configured") else "blocked",
            required=True,
            detail="OpenAI-compatible model is configured" if ai.get("configured") and not ai.get("mock") else "Mock model is usable for development only" if ai.get("mock") else "AI model credentials are missing",
            evidence={"provider": ai.get("provider"), "model": ai.get("model"), "mock": bool(ai.get("mock"))},
        ),
        _gate(
            "finance_safe_toolset",
            "ready" if "agent_action_intent_create" in runtime.tool_registry.names() and "agent_analyze_stock" in runtime.tool_registry.names() else "blocked",
            required=True,
            detail="Default financial tool surface is registered with durable intents",
            evidence={"tool_count": len(runtime.tool_registry.names()), "toolset": runtime.tool_registry.policy_engine.toolset},
        ),
        _gate(
            "control_plane",
            "ready" if control_token_configured else "blocked",
            required=True,
            detail="Control token is configured for confirm/deny and full-mode actions" if control_token_configured else "Control token is required before stateful actions can be approved",
            evidence={"loopback_only": True, "control_token_configured": control_token_configured},
        ),
        _gate(
            "database",
            "ready" if db_ready else "blocked",
            required=True,
            detail="SQLite database is ready for quant and strategy factory runs" if db_ready else "Configure a writable AIASK_SQLITE_PATH or AKSHARE_MCP_SQLITE_PATH before production runs",
            evidence={"backend": db_status.get("backend"), "path": db_status.get("path"), "writable": db_status.get("writable"), "sources": db_status.get("sources", [])},
        ),
        _gate(
            "strategy_factory",
            "ready" if not factory_partial else "degraded" if db_ready and not factory_errors else "blocked",
            required=True,
            detail="Strategy factory status, runs, and review snapshots are reachable" if not factory_partial else "Strategy factory is partially reachable or awaiting database/runtime availability",
            evidence={
                "status_success": bool(factory_status.get("success")),
                "runs_success": bool(factory_runs.get("success")),
                "review_success": bool(review_snapshot.get("success")),
                "error_codes": [str(item.get("error_code") or "") for item in (factory_status, factory_runs, review_snapshot) if item.get("success") is False],
            },
        ),
        _gate(
            "hermes_code_parity",
            "ready"
            if parity.get("core_code_status") == "present"
            and not parity.get("core_missing_hermes_tools")
            and not parity.get("core_missing_features")
            else "blocked",
            required=True,
            detail="AIASK-native core Hermes code surface is present; Hermes v0.14 delta gaps are tracked separately from financial production gates",
            evidence={
                "strict_status": parity.get("strict_status"),
                "coverage_ratio": parity.get("coverage_ratio"),
                "missing_hermes_tools": len(parity.get("core_missing_hermes_tools") or []),
                "missing_features": len(parity.get("core_missing_features") or []),
                "v014_missing_count": dict(parity.get("v014_delta") or {}).get("missing_count"),
                "v014_partial_count": dict(parity.get("v014_delta") or {}).get("partial_count"),
                "live_unverified_count": parity.get("live_unverified_count"),
            },
        ),
    ]
    optional_gates = [
        _gate(
            "hermes_full_mode",
            "ready" if full_mode_enabled and full_runtime is not None else "degraded" if full_mode_enabled else "blocked",
            required=False,
            detail="Hermes full mode is enabled and instantiated" if full_mode_enabled and full_runtime is not None else "Hermes full mode is optional and remains gated",
            evidence={"enabled": full_mode_enabled, "active": full_runtime is not None},
        ),
        _gate(
            "mcp_aggregation",
            "ready" if mcp_diagnostics.get("configured") and mcp_diagnostics.get("registration_status") == "registered" else "degraded",
            required=False,
            detail="MCP aggregation is registered" if mcp_diagnostics.get("configured") else "MCP config is optional until external tool aggregation is required",
            evidence={
                "configured": mcp_diagnostics.get("configured"),
                "registration_status": mcp_diagnostics.get("registration_status"),
                "discovered_counts": mcp_diagnostics.get("discovered_counts"),
            },
        ),
        _gate(
            "external_providers",
            "ready" if _env_configured("OPENAI_API_KEY") and (os.getenv("AIASK_GATEWAY_WEBHOOK_URL") or os.getenv("AIASK_GATEWAY_WEBHOOK_SECRET")) else "degraded",
            required=False,
            detail="External multimodal and gateway providers are configured" if _env_configured("OPENAI_API_KEY") else "External multimodal/gateway credentials are optional and live-gated",
            evidence={
                "openai": bool(os.getenv("OPENAI_API_KEY")),
                "gateway_webhook": bool(os.getenv("AIASK_GATEWAY_WEBHOOK_URL") or os.getenv("AIASK_GATEWAY_WEBHOOK_SECRET")),
                "homeassistant": _env_configured("HASS_URL", "HASS_TOKEN"),
                "rl": _env_configured("TINKER_API_KEY", "WANDB_API_KEY"),
            },
        ),
    ]
    gates = [*required_gates, *optional_gates]
    blocked_required = [item for item in required_gates if item["status"] == "blocked"]
    degraded_required = [item for item in required_gates if item["status"] == "degraded"]
    status = "blocked" if blocked_required else "degraded" if degraded_required else "ready"
    return {
        "object": "aiask.financial_system_readiness",
        "status": status,
        "production_ready": status == "ready",
        "required_gates": required_gates,
        "optional_gates": optional_gates,
        "summary": {
            "required_total": len(required_gates),
            "required_ready": sum(1 for item in required_gates if item["status"] == "ready"),
            "required_degraded": len(degraded_required),
            "required_blocked": len(blocked_required),
            "optional_ready": sum(1 for item in optional_gates if item["status"] == "ready"),
            "optional_degraded": sum(1 for item in optional_gates if item["status"] == "degraded"),
        },
        "parity": {
            "strict_status": parity.get("strict_status"),
            "code_status": parity.get("code_status"),
            "core_code_status": parity.get("core_code_status"),
            "live_status": parity.get("live_status"),
            "coverage_ratio": parity.get("coverage_ratio"),
            "complete_ratio": parity.get("complete_ratio"),
            "live_unverified_count": parity.get("live_unverified_count"),
            "v014_delta": parity.get("v014_delta"),
        },
        "disclaimer": "Production readiness excludes brokerage credentials and real trading enablement; all stateful strategy actions still require durable intent confirmation.",
    }
