"""Classic factor action handlers for quant_manager."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

import numpy as np

from ...data_source import data_source
from ...storage import get_db
from ..quant import SUPPORTED_FACTORS, run_factor_group_backtest, run_factor_ic_analysis
from .quant_mgr_helpers import (
    _as_code_list,
    _compute_alternative_factors_for_code,
    _compute_scalar_factor_bundle,
    _load_valuation_snapshot,
    _parse_date_value,
    _select_financial_snapshot,
    _sort_klines_ascending,
)

logger = logging.getLogger(__name__)

_CALCULATE_FACTORS_SUPPORTED = {
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
_BATCH_FACTORS_SUPPORTED = {"momentum", "value", "quality", "growth", "volatility", "reversal"}


async def _load_klines_with_fallback(
    *,
    db: Any,
    code: str,
    limit: int = 252,
) -> tuple[list[dict], list[str]]:
    klines = await db.get_klines(code, limit=limit)
    source_chain = ["db.get_klines"]
    if klines:
        return list(klines), source_chain

    logger.info("[QuantManager] No kline in DB, fallback data_source.get_kline: %s", code)
    klines_data = data_source.get_kline(code, period="daily", limit=limit)
    if not klines_data:
        return [], source_chain

    return (
        [
            {
                "date": item.get("date"),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "volume": item.get("volume"),
                "amount": item.get("amount", 0),
            }
            for item in klines_data
        ],
        ["data_source.get_kline"],
    )


async def handle_calculate_factors(
    *,
    kw: dict[str, Any],
    code: str | None,
    db: Any,
    ok: Callable[..., dict],
    fail: Callable[..., dict],
) -> dict:
    if not code:
        return fail("需要提供股票代码（code）")

    factors = kw.get("factors", ["momentum", "value", "quality", "growth"])
    unknown_factors = [factor for factor in factors if factor not in _CALCULATE_FACTORS_SUPPORTED]
    if unknown_factors:
        return fail(
            f"Unsupported factors: {unknown_factors}. "
            f"Supported: {sorted(_CALCULATE_FACTORS_SUPPORTED)}"
        )

    klines, source_chain = await _load_klines_with_fallback(db=db, code=code, limit=252)
    if not klines:
        return fail(
            f"未找到 {code} 的K线数据。\n\n"
            f"请先运行数据预热: data_warmup(action='warmup', stocks=['{code}'], lookback_days=252)",
            source_chain=source_chain,
        )

    ordered_klines = _sort_klines_ascending(klines)
    closes = [item.get("close") for item in ordered_klines if isinstance(item, dict) and item.get("close") is not None]
    if len(closes) < 2:
        return fail("K线数据不足，无法计算因子", source_chain=source_chain)

    financials = await db.get_financials(code, limit=4)
    latest_financial = _select_financial_snapshot(financials)
    valuation_snapshot = await _load_valuation_snapshot(db, code)
    factor_values: dict[str, dict[str, Any]] = {}

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
        volumes = [float(item.get("volume", 0) or 0) for item in klines[-20:]]
        amounts = [float(item.get("amount", 0) or 0) for item in klines[-20:]]
        avg_volume = float(np.mean(volumes)) if volumes else 0.0
        avg_amount = float(np.mean(amounts)) if amounts else 0.0
        factor_values["liquidity"] = {
            "avg_volume_20d": avg_volume,
            "avg_amount_20d": avg_amount,
            "score": float(avg_amount / 1e8),
            "level": "high" if avg_amount > 1e8 else ("low" if avg_amount < 1e7 else "medium"),
        }

    requested_alt = any(factor in factors for factor in ("sentiment", "event", "capital_flow", "alternative_composite"))
    if requested_alt:
        alt_days = int(kw.get("alt_lookback_days", 30) or 30)
        alt_limit = int(kw.get("alt_limit", 20) or 20)
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

    composite_score = float(np.mean([item.get("score", 0) for item in factor_values.values()])) if factor_values else 0.0
    return ok(
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


async def handle_factor_ic(
    *,
    kw: dict[str, Any],
    fail: Callable[..., dict],
    with_meta: Callable[..., dict],
) -> dict:
    factor_name = str(kw.get("factor_name", kw.get("factor", "momentum")) or "").strip().lower()
    period = kw.get("period", 20)
    codes = kw.get("codes", [])
    enable_neutralization = bool(kw.get("enable_neutralization", True))
    bootstrap_n = int(kw.get("bootstrap_n", 1000) or 1000)
    bootstrap_confidence = float(kw.get("bootstrap_confidence", 0.95) or 0.95)

    if factor_name not in SUPPORTED_FACTORS:
        return fail(
            f"Unsupported factor: {factor_name}. "
            f"Supported: {sorted(SUPPORTED_FACTORS.keys())}"
        )
    if not isinstance(codes, list) or not codes:
        return fail("需要提供股票列表（codes）")

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

    return with_meta(
        result,
        source_chain=["db.get_klines", "db.get_financials(optional)", "factor_analysis_dual_ic", "bootstrap_ci"],
    )


async def handle_backtest_factor(
    *,
    kw: dict[str, Any],
    fail: Callable[..., dict],
    with_meta: Callable[..., dict],
) -> dict:
    factor_name = str(kw.get("factor_name", kw.get("factor", "momentum")) or "").strip().lower()
    start_date = kw.get("start_date")
    end_date = kw.get("end_date")
    groups = kw.get("groups", 5)
    holding_days = kw.get("holding_days", 20)
    factor_lookback = kw.get("factor_lookback", 20)
    codes = kw.get("codes", [])

    if factor_name not in SUPPORTED_FACTORS:
        return fail(
            f"Unsupported factor: {factor_name}. "
            f"Supported: {sorted(SUPPORTED_FACTORS.keys())}"
        )
    if not isinstance(codes, list) or not codes:
        return fail("需要提供股票列表（codes）")

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

    return with_meta(
        result,
        source_chain=["db.get_klines", "db.get_financials(optional)", "numpy-grouping"],
    )


async def handle_multi_factor_score(
    *,
    kw: dict[str, Any],
    code: str | None,
    ok: Callable[..., dict],
    fail: Callable[..., dict],
    quant_manager_call: Callable[..., Any],
) -> dict:
    if not code:
        return fail("需要提供股票代码（code）")

    weights = kw.get(
        "weights",
        {
            "momentum": 0.3,
            "value": 0.3,
            "quality": 0.2,
            "volatility": 0.1,
            "liquidity": 0.1,
        },
    )

    result = await quant_manager_call(
        action="calculate_factors",
        code=code,
        kwargs={"factors": list(weights.keys())},
    )
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

    return ok(
        {
            "code": code,
            "total_score": float(total_score),
            "rating": rating,
            "recommendation": recommendation,
            "factor_scores": factor_scores,
        },
        source_chain=["quant_manager.calculate_factors"],
    )


async def handle_alternative_factors(
    *,
    kw: dict[str, Any],
    code: str | None,
    db: Any,
    ok: Callable[..., dict],
    fail: Callable[..., dict],
) -> dict:
    codes = _as_code_list(kw.get("codes"))
    if not codes and code:
        codes = [code]
    if not codes:
        return fail("需要提供 code 或 codes")

    lookback_days = int(kw.get("lookback_days", 30) or 30)
    limit = int(kw.get("limit", 20) or 20)
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

    return ok(
        {
            "codes": codes,
            "count": len(result_rows),
            "data_window": {"lookback_days": lookback_days, "limit_per_source": limit},
            "rows": result_rows,
        },
        source_chain=source_chain or ["quant_manager.alternative_factors"],
    )


async def handle_batch_compute_factors(
    *,
    kw: dict[str, Any],
    ok: Callable[..., dict],
    fail: Callable[..., dict],
    get_db_fn: Callable[[], Any] = get_db,
) -> dict:
    codes = kw.get("codes", [])
    if not isinstance(codes, list) or not codes:
        return fail("codes (list of stock codes) is required")
    factors = kw.get("factors", ["momentum", "value", "quality", "growth"])
    persist = bool(kw.get("persist", True))
    compute_ic = bool(kw.get("compute_ic", True))
    period = int(kw.get("period", 20) or 20)

    unknown = [factor for factor in factors if factor not in _BATCH_FACTORS_SUPPORTED]
    if unknown:
        return fail(f"Unsupported factors for batch: {unknown}. Supported: {sorted(_BATCH_FACTORS_SUPPORTED)}")

    db = get_db_fn()
    results = {}
    errors = []
    persist_buffer = []
    today = datetime.now().date()

    for stock_code in codes[:200]:
        try:
            klines, _source_chain = await _load_klines_with_fallback(db=db, code=stock_code, limit=252)
            if not klines:
                errors.append({"code": stock_code, "error": "no kline data"})
                continue

            ordered_klines = _sort_klines_ascending(klines)
            closes = [item.get("close") for item in ordered_klines if isinstance(item, dict) and item.get("close") is not None]
            if len(closes) < 20:
                errors.append({"code": stock_code, "error": "insufficient data"})
                continue

            financials = await db.get_financials(stock_code, limit=8)
            latest_fin = _select_financial_snapshot(financials)
            valuation_snapshot = await _load_valuation_snapshot(db, stock_code)
            factor_values = _compute_scalar_factor_bundle(
                closes,
                financial_snapshot=latest_fin,
                valuation_snapshot=valuation_snapshot,
                factors=factors,
            )

            results[stock_code] = factor_values
            if persist and factor_values:
                persist_buffer.append(
                    {
                        "stock_code": stock_code,
                        "factor_date": today,
                        "values": factor_values,
                    }
                )
        except Exception as exc:
            errors.append({"code": stock_code, "error": str(exc)})

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

    ic_results = {}
    if compute_ic and len(results) >= 10:
        for factor_name in factors:
            factor_vals = []
            forward_rets = []
            for stock_code, factor_values in results.items():
                if factor_name not in factor_values:
                    continue
                try:
                    klines = await db.get_klines(stock_code, limit=period + 60)
                    if not klines or len(klines) < period + 20:
                        continue
                    ordered_klines = _sort_klines_ascending(klines)
                    closes = [float(item.get("close", 0) or 0) for item in ordered_klines]
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
                        factors=[factor_name],
                    )
                    if factor_name not in lagged_bundle:
                        continue
                    lagged_fv = float(lagged_bundle[factor_name])
                    if factor_name in {"value", "quality", "growth"} and not lagged_fin:
                        continue
                    if factor_name == "value" and not lagged_valuation:
                        continue
                    close_lagged = closes[-(period + 1)]
                    close_now = closes[-1]
                    if close_lagged and close_now:
                        factor_vals.append(lagged_fv)
                        forward_rets.append((close_now - close_lagged) / close_lagged)
                except Exception:
                    continue

            if len(factor_vals) >= 10:
                from ...services.factor_calculator.analysis import AnalysisFactorsMixin

                ic_data = AnalysisFactorsMixin.calculate_factor_ic(factor_vals, forward_rets)
                ic_val = ic_data.get("ic", 0.0)
                rank_ic = ic_data.get("rank_ic", 0.0)
                ic_results[factor_name] = {"ic": ic_val, "rank_ic": rank_ic, "sample_size": len(factor_vals)}
                if persist:
                    await db.save_factor_ic(factor_name, str(period), today, ic_val, rank_ic, len(factor_vals))

    return ok(
        {
            "computed_count": len(results),
            "error_count": len(errors),
            "errors": errors[:10],
            "factors": factors,
            "ic": ic_results,
            "persisted": persist,
        },
        source_chain=["db.get_klines", "db.save_factor_values", "db.save_factor_ic"],
    )


__all__ = [
    "handle_alternative_factors",
    "handle_backtest_factor",
    "handle_batch_compute_factors",
    "handle_calculate_factors",
    "handle_factor_ic",
    "handle_multi_factor_score",
]
