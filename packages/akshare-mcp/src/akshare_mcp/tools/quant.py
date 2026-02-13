"""Quant factor tools."""

from typing import Any, Dict, Optional

import numpy as np
from scipy import stats

from ..services.factor_calculator import factor_calculator
from ..storage import get_db
from ..utils import fail, ok


SUPPORTED_FACTORS: Dict[str, Dict[str, Any]] = {
    "momentum": {
        "category": "technical",
        "description": "动量因子",
        "requires_financials": False,
    },
    "volatility": {
        "category": "risk",
        "description": "波动率因子",
        "requires_financials": False,
    },
    "value": {
        "category": "fundamental",
        "description": "价值因子",
        "requires_financials": True,
    },
    "quality": {
        "category": "fundamental",
        "description": "质量因子",
        "requires_financials": True,
    },
}

DEFAULT_FACTOR_LOOKBACK = 20


def _normalize_factor_name(factor: str) -> str:
    return str(factor or "").strip().lower()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _latest_financial_row(financials: Any) -> Optional[Dict[str, Any]]:
    if isinstance(financials, list):
        for item in financials:
            if isinstance(item, dict):
                return item
        return None
    if isinstance(financials, dict):
        return financials
    return None


def _extract_profit_growth(financial: Dict[str, Any]) -> float:
    for key in ("profit_growth", "profit_growth_yoy", "net_profit_growth", "revenue_growth"):
        val = _safe_float(financial.get(key), 0.0)
        if val != 0.0:
            return val
    return 0.0


def _calculate_factor_value(
    factor: str,
    closes: list,
    financial: Optional[Dict[str, Any]] = None,
    period: int = DEFAULT_FACTOR_LOOKBACK,
) -> Optional[float]:
    factor_name = _normalize_factor_name(factor)

    if factor_name == "momentum":
        if len(closes) < 2:
            return None
        lookback = max(2, min(int(period), len(closes)))
        return float(factor_calculator.calculate_momentum(closes, period=lookback))

    if factor_name == "volatility":
        if len(closes) < 3:
            return None
        lookback = max(3, min(int(period), len(closes)))
        return float(factor_calculator.calculate_volatility(closes, period=lookback))

    if factor_name == "value":
        if not financial:
            return None
        pe = _safe_float(financial.get("pe_ratio"), 0.0)
        pb = _safe_float(financial.get("pb_ratio"), 0.0)
        ps = _safe_float(financial.get("ps_ratio"), 0.0)
        if pe <= 0 and pb <= 0 and ps <= 0:
            return None
        return float(factor_calculator.calculate_value_factor(pe, pb, ps if ps > 0 else None))

    if factor_name == "quality":
        if not financial:
            return None
        roe = _safe_float(financial.get("roe"), 0.0)
        debt_ratio = _safe_float(financial.get("debt_ratio"), 0.0)
        growth = _extract_profit_growth(financial)
        return float(factor_calculator.calculate_quality_factor(roe, debt_ratio, growth if growth != 0 else None))

    return None


async def run_factor_ic_analysis(codes: list, factor: str, period: int = 20) -> Dict[str, Any]:
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

    if not codes:
        return fail("codes is required")

    lookback_period = max(2, int(period))
    db = get_db()
    factor_values = []
    future_returns = []
    stats_counter = {
        "input_codes": len(codes),
        "processed": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_no_factor_value": 0,
        "skipped_invalid_return": 0,
    }

    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]

    for code in codes:
        klines = await db.get_klines(code, limit=lookback_period + 30)
        if not klines or len(klines) < lookback_period + 5:
            stats_counter["skipped_no_kline"] += 1
            continue

        closes = [k["close"] for k in klines if isinstance(k, dict) and k.get("close") is not None]
        if len(closes) < lookback_period + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        financial = None
        if requires_financials:
            financial = _latest_financial_row(await db.get_financials(code, limit=1))
            if not financial:
                stats_counter["skipped_no_financials"] += 1
                continue

        factor_value = _calculate_factor_value(
            factor_name,
            closes[:lookback_period],
            financial=financial,
            period=min(lookback_period, len(closes[:lookback_period])),
        )
        if factor_value is None or np.isnan(factor_value):
            stats_counter["skipped_no_factor_value"] += 1
            continue

        current_idx = min(lookback_period - 1, len(closes) - 2)
        future_idx = min(current_idx + lookback_period, len(closes) - 1)
        if future_idx <= current_idx:
            stats_counter["skipped_invalid_return"] += 1
            continue

        current_price = closes[current_idx]
        future_price = closes[future_idx]
        if current_price <= 0:
            stats_counter["skipped_invalid_return"] += 1
            continue

        future_return = (future_price - current_price) / current_price
        factor_values.append(float(factor_value))
        future_returns.append(float(future_return))
        stats_counter["processed"] += 1

    sample_size = len(factor_values)
    if sample_size < 10:
        return fail(
            f"Not enough valid data for IC calculation: sample_size={sample_size}, "
            f"required>=10, stats={stats_counter}"
        )

    ic, p_value = stats.spearmanr(factor_values, future_returns)
    if np.isnan(ic) or np.isnan(p_value):
        return fail("IC calculation returned NaN")

    win_count = sum(
        1
        for factor_value, future_return in zip(factor_values, future_returns)
        if (factor_value >= 0 and future_return >= 0) or (factor_value < 0 and future_return < 0)
    )
    win_rate = win_count / sample_size if sample_size > 0 else 0.0

    # Cross-sectional proxy to keep backward compatibility for downstream consumers.
    ic_ir = float(ic * np.sqrt(sample_size))

    return ok(
        {
            "factor": factor_name,
            "ic": float(ic),
            "ic_ir": ic_ir,
            "p_value": float(p_value),
            "significant": bool(p_value < 0.05),
            "sample_size": sample_size,
            "period": lookback_period,
            "win_rate": float(win_rate),
            "data_window": {
                "lookback_bars": lookback_period + 30,
                "forward_period": lookback_period,
            },
            "stats": stats_counter,
            "source_chain": ["db.get_klines", "db.get_financials(optional)", "scipy.spearmanr"],
        }
    )


async def run_factor_group_backtest(
    codes: list,
    factor: str,
    groups: int = 5,
    holding_days: int = 20,
    factor_lookback: int = DEFAULT_FACTOR_LOOKBACK,
) -> Dict[str, Any]:
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

    if not codes:
        return fail("codes is required")

    groups = max(2, int(groups))
    holding_days = max(1, int(holding_days))
    factor_lookback = max(2, int(factor_lookback))

    db = get_db()
    stock_data = []
    stats_counter = {
        "input_codes": len(codes),
        "processed": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_no_factor_value": 0,
        "skipped_invalid_return": 0,
    }
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]
    fetch_bars = max(factor_lookback + holding_days + 5, 40)

    for code in codes:
        klines = await db.get_klines(code, limit=fetch_bars)
        if not klines or len(klines) < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        closes = [k["close"] for k in klines if isinstance(k, dict) and k.get("close") is not None]
        if len(closes) < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        financial = None
        if requires_financials:
            financial = _latest_financial_row(await db.get_financials(code, limit=1))
            if not financial:
                stats_counter["skipped_no_financials"] += 1
                continue

        entry_idx = min(factor_lookback - 1, len(closes) - 2)
        exit_idx = min(entry_idx + holding_days, len(closes) - 1)
        if exit_idx <= entry_idx:
            stats_counter["skipped_invalid_return"] += 1
            continue

        factor_value = _calculate_factor_value(
            factor_name,
            closes[: entry_idx + 1],
            financial=financial,
            period=min(factor_lookback, entry_idx + 1),
        )
        if factor_value is None or np.isnan(factor_value):
            stats_counter["skipped_no_factor_value"] += 1
            continue

        entry_price = closes[entry_idx]
        exit_price = closes[exit_idx]
        if entry_price <= 0:
            stats_counter["skipped_invalid_return"] += 1
            continue

        holding_return = (exit_price - entry_price) / entry_price
        stock_data.append(
            {
                "code": code,
                "factor_value": float(factor_value),
                "return": float(holding_return),
            }
        )
        stats_counter["processed"] += 1

    if len(stock_data) < groups * 2:
        return fail(
            f"Not enough stocks for grouping: valid={len(stock_data)}, required>={groups * 2}, stats={stats_counter}"
        )

    stock_data.sort(key=lambda x: x["factor_value"])
    group_size = max(1, len(stock_data) // groups)
    group_returns = []

    for i in range(groups):
        start_idx = i * group_size
        end_idx = start_idx + group_size if i < groups - 1 else len(stock_data)
        group_stocks = stock_data[start_idx:end_idx]
        if not group_stocks:
            group_returns.append({"group": i + 1, "avg_return": 0.0, "stock_count": 0})
            continue

        avg_return = float(np.mean([s["return"] for s in group_stocks]))
        group_returns.append({"group": i + 1, "avg_return": avg_return, "stock_count": len(group_stocks)})

    long_short_return = float(group_returns[-1]["avg_return"] - group_returns[0]["avg_return"])
    annual_return = (
        float((1 + long_short_return) ** (252.0 / holding_days) - 1.0)
        if long_short_return > -1.0
        else -1.0
    )

    all_returns = [item["return"] for item in stock_data]
    mean_ret = float(np.mean(all_returns)) if all_returns else 0.0
    std_ret = float(np.std(all_returns, ddof=1)) if len(all_returns) > 1 else 0.0
    sharpe_ratio = float((mean_ret / std_ret) * np.sqrt(252.0 / holding_days)) if std_ret > 0 else 0.0
    win_rate = float(sum(1 for r in all_returns if r > 0) / len(all_returns)) if all_returns else 0.0
    max_drawdown_proxy = float(abs(min(all_returns))) if all_returns else 0.0

    return ok(
        {
            "factor": factor_name,
            "groups": groups,
            "holding_days": holding_days,
            "factor_lookback": factor_lookback,
            "group_returns": group_returns,
            "long_short_return": long_short_return,
            "total_stocks": len(stock_data),
            "total_return": long_short_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown_proxy,
            "win_rate": win_rate,
            "stats": stats_counter,
            "source_chain": ["db.get_klines", "db.get_financials(optional)", "numpy-grouping"],
            "notes": "max_drawdown is a downside proxy in this single-horizon grouped backtest.",
        }
    )


def register(mcp):
    @mcp.tool()
    def get_factor_library(category: str = "all"):
        category_key = str(category or "all").strip().lower()
        factors = [
            {
                "name": name,
                "category": meta["category"],
                "description": meta["description"],
                "requires_financials": meta["requires_financials"],
                "status": "supported",
            }
            for name, meta in SUPPORTED_FACTORS.items()
            if category_key in ("all", meta["category"])
        ]
        return ok({"factors": factors, "count": len(factors), "supported_factors": sorted(SUPPORTED_FACTORS.keys())})

    @mcp.tool()
    async def calculate_factor(code: str, factor: str):
        try:
            factor_name = _normalize_factor_name(factor)
            if factor_name not in SUPPORTED_FACTORS:
                return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

            db = get_db()
            klines = await db.get_klines(code, limit=100)
            if not klines:
                return fail("No kline data")

            closes = [k["close"] for k in klines if isinstance(k, dict) and k.get("close") is not None]
            if len(closes) < 2:
                return fail("Not enough close data")

            financial = None
            if SUPPORTED_FACTORS[factor_name]["requires_financials"]:
                financial = _latest_financial_row(await db.get_financials(code, limit=1))
                if not financial:
                    return fail(f"No financial data for factor: {factor_name}")

            value = _calculate_factor_value(factor_name, closes, financial=financial, period=DEFAULT_FACTOR_LOOKBACK)
            if value is None or np.isnan(value):
                return fail(f"Failed to calculate factor: {factor_name}")

            return ok(
                {
                    "code": code,
                    "factor": factor_name,
                    "value": float(value),
                    "requires_financials": SUPPORTED_FACTORS[factor_name]["requires_financials"],
                    "sample_size": len(closes),
                }
            )
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def calculate_factor_ic(codes: list, factor: str, period: int = 20):
        """Calculate information coefficient (IC) by cross-section."""
        try:
            return await run_factor_ic_analysis(codes=codes, factor=factor, period=period)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def backtest_factor(codes: list, factor: str, groups: int = 5, holding_days: int = 20):
        """Run grouped factor backtest on a stock universe."""
        try:
            return await run_factor_group_backtest(
                codes=codes,
                factor=factor,
                groups=groups,
                holding_days=holding_days,
                factor_lookback=DEFAULT_FACTOR_LOOKBACK,
            )
        except Exception as e:
            return fail(str(e))
