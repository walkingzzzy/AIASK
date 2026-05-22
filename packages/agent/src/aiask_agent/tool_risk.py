from __future__ import annotations

import json
from typing import Any


READ_ONLY_STRATEGY_ACTIONS = frozenset(
    {
        "help",
        "list",
        "detail",
        "review_report",
        "events",
        "review",
        "my_subscriptions",
        "my_strategies",
        "personal_strategy_context",
        "personal_strategy_suggestions",
        "paper_session_get",
        "rank",
        "capabilities",
        "daily_snapshot",
        "daily_snapshots",
        "get_signals",
        "get_forward_returns",
        "get_signal_stats",
        "lifecycle_scan",
        "incubation_overview",
        "closure_review",
        "factory_status",
        "factory_dispatch_status",
        "factory_runs",
        "factory_run_detail",
        "factory_topn_latest",
        "factory_run_topn",
        "execution_audit_verification",
        "incubation_accounts",
        "incubation_metrics",
        "paper_account",
        "paper_orders",
        "paper_nav",
        "incubation_pipeline",
        "risk_events",
        "risk_snapshots",
        "runtime_alerts",
        "runtime_control",
        "promotion_reviews",
        "runtime_cycle_status",
        "domain_events",
        "domain_projection",
        "domain_projection_snapshot",
        "vector_profiles",
        "vector_indexes",
        "vector_index_snapshots",
        "vector_ann_search",
        "vector_health",
        "ai_experiments",
        "task_runs",
    }
)


CONFIRM_REQUIRED_STRATEGY_ACTIONS = frozenset(
    {
        "create",
        "publish",
        "archive",
        "update_metrics",
        "subscribe",
        "unsubscribe",
        "fork_strategy",
        "update_strategy",
        "delete_personal_strategy",
        "paper_session_get_or_create",
        "review_report_recheck",
        "submission_replay",
        "submit",
        "factory_run_once",
        "factory_dispatch_run",
        "execution_audit_acceptance",
        "incubation_sync_run",
        "incubation_pipeline_run",
        "risk_scan_run",
        "risk_recovery",
        "resolve_risk_event",
        "runtime_alert_dispatch_run",
        "runtime_alert_ack",
        "runtime_control_set",
        "promotion_review_run",
        "runtime_cycle_run",
        "domain_projection_rebuild",
        "vector_reconcile",
        "vector_rebuild",
        "vector_cleanup",
        "ai_generate",
        "ai_optimize_personal_strategy",
    }
)

MCP_CONTRACT_METADATA_FIELDS = (
    "input_schema",
    "output_schema",
    "freshness",
    "examples",
    "contract_version",
    "contract_source",
    "source_policy",
    "standard_model",
    "provider_choices",
    "provider_status",
    "quality_gate",
    "reconciliation",
    "form_schema",
)


STRATEGY_ACTION_SIDE_EFFECTS: dict[str, dict[str, Any]] = {
    **{
        action: {
            "level": "read_only",
            "target": f"strategy_manager.{action}",
            "confirmation_required": False,
            "idempotent": True,
        }
        for action in READ_ONLY_STRATEGY_ACTIONS
    },
    **{
        action: {
            "level": "stateful",
            "target": f"strategy_manager.{action}",
            "confirmation_required": True,
            "idempotent": False,
        }
        for action in CONFIRM_REQUIRED_STRATEGY_ACTIONS
    },
}


def classify_strategy_manager_action(action: str | None) -> dict[str, Any]:
    normalized = str(action or "").strip()
    if normalized in STRATEGY_ACTION_SIDE_EFFECTS:
        return dict(STRATEGY_ACTION_SIDE_EFFECTS[normalized])
    return {
        "level": "stateful",
        "target": f"strategy_manager.{normalized or 'unknown'}",
        "confirmation_required": True,
        "idempotent": False,
        "unknown_action": True,
    }


def normalize_side_effect(value: Any, *, target: str = "tool") -> dict[str, Any]:
    if isinstance(value, dict):
        payload = dict(value)
        payload.setdefault("level", "read_only")
        payload.setdefault("target", target)
        payload.setdefault("confirmation_required", False)
        payload.setdefault("idempotent", payload.get("level") == "read_only")
        return payload
    level = str(value or "read_only").strip() or "read_only"
    return {
        "level": level,
        "target": target,
        "confirmation_required": level in {"stateful", "confirm_required"},
        "idempotent": level == "read_only",
    }


def metadata_side_effect(metadata: dict[str, Any] | None, *, target: str = "tool") -> dict[str, Any]:
    return normalize_side_effect(dict(metadata or {}).get("side_effect"), target=target)


def metadata_is_read_only(metadata: dict[str, Any] | None, *, target: str = "tool") -> bool:
    return metadata_side_effect(metadata, target=target).get("level") == "read_only"


def extract_mcp_action(arguments: dict[str, Any] | None) -> str:
    payload = dict(arguments or {})
    action = str(payload.get("action") or "").strip()
    if action:
        return action
    params = payload.get("params")
    if isinstance(params, dict):
        action = str(params.get("action") or "").strip()
        if action:
            return action
    kwargs = payload.get("kwargs")
    if isinstance(kwargs, dict):
        return str(kwargs.get("action") or "").strip()
    if isinstance(kwargs, str) and kwargs.strip().startswith("{"):
        try:
            loaded = json.loads(kwargs)
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            return str(loaded.get("action") or "").strip()
    return ""


def strategy_action_params(arguments: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(arguments or {})
    params = payload.get("params")
    if isinstance(params, dict):
        return dict(params)
    kwargs = payload.get("kwargs")
    if isinstance(kwargs, dict):
        return dict(kwargs)
    if isinstance(kwargs, str) and kwargs.strip().startswith("{"):
        try:
            loaded = json.loads(kwargs)
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            return dict(loaded)
    return {k: v for k, v in payload.items() if k not in {"action", "params", "kwargs"}}


def mcp_tool_metadata(tool: dict[str, Any]) -> dict[str, Any]:
    raw_side_effect = tool.get("side_effect")
    tool_name = str(tool.get("name") or "").strip()
    metadata = {
        "capability": "mcp_financial",
        "category": "mcp_financial",
        "server": tool.get("server"),
    }
    if tool_name == "strategy_manager":
        metadata["side_effect"] = {
            "level": "read_only",
            "target": "strategy_manager",
            "confirmation_required": False,
            "idempotent": True,
            "action_scoped": True,
            "action_levels": {
                action: STRATEGY_ACTION_SIDE_EFFECTS[action]["level"]
                for action in sorted(STRATEGY_ACTION_SIDE_EFFECTS)
            },
            "confirm_required_actions": sorted(CONFIRM_REQUIRED_STRATEGY_ACTIONS),
        }
    else:
        metadata["side_effect"] = normalize_side_effect(raw_side_effect, target=tool_name)
    for field in MCP_CONTRACT_METADATA_FIELDS:
        if tool.get(field) is not None:
            metadata[field] = tool.get(field)
    return metadata


def mcp_call_side_effect(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    raw_side_effect: Any = None,
) -> dict[str, Any]:
    if str(tool_name or "").strip() == "strategy_manager":
        return classify_strategy_manager_action(extract_mcp_action(arguments))
    return normalize_side_effect(raw_side_effect, target=tool_name)
