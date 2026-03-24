"""Quant manager: factor analysis and workflow orchestration.

Two distinct IC analysis paths coexist — do NOT confuse them:

1. **Classic factor IC** (``factor_ic`` / ``batch_compute_factors``):
   Operates on SUPPORTED_FACTORS (predefined names like momentum, value, quality).
   ``run_factor_ic_analysis`` computes dual IC (Pearson + Rank IC) with bootstrap CI
   on a single stock's time-series.  ``batch_compute_factors`` computes cross-sectional
   IC / Rank IC across the universe and persists results.

2. **LLM candidate validation** (``validate_factor_candidate``):
   Operates on DSL-compiled candidate expressions produced by ``llm_factor_mining``.
   ``validate_factor_candidate_pipeline`` returns OOS validation, robustness, turnover,
   cost-capacity, and a composite rating.

The two paths differ in input granularity (pre-defined name vs DSL expression),
universe scope, and output schema.  Consumers must pick the right path.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import numpy as np
import pandas as pd

from ...services import (
    get_artifact_async,
    get_factor_llm_provider,
    get_factor_research_memory_service,
    list_artifacts_async,
    register_artifact,
    register_artifact_async,
    validate_factor_candidate_pipeline,
    validate_factor_generation_payload,
)
from ...services.factor_candidate_compiler import compile_factor_candidate
from ...services.factor_prompt_builder import build_factor_mining_prompt
from ...services.llm_alpha import LLMAlphaMiner
from ...data_source import data_source
from ...storage import get_db
from ...utils import fail, ok
from ..quant import (
    SUPPORTED_FACTORS,
    run_factor_group_backtest,
    run_factor_ic_analysis,
    run_factor_oos_validation,
)

# Re-exported helpers from sub-modules
from .quant_mgr_helpers import (
    NEGATIVE_SENTIMENT_TOKENS,
    POSITIVE_SENTIMENT_TOKENS,
    _as_code_list,
    _clip,
    _compute_scalar_factor_bundle,
    _compute_alternative_factors_for_code,
    _extract_news_items,
    _filter_quant_artifacts,
    _headline_sentiment_score,
    _load_valuation_snapshot,
    _parse_date_value,
    _rank_transform,
    _safe_float,
    _select_financial_snapshot,
    _sort_klines_ascending,
)
from .quant_mgr_automl import (
    _build_automl_dataset,
    _build_automl_features,
    _fit_automl_model,
    _select_anchor_factor,
)
from .data_sync_manager import run_runtime_data_warmup

logger = logging.getLogger(__name__)
_QUANT_MANAGER_IMPL = None
_MARKET_CODE_PATTERN = re.compile(r"^\d{6}$")


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_bool(name: str, default: bool) -> bool:
    return _coerce_bool(os.getenv(name), default)


def _filter_market_codes(values) -> list[str]:
    items = []
    seen: set[str] = set()
    for code in _as_code_list(values):
        token = str(code or "").strip().split(".", 1)[0].strip()
        if not token or token in seen or not _MARKET_CODE_PATTERN.fullmatch(token):
            continue
        seen.add(token)
        items.append(token)
    return items


def register_quant_manager(mcp):
    """Register quant manager tool."""

    @mcp.tool()
    async def quant_manager(
        action: str,
        code: Optional[str] = None,
        kwargs: Any = None,
        params: Any = None,
    ):
        """Quant manager with unified action + kwargs protocol."""
        try:
            start_time = time.perf_counter()
            trace_id = f"quant_manager:{action}:{int(time.time() * 1000)}"
            tool_version = "v1.2"
            db = get_db()

            tool_kwargs = {}
            if kwargs is not None:
                tool_kwargs["kwargs"] = kwargs
            if params is not None:
                tool_kwargs["params"] = params

            if isinstance(tool_kwargs.get("params"), dict):
                tool_kwargs = {**tool_kwargs, **tool_kwargs.get("params")}

            if tool_kwargs.get("kwargs") and isinstance(tool_kwargs.get("kwargs"), str):
                try:
                    extra = json.loads(tool_kwargs.get("kwargs") or "{}")
                    if isinstance(extra, dict):
                        tool_kwargs = {**tool_kwargs, **extra}
                except Exception:
                    pass

            if isinstance(tool_kwargs.get("kwargs"), dict):
                tool_kwargs = {**tool_kwargs, **tool_kwargs.get("kwargs")}

            _kw = tool_kwargs

            as_of = _kw.get("as_of", "")
            adjust = _kw.get("adjust", "")
            price_source_policy = _kw.get("price_source_policy", "auto")
            explain = _kw.get("explain", True)
            strict_mode = _kw.get("strict_mode", False)
            code = code or _kw.get("code") or _kw.get("Code") or _kw.get("stock_code") or _kw.get("symbol")

            def _with_meta(resp: dict, source_chain=None, data_timestamp: Optional[str] = None):
                if not isinstance(resp, dict):
                    return resp
                resp["meta"] = {
                    "trace_id": trace_id,
                    "tool_version": tool_version,
                    "data_timestamp": data_timestamp or datetime.now().strftime("%Y-%m-%d"),
                    "source_chain": source_chain or ["quant_manager"],
                    "cached": False,
                    "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                    "as_of": as_of,
                    "adjust": adjust,
                    "price_source_policy": price_source_policy,
                    "explain": explain,
                    "strict_mode": strict_mode,
                }
                return resp

            def _ok(data: dict, source_chain=None, data_timestamp: Optional[str] = None):
                return _with_meta(ok(data), source_chain, data_timestamp)

            def _fail(message: str, source_chain=None, data_timestamp: Optional[str] = None):
                return _with_meta(fail(message), source_chain, data_timestamp)

            async def _load_market_frame(one_code: str, bars: int = 180):
                fallback_reason = None
                source = "db.get_klines"
                klines = []
                try:
                    klines = await db.get_klines(one_code, limit=max(120, int(bars)))
                except Exception as exc:
                    fallback_reason = f"db.get_klines failed: {exc}"
                    klines = []
                if not klines:
                    ds_rows = data_source.get_kline(one_code, period="daily", limit=max(120, int(bars)))
                    if ds_rows:
                        source = "data_source.get_kline"
                        klines = [
                            {
                                "date": row.get("date"),
                                "open": row.get("open"),
                                "high": row.get("high"),
                                "low": row.get("low"),
                                "close": row.get("close"),
                                "volume": row.get("volume"),
                                "amount": row.get("amount", 0),
                            }
                            for row in ds_rows
                        ]
                if not klines:
                    return None, source, fallback_reason or "no kline data"
                ordered = _sort_klines_ascending(klines)
                frame = pd.DataFrame(ordered)
                return frame, source, fallback_reason

            async def _build_local_fallback_candidates(target_codes: list[str], candidate_count: int):
                miner = LLMAlphaMiner()
                fallback_rows = []
                fallback_source_chain: list[str] = []
                fallback_reasons: list[str] = []
                scoped_codes = list(target_codes or [])[:5]
                per_code = max(1, int(np.ceil(max(1, int(candidate_count)) / max(1, len(scoped_codes)))))
                fallback_dsl_templates = {
                    "momentum": ("zscore(momentum_20d, 20) + zscore(momentum_60d, 20)", ["momentum_20d", "momentum_60d"]),
                    "trend": ("ts_mean(return_5d, 10) + zscore(momentum_20d, 20)", ["return_5d", "momentum_20d"]),
                    "reversal": ("-return_5d", ["return_5d"]),
                    "volatility": ("-zscore(volatility_20d, 20)", ["volatility_20d"]),
                    "liquidity": ("zscore(volume_ratio_5_20, 10)", ["volume_ratio_5_20"]),
                    "risk_adjusted": ("zscore(momentum_20d, 20) - zscore(volatility_20d, 20)", ["momentum_20d", "volatility_20d"]),
                    "divergence": ("zscore(momentum_20d, 10) - zscore(momentum_60d, 20)", ["momentum_20d", "momentum_60d"]),
                    "custom": ("zscore(momentum_20d, 20) + zscore(volume_ratio_5_20, 10) - zscore(volatility_20d, 20)", ["momentum_20d", "volume_ratio_5_20", "volatility_20d"]),
                }

                for one_code in scoped_codes:
                    frame, one_source, reason = await _load_market_frame(one_code, bars=180)
                    if reason:
                        fallback_reasons.append(f"{one_code}: {reason}")
                    if frame is None or frame.empty:
                        continue
                    fallback_source_chain.append(one_source)
                    try:
                        raw_candidates = miner.generate_factor_candidates(
                            frame,
                            news_data=None,
                            num_candidates=min(8, per_code),
                        )
                    except Exception as exc:
                        fallback_reasons.append(f"{one_code}: local fallback generation failed: {exc}")
                        continue

                    for item in raw_candidates:
                        raw_formula = str(item.get("formula") or "").strip() or "close"
                        category = str(item.get("category") or "custom").strip().lower() or "custom"
                        expression_dsl = raw_formula
                        inputs = ["close"]
                        candidate_probe = {
                            "name": str(item.get("name") or f"{one_code}_fallback_factor"),
                            "hypothesis": "Local rule fallback candidate",
                            "family": category,
                            "inputs": ["close"],
                            "expression_dsl": expression_dsl,
                            "expected_holding_period": 10,
                            "expected_regime": [],
                            "complexity_hint": "medium",
                            "novelty_rationale": "Generated from local fallback seed pool",
                        }
                        try:
                            compiled_probe = compile_factor_candidate(candidate_probe)
                        except Exception:
                            compiled_probe = {"valid": False}
                        if compiled_probe.get("valid"):
                            inputs = list(compiled_probe.get("referenced_fields") or ["close"])
                        else:
                            expression_dsl, inputs = fallback_dsl_templates.get(category, fallback_dsl_templates["custom"])

                        fallback_rows.append(
                            {
                                "name": str(item.get("name") or f"{one_code}_fallback_factor"),
                                "hypothesis": str(item.get("description") or item.get("rationale") or "Local rule fallback candidate").strip(),
                                "family": category,
                                "inputs": inputs,
                                "expression_dsl": expression_dsl,
                                "expected_holding_period": 10,
                                "expected_regime": [],
                                "complexity_hint": "medium",
                                "novelty_rationale": str(item.get("rationale") or "Generated from local fallback seed pool").strip(),
                                "generation_trace": {
                                    "mode": "local_rule_fallback",
                                    "engine": str(item.get("engine") or item.get("category") or "local_rule_v1"),
                                    "code": one_code,
                                },
                                "source_model": "local_rule_fallback",
                            }
                        )
                        if len(fallback_rows) >= max(1, int(candidate_count)):
                            break
                    if len(fallback_rows) >= max(1, int(candidate_count)):
                        break

                if not fallback_rows:
                    raise RuntimeError("local fallback produced no candidates")

                validated = validate_factor_generation_payload(
                    {
                        "candidates": fallback_rows[: max(1, int(candidate_count))],
                        "warnings": ["local_rule_fallback"] + fallback_reasons[:10],
                        "analysis": {
                            "mode": "local_rule_fallback",
                            "codes": scoped_codes,
                        },
                    },
                    model="local_rule_fallback",
                    provider="local_rule",
                )
                return validated, fallback_source_chain or ["services.llm_alpha"], fallback_reasons

            async def _resolve_candidate_for_validation():
                raw_candidate = _kw.get("candidate")
                if isinstance(raw_candidate, str) and raw_candidate.strip():
                    try:
                        raw_candidate = json.loads(raw_candidate)
                    except Exception:
                        raise ValueError("candidate 必须是 dict 或可解析的 JSON 字符串")
                if isinstance(raw_candidate, dict):
                    return {
                        "candidate": raw_candidate,
                        "resolved_from": "inline_candidate",
                        "artifact_id": None,
                        "candidate_index": None,
                        "artifact_payload": None,
                    }

                artifact_id = str(_kw.get("artifact_id") or "").strip()
                if not artifact_id:
                    raise ValueError("需要提供 candidate 或 artifact_id")

                artifact = await get_artifact_async(artifact_id)
                if not artifact:
                    raise ValueError(f"artifact not found: {artifact_id}")

                artifact_payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else artifact
                candidates = list((artifact_payload or {}).get("candidates") or [])
                if not candidates:
                    raise ValueError(f"artifact {artifact_id} does not contain candidates")

                try:
                    candidate_index = int(_kw.get("candidate_index", 0) or 0)
                except Exception:
                    raise ValueError("candidate_index 必须是整数")
                if candidate_index < 0 or candidate_index >= len(candidates):
                    raise ValueError(f"candidate_index 越界: {candidate_index}, 可选范围 0..{len(candidates) - 1}")

                return {
                    "candidate": dict(candidates[candidate_index] or {}),
                    "resolved_from": "artifact_candidate",
                    "artifact_id": artifact_id,
                    "candidate_index": candidate_index,
                    "artifact_payload": artifact_payload,
                }

            def _payload_from_artifact_row(artifact: dict | None) -> dict:
                if not isinstance(artifact, dict):
                    return {}
                payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else artifact
                return payload if isinstance(payload, dict) else {}

            def _screen_compiler_candidates(candidates: list[dict] | None) -> dict:
                kept_candidates = []
                rejected_candidates = []
                for idx, raw_candidate in enumerate(list(candidates or [])):
                    candidate = dict(raw_candidate or {})
                    candidate_name = str(candidate.get("name") or f"candidate_{idx}").strip() or f"candidate_{idx}"
                    try:
                        compiled = compile_factor_candidate(candidate)
                    except Exception as exc:
                        rejected_candidates.append(
                            {
                                "name": candidate_name,
                                "reason": f"compile_exception:{exc}",
                                "unsupported_fields": [],
                                "unsupported_functions": [],
                            }
                        )
                        continue

                    if not compiled.get("valid"):
                        rejected_candidates.append(
                            {
                                "name": candidate_name,
                                "reason": "compiler_invalid",
                                "unsupported_fields": list(compiled.get("unsupported_fields") or []),
                                "unsupported_functions": list(compiled.get("unsupported_functions") or []),
                                "complexity_score": _safe_float(((compiled.get("complexity") or {}).get("score")), 0.0),
                            }
                        )
                        continue

                    kept_candidates.append(candidate)

                warnings = []
                if rejected_candidates:
                    sample = []
                    for item in rejected_candidates[:5]:
                        parts = [str(item.get("name") or "candidate")]
                        if item.get("unsupported_fields"):
                            parts.append(f"fields={item.get('unsupported_fields')}")
                        if item.get("unsupported_functions"):
                            parts.append(f"functions={item.get('unsupported_functions')}")
                        if item.get("reason") and not item.get("unsupported_fields") and not item.get("unsupported_functions"):
                            parts.append(str(item.get("reason")))
                        sample.append("|".join(parts))
                    warnings.append(
                        "compiler_screen_rejected="
                        f"{len(rejected_candidates)}/{len(list(candidates or []))}: " + "; ".join(sample)
                    )

                return {
                    "kept_candidates": kept_candidates,
                    "rejected_candidates": rejected_candidates,
                    "summary": {
                        "input_count": len(list(candidates or [])),
                        "kept_count": len(kept_candidates),
                        "rejected_count": len(rejected_candidates),
                    },
                    "warnings": warnings,
                }

            def _normalize_registry_item(artifact: dict, payload: dict) -> dict:
                candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
                rating = payload.get("rating") if isinstance(payload.get("rating"), dict) else {}
                metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
                candidate_resolution = payload.get("candidate_resolution") if isinstance(payload.get("candidate_resolution"), dict) else {}
                memory_record = payload.get("memory_record") if isinstance(payload.get("memory_record"), dict) else {}
                validation_report = (
                    payload.get("factor_validation_report") if isinstance(payload.get("factor_validation_report"), dict) else {}
                )
                lookahead_audit = payload.get("lookahead_audit") if isinstance(payload.get("lookahead_audit"), dict) else {}
                if not lookahead_audit:
                    nested_lookahead = validation_report.get("lookahead_audit")
                    lookahead_audit = nested_lookahead if isinstance(nested_lookahead, dict) else {}
                multiple_testing = payload.get("multiple_testing") if isinstance(payload.get("multiple_testing"), dict) else {}
                if not multiple_testing:
                    nested_multiple = validation_report.get("multiple_testing")
                    multiple_testing = nested_multiple if isinstance(nested_multiple, dict) else {}

                lookahead_risk = (
                    str(lookahead_audit.get("risk_level") or "unknown").strip().lower()
                    if lookahead_audit
                    else "unknown"
                )
                multiple_testing_risk = (
                    str(multiple_testing.get("risk_level") or "unknown").strip().lower()
                    if multiple_testing
                    else "unknown"
                )
                risk_rank = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
                overall_risk = "unknown"
                max_risk_rank = max(risk_rank.get(lookahead_risk, 0), risk_rank.get(multiple_testing_risk, 0))
                for name, rank in risk_rank.items():
                    if rank == max_risk_rank:
                        overall_risk = name
                block_reasons = []
                if lookahead_risk == "high":
                    block_reasons.append("lookahead_risk_high")
                if multiple_testing_risk == "high":
                    block_reasons.append("multiple_testing_risk_high")
                warnings = list(payload.get("warnings") or [])
                return {
                    "artifact_id": str(artifact.get("artifact_id") or payload.get("artifact_id") or ""),
                    "strategy": str(artifact.get("strategy") or payload.get("strategy") or ""),
                    "strategy_version": str(artifact.get("strategy_version") or payload.get("strategy_version") or ""),
                    "created_at": artifact.get("created_at") or payload.get("created_at"),
                    "updated_at": artifact.get("updated_at") or payload.get("updated_at"),
                    "codes": _as_code_list(payload.get("codes")),
                    "candidate": {
                        "name": candidate.get("name"),
                        "family": candidate.get("family"),
                        "expression_dsl": candidate.get("expression_dsl"),
                        "expected_regime": candidate.get("expected_regime"),
                        "expected_holding_period": candidate.get("expected_holding_period"),
                    },
                    "rating": {
                        "grade": rating.get("grade"),
                        "recommendation": rating.get("recommendation"),
                        "total_score": _safe_float(rating.get("total_score"), 0.0),
                    },
                    "metrics": {
                        "rank_ic_mean": _safe_float(metrics.get("rank_ic_mean"), 0.0),
                        "rank_ic_ir": _safe_float(metrics.get("rank_ic_ir"), 0.0),
                        "sample_dates": int(metrics.get("sample_dates", 0) or 0),
                    },
                    "risk_audit": {
                        "lookahead_risk_level": lookahead_risk,
                        "multiple_testing_risk_level": multiple_testing_risk,
                        "overall_risk_level": overall_risk,
                        "lookahead_available": bool(lookahead_audit.get("available")) if lookahead_audit else False,
                        "multiple_testing_available": bool(multiple_testing.get("available")) if multiple_testing else False,
                        "blocked": bool(block_reasons),
                        "block_reasons": block_reasons,
                        "warning_samples": warnings[:5],
                    },
                    "warnings_count": len(warnings),
                    "stage": str(payload.get("stage") or ""),
                    "source_generation_artifact_id": candidate_resolution.get("artifact_id"),
                    "memory_record_id": memory_record.get("artifact_id"),
                }

            async def _list_factor_candidate_registry_items(
                *,
                limit: int = 20,
                codes: list[str] | None = None,
                family: str | None = None,
                grade: str | None = None,
                recommendation: str | None = None,
                min_score: float | None = None,
                only_active: bool = False,
                market_codes_only: bool = False,
                include_synthetic: bool = False,
            ) -> list[dict]:
                def _looks_like_synthetic_candidate(
                    artifact_id: str,
                    payload: dict,
                    candidate: dict,
                    record_codes: list[str],
                ) -> bool:
                    if include_synthetic:
                        return False
                    text_parts = [
                        artifact_id,
                        str(payload.get("strategy") or ""),
                        str(payload.get("strategy_version") or ""),
                        str(candidate.get("name") or ""),
                        str(candidate.get("family") or ""),
                        str(candidate.get("expression_dsl") or ""),
                    ]
                    normalized = " ".join(text_parts).strip().lower()
                    synthetic_tokens = (
                        "_synthetic",
                        "_demo",
                        "_smoke",
                        "_fixture",
                        "_sample",
                        " demo ",
                        " smoke ",
                        " fixture ",
                        " synthetic ",
                        " sample ",
                    )
                    if any(token in normalized for token in synthetic_tokens):
                        return True
                    return market_codes_only and not _filter_market_codes(record_codes)

                fetch_limit = max(50, min(1000, int(limit) * 12))
                rows = await list_artifacts_async(limit=fetch_limit)
                summary_rows = rows if isinstance(rows, list) else []
                items = []
                requested_codes = _filter_market_codes(codes) if market_codes_only else list(codes or [])
                for row in summary_rows:
                    if str(row.get("strategy") or "").strip().lower() != "quant_factor_candidate_validation":
                        continue
                    artifact_id = str(row.get("artifact_id") or "").strip()
                    if not artifact_id:
                        continue
                    artifact = await get_artifact_async(artifact_id)
                    if not artifact:
                        continue
                    payload = _payload_from_artifact_row(artifact)
                    candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
                    rating = payload.get("rating") if isinstance(payload.get("rating"), dict) else {}
                    record_codes = _as_code_list(payload.get("codes"))
                    effective_record_codes = _filter_market_codes(record_codes) if market_codes_only else record_codes
                    record_family = str(candidate.get("family") or "").strip().lower()
                    record_grade = str(rating.get("grade") or "").strip().upper()
                    record_recommendation = str(rating.get("recommendation") or "").strip().lower()
                    total_score = _safe_float(rating.get("total_score"), 0.0)

                    if market_codes_only and not effective_record_codes:
                        continue
                    if requested_codes and not (set(requested_codes) & set(effective_record_codes)):
                        continue
                    if family and record_family != str(family).strip().lower():
                        continue
                    if grade and record_grade != str(grade).strip().upper():
                        continue
                    if recommendation and record_recommendation != str(recommendation).strip().lower():
                        continue
                    if min_score is not None and total_score < float(min_score):
                        continue
                    if only_active and record_recommendation not in {"promote", "review"}:
                        continue
                    if _looks_like_synthetic_candidate(artifact_id, payload, candidate, record_codes):
                        continue

                    items.append(_normalize_registry_item(artifact, payload))

                items.sort(
                    key=lambda item: (
                        float(((item.get("rating") or {}).get("total_score") or 0.0)),
                        str(item.get("updated_at") or item.get("created_at") or ""),
                    ),
                    reverse=True,
                )
                return items[: max(1, int(limit))]

            def _summarize_factor_candidate_registry(items: list[dict]) -> dict:
                grade_counts = {}
                recommendation_counts = {}
                family_counts = {}
                lookahead_risk_counts = {}
                multiple_testing_risk_counts = {}
                overall_risk_counts = {}
                total_scores = []
                active_items = 0
                governed_active_items = 0
                blocked_items = 0
                blocked_active_items = 0
                for item in list(items or []):
                    rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
                    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
                    risk_audit = item.get("risk_audit") if isinstance(item.get("risk_audit"), dict) else {}
                    grade = str(rating.get("grade") or "").strip().upper()
                    recommendation = str(rating.get("recommendation") or "").strip().lower()
                    family_name = str(candidate.get("family") or "").strip().lower()
                    total_score = _safe_float(rating.get("total_score"), 0.0)
                    lookahead_risk = str(risk_audit.get("lookahead_risk_level") or "unknown").strip().lower()
                    multiple_testing_risk = str(risk_audit.get("multiple_testing_risk_level") or "unknown").strip().lower()
                    overall_risk = str(risk_audit.get("overall_risk_level") or "unknown").strip().lower()
                    blocked = bool(risk_audit.get("blocked"))
                    if grade:
                        grade_counts[grade] = int(grade_counts.get(grade, 0)) + 1
                    if recommendation:
                        recommendation_counts[recommendation] = int(recommendation_counts.get(recommendation, 0)) + 1
                    if family_name:
                        family_counts[family_name] = int(family_counts.get(family_name, 0)) + 1
                    if lookahead_risk:
                        lookahead_risk_counts[lookahead_risk] = int(lookahead_risk_counts.get(lookahead_risk, 0)) + 1
                    if multiple_testing_risk:
                        multiple_testing_risk_counts[multiple_testing_risk] = (
                            int(multiple_testing_risk_counts.get(multiple_testing_risk, 0)) + 1
                        )
                    if overall_risk:
                        overall_risk_counts[overall_risk] = int(overall_risk_counts.get(overall_risk, 0)) + 1
                    total_scores.append(total_score)
                    if recommendation in {"promote", "review"}:
                        active_items += 1
                        if blocked:
                            blocked_active_items += 1
                        else:
                            governed_active_items += 1
                    if blocked:
                        blocked_items += 1
                return {
                    "count": len(list(items or [])),
                    "active_count": active_items,
                    "governed_active_count": governed_active_items,
                    "blocked_count": blocked_items,
                    "blocked_active_count": blocked_active_items,
                    "grade_counts": grade_counts,
                    "recommendation_counts": recommendation_counts,
                    "family_counts": family_counts,
                    "lookahead_risk_counts": lookahead_risk_counts,
                    "multiple_testing_risk_counts": multiple_testing_risk_counts,
                    "overall_risk_counts": overall_risk_counts,
                    "avg_total_score": round(float(np.mean(total_scores)), 6) if total_scores else 0.0,
                    "max_total_score": round(float(max(total_scores)), 6) if total_scores else 0.0,
                }

            def _build_active_candidate_pool(items: list[dict]) -> dict:
                family_bucket = {}
                regime_counts = {}
                top_candidates = []
                excluded_candidates = []
                exclusion_reason_counts = {}

                for item in list(items or []):
                    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
                    rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
                    risk_audit = item.get("risk_audit") if isinstance(item.get("risk_audit"), dict) else {}
                    family = str(candidate.get("family") or "unknown").strip().lower() or "unknown"
                    recommendation = str(rating.get("recommendation") or "").strip().lower()
                    score = _safe_float(rating.get("total_score"), 0.0)
                    regimes = candidate.get("expected_regime") if isinstance(candidate.get("expected_regime"), list) else []
                    exclusion_reasons = []

                    if recommendation not in {"promote", "review"}:
                        exclusion_reasons.append(f"recommendation_{recommendation or 'unknown'}")
                    exclusion_reasons.extend(
                        [str(reason).strip() for reason in list(risk_audit.get("block_reasons") or []) if str(reason).strip()]
                    )
                    if exclusion_reasons:
                        for reason in exclusion_reasons:
                            exclusion_reason_counts[reason] = int(exclusion_reason_counts.get(reason, 0)) + 1
                        excluded_candidates.append(
                            {
                                "artifact_id": item.get("artifact_id"),
                                "name": candidate.get("name"),
                                "family": family,
                                "grade": rating.get("grade"),
                                "recommendation": recommendation,
                                "total_score": score,
                                "risk_audit": risk_audit,
                                "reasons": exclusion_reasons,
                            }
                        )
                        continue

                    bucket = family_bucket.setdefault(
                        family,
                        {
                            "family": family,
                            "count": 0,
                            "promote_count": 0,
                            "review_count": 0,
                            "scores": [],
                        },
                    )
                    bucket["count"] += 1
                    bucket["scores"].append(score)
                    if recommendation == "promote":
                        bucket["promote_count"] += 1
                    if recommendation == "review":
                        bucket["review_count"] += 1

                    for regime in [str(r).strip().lower() for r in regimes if str(r).strip()]:
                        regime_counts[regime] = int(regime_counts.get(regime, 0)) + 1

                    top_candidates.append(
                        {
                            "artifact_id": item.get("artifact_id"),
                            "name": candidate.get("name"),
                            "family": family,
                            "expected_regime": regimes,
                            "grade": rating.get("grade"),
                            "recommendation": recommendation,
                            "total_score": score,
                            "risk_audit": risk_audit,
                        }
                    )

                family_summary = []
                for bucket in family_bucket.values():
                    scores = list(bucket.pop("scores") or [])
                    bucket["avg_total_score"] = round(float(np.mean(scores)), 6) if scores else 0.0
                    bucket["max_total_score"] = round(float(max(scores)), 6) if scores else 0.0
                    family_summary.append(bucket)
                family_summary.sort(key=lambda item: (item.get("avg_total_score", 0.0), item.get("count", 0)), reverse=True)

                regime_summary = [
                    {"regime": regime, "count": count}
                    for regime, count in sorted(regime_counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
                ]
                top_candidates.sort(key=lambda item: (item.get("total_score", 0.0), str(item.get("artifact_id") or "")), reverse=True)
                excluded_candidates.sort(
                    key=lambda item: (item.get("total_score", 0.0), str(item.get("artifact_id") or "")),
                    reverse=True,
                )

                return {
                    "source_count": len(list(items or [])),
                    "count": len(top_candidates),
                    "excluded_count": len(excluded_candidates),
                    "family_summary": family_summary,
                    "regime_summary": regime_summary,
                    "top_candidates": top_candidates[:20],
                    "excluded_candidates": excluded_candidates[:20],
                    "exclusion_reason_counts": exclusion_reason_counts,
                }

            def _normalize_episode_item(artifact: dict, payload: dict) -> dict:
                summary = payload.get("episode_summary") if isinstance(payload.get("episode_summary"), dict) else {}
                return {
                    "artifact_id": str(artifact.get("artifact_id") or payload.get("artifact_id") or ""),
                    "strategy": str(artifact.get("strategy") or payload.get("strategy") or ""),
                    "strategy_version": str(artifact.get("strategy_version") or payload.get("strategy_version") or ""),
                    "created_at": artifact.get("created_at") or payload.get("created_at"),
                    "updated_at": artifact.get("updated_at") or payload.get("updated_at"),
                    "source_artifact_id": payload.get("source_artifact_id"),
                    "codes": _as_code_list(payload.get("codes")),
                    "candidate_limit": int(payload.get("candidate_limit", 0) or 0),
                    "validated_count": int(summary.get("validated_count", 0) or 0),
                    "failed_count": int(summary.get("failed_count", 0) or 0),
                    "grade_counts": summary.get("grade_counts") if isinstance(summary.get("grade_counts"), dict) else {},
                    "recommendation_counts": summary.get("recommendation_counts") if isinstance(summary.get("recommendation_counts"), dict) else {},
                    "best_candidate": summary.get("best_candidate") if isinstance(summary.get("best_candidate"), dict) else {},
                    "worst_candidate": summary.get("worst_candidate") if isinstance(summary.get("worst_candidate"), dict) else {},
                }

            async def _list_replay_episode_items(
                *,
                limit: int = 20,
                codes: list[str] | None = None,
                source_artifact_id: str | None = None,
            ) -> list[dict]:
                fetch_limit = max(50, min(1000, int(limit) * 12))
                rows = await list_artifacts_async(limit=fetch_limit)
                summary_rows = rows if isinstance(rows, list) else []
                items = []
                for row in summary_rows:
                    if str(row.get("strategy") or "").strip().lower() != "quant_factor_episode_replay":
                        continue
                    artifact_id = str(row.get("artifact_id") or "").strip()
                    if not artifact_id:
                        continue
                    artifact = await get_artifact_async(artifact_id)
                    if not artifact:
                        continue
                    payload = _payload_from_artifact_row(artifact)
                    record_codes = _as_code_list(payload.get("codes"))
                    record_source_artifact_id = str(payload.get("source_artifact_id") or "").strip()
                    if codes and not (set(codes) & set(record_codes)):
                        continue
                    if source_artifact_id and record_source_artifact_id != str(source_artifact_id).strip():
                        continue
                    items.append(_normalize_episode_item(artifact, payload))

                items.sort(
                    key=lambda item: (
                        int(item.get("validated_count", 0) or 0),
                        str(item.get("updated_at") or item.get("created_at") or ""),
                    ),
                    reverse=True,
                )
                return items[: max(1, int(limit))]

            def _summarize_replay_episode_items(items: list[dict]) -> dict:
                validated_counts = []
                failed_counts = []
                for item in list(items or []):
                    validated_counts.append(int(item.get("validated_count", 0) or 0))
                    failed_counts.append(int(item.get("failed_count", 0) or 0))
                replayed_counts = [v + f for v, f in zip(validated_counts, failed_counts)]
                success_rates = [
                    (v / max(1, v + f))
                    for v, f in zip(validated_counts, failed_counts)
                ]
                return {
                    "count": len(list(items or [])),
                    "avg_validated_count": round(float(np.mean(validated_counts)), 6) if validated_counts else 0.0,
                    "avg_failed_count": round(float(np.mean(failed_counts)), 6) if failed_counts else 0.0,
                    "avg_replayed_count": round(float(np.mean(replayed_counts)), 6) if replayed_counts else 0.0,
                    "avg_success_rate": round(float(np.mean(success_rates)), 6) if success_rates else 0.0,
                    "max_validated_count": max(validated_counts) if validated_counts else 0,
                }

            if action == "help":
                return _ok(
                    {
                        "supported_actions": {
                            "calculate_factors": "计算因子（需要 code）",
                            "alternative_factors": "P2 另类数据因子化（新闻/公告/研报/资金流）",
                            "factor_ic": "因子 IC 分析（需要 codes, factor）",
                            "backtest_factor": "因子分组回测（需要 codes, factor）",
                            "multi_factor_score": "多因子评分（需要 code）",
                            "llm_factor_mining": "P0 LLM 因子候选生成（真实模型调用 + schema 校验 + fallback）",
                            "validate_factor_candidate": "P1 候选因子验证（DSL 编译 + 横截面 IC 检验，可直接吃 artifact）",
                            "factor_research_memory": "P2 研究记忆查询（list|get|recall|stats）",
                            "factor_candidate_registry": "P2 治理后候选池注册表（list|get|summary|active_pool）",
                            "replay_factor_episode": "P2 因子研究 episode 回放/查询（run|get|list|summary）",
                            "automl_discovery": "P2 AutoML 因子发现（特征筛选+集成+OOS锚点验证）",
                            "feature_store": "P2 特征快照/实验追踪（snapshot|get|list）",
                            "replay_experiment": "P2 结果回放（基于 artifact_id 复跑并输出漂移）",
                            "help": "显示帮助信息",
                        }
                    }
                )

            elif action == "llm_factor_mining":
                codes = _as_code_list(_kw.get("codes"))
                if not codes and code:
                    codes = [code]
                if not codes:
                    return _fail("需要提供 code 或 codes")

                candidate_count = max(1, min(int(_kw.get("candidate_count", 8) or 8), 16))
                lookback_bars = max(120, min(int(_kw.get("lookback_bars", 180) or 180), 360))
                alternative_lookback_days = max(7, min(int(_kw.get("alternative_lookback_days", 30) or 30), 90))
                allow_fallback = bool(_kw.get("allow_fallback", True))
                persist_artifact = bool(_kw.get("persist_artifact", True))
                dedup_mode = str(_kw.get("dedup_mode", "penalty") or "penalty").strip().lower()
                dedup_high_similarity_threshold = float(_kw.get("dedup_high_similarity_threshold", 0.98) or 0.98)
                dedup_failure_similarity_threshold = float(_kw.get("dedup_failure_similarity_threshold", 0.93) or 0.93)
                startup_warmup_enabled = _coerce_bool(
                    _kw.get("startup_warmup"),
                    _env_bool("FACTOR_LLM_STARTUP_WARMUP_ENABLED", True),
                )
                startup_warmup_force = _coerce_bool(
                    _kw.get("startup_warmup_force"),
                    _env_bool("FACTOR_LLM_STARTUP_WARMUP_FORCE", False),
                )
                startup_warmup_limit = max(
                    1,
                    min(
                        int(
                            _kw.get("startup_warmup_limit")
                            or os.getenv("FACTOR_LLM_STARTUP_WARMUP_LIMIT", "4")
                            or 4
                        ),
                        20,
                    ),
                )
                startup_warmup_task_type = (
                    str(
                        _kw.get("startup_warmup_task_type")
                        or os.getenv("FACTOR_LLM_STARTUP_WARMUP_TASK_TYPE", "core_market,factor_context")
                        or "core_market,factor_context"
                    )
                    .strip()
                    .lower()
                    or "core_market,factor_context"
                )

                provider = get_factor_llm_provider()
                memory_service = get_factor_research_memory_service()
                prompt = None
                generation = None
                warnings: list[str] = []
                source_chain = []
                memory_context = {}
                blocked_candidates: list[dict] = []
                startup_warmup = {
                    "ok": True,
                    "status": "disabled",
                    "task_type": startup_warmup_task_type,
                    "force": startup_warmup_force,
                    "matched": 0,
                    "executed": 0,
                    "failed": 0,
                    "executed_task_ids": [],
                    "failed_schedule_ids": [],
                    "schedules": [],
                }
                dedup_summary = {
                    "mode": dedup_mode,
                    "input_count": 0,
                    "kept_count": 0,
                    "blocked_count": 0,
                    "blocked_ratio": 0.0,
                }

                if startup_warmup_enabled:
                    try:
                        startup_warmup = await run_runtime_data_warmup(
                            task_type=startup_warmup_task_type,
                            force=startup_warmup_force,
                            limit=startup_warmup_limit,
                            source="llm_factor_mining",
                        )
                        source_chain.append("tools.managers.data_sync_manager")
                        if startup_warmup.get("status") in {"failed", "partial"}:
                            warnings.append(
                                f"startup_warmup_{startup_warmup.get('status')}: "
                                f"matched={startup_warmup.get('matched', 0)} executed={startup_warmup.get('executed', 0)} failed={startup_warmup.get('failed', 0)}"
                            )
                    except Exception as exc:
                        startup_warmup = {
                            "ok": False,
                            "status": "failed",
                            "task_type": startup_warmup_task_type,
                            "force": startup_warmup_force,
                            "matched": 0,
                            "executed": 0,
                            "failed": 0,
                            "executed_task_ids": [],
                            "failed_schedule_ids": [],
                            "schedules": [],
                            "error": str(exc),
                        }
                        warnings.append(f"startup_warmup_failed: {exc}")

                try:
                    memory_context = await memory_service.build_prompt_memory_context(
                        codes=codes,
                        limit=max(6, candidate_count),
                        query_text=f"codes:{','.join(codes[:8])} factor research prompt",
                    )
                    source_chain.append("services.factor_research_memory")
                except Exception as exc:
                    warnings.append(f"memory_context_failed: {exc}")
                    memory_context = {}

                try:
                    prompt = await build_factor_mining_prompt(
                        db=db,
                        codes=codes,
                        candidate_count=candidate_count,
                        lookback_bars=lookback_bars,
                        alternative_lookback_days=alternative_lookback_days,
                        memory_context=memory_context,
                    )
                    source_chain.extend(list(prompt.source_chain or []))
                    source_chain.append("services.factor_prompt_builder")
                except Exception as exc:
                    warnings.append(f"prompt_build_failed: {exc}")
                    if not allow_fallback:
                        return _fail(
                            f"构建 LLM 因子研究上下文失败: {exc}",
                            source_chain=["services.factor_prompt_builder"],
                        )

                fallback_used = False
                fallback_reason = None
                if prompt is not None and provider.is_enabled():
                    try:
                        generation = await provider.generate_candidates(prompt, candidate_count=candidate_count)
                        source_chain.append("services.factor_llm_provider")
                    except Exception as exc:
                        fallback_reason = str(exc)
                        warnings.append(f"llm_generation_failed: {exc}")
                elif prompt is not None:
                    fallback_reason = "factor llm provider not configured"
                    warnings.append(fallback_reason)

                if generation is None:
                    if not allow_fallback:
                        return _fail(
                            fallback_reason or "factor llm generation unavailable",
                            source_chain=source_chain or ["services.factor_llm_provider"],
                        )
                    try:
                        generation, fallback_source_chain, fallback_reasons = await _build_local_fallback_candidates(
                            codes,
                            candidate_count=candidate_count,
                        )
                        source_chain.extend(fallback_source_chain)
                        fallback_used = True
                        warnings.extend(fallback_reasons[:10])
                    except Exception as exc:
                        return _fail(
                            f"LLM 因子生成失败，且本地回退也失败: {exc}",
                            source_chain=source_chain or ["services.factor_llm_provider", "services.llm_alpha"],
                        )

                pre_dedup_candidate_count = int(generation.get("candidate_count") or len(generation.get("candidates") or []))
                compiler_screening = _screen_compiler_candidates(list(generation.get("candidates") or []))
                generation["candidates"] = list(compiler_screening.get("kept_candidates") or [])
                warnings.extend(list(compiler_screening.get("warnings") or []))
                source_chain.append("services.factor_candidate_compiler")

                if not generation.get("candidates"):
                    fallback_reason = "llm generated 0 compiler-valid candidates"
                    if allow_fallback and not fallback_used:
                        try:
                            generation, fallback_source_chain, fallback_reasons = await _build_local_fallback_candidates(
                                codes,
                                candidate_count=candidate_count,
                            )
                            source_chain.extend(fallback_source_chain)
                            fallback_used = True
                            warnings.append(fallback_reason)
                            warnings.extend(fallback_reasons[:10])
                            compiler_screening = _screen_compiler_candidates(list(generation.get("candidates") or []))
                            generation["candidates"] = list(compiler_screening.get("kept_candidates") or [])
                            warnings.extend(list(compiler_screening.get("warnings") or []))
                        except Exception as exc:
                            return _fail(
                                f"LLM 产出的候选无法通过 compiler 校验，且本地回退也失败: {exc}",
                                source_chain=source_chain or ["services.factor_llm_provider", "services.factor_candidate_compiler", "services.llm_alpha"],
                            )

                    if not generation.get("candidates"):
                        return _fail(
                            "LLM generated 0 compiler-valid candidates",
                            source_chain=source_chain or ["services.factor_llm_provider", "services.factor_candidate_compiler"],
                        )

                try:
                    memory_annotation = await memory_service.annotate_generated_candidates(
                        list(generation.get("candidates") or []),
                        codes=codes,
                    )
                    generation["candidates"] = list(memory_annotation.get("candidates") or generation.get("candidates") or [])
                    dedup_summary.update(
                        {
                            "input_count": len(generation.get("candidates") or []),
                            "kept_count": len(generation.get("candidates") or []),
                            "blocked_count": 0,
                            "blocked_ratio": 0.0,
                        }
                    )
                    warnings.extend(list(memory_annotation.get("warnings") or []))
                    source_chain.append("services.factor_research_memory")

                    duplicate_policy = getattr(memory_service, "apply_duplicate_policy", None)
                    if callable(duplicate_policy):
                        policy_result = duplicate_policy(
                            list(generation.get("candidates") or []),
                            dedup_mode=dedup_mode,
                            high_similarity_threshold=dedup_high_similarity_threshold,
                            failure_similarity_threshold=dedup_failure_similarity_threshold,
                        )
                        generation["candidates"] = list(policy_result.get("kept_candidates") or generation.get("candidates") or [])
                        blocked_candidates = list(policy_result.get("blocked_candidates") or [])
                        dedup_summary = dict(policy_result.get("summary") or dedup_summary)
                        dedup_summary["mode"] = policy_result.get("mode") or dedup_mode
                        warnings.extend(list(policy_result.get("warnings") or []))
                except Exception as exc:
                    warnings.append(f"memory_annotation_failed: {exc}")

                artifact_id = str(_kw.get("artifact_id") or f"factor_llm_{int(time.time())}_{uuid4().hex[:8]}")
                payload = {
                    "artifact_id": artifact_id,
                    "action": "llm_factor_mining",
                    "codes": codes,
                    "generation_mode": "local_rule_fallback" if fallback_used else "llm_provider",
                    "provider_enabled": bool(provider.is_enabled()),
                    "provider": generation.get("provider") or getattr(provider.config, "provider", "openai_compatible"),
                    "model": generation.get("model") or getattr(provider.config, "model", ""),
                    "candidate_count": len(generation.get("candidates") or []),
                    "pre_dedup_candidate_count": pre_dedup_candidate_count,
                    "compiler_screening": compiler_screening.get("summary") or {},
                    "requested_candidate_count": candidate_count,
                    "candidates": list(generation.get("candidates") or []),
                    "blocked_candidates": [
                        *list(compiler_screening.get("rejected_candidates") or []),
                        *blocked_candidates,
                    ],
                    "dedup_summary": dedup_summary,
                    "analysis": dict(generation.get("analysis") or {}),
                    "warnings": list(dict.fromkeys([*list(generation.get("warnings") or []), *warnings]))[:20],
                    "fallback_used": fallback_used,
                    "fallback_reason": fallback_reason,
                    "degraded": bool(fallback_used or warnings or blocked_candidates),
                    "startup_warmup": startup_warmup,
                    "prompt_context": prompt.context_summary if (prompt is not None and explain) else None,
                    "memory_context": memory_context if explain else {"available": bool(memory_context)},
                    "schema_path": getattr(prompt, "schema_path", ""),
                    "params": {
                        "candidate_count": candidate_count,
                        "lookback_bars": lookback_bars,
                        "alternative_lookback_days": alternative_lookback_days,
                        "allow_fallback": allow_fallback,
                        "dedup_mode": dedup_mode,
                        "dedup_high_similarity_threshold": dedup_high_similarity_threshold,
                        "dedup_failure_similarity_threshold": dedup_failure_similarity_threshold,
                        "startup_warmup_enabled": startup_warmup_enabled,
                        "startup_warmup_force": startup_warmup_force,
                        "startup_warmup_limit": startup_warmup_limit,
                        "startup_warmup_task_type": startup_warmup_task_type,
                    },
                }
                if explain and prompt is not None:
                    payload["prompt_preview"] = {
                        "system_prompt": prompt.system_prompt,
                        "user_prompt": prompt.user_prompt,
                    }

                if persist_artifact:
                    await register_artifact_async(
                        {
                            "artifact_id": artifact_id,
                            "strategy": "quant_llm_factor_mining",
                            "strategy_version": "p0.v1",
                            "code": ",".join(codes[:5]),
                            "payload": payload,
                            "created_at": datetime.now().isoformat(),
                        }
                    )
                    source_chain.append("services.artifact_registry")

                return _ok(
                    payload,
                    source_chain=source_chain or ["services.factor_prompt_builder", "services.factor_llm_provider"],
                )

            elif action == "validate_factor_candidate":
                resolved = await _resolve_candidate_for_validation()
                candidate = dict(resolved.get("candidate") or {})
                artifact_payload = resolved.get("artifact_payload") if isinstance(resolved.get("artifact_payload"), dict) else {}
                memory_service = get_factor_research_memory_service()

                codes = _as_code_list(_kw.get("codes"))
                if not codes and code:
                    codes = [code]
                if not codes:
                    codes = _as_code_list(artifact_payload.get("codes"))
                if len(codes) < 3:
                    return _fail("validate_factor_candidate 至少需要 3 个 codes 进行横截面验证")

                lookback_bars = max(120, min(int(_kw.get("lookback_bars", 220) or 220), 500))
                horizon_days = max(3, min(int(_kw.get("horizon_days", 10) or 10), 30))
                max_dates = max(20, min(int(_kw.get("max_dates", 60) or 60), 120))
                persist_artifact = bool(_kw.get("persist_artifact", True))
                write_memory = bool(_kw.get("write_memory", True))

                validation = await validate_factor_candidate_pipeline(
                    db,
                    candidate,
                    codes=codes,
                    lookback_bars=lookback_bars,
                    horizon_days=horizon_days,
                    max_dates=max_dates,
                )
                source_chain = list(validation.get("source_chain") or ["services.factor_candidate_compiler", "services.factor_validation_pipeline"])

                if not validation.get("success"):
                    memory_record = None
                    if write_memory:
                        try:
                            memory_record = await memory_service.record_validation_outcome(
                                candidate=candidate,
                                validation={"rating": {"grade": "D", "recommendation": "reject"}, "metrics": {}},
                                codes=codes,
                                source_artifact_id=resolved.get("artifact_id"),
                                source_action="validate_factor_candidate",
                                explicit_status="fail",
                                tags=[str(validation.get("stage") or "validate_failed")],
                            )
                            source_chain.append("services.factor_research_memory")
                        except Exception:
                            memory_record = None
                    resp = fail(validation.get("error") or "candidate validation failed")
                    resp["data"] = validation
                    if memory_record is not None:
                        resp["data"]["memory_record"] = memory_record
                    return _with_meta(resp, source_chain=source_chain)

                artifact_id = str(_kw.get("output_artifact_id") or f"factor_validation_{int(time.time())}_{uuid4().hex[:8]}")
                memory_record = None
                if write_memory:
                    try:
                        memory_record = await memory_service.record_validation_outcome(
                            candidate=validation.get("compiled", {}).get("candidate") or candidate,
                            validation=validation,
                            codes=codes,
                            source_artifact_id=resolved.get("artifact_id"),
                            source_action="validate_factor_candidate",
                            tags=[
                                str((validation.get("rating") or {}).get("grade") or "").strip(),
                                str((validation.get("rating") or {}).get("recommendation") or "").strip(),
                            ],
                        )
                        source_chain.append("services.factor_research_memory")
                    except Exception as exc:
                        validation.setdefault("warnings", []).append(f"memory_write_failed: {exc}")

                payload = {
                    "artifact_id": artifact_id,
                    "action": "validate_factor_candidate",
                    "codes": codes,
                    "candidate_resolution": {
                        "resolved_from": resolved.get("resolved_from"),
                        "artifact_id": resolved.get("artifact_id"),
                        "candidate_index": resolved.get("candidate_index"),
                    },
                    "candidate": validation.get("compiled", {}).get("candidate") or candidate,
                    "compiled": validation.get("compiled") or {},
                    "metrics": validation.get("metrics") or {},
                    "coverage": validation.get("coverage") or {},
                    "latest_snapshot": validation.get("latest_snapshot") or {},
                    "cross_section_dates": validation.get("cross_section_dates") or [],
                    "lookahead_audit": validation.get("lookahead_audit") or {},
                    "multiple_testing": validation.get("multiple_testing") or {},
                    "oos_validation": validation.get("oos_validation") or {},
                    "robustness": validation.get("robustness") or {},
                    "similarity": validation.get("similarity") or {},
                    "turnover": validation.get("turnover") or {},
                    "cost_capacity": validation.get("cost_capacity") or {},
                    "rating": validation.get("rating") or {},
                    "validation_report": validation.get("validation_report") or {},
                    "factor_validation_report": validation.get("factor_validation_report") or {},
                    "memory_record": memory_record,
                    "warnings": validation.get("warnings") or [],
                    "params": {
                        "lookback_bars": lookback_bars,
                        "horizon_days": horizon_days,
                        "max_dates": max_dates,
                    },
                    "stage": validation.get("stage", "validated"),
                    "degraded": bool(validation.get("warnings")),
                }

                if persist_artifact:
                    await register_artifact_async(
                        {
                            "artifact_id": artifact_id,
                            "strategy": "quant_factor_candidate_validation",
                            "strategy_version": "p1.v1",
                            "code": ",".join(codes[:5]),
                            "payload": payload,
                            "created_at": datetime.now().isoformat(),
                        }
                    )
                    source_chain.append("services.artifact_registry")

                return _ok(payload, source_chain=list(dict.fromkeys(source_chain)))

            elif action == "factor_research_memory":
                memory_service = get_factor_research_memory_service()
                op = str(_kw.get("op", "list") or "list").strip().lower()

                if op in {"list", "ls"}:
                    codes = _as_code_list(_kw.get("codes"))
                    status = str(_kw.get("status") or "").strip() or None
                    family = str(_kw.get("family") or "").strip() or None
                    limit = max(1, min(int(_kw.get("limit", 20) or 20), 100))
                    items = await memory_service.list_memory_records(
                        limit=limit,
                        codes=codes or None,
                        status=status,
                        family=family,
                    )
                    return _ok(
                        {
                            "op": "list",
                            "count": len(items),
                            "items": items,
                        },
                        source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
                    )

                if op in {"get", "detail"}:
                    artifact_id = str(_kw.get("artifact_id") or "").strip()
                    if not artifact_id:
                        return _fail("factor_research_memory get 需要 artifact_id")
                    item = await memory_service.get_memory_record(artifact_id)
                    if not item:
                        return _fail(f"memory record not found: {artifact_id}")
                    return _ok(
                        {"op": "get", "item": item},
                        source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
                    )

                if op in {"recall", "search"}:
                    raw_candidate = _kw.get("candidate")
                    if isinstance(raw_candidate, str) and raw_candidate.strip():
                        try:
                            raw_candidate = json.loads(raw_candidate)
                        except Exception:
                            return _fail("candidate 必须是 dict 或可解析的 JSON 字符串")
                    query_text = str(_kw.get("query_text") or "").strip() or None
                    codes = _as_code_list(_kw.get("codes"))
                    status = str(_kw.get("status") or "").strip() or None
                    limit = max(1, min(int(_kw.get("limit", 5) or 5), 20))
                    items = await memory_service.recall_similar_candidates(
                        candidate=raw_candidate if isinstance(raw_candidate, dict) else None,
                        query_text=query_text,
                        codes=codes or None,
                        status=status,
                        limit=limit,
                    )
                    return _ok(
                        {
                            "op": "recall",
                            "count": len(items),
                            "items": items,
                        },
                        source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
                    )

                if op in {"stats", "summary"}:
                    codes = _as_code_list(_kw.get("codes"))
                    status = str(_kw.get("status") or "").strip() or None
                    family = str(_kw.get("family") or "").strip() or None
                    limit = max(1, min(int(_kw.get("limit", 200) or 200), 500))
                    stats = await memory_service.summarize_memory_records(
                        limit=limit,
                        codes=codes or None,
                        status=status,
                        family=family,
                    )
                    return _ok(
                        {
                            "op": "stats",
                            "stats": stats,
                        },
                        source_chain=["services.factor_research_memory", "services.factor_candidate_storage"],
                    )

                return _fail("Unknown factor_research_memory op. Supported: list|get|recall|stats")

            elif action == "factor_candidate_registry":
                op = str(_kw.get("op", "list") or "list").strip().lower()

                if op in {"list", "ls"}:
                    codes = _as_code_list(_kw.get("codes"))
                    market_codes_only = bool(_kw.get("market_codes_only", False))
                    include_synthetic = bool(_kw.get("include_synthetic", False))
                    family = str(_kw.get("family") or "").strip() or None
                    grade = str(_kw.get("grade") or "").strip() or None
                    recommendation = str(_kw.get("recommendation") or "").strip() or None
                    min_score = _kw.get("min_score")
                    min_score = None if min_score in {None, ""} else _safe_float(min_score, 0.0)
                    only_active = bool(_kw.get("only_active", False))
                    limit = max(1, min(int(_kw.get("limit", 20) or 20), 100))
                    items = await _list_factor_candidate_registry_items(
                        limit=limit,
                        codes=codes or None,
                        family=family,
                        grade=grade,
                        recommendation=recommendation,
                        min_score=min_score,
                        only_active=only_active,
                        market_codes_only=market_codes_only,
                        include_synthetic=include_synthetic,
                    )
                    return _ok(
                        {
                            "op": "list",
                            "count": len(items),
                            "items": items,
                            "summary": _summarize_factor_candidate_registry(items),
                        },
                        source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
                    )

                if op in {"summary", "stats"}:
                    codes = _as_code_list(_kw.get("codes"))
                    market_codes_only = bool(_kw.get("market_codes_only", False))
                    include_synthetic = bool(_kw.get("include_synthetic", False))
                    family = str(_kw.get("family") or "").strip() or None
                    grade = str(_kw.get("grade") or "").strip() or None
                    recommendation = str(_kw.get("recommendation") or "").strip() or None
                    min_score = _kw.get("min_score")
                    min_score = None if min_score in {None, ""} else _safe_float(min_score, 0.0)
                    only_active = bool(_kw.get("only_active", False))
                    limit = max(1, min(int(_kw.get("limit", 200) or 200), 500))
                    items = await _list_factor_candidate_registry_items(
                        limit=limit,
                        codes=codes or None,
                        family=family,
                        grade=grade,
                        recommendation=recommendation,
                        min_score=min_score,
                        only_active=only_active,
                        market_codes_only=market_codes_only,
                        include_synthetic=include_synthetic,
                    )
                    return _ok(
                        {
                            "op": "summary",
                            "summary": _summarize_factor_candidate_registry(items),
                        },
                        source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
                    )

                if op in {"active_pool", "pool"}:
                    codes = _as_code_list(_kw.get("codes"))
                    market_codes_only = bool(_kw.get("market_codes_only", True))
                    include_synthetic = bool(_kw.get("include_synthetic", False))
                    family = str(_kw.get("family") or "").strip() or None
                    min_score = _kw.get("min_score")
                    min_score = None if min_score in {None, ""} else _safe_float(min_score, 0.0)
                    limit = max(1, min(int(_kw.get("limit", 200) or 200), 500))
                    items = await _list_factor_candidate_registry_items(
                        limit=limit,
                        codes=codes or None,
                        family=family,
                        recommendation=None,
                        min_score=min_score,
                        only_active=True,
                        market_codes_only=market_codes_only,
                        include_synthetic=include_synthetic,
                    )
                    return _ok(
                        {
                            "op": "active_pool",
                            "summary": _summarize_factor_candidate_registry(items),
                            "active_pool": _build_active_candidate_pool(items),
                        },
                        source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
                    )

                if op in {"get", "detail"}:
                    artifact_id = str(_kw.get("artifact_id") or "").strip()
                    if not artifact_id:
                        return _fail("factor_candidate_registry get 需要 artifact_id")
                    artifact = await get_artifact_async(artifact_id)
                    if not artifact:
                        return _fail(f"artifact not found: {artifact_id}")
                    if str(artifact.get("strategy") or "").strip().lower() != "quant_factor_candidate_validation":
                        return _fail(f"artifact {artifact_id} is not quant_factor_candidate_validation")
                    payload = _payload_from_artifact_row(artifact)
                    return _ok(
                        {
                            "op": "get",
                            "item": _normalize_registry_item(artifact, payload),
                            "artifact": artifact,
                        },
                        source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
                    )

                return _fail("Unknown factor_candidate_registry op. Supported: list|get|summary|active_pool")

            elif action == "replay_factor_episode":
                op = str(_kw.get("op", "run") or "run").strip().lower()

                if op in {"list", "ls"}:
                    codes = _as_code_list(_kw.get("codes"))
                    source_artifact_id = str(_kw.get("source_artifact_id") or "").strip() or None
                    limit = max(1, min(int(_kw.get("limit", 20) or 20), 100))
                    items = await _list_replay_episode_items(
                        limit=limit,
                        codes=codes or None,
                        source_artifact_id=source_artifact_id,
                    )
                    return _ok(
                        {
                            "op": "list",
                            "count": len(items),
                            "items": items,
                            "summary": _summarize_replay_episode_items(items),
                        },
                        source_chain=["services.artifact_registry", "quant_manager.replay_factor_episode"],
                    )

                if op in {"summary", "stats"}:
                    codes = _as_code_list(_kw.get("codes"))
                    source_artifact_id = str(_kw.get("source_artifact_id") or "").strip() or None
                    limit = max(1, min(int(_kw.get("limit", 200) or 200), 500))
                    items = await _list_replay_episode_items(
                        limit=limit,
                        codes=codes or None,
                        source_artifact_id=source_artifact_id,
                    )
                    return _ok(
                        {
                            "op": "summary",
                            "summary": _summarize_replay_episode_items(items),
                        },
                        source_chain=["services.artifact_registry", "quant_manager.replay_factor_episode"],
                    )

                if op in {"get", "detail"}:
                    artifact_id = str(_kw.get("artifact_id") or "").strip()
                    if not artifact_id:
                        return _fail("replay_factor_episode get 需要 artifact_id")
                    artifact = await get_artifact_async(artifact_id)
                    if not artifact:
                        return _fail(f"artifact not found: {artifact_id}")
                    if str(artifact.get("strategy") or "").strip().lower() != "quant_factor_episode_replay":
                        return _fail(f"artifact {artifact_id} is not quant_factor_episode_replay")
                    payload = _payload_from_artifact_row(artifact)
                    return _ok(
                        {
                            "op": "get",
                            "item": _normalize_episode_item(artifact, payload),
                            "artifact": artifact,
                        },
                        source_chain=["services.artifact_registry", "quant_manager.replay_factor_episode"],
                    )

                artifact_id = str(_kw.get("artifact_id") or "").strip()
                if not artifact_id:
                    return _fail("replay_factor_episode 需要 artifact_id")

                artifact = await get_artifact_async(artifact_id)
                if not artifact:
                    return _fail(f"artifact not found: {artifact_id}")

                strategy = str(artifact.get("strategy") or "").strip().lower()
                payload = _payload_from_artifact_row(artifact)
                if strategy != "quant_llm_factor_mining":
                    return _fail(f"artifact {artifact_id} is not quant_llm_factor_mining")

                source_codes = _as_code_list(payload.get("codes"))
                replay_codes = _as_code_list(_kw.get("codes")) or source_codes
                if len(replay_codes) < 3:
                    return _fail("replay_factor_episode 至少需要 3 个 codes，可通过 kwargs.codes 覆盖")

                candidates = [dict(item) for item in list(payload.get("candidates") or []) if isinstance(item, dict)]
                if not candidates:
                    return _fail(f"artifact {artifact_id} does not contain candidates")

                lookback_bars = max(120, min(int(_kw.get("lookback_bars", (payload.get("params") or {}).get("lookback_bars", 220)) or 220), 500))
                horizon_days = max(3, min(int(_kw.get("horizon_days", (payload.get("params") or {}).get("horizon_days", 10)) or 10), 30))
                max_dates = max(20, min(int(_kw.get("max_dates", 60) or 60), 120))
                write_memory = bool(_kw.get("write_memory", False))
                persist_artifact = bool(_kw.get("persist_artifact", True))
                candidate_limit = max(1, min(int(_kw.get("candidate_limit", len(candidates)) or len(candidates)), len(candidates)))

                outcomes = []
                grade_counts = {}
                recommendation_counts = {}
                success_count = 0
                failed_count = 0
                best_outcome = None
                worst_outcome = None

                for idx, candidate_item in enumerate(candidates[:candidate_limit]):
                    validation_resp = await quant_manager(
                        action="validate_factor_candidate",
                        kwargs={
                            "candidate": candidate_item,
                            "codes": replay_codes,
                            "lookback_bars": lookback_bars,
                            "horizon_days": horizon_days,
                            "max_dates": max_dates,
                            "persist_artifact": False,
                            "write_memory": write_memory,
                        },
                    )
                    if validation_resp.get("success"):
                        data = validation_resp.get("data", {}) if isinstance(validation_resp.get("data"), dict) else {}
                        rating = data.get("rating") if isinstance(data.get("rating"), dict) else {}
                        grade = str(rating.get("grade") or "").strip().upper()
                        recommendation = str(rating.get("recommendation") or "").strip().lower()
                        total_score = _safe_float(rating.get("total_score"), 0.0)
                        row = {
                            "candidate_index": idx,
                            "name": candidate_item.get("name"),
                            "family": candidate_item.get("family"),
                            "status": "validated",
                            "grade": grade,
                            "recommendation": recommendation,
                            "total_score": total_score,
                            "rank_ic_mean": _safe_float((data.get("metrics") or {}).get("rank_ic_mean"), 0.0),
                            "warnings": list(data.get("warnings") or []),
                        }
                        outcomes.append(row)
                        success_count += 1
                        if grade:
                            grade_counts[grade] = int(grade_counts.get(grade, 0)) + 1
                        if recommendation:
                            recommendation_counts[recommendation] = int(recommendation_counts.get(recommendation, 0)) + 1
                        if best_outcome is None or total_score > _safe_float(best_outcome.get("total_score"), -1e9):
                            best_outcome = row
                        if worst_outcome is None or total_score < _safe_float(worst_outcome.get("total_score"), 1e9):
                            worst_outcome = row
                    else:
                        failed_count += 1
                        fail_payload = validation_resp.get("data", {}) if isinstance(validation_resp.get("data"), dict) else {}
                        outcomes.append(
                            {
                                "candidate_index": idx,
                                "name": candidate_item.get("name"),
                                "family": candidate_item.get("family"),
                                "status": "failed",
                                "stage": fail_payload.get("stage"),
                                "error": validation_resp.get("error") or validation_resp.get("message") or "candidate validation failed",
                            }
                        )

                output_artifact_id = str(_kw.get("output_artifact_id") or f"factor_episode_{int(time.time())}_{uuid4().hex[:8]}")
                replay_payload = {
                    "artifact_id": output_artifact_id,
                    "action": "replay_factor_episode",
                    "source_artifact_id": artifact_id,
                    "codes": replay_codes,
                    "candidate_limit": candidate_limit,
                    "params": {
                        "lookback_bars": lookback_bars,
                        "horizon_days": horizon_days,
                        "max_dates": max_dates,
                        "write_memory": write_memory,
                    },
                    "episode_summary": {
                        "input_candidate_count": len(candidates),
                        "replayed_candidate_count": len(outcomes),
                        "validated_count": success_count,
                        "failed_count": failed_count,
                        "grade_counts": grade_counts,
                        "recommendation_counts": recommendation_counts,
                        "best_candidate": best_outcome,
                        "worst_candidate": worst_outcome,
                    },
                    "outcomes": outcomes,
                    "source_generation_summary": {
                        "provider": payload.get("provider"),
                        "model": payload.get("model"),
                        "generation_mode": payload.get("generation_mode"),
                        "dedup_summary": payload.get("dedup_summary") if isinstance(payload.get("dedup_summary"), dict) else {},
                        "blocked_candidates": list(payload.get("blocked_candidates") or []),
                    },
                }

                if persist_artifact:
                    register_artifact(
                        {
                            "artifact_id": output_artifact_id,
                            "strategy": "quant_factor_episode_replay",
                            "strategy_version": "p2.v2",
                            "code": ",".join(replay_codes[:5]),
                            "payload": replay_payload,
                            "created_at": datetime.now().isoformat(),
                        }
                    )

                return _ok(
                    replay_payload,
                    source_chain=["services.artifact_registry", "quant_manager.validate_factor_candidate"],
                )

            elif action == "calculate_factors":
                if not code:
                    return _fail("需要提供股票代码（code）")

                factors = _kw.get("factors", ["momentum", "value", "quality", "growth"])
                supported_factors = {
                    "momentum",
                    "value",
                    "quality",
                    "growth",
                    "volatility",
                    "liquidity",
                    "sentiment",
                    "event",
                    "capital_flow",
                    "alternative_composite",
                }
                unknown_factors = [f for f in factors if f not in supported_factors]
                if unknown_factors:
                    return _fail(
                        f"Unsupported factors: {unknown_factors}. "
                        f"Supported: {sorted(supported_factors)}"
                    )

                klines = await db.get_klines(code, limit=252)
                source_chain = ["db.get_klines"]

                if not klines:
                    logger.info("[QuantManager] No kline in DB, fallback data_source.get_kline: %s", code)
                    klines_data = data_source.get_kline(code, period="daily", limit=252)
                    if klines_data:
                        klines = [
                            {
                                "date": k.get("date"),
                                "open": k.get("open"),
                                "high": k.get("high"),
                                "low": k.get("low"),
                                "close": k.get("close"),
                                "volume": k.get("volume"),
                                "amount": k.get("amount", 0),
                            }
                            for k in klines_data
                        ]
                        source_chain = ["data_source.get_kline"]

                if not klines:
                    return _fail(
                        f"未找到 {code} 的K线数据。\n\n"
                        f"请先运行数据预热: data_warmup(action='warmup', stocks=['{code}'], lookback_days=252)",
                        source_chain=source_chain,
                    )

                ordered_klines = _sort_klines_ascending(klines)
                closes = [k.get("close") for k in ordered_klines if isinstance(k, dict) and k.get("close") is not None]
                if len(closes) < 2:
                    return _fail("K线数据不足，无法计算因子", source_chain=source_chain)

                financials = await db.get_financials(code, limit=4)
                latest_financial = _select_financial_snapshot(financials)
                valuation_snapshot = await _load_valuation_snapshot(db, code)

                factor_values = {}

                if "momentum" in factors:
                    momentum_20 = (closes[-1] - closes[-20]) / closes[-20] if len(closes) >= 20 and closes[-20] else 0.0
                    momentum_60 = (closes[-1] - closes[-60]) / closes[-60] if len(closes) >= 60 and closes[-60] else 0.0
                    momentum_120 = (closes[-1] - closes[-120]) / closes[-120] if len(closes) >= 120 and closes[-120] else 0.0
                    factor_values["momentum"] = {
                        "momentum_20d": float(momentum_20),
                        "momentum_60d": float(momentum_60),
                        "momentum_120d": float(momentum_120),
                        "score": float((momentum_20 + momentum_60 + momentum_120) / 3.0),
                        "level": "strong" if momentum_60 > 0.1 else ("weak" if momentum_60 < -0.1 else "neutral"),
                    }

                if "value" in factors:
                    pe_ratio = float(valuation_snapshot.get("pe_ratio", 0) or 0)
                    pb_ratio = float(valuation_snapshot.get("pb_ratio", 0) or 0)
                    ps_ratio = float(latest_financial.get("ps_ratio", 0) or 0)
                    pe_score = 1.0 / pe_ratio if pe_ratio > 0 else 0.0
                    pb_score = 1.0 / pb_ratio if pb_ratio > 0 else 0.0
                    value_components = [score for score in (pe_score, pb_score) if score > 0]
                    if ps_ratio > 0:
                        value_components.append(1.0 / ps_ratio)
                    value_score = sum(value_components) / len(value_components) if value_components else 0.0
                    factor_values["value"] = {
                        "pe_ratio": pe_ratio,
                        "pb_ratio": pb_ratio,
                        "ps_ratio": ps_ratio,
                        "score": float(value_score),
                        "level": "undervalued" if pe_ratio > 0 and pe_ratio < 15 and pb_ratio > 0 and pb_ratio < 2 else (
                            "overvalued" if pe_ratio > 30 else "fair"
                        ),
                    }

                if "quality" in factors:
                    roe = float(latest_financial.get("roe", 0) or 0)
                    roa = float(latest_financial.get("roa", 0) or 0)
                    gross_margin = float(latest_financial.get("gross_margin", 0) or 0)
                    debt_ratio = float(latest_financial.get("debt_ratio", 0) or 0)
                    quality_score = (
                        (roe / 30 if roe > 0 else 0) * 0.4
                        + (roa / 15 if roa > 0 else 0) * 0.3
                        + (gross_margin / 50 if gross_margin > 0 else 0) * 0.2
                        + ((1 - debt_ratio) if debt_ratio < 1 else 0) * 0.1
                    )
                    factor_values["quality"] = {
                        "roe": roe,
                        "roa": roa,
                        "gross_margin": gross_margin,
                        "debt_ratio": debt_ratio,
                        "score": float(quality_score),
                        "level": "high" if roe > 15 and debt_ratio < 0.5 else ("low" if roe < 5 else "medium"),
                    }

                if "growth" in factors:
                    revenue_growth = float(latest_financial.get("revenue_growth", 0) or 0)
                    profit_growth = float(latest_financial.get("profit_growth", 0) or 0)
                    growth_score = float(max(min((revenue_growth + profit_growth) / 200.0, 1.0), -1.0))
                    factor_values["growth"] = {
                        "revenue_growth": revenue_growth,
                        "profit_growth": profit_growth,
                        "score": growth_score,
                        "level": "high" if revenue_growth > 15 and profit_growth > 15 else (
                            "low" if revenue_growth < 0 and profit_growth < 0 else "medium"
                        ),
                    }

                if "volatility" in factors:
                    prices = np.array(closes, dtype=float)
                    returns = np.diff(prices) / prices[:-1]
                    volatility = float(np.std(returns) * np.sqrt(252)) if len(returns) > 1 else 0.0
                    factor_values["volatility"] = {
                        "annual_volatility": volatility,
                        "score": float(1.0 / volatility if volatility > 0 else 0.0),
                        "level": "high" if volatility > 0.4 else ("low" if volatility < 0.2 else "medium"),
                    }

                if "liquidity" in factors:
                    volumes = [float(k.get("volume", 0) or 0) for k in klines[-20:]]
                    amounts = [float(k.get("amount", 0) or 0) for k in klines[-20:]]
                    avg_volume = float(np.mean(volumes)) if volumes else 0.0
                    avg_amount = float(np.mean(amounts)) if amounts else 0.0
                    factor_values["liquidity"] = {
                        "avg_volume_20d": avg_volume,
                        "avg_amount_20d": avg_amount,
                        "score": float(avg_amount / 1e8),
                        "level": "high" if avg_amount > 1e8 else ("low" if avg_amount < 1e7 else "medium"),
                    }

                requested_alt = any(
                    f in factors for f in ("sentiment", "event", "capital_flow", "alternative_composite")
                )
                if requested_alt:
                    alt_days = int(_kw.get("alt_lookback_days", 30) or 30)
                    alt_limit = int(_kw.get("alt_limit", 20) or 20)
                    alt_factors, alt_sources = await _compute_alternative_factors_for_code(
                        db=db,
                        code=code,
                        lookback_days=alt_days,
                        limit=alt_limit,
                    )
                    for key in ("sentiment", "event", "capital_flow", "alternative_composite"):
                        if key in factors and key in alt_factors:
                            factor_values[key] = alt_factors[key]
                    source_chain = source_chain + alt_sources

                composite_score = float(np.mean([f.get("score", 0) for f in factor_values.values()])) if factor_values else 0.0
                return _ok(
                    {
                        "code": code,
                        "factors": factor_values,
                        "composite_score": composite_score,
                        "data_window": {
                            "kline_bars": len(closes),
                            "financial_records": len(financials) if isinstance(financials, list) else (1 if isinstance(financials, dict) else 0),
                        },
                    },
                    source_chain=source_chain + ["db.get_financials"],
                )

            elif action == "factor_ic":
                factor_name = str(_kw.get("factor_name", _kw.get("factor", "momentum")) or "").strip().lower()
                period = _kw.get("period", 20)
                codes = _kw.get("codes", [])
                enable_neutralization = bool(_kw.get("enable_neutralization", True))
                bootstrap_n = int(_kw.get("bootstrap_n", 1000) or 1000)
                bootstrap_confidence = float(_kw.get("bootstrap_confidence", 0.95) or 0.95)

                if factor_name not in SUPPORTED_FACTORS:
                    return _fail(
                        f"Unsupported factor: {factor_name}. "
                        f"Supported: {sorted(SUPPORTED_FACTORS.keys())}"
                    )
                if not isinstance(codes, list) or not codes:
                    return _fail("需要提供股票列表（codes）")

                result = await run_factor_ic_analysis(
                    codes=codes,
                    factor=factor_name,
                    period=period,
                    enable_neutralization=enable_neutralization,
                    bootstrap_n=bootstrap_n,
                    bootstrap_confidence=bootstrap_confidence,
                )
                if result.get("success") and isinstance(result.get("data"), dict):
                    result["data"]["factor_name"] = result["data"].get("factor", factor_name)
                    result["data"]["description"] = "IC>0 表示因子与未来收益同向关联，IC<0 则反向"

                return _with_meta(
                    result,
                    source_chain=["db.get_klines", "db.get_financials(optional)", "factor_analysis_dual_ic", "bootstrap_ci"],
                )

            elif action == "backtest_factor":
                factor_name = str(_kw.get("factor_name", _kw.get("factor", "momentum")) or "").strip().lower()
                start_date = _kw.get("start_date")
                end_date = _kw.get("end_date")
                groups = _kw.get("groups", 5)
                holding_days = _kw.get("holding_days", 20)
                factor_lookback = _kw.get("factor_lookback", 20)
                codes = _kw.get("codes", [])

                if factor_name not in SUPPORTED_FACTORS:
                    return _fail(
                        f"Unsupported factor: {factor_name}. "
                        f"Supported: {sorted(SUPPORTED_FACTORS.keys())}"
                    )
                if not isinstance(codes, list) or not codes:
                    return _fail("需要提供股票列表（codes）")

                result = await run_factor_group_backtest(
                    codes=codes,
                    factor=factor_name,
                    groups=groups,
                    holding_days=holding_days,
                    factor_lookback=factor_lookback,
                )
                if result.get("success") and isinstance(result.get("data"), dict):
                    result["data"]["factor_name"] = result["data"].get("factor", factor_name)
                    result["data"]["start_date"] = start_date
                    result["data"]["end_date"] = end_date

                return _with_meta(
                    result,
                    source_chain=["db.get_klines", "db.get_financials(optional)", "numpy-grouping"],
                )

            elif action == "multi_factor_score":
                if not code:
                    return _fail("需要提供股票代码（code）")

                weights = _kw.get(
                    "weights",
                    {
                        "momentum": 0.3,
                        "value": 0.3,
                        "quality": 0.2,
                        "volatility": 0.1,
                        "liquidity": 0.1,
                    },
                )

                result = await quant_manager(action="calculate_factors", code=code, factors=list(weights.keys()))
                if not result.get("success"):
                    return result

                factors_data = result["data"]["factors"]
                total_score = 0.0
                factor_scores = {}

                for factor_name, weight in weights.items():
                    if factor_name in factors_data:
                        score = float(factors_data[factor_name].get("score", 0.0))
                        weighted_score = score * float(weight)
                        total_score += weighted_score
                        factor_scores[factor_name] = {
                            "score": score,
                            "weight": float(weight),
                            "weighted_score": float(weighted_score),
                        }

                if total_score > 0.7:
                    rating, recommendation = "A", "strong_buy"
                elif total_score > 0.5:
                    rating, recommendation = "B", "buy"
                elif total_score > 0.3:
                    rating, recommendation = "C", "hold"
                else:
                    rating, recommendation = "D", "sell"

                return _ok(
                    {
                        "code": code,
                        "total_score": float(total_score),
                        "rating": rating,
                        "recommendation": recommendation,
                        "factor_scores": factor_scores,
                    },
                    source_chain=["quant_manager.calculate_factors"],
                )

            elif action == "alternative_factors":
                codes = _as_code_list(_kw.get("codes"))
                if not codes and code:
                    codes = [code]
                if not codes:
                    return _fail("需要提供 code 或 codes")

                lookback_days = int(_kw.get("lookback_days", 30) or 30)
                limit = int(_kw.get("limit", 20) or 20)
                lookback_days = max(7, min(180, lookback_days))
                limit = max(5, min(100, limit))

                result_rows = []
                source_chain = []
                for one_code in codes:
                    factors, one_source_chain = await _compute_alternative_factors_for_code(
                        db=db,
                        code=one_code,
                        lookback_days=lookback_days,
                        limit=limit,
                    )
                    source_chain.extend(one_source_chain)
                    result_rows.append({"code": one_code, "factors": factors})

                return _ok(
                    {
                        "codes": codes,
                        "count": len(result_rows),
                        "data_window": {"lookback_days": lookback_days, "limit_per_source": limit},
                        "rows": result_rows,
                    },
                    source_chain=source_chain or ["quant_manager.alternative_factors"],
                )

            elif action == "automl_discovery":
                codes = _as_code_list(_kw.get("codes"))
                if not codes:
                    return _fail("需要提供股票列表（codes）")

                horizon_days = int(_kw.get("horizon_days", 10) or 10)
                lookback_bars = int(_kw.get("lookback_bars", 160) or 160)
                top_k_features = int(_kw.get("top_k_features", 6) or 6)
                train_ratio = float(_kw.get("train_ratio", 0.7) or 0.7)
                max_feature_corr = float(_kw.get("max_feature_corr", 0.85) or 0.85)
                include_alternative = bool(_kw.get("include_alternative", True))
                alt_lookback_days = int(_kw.get("alt_lookback_days", 30) or 30)
                persist_artifact = bool(_kw.get("persist_artifact", True))
                run_anchor_oos = bool(_kw.get("run_anchor_oos", True))

                records, dataset_stats = await _build_automl_dataset(
                    db=db,
                    codes=codes,
                    horizon_days=max(3, min(30, horizon_days)),
                    lookback_bars=max(120, min(500, lookback_bars)),
                    include_alternative=include_alternative,
                    alt_lookback_days=max(7, min(120, alt_lookback_days)),
                )
                model_res = _fit_automl_model(
                    records=records,
                    top_k_features=max(2, min(15, top_k_features)),
                    train_ratio=_clip(train_ratio, 0.55, 0.9),
                    max_feature_corr=_clip(max_feature_corr, 0.5, 0.99),
                )
                if not model_res.get("success"):
                    return _fail(
                        model_res.get("error", "automl failed"),
                        source_chain=["db.get_klines", "numpy.feature_selection"],
                    )

                selected_features = model_res.get("selected_features", [])
                anchor_factor = _select_anchor_factor(selected_features)
                anchor_oos = None
                if run_anchor_oos:
                    try:
                        anchor_oos = await run_factor_oos_validation(
                            codes=codes,
                            factor=anchor_factor,
                            factor_lookback=20,
                            forward_period=max(5, min(20, horizon_days)),
                            panel_periods=180,
                            wf_train_window=60,
                            wf_test_window=20,
                            wf_step=20,
                            kfold_n_folds=5,
                            kfold_purge_gap=5,
                            bootstrap_n=600,
                            bootstrap_confidence=0.95,
                        )
                    except Exception as exc:
                        anchor_oos = fail(f"anchor_oos_failed: {exc}")

                artifact_id = f"quant_automl_{int(time.time())}_{uuid4().hex[:8]}"
                output = {
                    "artifact_id": artifact_id,
                    "codes": codes,
                    "dataset_stats": dataset_stats,
                    "selected_features": selected_features,
                    "feature_weights": model_res.get("feature_weights", {}),
                    "feature_importance_abs_corr": model_res.get("feature_importance_abs_corr", []),
                    "metrics": model_res.get("metrics", {}),
                    "threshold_backtest": model_res.get("threshold_backtest", []),
                    "train_test_split": model_res.get("train_test_split", {}),
                    "robust_constraints": {
                        "min_sample_required": 80,
                        "max_feature_corr": _clip(max_feature_corr, 0.5, 0.99),
                        "passed": bool(dataset_stats.get("sample_count", 0) >= 80),
                    },
                    "oos_anchor": {
                        "factor": anchor_factor,
                        "result": anchor_oos,
                    },
                    "params": {
                        "horizon_days": horizon_days,
                        "lookback_bars": lookback_bars,
                        "top_k_features": top_k_features,
                        "train_ratio": train_ratio,
                        "include_alternative": include_alternative,
                        "alt_lookback_days": alt_lookback_days,
                    },
                }

                if persist_artifact:
                    register_artifact(
                        {
                            "artifact_id": artifact_id,
                            "strategy": "quant_automl_discovery",
                            "strategy_version": "p2.v1",
                            "code": ",".join(codes[:5]),
                            "payload": output,
                            "created_at": datetime.now().isoformat(),
                        }
                    )

                return _ok(
                    output,
                    source_chain=[
                        "db.get_klines",
                        "db.get_financials",
                        "tools.news.*",
                        "tools.fund_flow.*",
                        "numpy.feature_selection_ensemble",
                        "quant.run_factor_oos_validation(anchor)",
                        "services.artifact_registry",
                    ],
                )

            elif action == "feature_store":
                op = str(_kw.get("op", "list") or "list").strip().lower()
                if op in {"snapshot", "create"}:
                    codes = _as_code_list(_kw.get("codes"))
                    if not codes and code:
                        codes = [code]
                    if not codes:
                        return _fail("feature_store snapshot 需要 code 或 codes")

                    factors = _kw.get(
                        "factors",
                        [
                            "momentum",
                            "value",
                            "quality",
                            "volatility",
                            "liquidity",
                            "sentiment",
                            "event",
                            "capital_flow",
                            "alternative_composite",
                        ],
                    )
                    snapshot_rows = []
                    for one_code in codes:
                        fac_res = await quant_manager(action="calculate_factors", code=one_code, factors=factors)
                        if fac_res.get("success"):
                            snapshot_rows.append(
                                {
                                    "code": one_code,
                                    "factors": fac_res.get("data", {}).get("factors", {}),
                                    "composite_score": fac_res.get("data", {}).get("composite_score"),
                                }
                            )

                    artifact_id = str(_kw.get("artifact_id") or f"feature_store_{int(time.time())}_{uuid4().hex[:8]}")
                    payload = {
                        "artifact_id": artifact_id,
                        "strategy": "feature_store_snapshot",
                        "strategy_version": "p2.v1",
                        "code": ",".join(codes[:5]),
                        "snapshot_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "codes": codes,
                        "factors": factors,
                        "rows": snapshot_rows,
                        "count": len(snapshot_rows),
                    }
                    register_artifact(payload)
                    return _ok(
                        {
                            "op": "snapshot",
                            "artifact_id": artifact_id,
                            "count": len(snapshot_rows),
                            "codes": codes,
                        },
                        source_chain=["quant_manager.calculate_factors", "services.artifact_registry"],
                    )

                if op in {"get", "detail"}:
                    artifact_id = str(_kw.get("artifact_id") or "").strip()
                    if not artifact_id:
                        return _fail("feature_store get 需要 artifact_id")
                    artifact = await get_artifact_async(artifact_id)
                    if not artifact:
                        return _fail(f"artifact not found: {artifact_id}")
                    return _ok(
                        {"op": "get", "artifact": artifact},
                        source_chain=["services.artifact_registry"],
                    )

                if op in {"list", "ls"}:
                    limit = int(_kw.get("limit", 20) or 20)
                    items = await list_artifacts_async(limit=max(1, min(200, limit)))
                    filtered = _filter_quant_artifacts(items if isinstance(items, list) else [])
                    return _ok(
                        {"op": "list", "items": filtered, "count": len(filtered)},
                        source_chain=["services.artifact_registry"],
                    )

                if op in {"track", "log"}:
                    artifact_id = str(_kw.get("artifact_id") or f"quant_exp_{int(time.time())}_{uuid4().hex[:8]}")
                    payload = {
                        "artifact_id": artifact_id,
                        "strategy": "quant_experiment",
                        "strategy_version": str(_kw.get("strategy_version") or "p2.v1"),
                        "code": str(_kw.get("code") or code or ""),
                        "name": str(_kw.get("name") or ""),
                        "params": _kw.get("params") if isinstance(_kw.get("params"), dict) else {},
                        "metrics": _kw.get("metrics") if isinstance(_kw.get("metrics"), dict) else {},
                        "notes": str(_kw.get("notes") or ""),
                        "tracked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    register_artifact(payload)
                    return _ok(
                        {"op": "track", "artifact_id": artifact_id},
                        source_chain=["services.artifact_registry"],
                    )

                return _fail("Unknown feature_store op. Supported: snapshot|get|list|track")

            elif action == "replay_experiment":
                artifact_id = str(_kw.get("artifact_id") or "").strip()
                if not artifact_id:
                    return _fail("需要 artifact_id")

                artifact = await get_artifact_async(artifact_id)
                if not artifact:
                    return _fail(f"artifact not found: {artifact_id}")

                strategy = str(artifact.get("strategy") or "").lower()
                payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else artifact
                if strategy != "quant_automl_discovery":
                    return _fail(f"artifact {artifact_id} is not quant_automl_discovery")

                params = payload.get("params", {}) if isinstance(payload, dict) else {}
                replay_codes = _as_code_list(payload.get("codes")) or _as_code_list(params.get("codes")) or _as_code_list(_kw.get("codes"))
                if not replay_codes:
                    return _fail("replay requires codes in artifact or kwargs")

                replay_action = await quant_manager(
                    action="automl_discovery",
                    kwargs={
                        "codes": replay_codes,
                        "horizon_days": params.get("horizon_days", 10),
                        "lookback_bars": params.get("lookback_bars", 160),
                        "top_k_features": params.get("top_k_features", 6),
                        "train_ratio": params.get("train_ratio", 0.7),
                        "include_alternative": params.get("include_alternative", True),
                        "alt_lookback_days": params.get("alt_lookback_days", 30),
                        "persist_artifact": False,
                        "run_anchor_oos": bool(_kw.get("run_anchor_oos", True)),
                    },
                )
                if not replay_action.get("success"):
                    return replay_action

                old_metrics = (payload.get("metrics") or {}) if isinstance(payload, dict) else {}
                new_metrics = replay_action.get("data", {}).get("metrics", {})
                metric_delta = {}
                for metric_name in ("test_ic", "hit_rate", "long_short_return"):
                    ov = _safe_float(old_metrics.get(metric_name), 0.0)
                    nv = _safe_float(new_metrics.get(metric_name), 0.0)
                    metric_delta[metric_name] = {"old": ov, "new": nv, "delta": float(nv - ov)}

                return _ok(
                    {
                        "artifact_id": artifact_id,
                        "replay_metrics": new_metrics,
                        "metric_delta": metric_delta,
                        "replay_result": replay_action.get("data"),
                    },
                    source_chain=["services.artifact_registry", "quant_manager.automl_discovery"],
                )

            elif action == "batch_compute_factors":
                # Batch compute and persist factor values + IC for multiple stocks
                codes = _kw.get("codes", [])
                if not isinstance(codes, list) or not codes:
                    return _fail("codes (list of stock codes) is required")
                factors = _kw.get("factors", ["momentum", "value", "quality", "growth"])
                persist = bool(_kw.get("persist", True))
                compute_ic = bool(_kw.get("compute_ic", True))
                period = int(_kw.get("period", 20) or 20)

                supported = {"momentum", "value", "quality", "growth", "volatility", "reversal"}
                unknown = [f for f in factors if f not in supported]
                if unknown:
                    return _fail(f"Unsupported factors for batch: {unknown}. Supported: {sorted(supported)}")

                db = get_db()
                results = {}
                errors = []
                persist_buffer = []
                today = datetime.now().date()

                for stock_code in codes[:200]:  # cap at 200
                    try:
                        klines = await db.get_klines(stock_code, limit=252)
                        if not klines:
                            klines_data = data_source.get_kline(stock_code, period="daily", limit=252)
                            klines = [
                                {"date": k.get("date"), "open": k.get("open"), "high": k.get("high"),
                                 "low": k.get("low"), "close": k.get("close"),
                                 "volume": k.get("volume"), "amount": k.get("amount", 0)}
                                for k in (klines_data or [])
                            ]
                        if not klines:
                            errors.append({"code": stock_code, "error": "no kline data"})
                            continue

                        ordered_klines = _sort_klines_ascending(klines)
                        closes = [k.get("close") for k in ordered_klines if isinstance(k, dict) and k.get("close") is not None]
                        if len(closes) < 20:
                            errors.append({"code": stock_code, "error": "insufficient data"})
                            continue

                        financials = await db.get_financials(stock_code, limit=8)
                        latest_fin = _select_financial_snapshot(financials)
                        valuation_snapshot = await _load_valuation_snapshot(db, stock_code)
                        fv = _compute_scalar_factor_bundle(
                            closes,
                            financial_snapshot=latest_fin,
                            valuation_snapshot=valuation_snapshot,
                            factors=factors,
                        )

                        results[stock_code] = fv

                        if persist and fv:
                            persist_buffer.append({
                                "stock_code": stock_code,
                                "factor_date": today,
                                "values": fv,
                            })
                    except Exception as e:
                        errors.append({"code": stock_code, "error": str(e)})

                if persist and persist_buffer:
                    try:
                        if hasattr(db, "save_factor_values_batch"):
                            await db.save_factor_values_batch(persist_buffer)
                        else:
                            for item in persist_buffer:
                                await db.save_factor_values(item["stock_code"], item["factor_date"], item["values"])
                    except Exception as exc:
                        logger.warning("batch_compute_factors persist batch failed, retrying row-wise: %s", exc)
                        for item in persist_buffer:
                            try:
                                await db.save_factor_values(item["stock_code"], item["factor_date"], item["values"])
                            except Exception as row_exc:
                                errors.append({"code": item["stock_code"], "error": f"persist failed: {row_exc}"})

                # Compute cross-sectional IC if requested
                # IC = corr(factor_value[t-period], return[t-period -> t])
                # We use lagged factor values paired with subsequent realized returns
                ic_results = {}
                if compute_ic and len(results) >= 10:
                    for fname in factors:
                        factor_vals = []
                        forward_rets = []
                        for stock_code, fv in results.items():
                            if fname not in fv:
                                continue
                            try:
                                klines = await db.get_klines(stock_code, limit=period + 60)
                                if not klines or len(klines) < period + 20:
                                    continue
                                ordered_klines = _sort_klines_ascending(klines)
                                closes = [float(k.get("close", 0) or 0) for k in ordered_klines]
                                # Lagged factor: compute factor from data ending period days ago
                                lagged_closes = closes[:-(period)]
                                if len(lagged_closes) < 20 or not lagged_closes[-20]:
                                    continue
                                lagged_date = _parse_date_value(ordered_klines[-(period + 1)].get("date"))
                                financials = await db.get_financials(stock_code, limit=8)
                                lagged_fin = _select_financial_snapshot(financials, as_of_date=lagged_date)
                                lagged_valuation = await _load_valuation_snapshot(db, stock_code, as_of_date=lagged_date)
                                lagged_bundle = _compute_scalar_factor_bundle(
                                    lagged_closes,
                                    financial_snapshot=lagged_fin,
                                    valuation_snapshot=lagged_valuation,
                                    factors=[fname],
                                )
                                if fname not in lagged_bundle:
                                    continue
                                lagged_fv = float(lagged_bundle[fname])
                                if fname in {"value", "quality", "growth"} and not lagged_fin:
                                    continue
                                if fname == "value" and not lagged_valuation:
                                    continue
                                # Forward return: from lagged point to now
                                c_lagged = closes[-(period + 1)]
                                c_now = closes[-1]
                                if c_lagged and c_now:
                                    factor_vals.append(lagged_fv)
                                    forward_rets.append((c_now - c_lagged) / c_lagged)
                            except Exception:
                                continue

                        if len(factor_vals) >= 10:
                            from ...services.factor_calculator.analysis import AnalysisFactorsMixin
                            ic_data = AnalysisFactorsMixin.calculate_factor_ic(factor_vals, forward_rets)
                            ic_val = ic_data.get("ic", 0.0)
                            rank_ic = ic_data.get("rank_ic", 0.0)
                            ic_results[fname] = {"ic": ic_val, "rank_ic": rank_ic, "sample_size": len(factor_vals)}
                            if persist:
                                await db.save_factor_ic(fname, str(period), today, ic_val, rank_ic, len(factor_vals))

                return _ok({
                    "computed_count": len(results),
                    "error_count": len(errors),
                    "errors": errors[:10],
                    "factors": factors,
                    "ic": ic_results,
                    "persisted": persist,
                }, source_chain=["db.get_klines", "db.save_factor_values", "db.save_factor_ic"])

            elif action == "factor_ic_history":
                factor_name = str(_kw.get("factor_name", "")).strip()
                period = str(_kw.get("period", "20"))
                limit = min(max(int(_kw.get("limit", 60)), 1), 500)
                if not factor_name:
                    return _fail("factor_name is required")
                db = get_db()
                rows = await db.get_factor_ic_history(factor_name, period, limit)
                return _ok({
                    "factor_name": factor_name,
                    "period": period,
                    "history": [
                        {
                            "date": str(r.get("ic_date", "")),
                            "ic_value": r.get("ic_value"),
                            "rank_ic": r.get("rank_ic"),
                            "stock_count": r.get("stock_count"),
                        }
                        for r in rows
                    ],
                    "count": len(rows),
                })

            elif action == "scheduler_status":
                from ...services.factor_scheduler import get_factor_scheduler
                scheduler = get_factor_scheduler()
                return _ok(scheduler.status())

            elif action == "scheduler_run_now":
                from ...services.factor_scheduler import get_factor_scheduler
                scheduler = get_factor_scheduler()
                result = await scheduler.run_once()
                return _ok(result or {"message": "run completed"})

            return _fail(
                "Unknown action: {action}. Supported: help, calculate_factors, alternative_factors, "
                "factor_ic, backtest_factor, multi_factor_score, llm_factor_mining, validate_factor_candidate, factor_research_memory, factor_candidate_registry, replay_factor_episode, automl_discovery, feature_store, "
                "replay_experiment, batch_compute_factors, factor_ic_history, scheduler_status, scheduler_run_now"
                .format(action=action)
            )
        except Exception as e:
            return _fail(str(e))


class _QuantManagerProbeMCP:
    """Minimal MCP stub used to expose the registered quant_manager as a module-level callable."""

    def __init__(self):
        self.fn = None

    def tool(self):
        def _decorator(fn):
            self.fn = fn
            return fn

        return _decorator


def _get_quant_manager_impl():
    global _QUANT_MANAGER_IMPL
    if _QUANT_MANAGER_IMPL is None:
        probe = _QuantManagerProbeMCP()
        register_quant_manager(probe)
        _QUANT_MANAGER_IMPL = probe.fn
    return _QUANT_MANAGER_IMPL


async def quant_manager(
    action: str,
    code: Optional[str] = None,
    kwargs: Any = None,
    params: Any = None,
    **extra_kwargs,
):
    """Module-level wrapper so internal services can import and call quant_manager directly."""

    impl = _get_quant_manager_impl()
    if impl is None:
        raise RuntimeError("quant_manager implementation is unavailable")
    merged_params = dict(params) if isinstance(params, dict) else {}
    if extra_kwargs:
        merged_params = {**extra_kwargs, **merged_params}
    resolved_params = merged_params if merged_params else params
    return await impl(action=action, code=code, kwargs=kwargs, params=resolved_params)
