
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape
from typing import Any
from uuid import uuid4

from ..storage import get_db
from ..tools.finance import get_financials
from ..tools.manager_protocol import LINEAGE_REFERENCE_KEYS
from ..tools.trade_plan import generate_plan
from ..utils import normalize_code
from .analysis_integrity_validator import validate_analysis_integrity
from .artifact_registry import get_artifact_async, list_artifacts_async, register_artifact_async
from .decision_context_builder import build_stock_context, build_user_context
from .decision_contracts import get_unified_decision_summary_payload
from .decision_event_builder import build_event_context
from .decision_quant_builder import build_quant_context

ANALYSIS_STRATEGY = "stock_deep_analysis"
ANALYSIS_VERSION = "stock-deep-analysis.v1"
SUPPORTED_ANALYSIS_TASKS = {"quick_scan", "deep_analysis", "recover_gaps", "rebuild_report", "trade_plan"}
_SUMMARY_ONLY_FIELDS = (
    "run_id",
    "task",
    "status",
    "code",
    "name",
    "market",
    "current_stage",
    "report_ready",
    "digest",
    "gap_count",
    "artifact_ids",
    "resource_uris",
    "updated_at",
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_id(run_id: str, suffix: str | None = None) -> str:
    return run_id if not suffix else f"{run_id}:{suffix}"


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _response_data(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    return dict(data) if isinstance(data, dict) else {}


def _extract_lineage(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(payload or {})
    lineage: dict[str, Any] = {}
    for key in LINEAGE_REFERENCE_KEYS:
        value = source.get(key)
        if value not in (None, "", []):
            lineage[key] = value
    explicit = source.get("lineage")
    if isinstance(explicit, dict):
        for key, value in explicit.items():
            if value not in (None, "", []):
                lineage.setdefault(str(key), value)
    return lineage


def _stage_result(stage: str, *, status: str, success: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "success": success,
        "detail": dict(detail or {}),
        "updated_at": _utcnow_iso(),
    }


def _task_profile(task: str) -> dict[str, Any]:
    normalized = str(task or "deep_analysis").strip().lower()
    if normalized == "quick_scan":
        return {
            "task": normalized,
            "include_report": True,
            "include_trade_plan": False,
            "section_keys": ["overview", "trend_and_structure", "risks_and_counterpoints", "action_plan"],
            "title": "Quick Scan",
        }
    if normalized == "trade_plan":
        return {
            "task": normalized,
            "include_report": True,
            "include_trade_plan": True,
            "section_keys": [
                "overview",
                "trend_and_structure",
                "events_and_catalysts",
                "risks_and_counterpoints",
                "action_plan",
            ],
            "title": "Trade Plan",
        }
    return {
        "task": normalized if normalized in SUPPORTED_ANALYSIS_TASKS else "deep_analysis",
        "include_report": normalized != "recover_gaps",
        "include_trade_plan": False,
        "section_keys": [
            "overview",
            "valuation",
            "financial_quality",
            "trend_and_structure",
            "events_and_catalysts",
            "risks_and_counterpoints",
            "action_plan",
            "evidence_and_gaps",
        ],
        "title": "Deep Analysis",
    }


def _normalize_task(task: str | None) -> str:
    normalized = str(task or "deep_analysis").strip().lower()
    return normalized if normalized in SUPPORTED_ANALYSIS_TASKS else "deep_analysis"


async def _resolve_target(query: str) -> dict[str, Any]:
    raw = str(query or "").strip()
    normalized = normalize_code(raw)
    if len(normalized) == 6 and normalized.isdigit():
        return {
            "query": raw,
            "resolved": True,
            "code": normalized,
            "name": "",
            "resolution_mode": "direct_code",
            "candidates": [],
        }

    if not raw:
        return {
            "query": raw,
            "resolved": False,
            "code": "",
            "name": "",
            "resolution_mode": "empty_query",
            "candidates": [],
        }

    db = get_db()
    rows: list[dict[str, Any]] = []
    try:
        async with db.acquire() as conn:
            fetched = await conn.fetch(
                """
                SELECT code, stock_name, industry, market_cap
                FROM stocks
                WHERE stock_name LIKE $1
                   OR code LIKE $2
                   OR (industry IS NOT NULL AND industry LIKE $1)
                ORDER BY
                  CASE WHEN stock_name = $3 THEN 0 ELSE 1 END,
                  market_cap DESC NULLS LAST
                LIMIT 8
                """,
                f"%{raw}%",
                f"%{raw}%",
                raw,
            )
            rows = [dict(row) for row in fetched]
    except Exception:
        rows = []

    candidates = [
        {
            "code": str(item.get("code") or ""),
            "name": str(item.get("stock_name") or item.get("name") or ""),
            "industry": item.get("industry"),
            "market_cap": _safe_float(item.get("market_cap")),
        }
        for item in rows
        if str(item.get("code") or "").strip()
    ]

    exact_name = [item for item in candidates if item.get("name") == raw]
    if len(exact_name) == 1:
        selected = exact_name[0]
        return {
            "query": raw,
            "resolved": True,
            "code": selected["code"],
            "name": selected["name"],
            "resolution_mode": "exact_name_match",
            "candidates": candidates,
        }

    if len(candidates) == 1:
        selected = candidates[0]
        return {
            "query": raw,
            "resolved": True,
            "code": selected["code"],
            "name": selected["name"],
            "resolution_mode": "single_candidate",
            "candidates": candidates,
        }

    return {
        "query": raw,
        "resolved": False,
        "code": "",
        "name": "",
        "resolution_mode": "ambiguous_name" if candidates else "not_found",
        "candidates": candidates,
    }


async def _persist_artifact(
    *,
    artifact_id: str,
    artifact_type: str,
    code: str,
    run_id: str,
    task: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await register_artifact_async(
        {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "strategy": ANALYSIS_STRATEGY,
            "strategy_version": ANALYSIS_VERSION,
            "code": code,
            "run_id": run_id,
            "task": task,
            "payload": payload,
            "lineage": {"run_id": run_id, "security_code": code},
        }
    )


async def _assemble_contexts(code: str, user_id: str | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    async def _wrap(coro, fallback: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await coro
            return dict(result or {})
        except Exception as exc:
            payload = dict(fallback)
            payload.setdefault("warnings", []).append(f"{type(exc).__name__}: {exc}")
            payload.setdefault("fallback_reason", []).append(f"{type(exc).__name__}: {exc}")
            payload["degraded"] = True
            return payload

    stock_context, quant_context, event_context, user_context = await asyncio.gather(
        _wrap(build_stock_context(code), {"code": code, "score": None, "warnings": [], "fallback_reason": []}),
        _wrap(build_quant_context(code), {"code": code, "score": None, "warnings": [], "fallback_reason": []}),
        _wrap(build_event_context(code), {"code": code, "score": None, "warnings": [], "fallback_reason": []}),
        _wrap(build_user_context(user_id), {"user_id": user_id, "warnings": [], "fallback_reason": [], "degraded": True}),
    )
    return stock_context, quant_context, event_context, user_context


async def _safe_profile_payload(code: str) -> dict[str, Any]:
    try:
        from ...resources.stock_and_watchlist import build_stock_profile_resource_payload

        return await build_stock_profile_resource_payload(code)
    except Exception as exc:
        return {
            "uri": f"resource://stock/{code}/profile",
            "code": code,
            "found": False,
            "error": f"{type(exc).__name__}: {exc}",
            "stock": {"code": code, "name": ""},
            "realtime_quote": {},
        }


async def _safe_financial_payload(code: str) -> dict[str, Any]:
    try:
        result = await get_financials(code)
        return dict(result or {})
    except Exception as exc:
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "data": {},
        }


async def _safe_decision_summary(code: str, investment_style: str, user_id: str | None) -> dict[str, Any]:
    try:
        return await get_unified_decision_summary_payload(
            code=code,
            investment_style=investment_style,
            user_id=user_id,
        )
    except Exception as exc:
        return {
            "code": code,
            "action": "wait",
            "confidence": None,
            "summary": "统一决策摘要构建失败，已降级为等待确认。",
            "reasons": [],
            "risks": [f"{type(exc).__name__}: {exc}"],
            "fallback_reason": [f"{type(exc).__name__}: {exc}"],
        }


def _append_evidence(
    evidence: list[dict[str, Any]],
    *,
    section: str,
    label: str,
    statement: str,
    value: Any,
    source: str,
    source_field: str,
    kind: str = "fact",
) -> None:
    if value in (None, "", [], {}):
        return
    evidence_id = f"ev{len(evidence) + 1:02d}"
    evidence.append(
        {
            "evidence_id": evidence_id,
            "section": section,
            "kind": kind,
            "label": label,
            "statement": statement,
            "value": value,
            "source": source,
            "source_field": source_field,
        }
    )
