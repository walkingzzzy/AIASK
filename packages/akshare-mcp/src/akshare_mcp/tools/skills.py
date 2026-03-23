"""Skill tools with safe orchestrated execution."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from ..utils import normalize_code, ok, fail


_FALLBACK_SKILLS: List[Dict[str, Any]] = [
    {
        "id": "momentum_screen",
        "name": "Momentum Screen",
        "category": "screening",
        "description": "fallback demo",
    },
    {
        "id": "value_screen",
        "name": "Value Screen",
        "category": "screening",
        "description": "fallback demo",
    },
    {
        "id": "trend_follow",
        "name": "Trend Follow",
        "category": "strategy",
        "description": "fallback demo",
    },
]

_SKILL_STATUS_VALUES = {"registered", "executable", "deprecated"}
_ORCHESTRATED_SKILL_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "task": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["completed", "partial_failed", "unsupported_task"],
        },
        "steps": {"type": "array", "items": {"type": "object"}},
        "summary": {"type": "object"},
    },
    "required": ["task", "status", "steps", "summary"],
    "additionalProperties": True,
}

_SKILL_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "akshare-market": {
        "supported_tasks": ["smoke_test", "quick_scan", "quote_only"],
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "enum": ["smoke_test", "quick_scan", "quote_only"],
                },
                "code": {"type": "string", "description": "6-digit stock code"},
                "daily_limit": {"type": "integer", "minimum": 1},
                "minute_limit": {"type": "integer", "minimum": 1},
                "minute_period": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
    },
    "akshare-fund-manager-pro": {
        "supported_tasks": ["full_cycle", "daily_brief", "smoke_test"],
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "enum": ["full_cycle", "daily_brief", "smoke_test"],
                },
                "codes": {"type": "array", "items": {"type": "string"}},
                "code": {"type": "string"},
                "lookback_days": {"type": "integer", "minimum": 30},
                "total_capital": {"type": "number"},
                "method": {"type": "string"},
                "confidence": {"type": "number"},
                "benchmark": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
    },
}

_SKILL_CONTRACTS.update(
    {
        "akshare-asset-allocation": {
            "supported_tasks": ["allocation_plan", "rebalance_plan", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["allocation_plan", "rebalance_plan", "smoke_test"]},
                    "risk_profile": {"type": "string"},
                    "horizon_years": {"type": "number"},
                    "total_capital": {"type": "number"},
                    "liquidity_buffer": {"type": "number"},
                    "max_drawdown": {"type": "number"},
                    "asset_scope": {"type": "array", "items": {"type": "string"}},
                    "rebalance_frequency": {"type": "string"},
                    "rebalance_threshold": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-fee-costs": {
            "supported_tasks": ["cost_sensitivity", "single_backtest", "batch_backtest", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "enum": ["cost_sensitivity", "single_backtest", "batch_backtest", "smoke_test"],
                    },
                    "code": {"type": "string"},
                    "codes": {"type": "array", "items": {"type": "string"}},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "initial_capital": {"type": "number"},
                    "commission": {"type": "number"},
                    "slippage": {"type": "number"},
                    "turnover_per_year": {"type": "number"},
                    "years": {"type": "integer"},
                    "annual_return_assumption": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-factor-mining": {
            "supported_tasks": ["candidate_pipeline", "candidate_generation", "candidate_registry", "scheduler_check", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "enum": ["candidate_pipeline", "candidate_generation", "candidate_registry", "scheduler_check", "smoke_test"],
                    },
                    "code": {"type": "string"},
                    "codes": {"type": "array", "items": {"type": "string"}},
                    "stock_codes": {"type": "array", "items": {"type": "string"}},
                    "artifact_id": {"type": "string"},
                    "candidate_index": {"type": "integer", "minimum": 0},
                    "candidate_count": {"type": "integer", "minimum": 1},
                    "lookback_bars": {"type": "integer", "minimum": 120},
                    "horizon_days": {"type": "integer", "minimum": 3},
                    "max_dates": {"type": "integer", "minimum": 20},
                    "limit": {"type": "integer", "minimum": 1},
                    "candidate": {"type": "object"},
                    "op": {"type": "string"},
                    "memory_op": {"type": "string"},
                    "run_scheduler_now": {"type": "boolean"},
                    "persist_artifact": {"type": "boolean"},
                    "write_memory": {"type": "boolean"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-fund-news": {
            "supported_tasks": ["news_digest", "research_digest", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["news_digest", "research_digest", "smoke_test"]},
                    "code": {"type": "string"},
                    "keyword": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "news_limit": {"type": "integer", "minimum": 1},
                    "research_limit": {"type": "integer", "minimum": 1},
                    "market_news_limit": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-fundamental": {
            "supported_tasks": ["fundamental_snapshot", "financials_only", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["fundamental_snapshot", "financials_only", "smoke_test"]},
                    "code": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-investor-protection": {
            "supported_tasks": ["protection_brief", "audit_log", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["protection_brief", "audit_log", "smoke_test"]},
                    "region": {"type": "string"},
                    "broker_region": {"type": "string"},
                    "recommendation_context": {"type": "object"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-ips-discipline": {
            "supported_tasks": ["draft_ips", "discipline_checklist", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["draft_ips", "discipline_checklist", "smoke_test"]},
                    "goal": {"type": "string"},
                    "horizon_years": {"type": "number"},
                    "risk_profile": {"type": "string"},
                    "max_drawdown": {"type": "number"},
                    "liquidity_need": {"type": "string"},
                    "rebalance_frequency": {"type": "string"},
                    "rebalance_threshold": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-macro-options-alerts": {
            "supported_tasks": ["macro_options_brief", "alert_blueprint", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["macro_options_brief", "alert_blueprint", "smoke_test"]},
                    "indicator": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "underlying": {"type": "string"},
                    "expiry_month": {"type": "string"},
                    "alert_name": {"type": "string"},
                    "threshold": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-performance-attribution": {
            "supported_tasks": ["attribution_report", "benchmark_frame", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["attribution_report", "benchmark_frame", "smoke_test"]},
                    "holdings": {"type": "array", "items": {"type": "object"}},
                    "portfolio_return": {"type": "number"},
                    "benchmark_return": {"type": "number"},
                    "risk_sources": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-portfolio": {
            "supported_tasks": ["portfolio_backtest", "batch_backtest", "allocation_snapshot", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "enum": ["portfolio_backtest", "batch_backtest", "allocation_snapshot", "smoke_test"],
                    },
                    "code": {"type": "string"},
                    "codes": {"type": "array", "items": {"type": "string"}},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "method": {"type": "string"},
                    "initial_capital": {"type": "number"},
                    "commission": {"type": "number"},
                    "slippage": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-portfolio-manager-core": {
            "supported_tasks": ["closed_loop_plan", "execution_gate", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["closed_loop_plan", "execution_gate", "smoke_test"]},
                    "goal": {"type": "string"},
                    "risk_profile": {"type": "string"},
                    "codes": {"type": "array", "items": {"type": "string"}},
                    "max_position_pct": {"type": "number"},
                    "max_drawdown": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-quant": {
            "supported_tasks": ["factor_inventory", "signal_research", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["factor_inventory", "signal_research", "smoke_test"]},
                    "code": {"type": "string"},
                    "factor": {"type": "string"},
                    "window_days": {"type": "integer", "minimum": 10},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-quant-data-engineering": {
            "supported_tasks": ["quality_check", "warmup_blueprint", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["quality_check", "warmup_blueprint", "smoke_test"]},
                    "code": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-quant-methods-foundation": {
            "supported_tasks": ["risk_metrics", "correlation_frame", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["risk_metrics", "correlation_frame", "smoke_test"]},
                    "series": {"type": "object"},
                    "annualization_factor": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-quant-ml-signals": {
            "supported_tasks": ["signal_guardrails", "research_card", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["signal_guardrails", "research_card", "smoke_test"]},
                    "code": {"type": "string"},
                    "factor": {"type": "string"},
                    "train_window": {"type": "integer"},
                    "test_window": {"type": "integer"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-quant-research-process": {
            "supported_tasks": ["stage_gate", "backtest_gate", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "enum": ["stage_gate", "backtest_gate", "smoke_test"]},
                    "code": {"type": "string"},
                    "codes": {"type": "array", "items": {"type": "string"}},
                    "factor": {"type": "string"},
                    "hypothesis": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
        "akshare-strategy-factory": {
            "supported_tasks": ["factory_cycle", "strategy_review", "runtime_governance", "smoke_test"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "enum": ["factory_cycle", "strategy_review", "runtime_governance", "smoke_test"],
                    },
                    "strategy_id": {"type": "string"},
                    "id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "index_name": {"type": "string"},
                    "trigger_factory_run": {"type": "boolean"},
                    "trigger_runtime_cycle": {"type": "boolean"},
                    "runtime_alert_limit": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": True,
            },
            "output_schema": _ORCHESTRATED_SKILL_OUTPUT_SCHEMA,
        },
    }
)


def _find_repo_skills_root() -> Path | None:
    """Find repo-local .codex/skills from current package location."""
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        candidate = parent / ".codex" / "skills"
        if candidate.is_dir():
            return candidate
    return None


def _find_repo_root() -> Path | None:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / ".codex" / "skills").is_dir():
            return parent
    return None


def _list_skill_roots() -> List[Path]:
    roots: List[Path] = []

    repo_root = _find_repo_skills_root()
    if repo_root is not None:
        roots.append(repo_root)

    home_root = Path.home() / ".codex" / "skills"
    if home_root.is_dir() and home_root not in roots:
        roots.append(home_root)

    return roots


def _filter_visible_skills(skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    visible: List[Dict[str, Any]] = []
    for item in list(skills or []):
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("id") or "").strip()
        if not skill_id:
            continue
        visible.append(dict(item))
    return visible


def _parse_bool_flag(value: Any) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _normalize_skill_status(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if text in _SKILL_STATUS_VALUES:
        return text
    return None


def _parse_skill_md(md_path: Path) -> Dict[str, Any]:
    """Parse SKILL.md front matter."""
    skill_id = md_path.parent.name
    name = skill_id
    description = ""
    status: Optional[str] = None
    deprecated: Optional[bool] = None

    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            for line in lines[1:]:
                s = line.strip()
                if s == "---":
                    break
                if ":" not in s:
                    continue
                key, raw_value = s.split(":", 1)
                key = key.strip().lower()
                value = raw_value.strip()
                if key == "name":
                    name = value or name
                elif key == "description":
                    description = value
                elif key == "status":
                    status = _normalize_skill_status(value)
                elif key == "deprecated":
                    deprecated = _parse_bool_flag(value)
    except Exception:
        pass

    category = "general"
    if "-" in skill_id:
        parts = skill_id.split("-")
        if len(parts) >= 2:
            category = parts[1]

    payload = {
        "id": skill_id,
        "name": name,
        "category": category,
        "description": description,
        "path": str(md_path),
    }
    if status is not None:
        payload["status"] = status
    if deprecated is not None:
        payload["deprecated"] = deprecated
    return payload


def _load_skills() -> List[Dict[str, Any]]:
    skills_roots = _list_skill_roots()
    if not skills_roots:
        return _filter_visible_skills(_FALLBACK_SKILLS)

    deduped: Dict[str, Dict[str, Any]] = {}
    for skills_root in skills_roots:
        for md in skills_root.glob("*/SKILL.md"):
            if md.parent.name.startswith("_"):
                continue
            parsed = _parse_skill_md(md)
            skill_id = str(parsed.get("id") or "")
            if not skill_id or skill_id in deduped:
                continue
            deduped[skill_id] = parsed

    skills = list(deduped.values())
    if not skills:
        return _filter_visible_skills(_FALLBACK_SKILLS)

    skills.sort(key=lambda x: x.get("id", ""))
    return list(skills or [])


def _available_skill_handlers() -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
    return dict(_SKILL_EXECUTORS)


def _load_skill_coverage_audit() -> Dict[str, Any] | None:
    repo_root = _find_repo_root()
    if repo_root is None:
        return None
    audit_path = repo_root / "skill_tool_coverage_runtime.json"
    if not audit_path.is_file():
        return None
    try:
        payload = json.loads(audit_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _resolve_skill_status(skill: Dict[str, Any], *, handler_available: bool, contract: Dict[str, Any]) -> str:
    if contract.get("deprecated") or skill.get("deprecated"):
        return "deprecated"

    configured_status = (
        _normalize_skill_status(contract.get("status"))
        or _normalize_skill_status(skill.get("status"))
    )
    if configured_status == "deprecated":
        return "deprecated"
    return "executable" if handler_available else "registered"


def _enrich_skills(skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    available_handlers = _available_skill_handlers()
    enriched: List[Dict[str, Any]] = []
    for skill in skills:
        skill_id = str(skill.get("id") or "")
        contract = dict(_SKILL_CONTRACTS.get(skill_id) or {})
        handler_available = skill_id in available_handlers
        status = _resolve_skill_status(skill, handler_available=handler_available, contract=contract)
        executable = status == "executable" and handler_available
        execution_mode = "deprecated" if status == "deprecated" else ("orchestrated" if executable else "no_handler")
        enriched.append(
            {
                **skill,
                "status": status,
                "executable": executable,
                "deprecated": status == "deprecated",
                "handler_available": handler_available,
                "execution_mode": execution_mode,
                "input_schema": contract.get("input_schema") or skill.get("input_schema"),
                "output_schema": contract.get("output_schema") or skill.get("output_schema"),
                "supported_tasks": list(contract.get("supported_tasks") or skill.get("supported_tasks") or []),
            }
        )
    return enriched


def _build_skill_registry_summary(skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(list(skills or []))
    executable = len([skill for skill in skills if skill.get("executable")])
    deprecated = len([skill for skill in skills if skill.get("status") == "deprecated"])
    registered_only = len([skill for skill in skills if skill.get("status") == "registered"])
    execution_gap = [
        {
            "id": skill.get("id"),
            "name": skill.get("name"),
            "status": skill.get("status"),
            "execution_mode": skill.get("execution_mode"),
        }
        for skill in skills
        if not skill.get("executable") and skill.get("status") != "deprecated"
    ][:20]
    audit = _load_skill_coverage_audit() or {}
    tool_reference_coverage = dict(audit.get("coverage") or {})
    tool_reference_coverage.update(
        {
            "tool_count": int(audit.get("tool_count") or 0),
            "skills_count": int(audit.get("skills_count") or 0),
            "generated_at": audit.get("generated_at"),
        }
    )
    executors = dict(audit.get("executors") or {})
    available_handlers = sorted(_available_skill_handlers().keys())
    return {
        "total_count": total,
        "executable_count": executable,
        "registered_only_count": registered_only,
        "deprecated_count": deprecated,
        "executor_coverage_ratio": round(executable / total, 4) if total else 0.0,
        "executable_skill_ids": [skill.get("id") for skill in skills if skill.get("executable")],
        "execution_gap": execution_gap,
        "available_handlers": available_handlers,
        "tool_reference_coverage": tool_reference_coverage or None,
        "executor_audit": executors or None,
    }


def _normalize_params(params: Any) -> Dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, dict):
        return dict(params)
    if isinstance(params, str):
        raw = params.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"raw_params": params}
    return {"raw_params": params}


def _skills_source(skills: List[Dict[str, Any]]) -> str:
    return "codex_registry" if skills and any(skill.get("path") for skill in skills) else "fallback_demo"


def _skill_meta(
    *,
    backend_requested: str,
    backend_used: str,
    fallback_used: bool,
    fallback_reason: Any = None,
    started_at: datetime | None = None,
) -> Dict[str, Any]:
    latency_ms = 0
    if started_at is not None:
        latency_ms = max(0, int((datetime.now() - started_at).total_seconds() * 1000))
    return {
        "backend_requested": backend_requested,
        "backend_used": backend_used,
        "fallback_used": bool(fallback_used),
        "fallback_reason": fallback_reason,
        "latency_ms": latency_ms,
    }


def _skill_payload(
    payload: Dict[str, Any],
    *,
    backend_requested: str,
    backend_used: str,
    fallback_used: bool,
    fallback_reason: Any = None,
    started_at: datetime | None = None,
) -> Dict[str, Any]:
    return {
        **payload,
        **_skill_meta(
            backend_requested=backend_requested,
            backend_used=backend_used,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            started_at=started_at,
        ),
    }


def _skill_ok(
    payload: Dict[str, Any],
    *,
    backend_requested: str,
    backend_used: str,
    fallback_used: bool,
    fallback_reason: Any = None,
    started_at: datetime | None = None,
) -> Dict[str, Any]:
    return ok(
        _skill_payload(
            payload,
            backend_requested=backend_requested,
            backend_used=backend_used,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            started_at=started_at,
        )
    )


def _skill_fail(
    error: Any,
    *,
    backend_requested: str,
    backend_used: str,
    fallback_used: bool,
    fallback_reason: Any = None,
    started_at: datetime | None = None,
    error_code: str | None = None,
    detail: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result = fail(error)
    result["message"] = str(error)
    if error_code is not None:
        result["error_code"] = error_code
    if detail is not None:
        result["detail"] = detail
    result.update(
        _skill_meta(
            backend_requested=backend_requested,
            backend_used=backend_used,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            started_at=started_at,
        )
    )
    return result


def _step_result(step: str, output: Any = None, error: str | None = None) -> Dict[str, Any]:
    if error is not None:
        return {"step": step, "success": False, "error": error}
    if isinstance(output, dict):
        return {"step": step, "success": bool(output.get("success", True)), "output": output}
    return {"step": step, "success": True, "output": output}


def _run_step(step: str, fn: Callable[..., Any], **kwargs: Any) -> Dict[str, Any]:
    try:
        result = fn(**kwargs)
        return _step_result(step, output=result)
    except Exception as e:
        return _step_result(step, error=f"{type(e).__name__}: {e}")


async def _run_step_async(step: str, fn: Callable[..., Any], **kwargs: Any) -> Dict[str, Any]:
    import inspect
    try:
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return _step_result(step, output=result)
    except Exception as e:
        return _step_result(step, error=f"{type(e).__name__}: {e}")


def _finalize_skill_result(
    task: str,
    steps: List[Dict[str, Any]],
    *,
    backend_requested: str = "skill_orchestrator",
    backend_used: str = "skill_orchestrator",
    fallback_used: bool = False,
    fallback_reason: Any = None,
    started_at: datetime | None = None,
) -> Dict[str, Any]:
    failed = [s["step"] for s in steps if not s.get("success")]
    return _skill_payload(
        {
            "task": task,
            "status": "completed" if not failed else "partial_failed",
            "steps": steps,
            "summary": {
                "total_steps": len(steps),
                "failed_steps": failed,
                "success_count": len(steps) - len(failed),
                "failed_count": len(failed),
            },
        },
        backend_requested=backend_requested,
        backend_used=backend_used,
        fallback_used=fallback_used or bool(failed),
        fallback_reason=fallback_reason if fallback_reason is not None else (failed or None),
        started_at=started_at,
    )


def _unsupported_task_result(task: str, supported_tasks: List[str]) -> Dict[str, Any]:
    return {
        "task": task,
        "status": "unsupported_task",
        "steps": [],
        "summary": {
            "total_steps": 0,
            "failed_steps": [],
            "supported_tasks": supported_tasks,
        },
    }


def _safe_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_codes_input(raw_codes: Any, fallback: List[str]) -> List[str]:
    values: List[str] = []
    if isinstance(raw_codes, str):
        values = [item.strip() for item in raw_codes.split(",") if item.strip()]
    elif isinstance(raw_codes, list):
        values = [str(item or "").strip() for item in raw_codes if str(item or "").strip()]
    deduped: List[str] = []
    seen: set[str] = set()
    for raw in values or fallback:
        code = normalize_code(str(raw or ""))
        if not code or code in seen:
            continue
        seen.add(code)
        deduped.append(code)
    return deduped or [normalize_code(str(fallback[0] or "600519"))]


def _normalize_holdings_input(params: Dict[str, Any], default_codes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    raw_holdings = params.get("holdings")
    if isinstance(raw_holdings, list) and raw_holdings:
        parsed: List[Dict[str, Any]] = []
        for item in raw_holdings:
            if not isinstance(item, dict):
                continue
            code = normalize_code(str(item.get("code") or item.get("symbol") or ""))
            if not code:
                continue
            parsed.append(
                {
                    "code": code,
                    "weight": _safe_float(item.get("weight"), 0.0),
                    "value": _safe_float(item.get("value"), 0.0),
                    "return_pct": _safe_float(item.get("return_pct"), 0.0),
                }
            )
        if parsed:
            total_weight = sum(max(0.0, float(item.get("weight") or 0.0)) for item in parsed) or 1.0
            return [
                {
                    **item,
                    "weight": round(max(0.0, float(item.get("weight") or 0.0)) / total_weight, 6),
                }
                for item in parsed
            ]

    codes = _normalize_codes_input(params.get("codes") or params.get("code"), default_codes or ["600519", "000001", "510300"])
    weight = round(1.0 / len(codes), 6) if codes else 1.0
    notional = _safe_float(params.get("initial_capital") or params.get("total_capital"), 1_000_000.0)
    return [
        {
            "code": code,
            "weight": weight,
            "value": round(notional * weight, 2),
            "return_pct": _safe_float(params.get("default_return_pct"), 0.0),
        }
        for code in codes
    ]


def _default_notice_window(params: Dict[str, Any]) -> tuple[str, str]:
    end_date = str(params.get("end_date") or datetime.now().strftime("%Y-%m-%d"))
    start_date = str(
        params.get("start_date")
        or (datetime.now() - timedelta(days=_safe_int(params.get("window_days"), 30))).strftime("%Y-%m-%d")
    )
    return start_date, end_date


def _normalize_rebalance_threshold(value: Any, default: float = 0.08) -> float:
    threshold = _safe_float(value, default)
    if threshold > 1:
        threshold = threshold / 100.0
    return max(0.01, min(threshold, 0.30))


def _static_step(step: str, output: Dict[str, Any]) -> Dict[str, Any]:
    return _step_result(step, output=output)


def _response_data_dict(response: Any) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    return dict(data) if isinstance(data, dict) else {}


async def _exec_market(params: Dict[str, Any]) -> Dict[str, Any]:
    from .market.kline import get_kline, get_kline_data, get_minute_kline
    from .market.order_book import get_order_book
    from .market.quote import get_realtime_quote

    task = str(params.get("task") or "smoke_test").strip().lower()
    code = normalize_code(str(params.get("code") or "600519"))

    daily_limit = int(params.get("daily_limit", 30) or 30)
    minute_limit = int(params.get("minute_limit", 30) or 30)
    minute_period = str(params.get("minute_period") or "5m")
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    steps: List[Dict[str, Any]] = []
    if task in {"smoke_test", "quick_scan"}:
        steps.append(_run_step("get_realtime_quote", get_realtime_quote, stock_code=code))
        if start_date or end_date:
            steps.append(
                await _run_step_async(
                    "get_kline_data",
                    get_kline_data,
                    code=code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    limit=daily_limit,
                )
            )
        else:
            steps.append(await _run_step_async("get_kline", get_kline, stock_code=code, period="daily", limit=daily_limit))
        steps.append(
            _run_step("get_minute_kline", get_minute_kline, stock_code=code, period=minute_period, limit=minute_limit)
        )
        steps.append(_run_step("get_order_book", get_order_book, stock_code=code))
        return _finalize_skill_result(task, steps)

    if task in {"quote_only", "quote"}:
        steps.append(_run_step("get_realtime_quote", get_realtime_quote, stock_code=code))
        return _finalize_skill_result(task, steps)

    return {
        "task": task,
        "status": "unsupported_task",
        "steps": [],
        "summary": {
            "total_steps": 0,
            "failed_steps": [],
            "supported_tasks": ["smoke_test", "quick_scan", "quote_only"],
        },
    }


async def _exec_fund_manager_pro(params: Dict[str, Any]) -> Dict[str, Any]:
    from .market.kline import get_kline
    from .market.quote import get_realtime_quote
    from .news import get_stock_notices, get_stock_research
    from ..services import backtest_engine
    from ..services.portfolio_optimization import simple_portfolio_optimizer as portfolio_optimizer
    from ..services.risk_model import risk_model

    task = str(params.get("task") or "full_cycle").strip().lower()

    raw_codes = params.get("codes")
    if isinstance(raw_codes, str):
        raw_codes = [x.strip() for x in raw_codes.split(",") if x and str(x).strip()]
    if not isinstance(raw_codes, list) or not raw_codes:
        raw_codes = [params.get("code") or "600519", "000001", "000858"]

    dedup_codes: List[str] = []
    seen: set[str] = set()
    for raw in raw_codes:
        code = normalize_code(str(raw or ""))
        if not code or code in seen:
            continue
        seen.add(code)
        dedup_codes.append(code)
    if not dedup_codes:
        dedup_codes = ["600519", "000001", "000858"]

    lead_code = dedup_codes[0]
    lookback_days = max(30, int(params.get("lookback_days", 120) or 120))
    total_capital = float(params.get("total_capital", 1_000_000) or 1_000_000)
    optimization_method = str(params.get("method") or "equal_weight").strip().lower()
    confidence = float(params.get("confidence", 0.95) or 0.95)

    context: Dict[str, Any] = {
        "codes": dedup_codes,
        "lead_code": lead_code,
        "lookback_days": lookback_days,
        "total_capital": total_capital,
        "optimization_method": optimization_method,
        "confidence": confidence,
    }
    steps: List[Dict[str, Any]] = []

    def _research_step() -> Dict[str, Any]:
        end_date = str(params.get("end_date") or datetime.now().strftime("%Y-%m-%d"))
        start_date = str(
            params.get("start_date")
            or (datetime.now() - timedelta(days=int(params.get("event_window_days", 30) or 30))).strftime("%Y-%m-%d")
        )

        research_res = get_stock_research(stock_code=lead_code, limit=int(params.get("research_limit", 5) or 5))
        notices_res = get_stock_notices(start_date=start_date, end_date=end_date, stock_code=lead_code)

        context["research"] = {"reports": research_res, "events": notices_res}

        reports_count = 0
        if isinstance(research_res, dict) and research_res.get("success"):
            reports_count = int((research_res.get("data") or {}).get("total") or 0)

        events_count = 0
        if isinstance(notices_res, dict) and notices_res.get("success"):
            events_count = len(((notices_res.get("data") or {}).get("events") or []))

        fallback_reasons = [
            reason
            for reason in [
                "research_reports_empty" if reports_count == 0 else None,
                "events_empty" if events_count == 0 else None,
            ]
            if reason
        ]

        return ok(
            {
                "lead_code": lead_code,
                "window": {"start_date": start_date, "end_date": end_date},
                "reports_count": reports_count,
                "events_count": events_count,
                "fallback_used": bool(fallback_reasons),
                "fallback_reason": fallback_reasons or None,
            }
        )

    async def _portfolio_step() -> Dict[str, Any]:
        market_data: Dict[str, Dict[str, Any]] = {}
        dropped: List[str] = []
        returns_list: List[np.ndarray] = []
        valid_codes: List[str] = []

        for code in dedup_codes:
            kline_res = await get_kline(stock_code=code, period="daily", limit=max(lookback_days + 10, 80))
            if not (isinstance(kline_res, dict) and kline_res.get("success")):
                dropped.append(code)
                continue

            rows = kline_res.get("data") or []
            cleaned_rows = [r for r in rows if isinstance(r, dict) and r.get("close") is not None]
            if len(cleaned_rows) < 30:
                dropped.append(code)
                continue

            closes = []
            for row in cleaned_rows:
                try:
                    closes.append(float(row.get("close")))
                except Exception:
                    pass
            if len(closes) < 30:
                dropped.append(code)
                continue

            returns = np.diff(np.array(closes, dtype=float)) / np.array(closes[:-1], dtype=float)
            if len(returns) < 20:
                dropped.append(code)
                continue

            valid_codes.append(code)
            returns_list.append(returns)
            market_data[code] = {
                "rows": cleaned_rows,
                "latest_close": float(closes[-1]),
                "series_len": len(closes),
            }

        if not valid_codes:
            return fail("No valid codes with sufficient kline data for portfolio construction")

        min_len = min(len(x) for x in returns_list)
        returns_matrix = np.array([x[-min_len:] for x in returns_list], dtype=float)

        weights_map: Dict[str, float]
        method_used = optimization_method
        try:
            if optimization_method == "risk_parity" and len(valid_codes) >= 2:
                weights_map = portfolio_optimizer.optimize_risk_parity(valid_codes, returns_matrix)
            elif optimization_method == "mean_variance" and len(valid_codes) >= 2:
                expected_returns = np.mean(returns_matrix, axis=1)
                weights_map = portfolio_optimizer.optimize_mean_variance(
                    valid_codes, returns_matrix, expected_returns, risk_aversion=float(params.get("risk_aversion", 1.0) or 1.0)
                )
            elif optimization_method == "max_sharpe" and len(valid_codes) >= 2:
                expected_returns = np.mean(returns_matrix, axis=1)
                weights_map = portfolio_optimizer.optimize_max_sharpe(
                    valid_codes,
                    returns_matrix,
                    expected_returns,
                    risk_free_rate=float(params.get("risk_free_rate", 0.03) or 0.03),
                ).get("weights", {})
            else:
                method_used = "equal_weight"
                weights_map = portfolio_optimizer.optimize_equal_weight(valid_codes)
        except Exception:
            method_used = "equal_weight_fallback"
            weights_map = portfolio_optimizer.optimize_equal_weight(valid_codes)

        weight_sum = sum(float(v) for v in weights_map.values()) or 1.0
        normalized_weights = {code: float(weights_map.get(code, 0.0)) / weight_sum for code in valid_codes}

        holdings: List[Dict[str, Any]] = []
        for code in valid_codes:
            w = float(normalized_weights.get(code, 0.0))
            latest = float(market_data[code]["latest_close"])
            value = total_capital * w
            holdings.append({"code": code, "weight": w, "value": value, "latest_close": latest})

        context["portfolio"] = {
            "valid_codes": valid_codes,
            "dropped_codes": dropped,
            "weights": normalized_weights,
            "returns_matrix": returns_matrix,
            "holdings": holdings,
            "market_data": market_data,
            "method_used": method_used,
        }

        return ok(
            {
                "method_used": method_used,
                "valid_codes": valid_codes,
                "dropped_codes": dropped,
                "weights": normalized_weights,
                "lookback_days": lookback_days,
            }
        )

    def _risk_step() -> Dict[str, Any]:
        portfolio_ctx = context.get("portfolio") or {}
        holdings = portfolio_ctx.get("holdings") or []
        returns_matrix = portfolio_ctx.get("returns_matrix")
        if not holdings or returns_matrix is None:
            return fail("Portfolio context missing; cannot run risk stage")

        weights = np.array([float(h["weight"]) for h in holdings], dtype=float)
        if len(weights) == 1:
            portfolio_returns = returns_matrix[0]
            var_result = risk_model.calculate_var(
                portfolio_returns.tolist(), confidence=confidence, portfolio_value=total_capital
            )
            risk_result = {
                "volatility": float(np.std(portfolio_returns)),
                "annual_volatility": float(np.std(portfolio_returns) * np.sqrt(252)),
                "variance": float(np.var(portfolio_returns)),
            }
        else:
            portfolio_returns = np.dot(weights, returns_matrix)
            var_result = risk_model.calculate_var(
                portfolio_returns.tolist(), confidence=confidence, portfolio_value=total_capital
            )
            risk_result = risk_model.calculate_portfolio_risk(
                [{"code": h["code"], "weight": float(h["weight"])} for h in holdings], returns_matrix
            )

        scenario_list = params.get("scenarios") or ["market_crash", "sector_rotation"]
        if isinstance(scenario_list, str):
            scenario_list = [x.strip() for x in scenario_list.split(",") if x.strip()]
        stress_results = []
        for scenario in scenario_list:
            stress_results.append(risk_model.stress_test(holdings, scenario=scenario))

        context["risk"] = {
            "var": var_result,
            "risk": risk_result,
            "stress_tests": stress_results,
            "portfolio_returns": portfolio_returns,
        }

        return ok(
            {
                "confidence": confidence,
                "var": var_result,
                "risk": risk_result,
                "stress_tests": stress_results,
            }
        )

    def _compliance_step() -> Dict[str, Any]:
        portfolio_ctx = context.get("portfolio") or {}
        holdings = portfolio_ctx.get("holdings") or []
        if not holdings:
            return fail("Portfolio context missing; cannot run compliance stage")

        first = holdings[0]
        order_code = str(params.get("order_code") or first["code"])
        direction = str(params.get("direction") or "buy").strip().lower()

        price = None
        for h in holdings:
            if h["code"] == order_code:
                price = h.get("latest_close")
                break

        try:
            quote_res = get_realtime_quote(stock_code=order_code)
            if isinstance(quote_res, dict):
                if quote_res.get("success"):
                    quote_price = (quote_res.get("data") or {}).get("price")
                    if quote_price is not None:
                        price = quote_price
                elif quote_res.get("price") is not None:
                    price = quote_res.get("price")
        except Exception:
            quote_res = None
        if price is None:
            return fail(f"Cannot resolve price for compliance check: {order_code}")

        target_value = total_capital * float(first["weight"])
        quantity = int(params.get("quantity") or (target_value / float(price) // 100) * 100)
        order_value = float(quantity) * float(price)
        max_single_order_pct = float(params.get("max_single_order_pct", 0.40) or 0.40)
        max_position_pct = float(params.get("max_position_pct", 0.40) or 0.40)

        checks = {
            "lot_size_100": quantity > 0 and quantity % 100 == 0,
            "price_positive": float(price) > 0,
            "single_order_limit": order_value <= total_capital * max_single_order_pct,
            "position_limit": float(first["weight"]) <= max_position_pct,
            "direction_valid": direction in {"buy", "sell"},
        }
        issues = [k for k, passed in checks.items() if not passed]
        passed = len(issues) == 0

        context["compliance"] = {
            "passed": passed,
            "issues": issues,
            "order": {
                "code": order_code,
                "direction": direction,
                "quantity": quantity,
                "price": float(price),
                "order_value": order_value,
            },
            "checks": checks,
        }

        return ok(
            {
                "mode": "equivalent_check",
                "passed": passed,
                "issues": issues,
                "checks": checks,
                "order": context["compliance"]["order"],
            }
        )

    def _execution_step() -> Dict[str, Any]:
        compliance_ctx = context.get("compliance") or {}
        if not compliance_ctx:
            return fail("Compliance context missing; cannot build execution plan")

        if not compliance_ctx.get("passed"):
            return fail(f"Compliance gate not passed: {compliance_ctx.get('issues')}")

        order = compliance_ctx.get("order") or {}
        quantity = int(order.get("quantity") or 0)
        duration_minutes = max(5, int(params.get("duration_minutes", 60) or 60))
        slices = max(1, int(params.get("slices", 6) or 6))
        interval = max(1, duration_minutes // slices)

        base = quantity // slices
        remainder = quantity % slices
        plan: List[Dict[str, Any]] = []
        for idx in range(slices):
            plan.append(
                {
                    "slice": idx + 1,
                    "offset_min": idx * interval,
                    "quantity": base + (1 if idx < remainder else 0),
                    "algo": "twap",
                }
            )

        context["execution"] = {
            "task": "twap_plan_only",
            "duration_minutes": duration_minutes,
            "slices": slices,
            "plan": plan,
            "order": order,
        }
        return ok(context["execution"])

    async def _review_step() -> Dict[str, Any]:
        portfolio_ctx = context.get("portfolio") or {}
        market_data = portfolio_ctx.get("market_data") or {}
        lead_rows = (market_data.get(lead_code) or {}).get("rows") or []
        if len(lead_rows) < 30:
            return fail(f"Insufficient kline rows for review: {lead_code}")

        benchmark = normalize_code(str(params.get("benchmark") or "000300"))
        benchmark_rows: List[Dict[str, Any]] = []
        benchmark_res = await get_kline(stock_code=benchmark, period="daily", limit=len(lead_rows))
        if isinstance(benchmark_res, dict) and benchmark_res.get("success"):
            benchmark_rows = benchmark_res.get("data") or []

        backtest_params = {
            "initial_capital": float(total_capital * float(portfolio_ctx.get("weights", {}).get(lead_code, 1.0))),
            "commission": float(params.get("commission", 0.0003) or 0.0003),
            "slippage": float(params.get("slippage", 0.0001) or 0.0001),
            "short_period": int(params.get("short_period", 5) or 5),
            "long_period": int(params.get("long_period", 20) or 20),
            "benchmark": benchmark,
            "benchmark_klines": benchmark_rows,
        }
        backtest_result = backtest_engine.run_backtest(
            lead_code,
            lead_rows,
            strategy=str(params.get("strategy") or "ma_cross"),
            params=backtest_params,
        )
        if not backtest_result.get("success"):
            return fail(backtest_result.get("error") or "Backtest failed")

        risk_ctx = context.get("risk") or {}
        review_data = {
            "lead_code": lead_code,
            "backtest": backtest_result.get("data"),
            "risk_snapshot": {
                "var": risk_ctx.get("var"),
                "volatility": (risk_ctx.get("risk") or {}).get("annual_volatility"),
            },
        }
        context["review"] = review_data
        return ok(review_data)

    if task in {"full_cycle", "daily_brief", "smoke_test"}:
        steps.append(_run_step("research", _research_step))
        steps.append(await _run_step_async("portfolio_construction", _portfolio_step))
        steps.append(_run_step("risk_assessment", _risk_step))
        steps.append(_run_step("compliance_check", _compliance_step))
        steps.append(_run_step("execution_plan", _execution_step))
        steps.append(await _run_step_async("performance_review", _review_step))

        result = _finalize_skill_result(task, steps)
        ring_names = [
            "research",
            "portfolio_construction",
            "risk_assessment",
            "compliance_check",
            "execution_plan",
            "performance_review",
        ]
        ring_status = {
            ring: next((bool(s.get("success")) for s in steps if s.get("step") == ring), False)
            for ring in ring_names
        }
        result["summary"]["ring_status"] = ring_status
        result["summary"]["ring_count"] = len(ring_names)
        result["summary"]["ring_passed"] = sum(1 for v in ring_status.values() if v)
        result["summary"]["closed_loop_gate"] = all(ring_status.values())
        result["summary"]["note"] = (
            "Equivalent compliance and execution planning are used inside run_skill orchestrator; "
            "no live order is sent."
        )
        return result

    return {
        "task": task,
        "status": "unsupported_task",
        "steps": [],
        "summary": {
            "total_steps": 0,
            "failed_steps": [],
            "supported_tasks": ["full_cycle", "daily_brief", "smoke_test"],
        },
    }


def _exec_asset_allocation(params: Dict[str, Any]) -> Dict[str, Any]:
    task = str(params.get("task") or "allocation_plan").strip().lower()
    supported_tasks = ["allocation_plan", "rebalance_plan", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    risk_profile = str(params.get("risk_profile") or "balanced").strip().lower()
    horizon_years = max(1.0, _safe_float(params.get("horizon_years"), 5.0))
    total_capital = max(10_000.0, _safe_float(params.get("total_capital"), 1_000_000.0))
    liquidity_buffer = max(0.03, min(_safe_float(params.get("liquidity_buffer"), 0.10), 0.40))
    max_drawdown = max(0.05, min(_safe_float(params.get("max_drawdown"), 0.18), 0.45))
    rebalance_frequency = str(params.get("rebalance_frequency") or "monthly").strip().lower()
    rebalance_threshold = _normalize_rebalance_threshold(params.get("rebalance_threshold"), 0.08)

    model_map = {
        "conservative": {"equity_etf": 0.30, "bond_etf": 0.45, "gold_etf": 0.10, "cash": 0.15},
        "balanced": {"equity_etf": 0.55, "bond_etf": 0.25, "gold_etf": 0.10, "cash": 0.10},
        "growth": {"equity_etf": 0.72, "bond_etf": 0.12, "gold_etf": 0.08, "cash": 0.08},
        "aggressive": {"equity_etf": 0.82, "bond_etf": 0.06, "gold_etf": 0.06, "cash": 0.06},
    }
    target = dict(model_map.get(risk_profile, model_map["balanced"]))
    if horizon_years <= 3:
        shift = min(0.12, target.get("equity_etf", 0.0) * 0.2)
        target["equity_etf"] = max(0.0, target.get("equity_etf", 0.0) - shift)
        target["cash"] = target.get("cash", 0.0) + shift / 2
        target["bond_etf"] = target.get("bond_etf", 0.0) + shift / 2
    if liquidity_buffer > target.get("cash", 0.0):
        transfer = liquidity_buffer - target.get("cash", 0.0)
        target["cash"] = liquidity_buffer
        target["equity_etf"] = max(0.0, target.get("equity_etf", 0.0) - transfer)

    total_weight = sum(target.values()) or 1.0
    allocation = [
        {
            "asset_class": asset_class,
            "weight": round(weight / total_weight, 4),
            "target_value": round(total_capital * weight / total_weight, 2),
        }
        for asset_class, weight in target.items()
    ]
    rebalance_policy = {
        "frequency": rebalance_frequency,
        "threshold": rebalance_threshold,
        "cash_buffer": liquidity_buffer,
        "max_drawdown_guardrail": max_drawdown,
        "action_rule": "Only rebalance when drift exceeds threshold or liquidity/risk constraints change.",
    }
    steps = [
        _static_step(
            "collect_constraints",
            {
                "risk_profile": risk_profile,
                "horizon_years": horizon_years,
                "total_capital": total_capital,
                "liquidity_buffer": liquidity_buffer,
                "max_drawdown": max_drawdown,
            },
        ),
        _static_step("construct_target_allocation", {"allocation": allocation, "model": risk_profile}),
        _static_step("define_rebalance_policy", rebalance_policy),
    ]
    result = _finalize_skill_result(task, steps)
    result["summary"].update(
        {
            "risk_profile": risk_profile,
            "allocation_count": len(allocation),
            "target_allocation": allocation,
            "rebalance_policy": rebalance_policy,
        }
    )
    return result


async def _exec_fee_costs(params: Dict[str, Any]) -> Dict[str, Any]:
    from .backtest import run_batch_backtest, run_simple_backtest

    task = str(params.get("task") or "cost_sensitivity").strip().lower()
    supported_tasks = ["cost_sensitivity", "single_backtest", "batch_backtest", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    if task in {"cost_sensitivity", "smoke_test"}:
        initial_capital = max(10_000.0, _safe_float(params.get("initial_capital"), 1_000_000.0))
        annual_return = _safe_float(params.get("annual_return_assumption"), 0.10)
        turnover = max(0.1, _safe_float(params.get("turnover_per_year"), 3.0))
        years = max(1, _safe_int(params.get("years"), 5))
        scenarios = [
            {
                "label": "low_cost",
                "commission": _safe_float(params.get("low_commission"), 0.0002),
                "slippage": _safe_float(params.get("low_slippage"), 0.0001),
                "stamp_tax": _safe_float(params.get("low_stamp_tax"), 0.0005),
            },
            {
                "label": "base_case",
                "commission": _safe_float(params.get("commission"), 0.0003),
                "slippage": _safe_float(params.get("slippage"), 0.0002),
                "stamp_tax": _safe_float(params.get("stamp_tax"), 0.0005),
            },
            {
                "label": "high_cost",
                "commission": _safe_float(params.get("high_commission"), 0.0008),
                "slippage": _safe_float(params.get("high_slippage"), 0.0006),
                "stamp_tax": _safe_float(params.get("high_stamp_tax"), 0.0010),
            },
        ]
        comparisons = []
        for item in scenarios:
            total_cost_rate = turnover * (item["commission"] + item["slippage"] + item["stamp_tax"])
            net_return = annual_return - total_cost_rate
            terminal_value = initial_capital * ((1.0 + net_return) ** years)
            comparisons.append(
                {
                    "label": item["label"],
                    "annual_cost_rate": round(total_cost_rate, 4),
                    "net_return_assumption": round(net_return, 4),
                    "terminal_value": round(terminal_value, 2),
                    "capital_erosion": round(initial_capital * ((1.0 + annual_return) ** years) - terminal_value, 2),
                }
            )
        steps = [
            _static_step(
                "collect_cost_assumptions",
                {
                    "initial_capital": initial_capital,
                    "annual_return_assumption": annual_return,
                    "turnover_per_year": turnover,
                    "years": years,
                },
            ),
            _static_step("run_cost_sensitivity", {"scenarios": comparisons}),
            _static_step(
                "output_cost_guidance",
                {
                    "guidance": [
                        "Compare broker commission tiers before increasing turnover.",
                        "Treat slippage as a variable with market regime sensitivity.",
                        "Persist cost assumptions together with any backtest snapshot.",
                    ]
                },
            ),
        ]
        result = _finalize_skill_result(task, steps)
        result["summary"]["best_scenario"] = min(comparisons, key=lambda item: item["annual_cost_rate"])
        result["summary"]["worst_scenario"] = max(comparisons, key=lambda item: item["annual_cost_rate"])
        return result

    if task == "single_backtest":
        code = normalize_code(str(params.get("code") or "600519"))
        steps = [
            await _run_step_async(
                "run_simple_backtest",
                run_simple_backtest,
                code=code,
                strategy=str(params.get("strategy") or "ma_cross"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                initial_capital=_safe_float(params.get("initial_capital"), 100_000.0),
                commission=_safe_float(params.get("commission"), 0.0003),
                short_period=_safe_int(params.get("short_period"), 5),
                long_period=_safe_int(params.get("long_period"), 20),
                benchmark=str(params.get("benchmark") or "000300"),
                slippage=_safe_float(params.get("slippage"), 0.0),
            )
        ]
        return _finalize_skill_result(task, steps)

    codes = _normalize_codes_input(params.get("codes"), ["600519", "000001", "000858"])
    steps = [
        await _run_step_async(
            "run_batch_backtest",
            run_batch_backtest,
            codes=codes,
            strategy=str(params.get("strategy") or "ma_cross"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
            initial_capital=_safe_float(params.get("initial_capital"), 100_000.0),
            commission=_safe_float(params.get("commission"), 0.0003),
            short_period=_safe_int(params.get("short_period"), 5),
            long_period=_safe_int(params.get("long_period"), 20),
            use_parallel=bool(params.get("use_parallel", True)),
            fetch_concurrency=_safe_int(params.get("fetch_concurrency"), 8),
        )
    ]
    return _finalize_skill_result(task, steps)


async def _exec_factor_mining(params: Dict[str, Any]) -> Dict[str, Any]:
    from .managers.quant_manager import quant_manager as runtime_quant_manager

    task = str(params.get("task") or "candidate_pipeline").strip().lower()
    supported_tasks = ["candidate_pipeline", "candidate_generation", "candidate_registry", "scheduler_check", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    codes = _normalize_codes_input(
        params.get("stock_codes") or params.get("codes") or params.get("code"),
        ["600519", "000001", "000858"],
    )
    candidate_count = max(1, min(_safe_int(params.get("candidate_count"), 6), 16))
    lookback_bars = max(120, min(_safe_int(params.get("lookback_bars"), 220), 500))
    horizon_days = max(3, min(_safe_int(params.get("horizon_days"), 10), 30))
    max_dates = max(20, min(_safe_int(params.get("max_dates"), 60), 120))
    limit = max(1, min(_safe_int(params.get("limit"), 20), 500))
    candidate_index = max(0, _safe_int(params.get("candidate_index"), 0))
    run_scheduler_now = bool(_parse_bool_flag(params.get("run_scheduler_now")))

    generation_kwargs = {
        "codes": codes,
        "artifact_id": params.get("artifact_id"),
        "candidate_count": candidate_count,
        "lookback_bars": lookback_bars,
        "alternative_lookback_days": max(7, min(_safe_int(params.get("alternative_lookback_days"), 30), 90)),
        "allow_fallback": True if params.get("allow_fallback") is None else bool(params.get("allow_fallback")),
        "persist_artifact": True if params.get("persist_artifact") is None else bool(params.get("persist_artifact")),
        "dedup_mode": str(params.get("dedup_mode") or "penalty"),
        "dedup_high_similarity_threshold": _safe_float(params.get("dedup_high_similarity_threshold"), 0.98),
        "dedup_failure_similarity_threshold": _safe_float(params.get("dedup_failure_similarity_threshold"), 0.93),
        "startup_warmup": bool(_parse_bool_flag(params.get("startup_warmup"))) if params.get("startup_warmup") is not None else None,
        "startup_warmup_force": bool(_parse_bool_flag(params.get("startup_warmup_force"))) if params.get("startup_warmup_force") is not None else None,
        "startup_warmup_limit": max(1, min(_safe_int(params.get("startup_warmup_limit"), 4), 20)),
        "startup_warmup_task_type": str(params.get("startup_warmup_task_type") or "core_market,factor_context"),
    }
    validation_kwargs = {
        "artifact_id": params.get("artifact_id"),
        "candidate_index": candidate_index,
        "candidate": params.get("candidate"),
        "codes": codes,
        "lookback_bars": lookback_bars,
        "horizon_days": horizon_days,
        "max_dates": max_dates,
        "persist_artifact": True if params.get("persist_artifact") is None else bool(params.get("persist_artifact")),
        "write_memory": True if params.get("write_memory") is None else bool(params.get("write_memory")),
        "output_artifact_id": params.get("output_artifact_id"),
    }
    registry_op = str(params.get("op") or "active_pool").strip().lower() or "active_pool"
    memory_op = str(params.get("memory_op") or "stats").strip().lower() or "stats"
    registry_kwargs = {
        "op": registry_op,
        "artifact_id": params.get("artifact_id"),
        "codes": codes,
        "family": params.get("family"),
        "grade": params.get("grade"),
        "recommendation": params.get("recommendation"),
        "min_score": params.get("min_score"),
        "only_active": True if params.get("only_active") is None and registry_op == "active_pool" else bool(params.get("only_active", False)),
        "limit": limit,
    }
    memory_kwargs = {
        "op": memory_op,
        "artifact_id": params.get("artifact_id"),
        "candidate": params.get("candidate"),
        "query_text": params.get("query_text"),
        "codes": codes,
        "status": params.get("status"),
        "family": params.get("family"),
        "limit": limit,
    }

    steps: List[Dict[str, Any]] = []

    if task == "candidate_generation":
        generation_resp = await runtime_quant_manager(action="llm_factor_mining", kwargs=generation_kwargs)
        steps.append(_step_result("quant_manager.llm_factor_mining", output=generation_resp))
        result = _finalize_skill_result(task, steps)
        result["summary"]["codes"] = codes
        result["summary"]["candidate_count"] = candidate_count
        result["summary"]["artifact_id"] = _response_data_dict(generation_resp).get("artifact_id")
        return result

    if task == "candidate_registry":
        registry_resp = await runtime_quant_manager(action="factor_candidate_registry", kwargs=registry_kwargs)
        steps.append(_step_result("quant_manager.factor_candidate_registry", output=registry_resp))
        memory_resp = await runtime_quant_manager(action="factor_research_memory", kwargs=memory_kwargs)
        steps.append(_step_result("quant_manager.factor_research_memory", output=memory_resp))
        result = _finalize_skill_result(task, steps)
        result["summary"]["codes"] = codes
        result["summary"]["registry_op"] = registry_op
        result["summary"]["memory_op"] = memory_op
        return result

    if task == "scheduler_check":
        scheduler_status = await runtime_quant_manager(action="scheduler_status", kwargs={})
        steps.append(_step_result("quant_manager.scheduler_status", output=scheduler_status))
        if run_scheduler_now:
            scheduler_run = await runtime_quant_manager(action="scheduler_run_now", kwargs={})
            steps.append(_step_result("quant_manager.scheduler_run_now", output=scheduler_run))
        result = _finalize_skill_result(task, steps)
        result["summary"]["run_scheduler_now"] = run_scheduler_now
        return result

    generation_resp = await runtime_quant_manager(action="llm_factor_mining", kwargs=generation_kwargs)
    steps.append(_step_result("quant_manager.llm_factor_mining", output=generation_resp))
    generation_data = _response_data_dict(generation_resp)
    resolved_artifact_id = str(params.get("artifact_id") or generation_data.get("artifact_id") or "").strip()

    if resolved_artifact_id or isinstance(params.get("candidate"), dict):
        validation_kwargs["artifact_id"] = resolved_artifact_id or validation_kwargs.get("artifact_id")
        validation_resp = await runtime_quant_manager(action="validate_factor_candidate", kwargs=validation_kwargs)
        steps.append(_step_result("quant_manager.validate_factor_candidate", output=validation_resp))
    else:
        steps.append(
            _static_step(
                "quant_manager.validate_factor_candidate.skipped",
                {"reason": "artifact_id_or_inline_candidate_required"},
            )
        )

    registry_resp = await runtime_quant_manager(action="factor_candidate_registry", kwargs=registry_kwargs)
    steps.append(_step_result("quant_manager.factor_candidate_registry", output=registry_resp))
    memory_resp = await runtime_quant_manager(action="factor_research_memory", kwargs=memory_kwargs)
    steps.append(_step_result("quant_manager.factor_research_memory", output=memory_resp))
    scheduler_status = await runtime_quant_manager(action="scheduler_status", kwargs={})
    steps.append(_step_result("quant_manager.scheduler_status", output=scheduler_status))
    if task == "candidate_pipeline" and run_scheduler_now:
        scheduler_run = await runtime_quant_manager(action="scheduler_run_now", kwargs={})
        steps.append(_step_result("quant_manager.scheduler_run_now", output=scheduler_run))

    result = _finalize_skill_result(task, steps)
    result["summary"].update(
        {
            "codes": codes,
            "candidate_count": candidate_count,
            "artifact_id": resolved_artifact_id or None,
            "registry_op": registry_op,
            "memory_op": memory_op,
            "run_scheduler_now": run_scheduler_now,
        }
    )
    return result


async def _exec_strategy_factory(params: Dict[str, Any]) -> Dict[str, Any]:
    from .managers.strategy_manager import strategy_manager as runtime_strategy_manager

    task = str(params.get("task") or "factory_cycle").strip().lower()
    supported_tasks = ["factory_cycle", "strategy_review", "runtime_governance", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    strategy_id = str(params.get("strategy_id") or params.get("id") or "").strip()
    limit = max(1, min(_safe_int(params.get("limit"), 5), 100))
    runtime_alert_limit = max(1, min(_safe_int(params.get("runtime_alert_limit"), 20), 100))
    trigger_factory_run = bool(_parse_bool_flag(params.get("trigger_factory_run")))
    trigger_runtime_cycle = bool(_parse_bool_flag(params.get("trigger_runtime_cycle")))
    index_name = str(params.get("index_name") or "strategy_behavior").strip() or "strategy_behavior"

    steps: List[Dict[str, Any]] = []

    if task in {"factory_cycle", "smoke_test"}:
        status_resp = await runtime_strategy_manager(action="factory_status", params={})
        steps.append(_step_result("strategy_manager.factory_status", output=status_resp))
        capabilities_resp = await runtime_strategy_manager(action="capabilities", params={})
        steps.append(_step_result("strategy_manager.capabilities", output=capabilities_resp))
        if task != "smoke_test" and trigger_factory_run:
            run_resp = await runtime_strategy_manager(action="factory_run_once", params={})
            steps.append(_step_result("strategy_manager.factory_run_once", output=run_resp))
        runs_resp = await runtime_strategy_manager(action="factory_runs", params={"limit": limit})
        steps.append(_step_result("strategy_manager.factory_runs", output=runs_resp))
        if strategy_id:
            task_runs_resp = await runtime_strategy_manager(
                action="task_runs",
                params={"strategy_id": strategy_id, "limit": limit},
            )
            steps.append(_step_result("strategy_manager.task_runs", output=task_runs_resp))
        result = _finalize_skill_result(task, steps)
        result["summary"]["strategy_id"] = strategy_id or None
        result["summary"]["trigger_factory_run"] = trigger_factory_run if task != "smoke_test" else False
        return result

    if task == "strategy_review":
        rank_resp = await runtime_strategy_manager(action="rank", params={"status": "listed", "limit": limit})
        steps.append(_step_result("strategy_manager.rank", output=rank_resp))
        if strategy_id:
            detail_resp = await runtime_strategy_manager(action="detail", params={"strategy_id": strategy_id})
            steps.append(_step_result("strategy_manager.detail", output=detail_resp))
            review_report_resp = await runtime_strategy_manager(action="review_report", params={"strategy_id": strategy_id})
            steps.append(_step_result("strategy_manager.review_report", output=review_report_resp))
            events_resp = await runtime_strategy_manager(action="events", params={"strategy_id": strategy_id, "limit": limit})
            steps.append(_step_result("strategy_manager.events", output=events_resp))
        else:
            list_resp = await runtime_strategy_manager(action="list", params={"limit": limit})
            steps.append(_step_result("strategy_manager.list", output=list_resp))
        result = _finalize_skill_result(task, steps)
        result["summary"]["strategy_id"] = strategy_id or None
        return result

    capabilities_resp = await runtime_strategy_manager(action="capabilities", params={})
    steps.append(_step_result("strategy_manager.capabilities", output=capabilities_resp))
    runtime_cycle_status_resp = await runtime_strategy_manager(action="runtime_cycle_status", params={})
    steps.append(_step_result("strategy_manager.runtime_cycle_status", output=runtime_cycle_status_resp))
    vector_health_resp = await runtime_strategy_manager(
        action="vector_health",
        params={"index_name": index_name, "limit_versions": limit},
    )
    steps.append(_step_result("strategy_manager.vector_health", output=vector_health_resp))
    if trigger_runtime_cycle:
        runtime_cycle_run_resp = await runtime_strategy_manager(action="runtime_cycle_run", params={})
        steps.append(_step_result("strategy_manager.runtime_cycle_run", output=runtime_cycle_run_resp))
    if strategy_id:
        runtime_alerts_resp = await runtime_strategy_manager(
            action="runtime_alerts",
            params={"strategy_id": strategy_id, "limit": runtime_alert_limit},
        )
        steps.append(_step_result("strategy_manager.runtime_alerts", output=runtime_alerts_resp))
        runtime_control_resp = await runtime_strategy_manager(action="runtime_control", params={"strategy_id": strategy_id})
        steps.append(_step_result("strategy_manager.runtime_control", output=runtime_control_resp))
        promotion_reviews_resp = await runtime_strategy_manager(
            action="promotion_reviews",
            params={"strategy_id": strategy_id, "limit": limit},
        )
        steps.append(_step_result("strategy_manager.promotion_reviews", output=promotion_reviews_resp))
    else:
        vector_indexes_resp = await runtime_strategy_manager(
            action="vector_indexes",
            params={"index_name": index_name, "limit": limit},
        )
        steps.append(_step_result("strategy_manager.vector_indexes", output=vector_indexes_resp))

    result = _finalize_skill_result(task, steps)
    result["summary"]["strategy_id"] = strategy_id or None
    result["summary"]["index_name"] = index_name
    result["summary"]["trigger_runtime_cycle"] = trigger_runtime_cycle
    return result


async def _exec_fund_news(params: Dict[str, Any]) -> Dict[str, Any]:
    from .news import (
        get_analyst_ranking,
        get_market_news,
        get_stock_news,
        get_stock_notices,
        get_stock_research,
        search_research,
    )

    task = str(params.get("task") or "news_digest").strip().lower()
    supported_tasks = ["news_digest", "research_digest", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    code = normalize_code(str(params.get("code") or "600519"))
    keyword = str(params.get("keyword") or code).strip()
    start_date, end_date = _default_notice_window(params)
    news_limit = max(1, _safe_int(params.get("news_limit"), 5))
    research_limit = max(1, _safe_int(params.get("research_limit"), 5))
    market_news_limit = max(1, _safe_int(params.get("market_news_limit"), 5))

    async def _stock_news():
        return await asyncio.to_thread(get_stock_news, stock_code=code, limit=news_limit)

    async def _market_news():
        return await asyncio.to_thread(get_market_news, limit=market_news_limit)

    async def _stock_notices():
        return await asyncio.to_thread(get_stock_notices, start_date=start_date, end_date=end_date, stock_code=code)

    async def _stock_research():
        return await asyncio.to_thread(get_stock_research, stock_code=code, limit=research_limit)

    async def _search_research():
        return await asyncio.to_thread(search_research, keyword=keyword, stock_code=code, days=_safe_int(params.get("days"), 30))

    async def _analyst_ranking():
        return await asyncio.to_thread(get_analyst_ranking, year=str(params.get("year") or ""))

    steps: List[Dict[str, Any]] = []
    if task in {"news_digest", "smoke_test"}:
        steps.append(await _run_step_async("get_stock_news", _stock_news))
        steps.append(await _run_step_async("get_stock_notices", _stock_notices))
        steps.append(await _run_step_async("get_market_news", _market_news))
    else:
        steps.append(await _run_step_async("get_stock_research", _stock_research))
        steps.append(await _run_step_async("search_research", _search_research))
        steps.append(await _run_step_async("get_analyst_ranking", _analyst_ranking))

    result = _finalize_skill_result(task, steps)
    result["summary"]["code"] = code
    result["summary"]["window"] = {"start_date": start_date, "end_date": end_date}
    return result


async def _exec_fundamental(params: Dict[str, Any]) -> Dict[str, Any]:
    from .finance import get_financials, get_stock_info

    task = str(params.get("task") or "fundamental_snapshot").strip().lower()
    supported_tasks = ["fundamental_snapshot", "financials_only", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    code = normalize_code(str(params.get("code") or "600519"))
    steps: List[Dict[str, Any]] = []
    if task in {"fundamental_snapshot", "smoke_test"}:
        steps.append(_run_step("get_stock_info", get_stock_info, stock_code=code))
    steps.append(await _run_step_async("get_financials", get_financials, stock_code=code))

    result = _finalize_skill_result(task, steps)
    result["summary"]["code"] = code
    return result


def _exec_investor_protection(params: Dict[str, Any]) -> Dict[str, Any]:
    task = str(params.get("task") or "protection_brief").strip().lower()
    supported_tasks = ["protection_brief", "audit_log", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    region = str(params.get("region") or "CN").strip().upper()
    broker_region = str(params.get("broker_region") or region).strip().upper()
    protection_scope = {
        "region": region,
        "broker_region": broker_region,
        "protected_items": [
            "Custody/process failures under the applicable investor protection regime",
            "Disclosure and account-operation checks before acting on recommendations",
        ],
        "not_protected_items": [
            "Normal market loss and strategy drawdown",
            "Guarantees of profit or timing certainty",
        ],
    }
    audit_payload = {
        "user_intent": str(params.get("user_intent") or "investor_education"),
        "recommendation_context": dict(params.get("recommendation_context") or {}),
        "retention_rule": "Record recommendation rationale, risk boundary, and non-protected items together.",
    }
    steps = [
        _static_step("explain_protection_scope", protection_scope),
        _static_step(
            "explain_risk_boundary",
            {
                "core_message": "Investor protection does not replace diversification, risk budgeting, or suitability checks.",
                "next_actions": ["Verify broker/legal entity", "Review custody and claims process", "Confirm loss-bearing capacity"],
            },
        ),
    ]
    if task in {"audit_log", "smoke_test"}:
        steps.append(_static_step("prepare_recommendation_audit_payload", audit_payload))
    result = _finalize_skill_result(task, steps)
    result["summary"]["region"] = region
    return result


def _exec_ips_discipline(params: Dict[str, Any]) -> Dict[str, Any]:
    task = str(params.get("task") or "draft_ips").strip().lower()
    supported_tasks = ["draft_ips", "discipline_checklist", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    ips_draft = {
        "goal": str(params.get("goal") or "Grow capital within explicit drawdown limits"),
        "horizon_years": max(1.0, _safe_float(params.get("horizon_years"), 5.0)),
        "risk_profile": str(params.get("risk_profile") or "balanced").strip().lower(),
        "max_drawdown": max(0.05, min(_safe_float(params.get("max_drawdown"), 0.18), 0.50)),
        "liquidity_need": str(params.get("liquidity_need") or "medium"),
        "rebalance_frequency": str(params.get("rebalance_frequency") or "monthly"),
        "rebalance_threshold": _normalize_rebalance_threshold(params.get("rebalance_threshold"), 0.08),
        "behavior_rules": [
            "No ad-hoc position doubling after a loss",
            "Any exception to IPS must be documented with reason and expiry",
            "New strategies require a review window before capital increase",
        ],
    }
    steps = [
        _static_step("collect_ips_constraints", ips_draft),
        _static_step(
            "draft_behavior_discipline",
            {
                "discipline_checklist": [
                    "Target and constraint fields filled",
                    "Risk budget and rebalance trigger recorded",
                    "Temporary override rule documented",
                ]
            },
        ),
    ]
    result = _finalize_skill_result(task, steps)
    result["summary"]["ips_draft"] = ips_draft
    return result


async def _exec_macro_options_alerts(params: Dict[str, Any]) -> Dict[str, Any]:
    from .macro import get_macro_indicator
    from .options import get_option_chain

    task = str(params.get("task") or "macro_options_brief").strip().lower()
    supported_tasks = ["macro_options_brief", "alert_blueprint", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    indicator = str(params.get("indicator") or "cpi").strip().lower()
    limit = max(1, _safe_int(params.get("limit"), 12))
    underlying = str(params.get("underlying") or "510050").strip()
    expiry_month = str(params.get("expiry_month") or "").strip()
    threshold = _safe_float(params.get("threshold"), 0.0)
    steps: List[Dict[str, Any]] = []

    async def _macro():
        return await asyncio.to_thread(get_macro_indicator, indicator=indicator, limit=limit)

    async def _options():
        return await asyncio.to_thread(get_option_chain, underlying=underlying, expiry_month=expiry_month, limit=max(20, limit * 10))

    steps.append(await _run_step_async("get_macro_indicator", _macro))
    steps.append(await _run_step_async("get_option_chain", _options))
    steps.append(
        _static_step(
            "build_alert_blueprint",
            {
                "alert_name": str(params.get("alert_name") or f"{indicator}_{underlying}_monitor"),
                "threshold": threshold,
                "conditions": [
                    f"{indicator} change crosses {threshold}" if threshold else f"{indicator} surprises relative to prior print",
                    "Option open interest or implied skew changes materially",
                    "Escalate when macro direction and option positioning diverge",
                ],
            },
        )
    )
    result = _finalize_skill_result(task, steps)
    result["summary"]["indicator"] = indicator
    result["summary"]["underlying"] = underlying
    return result


def _exec_performance_attribution(params: Dict[str, Any]) -> Dict[str, Any]:
    task = str(params.get("task") or "attribution_report").strip().lower()
    supported_tasks = ["attribution_report", "benchmark_frame", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    holdings = _normalize_holdings_input(params, default_codes=["600519", "000001", "510300"])
    portfolio_return = _safe_float(params.get("portfolio_return"), 0.08)
    benchmark_return = _safe_float(params.get("benchmark_return"), 0.05)
    contributions = []
    for item in holdings:
        security_return = _safe_float(item.get("return_pct"), portfolio_return)
        contributions.append(
            {
                "code": item["code"],
                "weight": item["weight"],
                "return_pct": security_return,
                "contribution_pct": round(item["weight"] * security_return, 4),
            }
        )
    contributions.sort(key=lambda item: item["contribution_pct"], reverse=True)
    steps = [
        _static_step("collect_holdings_and_returns", {"holdings": holdings, "portfolio_return": portfolio_return}),
        _static_step("compute_contribution_split", {"contributions": contributions}),
        _static_step(
            "compare_vs_benchmark",
            {
                "benchmark_return": benchmark_return,
                "active_return": round(portfolio_return - benchmark_return, 4),
                "risk_sources": list(params.get("risk_sources") or ["allocation", "security_selection", "timing"]),
            },
        ),
    ]
    result = _finalize_skill_result(task, steps)
    result["summary"]["top_contributor"] = contributions[0] if contributions else None
    result["summary"]["active_return"] = round(portfolio_return - benchmark_return, 4)
    return result


async def _exec_portfolio(params: Dict[str, Any]) -> Dict[str, Any]:
    from .backtest import run_batch_backtest, run_simple_backtest

    task = str(params.get("task") or "allocation_snapshot").strip().lower()
    supported_tasks = ["portfolio_backtest", "batch_backtest", "allocation_snapshot", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    if task == "portfolio_backtest":
        code = normalize_code(str(params.get("code") or "600519"))
        steps = [
            await _run_step_async(
                "run_simple_backtest",
                run_simple_backtest,
                code=code,
                strategy=str(params.get("strategy") or "ma_cross"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                initial_capital=_safe_float(params.get("initial_capital"), 100_000.0),
                commission=_safe_float(params.get("commission"), 0.0003),
                short_period=_safe_int(params.get("short_period"), 5),
                long_period=_safe_int(params.get("long_period"), 20),
                benchmark=str(params.get("benchmark") or "000300"),
                slippage=_safe_float(params.get("slippage"), 0.0),
            )
        ]
        return _finalize_skill_result(task, steps)

    if task == "batch_backtest":
        codes = _normalize_codes_input(params.get("codes"), ["600519", "000001", "000858"])
        steps = [
            await _run_step_async(
                "run_batch_backtest",
                run_batch_backtest,
                codes=codes,
                strategy=str(params.get("strategy") or "ma_cross"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                initial_capital=_safe_float(params.get("initial_capital"), 100_000.0),
                commission=_safe_float(params.get("commission"), 0.0003),
                short_period=_safe_int(params.get("short_period"), 5),
                long_period=_safe_int(params.get("long_period"), 20),
                use_parallel=bool(params.get("use_parallel", True)),
                fetch_concurrency=_safe_int(params.get("fetch_concurrency"), 8),
            )
        ]
        return _finalize_skill_result(task, steps)

    holdings = _normalize_holdings_input(params, default_codes=["600519", "000001", "510300"])
    steps = [
        _static_step(
            "build_allocation_snapshot",
            {
                "method": str(params.get("method") or "equal_weight"),
                "holdings": holdings,
                "estimated_capital": round(sum(float(item.get("value") or 0.0) for item in holdings), 2),
            },
        ),
        _static_step(
            "outline_risk_checks",
            {
                "checks": [
                    "Validate concentration and sector exposure",
                    "Run historical drawdown and stress scenarios",
                    "Persist the approved snapshot with assumptions",
                ]
            },
        ),
    ]
    return _finalize_skill_result(task, steps)


def _exec_portfolio_manager_core(params: Dict[str, Any]) -> Dict[str, Any]:
    task = str(params.get("task") or "closed_loop_plan").strip().lower()
    supported_tasks = ["closed_loop_plan", "execution_gate", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    codes = _normalize_codes_input(params.get("codes"), ["600519", "000001", "510300"])
    max_position_pct = max(0.05, min(_safe_float(params.get("max_position_pct"), 0.30), 0.60))
    max_drawdown = max(0.05, min(_safe_float(params.get("max_drawdown"), 0.18), 0.50))
    stages = [
        {"stage": "profile", "gate": "risk_profile_resolved", "passed": bool(params.get("risk_profile") or True)},
        {"stage": "research", "gate": "candidate_codes_ready", "passed": bool(codes)},
        {"stage": "portfolio", "gate": "position_limit_set", "passed": max_position_pct <= 0.50},
        {"stage": "risk", "gate": "drawdown_guardrail_set", "passed": max_drawdown <= 0.35},
        {"stage": "execution", "gate": "execution_plan_documented", "passed": True},
        {"stage": "review", "gate": "post_trade_review_rule_defined", "passed": True},
    ]
    steps = [
        _static_step(
            "define_closed_loop_goal",
            {
                "goal": str(params.get("goal") or "Maintain a repeatable portfolio decision loop"),
                "risk_profile": str(params.get("risk_profile") or "balanced"),
                "codes": codes,
            },
        ),
        _static_step("evaluate_stage_gates", {"stages": stages}),
    ]
    result = _finalize_skill_result(task, steps)
    result["summary"]["closed_loop_gate"] = all(stage["passed"] for stage in stages)
    return result


def _exec_quant(params: Dict[str, Any]) -> Dict[str, Any]:
    from .quant import _factor_library_payload

    task = str(params.get("task") or "factor_inventory").strip().lower()
    supported_tasks = ["factor_inventory", "signal_research", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    factor_payload = _factor_library_payload(str(params.get("category") or "all"))
    selected_factor = str(params.get("factor") or "momentum").strip().lower()
    code = normalize_code(str(params.get("code") or "600519"))
    steps = [
        _static_step(
            "load_factor_library",
            {
                "factor_count": factor_payload.get("count"),
                "categories": factor_payload.get("categories"),
                "sample_factors": [item.get("name") for item in (factor_payload.get("factors") or [])[:5]],
            },
        )
    ]
    if task in {"signal_research", "smoke_test"}:
        steps.append(
            _static_step(
                "define_signal_research_card",
                {
                    "code": code,
                    "factor": selected_factor,
                    "window_days": max(10, _safe_int(params.get("window_days"), 60)),
                    "research_checks": [
                        "Verify data sufficiency and tradability",
                        "Measure factor direction and stability",
                        "Compare against alternative signal families",
                    ],
                },
            )
        )
    result = _finalize_skill_result(task, steps)
    result["summary"]["factor_count"] = factor_payload.get("count")
    return result


async def _exec_quant_data_engineering(params: Dict[str, Any]) -> Dict[str, Any]:
    from .market.kline import get_kline_data
    from .market.quote import get_realtime_quote

    task = str(params.get("task") or "quality_check").strip().lower()
    supported_tasks = ["quality_check", "warmup_blueprint", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    code = normalize_code(str(params.get("code") or "600519"))
    start_date, end_date = _default_notice_window(params)
    limit = max(20, _safe_int(params.get("limit"), 120))
    steps: List[Dict[str, Any]] = []
    if task in {"quality_check", "smoke_test"}:
        steps.append(_run_step("get_realtime_quote", get_realtime_quote, stock_code=code))
        steps.append(
            await _run_step_async(
                "get_kline_data",
                get_kline_data,
                code=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                adjust=str(params.get("adjust") or "qfq"),
            )
        )
    steps.append(
        _static_step(
            "define_warmup_blueprint",
            {
                "code": code,
                "window": {"start_date": start_date, "end_date": end_date},
                "fallback_chain": ["data_warmup", "sync_kline_data", "batch_sync_klines", "data_sync_manager(action=sync)"],
                "quality_contract": ["missing_values", "duplicate_rows", "price_jump_outliers", "cache_staleness"],
            },
        )
    )
    return _finalize_skill_result(task, steps)


def _exec_quant_methods_foundation(params: Dict[str, Any]) -> Dict[str, Any]:
    task = str(params.get("task") or "risk_metrics").strip().lower()
    supported_tasks = ["risk_metrics", "correlation_frame", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    raw_series = params.get("series") or {
        "alpha": [0.01, -0.004, 0.006, 0.008, -0.002, 0.004],
        "beta": [0.008, -0.003, 0.004, 0.007, -0.001, 0.003],
    }
    series_map = {
        str(name): np.asarray(values or [], dtype=float)
        for name, values in dict(raw_series).items()
        if isinstance(values, list) and values
    }
    annualization_factor = max(1.0, _safe_float(params.get("annualization_factor"), 252.0))
    if not series_map:
        return _unsupported_task_result(task, supported_tasks)

    metrics = {
        name: {
            "mean": round(float(np.mean(values)), 6),
            "volatility": round(float(np.std(values)), 6),
            "annualized_volatility": round(float(np.std(values) * np.sqrt(annualization_factor)), 6),
            "max_drawdown_proxy": round(float(np.min(np.cumsum(values))), 6),
        }
        for name, values in series_map.items()
    }
    ordered_names = list(series_map.keys())
    matrix = np.vstack([series_map[name] for name in ordered_names])
    covariance = np.cov(matrix).round(6).tolist() if len(ordered_names) > 1 else [[float(np.var(matrix[0]))]]
    correlation = np.corrcoef(matrix).round(6).tolist() if len(ordered_names) > 1 else [[1.0]]
    steps = [
        _static_step("compute_risk_metrics", {"metrics": metrics}),
        _static_step(
            "compute_dependency_matrix",
            {"names": ordered_names, "covariance": covariance, "correlation": correlation},
        ),
    ]
    result = _finalize_skill_result(task, steps)
    result["summary"]["series_count"] = len(series_map)
    return result


def _exec_quant_ml_signals(params: Dict[str, Any]) -> Dict[str, Any]:
    task = str(params.get("task") or "signal_guardrails").strip().lower()
    supported_tasks = ["signal_guardrails", "research_card", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    guardrails = {
        "code": normalize_code(str(params.get("code") or "600519")),
        "factor": str(params.get("factor") or "momentum").strip().lower(),
        "train_window": max(60, _safe_int(params.get("train_window"), 252)),
        "test_window": max(20, _safe_int(params.get("test_window"), 63)),
        "requirements": [
            "Separate in-sample and out-of-sample windows",
            "Track feature drift and prediction drift",
            "Keep a plain-language explanation for every promoted signal",
            "Backtest after cost assumptions, not before",
        ],
    }
    steps = [
        _static_step("define_ml_signal_guardrails", guardrails),
        _static_step(
            "build_research_card",
            {
                "validation_stack": ["factor_ic", "group_backtest", "oos_validation", "stress_test"],
                "failure_conditions": ["feature_instability", "oos_decay", "excess_turnover"],
            },
        ),
    ]
    result = _finalize_skill_result(task, steps)
    result["summary"]["research_ready"] = True
    return result


async def _exec_quant_research_process(params: Dict[str, Any]) -> Dict[str, Any]:
    from .backtest import run_simple_backtest

    task = str(params.get("task") or "stage_gate").strip().lower()
    supported_tasks = ["stage_gate", "backtest_gate", "smoke_test"]
    if task not in supported_tasks:
        return _unsupported_task_result(task, supported_tasks)

    code = normalize_code(str(params.get("code") or "600519"))
    factor = str(params.get("factor") or "momentum").strip().lower()
    hypothesis = str(params.get("hypothesis") or f"{factor} signal should improve risk-adjusted return").strip()
    stage_report = [
        {"stage": "definition", "passed": True, "note": hypothesis},
        {"stage": "data_gate", "passed": True, "note": "Use normalized kline inputs and explicit cost assumptions"},
        {"stage": "signal_gate", "passed": True, "note": f"Selected factor family: {factor}"},
        {"stage": "portfolio_gate", "passed": True, "note": "Position limits and risk budget must be written down"},
        {"stage": "review_gate", "passed": True, "note": "Persist results and limitations"},
    ]
    steps: List[Dict[str, Any]] = [_static_step("build_stage_gate_report", {"stages": stage_report})]
    if task in {"backtest_gate", "smoke_test"}:
        steps.append(
            await _run_step_async(
                "run_simple_backtest",
                run_simple_backtest,
                code=code,
                strategy=str(params.get("strategy") or "ma_cross"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                initial_capital=_safe_float(params.get("initial_capital"), 100_000.0),
                commission=_safe_float(params.get("commission"), 0.0003),
                short_period=_safe_int(params.get("short_period"), 5),
                long_period=_safe_int(params.get("long_period"), 20),
                benchmark=str(params.get("benchmark") or "000300"),
                slippage=_safe_float(params.get("slippage"), 0.0),
            )
        )
    result = _finalize_skill_result(task, steps)
    result["summary"]["all_stage_passed"] = all(stage["passed"] for stage in stage_report)
    return result


_SKILL_EXECUTORS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "akshare-asset-allocation": _exec_asset_allocation,
    "akshare-fee-costs": _exec_fee_costs,
    "akshare-factor-mining": _exec_factor_mining,
    "akshare-fund-news": _exec_fund_news,
    "akshare-fundamental": _exec_fundamental,
    "akshare-investor-protection": _exec_investor_protection,
    "akshare-ips-discipline": _exec_ips_discipline,
    "akshare-macro-options-alerts": _exec_macro_options_alerts,
    "akshare-market": _exec_market,
    "akshare-performance-attribution": _exec_performance_attribution,
    "akshare-portfolio": _exec_portfolio,
    "akshare-portfolio-manager-core": _exec_portfolio_manager_core,
    "akshare-quant": _exec_quant,
    "akshare-quant-data-engineering": _exec_quant_data_engineering,
    "akshare-quant-methods-foundation": _exec_quant_methods_foundation,
    "akshare-quant-ml-signals": _exec_quant_ml_signals,
    "akshare-quant-research-process": _exec_quant_research_process,
    "akshare-strategy-factory": _exec_strategy_factory,
    "akshare-fund-manager-pro": _exec_fund_manager_pro,
}


def register(mcp):
    @mcp.tool()
    def list_skills():
        """列出当前可发现的内置技能及其执行状态。

        Returns:
            dict: 标准技能响应，包含技能列表、数量、来源和注册表摘要。
        """
        started_at = datetime.now()
        skills = _enrich_skills(_load_skills())
        source = _skills_source(skills)
        registry_summary = _build_skill_registry_summary(skills)
        return _skill_ok(
            {"skills": skills, "count": len(skills), "source": source, "registry_summary": registry_summary},
            backend_requested="skills_registry",
            backend_used=source,
            fallback_used=source != "skills_registry",
            fallback_reason=None if source == "skills_registry" else "skills_registry_unavailable",
            started_at=started_at,
        )

    @mcp.tool()
    def search_skills(keyword: str):
        """按关键字检索技能元数据。

        Args:
            keyword: 技能 ID、名称、分类或描述关键字；为空时返回全部技能。

        Returns:
            dict: 标准技能响应，包含匹配技能和注册表摘要。
        """
        started_at = datetime.now()
        skills = _enrich_skills(_load_skills())
        source = _skills_source(skills)
        registry_summary = _build_skill_registry_summary(skills)
        keyword_lower = (keyword or "").strip().lower()
        if not keyword_lower:
            return _skill_ok(
                {"skills": skills, "keyword": keyword, "count": len(skills), "source": source, "registry_summary": registry_summary},
                backend_requested="skills_registry",
                backend_used=source,
                fallback_used=source != "skills_registry",
                fallback_reason=None if source == "skills_registry" else "skills_registry_unavailable",
                started_at=started_at,
            )

        matched = [
            skill
            for skill in skills
            if keyword_lower in skill.get("id", "").lower()
            or keyword_lower in skill.get("name", "").lower()
            or keyword_lower in skill.get("category", "").lower()
            or keyword_lower in skill.get("description", "").lower()
        ]
        return _skill_ok(
            {"skills": matched, "keyword": keyword, "count": len(matched), "source": source, "registry_summary": registry_summary},
            backend_requested="skills_registry",
            backend_used=source,
            fallback_used=source != "skills_registry",
            fallback_reason=None if source == "skills_registry" else "skills_registry_unavailable",
            started_at=started_at,
        )

    @mcp.tool()
    async def run_skill(skill_id: str, params: dict = None):
        """执行指定技能的编排处理器。

        Args:
            skill_id: 技能唯一标识。
            params: 传递给技能执行器的参数字典，缺省时会被标准化为空字典。

        Returns:
            dict: 标准技能成功/失败响应，包含执行结果、错误码和回退元信息。
        """
        started_at = datetime.now()
        normalized_params = _normalize_params(params)
        skills = _enrich_skills(_load_skills())
        source = _skills_source(skills)
        skill = next((s for s in skills if s.get("id") == skill_id), None)
        if not skill:
            return _skill_fail(
                f"Skill {skill_id} not found",
                backend_requested="skills_registry",
                backend_used="none",
                fallback_used=True,
                fallback_reason="skill_not_found",
                started_at=started_at,
                error_code="SKILL_NOT_FOUND",
                detail={"skill_id": skill_id},
            )

        available_handlers = _available_skill_handlers()
        executor = available_handlers.get(skill_id)
        if skill.get("status") == "deprecated":
            fallback_reasons = []
            if source != "codex_registry":
                fallback_reasons.append("skills_registry_unavailable")
            fallback_reasons.append("skill_deprecated")
            return _skill_fail(
                f"Skill {skill_id} is deprecated and cannot be executed",
                backend_requested="skill_executor",
                backend_used="registry_only",
                fallback_used=True,
                fallback_reason=fallback_reasons,
                started_at=started_at,
                error_code="SKILL_DEPRECATED",
                detail={"skill": skill},
            )

        if executor is None or not skill.get("executable"):
            fallback_reasons = []
            if source != "codex_registry":
                fallback_reasons.append("skills_registry_unavailable")
            fallback_reasons.append("handler_not_implemented")
            return _skill_fail(
                f"Skill {skill_id} is registered but not executable",
                backend_requested="skill_executor",
                backend_used="registry_only",
                fallback_used=True,
                fallback_reason=fallback_reasons,
                started_at=started_at,
                error_code="SKILL_NOT_EXECUTABLE",
                detail={
                    "skill": skill,
                    "available_handlers": sorted(available_handlers.keys()),
                },
            )

        try:
            import inspect
            if inspect.iscoroutinefunction(executor):
                execution = await executor(normalized_params)
            else:
                execution = executor(normalized_params)
        except Exception as e:
            fallback_reasons = [f"executor_exception:{type(e).__name__}"]
            if source != "codex_registry":
                fallback_reasons.insert(0, "skills_registry_unavailable")
            return _skill_fail(
                f"Skill {skill_id} execution failed: {type(e).__name__}: {e}",
                backend_requested="skill_executor",
                backend_used="none",
                fallback_used=True,
                fallback_reason=fallback_reasons,
                started_at=started_at,
                error_code="SKILL_EXECUTION_FAILED",
                detail={"skill": skill},
            )

        return _skill_ok(
            {
                "skill": skill,
                "execution": execution,
                "skill_id": skill_id,
                "skill_name": skill.get("name", ""),
                "params": normalized_params,
                "skill_path": skill.get("path", ""),
                "execution_mode": skill.get("execution_mode", "orchestrated"),
                "result": execution,
                "message": "Skill executed via built-in orchestrator",
                "source": source,
            },
            backend_requested="skill_executor",
            backend_used="built_in_orchestrator",
            fallback_used=source != "codex_registry",
            fallback_reason=None if source == "codex_registry" else ["skills_registry_unavailable"],
            started_at=started_at,
        )
