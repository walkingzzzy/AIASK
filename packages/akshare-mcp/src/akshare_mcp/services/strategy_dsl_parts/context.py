
from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

import numpy as np
import pandas as pd
from strategy_factory.api.semantic_contract import (
    audit_candidate_semantic_contract,
    inspect_strategy_dsl_support,
)

SUPPORTED_DSL_VERSION = "1.0"
SUPPORTED_FIELDS = {"open", "high", "low", "close", "volume"}
SUPPORTED_INDICATORS = {
    "sma", "ema", "roc", "rsi", "stddev", "zscore",
    "highest", "lowest", "volume_ratio", "atr",
    "adx", "turnover_rate", "upper_shadow_ratio", "rolling_count", "slope",
}
SUPPORTED_COMPARE_OPS = {"gt", "gte", "lt", "lte", "eq", "ne", "cross_above", "cross_below"}
SUPPORTED_BINARY_OPS = {"add", "sub", "mul", "div", "max", "min"}


def _normalize_code_list(values: Any, limit: int = 12) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key in ("code", "symbol", "stock_code"):
                if value.get(key) is not None:
                    visit(value.get(key))
            for key in ("codes", "symbols", "stock_codes", "target_symbols"):
                if value.get(key) is not None:
                    visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        raw = str(value or "").strip()
        if not raw:
            return
        if any(sep in raw for sep in [",", ";", "|", "\n", "\t", " "]):
            normalized = raw.replace(";", ",").replace("|", ",").replace("\n", ",").replace("\t", ",").replace(" ", ",")
            for part in normalized.split(","):
                visit(part)
            return
        code = raw.split(".")[0].strip()
        if not code or code in seen:
            return
        seen.add(code)
        codes.append(code)

    visit(values)
    return codes[: max(1, min(int(limit or 12), 40))]


def _structured_payload(value: Any, *, field: str = "summary") -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value in (None, "", [], {}):
        return {}
    return {field: str(value)}


def _factory_contract_required(payload: dict[str, Any]) -> bool:
    return any(
        payload.get(key) not in (None, "", [], {})
        for key in ("research_task", "target_symbols", "stock_pool", "hypothesis", "holding_horizon", "tags", "rationale")
    )


def _is_event_blueprint(payload: dict[str, Any]) -> bool:
    research_task = dict(payload.get("research_task") or {})
    event_context = dict(payload.get("event_context") or {})
    return bool(
        str(research_task.get("task_source") or "").strip().lower() == "event_driven"
        or research_task.get("event_id")
        or research_task.get("theme_code")
        or event_context.get("event_id")
        or event_context.get("theme_code")
    )


def _requires_stock_pool_rationale(payload: dict[str, Any]) -> bool:
    research_task = dict(payload.get("research_task") or {})
    research_symbols = set(
        _normalize_code_list(
            [
                research_task.get("target_symbols"),
                research_task.get("stock_pool"),
                (research_task.get("event_context") or {}).get("target_symbols"),
            ],
            limit=16,
        )
    )
    if not research_symbols:
        return False
    candidate_symbols = set(
        _normalize_code_list(
            [
                payload.get("target_symbols"),
                payload.get("stock_pool"),
                ((payload.get("dsl") or {}).get("metadata") or {}).get("target_symbols"),
                ((payload.get("dsl") or {}).get("metadata") or {}).get("stock_pool"),
            ],
            limit=16,
        )
    )
    return bool(candidate_symbols and not candidate_symbols.issubset(research_symbols))


def _validate_factory_blueprint_contract(payload: dict[str, Any], normalized_dsl: Optional[dict[str, Any]] = None) -> None:
    if not _factory_contract_required(payload):
        return
    risk_rules = dict(payload.get("risk_rules") or (normalized_dsl or {}).get("risk_rules") or {})
    if not risk_rules:
        raise ValueError("factory blueprint requires dsl risk_rules")
    if _is_event_blueprint(payload) and not dict(payload.get("holding_horizon") or {}):
        raise ValueError("event factory blueprint requires holding_horizon")
    if _requires_stock_pool_rationale(payload):
        stock_pool = dict(payload.get("stock_pool") or {})
        if not str(stock_pool.get("rationale") or "").strip():
            raise ValueError("expanded factory stock_pool requires rationale")


def build_ohlcv_frame(klines: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(klines or []))
    if frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    aliases = {
        "open": ["open", "开盘"],
        "high": ["high", "最高"],
        "low": ["low", "最低"],
        "close": ["close", "收盘", "close_price"],
        "volume": ["volume", "vol", "成交量"],
    }
    normalized = pd.DataFrame(index=frame.index)
    lower_map = {str(column).lower(): str(column) for column in frame.columns}
    for target, options in aliases.items():
        source = None
        for alias in options:
            source = lower_map.get(str(alias).lower())
            if source is not None:
                break
        if source is not None:
            normalized[target] = pd.to_numeric(frame[source], errors="coerce")
    if "close" not in normalized:
        normalized["close"] = 0.0
    normalized["open"] = normalized.get("open", normalized["close"]).fillna(normalized["close"])
    normalized["high"] = normalized.get("high", normalized["close"]).fillna(normalized["close"])
    normalized["low"] = normalized.get("low", normalized["close"]).fillna(normalized["close"])
    normalized["volume"] = normalized.get("volume", 0.0).fillna(0.0)
    if "turnover_rate" in frame.columns:
        normalized["turnover_rate"] = pd.to_numeric(frame["turnover_rate"], errors="coerce")
    elif "turnover" in frame.columns:
        normalized["turnover_rate"] = pd.to_numeric(frame["turnover"], errors="coerce")
    return normalized.astype(float)


def build_close_volume_frame(closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> pd.DataFrame:
    close_arr = np.asarray([] if closes is None else closes, dtype=float)
    volume_arr = np.asarray(volumes if volumes is not None else np.zeros(len(close_arr)), dtype=float)
    if len(volume_arr) != len(close_arr):
        volume_arr = np.resize(volume_arr, len(close_arr)) if len(close_arr) else np.array([], dtype=float)
    frame = pd.DataFrame({
        "open": close_arr,
        "high": close_arr,
        "low": close_arr,
        "close": close_arr,
        "volume": volume_arr,
        "turnover_rate": np.zeros(len(close_arr), dtype=float),
    })
    return frame.astype(float)


def normalize_strategy_dsl(dsl: dict[str, Any]) -> dict[str, Any]:
    payload = dict(dsl or {})
    entry_payload = payload.get("entry")
    exit_payload = payload.get("exit")
    signals_payload = dict(payload.get("signals") or {})
    if not entry_payload and isinstance(signals_payload, dict):
        entry_payload = _coerce_open_dsl_signal(signals_payload.get("entry"))
    if not exit_payload and isinstance(signals_payload, dict):
        exit_payload = _coerce_open_dsl_signal(signals_payload.get("exit"))
    entry = _normalize_condition(_coerce_open_dsl_signal(entry_payload))
    if not entry:
        raise ValueError("dsl.entry is required")
    exit_rule = _normalize_condition(_coerce_open_dsl_signal(exit_payload) or {
        "any": [{
            "op": "cross_below",
            "left": {"indicator": "sma", "field": "close", "window": 5},
            "right": {"indicator": "sma", "field": "close", "window": 20},
        }],
    })
    return {
        "version": str(payload.get("version") or SUPPORTED_DSL_VERSION),
        "timeframe": str(payload.get("timeframe") or "daily"),
        "entry": entry,
        "exit": exit_rule,
        "metadata": dict(payload.get("metadata") or {}),
        "risk_rules": dict(payload.get("risk_rules") or {}),
    }


def _coerce_open_dsl_signal(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    op = str(node.get("op") or "").strip().lower()
    conditions = list(node.get("conditions") or [])
    if op in {"all", "any"} and conditions:
        return {
            op: [
                _normalize_condition(dict(item or {}))
                for item in conditions
                if _normalize_condition(dict(item or {}))
            ]
        }
    return dict(node)


def _normalize_claims_for_mapping(prediction_contract: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for item in list(dict(prediction_contract or {}).get("claims") or []):
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or item.get("id") or "").strip()
        if not claim_id:
            continue
        claims.append(
            {
                **item,
                "claim_id": claim_id,
                "evidence_ids": [str(value).strip() for value in list(item.get("evidence_ids") or []) if str(value).strip()],
            }
        )
    return claims


def _normalize_trade_plan_nodes_for_mapping(trade_plan: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def _append(node: Any, *, phase: str, index: int = 0) -> None:
        if not isinstance(node, dict):
            return
        node_id = str(
            node.get("node_id")
            or node.get("plan_node_id")
            or node.get("trade_plan_node_id")
            or node.get("trade_plan_step_id")
            or node.get("id")
            or f"{phase}_{index}"
        ).strip()
        claim_ids = [str(item).strip() for item in list(node.get("claim_ids") or []) if str(item).strip()]
        nodes.append(
            {
                **node,
                "node_id": node_id,
                "phase": phase,
                "claim_ids": list(dict.fromkeys(claim_ids)),
            }
        )

    payload = dict(trade_plan or {})
    if isinstance(payload.get("entry"), dict):
        _append(payload.get("entry"), phase="entry")
    if isinstance(payload.get("exit"), dict):
        _append(payload.get("exit"), phase="exit")
    for phase_name in ("entries", "exits", "nodes", "steps"):
        for index, item in enumerate(list(payload.get(phase_name) or [])):
            resolved_phase = "entry" if phase_name == "entries" else "exit" if phase_name == "exits" else phase_name
            _append(item, phase=resolved_phase, index=index)
    if not nodes and payload:
        _append(payload, phase="node")
    return nodes


def _collect_trade_plan_refs_from_dsl(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key in (
            "trade_plan_node_id",
            "trade_plan_step_id",
            "plan_node_id",
            "mapped_trade_plan_node_id",
            "node_id",
        ):
            token = str(value.get(key) or "").strip()
            if token:
                refs.append(token)
        for child in value.values():
            refs.extend(_collect_trade_plan_refs_from_dsl(child))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_collect_trade_plan_refs_from_dsl(item))
    return list(dict.fromkeys(refs))


def _build_claim_to_trade_plan_map(
    *,
    prediction_contract: dict[str, Any],
    trade_plan: dict[str, Any],
) -> dict[str, Any]:
    claims = _normalize_claims_for_mapping(prediction_contract)
    trade_plan_nodes = _normalize_trade_plan_nodes_for_mapping(trade_plan)
    claim_to_trade_step_ids: dict[str, list[str]] = {}
    trade_step_to_claim_ids: dict[str, list[str]] = {}
    for node in trade_plan_nodes:
        node_id = str(node.get("node_id") or "").strip()
        node_claim_ids = [str(item).strip() for item in list(node.get("claim_ids") or []) if str(item).strip()]
        if not node_id:
            continue
        trade_step_to_claim_ids[node_id] = list(dict.fromkeys(node_claim_ids))
        for claim_id in node_claim_ids:
            claim_to_trade_step_ids.setdefault(claim_id, []).append(node_id)
    claim_ids = [str(item.get("claim_id") or "").strip() for item in claims if str(item.get("claim_id") or "").strip()]
    for claim_id in claim_ids:
        claim_to_trade_step_ids.setdefault(claim_id, [])
    return {
        "claim_to_trade_step_ids": {
            key: list(dict.fromkeys(value))
            for key, value in claim_to_trade_step_ids.items()
        },
        "trade_step_to_claim_ids": trade_step_to_claim_ids,
        "mapped_claim_count": sum(1 for value in claim_to_trade_step_ids.values() if value),
        "unmapped_claim_ids": [key for key, value in claim_to_trade_step_ids.items() if not value],
        "trade_step_count": len(trade_step_to_claim_ids),
    }


def _build_trade_plan_to_dsl_map(
    *,
    trade_plan: dict[str, Any],
    dsl: dict[str, Any],
) -> dict[str, Any]:
    trade_plan_nodes = _normalize_trade_plan_nodes_for_mapping(trade_plan)
    entry_refs = set(_collect_trade_plan_refs_from_dsl(dict(dsl or {}).get("entry")))
    exit_refs = set(_collect_trade_plan_refs_from_dsl(dict(dsl or {}).get("exit")))
    trade_step_to_dsl_sections: dict[str, list[str]] = {}
    for node in trade_plan_nodes:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            continue
        sections: list[str] = []
        phase = str(node.get("phase") or "").strip().lower()
        if node_id in entry_refs or (phase == "entry" and isinstance(trade_plan.get("entry"), dict)):
            sections.append("entry")
        if node_id in exit_refs or (phase == "exit" and isinstance(trade_plan.get("exit"), dict)):
            sections.append("exit")
        trade_step_to_dsl_sections[node_id] = sections
    return {
        "trade_step_to_dsl_sections": trade_step_to_dsl_sections,
        "dsl_entry_trade_step_ids": sorted(entry_refs),
        "dsl_exit_trade_step_ids": sorted(exit_refs),
        "mapped_trade_step_count": sum(1 for value in trade_step_to_dsl_sections.values() if value),
        "unmapped_trade_step_ids": [key for key, value in trade_step_to_dsl_sections.items() if not value],
    }


def _build_semantic_contract_bundle(
    *,
    payload: dict[str, Any],
    dsl: dict[str, Any],
    dsl_support_audit: dict[str, Any],
    claim_to_trade_plan_map: dict[str, Any],
    trade_plan_to_dsl_map: dict[str, Any],
) -> dict[str, Any]:
    candidate = {
        **dict(payload or {}),
        "dsl": dict(dsl or {}),
        "dsl_support_audit": dict(dsl_support_audit or {}),
        "claim_to_trade_plan_map": dict(claim_to_trade_plan_map or {}),
        "trade_plan_to_dsl_map": dict(trade_plan_to_dsl_map or {}),
    }
    audit = dict(audit_candidate_semantic_contract(candidate) or {})
    return {
        "evidence_alignment_audit": audit,
        "evidence_alignment_score": float(audit.get("evidence_alignment_score") or 0.0),
        "semantic_integrity_score": float(audit.get("semantic_integrity_score") or 0.0),
        "hard_fail_reasons": [
            str(item).strip()
            for item in list(audit.get("hard_fail_reasons") or [])
            if str(item).strip()
        ],
    }


def compile_strategy_blueprint(
    blueprint: dict[str, Any],
    market_frame: Optional[pd.DataFrame] = None,
    tune_for_factory: bool = False,
) -> dict[str, Any]:
    payload = dict(blueprint or {})
    dsl_support_audit = inspect_strategy_dsl_support(payload.get("dsl") or payload)
    trade_plan = dict(payload.get("trade_plan") or {})
    prediction_contract = dict(payload.get("prediction_contract") or {})
    claim_to_trade_plan_map = _build_claim_to_trade_plan_map(
        prediction_contract=prediction_contract,
        trade_plan=trade_plan,
    )
    if payload.get("dsl") or payload.get("entry"):
        dsl = payload.get("dsl") or {
            "version": payload.get("version"),
            "timeframe": payload.get("timeframe"),
            "entry": payload.get("entry"),
            "exit": payload.get("exit"),
            "metadata": payload.get("metadata") or {},
            "risk_rules": payload.get("risk_rules") or {},
        }
        normalized = normalize_strategy_dsl(dsl)
        if tune_for_factory:
            _validate_factory_blueprint_contract(payload, normalized)
        tuning = {
            "applied": False,
            "selected_variant": "original",
            "before": summarize_dsl_activity(market_frame, normalized),
            "after": summarize_dsl_activity(market_frame, normalized),
            "variants_evaluated": 1,
        }
        if tune_for_factory and market_frame is not None and not market_frame.empty:
            normalized, tuning = tune_strategy_dsl(normalized, market_frame)
        risk_rules = dict(payload.get("risk_rules") or normalized.get("risk_rules") or {})
        trade_plan_to_dsl_map = _build_trade_plan_to_dsl_map(
            trade_plan=trade_plan,
            dsl=normalized,
        )
        semantic_contract_bundle = _build_semantic_contract_bundle(
            payload=payload,
            dsl=normalized,
            dsl_support_audit=dsl_support_audit,
            claim_to_trade_plan_map=claim_to_trade_plan_map,
            trade_plan_to_dsl_map=trade_plan_to_dsl_map,
        )
        compile_failure_reasons = []
        if int(dsl_support_audit.get("unsupported_rule_count") or 0) > 0:
            compile_failure_reasons.append("dsl_contains_unsupported_rules")
        if semantic_contract_bundle["hard_fail_reasons"]:
            compile_failure_reasons.extend(
                [
                    reason
                    for reason in list(semantic_contract_bundle["hard_fail_reasons"])
                    if reason not in compile_failure_reasons
                ]
            )
        return {
            "strategy_type": "dsl_rule",
            "params": {
                "dsl": normalized,
                "risk_rules": risk_rules,
            },
            "name": str(payload.get("name") or "外部 AI DSL 策略"),
            "description": str(payload.get("description") or payload.get("rationale") or "外部 AI 生成的 DSL 策略"),
            "tags": list(dict.fromkeys(list(payload.get("tags") or []) + ["dsl_rule"])),
            "metadata": {
                "rationale": payload.get("rationale"),
                "hypothesis": payload.get("hypothesis"),
                "holding_horizon": dict(payload.get("holding_horizon") or {}),
                "trade_plan": _structured_payload(payload.get("trade_plan")),
                "risk_rules": risk_rules,
                "position_sizing": _structured_payload(payload.get("position_sizing")),
                "execution_notes": payload.get("execution_notes"),
                "stock_pool": dict(payload.get("stock_pool") or {}),
                "target_symbols": list(_normalize_code_list(payload.get("target_symbols"), limit=12)),
                "dsl": normalized,
                "dsl_tuning": tuning,
                "dsl_activity": tuning.get("after") or summarize_dsl_activity(market_frame, normalized),
                "dsl_support_audit": dsl_support_audit,
                "claim_to_trade_plan_map": claim_to_trade_plan_map,
                "trade_plan_to_dsl_map": trade_plan_to_dsl_map,
                "evidence_alignment_audit": semantic_contract_bundle["evidence_alignment_audit"],
                "evidence_alignment_score": semantic_contract_bundle["evidence_alignment_score"],
                "semantic_integrity_score": semantic_contract_bundle["semantic_integrity_score"],
                "hard_fail_reasons": semantic_contract_bundle["hard_fail_reasons"],
                "unsupported_rule_count": int(dsl_support_audit.get("unsupported_rule_count") or 0),
                "compile_failure_reasons": compile_failure_reasons,
            },
        }

    strategy_type = str(payload.get("strategy_type") or "").strip()
    params = dict(payload.get("params") or {})
    if not strategy_type or not params:
        raise ValueError("strategy blueprint must contain dsl or strategy_type+params")
    if tune_for_factory:
        _validate_factory_blueprint_contract(payload)
    semantic_contract_bundle = _build_semantic_contract_bundle(
        payload=payload,
        dsl=dict(payload.get("dsl") or {}),
        dsl_support_audit=dsl_support_audit,
        claim_to_trade_plan_map=claim_to_trade_plan_map,
        trade_plan_to_dsl_map={},
    )
    return {
        "strategy_type": strategy_type,
        "params": params,
        "name": str(payload.get("name") or f"外部 AI {strategy_type} 策略"),
        "description": str(payload.get("description") or payload.get("rationale") or "外部 AI 生成策略"),
        "tags": list(payload.get("tags") or []),
        "metadata": {
            "rationale": payload.get("rationale"),
            "hypothesis": payload.get("hypothesis"),
            "holding_horizon": dict(payload.get("holding_horizon") or {}),
            "trade_plan": _structured_payload(payload.get("trade_plan")),
            "risk_rules": dict(payload.get("risk_rules") or {}),
            "position_sizing": _structured_payload(payload.get("position_sizing")),
            "execution_notes": payload.get("execution_notes"),
            "stock_pool": dict(payload.get("stock_pool") or {}),
            "target_symbols": list(_normalize_code_list(payload.get("target_symbols"), limit=12)),
            "dsl_support_audit": dsl_support_audit,
            "claim_to_trade_plan_map": claim_to_trade_plan_map,
            "trade_plan_to_dsl_map": {},
            "evidence_alignment_audit": semantic_contract_bundle["evidence_alignment_audit"],
            "evidence_alignment_score": semantic_contract_bundle["evidence_alignment_score"],
            "semantic_integrity_score": semantic_contract_bundle["semantic_integrity_score"],
            "hard_fail_reasons": semantic_contract_bundle["hard_fail_reasons"],
            "unsupported_rule_count": int(dsl_support_audit.get("unsupported_rule_count") or 0),
            "compile_failure_reasons": list(semantic_contract_bundle["hard_fail_reasons"]),
        },
    }


def evaluate_dsl_masks(frame: pd.DataFrame, dsl: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    normalized = normalize_strategy_dsl(dsl)
    entry_mask = _eval_condition(frame, normalized["entry"]).fillna(False).to_numpy(dtype=bool)
    exit_mask = _eval_condition(frame, normalized["exit"]).fillna(False).to_numpy(dtype=bool)
    return entry_mask, exit_mask


def summarize_dsl_activity(frame: Optional[pd.DataFrame], dsl: dict[str, Any]) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {
            "entry_count": 0,
            "exit_count": 0,
            "active_days": 0,
            "overlap_count": 0,
            "score": 0.0,
        }
    normalized = normalize_strategy_dsl(dsl)
    entry_mask, exit_mask = evaluate_dsl_masks(frame, normalized)
    overlap = entry_mask & exit_mask
    entry_count = int(np.count_nonzero(entry_mask))
    exit_count = int(np.count_nonzero(exit_mask))
    active_days = int(np.count_nonzero(entry_mask | exit_mask))
    overlap_count = int(np.count_nonzero(overlap))
    return {
        "entry_count": entry_count,
        "exit_count": exit_count,
        "active_days": active_days,
        "overlap_count": overlap_count,
        "score": round(_dsl_activity_score(entry_count, exit_count, active_days, overlap_count), 4),
    }
