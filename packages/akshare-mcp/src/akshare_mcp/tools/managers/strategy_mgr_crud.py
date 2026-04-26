"""Strategy manager CRUD action handlers."""

import asyncio
import os
import random
import time
from datetime import datetime, timezone
from uuid import uuid4

from ...storage import get_db
from ...utils import fail, ok
from ...services.strategy_lifecycle_shared.presentation import (
    build_favorite_state,
    build_owner_state,
    build_paper_session_state,
    build_strategy_presentation,
    is_admin_actor,
    is_personal_strategy,
    normalize_actor_roles,
)
from .strategy_mgr_helpers import (
    build_factory_capability_health,
    build_incubation_overview,
    compute_nav_series,
    get_latest_quality_report,
    list_quality_reports,
    normalize_quality_report_contract,
    normalize_status_alias,
    parse_bool,
    normalize_time_filter,
    update_status,
)

import logging

logger = logging.getLogger(__name__)


def _load_signal_quality_registry_snapshot():
    try:
        from ...services.signal_quality_registry import (
            get_default_signal_quality_registry,
            get_default_signal_quality_registry_snapshot,
        )

        registry = get_default_signal_quality_registry()
        snapshot = dict(get_default_signal_quality_registry_snapshot() or {})
        return {
            **snapshot,
            "snapshot": snapshot,
            "drift": dict(registry.drift_check() or {}),
            "recent_probability": list(registry.recent_probability(5)),
            "recent_sentiment": list(registry.recent_sentiment(5)),
            "recent_factor": list(registry.recent_factor(5)),
        }
    except Exception:
        return {}


def _execution_audit_entity_chain_available(db) -> bool:
    required_methods = (
        "list_strategy_paper_orders",
        "list_strategy_paper_trades",
        "list_strategy_trade_positions",
        "list_strategy_trade_position_fills",
        "get_strategy_trade_audit_summary",
        "get_paper_nav_rows",
    )
    return all(hasattr(db, method) for method in required_methods)


async def _resolved(value):
    return value


def _trimmed(value) -> str:
    return str(value or "").strip()


def _actor_context(params: dict) -> tuple[str | None, list[str]]:
    actor_id = _trimmed(params.get("actor_id") or params.get("user_id")) or None
    actor_roles = normalize_actor_roles(
        params.get("actor_roles")
        or params.get("roles")
        or params.get("actor_role")
        or params.get("role")
    )
    return actor_id, actor_roles


def _strategy_source_strategy_id(strategy: dict | None) -> str | None:
    payload = dict(strategy or {})
    metadata = dict(dict(payload.get("params") or {}).get("metadata") or {})
    value = _trimmed(metadata.get("source_strategy_id"))
    return value or None


def _ensure_personal_strategy_mutation_allowed(
    strategy: dict | None,
    *,
    actor_id: str | None,
    actor_roles: list[str],
) -> str | None:
    payload = dict(strategy or {})
    if not payload:
        return "Strategy not found"
    if is_admin_actor(actor_roles):
        return None
    if not actor_id:
        return "actor_id is required"
    if _trimmed(payload.get("author_id")) != actor_id:
        return "only the strategy owner can modify this strategy"
    if not is_personal_strategy(payload):
        return "market strategies are read-only"
    return None


async def _load_personal_strategy_surface_state(
    db,
    strategy: dict | None,
    *,
    actor_id: str | None,
    actor_roles: list[str],
) -> tuple[dict, dict, dict]:
    payload = dict(strategy or {})
    owner_state = build_owner_state(payload, actor_id=actor_id, actor_roles=actor_roles)
    is_favorited = False
    if actor_id and payload.get("id") and hasattr(db, "is_subscribed"):
        try:
            is_favorited = bool(await db.is_subscribed(str(payload.get("id")), actor_id))
        except Exception:
            is_favorited = False
    favorite_state = build_favorite_state(actor_id=actor_id, is_favorited=is_favorited)
    paper_session = None
    if actor_id and payload.get("id") and hasattr(db, "get_strategy_paper_session"):
        try:
            paper_session = await db.get_strategy_paper_session(str(payload.get("id")), actor_id)
        except Exception:
            paper_session = None
    paper_session_state = build_paper_session_state(paper_session, actor_id=actor_id)
    return owner_state, favorite_state, paper_session_state


_PERSONAL_STRATEGY_FOCUS_FIELDS = (
    "name",
    "description",
    "params",
    "factor_weights",
    "tags",
)
_PERSONAL_STRATEGY_AI_MODIFICATION_TASK_NAME = "personal_strategy_ai_modification"
_PERSONAL_STRATEGY_AI_MODIFICATION_TASK_SCOPE = "strategy_market.personal_strategy_ai_modification"


def _clean_string_list(items) -> list[str]:
    return list(dict.fromkeys(
        [str(item or "").strip() for item in list(items or []) if str(item or "").strip()]
    ))


def _normalize_personal_strategy_focus_fields(value) -> list[str]:
    if isinstance(value, str):
        candidates = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        candidates = []
    focus_fields: list[str] = []
    allowed = set(_PERSONAL_STRATEGY_FOCUS_FIELDS)
    for item in candidates:
        normalized = _trimmed(item).lower()
        if normalized and normalized in allowed and normalized not in focus_fields:
            focus_fields.append(normalized)
    return focus_fields


def _sanitize_personal_strategy_snapshot(strategy: dict | None) -> dict:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    return {
        "id": _trimmed(payload.get("id")) or None,
        "name": _trimmed(payload.get("name")) or "",
        "description": _trimmed(payload.get("description")) or "",
        "strategy_type": _trimmed(payload.get("strategy_type")) or None,
        "status": _trimmed(payload.get("status")) or None,
        "author_id": _trimmed(payload.get("author_id")) or None,
        "tags": _clean_string_list(payload.get("tags")),
        "params": params,
        "factor_weights": dict(payload.get("factor_weights") or {}),
        "metadata": dict(params.get("metadata") or {}),
    }


def _compact_personal_strategy_value(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return value


def _build_personal_strategy_structured_diff(plan: dict) -> list[dict]:
    before = dict(plan.get("before") or {})
    after = dict(plan.get("after") or {})
    reasons = {
        str(item.get("field")): str(item.get("reason") or "")
        for item in list(plan.get("suggestions") or [])
        if isinstance(item, dict) and item.get("field")
    }
    fields = list(plan.get("changed_fields") or [])
    return [
        {
            "field": field,
            "changed": before.get(field) != after.get(field),
            "before": _compact_personal_strategy_value(before.get(field)),
            "after": _compact_personal_strategy_value(after.get(field)),
            "reason": reasons.get(field) or "根据当前个人策略草稿生成的 AI 修改建议。",
            "risk_level": "medium" if field in {"params", "factor_weights"} else "low",
        }
        for field in fields
    ]


def _build_personal_strategy_impact_summary(plan: dict) -> list[dict]:
    labels = {
        "name": "策略名称",
        "description": "策略说明",
        "params": "策略参数",
        "factor_weights": "因子权重",
        "tags": "策略标签",
    }
    return [
        {
            "field": field,
            "label": labels.get(field, field),
            "impact": (
                "会影响后续运行参数、回测和质检输入。"
                if field == "params"
                else "会影响因子暴露解释和后续比较。"
                if field == "factor_weights"
                else "主要影响展示、检索和人工复核。"
            ),
        }
        for field in list(plan.get("changed_fields") or [])
    ]


def _normalize_personal_strategy_apply_payload(value) -> dict:
    if not isinstance(value, dict):
        return {}
    allowed = set(_PERSONAL_STRATEGY_FOCUS_FIELDS)
    payload = {
        field: value.get(field)
        for field in allowed
        if field in value
    }
    if "tags" in payload:
        payload["tags"] = _clean_string_list(payload.get("tags"))
    if "params" in payload:
        payload["params"] = dict(payload.get("params") or {})
    if "factor_weights" in payload:
        payload["factor_weights"] = dict(payload.get("factor_weights") or {})
    return payload


def _overlay_personal_strategy_plan_apply_payload(plan: dict, apply_payload: dict) -> dict:
    payload = _normalize_personal_strategy_apply_payload(apply_payload)
    if not payload:
        return plan
    before = dict(plan.get("before") or {})
    after = {
        **dict(plan.get("after") or {}),
        **payload,
    }
    changed_fields = [
        field for field in _PERSONAL_STRATEGY_FOCUS_FIELDS
        if before.get(field) != after.get(field)
    ]
    suggestions = [
        {
            "field": field,
            "action_kind": "persist_update",
            "effect": "stateful",
            "reason": "用户确认应用的 AI 修改提案字段。",
            "before": before.get(field),
            "after": after.get(field),
        }
        for field in changed_fields
    ]
    return {
        **plan,
        "after": after,
        "apply_payload": {
            field: after.get(field)
            for field in changed_fields
        },
        "changed_fields": changed_fields,
        "suggestions": suggestions,
        "summary": (
            f"将提交个人策略 AI 修改：{'、'.join(changed_fields)}。"
            if changed_fields
            else "当前 AI 修改提案没有可提交字段。"
        ),
    }


def _build_personal_strategy_rollback_entry(
    strategy_id: str,
    before: dict,
    *,
    proposal_id: str | None = None,
    task_run_id=None,
) -> dict:
    updates = {
        field: before.get(field)
        for field in _PERSONAL_STRATEGY_FOCUS_FIELDS
        if field in before
    }
    return {
        "available": True,
        "label": "回滚到 AI 修改前快照",
        "manager_action": "update_strategy",
        "params": {
            "strategy_id": strategy_id,
            "updates": updates,
            "run_post_update_pipeline": True,
        },
        "bff_endpoint": {
            "method": "PATCH",
            "path": f"/strategy-market/{strategy_id}",
            "body": {
                **updates,
                "run_post_update_pipeline": True,
            },
        },
        "proposal_id": proposal_id,
        "task_run_id": task_run_id,
    }


def _build_personal_strategy_ai_review_payload(plan: dict, *, proposal_id: str | None = None) -> dict:
    resolved_proposal_id = proposal_id or f"aim_{uuid4().hex[:16]}"
    structured_diff = _build_personal_strategy_structured_diff(plan)
    return {
        "proposal_id": resolved_proposal_id,
        "update_state": "advisory",
        "state_label": "建议态",
        "advisory_only": True,
        "persisted": False,
        "confirmation_required": True,
        "structured_diff": structured_diff,
        "impact_summary": _build_personal_strategy_impact_summary(plan),
        "risk_prompts": list(plan.get("risk_notes") or []),
        "available_decisions": [
            {
                "decision": "confirm",
                "label": "确认应用",
                "effect": "stateful",
                "target_update_state": "submitted_update",
            },
            {
                "decision": "reject",
                "label": "拒绝",
                "effect": "readonly",
                "target_update_state": "rejected",
            },
            {
                "decision": "suggestion_only",
                "label": "仅生成建议",
                "effect": "advisory",
                "target_update_state": "advisory",
            },
        ],
    }


def _build_personal_strategy_ai_modification_record(
    *,
    strategy_id: str,
    actor_id: str | None,
    actor_roles: list[str],
    proposal_id: str | None,
    update_state: str,
    result: str,
    summary: str | None,
    changed_fields: list,
    task_run_id=None,
    experiment_id: str | None = None,
    rollback_entry: dict | None = None,
    recorded_at: str | None = None,
) -> dict:
    return {
        "dto_version": "strategy_market.personal_ai_modification_record.v1",
        "strategy_id": strategy_id,
        "proposal_id": proposal_id,
        "operator_id": actor_id,
        "operator_roles": list(actor_roles or []),
        "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(),
        "update_state": update_state,
        "result": result,
        "summary": summary,
        "changed_fields": list(changed_fields or []),
        "task_run_id": task_run_id,
        "experiment_id": experiment_id,
        "rollback_entry": rollback_entry,
    }


def _extract_personal_strategy_ai_modification_record(task_run: dict | None) -> dict | None:
    row = dict(task_run or {})
    if not row:
        return None
    result = dict(row.get("result") or {})
    record = result.get("last_ai_modification") or result.get("ai_modification")
    if isinstance(record, dict):
        return {
            **record,
            "task_run_id": record.get("task_run_id") or row.get("id"),
        }
    task_name = _trimmed(row.get("task_name"))
    if task_name == "ai_optimize_personal_strategy":
        return _build_personal_strategy_ai_modification_record(
            strategy_id=_trimmed(row.get("strategy_id")),
            actor_id=dict(row.get("payload") or {}).get("actor_id"),
            actor_roles=[],
            proposal_id=None,
            update_state="submitted_update",
            result="legacy_ai_optimize_completed",
            summary=dict(row.get("result") or {}).get("summary"),
            changed_fields=list(dict(row.get("result") or {}).get("changed_fields") or []),
            task_run_id=row.get("id"),
            experiment_id=dict(row.get("result") or {}).get("experiment_id"),
            rollback_entry=None,
            recorded_at=row.get("completed_at") or row.get("started_at"),
        )
    return None


async def _load_latest_personal_strategy_ai_modification(db, strategy_id: str) -> dict | None:
    if not strategy_id or not hasattr(db, "list_strategy_task_runs"):
        return None
    try:
        rows = await db.list_strategy_task_runs(strategy_id=strategy_id, limit=20)
    except Exception:
        return None
    for row in list(rows or []):
        task_name = _trimmed(dict(row or {}).get("task_name"))
        task_scope = _trimmed(dict(row or {}).get("task_scope"))
        if task_name in {_PERSONAL_STRATEGY_AI_MODIFICATION_TASK_NAME, "ai_optimize_personal_strategy"} or task_scope == _PERSONAL_STRATEGY_AI_MODIFICATION_TASK_SCOPE:
            record = _extract_personal_strategy_ai_modification_record(row)
            if record:
                return record
    return None


async def _record_personal_strategy_ai_modification(
    db,
    *,
    strategy_id: str,
    actor_id: str | None,
    actor_roles: list[str],
    proposal_id: str | None,
    update_state: str,
    result: str,
    summary: str | None,
    changed_fields: list,
    rollback_entry: dict | None = None,
    payload: dict | None = None,
) -> tuple[dict, dict | None]:
    recorded_at = datetime.now(timezone.utc).isoformat()
    record = _build_personal_strategy_ai_modification_record(
        strategy_id=strategy_id,
        actor_id=actor_id,
        actor_roles=actor_roles,
        proposal_id=proposal_id,
        update_state=update_state,
        result=result,
        summary=summary,
        changed_fields=list(changed_fields or []),
        rollback_entry=rollback_entry,
        recorded_at=recorded_at,
    )
    task_run = None
    if hasattr(db, "save_strategy_task_run"):
        task_run = await db.save_strategy_task_run({
            "strategy_id": strategy_id,
            "task_name": _PERSONAL_STRATEGY_AI_MODIFICATION_TASK_NAME,
            "task_scope": _PERSONAL_STRATEGY_AI_MODIFICATION_TASK_SCOPE,
            "task_key": f"{strategy_id}:{proposal_id or update_state}",
            "status": "success",
            "trace_id": f"ai_mod_{uuid4().hex[:12]}",
            "payload": {
                "strategy_id": strategy_id,
                "actor_id": actor_id,
                "actor_roles": list(actor_roles or []),
                "proposal_id": proposal_id,
                "update_state": update_state,
                **dict(payload or {}),
            },
            "result": {
                "update_state": update_state,
                "result": result,
                "summary": summary,
                "changed_fields": list(changed_fields or []),
                "rollback_entry": rollback_entry,
                "last_ai_modification": record,
            },
            "started_at": recorded_at,
            "completed_at": recorded_at,
        })
        if isinstance(task_run, dict) and task_run.get("id") is not None:
            record = {
                **record,
                "task_run_id": task_run.get("id"),
                "rollback_entry": {
                    **rollback_entry,
                    "task_run_id": task_run.get("id"),
                } if isinstance(rollback_entry, dict) else rollback_entry,
            }
    return record, task_run


def _build_personal_strategy_context(
    strategy: dict | None,
    *,
    actor_id: str | None,
    actor_roles: list[str],
    owner_state: dict | None,
    favorite_state: dict | None,
    paper_session_state: dict | None,
    last_ai_modification: dict | None = None,
) -> dict:
    snapshot = _sanitize_personal_strategy_snapshot(strategy)
    mutation_error = _ensure_personal_strategy_mutation_allowed(
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    factor_weights = dict(snapshot.get("factor_weights") or {})
    numeric_factor_weights = {
        key: float(value)
        for key, value in factor_weights.items()
        if isinstance(value, (int, float))
    }
    source_strategy_id = _trimmed(snapshot.get("metadata", {}).get("source_strategy_id")) or None
    default_focus = ["description", "factor_weights", "tags"]
    return {
        "strategy_id": snapshot.get("id"),
        "strategy_name": snapshot.get("name"),
        "strategy_type": snapshot.get("strategy_type"),
        "status": snapshot.get("status"),
        "actor_id": actor_id,
        "actor_roles": list(actor_roles or []),
        "owner_state": dict(owner_state or {}),
        "favorite_state": dict(favorite_state or {}),
        "paper_session_state": dict(paper_session_state or {}),
        "personal_strategy": is_personal_strategy(strategy or {}),
        "editable": bool(dict(owner_state or {}).get("editable")),
        "source_strategy_id": source_strategy_id,
        "draft_snapshot": snapshot,
        "draft_stats": {
            "description_present": bool(snapshot.get("description")),
            "tag_count": len(list(snapshot.get("tags") or [])),
            "param_key_count": len(dict(snapshot.get("params") or {})),
            "factor_weight_key_count": len(factor_weights),
            "factor_weight_abs_sum": round(sum(abs(value) for value in numeric_factor_weights.values()), 6),
        },
        "mutation_guard": {
            "allowed": mutation_error is None,
            "reason": mutation_error,
        },
        "last_ai_modification": dict(last_ai_modification or {}) or None,
        "action_modes": [
            {
                "action_kind": "view",
                "effect": "readonly",
                "available": True,
                "label": "查看当前个人策略上下文",
            },
            {
                "action_kind": "generate_update_suggestion",
                "effect": "advisory",
                "available": mutation_error is None,
                "label": "生成修改建议",
                "reason": mutation_error,
                "default_focus_fields": default_focus,
            },
            {
                "action_kind": "optimize",
                "effect": "stateful",
                "available": mutation_error is None,
                "label": "执行 AI 优化",
                "reason": mutation_error,
            },
            {
                "action_kind": "persist_update",
                "effect": "stateful",
                "available": mutation_error is None,
                "label": "保存到个人策略草稿",
                "reason": mutation_error,
            },
        ],
    }


def _build_personal_strategy_change_plan(
    strategy: dict | None,
    params: dict,
    *,
    mode: str,
    actor_id: str | None,
    actor_roles: list[str],
    owner_state: dict | None,
    favorite_state: dict | None,
    paper_session_state: dict | None,
) -> dict:
    snapshot = _sanitize_personal_strategy_snapshot(strategy)
    before = {
        "name": snapshot.get("name"),
        "description": snapshot.get("description"),
        "params": dict(snapshot.get("params") or {}),
        "factor_weights": dict(snapshot.get("factor_weights") or {}),
        "tags": list(snapshot.get("tags") or []),
    }
    after = {
        "name": before.get("name"),
        "description": before.get("description"),
        "params": dict(before.get("params") or {}),
        "factor_weights": dict(before.get("factor_weights") or {}),
        "tags": list(before.get("tags") or []),
    }
    focus_fields = _normalize_personal_strategy_focus_fields(params.get("focus_fields"))
    focus_enabled = set(focus_fields or _PERSONAL_STRATEGY_FOCUS_FIELDS)
    objective = _trimmed(params.get("objective") or params.get("goal") or params.get("target"))
    instructions = _trimmed(params.get("instructions") or params.get("prompt") or params.get("reason"))
    advisory_label = "AI优化" if mode == "optimize" else "AI建议"
    advisory_tail = objective or instructions or "补齐风险约束、执行纪律和样本跟踪。"
    change_reasons: dict[str, str] = {}

    if "description" in focus_enabled:
        current_description = _trimmed(before.get("description"))
        next_description = current_description
        advisory_note = f"{advisory_label}：{advisory_tail}"
        if not current_description:
            next_description = advisory_note
        elif advisory_note not in current_description:
            next_description = f"{current_description}｜{advisory_note}"
        if next_description != current_description:
            after["description"] = next_description
            change_reasons["description"] = "补齐当前草稿的 AI 说明与执行提示。"

    if "factor_weights" in focus_enabled:
        factor_weights = dict(before.get("factor_weights") or {})
        numeric_factor_weights = {
            key: float(value)
            for key, value in factor_weights.items()
            if isinstance(value, (int, float))
        }
        if numeric_factor_weights:
            total = sum(abs(value) for value in numeric_factor_weights.values()) or 0.0
            if total > 0:
                normalized_factor_weights = {
                    key: round(value / total, 6)
                    for key, value in numeric_factor_weights.items()
                }
                if any(
                    abs(normalized_factor_weights[key] - numeric_factor_weights.get(key, 0.0)) > 1e-6
                    for key in normalized_factor_weights
                ):
                    after["factor_weights"] = {
                        **factor_weights,
                        **normalized_factor_weights,
                    }
                    change_reasons["factor_weights"] = "将数值因子权重归一化，便于后续比较与执行。"

    if "params" in focus_enabled:
        params_payload = dict(before.get("params") or {})
        metadata = dict(params_payload.get("metadata") or {})
        metadata_changed = False
        if mode == "optimize":
            next_metadata = {
                **metadata,
                "ai_optimized_at": datetime.now(timezone.utc).isoformat(),
                "ai_optimizer": "strategy_manager.personal_strategy_optimizer",
                "source_strategy_id": metadata.get("source_strategy_id") or snapshot.get("id"),
            }
            metadata_changed = next_metadata != metadata
            metadata = next_metadata
        elif objective or instructions:
            suggestion_meta = {
                "objective": objective or None,
                "instructions": instructions or None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "strategy_manager.personal_strategy_suggestions",
            }
            next_metadata = dict(metadata)
            next_metadata["ai_pending_suggestion"] = suggestion_meta
            metadata_changed = next_metadata != metadata
            metadata = next_metadata
        if metadata_changed:
            params_payload["metadata"] = metadata
            after["params"] = params_payload
            change_reasons["params"] = "补齐 AI 处理上下文，便于后续继续优化或人工复核。"

    if "tags" in focus_enabled:
        tag_marker = "ai_optimized" if mode == "optimize" else "ai_suggested_update"
        next_tags = _clean_string_list([
            *list(before.get("tags") or []),
            "personal_strategy",
            tag_marker,
        ])
        if next_tags != list(before.get("tags") or []):
            after["tags"] = next_tags
            change_reasons["tags"] = "为个人策略补齐 AI 处理标签，便于后续筛选。"

    changed_fields = [
        field for field in ("name", "description", "params", "factor_weights", "tags")
        if before.get(field) != after.get(field)
    ]
    apply_payload = {
        field: after.get(field)
        for field in changed_fields
    }
    suggestions = [
        {
            "field": field,
            "action_kind": "persist_update" if mode == "optimize" else "generate_update_suggestion",
            "effect": "stateful" if mode == "optimize" else "advisory",
            "reason": change_reasons.get(field) or "根据当前个人策略草稿生成的 AI 调整建议。",
            "before": before.get(field),
            "after": after.get(field),
        }
        for field in changed_fields
    ]
    if changed_fields:
        summary = (
            f"{'已生成' if mode == 'suggest' else '将执行'}个人策略调整方案："
            f"{'、'.join(changed_fields)}。"
        )
    else:
        summary = "当前个人策略草稿未发现需要低风险自动调整的字段。"
    risk_notes = [
        "当前结果基于页面已有草稿字段生成，不替代人工研究结论。",
        "默认建议态不会写库；只有显式保存、应用建议、执行 AI 优化，或以 persist 模式调用建议动作时才会落库更新。",
    ]
    if mode == "optimize":
        risk_notes.append("AI 优化会直接写回当前个人策略草稿，请在执行前确认这是你的个人版本。")

    return {
        "strategy_id": snapshot.get("id"),
        "mode": mode,
        "objective": objective or None,
        "instructions": instructions or None,
        "focus_fields": focus_fields,
        "before": before,
        "after": after,
        "apply_payload": apply_payload,
        "changed_fields": changed_fields,
        "summary": summary,
        "suggestions": suggestions,
        "risk_notes": risk_notes,
        "context": _build_personal_strategy_context(
            strategy,
            actor_id=actor_id,
            actor_roles=actor_roles,
            owner_state=owner_state,
            favorite_state=favorite_state,
            paper_session_state=paper_session_state,
        ),
    }


def _personal_strategy_pipeline_warning(step: str, error: str) -> str:
    label_map = {
        "recompile": "DSL/运行契约重编译",
        "backtest": "回测重跑",
        "review_report_recheck": "质检重算",
        "submission_replay": "提交回放",
        "execution_audit_acceptance": "执行审计",
    }
    label = label_map.get(step) or step
    return f"{label}未完成：{error}"


def _extract_personal_strategy_backtest_metrics(result_payload: dict, *, backtest_id: str | None) -> dict:
    payload = dict(result_payload or {})

    def _safe_float(value, default: float = 0.0) -> float:
        try:
            if value is None:
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def _safe_int(value, default: int = 0) -> int:
        try:
            if value is None:
                return int(default)
            return int(float(value))
        except Exception:
            return int(default)

    trade_count = _safe_int(
        payload.get("trade_count")
        if payload.get("trade_count") is not None
        else payload.get("trades_count"),
        0,
    )
    return {
        "backtest_id": backtest_id,
        "total_return": round(_safe_float(payload.get("total_return"), 0.0), 6),
        "annual_return": round(_safe_float(payload.get("annual_return"), 0.0), 6),
        "sharpe_ratio": round(_safe_float(payload.get("sharpe_ratio"), 0.0), 6),
        "max_drawdown": round(_safe_float(payload.get("max_drawdown"), 0.0), 6),
        "win_rate": round(_safe_float(payload.get("win_rate"), 0.0), 6),
        "calmar_ratio": round(_safe_float(payload.get("calmar_ratio"), 0.0), 6),
        "trade_count": trade_count,
        "trades_count": trade_count,
        "final_capital": round(_safe_float(payload.get("final_capital"), 0.0), 4),
        "initial_capital": round(_safe_float(payload.get("initial_capital"), 100000.0), 4),
        "avg_holding_days": round(_safe_float(payload.get("avg_holding_days"), 0.0), 4),
        "sortino_ratio": round(_safe_float(payload.get("sortino_ratio"), 0.0), 6),
        "execution_summary": dict(payload.get("execution_summary") or {}),
        "cost_assumptions": dict(payload.get("cost_assumptions") or {}),
        "backtest_assumptions": {
            "strategy_type": _trimmed(payload.get("strategy")),
            "portfolio_backtest": bool(payload.get("portfolio_backtest")),
        },
        "recomputed_at": datetime.now(timezone.utc).isoformat(),
        "source": "strategy_manager.personal_strategy_post_update_pipeline",
    }


def _select_personal_strategy_update_fields(payload: dict | None) -> dict:
    data = dict(payload or {})
    allowed_fields = (
        "name",
        "description",
        "params",
        "factor_weights",
        "tags",
        "backtest_artifact_id",
    )
    return {
        field: data.get(field)
        for field in allowed_fields
        if field in data
    }


def _personal_strategy_update_changed(strategy: dict | None, updates: dict | None) -> bool:
    current = dict(strategy or {})
    payload = dict(updates or {})
    if not payload:
        return False
    for field, value in payload.items():
        if current.get(field) != value:
            return True
    return False


async def _rerun_personal_strategy_backtest(
    db,
    strategy: dict,
    *,
    history_limit: int = 1200,
) -> dict:
    from ...services.backtest import BacktestEngine
    from ...services.strategy_acceptance_remediation import (
        StrategyAcceptanceRemediationService,
        _strategy_runtime_params,
    )

    strategy_payload = dict(strategy or {})
    strategy_id = _trimmed(strategy_payload.get("id"))
    strategy_type = _trimmed(strategy_payload.get("strategy_type"))
    if not strategy_id:
        return {"status": "skipped", "reason": "strategy_id_missing"}
    if not strategy_type:
        return {"status": "skipped", "reason": "strategy_type_missing"}

    remediation = StrategyAcceptanceRemediationService()
    market_data = await remediation._load_market_data(
        db,
        strategy_payload,
        history_limit=max(250, int(history_limit or 1200)),
    )
    if not market_data:
        return {"status": "skipped", "reason": "market_data_missing"}

    runtime_params = {
        **dict(_strategy_runtime_params(strategy_payload) or {}),
        "strategy_id": strategy_id,
        "strategy_name": strategy_payload.get("name"),
        "target_symbols": list(market_data.keys()),
    }

    raw_result = (
        BacktestEngine.run_backtest(
            next(iter(market_data.keys())),
            next(iter(market_data.values())),
            strategy_type,
            runtime_params,
            return_trades=True,
        )
        if len(market_data) == 1
        else BacktestEngine.run_portfolio_backtest(
            market_data,
            strategy_type,
            runtime_params,
            return_trades=True,
        )
    )
    if not bool(dict(raw_result or {}).get("success")):
        return {
            "status": "failed",
            "reason": _trimmed(dict(raw_result or {}).get("error")) or "backtest_failed",
        }

    result_payload = dict(dict(raw_result or {}).get("data") or raw_result or {})
    trades = list(result_payload.get("trades") or [])
    backtest_id = None
    if hasattr(db, "acquire"):
        try:
            backtest_id = await remediation._persist_generated_backtest(
                db,
                strategy=strategy_payload,
                market_data=market_data,
                result_payload=result_payload,
                trades=trades,
            )
        except Exception as exc:
            logger.warning(
                "strategy_manager personal strategy backtest persistence failed for %s: %s",
                strategy_id,
                exc,
            )
    metrics = _extract_personal_strategy_backtest_metrics(
        result_payload,
        backtest_id=backtest_id,
    )
    if hasattr(db, "save_strategy_metrics"):
        await db.save_strategy_metrics(strategy_id, "backtest", metrics)
    return {
        "status": "completed",
        "backtest_id": backtest_id,
        "target_symbols": list(market_data.keys()),
        "portfolio_backtest": len(market_data) > 1,
        "metrics": metrics,
        "result": result_payload,
    }


async def _recompile_personal_strategy_runtime(db, strategy: dict) -> dict:
    from ...services.strategy_recompile_backfill import build_trend_strategy_recompile_backfill

    strategy_payload = dict(strategy or {})
    current_status = _trimmed(strategy_payload.get("status")).lower()
    synthetic_input = {
        **strategy_payload,
        "status": current_status if current_status in {"submitted", "incubating"} else "submitted",
    }
    result = build_trend_strategy_recompile_backfill(
        synthetic_input,
        backtest_metrics=dict(strategy_payload.get("backtest_metrics") or {}),
        force=True,
    )
    if str(result.get("status") or "").strip().lower() == "skipped":
        return {
            "status": "skipped",
            "reason": result.get("reason"),
            "deterministic_recompile_eligible": bool(result.get("deterministic_recompile_eligible")),
        }
    updated_payload = _select_personal_strategy_update_fields(result.get("updated_payload"))
    if _personal_strategy_update_changed(strategy_payload, updated_payload):
        updated = await db.update_strategy_fields(
            _trimmed(strategy_payload.get("id")),
            updated_payload,
        ) if hasattr(db, "update_strategy_fields") else None
    else:
        updated = strategy_payload
    return {
        "status": str(result.get("status") or "completed"),
        "reason": result.get("reason"),
        "deterministic_recompile_eligible": bool(result.get("deterministic_recompile_eligible")),
        "applied_param_fields": list(result.get("applied_param_fields") or []),
        "preserved_param_fields": list(result.get("preserved_param_fields") or []),
        "updated_strategy": updated or strategy_payload,
        "generated_candidate": dict(result.get("generated_candidate") or {}),
    }


async def _run_personal_strategy_post_update_pipeline(
    db,
    strategy: dict,
) -> tuple[dict, dict, list[str]]:
    from .strategy_mgr_lifecycle import (
        handle_execution_audit_acceptance,
        handle_review_report_recheck,
        handle_submission_replay,
    )

    strategy_payload = dict(strategy or {})
    risk_notes: list[str] = []
    pipeline = {
        "requested": True,
        "overall_status": "completed",
        "recompile": {"status": "skipped", "reason": "not_requested"},
        "backtest": {"status": "skipped", "reason": "not_requested"},
        "review_report_recheck": {"status": "skipped", "reason": "not_requested"},
        "submission_replay": {"status": "skipped", "reason": "not_requested"},
        "execution_audit_acceptance": {"status": "skipped", "reason": "not_requested"},
    }

    try:
        recompile = await _recompile_personal_strategy_runtime(db, strategy_payload)
        pipeline["recompile"] = {
            key: value
            for key, value in dict(recompile or {}).items()
            if key != "updated_strategy"
        }
        strategy_payload = dict(recompile.get("updated_strategy") or strategy_payload)
        if str(recompile.get("status") or "").strip().lower() == "failed":
            risk_notes.append(
                _personal_strategy_pipeline_warning(
                    "recompile",
                    _trimmed(recompile.get("reason")) or "runtime_recompile_failed",
                )
            )
    except Exception as exc:
        pipeline["recompile"] = {"status": "failed", "reason": str(exc)}
        risk_notes.append(_personal_strategy_pipeline_warning("recompile", str(exc)))

    try:
        backtest = await _rerun_personal_strategy_backtest(db, strategy_payload)
        pipeline["backtest"] = backtest
        if str(backtest.get("status") or "").strip().lower() == "failed":
            risk_notes.append(
                _personal_strategy_pipeline_warning(
                    "backtest",
                    _trimmed(backtest.get("reason")) or "backtest_failed",
                )
            )
        elif str(backtest.get("status") or "").strip().lower() == "completed":
            strategy_payload = {
                **strategy_payload,
                "backtest_metrics": dict(backtest.get("metrics") or {}),
            }
    except Exception as exc:
        pipeline["backtest"] = {"status": "failed", "reason": str(exc)}
        risk_notes.append(_personal_strategy_pipeline_warning("backtest", str(exc)))

    try:
        review_report = await handle_review_report_recheck(
            db,
            {"strategy_id": _trimmed(strategy_payload.get("id"))},
        )
        if bool(review_report.get("success")):
            review_payload = dict(review_report.get("data") or {})
            pipeline["review_report_recheck"] = {
                "status": "completed",
                "report_type": review_payload.get("report_type"),
                "quality_gate": dict(review_payload.get("quality_gate") or {}),
                "closure_review": dict(review_payload.get("closure_review") or {}),
            }
        else:
            pipeline["review_report_recheck"] = {
                "status": "failed",
                "reason": review_report.get("error"),
            }
            risk_notes.append(
                _personal_strategy_pipeline_warning(
                    "review_report_recheck",
                    _trimmed(review_report.get("error")) or "review_report_recheck_failed",
                )
            )
    except Exception as exc:
        pipeline["review_report_recheck"] = {"status": "failed", "reason": str(exc)}
        risk_notes.append(_personal_strategy_pipeline_warning("review_report_recheck", str(exc)))

    try:
        replay = await handle_submission_replay(
            db,
            {
                "strategy_id": _trimmed(strategy_payload.get("id")),
                "recheck_reports": False,
            },
        )
        if bool(replay.get("success")):
            replay_payload = dict(replay.get("data") or {})
            pipeline["submission_replay"] = {
                "status": "completed",
                "summary": dict(replay_payload.get("summary") or {}),
                "items": list(replay_payload.get("items") or []),
            }
        else:
            pipeline["submission_replay"] = {
                "status": "failed",
                "reason": replay.get("error"),
            }
            risk_notes.append(
                _personal_strategy_pipeline_warning(
                    "submission_replay",
                    _trimmed(replay.get("error")) or "submission_replay_failed",
                )
            )
    except Exception as exc:
        pipeline["submission_replay"] = {"status": "failed", "reason": str(exc)}
        risk_notes.append(_personal_strategy_pipeline_warning("submission_replay", str(exc)))

    try:
        acceptance = await handle_execution_audit_acceptance(
            db,
            {
                "strategy_id": _trimmed(strategy_payload.get("id")),
                "backfill": True,
            },
        )
        if bool(acceptance.get("success")):
            acceptance_payload = dict(acceptance.get("data") or {})
            pipeline["execution_audit_acceptance"] = {
                "status": "completed",
                "overall_ready": bool(acceptance_payload.get("overall_ready")),
                "acceptance_matrix": dict(acceptance_payload.get("acceptance_matrix") or {}),
                "recommendations": list(acceptance_payload.get("recommendations") or []),
            }
        else:
            pipeline["execution_audit_acceptance"] = {
                "status": "failed",
                "reason": acceptance.get("error"),
            }
            risk_notes.append(
                _personal_strategy_pipeline_warning(
                    "execution_audit_acceptance",
                    _trimmed(acceptance.get("error")) or "execution_audit_acceptance_failed",
                )
            )
    except Exception as exc:
        pipeline["execution_audit_acceptance"] = {"status": "failed", "reason": str(exc)}
        risk_notes.append(_personal_strategy_pipeline_warning("execution_audit_acceptance", str(exc)))

    step_statuses = [
        str(dict(pipeline.get(step) or {}).get("status") or "skipped").strip().lower()
        for step in (
            "recompile",
            "backtest",
            "review_report_recheck",
            "submission_replay",
            "execution_audit_acceptance",
        )
    ]
    if any(status == "failed" for status in step_statuses):
        pipeline["overall_status"] = (
            "completed_with_warnings"
            if any(status == "completed" for status in step_statuses)
            else "failed"
        )
    elif all(status == "skipped" for status in step_statuses):
        pipeline["overall_status"] = "skipped"

    refreshed = await db.get_strategy(_trimmed(strategy_payload.get("id"))) if hasattr(db, "get_strategy") else strategy_payload
    return pipeline, refreshed or strategy_payload, risk_notes


def _resolve_strategy_status_filter(raw_status, *, default: str = "visible"):
    raw = str(raw_status or default).strip()
    if not raw:
        raw = default
    tokens = [item.strip() for item in raw.replace("|", ",").split(",") if item.strip()]
    lowered = [token.lower() for token in tokens]
    if any(token in {"all", "*"} for token in lowered):
        return None
    if len(lowered) == 1 and lowered[0] in {"visible", "active", "market", "marketplace"}:
        return ["incubating", "listed"]
    normalized = [normalize_status_alias(token) for token in tokens]
    normalized = [token for token in normalized if token]
    if not normalized:
        return ["incubating", "listed"]
    return normalized[0] if len(normalized) == 1 else normalized


async def _load_similar_vector_profiles(db, strategy_id: str) -> list:
    try:
        from ...services.vector_platform import get_strategy_vector_platform
        return await get_strategy_vector_platform().find_similar_profiles(db, strategy_id, limit=5)
    except Exception as exc:
        logger.warning("strategy_manager.detail similar profiles failed for %s: %s", strategy_id, exc)
        return []


async def _load_vector_profiles(db, strategy_id: str, *, limit: int = 3) -> list:
    try:
        from ...services.vector_platform import get_strategy_vector_platform

        return await get_strategy_vector_platform().list_profiles(
            db,
            strategy_id=strategy_id,
            limit=max(1, min(int(limit or 3), 20)),
        )
    except Exception as exc:
        logger.warning("strategy_manager.detail vector profiles failed for %s: %s", strategy_id, exc)
        if hasattr(db, "list_strategy_vector_profiles"):
            return await db.list_strategy_vector_profiles(strategy_id=strategy_id, limit=max(1, min(int(limit or 3), 20)))
        return []


async def _load_latest_vector_index_snapshot(db, index_name: str = "strategy_behavior") -> dict | None:
    try:
        from ...services.vector_platform import get_strategy_vector_platform

        rows = await get_strategy_vector_platform().list_index_snapshots(
            db,
            index_name=index_name,
            limit=1,
        )
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("strategy_manager.detail latest vector snapshot failed for %s: %s", index_name, exc)
        if hasattr(db, "get_latest_strategy_vector_index_snapshot"):
            return await db.get_latest_strategy_vector_index_snapshot(index_name)
        return None


def _extract_strategy_market_summary_value(strategy: dict, key: str):
    value = strategy.get(key)
    if value not in (None, ""):
        return value
    params = strategy.get("params")
    if isinstance(params, dict):
        return params.get(key)
    return None


def _normalize_strategy_status_value(value) -> str:
    raw = _trimmed(value)
    if not raw:
        return ""
    normalized = normalize_status_alias(raw)
    return _trimmed(normalized or raw).lower()


def _incubation_surface_issue_count(value) -> int:
    if isinstance(value, (list, tuple, set)):
        return len([item for item in value if _trimmed(item)])
    return 0


def _incubation_surface_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _trimmed(value).lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _closure_snapshot_overview_payload(snapshot: dict | None, *, strategy_status: str) -> dict:
    payload = dict((snapshot or {}).get("snapshot") or {})
    metadata = dict((snapshot or {}).get("metadata") or {})
    snapshot_status = _normalize_strategy_status_value(metadata.get("strategy_status"))
    if snapshot_status and strategy_status and snapshot_status != strategy_status:
        return {}
    return payload


def _resolve_incubation_surface_stage(
    *,
    strategy_status: str,
    paper_account: dict | None = None,
    latest_pipeline_snapshot: dict | None = None,
    overview: dict | None = None,
    incubation_account: dict | None = None,
) -> tuple[str, str]:
    account_payload = dict(paper_account or {})
    account_stage = _trimmed(account_payload.get("incubation_stage"))
    if account_stage:
        return account_stage, "paper_account"

    account_status = _normalize_strategy_status_value(account_payload.get("status"))
    promotion_candidate = bool(account_payload.get("promotion_candidate"))
    if account_payload:
        if account_status in {"retired"}:
            return "promoted", "paper_account_status"
        if account_status in {"frozen", "failed", "archived"}:
            return "failed", "paper_account_status"
        if account_status == "guarded":
            return "observe", "paper_account_status"
        if account_status == "active":
            return ("candidate" if promotion_candidate else "warmup"), "paper_account_status"

    for value, source in (
        ((latest_pipeline_snapshot or {}).get("pipeline_stage"), "pipeline"),
        ((overview or {}).get("pipeline_stage"), "overview"),
        ((incubation_account or {}).get("stage"), "binding"),
    ):
        normalized = _trimmed(value)
        if normalized:
            return normalized, source
    if strategy_status == "listed":
        return "promoted", "status_fallback"
    if strategy_status == "incubating":
        return "observe", "status_fallback"
    return "not_started", "status_fallback"


def _build_strategy_incubation_surface(
    strategy: dict,
    *,
    paper_account: dict | None = None,
    latest_pipeline_snapshot: dict | None = None,
    overview: dict | None = None,
    incubation_account: dict | None = None,
    latest_metric: dict | None = None,
) -> dict:
    strategy_status = _normalize_strategy_status_value(strategy.get("status"))
    actual_account = dict(paper_account or {})
    snapshot = dict(latest_pipeline_snapshot or {})
    overview_payload = dict(overview or {})
    account = dict(incubation_account or {})
    metric = dict(latest_metric or {})
    pipeline_stage, stage_source = _resolve_incubation_surface_stage(
        strategy_status=strategy_status,
        paper_account=actual_account,
        latest_pipeline_snapshot=snapshot,
        overview=overview_payload,
        incubation_account=account,
    )
    snapshot_summary = dict(snapshot.get("summary") or {})
    hard_gate_result = dict(snapshot.get("hard_gate_result") or {})
    promotion_ready = _incubation_surface_bool(actual_account.get("promotion_candidate"))
    if promotion_ready is None:
        promotion_ready = _incubation_surface_bool(overview_payload.get("promotion_ready"))
    if promotion_ready is None:
        promotion_ready = _incubation_surface_bool(snapshot_summary.get("promotion_ready"))
    if promotion_ready is None:
        promotion_ready = pipeline_stage in {"graduation_ready", "promoted"}

    blockers = overview_payload.get("blockers")
    if blockers is None:
        blockers = snapshot.get("blockers")
    risk_flags = overview_payload.get("risk_flags")
    if risk_flags is None:
        risk_flags = snapshot.get("risk_flags")

    entered_incubator = bool(
        actual_account
        or snapshot
        or overview_payload
        or account
        or pipeline_stage != "not_started"
        or strategy_status in {"incubating", "listed"}
    )

    return {
        "entered_incubator": entered_incubator,
        "pipeline_stage": pipeline_stage,
        "stage_source": stage_source,
        "account_stage": _trimmed(actual_account.get("incubation_stage")) or None,
        "account_status": _trimmed(actual_account.get("status")) or None,
        "promotion_ready": bool(promotion_ready),
        "latest_decision": _trimmed(snapshot.get("latest_decision")) or _trimmed(metric.get("decision")) or None,
        "execution_audit_gate_status": (
            _trimmed(overview_payload.get("execution_audit_gate_status"))
            or _trimmed(hard_gate_result.get("execution_audit_gate_status"))
            or _trimmed(snapshot_summary.get("execution_audit_gate_status"))
            or None
        ),
        "blocker_count": _incubation_surface_issue_count(blockers),
        "risk_count": _incubation_surface_issue_count(risk_flags),
    }


async def _load_strategy_incubation_surface(db, strategy: dict) -> dict:
    sid = _trimmed((strategy or {}).get("id"))
    if not sid:
        return _build_strategy_incubation_surface(strategy or {})

    paper_account_task = (
        db.get_paper_account_by_strategy(sid)
        if hasattr(db, "get_paper_account_by_strategy")
        else _resolved(None)
    )
    latest_pipeline_snapshot_task = (
        db.get_latest_strategy_incubation_pipeline_snapshot(sid)
        if hasattr(db, "get_latest_strategy_incubation_pipeline_snapshot")
        else _resolved(None)
    )
    incubation_account_task = (
        db.get_strategy_incubation_account(sid)
        if hasattr(db, "get_strategy_incubation_account")
        else _resolved(None)
    )
    closure_snapshot_task = (
        db.get_latest_strategy_closure_snapshot(sid, snapshot_type="incubation_overview")
        if hasattr(db, "get_latest_strategy_closure_snapshot")
        else _resolved(None)
    )
    paper_account, latest_pipeline_snapshot, incubation_account, closure_snapshot = await asyncio.gather(
        paper_account_task,
        latest_pipeline_snapshot_task,
        incubation_account_task,
        closure_snapshot_task,
    )

    strategy_status = _normalize_strategy_status_value((strategy or {}).get("status"))
    overview = _closure_snapshot_overview_payload(closure_snapshot, strategy_status=strategy_status)
    if not overview and not paper_account and strategy_status in {"incubating", "listed", "deprecated", "suspended"}:
        overview = await _resolve_strategy_incubation_overview(db, strategy) or {}

    pipeline_stage, _ = _resolve_incubation_surface_stage(
        strategy_status=strategy_status,
        paper_account=paper_account,
        latest_pipeline_snapshot=latest_pipeline_snapshot,
        overview=overview,
        incubation_account=incubation_account,
    )
    latest_metric = None
    if (
        hasattr(db, "get_latest_strategy_incubation_metric")
        and not _trimmed((latest_pipeline_snapshot or {}).get("latest_decision"))
        and pipeline_stage != "not_started"
    ):
        latest_metric = await db.get_latest_strategy_incubation_metric(sid)

    return _build_strategy_incubation_surface(
        strategy or {},
        paper_account=paper_account,
        latest_pipeline_snapshot=latest_pipeline_snapshot,
        overview=overview,
        incubation_account=incubation_account,
        latest_metric=latest_metric,
    )


def _build_strategy_market_summary(
    strategy: dict,
    *,
    metrics: dict | None = None,
    incubation_surface: dict | None = None,
) -> dict:
    summary = {
        "id": strategy.get("id"),
        "name": strategy.get("name"),
        "strategy_type": strategy.get("strategy_type"),
        "description": strategy.get("description"),
        "status": strategy.get("status"),
        "subscriber_count": strategy.get("subscriber_count"),
        "favorite_count": strategy.get("favorite_count") if strategy.get("favorite_count") is not None else strategy.get("subscriber_count"),
        "avg_rating": strategy.get("avg_rating"),
        "review_count": strategy.get("review_count"),
        "sample_start_date": _extract_strategy_market_summary_value(strategy, "sample_start_date"),
        "sample_end_date": _extract_strategy_market_summary_value(strategy, "sample_end_date"),
        "turnover_rate": _extract_strategy_market_summary_value(strategy, "turnover_rate"),
        "capacity": _extract_strategy_market_summary_value(strategy, "capacity"),
        "capacity_label": _extract_strategy_market_summary_value(strategy, "capacity_label"),
        "incubation_surface": incubation_surface,
    }

    if metrics:
        metric_summary = {
            "total_return": metrics.get("total_return"),
            "annual_return": metrics.get("annual_return"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "win_rate": metrics.get("win_rate"),
        }
        summary["metrics"] = metric_summary
        summary["total_return"] = metric_summary["total_return"]
        summary["annual_return"] = metric_summary["annual_return"]
        summary["sharpe_ratio"] = metric_summary["sharpe_ratio"]
        summary["max_drawdown"] = metric_summary["max_drawdown"]
        summary["win_rate"] = metric_summary["win_rate"]

    return {key: value for key, value in summary.items() if value is not None or key in {"id", "name"}}


async def _enrich_rank_strategy(db, strategy: dict, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        metrics_list, incubation_surface = await asyncio.gather(
            db.get_strategy_metrics(strategy["id"]),
            _load_strategy_incubation_surface(db, strategy),
        )

    all_period = next((m for m in metrics_list if m.get("period") == "all"), {})
    return _build_strategy_market_summary(strategy, metrics=all_period, incubation_surface=incubation_surface)


async def handle_help(db, params: dict) -> dict:
    return ok({
        "actions": [
            "create", "publish", "archive", "list", "detail",
            "update_metrics", "review", "subscribe", "unsubscribe",
            "my_subscriptions", "favorite", "unfavorite", "my_favorites", "my_strategies", "fork_strategy", "personal_strategy_context", "personal_strategy_suggestions", "update_strategy", "delete_personal_strategy",
            "paper_session_get", "paper_session_get_or_create",
            "rank", "submit", "capabilities", "daily_snapshot", "daily_snapshots",
            "incubation_accounts", "incubation_metrics", "paper_account", "paper_orders", "paper_nav", "incubation_sync_run", "risk_events", "risk_snapshots", "risk_scan_run", "risk_recovery", "resolve_risk_event", "runtime_alerts", "runtime_alert_dispatch_run", "runtime_alert_ack",
            "vector_profiles", "vector_indexes", "vector_reconcile", "vector_rebuild", "vector_health", "vector_cleanup",
            "ai_generate", "ai_optimize_personal_strategy", "ai_experiments", "task_runs", "domain_events", "domain_projection", "domain_projection_snapshot", "domain_projection_rebuild",
            "runtime_control", "runtime_control_set", "promotion_reviews", "promotion_review_run",
            "runtime_cycle_run", "runtime_cycle_status", "lifecycle_scan", "get_signals", "get_forward_returns", "get_signal_stats",
            "factory_status", "factory_run_once", "factory_dispatch_run", "factory_dispatch_status", "factory_runs", "factory_run_detail", "factory_topn_latest", "factory_run_topn", "execution_audit_verification", "review_report", "review_report_recheck", "submission_replay", "events", "closure_review",
            "incubation_overview", "help",
        ],
        "description": "策略超市管理器（含生命周期与前向信号跟踪）",
    })


async def handle_create(db, params: dict) -> dict:
    name = str(params.get("name", "")).strip()
    if not name:
        return fail("name is required")
    strategy_type = str(params.get("strategy_type") or params.get("type") or "custom").strip()
    sid = f"strat_{int(time.time())}_{uuid4().hex[:8]}"
    tags = list(params.get("tags") or [])
    metadata = dict(dict(params.get("params") or {}).get("metadata") or {})
    if params.get("personal_strategy") or metadata.get("source_strategy_id"):
        tags = [*tags, "personal_strategy"]
    if "personal_strategy" in {str(item or "").strip().lower() for item in tags}:
        tags = [str(item or "").strip() for item in tags if str(item or "").strip()]
        tags = list(dict.fromkeys(tags))
    data = {
        "id": sid,
        "name": name,
        "description": params.get("description", ""),
        "author_id": str(params.get("author_id") or params.get("user_id") or "default"),
        "strategy_type": strategy_type,
        "params": params.get("params") or {},
        "factor_weights": params.get("factor_weights") or {},
        "status": "draft",
        "tags": tags,
        "backtest_artifact_id": params.get("backtest_artifact_id"),
    }
    result = await db.save_strategy(data)
    return ok({"strategy_id": sid, "strategy": result})


async def handle_publish(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    await update_status(db, sid, "listed", actor_id="strategy_manager", reason="manual_publish")
    return ok({"strategy_id": sid, "status": "listed"})


async def handle_archive(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    await update_status(db, sid, "archived", actor_id="strategy_manager", reason="manual_archive")
    return ok({"strategy_id": sid, "status": "archived"})


async def handle_list(db, params: dict) -> dict:
    status = _resolve_strategy_status_filter(params.get("status"), default="visible")
    strategy_type = params.get("strategy_type") or params.get("type")
    limit = min(max(int(params.get("limit", 20)), 1), 100)
    offset = max(int(params.get("offset", 0)), 0)
    rows = await db.list_strategies(status, strategy_type, limit, offset)
    incubation_surfaces = await asyncio.gather(*[
        _load_strategy_incubation_surface(db, row)
        for row in rows
    ]) if rows else []
    return ok({
        "strategies": [
            _build_strategy_market_summary(row, incubation_surface=incubation_surfaces[index])
            for index, row in enumerate(rows)
        ],
        "count": len(rows),
    })


async def handle_detail(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")

    actor_id, actor_roles = _actor_context(params)
    user_id = str(actor_id or params.get("user_id") or "default")
    metrics, reviews, is_sub, latest_quality_report, incubation_overview, incubation_account, incubation_metric, strategy_paper_account, risk_events, latest_runtime_risk_snapshot, runtime_control, runtime_alerts, latest_promotion_review, latest_projection_snapshot, latest_vector_index_snapshot, latest_incubation_pipeline_snapshot, vector_profiles, similar_vector_profiles, domain_events, task_runs, nav_series, signal_event_snapshots = await asyncio.gather(
        db.get_strategy_metrics(sid),
        db.get_reviews(sid, limit=10),
        db.is_subscribed(sid, user_id),
        get_latest_quality_report(db, sid),
        _resolve_strategy_incubation_overview(db, strategy),
        db.get_strategy_incubation_account(sid) if hasattr(db, "get_strategy_incubation_account") else _resolved(None),
        db.get_latest_strategy_incubation_metric(sid) if hasattr(db, "get_latest_strategy_incubation_metric") else _resolved(None),
        db.get_paper_account_by_strategy(sid) if hasattr(db, "get_paper_account_by_strategy") else _resolved(None),
        db.list_strategy_runtime_risk_events(strategy_id=sid, status="open", limit=5) if hasattr(db, "list_strategy_runtime_risk_events") else _resolved([]),
        db.get_latest_strategy_runtime_risk_snapshot(sid) if hasattr(db, "get_latest_strategy_runtime_risk_snapshot") else _resolved(None),
        db.get_strategy_runtime_control(sid) if hasattr(db, "get_strategy_runtime_control") else _resolved(None),
        db.list_strategy_runtime_alerts(strategy_id=sid, status="open_or_ack", limit=5) if hasattr(db, "list_strategy_runtime_alerts") else _resolved([]),
        db.get_latest_strategy_promotion_review(sid) if hasattr(db, "get_latest_strategy_promotion_review") else _resolved(None),
        db.get_latest_strategy_projection_snapshot(sid) if hasattr(db, "get_latest_strategy_projection_snapshot") else _resolved(None),
        _load_latest_vector_index_snapshot(db, 'strategy_behavior'),
        db.get_latest_strategy_incubation_pipeline_snapshot(sid) if hasattr(db, "get_latest_strategy_incubation_pipeline_snapshot") else _resolved(None),
        _load_vector_profiles(db, sid, limit=3),
        _load_similar_vector_profiles(db, sid),
        db.list_strategy_domain_events(strategy_id=sid, limit=5) if hasattr(db, "list_strategy_domain_events") else _resolved([]),
        db.list_strategy_task_runs(strategy_id=sid, limit=5) if hasattr(db, "list_strategy_task_runs") else _resolved([]),
        compute_nav_series(db, sid),
        db.list_strategy_signal_event_snapshots(strategy_id=sid, latest_only=True, limit=10) if hasattr(db, "list_strategy_signal_event_snapshots") else _resolved([]),
    )
    metric_noise_enabled = os.getenv("STRATEGY_METRIC_NOISE_ENABLED", "1").strip() not in ("0", "false", "no")
    if not is_sub and metrics and metric_noise_enabled:
        noise = 1 + random.uniform(-0.001, 0.001)
        for m in metrics:
            for key in ("total_return", "annual_return", "sharpe_ratio", "calmar_ratio"):
                if m.get(key) is not None:
                    m[key] = round(float(m[key]) * noise, 6)
            m["approximate"] = True
    latest_quality_report = normalize_quality_report_contract(
        latest_quality_report,
        strategy_id=sid,
        strategy_type=strategy.get("strategy_type"),
        default_review_source="strategy_manager.detail",
    )
    owner_state, favorite_state, paper_session_state = await _load_personal_strategy_surface_state(
        db,
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    incubation_surface = _build_strategy_incubation_surface(
        strategy,
        paper_account=strategy_paper_account,
        latest_pipeline_snapshot=latest_incubation_pipeline_snapshot,
        overview=incubation_overview,
        incubation_account=incubation_account,
        latest_metric=incubation_metric,
    )
    strategy_with_surface = {
        **dict(strategy or {}),
        "incubation_surface": incubation_surface,
        "favorite_count": strategy.get("favorite_count") if strategy.get("favorite_count") is not None else strategy.get("subscriber_count"),
    }
    presentation = build_strategy_presentation(
        strategy_with_surface,
        owner_state=owner_state,
        favorite_state=favorite_state,
        paper_session_state=paper_session_state,
        overview=incubation_overview,
        report=latest_quality_report,
        runtime_control=runtime_control,
        risk_events=risk_events,
    )
    personal_strategy_context = _build_personal_strategy_context(
        strategy_with_surface,
        actor_id=actor_id,
        actor_roles=actor_roles,
        owner_state=owner_state,
        favorite_state=favorite_state,
        paper_session_state=paper_session_state,
    )

    return ok({
        "strategy": strategy_with_surface, "metrics": metrics, "reviews": reviews,
        "nav_series": nav_series,
        "latest_quality_report": latest_quality_report,
        "incubation_overview": incubation_overview,
        "incubation_account": incubation_account,
        "latest_incubation_metric": incubation_metric,
        "latest_promotion_review": latest_promotion_review,
        "latest_projection_snapshot": latest_projection_snapshot,
        "latest_vector_index_snapshot": latest_vector_index_snapshot,
        "latest_incubation_pipeline_snapshot": latest_incubation_pipeline_snapshot,
        "runtime_control": runtime_control,
        "runtime_alerts": runtime_alerts,
        "latest_runtime_risk_snapshot": latest_runtime_risk_snapshot,
        "signal_event_snapshots": signal_event_snapshots,
        "open_risk_events": risk_events,
        "vector_profiles": vector_profiles,
        "similar_vector_profiles": similar_vector_profiles,
        "domain_events": domain_events,
        "task_runs": task_runs,
        "owner_state": owner_state,
        "favorite_state": favorite_state,
        "paper_session_state": paper_session_state,
        "presentation": presentation,
        "personal_strategy_context": personal_strategy_context,
    })


async def _resolve_strategy_incubation_overview(db, strategy: dict) -> dict | None:
    try:
        return await build_incubation_overview(db, strategy)
    except Exception as exc:
        logger.warning("strategy_manager.detail incubation overview failed for %s: %s", strategy.get("id"), exc)
        return None


async def handle_review_report(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    limit = min(max(int(params.get("limit", 10)), 1), 50)
    strategy = await db.get_strategy(sid) if hasattr(db, "get_strategy") else None
    strategy_type = str((strategy or {}).get("strategy_type") or "").strip() or None
    reports = [
        normalize_quality_report_contract(
            report,
            strategy_id=sid,
            strategy_type=strategy_type,
            default_review_source="strategy_manager.review_report",
        )
        for report in await list_quality_reports(db, sid, limit=limit)
    ]
    latest = reports[0] if reports else None
    return ok({**(latest or {}), "reports": reports})


async def handle_events(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    limit = min(max(int(params.get("limit", 50)), 1), 200)
    rows = []
    if hasattr(db, "list_strategy_status_events"):
        try:
            rows = await db.list_strategy_status_events(
                sid,
                event_type=str(params.get("event_type") or "").strip() or None,
                from_status=str(params.get("from_status") or "").strip() or None,
                to_status=str(params.get("to_status") or "").strip() or None,
                actor_id=str(params.get("actor_id") or "").strip() or None,
                start_time=normalize_time_filter(params.get("start_time")),
                end_time=normalize_time_filter(params.get("end_time"), is_end=True),
                limit=limit,
            )
        except TypeError:
            rows = await db.list_strategy_status_events(sid, limit=limit)
    return ok({"events": rows, "count": len(rows)})


async def handle_update_metrics(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    metrics = params.get("metrics") or {}
    period = str(params.get("period", "all"))
    await db.save_strategy_metrics(sid, period, metrics)
    return ok({"strategy_id": sid, "period": period, "updated": True})


async def handle_review(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    user_id = str(params.get("user_id", "default"))
    rating = int(params.get("rating", 3))
    comment = params.get("comment")
    if not sid:
        return fail("strategy_id is required")
    if rating < 1 or rating > 5:
        return fail("rating must be 1-5")
    await db.save_review(sid, user_id, rating, comment)
    return ok({"strategy_id": sid, "user_id": user_id, "rating": rating})


async def handle_subscribe(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    user_id = str(params.get("user_id", "default"))
    if not sid:
        return fail("strategy_id is required")
    await db.subscribe_strategy(sid, user_id)
    return ok({"strategy_id": sid, "user_id": user_id, "subscribed": True, "favorited": True})


async def handle_unsubscribe(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    user_id = str(params.get("user_id", "default"))
    if not sid:
        return fail("strategy_id is required")
    await db.unsubscribe_strategy(sid, user_id)
    return ok({"strategy_id": sid, "user_id": user_id, "unsubscribed": True, "favorited": False})


async def handle_my_subscriptions(db, params: dict) -> dict:
    user_id = str(params.get("user_id", "default"))
    rows = await db.list_user_subscriptions(user_id)
    return ok({"subscriptions": rows, "favorites": rows, "items": rows, "count": len(rows)})


async def handle_favorite(db, params: dict) -> dict:
    result = await handle_subscribe(db, params)
    if isinstance(result, dict):
        result.setdefault("data", {})
        if isinstance(result.get("data"), dict):
            result["data"]["compat_alias"] = "favorite"
            result["data"]["canonical_action"] = "favorite"
            result["data"]["legacy_action"] = "subscribe"
    return result


async def handle_unfavorite(db, params: dict) -> dict:
    result = await handle_unsubscribe(db, params)
    if isinstance(result, dict):
        result.setdefault("data", {})
        if isinstance(result.get("data"), dict):
            result["data"]["compat_alias"] = "unfavorite"
            result["data"]["canonical_action"] = "unfavorite"
            result["data"]["legacy_action"] = "unsubscribe"
    return result


async def handle_my_favorites(db, params: dict) -> dict:
    result = await handle_my_subscriptions(db, params)
    if isinstance(result, dict):
        result.setdefault("data", {})
        if isinstance(result.get("data"), dict):
            result["data"]["compat_alias"] = "my_favorites"
            result["data"]["canonical_action"] = "my_favorites"
            result["data"]["legacy_action"] = "my_subscriptions"
    return result


async def handle_my_strategies(db, params: dict) -> dict:
    actor_id, actor_roles = _actor_context(params)
    if not actor_id:
        return fail("actor_id is required")
    include_archived = str(params.get("include_archived") or "").strip().lower() in {"1", "true", "yes"}
    limit = min(max(int(params.get("limit", 50)), 1), 200)
    offset = max(int(params.get("offset", 0)), 0)
    rows = await db.list_user_strategies(
        actor_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    ) if hasattr(db, "list_user_strategies") else []
    favorite_rows = await db.list_user_subscriptions(actor_id) if hasattr(db, "list_user_subscriptions") else []
    favorite_ids = {
        _trimmed(item.get("id") or item.get("strategy_id"))
        for item in list(favorite_rows or [])
        if _trimmed(item.get("id") or item.get("strategy_id"))
    }
    incubation_surfaces = await asyncio.gather(*[
        _load_strategy_incubation_surface(db, row)
        for row in rows
    ]) if rows else []
    items = []
    for index, row in enumerate(rows):
        owner_state = build_owner_state(row, actor_id=actor_id, actor_roles=actor_roles)
        favorite_state = build_favorite_state(actor_id=actor_id, is_favorited=row.get("id") in favorite_ids)
        session = await db.get_strategy_paper_session(row.get("id"), actor_id) if hasattr(db, "get_strategy_paper_session") else None
        paper_session_state = build_paper_session_state(session, actor_id=actor_id)
        items.append({
            **_build_strategy_market_summary(row, incubation_surface=incubation_surfaces[index]),
            "owner_state": owner_state,
            "favorite_state": favorite_state,
            "paper_session_state": paper_session_state,
        })
    return ok({"strategies": items, "items": items, "count": len(items)})


async def handle_fork_strategy(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    actor_id, actor_roles = _actor_context(params)
    if not actor_id:
        return fail("actor_id is required")
    parent = await db.get_strategy(sid)
    if not parent:
        return fail(f"Strategy not found: {sid}")
    fork_id = f"strat_{int(time.time())}_{uuid4().hex[:8]}"
    parent_tags = [str(item or "").strip() for item in list(parent.get("tags") or []) if str(item or "").strip()]
    tags = list(dict.fromkeys([*parent_tags, "personal_strategy", "forked_strategy"]))
    parent_params = dict(parent.get("params") or {})
    metadata = dict(parent_params.get("metadata") or {})
    metadata.update({
        "source_strategy_id": sid,
        "forked_at": datetime.now(timezone.utc).isoformat(),
        "forked_by": actor_id,
    })
    fork_params = {
        **parent_params,
        "metadata": metadata,
    }
    data = {
        "id": fork_id,
        "name": f"{parent.get('name') or sid} · 我的版本",
        "description": parent.get("description") or "",
        "author_id": actor_id,
        "strategy_type": str(parent.get("strategy_type") or "custom"),
        "params": fork_params,
        "factor_weights": dict(parent.get("factor_weights") or {}),
        "status": "draft",
        "tags": tags,
        "backtest_artifact_id": parent.get("backtest_artifact_id"),
    }
    strategy = await db.save_strategy(data)
    if hasattr(db, "save_strategy_lineage"):
        await db.save_strategy_lineage(
            fork_id,
            sid,
            "user_fork",
            {"source": "strategy_market", "actor_id": actor_id, "actor_roles": actor_roles},
        )
    owner_state, favorite_state, paper_session_state = await _load_personal_strategy_surface_state(
        db,
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    return ok({
        "strategy_id": fork_id,
        "source_strategy_id": sid,
        "strategy": strategy,
        "owner_state": owner_state,
        "favorite_state": favorite_state,
        "paper_session_state": paper_session_state,
    })


async def handle_personal_strategy_context(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    strategy = await db.get_strategy(sid) if hasattr(db, "get_strategy") else None
    if not strategy:
        return fail(f"Strategy not found: {sid}")
    actor_id, actor_roles = _actor_context(params)
    owner_state, favorite_state, paper_session_state = await _load_personal_strategy_surface_state(
        db,
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    return ok(_build_personal_strategy_context(
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
        owner_state=owner_state,
        favorite_state=favorite_state,
        paper_session_state=paper_session_state,
    ))


async def handle_personal_strategy_suggestions(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    actor_id, actor_roles = _actor_context(params)
    strategy = await db.get_strategy(sid) if hasattr(db, "get_strategy") else None
    error = _ensure_personal_strategy_mutation_allowed(
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    if error:
        return fail(error)
    owner_state, favorite_state, paper_session_state = await _load_personal_strategy_surface_state(
        db,
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    plan = _build_personal_strategy_change_plan(
        strategy,
        params,
        mode="suggest",
        actor_id=actor_id,
        actor_roles=actor_roles,
        owner_state=owner_state,
        favorite_state=favorite_state,
        paper_session_state=paper_session_state,
    )
    persist = parse_bool(params.get("persist"), False)
    run_post_update_pipeline = parse_bool(params.get("run_post_update_pipeline"), persist)
    if not persist:
        return ok({
            "strategy_id": sid,
            "advisory_only": True,
            "persisted": False,
            **plan,
        })
    apply_payload = dict(plan.get("apply_payload") or {})
    updated = (
        await db.update_strategy_fields(sid, apply_payload)
        if apply_payload and hasattr(db, "update_strategy_fields")
        else strategy
    )
    if not updated:
        return fail(f"Strategy not found: {sid}")
    post_update_pipeline = {
        "requested": False,
        "overall_status": "skipped",
    }
    pipeline_notes: list[str] = []
    if run_post_update_pipeline:
        post_update_pipeline, updated, pipeline_notes = await _run_personal_strategy_post_update_pipeline(
            db,
            updated,
        )
    owner_state, favorite_state, paper_session_state = await _load_personal_strategy_surface_state(
        db,
        updated,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    return ok({
        "strategy_id": sid,
        "advisory_only": False,
        "persisted": True,
        **plan,
        "risk_notes": [
            *list(plan.get("risk_notes") or []),
            *pipeline_notes,
        ],
        "post_update_pipeline": post_update_pipeline,
        "strategy": updated,
        "context": _build_personal_strategy_context(
            updated,
            actor_id=actor_id,
            actor_roles=actor_roles,
            owner_state=owner_state,
            favorite_state=favorite_state,
            paper_session_state=paper_session_state,
        ),
    })


async def handle_update_strategy(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    actor_id, actor_roles = _actor_context(params)
    strategy = await db.get_strategy(sid)
    error = _ensure_personal_strategy_mutation_allowed(
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    if error:
        return fail(error)
    updates = dict(params.get("updates") or {})
    for field in ("name", "description", "params", "factor_weights", "tags", "backtest_artifact_id"):
        if field in params:
            updates[field] = params.get(field)
    if "tags" in updates:
        updates["tags"] = list(dict.fromkeys(
            [str(item or "").strip() for item in list(updates.get("tags") or []) if str(item or "").strip()]
        ))
    updated = await db.update_strategy_fields(sid, updates) if hasattr(db, "update_strategy_fields") else None
    if not updated:
        return fail(f"Strategy not found: {sid}")
    post_update_pipeline = {
        "requested": False,
        "overall_status": "skipped",
    }
    pipeline_notes: list[str] = []
    if parse_bool(params.get("run_post_update_pipeline"), False):
        post_update_pipeline, updated, pipeline_notes = await _run_personal_strategy_post_update_pipeline(
            db,
            updated,
        )
    owner_state, favorite_state, paper_session_state = await _load_personal_strategy_surface_state(
        db,
        updated,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    return ok({
        "strategy_id": sid,
        "strategy": updated,
        "owner_state": owner_state,
        "favorite_state": favorite_state,
        "paper_session_state": paper_session_state,
        "post_update_pipeline": post_update_pipeline,
        "risk_notes": pipeline_notes,
    })


async def handle_delete_personal_strategy(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    actor_id, actor_roles = _actor_context(params)
    strategy = await db.get_strategy(sid)
    error = _ensure_personal_strategy_mutation_allowed(
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    if error:
        return fail(error)
    await update_status(
        db,
        sid,
        "archived",
        actor_id=actor_id or "strategy_manager",
        reason="personal_strategy_deleted",
    )
    return ok({"strategy_id": sid, "archived": True, "status": "archived"})


async def handle_paper_session_get(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    actor_id, actor_roles = _actor_context(params)
    if not actor_id:
        return fail("actor_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")
    session = await db.get_strategy_paper_session(sid, actor_id) if hasattr(db, "get_strategy_paper_session") else None
    state = build_paper_session_state(session, actor_id=actor_id)
    return ok({
        "strategy_id": sid,
        "strategy_name": strategy.get("name"),
        "session": session,
        "paper_session_state": state,
    })


async def handle_paper_session_get_or_create(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    actor_id, actor_roles = _actor_context(params)
    if not actor_id:
        return fail("actor_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")
    existing = await db.get_strategy_paper_session(sid, actor_id) if hasattr(db, "get_strategy_paper_session") else None
    created = False
    session = existing
    if existing and hasattr(db, "touch_strategy_paper_session"):
        session = await db.touch_strategy_paper_session(sid, actor_id) or existing
    if not existing:
        account_id = f"pp_{uuid4().hex[:8]}"
        account = await db.save_paper_account({
            "id": account_id,
            "user_id": actor_id,
            "name": f"个人策略模拟盘_{strategy.get('name') or sid}",
            "initial_capital": 100000,
            "current_capital": 100000,
            "total_value": 100000,
            "account_type": "personal_strategy",
            "status": "active",
        }) if hasattr(db, "save_paper_account") else {"id": account_id}
        session = await db.save_strategy_paper_session({
            "strategy_id": sid,
            "user_id": actor_id,
            "account_id": account.get("id") or account_id,
            "session_type": "personal_paper",
            "source_strategy_id": _strategy_source_strategy_id(strategy),
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }) if hasattr(db, "save_strategy_paper_session") else None
        created = True
    account = await db.get_paper_account(session.get("account_id")) if session and hasattr(db, "get_paper_account") else None
    payload = dict(session or {})
    if account:
        payload.setdefault("account_name", account.get("name"))
        payload.setdefault("account_status", account.get("status"))
    state = build_paper_session_state(payload, actor_id=actor_id)
    return ok({
        "strategy_id": sid,
        "strategy_name": strategy.get("name"),
        "created": created,
        "session": payload or None,
        "account": account,
        "paper_session_state": state,
    })


async def handle_rank(db, params: dict) -> dict:
    from ...services.ranking import rrf_rank

    status = _resolve_strategy_status_filter(params.get("status"), default="visible")
    strategy_type = params.get("strategy_type") or params.get("type")
    limit = min(max(int(params.get("limit", 50)), 1), 200)
    offset = max(int(params.get("offset", 0)), 0)
    rank_keys = params.get("rank_keys")

    fetch_limit = limit + offset
    strategies = await db.list_strategies(status, strategy_type, fetch_limit, 0)
    if not strategies:
        return ok({"strategies": [], "count": 0, "offset": offset, "limit": limit})

    semaphore = asyncio.Semaphore(8)
    enriched = await asyncio.gather(*[
        _enrich_rank_strategy(db, strategy, semaphore)
        for strategy in strategies
    ])

    ranked = rrf_rank(enriched, rank_keys)
    page = ranked[offset:offset + limit]
    return ok({"strategies": page, "count": len(ranked), "offset": offset, "limit": limit})


async def handle_ai_optimize_personal_strategy(db, params: dict) -> dict:
    sid = _trimmed(params.get("strategy_id") or params.get("id"))
    if not sid:
        return fail("strategy_id is required")
    actor_id, actor_roles = _actor_context(params)
    strategy = await db.get_strategy(sid)
    error = _ensure_personal_strategy_mutation_allowed(
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    if error:
        return fail(error)
    owner_state, favorite_state, paper_session_state = await _load_personal_strategy_surface_state(
        db,
        strategy,
        actor_id=actor_id,
        actor_roles=actor_roles,
    )
    plan = _build_personal_strategy_change_plan(
        strategy,
        params,
        mode="optimize",
        actor_id=actor_id,
        actor_roles=actor_roles,
        owner_state=owner_state,
        favorite_state=favorite_state,
        paper_session_state=paper_session_state,
    )
    before = dict(plan.get("before") or {})
    started_at = datetime.now(timezone.utc)
    task_run = await db.save_strategy_task_run({
        "strategy_id": sid,
        "task_name": "ai_optimize_personal_strategy",
        "task_scope": "strategy_market.personal_strategy",
        "task_key": f"{sid}:ai_optimize_personal_strategy",
        "status": "running",
        "trace_id": f"ai_opt_{uuid4().hex[:12]}",
        "payload": {
            "strategy_id": sid,
            "actor_id": actor_id,
            "before": before,
            "objective": plan.get("objective"),
            "instructions": plan.get("instructions"),
            "focus_fields": list(plan.get("focus_fields") or []),
        },
        "started_at": started_at.isoformat(),
    }) if hasattr(db, "save_strategy_task_run") else None
    experiment_id = f"sge_{uuid4().hex[:16]}"
    try:
        apply_payload = dict(plan.get("apply_payload") or {})
        if apply_payload:
            updated = await db.update_strategy_fields(sid, apply_payload) if hasattr(db, "update_strategy_fields") else None
            if not updated:
                raise ValueError(f"Strategy not found: {sid}")
        else:
            updated = strategy
        post_update_pipeline, updated, pipeline_notes = await _run_personal_strategy_post_update_pipeline(
            db,
            updated,
        )
        after = {
            "name": updated.get("name"),
            "description": updated.get("description"),
            "params": dict(updated.get("params") or {}),
            "factor_weights": dict(updated.get("factor_weights") or {}),
            "tags": list(updated.get("tags") or []),
        }
        changed_fields = list(plan.get("changed_fields") or [])
        if hasattr(db, "save_strategy_generation_experiment"):
            await db.save_strategy_generation_experiment({
                "experiment_id": experiment_id,
                "strategy_id": sid,
                "generated_strategy_id": sid,
                "task_run_id": task_run.get("id") if task_run else None,
                "source": "strategy_manager.personal_strategy",
                "generator_type": "personal_strategy_optimizer",
                "optimizer_type": "heuristic",
                "status": "completed",
                "hypothesis": "Improve personal strategy readiness with stronger metadata and normalized weights.",
                "parameters": {
                    "actor_id": actor_id,
                    "requested_changes": list(changed_fields),
                    "objective": plan.get("objective"),
                    "instructions": plan.get("instructions"),
                    "focus_fields": list(plan.get("focus_fields") or []),
                },
                "strategy_spec": {"before": before, "after": after},
                "evaluation": {"changed_fields": changed_fields},
                "result": after,
            })
        if task_run and hasattr(db, "update_strategy_task_run"):
            await db.update_strategy_task_run(
                int(task_run.get("id")),
                status="success",
                result={
                    "strategy_id": sid,
                    "experiment_id": experiment_id,
                    "changed_fields": changed_fields,
                    "summary": plan.get("summary"),
                    "after": after,
                    "post_update_pipeline": post_update_pipeline,
                },
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        response_context = _build_personal_strategy_context(
            updated,
            actor_id=actor_id,
            actor_roles=actor_roles,
            owner_state=owner_state,
            favorite_state=favorite_state,
            paper_session_state=paper_session_state,
        )
        return ok({
            "strategy_id": sid,
            "task_run_id": task_run.get("id") if task_run else None,
            "experiment_id": experiment_id,
            "before": before,
            "after": after,
            "changed_fields": changed_fields,
            "summary": plan.get("summary"),
            "suggestions": plan.get("suggestions"),
            "risk_notes": [
                *list(plan.get("risk_notes") or []),
                *pipeline_notes,
            ],
            "post_update_pipeline": post_update_pipeline,
            "context": response_context,
            "strategy": updated,
        })
    except Exception as exc:
        if task_run and hasattr(db, "update_strategy_task_run"):
            await db.update_strategy_task_run(
                int(task_run.get("id")),
                status="failed",
                error=str(exc),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        return fail(f"ai optimize failed: {exc}")


async def handle_capabilities(db, params: dict) -> dict:
    from strategy_factory import get_factory_constants

    factory_constants = get_factory_constants()
    high_confidence_feature_flags = dict(factory_constants.get("HIGH_CONFIDENCE_FEATURE_FLAGS") or {})
    latest_run = await db.get_latest_strategy_factory_run() if hasattr(db, "get_latest_strategy_factory_run") else None
    capability_health = build_factory_capability_health(
        db,
        factory_constants=factory_constants,
        latest_run=latest_run,
    )
    return ok({
        "daily_snapshot": hasattr(db, "get_daily_snapshot") and hasattr(db, "list_daily_snapshots"),
        "factory_runs": hasattr(db, "save_strategy_factory_run") and hasattr(db, "get_latest_strategy_factory_run"),
        "factory_dispatch": hasattr(db, "create_strategy_factory_dispatch") and hasattr(db, "get_strategy_factory_dispatch"),
        "factory_bulk_lane": hasattr(db, "list_stock_universe") and hasattr(db, "save_strategy_factory_run"),
        "factory_bulk_lane_enabled": bool(factory_constants.get("STOCK_STRATEGY_MATRIX_ENABLED")),
        "factory_pre_gate_enabled": bool(factory_constants.get("FACTORY_PRE_GATE_ENABLED")),
        "high_confidence_enabled": bool(factory_constants.get("STRATEGY_FACTORY_HIGH_CONFIDENCE_ENABLED")),
        "evidence_contract_enabled": bool(factory_constants.get("STRATEGY_FACTORY_EVIDENCE_CONTRACT_ENABLED")),
        "confidence_diagnostics_enabled": bool(
            factory_constants.get("STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED")
        ),
        "execution_audit_enabled": bool(factory_constants.get("STRATEGY_FACTORY_EXECUTION_AUDIT_ENABLED")),
        "execution_audit_verification": hasattr(db, "get_execution_audit_verification"),
        "quality_ui_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_QUALITY_UI_V2_ENABLED")),
        "research_protocol_v2_enabled": bool(
            factory_constants.get("STRATEGY_FACTORY_RESEARCH_PROTOCOL_V2_ENABLED")
        ),
        "gate_model_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_GATE_MODEL_V2_ENABLED")),
        "trace_ledger_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_TRACE_LEDGER_V2_ENABLED")),
        "feedback_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_FEEDBACK_V2_ENABLED")),
        "trace_ledger_v2_implemented": True,
        "governance_gate_report_v2_implemented": True,
        "execution_audit_entity_chain_available": _execution_audit_entity_chain_available(db),
        "spec_completeness_mode": str(
            factory_constants.get("STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE") or "warn"
        ),
        "high_confidence_feature_flags": high_confidence_feature_flags,
        "signal_quality_registry": _load_signal_quality_registry_snapshot(),
        "paper_incubation": hasattr(db, "save_strategy_incubation_account") and hasattr(db, "save_strategy_incubation_metric"),
        "paper_trading": hasattr(db, "save_paper_account") and hasattr(db, "save_paper_order") and hasattr(db, "get_paper_nav_rows"),
        "incubation_pipeline": hasattr(db, "save_strategy_incubation_pipeline_snapshot") and hasattr(db, "list_strategy_incubation_metrics"),
        "runtime_risk": hasattr(db, "save_strategy_runtime_risk_event"),
        "risk_snapshots": hasattr(db, "save_strategy_runtime_risk_snapshot") and hasattr(db, "list_strategy_runtime_risk_snapshots"),
        "risk_recovery": hasattr(db, "save_strategy_runtime_risk_snapshot") and hasattr(db, "save_strategy_runtime_control"),
        "execution_risk": hasattr(db, "save_strategy_runtime_risk_event"),
        "runtime_controls": hasattr(db, "save_strategy_runtime_control") and hasattr(db, "get_strategy_runtime_control"),
        "runtime_alerting": hasattr(db, "save_strategy_runtime_alert") and hasattr(db, "list_strategy_runtime_alerts"),
        "signal_event_snapshots": hasattr(db, "save_strategy_signal_event_snapshot") and hasattr(db, "list_strategy_signal_event_snapshots"),
        "promotion_pipeline": hasattr(db, "save_strategy_promotion_review") and hasattr(db, "get_latest_strategy_promotion_review"),
        "projection_snapshots": hasattr(db, "save_strategy_projection_snapshot") and hasattr(db, "get_latest_strategy_projection_snapshot"),
        "event_replay": hasattr(db, "save_strategy_projection_snapshot") and hasattr(db, "list_strategy_domain_events"),
        "vector_platform": hasattr(db, "save_strategy_vector_profile") and hasattr(db, "save_vector_index_registry"),
        "vector_governance": hasattr(db, "save_vector_index_registry") and hasattr(db, "list_strategy_vector_profiles"),
        "persistent_vector_index": hasattr(db, "save_strategy_vector_index_snapshot") and hasattr(db, "replace_strategy_vector_index_items"),
        "ann_vector_search": hasattr(db, "list_strategy_vector_index_items") and hasattr(db, "save_strategy_vector_index_snapshot"),
        "vector_health": hasattr(db, "get_strategy_vector_health") or (
            hasattr(db, "list_vector_collections") and hasattr(db, "list_vector_index_snapshots")
        ),
        "vector_cleanup": hasattr(db, "cleanup_strategy_vector_history") or hasattr(db, "cleanup_vector_collection_history"),
        "ai_generation": hasattr(db, "save_strategy_generation_experiment") and hasattr(db, "save_strategy_task_run"),
        "multi_agent_review": hasattr(db, "save_strategy_generation_experiment"),
        "quality_governance": hasattr(db, "save_strategy_quality_report") and hasattr(db, "list_strategy_status_events"),
        "domain_events": hasattr(db, "save_strategy_domain_event") and hasattr(db, "list_strategy_domain_events"),
        "domain_projection": hasattr(db, "list_strategy_status_events") and hasattr(db, "list_strategy_domain_events"),
        "runtime_cycle": hasattr(db, "save_strategy_task_run") and hasattr(db, "save_strategy_incubation_metric"),
        "personal_strategy_crud": hasattr(db, "list_user_strategies") and hasattr(db, "update_strategy_fields"),
        "personal_paper_sessions": hasattr(db, "save_strategy_paper_session") and hasattr(db, "get_strategy_paper_session"),
        "capability_health": capability_health,
    })


async def handle_daily_snapshot(db, params: dict) -> dict:
    snapshot_date = params.get("snapshot_date")
    row = await db.get_daily_snapshot(snapshot_date) if hasattr(db, "get_daily_snapshot") else None
    if not row:
        return fail("daily snapshot not found")
    return ok(row)


async def handle_daily_snapshots(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 20)), 1), 200)
    rows = await db.list_daily_snapshots(
        limit=limit,
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
    ) if hasattr(db, "list_daily_snapshots") else []
    return ok({"items": rows, "count": len(rows)})


async def handle_get_signals(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    user_id = str(params.get("user_id", "default"))
    limit = min(max(int(params.get("limit", 100)), 1), 500)
    is_sub = await db.is_subscribed(sid, user_id)
    if is_sub:
        signals = await db.get_signals(sid, limit=limit)
    else:
        signals = await db.get_signals_public(sid, limit=limit)
    return ok({"signals": signals, "count": len(signals), "subscriber": is_sub})


async def handle_get_forward_returns(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    extra_kwargs = {}
    if params.get("lookback_days") is not None:
        extra_kwargs["lookback_days"] = int(params.get("lookback_days"))
    if params.get("eps") is not None:
        extra_kwargs["eps"] = float(params.get("eps"))
    stats = await db.get_signal_stats(sid, **extra_kwargs)
    return ok(stats)


async def handle_get_signal_stats(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    extra_kwargs = {}
    if params.get("lookback_days") is not None:
        extra_kwargs["lookback_days"] = int(params.get("lookback_days"))
    if params.get("eps") is not None:
        extra_kwargs["eps"] = float(params.get("eps"))
    stats = await db.get_signal_stats(sid, **extra_kwargs)
    return ok(stats)
