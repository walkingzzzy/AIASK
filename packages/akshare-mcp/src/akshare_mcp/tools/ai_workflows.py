"""AI-facing narrow MCP workflow tools."""


from __future__ import annotations

import asyncio
import math
import time
from typing import Any
from uuid import uuid4

from ..services.artifact_registry import get_artifact_async, register_artifact_async
from ..services.lineage_tracker import LineageContext
from ..services.stock_deep_analysis import run_stock_deep_analysis
from ..utils import normalize_code, resolve_existing_security_code_async
from ._decision_unified import get_unified_decision_summary
from .data_quality import build_quality_meta, infer_missing_fields
from .finance import get_financials
from .manager_protocol import fail_with_meta, ok_with_meta
from .managers.quant_manager import quant_manager
from .managers.strategy_manager import strategy_manager
from .market.kline import get_kline
from .pit_middleware import build_pit_meta_simple
from .skills_strategy_workflows import build_strategy_review_workflow_payload
from .tool_catalog import build_tool_meta


def _normalize_codes(code: str | None = None, codes: list[str] | None = None) -> list[str]:
    values = list(codes or [])
    if code:
        values.append(code)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        token = normalize_code(str(raw or ""))
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _response_success(response: Any) -> bool:
    return not isinstance(response, dict) or response.get("success", True) is not False


def _response_data(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    return dict(data) if isinstance(data, dict) else {}


def _nested_dict(value: Any, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get(key)
    return dict(nested) if isinstance(nested, dict) else {}


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


_BINARY_LABEL_TRUE = {"1", "true", "t", "yes", "y", "hit", "correct", "success", "positive"}
_BINARY_LABEL_FALSE = {"0", "false", "f", "no", "n", "miss", "incorrect", "failure", "negative"}


def _normalize_binary_outcomes(values: list[Any] | None) -> list[float]:
    normalized: list[float] = []
    for index, item in enumerate(list(values or [])):
        if isinstance(item, bool):
            normalized.append(1.0 if item else 0.0)
            continue
        numeric = _safe_float(item)
        if numeric is not None:
            if numeric in {0.0, 1.0}:
                normalized.append(float(numeric))
                continue
            raise ValueError(
                f"labels/outcomes must contain binary observed outcomes (0/1); "
                f"received {item!r} at index {index}"
            )
        text = str(item or "").strip().lower()
        if text in _BINARY_LABEL_TRUE:
            normalized.append(1.0)
            continue
        if text in _BINARY_LABEL_FALSE:
            normalized.append(0.0)
            continue
        raise ValueError(
            "labels/outcomes must be binary observed outcomes aligned 1:1 with probabilities. "
            f"Unsupported label at index {index}: {item!r}. "
            "Class-name labels like ['up', 'flat', 'down'] are not supported by this workflow."
        )
    return normalized


def _normalize_registry_status(registry_stage: Any) -> str:
    stage = str(registry_stage or "").strip().lower()
    if stage in {"governed", "challenger", "champion"}:
        return "active"
    if stage == "retired":
        return "retired"
    if stage in {"draft", "validated"}:
        return "candidate"
    return "unregistered"


def _derive_registry_status(
    *,
    generation_data: dict[str, Any],
    validation_data: dict[str, Any],
    registry_item: dict[str, Any],
) -> str:
    candidate_resolution = _nested_dict(validation_data, "candidate_resolution")
    rating = _nested_dict(validation_data, "rating")
    governance = _nested_dict(validation_data, "governance")
    rating_governance = _nested_dict(rating, "governance")
    registry_lineage = _nested_dict(registry_item, "lineage")

    for stage in (
        registry_item.get("registry_stage"),
        _nested_dict(registry_item, "governance").get("registry_stage"),
        governance.get("registry_stage"),
        rating_governance.get("registry_stage"),
        validation_data.get("registry_stage"),
        candidate_resolution.get("registry_stage"),
    ):
        normalized = _normalize_registry_status(stage)
        if normalized != "unregistered":
            return normalized

    if registry_item or validation_data or generation_data:
        return "candidate"
    return "unregistered"


def _extract_existing_factor_pool(
    *,
    registry_pool_data: dict[str, Any],
    registry_active_pool_data: dict[str, Any],
    exclude_artifact_id: str | None = None,
) -> list[str]:
    exclude_id = str(exclude_artifact_id or "").strip()
    values: list[str] = []
    seen: set[str] = set()

    for item in list(registry_pool_data.get("items") or []):
        if not isinstance(item, dict):
            continue
        if exclude_id and str(item.get("artifact_id") or "").strip() == exclude_id:
            continue
        candidate = _nested_dict(item, "candidate")
        descriptor = (
            str(candidate.get("expression_dsl") or "").strip()
            or " ".join(
                part
                for part in (
                    str(candidate.get("family") or "").strip(),
                    str(candidate.get("name") or "").strip(),
                )
                if part
            ).strip()
        )
        if descriptor and descriptor not in seen:
            seen.add(descriptor)
            values.append(descriptor)

    if values:
        return values

    active_pool = _nested_dict(registry_active_pool_data, "active_pool")
    for item in list(active_pool.get("top_candidates") or []):
        if not isinstance(item, dict):
            continue
        if exclude_id and str(item.get("artifact_id") or "").strip() == exclude_id:
            continue
        descriptor = " ".join(
            part
            for part in (
                str(item.get("family") or "").strip(),
                str(item.get("name") or "").strip(),
            )
            if part
        ).strip()
        if descriptor and descriptor not in seen:
            seen.add(descriptor)
            values.append(descriptor)
    return values


def _resolve_memory_record_id(
    *,
    validation_data: dict[str, Any],
    registry_item: dict[str, Any],
) -> str | None:
    validation_lineage = _nested_dict(validation_data, "lineage")
    memory_record = _nested_dict(validation_data, "memory_record")
    registry_lineage = _nested_dict(registry_item, "lineage")
    for value in (
        memory_record.get("artifact_id"),
        validation_lineage.get("memory_record_id"),
        registry_item.get("memory_record_id"),
        registry_lineage.get("memory_record_id"),
    ):
        token = str(value or "").strip()
        if token:
            return token
    return None


def _extract_rank_ic_history(validation_data: dict[str, Any]) -> list[float]:
    factor_validation_report = _nested_dict(validation_data, "factor_validation_report")
    cross_section = _nested_dict(factor_validation_report, "cross_section")
    history: list[float] = []
    for row in list(cross_section.get("dates") or []):
        if not isinstance(row, dict):
            continue
        rank_ic = _safe_float(row.get("rank_ic"))
        if rank_ic is None:
            continue
        history.append(rank_ic)
    return history


def _derive_decay_monitor_status(
    *,
    validation_data: dict[str, Any],
    memory_item: dict[str, Any],
) -> str:
    runtime_feedback = [
        dict(item)
        for item in list(memory_item.get("runtime_feedback") or [])
        if isinstance(item, dict)
    ]
    latest_feedback = runtime_feedback[0] if runtime_feedback else {}
    latest_recommended_action = str(
        latest_feedback.get("recommended_action")
        or memory_item.get("last_feedback_recommended_action")
        or ""
    ).strip().lower()
    memory_status = str(memory_item.get("status") or "").strip().lower()

    decay_detected = bool(latest_feedback.get("decay_detected"))
    regime_shift_detected = bool(latest_feedback.get("regime_shift_detected"))
    if decay_detected or regime_shift_detected:
        if latest_recommended_action in {"deprecate", "retire", "retired", "replace"}:
            return "decayed"
        return "decaying"
    if memory_status == "degraded":
        if latest_recommended_action in {"deprecate", "retire", "retired", "replace"}:
            return "decayed"
        return "decaying"
    if runtime_feedback:
        return "stable"

    ic_history = _extract_rank_ic_history(validation_data)
    if len(ic_history) >= 4:
        try:
            from ..services.governance_monitor import check_factor_decay

            decay_report = check_factor_decay("factor_candidate", ic_history)
            decay_status = str(decay_report.get("decay_status") or "").strip().lower()
            if decay_status in {"stable", "decaying", "decayed"}:
                return decay_status
        except Exception:
            pass

    return "not_monitored"


def _step(step: str, response: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "step": step,
        "success": _response_success(response),
    }
    if isinstance(response, dict):
        payload["output"] = response
    else:
        payload["output"] = {"value": response}
    return payload


def _collect_failed_steps(steps: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("step") or "") for item in steps if not item.get("success")]


def _budget_fail_response(
    *,
    step: str,
    message: str,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": False,
        "error": message,
        "data": {"step": step, "degraded": True},
    }
    if timeout_sec is not None:
        safe_timeout = _safe_float(timeout_sec)
        payload["data"]["timeout_sec"] = round(safe_timeout if safe_timeout is not None else 0.0, 3)
    return payload


async def _run_workflow_stage(
    *,
    step: str,
    coro: Any,
    deadline: float,
    stage_timeout: float,
) -> dict[str, Any]:
    remaining = deadline - time.perf_counter()
    if remaining <= 0.5:
        return _budget_fail_response(step=step, message="workflow_budget_exhausted", timeout_sec=0.0)

    safe_stage_timeout = _safe_float(stage_timeout)
    timeout_sec = max(0.5, min(safe_stage_timeout if safe_stage_timeout is not None else remaining, remaining))
    try:
        return await asyncio.wait_for(coro, timeout=timeout_sec)
    except asyncio.TimeoutError:
        return _budget_fail_response(step=step, message=f"timeout>{timeout_sec:.1f}s", timeout_sec=timeout_sec)
    except Exception as exc:
        return _budget_fail_response(step=step, message=f"{type(exc).__name__}: {exc}", timeout_sec=timeout_sec)


def _meta_quality(
    *,
    workflow_name: str,
    steps: list[dict[str, Any]],
    minimum_quality_passed: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    failed_steps = _collect_failed_steps(steps)
    quality = {
        "status": "good" if not failed_steps else "partial_failed",
        "failed_steps": failed_steps,
        "step_count": len(steps),
        "successful_steps": len(steps) - len(failed_steps),
        "workflow": workflow_name,
    }
    if minimum_quality_passed is not None:
        quality["minimum_quality_passed"] = minimum_quality_passed
    if extra:
        quality.update(extra)
    return quality


async def _persist_optional_artifact(
    *,
    enabled: bool,
    artifact_id: str | None,
    strategy: str,
    payload: dict[str, Any],
) -> str | None:
    if not enabled and not artifact_id:
        return None
    resolved_artifact_id = str(artifact_id or f"{strategy}_{int(time.time())}_{uuid4().hex[:8]}")
    artifact_payload = dict(payload or {})
    artifact_payload["artifact_id"] = resolved_artifact_id
    artifact_payload.setdefault("strategy", strategy)
    artifact_payload.setdefault("strategy_version", "workflow_v1")
    await register_artifact_async(
        artifact_payload
    )
    return resolved_artifact_id

from akshare_mcp._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'ai_workflows_parts',
    'def register(mcp) -> None:\n    @mcp.tool(\n        title="Analyze Stock Workflow",\n        description="AI-facing stock snapshot workflow with profile, kline, financial and decision context.",\n        structured_output=True,\n        meta=build_tool_meta("analyze_stock_workflow"),\n    )\n',
    ['parsers.py', 'payloads.py', 'formatters.py'],
    future_annotations=True,
)
