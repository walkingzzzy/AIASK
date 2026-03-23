"""策略工厂面板、验证与风险报告。"""

from __future__ import annotations

from typing import List

import numpy as np

from ..domain.targets import _resolve_strategy_sample_codes
from ..infrastructure.mcp_services import (
    get_normalize_klines,
    get_risk_model_class,
    get_strategy_registry,
    get_validation_runtime,
)


def _generate_strategy_signal_series(klass, params: dict, closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    instance = klass()
    instance.set_parameters(params or {})
    try:
        signals = np.asarray(instance.generate_signals(closes, volumes), dtype=np.float64)
    except TypeError:
        signals = np.asarray(instance.generate_signals(closes), dtype=np.float64)
    return signals


def _build_family_returns(
    klass,
    params: dict,
    close_histories: List[np.ndarray],
    volume_histories: List[np.ndarray],
    *,
    min_len: int,
) -> np.ndarray | None:
    if min_len < 24 or not close_histories:
        return None

    def _series_for(candidate_params: dict) -> np.ndarray | None:
        family_columns: List[np.ndarray] = []
        for closes, volumes in zip(close_histories, volume_histories):
            if len(closes) < min_len + 1:
                continue
            signals = _generate_strategy_signal_series(klass, candidate_params, closes, volumes)
            aligned_signals = signals[:-1]
            aligned_returns = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
            if len(aligned_signals) < min_len or len(aligned_returns) < min_len:
                continue
            family_columns.append((aligned_signals[-min_len:] * aligned_returns[-min_len:]).astype(np.float64))
        if not family_columns:
            return None
        return np.mean(np.column_stack(family_columns), axis=1)

    series_family: List[np.ndarray] = []
    base = _series_for(dict(params or {}))
    if base is None:
        return None
    series_family.append(base)

    for key, value in sorted((params or {}).items()):
        if not isinstance(value, (int, float)) or value == 0:
            continue
        for mult in (0.8, 1.2):
            varied = dict(params or {})
            varied_value = float(value) * mult
            if isinstance(value, int):
                varied[key] = max(1, int(round(varied_value)))
            else:
                varied[key] = float(varied_value)
            candidate = _series_for(varied)
            if candidate is None:
                continue
            if any(np.allclose(candidate, existing, atol=1e-9, rtol=1e-6) for existing in series_family):
                continue
            series_family.append(candidate)

    return np.column_stack(series_family) if series_family else None


async def _build_strategy_panels(strategy_type: str, params: dict, db, sample_size: int = 6) -> dict:
    strategy_registry = get_strategy_registry()
    normalize_klines = get_normalize_klines()
    klass = strategy_registry.get(strategy_type)
    if klass is None:
        return {}
    factor_columns: List[np.ndarray] = []
    return_columns: List[np.ndarray] = []
    strategy_series: List[np.ndarray] = []
    close_histories: List[np.ndarray] = []
    volume_histories: List[np.ndarray] = []
    holdings: List[dict] = []
    sample_codes = _resolve_strategy_sample_codes(strategy_type, params, sample_size=sample_size)
    for code in sample_codes:
        try:
            klines = await db.get_klines(code, limit=220)
            ordered = normalize_klines(klines)
            closes = np.array([float(k.get("close", 0) or 0) for k in ordered], dtype=np.float64)
            volumes = np.array([float(k.get("volume", 0) or 0) for k in ordered], dtype=np.float64)
            if len(closes) < 90:
                continue
            signals = _generate_strategy_signal_series(klass, params or {}, closes, volumes)
            aligned_signals = signals[:-1]
            aligned_returns = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
            if len(aligned_signals) < 60 or len(aligned_signals) != len(aligned_returns):
                continue
            factor_columns.append(aligned_signals[-120:])
            return_columns.append(aligned_returns[-120:])
            strategy_series.append((aligned_signals[-120:] * aligned_returns[-120:]).astype(np.float64))
            close_histories.append(closes)
            volume_histories.append(volumes)
            latest_signal = float(aligned_signals[-1]) if len(aligned_signals) else 0.0
            if latest_signal != 0:
                holdings.append({"code": code, "weight": abs(latest_signal), "value": 100000.0 * abs(latest_signal)})
        except Exception:
            continue
    if len(factor_columns) < 3:
        return {}
    min_len = min(len(col) for col in factor_columns)
    factor_panel = np.column_stack([col[-min_len:] for col in factor_columns])
    return_panel = np.column_stack([col[-min_len:] for col in return_columns])
    strategy_returns = np.mean(np.column_stack([col[-min_len:] for col in strategy_series]), axis=1)
    family_returns = _build_family_returns(
        klass,
        params or {},
        close_histories,
        volume_histories,
        min_len=min_len,
    )
    total_weight = sum(item["weight"] for item in holdings) or 1.0
    holdings = [
        {**item, "weight": float(item["weight"] / total_weight)}
        for item in holdings
    ] or [{"code": "cash", "weight": 1.0, "value": 100000.0}]
    return {
        "factor_panel": factor_panel,
        "return_panel": return_panel,
        "strategy_returns": strategy_returns,
        "family_returns": family_returns,
        "holdings": holdings,
    }


async def _run_validation_report(strategy_type: str, params: dict, db) -> dict | None:
    validation_runtime = get_validation_runtime()
    panels = await _build_strategy_panels(strategy_type, params, db)
    factor_panel = panels.get("factor_panel")
    return_panel = panels.get("return_panel")
    strategy_returns = panels.get("strategy_returns")
    family_returns = panels.get("family_returns")
    if factor_panel is None or return_panel is None:
        return None
    pipeline = validation_runtime.FactorValidationPipeline(validation_parallel=False)
    return pipeline.run(
        factor_panel,
        return_panel,
        factor_name=f"strategy:{strategy_type}",
        validation_parallel=False,
        strategy_returns=strategy_returns,
        family_returns=family_returns,
    )


async def _run_risk_report(strategy_type: str, params: dict, db) -> dict | None:
    risk_model = get_risk_model_class()
    panels = await _build_strategy_panels(strategy_type, params, db)
    strategy_returns = panels.get("strategy_returns")
    holdings = panels.get("holdings")
    if strategy_returns is None or holdings is None or len(strategy_returns) == 0:
        return None
    var_report = risk_model.calculate_var(strategy_returns.tolist(), confidence=0.95, portfolio_value=1000000)
    stress_report = risk_model.stress_test(holdings, scenario="market_crash")
    return {
        "var_percent": round(float(var_report.get("var_percent", 0.0)), 4),
        "cvar_percent": round(float(var_report.get("cvar_percent", 0.0)), 4),
        "stress_loss_percent": round(float(stress_report.get("loss_percent", 0.0)), 4),
        "scenario": stress_report.get("scenario"),
    }
