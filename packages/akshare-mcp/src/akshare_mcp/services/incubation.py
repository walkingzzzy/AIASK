"""策略模拟盘孵化：账户绑定、信号下发、指标沉淀。"""


from __future__ import annotations

import inspect
import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from strategy_factory.api.semantic_contract import build_signal_evidence_records

from .trade_audit_writer import record_trade_fill_from_order_and_trade

logger = logging.getLogger(__name__)


def _safe_rules_dict(value) -> dict:
    """将 risk_rules 字段安全地转换为 dict，防止反复 json.dumps 造成多层嵌套。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}

DEFAULT_INCUBATION_CAPITAL = 100000.0
DEFAULT_INCUBATION_RULES = {
    'max_position_pct': 25.0,
    'max_drawdown_pct': 18.0,
    'stop_loss_pct': 8.0,
}


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


def _runtime_playbook_for_strategy(strategy: dict) -> dict:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    return dict(
        payload.get("runtime_playbook")
        or params.get("runtime_playbook")
        or {}
    )


def _runtime_execution_guard(strategy: dict) -> dict:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    instrument_profile = dict(
        payload.get("instrument_profile")
        or params.get("instrument_profile")
        or {}
    )
    measurement_source = str(
        instrument_profile.get("measurement_source") or "default_board_profile"
    ).strip().lower() or "default_board_profile"
    measured_profile_complete = bool(instrument_profile.get("measured_profile_complete"))
    target_symbols = list(
        payload.get("target_symbols")
        or params.get("target_symbols")
        or []
    )
    single_name_trend = strategy_type in {"ma_cross", "momentum", "volatility_breakout", "event_structure_breakout"} and len(target_symbols) == 1
    proxy_runtime_used = bool(payload.get("proxy_runtime_used") or params.get("proxy_runtime_used"))
    runtime_family_data_source = str(
        payload.get("runtime_family_data_source")
        or params.get("runtime_family_data_source")
        or (
            "price_proxy_runtime"
            if strategy_type in {"quality_factor", "value_factor", "growth_factor"}
            else "market_data_runtime"
        )
    ).strip().lower() or "market_data_runtime"
    if strategy_type in {"quality_factor", "value_factor", "growth_factor"} and runtime_family_data_source != "fundamental_runtime":
        proxy_runtime_used = True
    semantic_runtime_match = (
        bool(payload.get("semantic_runtime_match"))
        if payload.get("semantic_runtime_match") is not None
        else bool(params.get("semantic_runtime_match"))
        if params.get("semantic_runtime_match") is not None
        else not proxy_runtime_used
    )
    execution_readiness_tier = str(
        payload.get("execution_readiness_tier")
        or params.get("execution_readiness_tier")
        or ""
    ).strip().lower()
    default_profile_runtime_blocked = single_name_trend and (
        measurement_source == "default_board_profile" or not measured_profile_complete
    )
    diagnostic_only = bool(payload.get("diagnostic_only") or params.get("diagnostic_only"))
    semantic_contract_missing_fields = list(
        payload.get("semantic_contract_missing_fields")
        or params.get("semantic_contract_missing_fields")
        or []
    )
    if proxy_runtime_used or default_profile_runtime_blocked or semantic_contract_missing_fields:
        diagnostic_only = True
    if not execution_readiness_tier:
        execution_readiness_tier = (
            "observe_diagnostic_only"
            if diagnostic_only or proxy_runtime_used or default_profile_runtime_blocked
            else "formal_runtime_ready"
        )
    allow_signal_entries = (
        not diagnostic_only
        and not proxy_runtime_used
        and semantic_runtime_match
        and execution_readiness_tier == "formal_runtime_ready"
    )
    # observe 诊断性纸面交易闸门:打破"要证据才能 formal、但只有 formal 才准下单产证据"的死锁。
    # observe 样本(零资本模拟)允许下诊断纸面单以积累 forward returns / effective_n,
    # 但仅限结构合法的样本——契约缺字段等结构性损坏仍禁止。不改变 formal 资格判定。
    import os as _os
    observe_paper_enabled = str(
        _os.getenv("INCUBATION_OBSERVE_PAPER_ENTRIES_ENABLED", "1")
    ).strip().lower() in {"1", "true", "yes", "on"}
    allow_observe_paper_entries = (
        observe_paper_enabled
        and not allow_signal_entries  # formal 走正常通道,无需此档
        and not semantic_contract_missing_fields  # 结构性损坏不放行
    )
    reasons: list[str] = []
    if semantic_contract_missing_fields:
        reasons.append("final_strategy_missing_semantic_contract")
    if proxy_runtime_used:
        reasons.append("proxy_runtime_not_allowed_for_formal_incubation")
    if default_profile_runtime_blocked:
        reasons.append("default_profile_not_allowed_for_single_name_runtime")
    if diagnostic_only and not reasons:
        reasons.append("diagnostic_only")
    return {
        "allow_signal_entries": allow_signal_entries,
        "allow_observe_paper_entries": allow_observe_paper_entries,
        "diagnostic_only": diagnostic_only,
        "proxy_runtime_used": proxy_runtime_used,
        "semantic_runtime_match": semantic_runtime_match,
        "execution_readiness_tier": execution_readiness_tier,
        "runtime_family_data_source": runtime_family_data_source,
        "reasons": list(dict.fromkeys(reasons)),
    }


def _strategy_account_risk_rules(strategy: dict) -> dict:
    params = dict(dict(strategy or {}).get("params") or {})
    runtime_playbook = _runtime_playbook_for_strategy(strategy)
    exit_policy = dict(runtime_playbook.get("exit_policy") or {})
    position_policy = dict(runtime_playbook.get("position_policy") or {})
    risk_rules = _safe_rules_dict(
        dict(strategy or {}).get("risk_rules")
        or params.get("risk_rules")
        or {}
    )
    merged = dict(DEFAULT_INCUBATION_RULES)
    merged.update(risk_rules)
    stop_loss_pct = exit_policy.get("initial_stop_loss_pct")
    if stop_loss_pct is not None:
        merged["stop_loss_pct"] = round(_safe_float(stop_loss_pct, 0.08) * 100.0, 4)
    max_position_pct = position_policy.get("max_position_pct")
    if max_position_pct is not None:
        merged["max_position_pct"] = round(_safe_float(max_position_pct, 0.25) * 100.0, 4)
    return merged


def _parse_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_async_db_method(db, name: str):
    """Only treat explicitly provided async methods as adapter overrides.

    ``MagicMock``/``Mock`` synthesizes arbitrary attributes on access, so
    ``hasattr`` is too permissive here and can leak un-awaited child mocks
    into fallback branches during tests.
    """
    method = getattr(db, name, None)
    if method is None or not callable(method):
        return None
    if inspect.iscoroutinefunction(method):
        return method
    if hasattr(method, "await_count"):
        return method
    return None


def _get_db_acquire(db):
    """Return a real acquire() hook, not a lazily synthesized mock child."""
    acquire = getattr(db, "acquire", None)
    if not callable(acquire):
        return None

    raw = getattr(db, "raw", None)
    target = getattr(raw, "acquire", None) if raw is not None else acquire
    if target is None or not callable(target):
        return None
    if type(target).__module__.startswith("unittest.mock"):
        return None
    return acquire


def _build_signal_id(strategy_id: str, signal: dict, signal_date: date, code: str, direction: str) -> str:
    explicit = str(signal.get("signal_id") or signal.get("id") or "").strip()
    if explicit:
        return explicit
    seed = f"{strategy_id}:{signal_date}:{code}:{direction}"
    return f"sig_{uuid5(NAMESPACE_URL, seed).hex[:16]}"


def _build_position_id(strategy_id: str, account_id: str, code: str, signal_id: str) -> str:
    seed = f"{strategy_id}:{account_id}:{code}:{signal_id}:{uuid4().hex}"
    return f"pos_{uuid5(NAMESPACE_URL, seed).hex[:16]}"


def _resolve_strategy_target_codes(strategy: dict) -> set[str]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    ordered: list[str] = []
    seen: set[str] = set()
    filter_payloads: list[dict] = []

    def _push(value) -> None:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _push(item)
            return
        if isinstance(value, dict):
            for key in ("symbols", "target_symbols", "symbol", "stock_code", "code"):
                if key in value:
                    _push(value.get(key))
            return
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)

    def _collect_codes(value) -> list[str]:
        resolved_codes: list[str] = []
        local_seen: set[str] = set()

        def _visit(item) -> None:
            if isinstance(item, (list, tuple, set)):
                for entry in item:
                    _visit(entry)
                return
            if isinstance(item, dict):
                for key in (
                    "prioritized_symbols",
                    "preferred_symbols",
                    "universe_priority_symbols",
                    "excluded_symbols",
                    "symbols",
                    "target_symbols",
                    "symbol",
                    "stock_code",
                    "code",
                ):
                    if key in item:
                        _visit(item.get(key))
                return
            text = str(item or "").strip()
            if text and text not in local_seen:
                local_seen.add(text)
                resolved_codes.append(text)

        _visit(value)
        return resolved_codes

    for candidate in (
        payload.get("target_symbols"),
        payload.get("stock_pool"),
        payload.get("research_task"),
        params.get("target_symbols"),
        params.get("stock_pool"),
        params.get("research_task"),
        dict(params.get("dsl") or {}).get("metadata"),
    ):
        _push(candidate)
    for candidate in (
        payload.get("stock_pool"),
        payload.get("research_task"),
        params.get("stock_pool"),
        params.get("research_task"),
        dict(params.get("dsl") or {}).get("metadata"),
    ):
        if isinstance(candidate, dict):
            filters = dict(candidate.get("filters") or {})
            if filters:
                filter_payloads.append(filters)

    prioritized_symbols = _collect_codes(
        [
            params.get("prioritized_symbols"),
            params.get("preferred_symbols"),
            params.get("universe_priority_symbols"),
            [payload_.get("prioritized_symbols") for payload_ in filter_payloads],
            [payload_.get("preferred_symbols") for payload_ in filter_payloads],
            [payload_.get("universe_priority_symbols") for payload_ in filter_payloads],
        ]
    )
    excluded_symbols = set(
        _collect_codes(
            [
                params.get("excluded_symbols"),
                [payload_.get("excluded_symbols") for payload_ in filter_payloads],
            ]
        )
    )
    budget_candidates = [
        params.get("max_active_symbols"),
        *[payload_.get("max_active_symbols") for payload_ in filter_payloads],
    ]
    max_active_symbols = 0
    for raw_budget in budget_candidates:
        try:
            max_active_symbols = max(max_active_symbols, int(raw_budget or 0))
        except Exception:
            continue

    resolved = [code for code in ordered if code not in excluded_symbols]
    if prioritized_symbols:
        priority_order = [code for code in prioritized_symbols if code in resolved]
        remaining = [code for code in resolved if code not in set(priority_order)]
        resolved = [*priority_order, *remaining]
    if max_active_symbols > 0:
        resolved = resolved[:max_active_symbols]
    return set(resolved)


def _as_dict(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _dedup_strings(values) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _runtime_action_lineage(strategy: dict, reason: str) -> dict:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    runtime_playbook = _runtime_playbook_for_strategy(payload)
    runtime_provenance = dict(runtime_playbook.get("_provenance") or {})
    semantic_lineage = {
        "claim_to_trade_plan_map": _as_dict(
            payload.get("claim_to_trade_plan_map") or params.get("claim_to_trade_plan_map")
        ),
        "trade_plan_to_dsl_map": _as_dict(
            payload.get("trade_plan_to_dsl_map") or params.get("trade_plan_to_dsl_map")
        ),
    }
    claim_map = _as_dict(semantic_lineage["claim_to_trade_plan_map"])
    trade_map = _as_dict(semantic_lineage["trade_plan_to_dsl_map"])
    trade_step_to_claim_ids = _as_dict(claim_map.get("trade_step_to_claim_ids"))
    trade_step_sections = _as_dict(trade_map.get("trade_step_to_dsl_sections"))
    source_trade_step_ids = _dedup_strings(
        list(runtime_playbook.get("source_trade_step_ids") or [])
        + list(runtime_provenance.get("source_trade_step_ids") or [])
    )
    exit_trade_step_ids = _dedup_strings(
        [
            step_id
            for step_id, sections in trade_step_sections.items()
            if "exit" in [str(section).strip().lower() for section in list(sections or [])]
        ]
    )
    if source_trade_step_ids:
        exit_trade_step_ids = _dedup_strings(
            [step_id for step_id in source_trade_step_ids if step_id in set(exit_trade_step_ids)]
            or exit_trade_step_ids
            or source_trade_step_ids
        )

    normalized_reason = str(reason or "").strip().lower()
    runtime_action_reason = normalized_reason
    runtime_action_source = "unmapped_runtime_action"
    label_token = ""
    if normalized_reason == "runtime_playbook_stop_loss":
        runtime_action_reason = "stop_loss"
        runtime_action_source = "runtime_playbook.exit_policy.initial_stop_loss_pct"
    elif normalized_reason == "runtime_playbook_time_stop":
        runtime_action_reason = "time_stop"
        runtime_action_source = "runtime_playbook.exit_policy.time_stop_days"
    elif normalized_reason.startswith("runtime_playbook_"):
        label_token = normalized_reason.removeprefix("runtime_playbook_")
        loss_bands = list(_as_dict(runtime_playbook.get("adverse_move_policy")).get("loss_bands") or [])
        for index, item in enumerate(loss_bands):
            band = dict(item or {})
            band_label = str(band.get("label") or "").strip().lower()
            band_action = str(band.get("action") or "").strip().lower()
            if label_token not in {band_label, band_action}:
                continue
            runtime_action_reason = (
                "reduce"
                if band_action == "reduce"
                else "freeze_reentry"
                if band_action == "freeze_reentry"
                else "stop_loss"
            )
            runtime_action_source = (
                f"runtime_playbook.adverse_move_policy.loss_bands[{index}]"
                f".{band_label or band_action or 'band'}"
            )
            break

    def _token_set(value: str) -> set[str]:
        return {
            token
            for token in str(value or "").replace("-", "_").split("_")
            if token
        }

    match_tokens = _token_set(label_token or runtime_action_reason)
    candidate_trade_step_ids = list(exit_trade_step_ids)
    token_matches = [
        step_id
        for step_id in candidate_trade_step_ids
        if match_tokens and _token_set(step_id).intersection(match_tokens)
    ]
    if len(token_matches) == 1:
        applied_trade_step_id = token_matches[0]
    elif len(candidate_trade_step_ids) == 1:
        applied_trade_step_id = candidate_trade_step_ids[0]
    else:
        applied_trade_step_id = None

    claim_candidates = _dedup_strings(
        trade_step_to_claim_ids.get(applied_trade_step_id) or []
    ) if applied_trade_step_id else []
    applied_claim_id = claim_candidates[0] if len(claim_candidates) == 1 else None
    return {
        "applied_trade_step_id": applied_trade_step_id,
        "applied_claim_id": applied_claim_id,
        "runtime_action_reason": runtime_action_reason,
        "runtime_action_source": runtime_action_source,
        "lineage_status": "mapped_runtime_action" if applied_trade_step_id else "unmapped_runtime_action",
        "trade_step_candidates": candidate_trade_step_ids,
        "claim_candidates": claim_candidates,
    }


async def _find_open_trade_position(db, strategy_id: str, account_id: str, code: str) -> Optional[dict]:
    list_positions_method = _get_async_db_method(db, "list_strategy_trade_positions")
    if list_positions_method is None:
        return None
    rows = await list_positions_method(strategy_id=strategy_id, account_id=account_id, code=code, limit=20)
    for row in list(rows or []):
        status = str((row or {}).get("status") or "").strip().lower()
        if status in {"pending_entry", "open"}:
            return dict(row)
    return None


async def _save_trade_position_seed(db, payload: dict) -> Optional[dict]:
    save_method = _get_async_db_method(db, "save_strategy_trade_position")
    if save_method is None:
        return None
    return await save_method(payload)


async def _record_trade_audit_fill(db, order: dict, trade: dict) -> Optional[dict]:
    return await record_trade_fill_from_order_and_trade(
        db,
        order,
        trade,
        source="incubation_settlement",
    )


def _per_symbol_regime_enabled() -> bool:
    """P0-3: 是否对信号标的逐股推断 trend_regime / vol_regime。

    默认 OFF：保持历史行为（trend/vol 维度恒 "unknown"，仅 sentiment 由 fear_greed 推断）。
    ON：按标的最新 K 线推断 trend（MA20 斜率 + 20 日动量）与 vol（20 日已实现波动率分位）。
    """
    raw = os.getenv("STRATEGY_FACTORY_PER_SYMBOL_REGIME_ENABLED")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _infer_symbol_regime(closes: list[float]) -> dict:
    """从收盘价序列推断 trend_regime / vol_regime（自包含，无外部依赖）。

    返回的标签为消费侧（ForwardVerifier）按字符串分组的自由 token：
    - trend_regime: trend_up / trend_down / range
    - vol_regime:   high_vol / normal_vol / low_vol
    数据不足时对应维度返回 "unknown"（不阻断）。
    """
    labels = {"trend_regime": "unknown", "vol_regime": "unknown"}
    try:
        series = [float(c) for c in closes if c is not None and float(c) > 0]
    except (TypeError, ValueError):
        return labels
    n = len(series)
    if n < 20:
        return labels

    # ── trend：20 日动量 + MA20 斜率方向 ──
    ret_20 = (series[-1] - series[-20]) / series[-20] if series[-20] else 0.0
    ma20_now = sum(series[-20:]) / 20.0
    if n >= 25:
        ma20_prev = sum(series[-25:-5]) / 20.0
    else:
        ma20_prev = sum(series[:20]) / 20.0
    ma_slope = (ma20_now - ma20_prev) / ma20_prev if ma20_prev else 0.0
    if ret_20 > 0.05 and ma_slope > 0:
        labels["trend_regime"] = "trend_up"
    elif ret_20 < -0.05 and ma_slope < 0:
        labels["trend_regime"] = "trend_down"
    else:
        labels["trend_regime"] = "range"

    # ── vol：最近 20 日已实现年化波动率，按绝对阈值分档 ──
    window = series[-21:] if n >= 21 else series
    rets = [
        (window[i] - window[i - 1]) / window[i - 1]
        for i in range(1, len(window))
        if window[i - 1]
    ]
    if len(rets) >= 5:
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
        ann_vol = (var ** 0.5) * (252 ** 0.5)
        if ann_vol >= 0.45:
            labels["vol_regime"] = "high_vol"
        elif ann_vol <= 0.20:
            labels["vol_regime"] = "low_vol"
        else:
            labels["vol_regime"] = "normal_vol"
    return labels


async def _infer_symbol_regime_from_db(db, code: str) -> dict:
    """P0-3: 取标的最新 K 线并推断 trend/vol regime。任何异常都回退 unknown（不阻断）。"""
    labels = {"trend_regime": "unknown", "vol_regime": "unknown"}
    if not code:
        return labels
    try:
        get_klines = getattr(db, "get_klines", None)
        if get_klines is None:
            return labels
        klines = await get_klines(code, limit=60)
        if not klines:
            return labels
        # 统一为时间升序的收盘价序列
        rows = list(klines)
        try:
            rows.sort(key=lambda r: str((r or {}).get("date") or ""))
        except Exception:
            pass
        closes = [
            (r or {}).get("close")
            for r in rows
            if isinstance(r, dict) and (r or {}).get("close") is not None
        ]
        return _infer_symbol_regime(closes)
    except Exception:
        return labels


def _resolve_signal_regime(strategy: dict, regime: Optional[dict]) -> dict:
    """INVERT-DESIGN P1 改动D：解析信号当日市场状态标签。

    优先用显式传入的 regime；否则从策略快照的 fear_greed 推断 sentiment_regime。
    trend_regime / vol_regime 由调用方（_persist_signal_evidence，持有 db+code）逐标的推断后经
    regime 传入；未传入时缺省为 unknown。任何异常都不阻断信号落库。
    """
    labels = {"trend_regime": "unknown", "vol_regime": "unknown", "sentiment_regime": "unknown"}
    try:
        if regime:
            for key in labels:
                value = str(dict(regime).get(key) or "").strip().lower()
                if value:
                    labels[key] = value
        if labels["sentiment_regime"] == "unknown":
            payload = dict(strategy or {})
            params = dict(payload.get("params") or {})
            snapshot = dict(payload.get("snapshot") or params.get("snapshot") or {})
            fg = (
                snapshot.get("fear_greed_index")
                or snapshot.get("fear_greed")
                or payload.get("fear_greed_index")
                or params.get("fear_greed_index")
            )
            if fg is not None:
                try:
                    fg_val = float(fg)
                    labels["sentiment_regime"] = (
                        "fear" if fg_val < 30 else "greed" if fg_val > 70 else "neutral"
                    )
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return labels


async def _persist_signal_evidence(
    db,
    strategy: dict,
    *,
    signal_id: str,
    position_id: str,
    account_id: str,
    signal_date: date,
    code: str,
    regime: Optional[dict] = None,
) -> None:
    save_method = _get_async_db_method(db, "save_strategy_signal_evidence")
    if save_method is None:
        return
    # regime 缺省时由 _resolve_signal_regime 兜底（各维度 unknown），不阻断主流程。
    # P0-3: toggle ON 时，对信号标的逐股推断 trend/vol regime，合并进显式 regime（不覆盖已传入的非空值）。
    effective_regime = dict(regime or {})
    if _per_symbol_regime_enabled():
        inferred = await _infer_symbol_regime_from_db(db, code)
        for dim in ("trend_regime", "vol_regime"):
            existing = str(effective_regime.get(dim) or "").strip().lower()
            if existing in ("", "unknown") and inferred.get(dim) not in (None, "unknown"):
                effective_regime[dim] = inferred[dim]
    regime_labels = _resolve_signal_regime(strategy, effective_regime)
    for evidence in build_signal_evidence_records(
        strategy,
        signal_id=signal_id,
        position_id=position_id,
        account_id=account_id,
        signal_date=signal_date,
        code=code,
        regime=regime_labels,
    ):
        try:
            await save_method(
                {
                    "id": evidence.get("id") or f"{signal_id}:{evidence.get('evidence_id')}",
                    "signal_id": signal_id,
                    "strategy_id": strategy.get("id"),
                    "signal_date": signal_date,
                    "signal_ts": evidence.get("signal_ts"),
                    "code": code,
                    "candidate_artifact_id": evidence.get("candidate_artifact_id"),
                    "experiment_id": evidence.get("experiment_id"),
                    "evidence_id": evidence.get("evidence_id"),
                    "applied_claim_id": evidence.get("applied_claim_id"),
                    "applied_trade_step_id": evidence.get("applied_trade_step_id"),
                    "source_type": evidence.get("source_type") or evidence.get("evidence_type"),
                    "direction": evidence.get("direction"),
                    "horizon_days": evidence.get("horizon_days"),
                    "raw_confidence": evidence.get("raw_confidence"),
                    "calibrated_confidence": evidence.get("calibrated_confidence"),
                    "proxy_only": evidence.get("proxy_only"),
                    "doc_uid": evidence.get("doc_uid"),
                    "headline_label_id": evidence.get("headline_label_id"),
                    # 改动D：regime 标签随 payload(JSON) 落库，避免依赖表新增列；
                    # ForwardVerifier 从 evidence_payload 读取分 regime 聚合。
                    "payload": evidence.get("evidence_payload") or evidence,
                }
            )
        except Exception as exc:
            logger.warning(
                "StrategyIncubationService: save signal evidence failed for %s/%s: %s",
                strategy.get("id"),
                signal_id,
                exc,
            )


async def _persist_runtime_signal_evidence(
    db,
    strategy: dict,
    *,
    signal_id: str,
    position_id: str,
    account_id: str,
    signal_date: date,
    code: str,
    reason: str,
) -> None:
    save_method = _get_async_db_method(db, "save_strategy_signal_evidence")
    if save_method is None:
        return
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    lineage = _runtime_action_lineage(payload, reason)
    candidate_artifact_id = str(
        payload.get("candidate_artifact_id")
        or payload.get("source_candidate_artifact_id")
        or params.get("source_candidate_artifact_id")
        or payload.get("hypothesis_artifact_id")
        or params.get("hypothesis_artifact_id")
        or ""
    ).strip() or None
    experiment_id = str(payload.get("experiment_id") or params.get("experiment_id") or "").strip() or None
    evidence_id = f"runtime_action:{str(lineage.get('runtime_action_reason') or reason).strip().lower()}"
    runtime_payload = {
        "strategy_id": payload.get("id"),
        "signal_id": signal_id,
        "position_id": position_id,
        "account_id": account_id,
        "signal_date": str(signal_date),
        "code": code,
        "raw_reason": reason,
        "runtime_action_reason": lineage.get("runtime_action_reason"),
        "runtime_action_source": lineage.get("runtime_action_source"),
        "applied_claim_id": lineage.get("applied_claim_id"),
        "applied_trade_step_id": lineage.get("applied_trade_step_id"),
        "lineage_status": lineage.get("lineage_status"),
        "trade_step_candidates": lineage.get("trade_step_candidates") or [],
        "claim_candidates": lineage.get("claim_candidates") or [],
    }
    try:
        await save_method(
            {
                "id": (
                    f"{signal_id}:{evidence_id}:"
                    f"{str(lineage.get('applied_claim_id') or 'unclaimed').strip()}:"
                    f"{str(lineage.get('applied_trade_step_id') or 'unmapped_step').strip()}"
                ),
                "signal_id": signal_id,
                "strategy_id": payload.get("id"),
                "signal_date": signal_date,
                "signal_ts": datetime.combine(signal_date, datetime.min.time(), tzinfo=timezone.utc),
                "code": code,
                "candidate_artifact_id": candidate_artifact_id,
                "experiment_id": experiment_id,
                "evidence_id": evidence_id,
                "applied_claim_id": lineage.get("applied_claim_id"),
                "applied_trade_step_id": lineage.get("applied_trade_step_id"),
                "source_type": "runtime_playbook",
                "direction": "down",
                "runtime_action_reason": lineage.get("runtime_action_reason"),
                "runtime_action_source": lineage.get("runtime_action_source"),
                "payload": runtime_payload,
            }
        )
    except Exception as exc:
        logger.warning(
            "StrategyIncubationService: save runtime signal evidence failed for %s/%s: %s",
            payload.get("id"),
            signal_id,
            exc,
        )

from akshare_mcp._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'incubation_parts',
    'class StrategyIncubationService:\n',
    ['context.py', 'specs.py', 'runtime.py'],
    future_annotations=True,
)



_incubation_service: Optional[StrategyIncubationService] = None


def get_strategy_incubation_service() -> StrategyIncubationService:
    global _incubation_service
    if _incubation_service is None:
        _incubation_service = StrategyIncubationService()
    return _incubation_service
