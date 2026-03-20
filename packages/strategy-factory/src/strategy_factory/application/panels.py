"""策略工厂面板、验证与风险报告。"""

from __future__ import annotations

from typing import List

import numpy as np

from akshare_mcp.services.backtest.strategy_registry import StrategyRegistry
from akshare_mcp.services.data_pipeline import normalize_klines
from akshare_mcp.services.risk_model import RiskModel
from akshare_mcp.services.validation import FactorValidationPipeline

from ..domain.targets import _resolve_strategy_sample_codes


async def _build_strategy_panels(strategy_type: str, params: dict, db, sample_size: int = 6) -> dict:
    klass = StrategyRegistry.get(strategy_type)
    if klass is None:
        return {}
    factor_columns: List[np.ndarray] = []
    return_columns: List[np.ndarray] = []
    strategy_series: List[np.ndarray] = []
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
            instance = klass()
            instance.set_parameters(params or {})
            try:
                signals = np.asarray(instance.generate_signals(closes, volumes), dtype=np.float64)
            except TypeError:
                signals = np.asarray(instance.generate_signals(closes), dtype=np.float64)
            aligned_signals = signals[:-1]
            aligned_returns = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
            if len(aligned_signals) < 60 or len(aligned_signals) != len(aligned_returns):
                continue
            factor_columns.append(aligned_signals[-120:])
            return_columns.append(aligned_returns[-120:])
            strategy_series.append((aligned_signals[-120:] * aligned_returns[-120:]).astype(np.float64))
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
    total_weight = sum(item["weight"] for item in holdings) or 1.0
    holdings = [
        {**item, "weight": float(item["weight"] / total_weight)}
        for item in holdings
    ] or [{"code": "cash", "weight": 1.0, "value": 100000.0}]
    return {
        "factor_panel": factor_panel,
        "return_panel": return_panel,
        "strategy_returns": strategy_returns,
        "holdings": holdings,
    }


async def _run_validation_report(strategy_type: str, params: dict, db) -> dict | None:
    panels = await _build_strategy_panels(strategy_type, params, db)
    factor_panel = panels.get("factor_panel")
    return_panel = panels.get("return_panel")
    if factor_panel is None or return_panel is None:
        return None
    pipeline = FactorValidationPipeline(validation_parallel=False)
    return pipeline.run(
        factor_panel,
        return_panel,
        factor_name=f"strategy:{strategy_type}",
        validation_parallel=False,
    )


async def _run_risk_report(strategy_type: str, params: dict, db) -> dict | None:
    panels = await _build_strategy_panels(strategy_type, params, db)
    strategy_returns = panels.get("strategy_returns")
    holdings = panels.get("holdings")
    if strategy_returns is None or holdings is None or len(strategy_returns) == 0:
        return None
    var_report = RiskModel.calculate_var(strategy_returns.tolist(), confidence=0.95, portfolio_value=1000000)
    stress_report = RiskModel.stress_test(holdings, scenario="market_crash")
    return {
        "var_percent": round(float(var_report.get("var_percent", 0.0)), 4),
        "cvar_percent": round(float(var_report.get("cvar_percent", 0.0)), 4),
        "stress_loss_percent": round(float(stress_report.get("loss_percent", 0.0)), 4),
        "scenario": stress_report.get("scenario"),
    }
