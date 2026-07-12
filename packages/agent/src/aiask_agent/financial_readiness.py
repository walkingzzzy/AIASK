from __future__ import annotations

import os
from typing import Any

from .capabilities import parity_summary
from .env_config import load_project_env
from .gateway import ADAPTERS
from .mcp_client import MCPAggregator
from .memory_providers import MemoryProviderManager
from .model_client import MockModelClient
from .runtime import AgentRuntime
from .adapters import quant as quant_adapter


LIVE_SMOKE_WORKING_DIRECTORY = "packages/agent"
LIVE_SMOKE_SELF_TEST_COMMAND = r"uv run python ..\..\scripts\ops\live_readiness_smoke.py --self-test --pretty"
LIVE_SMOKE_LIVE_COMMAND = r"uv run python ..\..\scripts\ops\live_readiness_smoke.py --endpoint http://127.0.0.1:8765 --pretty"
LIVE_SMOKE_ENVIRONMENT_NOTE = "Run from packages/agent so the Agent runtime dependencies are loaded; root or system Python may report missing FastAPI/pandas dependencies."
LIVE_SMOKE_CHECKS: tuple[dict[str, Any], ...] = (
    {"name": "health", "method": "GET", "path": "/health/detailed"},
    {"name": "tools", "method": "GET", "path": "/v1/tools"},
    {"name": "financial_readiness", "method": "GET", "path": "/v1/financial-system/readiness"},
    {"name": "workbench_summary", "method": "GET", "path": "/v1/desktop/workbench/summary?session_limit=5&run_limit=5"},
    {"name": "memory_status", "method": "GET", "path": "/v1/desktop/settings/status"},
    {"name": "session_search", "method": "GET", "path": "/v1/search?query=AIASK&limit=5"},
    {"name": "memory_search", "method": "POST", "path": "/v1/tools/agent_memory_search"},
    {"name": "mcp_servers", "method": "GET", "path": "/v1/mcp/servers?all=true"},
    {"name": "mcp_tools", "method": "GET", "path": "/v1/mcp/tools?all=true"},
    {"name": "financial_manager_catalog", "method": "GET", "path": "/v1/desktop/financial-manager/catalog"},
    {"name": "financial_manager_query", "method": "POST", "path": "/v1/desktop/financial-manager/query"},
    {"name": "data_status", "method": "GET", "path": "/v1/desktop/data/status?codes=600519,000001&max_stale_days=5"},
    {"name": "factory_status", "method": "POST", "path": "/v1/tools/agent_factory_status", "observes": ["success", "runtime_enabled", "event_runtime_mode", "daily_run_count", "cycle_count"]},
    {"name": "factory_formal_diagnostics", "method": "POST", "path": "/v1/tools/agent_factory_formal_diagnostics", "observes": ["formal_count", "observe_count", "signal_id_coverage", "hard_gate_histogram", "exit_funnel", "top_blockers"]},
    {"name": "market_temperature_cache", "method": "POST", "path": "/v1/tools/agent_market_temperature_cache_readiness", "observes": ["ready", "status", "blockers", "warnings"]},
    {"name": "market_temperature_forward_validation", "method": "POST", "path": "/v1/tools/agent_market_temperature_forward_validation", "observes": ["benchmark_status", "quality_status", "warnings", "sample_count"]},
    {"name": "quant_research", "method": "POST", "path": "/v1/desktop/quant/research-runs"},
)


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


def _next_action(
    action_id: str,
    title: str,
    detail: str,
    *,
    priority: str = "recommended",
    target_page: str = "readiness-health",
    endpoint: str | None = None,
    env_vars: list[str] | None = None,
    gate: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action_id": action_id,
        "title": title,
        "detail": detail,
        "priority": priority,
        "target_page": target_page,
    }
    if endpoint:
        payload["endpoint"] = endpoint
    if env_vars:
        payload["env_vars"] = list(env_vars)
    if gate:
        payload["gate"] = gate
    return payload


def _build_next_actions(
    *,
    required_gates: list[dict[str, Any]],
    optional_gates: list[dict[str, Any]],
    mcp_diagnostics: dict[str, Any],
    full_mode_enabled: bool,
    control_token_configured: bool,
    status: str,
) -> list[dict[str, Any]]:
    gate_by_name = {str(item.get("name") or ""): item for item in [*required_gates, *optional_gates]}
    actions: list[dict[str, Any]] = []

    ai_gate = gate_by_name.get("ai_model", {})
    if ai_gate.get("status") in {"blocked", "degraded"}:
        actions.append(
            _next_action(
                "configure_model_provider",
                "Configure a real model provider",
                "Set an OpenAI-compatible provider and verify /v1/ai/smoke before judging financial Agent quality.",
                priority="critical" if ai_gate.get("status") == "blocked" else "recommended",
                target_page="settings",
                endpoint="/v1/ai/status",
                env_vars=["AIASK_AGENT_MODEL_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL"],
                gate="ai_model",
            )
        )

    if not control_token_configured or gate_by_name.get("control_plane", {}).get("status") == "blocked":
        actions.append(
            _next_action(
                "set_control_token",
                "Set the Agent control token",
                "Stateful intents, MCP administration, full-mode operations, and approval flows need AIASK_AGENT_CONTROL_TOKEN or AIASK_LOCAL_CONTROL_TOKEN.",
                priority="critical",
                target_page="settings",
                env_vars=["AIASK_AGENT_CONTROL_TOKEN", "AIASK_LOCAL_CONTROL_TOKEN"],
                gate="control_plane",
            )
        )

    database_gate = gate_by_name.get("database", {})
    if database_gate.get("status") == "blocked":
        actions.append(
            _next_action(
                "configure_writable_database",
                "Configure a writable local database",
                "Set AIASK_SQLITE_PATH or AKSHARE_MCP_SQLITE_PATH to a writable SQLite file, then rerun data readiness.",
                priority="critical",
                target_page="data",
                endpoint="/v1/desktop/data/status",
                env_vars=["AIASK_SQLITE_PATH", "AKSHARE_MCP_SQLITE_PATH"],
                gate="database",
            )
        )

    strategy_gate = gate_by_name.get("strategy_factory", {})
    if strategy_gate.get("status") in {"blocked", "degraded"}:
        actions.append(
            _next_action(
                "inspect_strategy_factory",
                "Inspect Strategy Factory readiness",
                "Open the Strategy Factory panel to review status, runs, snapshots, and database/runtime errors before running factory actions.",
                priority="critical" if strategy_gate.get("status") == "blocked" else "recommended",
                target_page="strategy-factory",
                endpoint="/v1/desktop/capabilities",
                gate="strategy_factory",
            )
        )

    semantic_gate = gate_by_name.get("semantic_search", {})
    if semantic_gate.get("status") in {"blocked", "degraded"}:
        actions.append(
            _next_action(
                "verify_semantic_search",
                "Verify memory and session search",
                "Run the read-only memory/session search smoke before relying on Agent recall, run history search, or vector-backed research UX.",
                priority="critical" if semantic_gate.get("status") == "blocked" else "recommended",
                target_page="readiness-health",
                endpoint="/v1/search",
                gate="semantic_search",
            )
        )

    mcp_gate = gate_by_name.get("mcp_aggregation", {})
    missing_auth = [str(item) for item in list(mcp_diagnostics.get("missing_auth_env_vars") or []) if str(item).strip()]
    if missing_auth:
        actions.append(
            _next_action(
                "configure_mcp_auth",
                "Configure MCP authorization",
                "The MCP server is registered but some auth environment variables are missing. Configure them in the Agent process and refresh MCP discovery.",
                priority="recommended",
                target_page="mcp-connectors",
                endpoint="/v1/mcp/tools",
                env_vars=missing_auth,
                gate="mcp_aggregation",
            )
        )
    elif mcp_gate.get("status") != "ready":
        detected_port = str(mcp_diagnostics.get("detected_service_port") or "").strip()
        actions.append(
            _next_action(
                "register_or_discover_mcp",
                "Register or discover the financial MCP server",
                "Use MCP / Connectors to register the local AKShare MCP endpoint and refresh the wrapped Agent tool registry.",
                priority="recommended",
                target_page="mcp-connectors",
                endpoint="/v1/mcp/register-local" if detected_port else "/v1/mcp/discover",
                gate="mcp_aggregation",
            )
        )

    if not full_mode_enabled:
        actions.append(
            _next_action(
                "enable_full_mode_when_needed",
                "Enable full mode only when advanced tools are needed",
                "The default finance_safe mode is intentionally narrow. Enable full mode for plugins, browser, terminal, RL, learning, and MCP administration demos.",
                priority="optional",
                target_page="settings",
                env_vars=["AIASK_AGENT_ENABLE_HERMES_FULL", "AIASK_AGENT_TOOLSET", "AIASK_AGENT_ENABLE_GENERAL_TOOLS"],
                gate="hermes_full_mode",
            )
        )

    if status == "ready":
        actions.insert(
            0,
            _next_action(
                "run_live_financial_workflow",
                "Run one live read-only financial workflow",
                "Start with Financial Manager read-only risk/query, then run Quant Research and confirm the report is completed or explicitly blocked by data freshness.",
                priority="recommended",
                target_page="financial-manager",
                endpoint="/v1/desktop/financial-manager/query",
            ),
        )

    return actions[:8]


def _live_smoke_checklist(next_actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "aiask.live_smoke_checklist",
        "status": "ready" if not any(item.get("priority") == "critical" for item in next_actions) else "blocked",
        "script": "scripts/ops/live_readiness_smoke.py",
        "working_directory": LIVE_SMOKE_WORKING_DIRECTORY,
        "self_test_command": LIVE_SMOKE_SELF_TEST_COMMAND,
        "live_command": LIVE_SMOKE_LIVE_COMMAND,
        "environment_note": LIVE_SMOKE_ENVIRONMENT_NOTE,
        "checks": [dict(item) for item in LIVE_SMOKE_CHECKS],
    }


async def financial_system_readiness(
    runtime: AgentRuntime,
    *,
    full_runtime: AgentRuntime | None = None,
    full_mode_enabled: bool = False,
    control_token_configured: bool = False,
    ai_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    load_project_env()
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
    memory_status = MemoryProviderManager(path=runtime.session_store.path).status()
    memory_providers = [item for item in list(memory_status.get("providers") or []) if isinstance(item, dict)]
    active_memory_provider = str(memory_status.get("active_provider") or memory_status.get("default_provider") or "sqlite")
    active_memory = next((item for item in memory_providers if str(item.get("name") or "") == active_memory_provider), None)
    sqlite_memory = next((item for item in memory_providers if str(item.get("name") or "") == "sqlite"), {})
    vector_memory = next((item for item in memory_providers if str(item.get("name") or "") == "vector"), {})
    memory_probe = await runtime.tool_registry.call_tool(
        "agent_memory_search",
        {"query": "AIASK_READINESS_PROBE", "limit": 1, "_timeout_seconds": 5},
    )
    session_probe_failed = False
    session_probe_count = 0
    session_probe_error: str | None = None
    try:
        session_probe = runtime.session_store.search(query="AIASK_READINESS_PROBE", limit=1)
        session_probe_count = len(session_probe)
    except Exception as exc:
        session_probe_failed = True
        session_probe_error = str(exc)[:160]
    memory_search_ready = bool(memory_probe.get("success"))
    session_search_ready = not session_probe_failed
    semantic_ready = (
        "agent_memory_search" in runtime.tool_registry.names()
        and "agent_session_search" in runtime.tool_registry.names()
        and memory_search_ready
        and session_search_ready
    )
    db_env_snapshot = {key: os.environ.get(key) for key in quant_adapter.DATABASE_ENV_KEYS}
    try:
        factory_status = await runtime.tool_registry.call_tool("agent_factory_status", {"recent_run_limit": 5, "_timeout_seconds": 5})
        factory_runs = await runtime.tool_registry.call_tool("agent_factory_runs", {"limit": 5, "_timeout_seconds": 5})
        review_snapshot = await runtime.tool_registry.call_tool("agent_strategy_review_snapshot", {"limit": 5, "_timeout_seconds": 5})
        factory_diagnostics = await runtime.tool_registry.call_tool(
            "agent_factory_formal_diagnostics",
            {"top_n": 10, "_timeout_seconds": 8},
        )
    finally:
        for key, value in db_env_snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    factory_errors = [
        item
        for item in (factory_status, factory_runs, review_snapshot, factory_diagnostics)
        if item.get("success") is False and str(item.get("error_code") or "") not in {"STRATEGY_FACTORY_DATABASE_UNAVAILABLE", "STRATEGY_FACTORY_DATABASE_RECOVERY"}
    ]
    factory_partial = any(item.get("success") is False for item in (factory_status, factory_runs, review_snapshot, factory_diagnostics))

    # P0-D: production factory probes (L2/L3). Mock infra-ready must not claim production_ready.
    factory_diag_data = dict((factory_diagnostics or {}).get("data") or {}) if isinstance(factory_diagnostics, dict) else {}
    formal_count = int(factory_diag_data.get("formal_count") or 0)
    observe_count = int(factory_diag_data.get("observe_count") or 0)
    incubating_count = int(factory_diag_data.get("incubating_count") or 0)
    signal_id_coverage = factory_diag_data.get("signal_id_coverage")
    orders_total = int(factory_diag_data.get("orders_total") or 0)
    hard_hist = dict(factory_diag_data.get("hard_gate_histogram") or {})
    exit_funnel = dict(factory_diag_data.get("exit_funnel") or {})
    open_positions = int(exit_funnel.get("open_positions") or 0)
    closed_positions = int(exit_funnel.get("closed") or 0)
    top_blockers = list(factory_diag_data.get("top_blockers") or [])
    evidence_gaps = list(factory_diag_data.get("evidence_gaps") or [])
    diagnostics_ok = bool(factory_diagnostics.get("success")) and bool(factory_diag_data.get("ok", True))

    def _probe_status_lineage() -> tuple[str, str]:
        if not diagnostics_ok:
            return "degraded", "factory formal diagnostics unavailable"
        if orders_total <= 0:
            return "degraded", "no paper orders yet; signal lineage coverage not measurable"
        try:
            cov = float(signal_id_coverage) if signal_id_coverage is not None else 0.0
        except Exception:
            cov = 0.0
        if cov < 0.95:
            return "blocked", f"order signal_id coverage={cov:.2%} below 95% floor"
        return "ready", f"order signal_id coverage={cov:.2%}"

    def _probe_exit_continuity() -> tuple[str, str]:
        if not diagnostics_ok:
            return "degraded", "factory formal diagnostics unavailable"
        if open_positions <= 0 and closed_positions <= 0:
            return "degraded", "no trade positions yet; exit continuity not measurable"
        if open_positions > 0 and closed_positions == 0:
            return "blocked", f"open_positions={open_positions} but closed=0 (exit pathway starved)"
        return "ready", f"open={open_positions} closed={closed_positions}"

    def _probe_hard_gate_health() -> tuple[str, str]:
        if not diagnostics_ok:
            return "degraded", "factory formal diagnostics unavailable"
        missing = int(hard_hist.get("missing") or 0)
        bootstrap = int(hard_hist.get("bootstrap_pending") or 0)
        passed = int(hard_hist.get("passed") or 0)
        pool = max(observe_count + formal_count, incubating_count, sum(int(v or 0) for v in hard_hist.values()))
        if pool <= 0:
            return "degraded", "no incubating/formal pool for hard-gate histogram"
        if passed == 0 and (missing + bootstrap) >= max(pool, 1) and observe_count > 0:
            return "blocked", "hard gate fully missing/bootstrap_pending with observe pool present"
        if passed == 0 and observe_count > 0:
            return "degraded", "hard gate has no passed strategies yet"
        return "ready", f"hard_gate passed={passed} missing={missing} bootstrap_pending={bootstrap}"

    def _probe_formal_pipeline() -> tuple[str, str]:
        if not diagnostics_ok:
            return "degraded", "factory formal diagnostics unavailable"
        if formal_count > 0:
            return "ready", f"formal_count={formal_count}"
        if not top_blockers and observe_count > 0:
            return "blocked", "formal=0 and blockers not exposed (unexplainable empty formal pool)"
        if formal_count == 0 and observe_count > 0:
            top = top_blockers[0] if top_blockers else {"code": "unknown", "count": 0}
            return "degraded", f"formal=0; top_blocker={top.get('code')} count={top.get('count')}"
        return "degraded", "formal pool empty (no observe/formal samples)"

    def _probe_evidence_coverage() -> tuple[str, str]:
        if not diagnostics_ok:
            return "degraded", "factory formal diagnostics unavailable"
        trades_total = int(factory_diag_data.get("trades_total") or 0)
        signals_total = int(factory_diag_data.get("signals_total") or 0)
        if trades_total <= 0 and signals_total <= 0 and orders_total <= 0 and (observe_count > 0 or incubating_count > 0):
            return "blocked", "runtime pool present but signals/orders/trades are all zero"
        if evidence_gaps:
            return "degraded", f"evidence_gaps={len(evidence_gaps)}"
        return "ready", f"signals={signals_total} orders={orders_total} trades={trades_total}"

    lineage_status, lineage_detail = _probe_status_lineage()
    exit_status, exit_detail = _probe_exit_continuity()
    hard_status, hard_detail = _probe_hard_gate_health()
    formal_status, formal_detail = _probe_formal_pipeline()
    evidence_status, evidence_detail = _probe_evidence_coverage()

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
            detail="Strategy factory status, runs, review, and formal diagnostics are reachable" if not factory_partial else "Strategy factory is partially reachable or awaiting database/runtime availability",
            evidence={
                "status_success": bool(factory_status.get("success")),
                "runs_success": bool(factory_runs.get("success")),
                "review_success": bool(review_snapshot.get("success")),
                "diagnostics_success": bool(factory_diagnostics.get("success")),
                "error_codes": [str(item.get("error_code") or "") for item in (factory_status, factory_runs, review_snapshot, factory_diagnostics) if item.get("success") is False],
            },
        ),
        _gate(
            "factory_evidence_coverage",
            evidence_status,
            required=True,
            detail=evidence_detail,
            evidence={
                "formal_count": formal_count,
                "observe_count": observe_count,
                "orders_total": orders_total,
                "trades_total": int(factory_diag_data.get("trades_total") or 0),
                "signals_total": int(factory_diag_data.get("signals_total") or 0),
                "evidence_gaps": evidence_gaps[:5],
            },
        ),
        _gate(
            "signal_lineage_coverage",
            lineage_status,
            required=True,
            detail=lineage_detail,
            evidence={
                "signal_id_coverage": signal_id_coverage,
                "orders_total": orders_total,
                "orders_with_signal_id": int(factory_diag_data.get("orders_with_signal_id") or 0),
            },
        ),
        _gate(
            "exit_continuity",
            exit_status,
            required=True,
            detail=exit_detail,
            evidence=dict(exit_funnel),
        ),
        _gate(
            "hard_gate_health",
            hard_status,
            required=True,
            detail=hard_detail,
            evidence={"hard_gate_histogram": hard_hist, "observe_count": observe_count, "formal_count": formal_count},
        ),
        _gate(
            "formal_pipeline",
            formal_status,
            required=True,
            detail=formal_detail,
            evidence={"formal_count": formal_count, "observe_count": observe_count, "top_blockers": top_blockers[:5]},
        ),
        _gate(
            "semantic_search",
            "ready" if semantic_ready else "blocked",
            required=True,
            detail="Memory search and session search probes are callable" if semantic_ready else "Agent memory/session search probes failed; recall and run search UX cannot be trusted yet",
            evidence={
                "active_provider": active_memory_provider,
                "sqlite_provider_status": sqlite_memory.get("status"),
                "memory_tool_registered": "agent_memory_search" in runtime.tool_registry.names(),
                "session_tool_registered": "agent_session_search" in runtime.tool_registry.names(),
                "memory_probe_success": memory_search_ready,
                "memory_probe_count": len(list(((memory_probe.get("data") or {}).get("items") or []) if isinstance(memory_probe.get("data"), dict) else [])),
                "memory_probe_error_code": memory_probe.get("error_code"),
                "session_probe_success": session_search_ready,
                "session_probe_count": session_probe_count,
                "session_probe_error": session_probe_error,
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
            "vector_provider",
            "ready" if vector_memory.get("configured") else "degraded",
            required=False,
            detail="External vector memory provider is configured" if vector_memory.get("configured") else "External vector memory provider is optional; built-in SQLite memory/session search remains the readiness baseline",
            evidence={
                "active_provider": active_memory_provider,
                "configured": bool(vector_memory.get("configured")),
                "status": vector_memory.get("status"),
                "required_env": vector_memory.get("required_env", ["AIASK_VECTOR_MEMORY_URL"]),
                "active_provider_configured": bool((active_memory or {}).get("configured", True)),
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
    is_mock_ai = bool(ai.get("mock"))
    # P0-D5: infrastructure "ready" under mock is never production_ready.
    production_ready = status == "ready" and not is_mock_ai
    next_actions = _build_next_actions(
        required_gates=required_gates,
        optional_gates=optional_gates,
        mcp_diagnostics=mcp_diagnostics,
        full_mode_enabled=full_mode_enabled,
        control_token_configured=control_token_configured,
        status=status,
    )
    if is_mock_ai:
        next_actions = [
            _next_action(
                "replace_mock_model",
                "Replace mock model before production",
                "Mock e2e green does not mean Live production ready. Configure a real OpenAI-compatible provider.",
                priority="critical",
                target_page="settings",
                env_vars=["AIASK_AGENT_MODEL_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL"],
                gate="ai_model",
            ),
            *next_actions,
        ]
    # surface factory next_actions from diagnostics
    for item in list(factory_diag_data.get("next_actions") or [])[:5]:
        code = str(item.get("code") or "factory_action")
        detail = str(item.get("detail") or "")
        if not detail:
            continue
        next_actions.append(
            _next_action(
                f"factory_{code}",
                code.replace("_", " ").title(),
                detail,
                priority="recommended",
                target_page="factory",
                gate="formal_pipeline",
            )
        )
    return {
        "object": "aiask.financial_system_readiness",
        "status": status,
        "production_ready": production_ready,
        "factory_diagnostics": {
            "formal_count": formal_count,
            "observe_count": observe_count,
            "signal_id_coverage": signal_id_coverage,
            "hard_gate_histogram": hard_hist,
            "exit_funnel": exit_funnel,
            "top_blockers": top_blockers[:10],
            "ok": diagnostics_ok,
        },
        "required_gates": required_gates,
        "optional_gates": optional_gates,
        "next_actions": next_actions,
        "live_smoke": _live_smoke_checklist(next_actions),
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
            "v016_delta": parity.get("v016_delta"),
        },
        "disclaimer": "Production readiness excludes brokerage credentials and real trading enablement; all stateful strategy actions still require durable intent confirmation.",
    }
