"""Execution manager: TWAP/VWAP planning with lifecycle tracking and cost transparency."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ...utils import fail, ok, normalize_code
from .compliance_manager import evaluate_order_compliance
from ..risk_guard import audit_event


_EXECUTION_TASKS: dict[str, dict[str, Any]] = {}


_SOFT_GATE_PROFILES: dict[str, dict[str, float | int]] = {
    "conservative": {
        "max_order_shares": 500_000,
        "max_slice_shares": 100_000,
        "min_duration_minutes": 10,
        "max_cost_ratio": 0.003,
    },
    "balanced": {
        "max_order_shares": 1_000_000,
        "max_slice_shares": 200_000,
        "min_duration_minutes": 5,
        "max_cost_ratio": 0.005,
    },
    "aggressive": {
        "max_order_shares": 2_000_000,
        "max_slice_shares": 400_000,
        "min_duration_minutes": 3,
        "max_cost_ratio": 0.008,
    },
}

_SOFT_GATE_THRESHOLD_KEYS = (
    "max_order_shares",
    "max_slice_shares",
    "min_duration_minutes",
    "max_cost_ratio",
)


_SOFT_GATE_RUNTIME_CONFIG: dict[str, Any] = {
    "default_profile": "balanced",
    "default_threshold_overrides": {},
    "code_profiles": {},
}


def _apply_soft_gate_runtime_defaults(kwargs: dict) -> dict:
    """Apply runtime soft-gate defaults when request-level params are absent."""
    merged = dict(kwargs)
    code = str(merged.get("code") or "").strip()

    if merged.get("soft_gate_profile") is None:
        code_profiles = _SOFT_GATE_RUNTIME_CONFIG.get("code_profiles", {})
        if code and isinstance(code_profiles, dict) and code_profiles.get(code):
            merged["soft_gate_profile"] = code_profiles.get(code)
        else:
            merged["soft_gate_profile"] = _SOFT_GATE_RUNTIME_CONFIG.get("default_profile", "balanced")

    default_overrides = _SOFT_GATE_RUNTIME_CONFIG.get("default_threshold_overrides", {})
    if isinstance(default_overrides, dict):
        for key in _SOFT_GATE_THRESHOLD_KEYS:
            if merged.get(key) is None and default_overrides.get(key) is not None:
                merged[key] = default_overrides.get(key)

    return merged


def _soft_gate_config_view() -> dict:
    return {
        "default_profile": _SOFT_GATE_RUNTIME_CONFIG.get("default_profile", "balanced"),
        "default_threshold_overrides": dict(_SOFT_GATE_RUNTIME_CONFIG.get("default_threshold_overrides", {})),
        "code_profiles": dict(_SOFT_GATE_RUNTIME_CONFIG.get("code_profiles", {})),
    }





def _resolve_soft_gate_thresholds(kwargs: dict) -> dict:
    """Resolve soft gate thresholds by profile + per-request overrides."""
    kwargs = _apply_soft_gate_runtime_defaults(kwargs)
    profile = str(kwargs.get("soft_gate_profile", "balanced") or "balanced").strip().lower()
    if profile not in _SOFT_GATE_PROFILES:
        profile = "balanced"

    base = dict(_SOFT_GATE_PROFILES[profile])

    if kwargs.get("max_order_shares") is not None:
        base["max_order_shares"] = int(kwargs.get("max_order_shares") or base["max_order_shares"])
    if kwargs.get("max_slice_shares") is not None:
        base["max_slice_shares"] = int(kwargs.get("max_slice_shares") or base["max_slice_shares"])
    if kwargs.get("min_duration_minutes") is not None:
        base["min_duration_minutes"] = int(kwargs.get("min_duration_minutes") or base["min_duration_minutes"])
    if kwargs.get("max_cost_ratio") is not None:
        base["max_cost_ratio"] = float(kwargs.get("max_cost_ratio") or base["max_cost_ratio"])

    return {
        "profile": profile,
        "max_order_shares": int(base["max_order_shares"]),
        "max_slice_shares": int(base["max_slice_shares"]),
        "min_duration_minutes": int(base["min_duration_minutes"]),
        "max_cost_ratio": float(base["max_cost_ratio"]),
    }




def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_kwargs(kwargs: dict) -> dict:
    """Normalize kwargs, merge kwargs payload and keep backward-compatible aliases."""
    params = kwargs.get("params")
    if isinstance(params, dict):
        kwargs = {**kwargs, **params}
    raw = kwargs.get("kwargs")
    if isinstance(raw, dict):
        kwargs = {**kwargs, **raw}
    elif isinstance(raw, str):
        try:
            extra = json.loads(raw or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass

    if "code" not in kwargs or kwargs.get("code") is None:
        kwargs["code"] = kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")

    # Backward-compatible aliases
    if kwargs.get("total_shares") is None:
        kwargs["total_shares"] = kwargs.get("total_quantity") or kwargs.get("quantity")
    if kwargs.get("duration") is None:
        kwargs["duration"] = kwargs.get("duration_minutes") or kwargs.get("minutes")
    if kwargs.get("slices") is None and kwargs.get("slice_count") is not None:
        kwargs["slices"] = kwargs.get("slice_count")

    return kwargs


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _normalize_threshold_overrides(raw: dict) -> dict:
    normalized: dict[str, Any] = {}
    for key in _SOFT_GATE_THRESHOLD_KEYS:
        if raw.get(key) is None:
            continue
        if key == "max_cost_ratio":
            normalized[key] = float(raw.get(key))
        else:
            normalized[key] = int(raw.get(key))
    return normalized


def _warnings_by_severity(warnings: list[dict]) -> dict[str, int]:
    result = {"low": 0, "medium": 0, "high": 0}
    for warning in warnings:
        sev = str(warning.get("severity") or "").strip().lower()
        if sev in result:
            result[sev] += 1
    return result


def _warnings_by_profile(warnings: list[dict]) -> dict[str, int]:
    result: dict[str, int] = {}
    for warning in warnings:
        profile = str(warning.get("threshold_profile") or "unknown").strip().lower() or "unknown"
        result[profile] = result.get(profile, 0) + 1
    return result


def _merge_counter(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)


def _profile_distribution(tasks: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {"unknown": 0}
    for name in _SOFT_GATE_PROFILES.keys():
        dist[name] = 0
    for task in tasks:
        soft_gate = task.get("soft_gate") if isinstance(task.get("soft_gate"), dict) else {}
        profile = str(soft_gate.get("profile") or "unknown").strip().lower() or "unknown"
        if profile not in dist:
            dist[profile] = 0
        dist[profile] += 1
    return dist


def _set_config_result() -> dict:
    return {"soft_gate_config": _soft_gate_config_view()}


def _set_runtime_code_profiles(code_profiles: dict, merge: bool) -> tuple[bool, str | None]:
    current = _SOFT_GATE_RUNTIME_CONFIG.get("code_profiles", {}) if merge else {}
    if not isinstance(current, dict):
        current = {}
    new_map: dict[str, str] = dict(current)
    for code_key, profile_val in code_profiles.items():
        code = str(code_key or "").strip()
        if not code:
            continue
        if profile_val is None:
            new_map.pop(code, None)
            continue
        profile = str(profile_val).strip().lower()
        if profile not in _SOFT_GATE_PROFILES:
            return False, f"invalid profile for code {code}: {profile}"
        new_map[code] = profile
    _SOFT_GATE_RUNTIME_CONFIG["code_profiles"] = new_map
    return True, None


def _remove_runtime_code_profiles(codes: list[Any]) -> None:
    current = _SOFT_GATE_RUNTIME_CONFIG.get("code_profiles", {})
    if not isinstance(current, dict):
        current = {}
    new_map = dict(current)
    for item in codes:
        code = str(item or "").strip()
        if code:
            new_map.pop(code, None)
    _SOFT_GATE_RUNTIME_CONFIG["code_profiles"] = new_map


def _apply_default_threshold_overrides(overrides: dict, merge: bool) -> None:
    normalized = _normalize_threshold_overrides(overrides)
    if merge:
        current = _SOFT_GATE_RUNTIME_CONFIG.get("default_threshold_overrides", {})
        if not isinstance(current, dict):
            current = {}
        merged = dict(current)
        merged.update(normalized)
        _SOFT_GATE_RUNTIME_CONFIG["default_threshold_overrides"] = merged
    else:
        _SOFT_GATE_RUNTIME_CONFIG["default_threshold_overrides"] = normalized


def _remove_default_threshold_keys(keys: list[Any]) -> None:
    current = _SOFT_GATE_RUNTIME_CONFIG.get("default_threshold_overrides", {})
    if not isinstance(current, dict):
        current = {}
    new_map = dict(current)
    for item in keys:
        key = str(item or "").strip()
        if key in _SOFT_GATE_THRESHOLD_KEYS:
            new_map.pop(key, None)
    _SOFT_GATE_RUNTIME_CONFIG["default_threshold_overrides"] = new_map


def _set_config_impl(kwargs: dict) -> tuple[bool, str | None]:
    default_profile = kwargs.get("default_profile")
    if default_profile is not None:
        profile = str(default_profile).strip().lower()
        if profile not in _SOFT_GATE_PROFILES:
            return False, "default_profile must be one of conservative/balanced/aggressive"
        _SOFT_GATE_RUNTIME_CONFIG["default_profile"] = profile

    default_threshold_overrides = kwargs.get("default_threshold_overrides")
    merge_default_threshold_overrides = _to_bool(kwargs.get("merge_default_threshold_overrides"), default=False)
    if default_threshold_overrides is not None:
        if not isinstance(default_threshold_overrides, dict):
            return False, "default_threshold_overrides must be a dict"
        try:
            _apply_default_threshold_overrides(default_threshold_overrides, merge=merge_default_threshold_overrides)
        except Exception:
            return False, "default_threshold_overrides contains invalid threshold value"

    remove_default_threshold_keys = kwargs.get("remove_default_threshold_keys")
    if remove_default_threshold_keys is not None:
        if not isinstance(remove_default_threshold_keys, list):
            return False, "remove_default_threshold_keys must be a list"
        _remove_default_threshold_keys(remove_default_threshold_keys)

    code_profiles = kwargs.get("code_profiles")
    merge_code_profiles = _to_bool(kwargs.get("merge_code_profiles"), default=False)
    if code_profiles is not None:
        if not isinstance(code_profiles, dict):
            return False, "code_profiles must be a dict"
        ok_flag, err = _set_runtime_code_profiles(code_profiles, merge=merge_code_profiles)
        if not ok_flag:
            return False, err

    remove_code_profiles = kwargs.get("remove_code_profiles")
    if remove_code_profiles is not None:
        if not isinstance(remove_code_profiles, list):
            return False, "remove_code_profiles must be a list"
        _remove_runtime_code_profiles(remove_code_profiles)

    return True, None


def _summary_aggregates(tasks: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    estimated_total_cost = 0.0
    warning_count = 0
    high_severity_task_count = 0
    soft_gate_profile_distribution = _profile_distribution(tasks)
    warnings_by_profile: dict[str, int] = {}
    warnings_by_severity: dict[str, int] = {"low": 0, "medium": 0, "high": 0}

    for task in tasks:
        status = str(task.get("status", "unknown"))
        by_status[status] = by_status.get(status, 0) + 1
        estimated_total_cost += float(task.get("cost_model", {}).get("estimated", {}).get("total", 0.0))

        sg = task.get("soft_gate") if isinstance(task.get("soft_gate"), dict) else {}
        warnings = task.get("pretrade_warnings") if isinstance(task.get("pretrade_warnings"), list) else []
        warning_count += int(sg.get("warning_count", len(warnings)) or 0)
        if bool(sg.get("has_high_severity", False)):
            high_severity_task_count += 1

        _merge_counter(warnings_by_profile, _warnings_by_profile(warnings))
        _merge_counter(warnings_by_severity, _warnings_by_severity(warnings))

    return {
        "total_tasks": len(tasks),
        "by_status": by_status,
        "estimated_total_cost": float(estimated_total_cost),
        "warning_count": int(warning_count),
        "high_severity_task_count": int(high_severity_task_count),
        "soft_gate_profile_distribution": soft_gate_profile_distribution,
        "warnings_by_profile": warnings_by_profile,
        "warnings_by_severity": warnings_by_severity,
    }



def _append_event(task: dict, status: str, note: str, payload: dict | None = None) -> None:
    event = {
        "at": _now_iso(),
        "status": status,
        "note": note,
    }
    if payload:
        event["payload"] = payload
    task.setdefault("lifecycle", []).append(event)


def _refresh_task_status(task: dict) -> None:
    """Advance status by elapsed time to support lifecycle visibility."""
    status = task.get("status")
    if status in {"completed", "failed"}:
        return

    created_at = task.get("created_at")
    if not created_at:
        return

    try:
        created_dt = datetime.fromisoformat(created_at)
    except Exception:
        return

    elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds()
    duration_minutes = int(task.get("plan", {}).get("duration_minutes", 0) or 0)

    if status == "queued" and elapsed >= 1:
        task["status"] = "executing"
        _append_event(task, "executing", "task moved from queue to execution")
        status = "executing"

    if status == "executing" and duration_minutes > 0 and elapsed >= duration_minutes * 60:
        task["status"] = "completed"
        task["completed_at"] = _now_iso()
        _append_event(task, "completed", "task execution completed")


def _build_cost_model(kwargs: dict, total_shares: int) -> dict:
    """Build execution cost model via unified cost_model service."""
    from ...services.cost_model import build_cost_model

    reference_price = float(kwargs.get("reference_price", 0.0) or 0.0)
    notional = float(total_shares) * reference_price
    return build_cost_model(
        kwargs, notional=notional, default_mode="execution",
        reference_price_fallback=reference_price,
    )



def _enrich_kwargs_with_realtime(code: str, kwargs: dict) -> dict:
    """从实时行情自动填充 reference_price / avg_minute_volume（P1-c）。"""
    try:
        from ...data_source import data_source
        quote = data_source.get_realtime_quote(code)
        if not quote:
            return kwargs
        if not kwargs.get("reference_price"):
            price = quote.get("price")
            if price and float(price) > 0:
                kwargs["reference_price"] = float(price)
        if not kwargs.get("avg_minute_volume"):
            vol = quote.get("volume")
            if vol and float(vol) > 0:
                kwargs["avg_minute_volume"] = float(vol) / 240.0
                # 标记为自动填充，避免将实时估算值直接用于高等级参与率风控判定（防止噪声误报）
                kwargs["__auto_avg_minute_volume"] = True
    except Exception:
        pass
    return kwargs


def _build_soft_gate_warnings(
    kwargs: dict,
    total_shares: int,
    duration: int,
    slices: int,
    cost_model: dict,
) -> tuple[list[dict], dict]:
    """执行前置闸门（P1/P2 软校验）：仅告警不阻断，支持 profile 阈值策略。"""
    warnings: list[dict] = []
    thresholds = _resolve_soft_gate_thresholds(kwargs)

    reference_price = float(kwargs.get("reference_price", 0.0) or 0.0)
    if reference_price <= 0:
        warnings.append(
            {
                "type": "price_missing",
                "severity": "medium",
                "message": "reference_price 缺失或无效，成本估算可能偏差较大",
                "suggestion": "传入 reference_price 以提升费用与冲击成本估算准确性",
                "threshold_profile": thresholds["profile"],
            }
        )

    max_order_shares = int(thresholds["max_order_shares"])
    if total_shares > max_order_shares:
        warnings.append(
            {
                "type": "order_size_large",
                "severity": "high",
                "message": f"委托总量 {total_shares} 超过软阈值 {max_order_shares}",
                "suggestion": "考虑拆分为多批次执行或降低单次下单规模",
                "threshold_profile": thresholds["profile"],
            }
        )

    max_slice_shares = int(thresholds["max_slice_shares"])
    shares_per_slice = max(1, total_shares // max(1, slices))
    if shares_per_slice > max_slice_shares:
        warnings.append(
            {
                "type": "slice_too_large",
                "severity": "medium",
                "message": f"单片委托量 {shares_per_slice} 超过软阈值 {max_slice_shares}",
                "suggestion": "提高 slices 或拉长 duration_minutes，降低瞬时冲击",
                "threshold_profile": thresholds["profile"],
            }
        )

    min_duration_minutes = int(thresholds["min_duration_minutes"])
    if duration < min_duration_minutes:
        warnings.append(
            {
                "type": "duration_too_short",
                "severity": "medium",
                "message": f"执行时长 {duration} 分钟低于建议阈值 {min_duration_minutes} 分钟",
                "suggestion": "适当增加执行时长，平滑成交路径",
                "threshold_profile": thresholds["profile"],
            }
        )

    estimated = cost_model.get("estimated", {}) if isinstance(cost_model, dict) else {}
    notional = float(estimated.get("notional", 0.0) or 0.0)
    total_cost = float(estimated.get("total", 0.0) or 0.0)
    cost_ratio = (total_cost / notional) if notional > 0 else 0.0
    max_cost_ratio = float(thresholds["max_cost_ratio"])
    if notional > 0 and cost_ratio > max_cost_ratio:
        warnings.append(
            {
                "type": "cost_ratio_high",
                "severity": "medium",
                "message": f"预计总成本占比 {cost_ratio:.4%} 超过软阈值 {max_cost_ratio:.2%}",
                "suggestion": "可尝试降低冲击参数、增加执行时长或改用更细粒度切片",
                "threshold_profile": thresholds["profile"],
            }
        )

    market_session = str(kwargs.get("market_session") or "continuous").strip().lower()
    if market_session and market_session not in {"continuous", "normal", "intraday"}:
        warnings.append(
            {
                "type": "market_session_risk",
                "severity": "medium",
                "message": f"当前执行时段标识为 {market_session}，可能存在流动性与冲击成本风险",
                "suggestion": "优先在连续竞价主时段执行，或提高切片数量并延长执行时长",
                "threshold_profile": thresholds["profile"],
            }
        )

    avg_minute_volume_raw = kwargs.get("avg_minute_volume")
    auto_avg_minute_volume = bool(kwargs.get("__auto_avg_minute_volume", False))
    if avg_minute_volume_raw is not None:
        try:
            avg_minute_volume = float(avg_minute_volume_raw)
        except Exception:
            avg_minute_volume = 0.0
        if avg_minute_volume > 0:
            max_participation_rate = float(kwargs.get("max_participation_rate", 0.2) or 0.2)
            participation_rate = float(shares_per_slice) / avg_minute_volume
            if participation_rate > max_participation_rate:
                # 自动填充的成交量为估算值，避免直接触发高严重级别误报
                if auto_avg_minute_volume:
                    severity = "medium"
                else:
                    severity = "high" if participation_rate > max_participation_rate * 1.5 else "medium"
                warnings.append(
                    {
                        "type": "participation_rate_high",
                        "severity": severity,
                        "message": (
                            f"单片参与率 {participation_rate:.2%} 超过阈值 {max_participation_rate:.2%} "
                            f"(avg_minute_volume={int(avg_minute_volume)})"
                        ),
                        "suggestion": "降低单片下单量或延长执行时长，控制单位时间参与率",
                        "threshold_profile": thresholds["profile"],
                    }
                )

    top_of_book_volume_raw = kwargs.get("top_of_book_volume")
    if top_of_book_volume_raw is not None:
        try:
            top_of_book_volume = float(top_of_book_volume_raw)
        except Exception:
            top_of_book_volume = 0.0
        if top_of_book_volume > 0:
            max_top_book_ratio = float(kwargs.get("max_top_book_ratio", 0.3) or 0.3)
            top_book_ratio = float(shares_per_slice) / top_of_book_volume
            if top_book_ratio > max_top_book_ratio:
                severity = "high" if top_book_ratio > max_top_book_ratio * 2 else "medium"
                warnings.append(
                    {
                        "type": "top_book_impact_high",
                        "severity": severity,
                        "message": (
                            f"单片/盘口一档量比值 {top_book_ratio:.2f} 超过阈值 {max_top_book_ratio:.2f} "
                            f"(top_of_book_volume={int(top_of_book_volume)})"
                        ),
                        "suggestion": "降低单片委托量、增加切片，或等待盘口深度改善后执行",
                        "threshold_profile": thresholds["profile"],
                    }
                )

    return warnings, thresholds


def _run_pretrade_gate(
    code: str,
    direction: str,
    total_shares: int,
    kwargs: dict,
    soft_warnings: list[dict],
) -> dict:
    """执行前置闸门（硬闸门 + 软闸门合并）。

    硬闸门：调用 compliance_manager.evaluate_order_compliance，违规则阻断。
    软闸门：合并已有 soft_gate warnings，仅告警不阻断。
    审计：通过 risk_guard.audit_event 记录闸门决策。
    """
    price_raw = kwargs.get("reference_price") or kwargs.get("price")
    compliance = evaluate_order_compliance(code, direction, total_shares, price_raw)

    # 将合规 warnings 转为统一格式并合并到 soft_warnings
    for cw in compliance.get("warnings", []):
        soft_warnings.append({
            "type": "compliance_advisory",
            "severity": "low",
            "message": cw,
            "suggestion": "",
            "source": "compliance_manager",
        })

    # 执行管理语义：可通过拆单化解的限制类违规（数量/金额/买入手数）降级为软告警，不阻断任务创建
    violations = [str(v) for v in (compliance.get("violations", []) or [])]
    soft_violation_patterns = ("单笔数量超限", "单笔金额超限", "买入数量必须为")
    soft_violations: list[str] = []
    hard_violations: list[str] = []
    for v in violations:
        if any(p in v for p in soft_violation_patterns):
            soft_violations.append(v)
        else:
            hard_violations.append(v)

    for v in soft_violations:
        sev = "high" if ("单笔数量超限" in v or "单笔金额超限" in v) else "medium"
        soft_warnings.append({
            "type": "compliance_soft_limit",
            "severity": sev,
            "message": v,
            "suggestion": "建议通过拆单、延长执行时长或分批执行化解该限制",
            "source": "compliance_manager",
        })

    compliance_blocked = len(hard_violations) > 0

    gate_result = {
        "compliance_passed": not compliance_blocked,
        "compliance_blocked": compliance_blocked,
        "compliance_violations": hard_violations,
        "compliance_soft_violations": soft_violations,
        "compliance_checks": compliance.get("checks", {}),
        "order_amount": compliance.get("order_amount"),
    }

    # 审计记录
    audit_event(
        action=f"pretrade_gate:{direction}",
        params={"code": code, "direction": direction, "total_shares": total_shares,
                "price": price_raw},
        result={"compliance_passed": not compliance_blocked,
                "violations": hard_violations,
                "soft_warning_count": len(soft_warnings)},
        reason="blocked" if compliance_blocked else "passed",
    )

    return gate_result


def _task_brief(task: dict) -> dict:
    soft_gate = task.get("soft_gate") if isinstance(task.get("soft_gate"), dict) else {}
    warnings = task.get("pretrade_warnings") if isinstance(task.get("pretrade_warnings"), list) else []
    return {
        "task_id": task.get("task_id"),
        "artifact_id": task.get("artifact_id"),
        "algorithm": task.get("algorithm"),
        "code": task.get("code"),
        "status": task.get("status"),
        "created_at": task.get("created_at"),
        "total_shares": task.get("total_shares"),
        "duration_minutes": task.get("plan", {}).get("duration_minutes"),
        "soft_gate_profile": str(soft_gate.get("profile", "unknown") or "unknown"),
        "warning_count": int(soft_gate.get("warning_count", len(warnings)) or 0),
        "has_high_severity": bool(soft_gate.get("has_high_severity", False)),
    }


def _create_task(algorithm: str, code: str, total_shares: int, duration: int, slices: int, kwargs: dict) -> dict:
    task_id = f"exec_{uuid.uuid4().hex[:12]}"
    artifact_id = str(kwargs.get("artifact_id") or "").strip() or None
    cost_model = _build_cost_model(kwargs, total_shares)

    shares_per_slice = total_shares // slices if slices > 0 else total_shares
    remainder = total_shares - shares_per_slice * slices
    interval = max(1, duration // max(1, slices))

    task = {
        "task_id": task_id,
        "artifact_id": artifact_id,
        "algorithm": algorithm,
        "code": code,
        "status": "queued",
        "created_at": _now_iso(),
        "total_shares": int(total_shares),
        "total_quantity": int(total_shares),
        "plan": {
            "duration_minutes": int(duration),
            "duration": int(duration),
            "slices": int(slices),
            "shares_per_slice": int(shares_per_slice),
            "remainder_shares": int(remainder),
            "interval_minutes": int(interval),
        },
        "cost_model": cost_model,
        "lifecycle": [],
    }
    _append_event(task, "queued", "task created and queued")
    _EXECUTION_TASKS[task_id] = task
    return task


def register_execution_manager(mcp):
    """Register execution manager tool."""

    @mcp.tool()
    async def execution_manager(action: str, **kwargs):
        """
        Execution manager with unified action + kwargs protocol.
        Supports structured ``params`` in addition to legacy ``kwargs`` payloads.

        Actions:
        - help
        - get_config
        - set_config
        - twap
        - vwap
        - list
        - summary
        - update (optional manual status update)

        Args by action:
        - set_config:
          - default_profile(optional)
          - default_threshold_overrides(optional, dict)
          - merge_default_threshold_overrides(optional, bool, 默认 false)
          - remove_default_threshold_keys(optional, list[str])
          - code_profiles(optional, dict[code->profile|null])
          - merge_code_profiles(optional, bool, 默认 false)
          - remove_code_profiles(optional, list[str])
        - twap/vwap: code, total_shares|total_quantity, duration|duration_minutes,
          slices(optional), reference_price(optional), artifact_id(optional),
          soft_gate_profile(optional: conservative/balanced/aggressive, 默认 balanced),
          max_order_shares/max_slice_shares/min_duration_minutes/max_cost_ratio(optional, 软告警阈值，显式参数优先于 profile 默认值),
          market_session(optional, continuous/normal/intraday 为低风险；其他值触发时段风险告警),
          avg_minute_volume(optional, 配合 max_participation_rate 默认0.2 做参与率软告警),
          top_of_book_volume(optional, 配合 max_top_book_ratio 默认0.3 做盘口冲击软告警)
        - summary: task_id(optional)
        - update: task_id, status, note(optional)

        Return highlights:
        - get_config/set_config: 软闸门运行时配置快照（支持增量更新与删除）
        - twap/vwap: 额外返回 warnings(list) 与 soft_gate(dict, non-blocking, 含 profile/thresholds)
        - list: 每条任务摘要包含 warning_count/has_high_severity
        - summary: 支持查看任务级 warnings/soft_gate 或全局 warning 汇总（含 profile/severity 分布）

        Examples:
        - execution_manager(action="set_config", kwargs='{"default_profile":"balanced","code_profiles":{"600519":"conservative"}}')
        - execution_manager(action="set_config", kwargs='{"merge_code_profiles":true,"code_profiles":{"000001":"aggressive"}}')
        - execution_manager(action="set_config", kwargs='{"merge_code_profiles":true,"code_profiles":{"000001":null}}')
        - execution_manager(action="get_config", kwargs="{}")
        - execution_manager(action="twap", kwargs='{"code":"600519","total_quantity":1000,"duration_minutes":60,"artifact_id":"art_demo_001"}')
        - execution_manager(action="vwap", kwargs='{"code":"000001","total_quantity":1500000,"duration_minutes":3}')
        - execution_manager(action="list", kwargs="{}")
        - execution_manager(action="summary", kwargs='{"task_id":"exec_xxx"}')
        """
        try:
            kwargs = _normalize_kwargs(dict(kwargs))
            supported_actions = {
                "twap": "TWAP execution planning (time-weighted average price)",
                "vwap": "VWAP execution planning (volume-weighted average price)",
                "list": "list execution tasks with lifecycle status",
                "summary": "task or global summary, including cost assumptions",
                "update": "manual status update for simulation/reconciliation",
                "get_config": "get runtime soft-gate configuration",
                "set_config": "set runtime soft-gate configuration",
                "help": "show help information",
            }

            if action == "help":
                return ok({"supported_actions": supported_actions})

            if action == "get_config":
                return ok({"soft_gate_config": _soft_gate_config_view()})

            if action == "set_config":
                ok_flag, err = _set_config_impl(kwargs)
                if not ok_flag:
                    return fail(str(err))
                return ok(_set_config_result())

            if action in {"twap", "vwap"}:
                code = kwargs.get("code")
                total_shares = kwargs.get("total_shares")
                duration = kwargs.get("duration", 60)
                direction = str(kwargs.get("direction", "buy")).strip().lower()

                if not code:
                    return fail("code is required")
                if total_shares is None:
                    return fail("total_shares or total_quantity is required")

                try:
                    total_shares = int(total_shares)
                    duration = int(duration)
                except Exception:
                    return fail("total_shares and duration must be integers")

                if total_shares <= 0:
                    return fail("total_shares must be > 0")
                if duration <= 0:
                    return fail("duration must be > 0")

                if action == "twap":
                    slices = kwargs.get("slices")
                    slices = int(slices) if slices is not None else max(1, duration // 5)
                else:
                    slices = kwargs.get("slices")
                    slices = int(slices) if slices is not None else max(1, duration // 10)

                if slices <= 0:
                    slices = 1

                # --- P1-c: 实时行情自动填充 reference_price / avg_minute_volume ---
                _enrich_kwargs_with_realtime(str(code), kwargs)

                # --- 软闸门（soft gate）：阈值告警 ---
                # 先创建 task 以获取 cost_model，再做软闸门检查
                task = _create_task(action.upper(), str(code), total_shares, duration, slices, kwargs)

                warnings, thresholds = _build_soft_gate_warnings(
                    kwargs=kwargs,
                    total_shares=total_shares,
                    duration=duration,
                    slices=slices,
                    cost_model=task.get("cost_model", {}),
                )

                # --- 硬闸门（hard gate）：合规检查，违规阻断 ---
                gate = _run_pretrade_gate(
                    code=str(code),
                    direction=direction,
                    total_shares=total_shares,
                    kwargs=kwargs,
                    soft_warnings=warnings,
                )

                if gate["compliance_blocked"]:
                    # 合规违规 → 阻断，撤销已创建的 task
                    _EXECUTION_TASKS.pop(task["task_id"], None)
                    return fail(
                        f"合规闸门阻断: {'; '.join(gate['compliance_violations'])}",
                        data={
                            "code": str(code),
                            "direction": direction,
                            "total_shares": total_shares,
                            "compliance_gate": gate,
                            "soft_warnings": warnings,
                        },
                    )

                soft_gate = {
                    "enabled": True,
                    "blocking": False,
                    "profile": thresholds["profile"],
                    "thresholds": {
                        "max_order_shares": thresholds["max_order_shares"],
                        "max_slice_shares": thresholds["max_slice_shares"],
                        "min_duration_minutes": thresholds["min_duration_minutes"],
                        "max_cost_ratio": thresholds["max_cost_ratio"],
                    },
                    "warning_count": len(warnings),
                    "has_high_severity": any(w.get("severity") == "high" for w in warnings),
                }
                task["pretrade_warnings"] = warnings
                task["soft_gate"] = soft_gate
                task["compliance_gate"] = gate

                return ok(
                    {
                        "algorithm": task["algorithm"],
                        "task_id": task["task_id"],
                        "artifact_id": task.get("artifact_id"),
                        "code": task["code"],
                        "status": task["status"],
                        "total_shares": task["total_shares"],
                        "total_quantity": task["total_quantity"],
                        "duration": task["plan"]["duration"],
                        "duration_minutes": task["plan"]["duration_minutes"],
                        "slices": task["plan"]["slices"],
                        "shares_per_slice": task["plan"]["shares_per_slice"],
                        "interval": task["plan"]["interval_minutes"],
                        "remainder_shares": task["plan"]["remainder_shares"],
                        "cost_model": task["cost_model"],
                        "warnings": warnings,
                        "soft_gate": soft_gate,
                        "compliance_gate": gate,
                        "lifecycle": task["lifecycle"],
                    }
                )

            if action == "list":
                status_filter = str(kwargs.get("status", "")).strip().lower()
                tasks = list(_EXECUTION_TASKS.values())
                for task in tasks:
                    _refresh_task_status(task)

                if status_filter:
                    tasks = [t for t in tasks if str(t.get("status", "")).lower() == status_filter]

                pending = [_task_brief(t) for t in tasks if t.get("status") in {"queued", "executing"}]
                completed = [_task_brief(t) for t in tasks if t.get("status") in {"completed", "failed"}]

                if not tasks:
                    return ok(
                        {
                            "message": "no execution tasks",
                            "tasks": [],
                            "pending_orders": [],
                            "completed_orders": [],
                            "count": 0,
                        }
                    )

                return ok(
                    {
                        "tasks": [_task_brief(t) for t in tasks],
                        "count": len(tasks),
                        "pending_orders": pending,
                        "completed_orders": completed,
                    }
                )

            if action == "summary":
                task_id = kwargs.get("task_id")
                tasks = list(_EXECUTION_TASKS.values())
                for task in tasks:
                    _refresh_task_status(task)

                if task_id:
                    task = _EXECUTION_TASKS.get(str(task_id))
                    if not task:
                        return fail(f"task not found: {task_id}")

                    warnings = task.get("pretrade_warnings") if isinstance(task.get("pretrade_warnings"), list) else []
                    soft_gate = task.get("soft_gate") if isinstance(task.get("soft_gate"), dict) else {
                        "enabled": False,
                        "blocking": False,
                        "warning_count": len(warnings),
                        "has_high_severity": any(w.get("severity") == "high" for w in warnings),
                    }

                    return ok(
                        {
                            "task": task,
                            "lifecycle_count": len(task.get("lifecycle", [])),
                            "estimated_cost_total": float(task.get("cost_model", {}).get("estimated", {}).get("total", 0.0)),
                            "warnings": warnings,
                            "soft_gate": soft_gate,
                        }
                    )

                if not tasks:
                    return ok(
                        {
                            "total_tasks": 0,
                            "by_status": {},
                            "estimated_total_cost": 0.0,
                            "warning_count": 0,
                            "high_severity_task_count": 0,
                            "soft_gate_profile_distribution": _profile_distribution([]),
                            "warnings_by_profile": {},
                            "warnings_by_severity": {"low": 0, "medium": 0, "high": 0},
                        }
                    )

                return ok(_summary_aggregates(tasks))

            if action == "update":
                task_id = str(kwargs.get("task_id") or "").strip()
                new_status = str(kwargs.get("status") or "").strip().lower()
                note = str(kwargs.get("note") or "manual update")

                if not task_id:
                    return fail("task_id is required")
                if new_status not in {"queued", "executing", "completed", "failed"}:
                    return fail("status must be one of queued/executing/completed/failed")

                task = _EXECUTION_TASKS.get(task_id)
                if not task:
                    return fail(f"task not found: {task_id}")

                task["status"] = new_status
                if new_status in {"completed", "failed"}:
                    task["completed_at"] = _now_iso()
                _append_event(task, new_status, note)

                return ok({"task": task})

            return fail(f"Unknown action: {action}. Supported: {', '.join(supported_actions.keys())}")
        except Exception as e:
            return fail(str(e))
