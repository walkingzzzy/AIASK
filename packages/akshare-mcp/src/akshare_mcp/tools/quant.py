"""Quant factor tools."""

from typing import Any, Dict, List, Optional

import numpy as np
from scipy import stats

from ..services.slippage import SlippageCalculator, SlippageModelType
from ..services.factor_calculator import factor_calculator
from ..services.factor_analysis import FactorAnalyzer as ICFactorAnalyzer
from ..services.validation import FactorValidationPipeline, bootstrap_ic_ci
from ..storage import get_db
from ..utils import fail, ok


SUPPORTED_FACTORS: Dict[str, Dict[str, Any]] = {
    "momentum": {
        "category": "technical",
        "description": "动量因子",
        "requires_financials": False,
        "sub_factors": ["return_20d", "return_60d", "trend_strength"],
        "aliases": ["mom", "mtm", "price_momentum"],
    },
    "trend": {
        "category": "technical",
        "description": "趋势因子",
        "requires_financials": False,
        "sub_factors": ["ma20_slope", "ma60_slope", "price_above_ma"],
        "aliases": ["ma_trend", "trend_strength", "moving_trend"],
    },
    "reversal": {
        "category": "technical",
        "description": "反转因子",
        "requires_financials": False,
        "sub_factors": ["short_term_reversal", "oversold_rebound"],
        "aliases": ["mean_reversion", "rev", "revert"],
    },
    "volatility": {
        "category": "risk",
        "description": "波动率因子",
        "requires_financials": False,
        "sub_factors": ["realized_vol_20d", "atr_proxy"],
        "aliases": ["vol", "risk_volatility", "sigma"],
    },
    "value": {
        "category": "fundamental",
        "description": "价值因子",
        "requires_financials": True,
        "sub_factors": ["pe", "pb", "ps"],
        "aliases": ["valuation", "cheapness", "value_score"],
    },
    "quality": {
        "category": "fundamental",
        "description": "质量因子",
        "requires_financials": True,
        "sub_factors": ["roe", "debt_ratio", "profit_growth"],
        "aliases": ["profitability", "quality_score", "high_quality"],
    },
    "growth": {
        "category": "fundamental",
        "description": "成长因子",
        "requires_financials": True,
        "sub_factors": ["revenue_growth", "profit_growth", "eps_growth"],
        "aliases": ["growth_score", "earnings_growth", "sales_growth"],
    },
    "size": {
        "category": "fundamental",
        "description": "规模因子",
        "requires_financials": False,
        "sub_factors": ["market_cap", "float_market_cap"],
        "aliases": ["market_cap", "small_cap", "size_score"],
    },
}

DEFAULT_FACTOR_LOOKBACK = 20

REVENUE_GROWTH_KEYS = (
    "revenue_growth",
    "revenue_growth_yoy",
    "sales_growth",
    "sales_growth_yoy",
    "operating_revenue_growth",
    "or_yoy",
    "total_revenue_growth",
)
PROFIT_GROWTH_KEYS = (
    "profit_growth",
    "profit_growth_yoy",
    "net_profit_growth",
    "netprofit_yoy",
    "np_growth",
    "earnings_growth",
    "eps_growth",
    "eps_growth_yoy",
)
MARKET_CAP_KEYS = (
    "market_cap",
    "total_market_cap",
    "total_mv",
    "circ_mv",
    "float_market_cap",
    "mkt_cap",
    "totalMarketCap",
    "floatMarketCap",
    "总市值",
    "流通市值",
)

_SLIPPAGE_MODEL_MAP = {
    "fixed": SlippageModelType.FIXED,
    "volume_based": SlippageModelType.VOLUME_BASED,
    "market_impact": SlippageModelType.MARKET_IMPACT,
}


def _normalize_factor_name(factor: str) -> str:
    return str(factor or "").strip().lower()


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
        return bool(default)
    return bool(value)


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


def _first_valid_float(
    payload: Optional[Dict[str, Any]],
    keys: Any,
    *,
    positive_only: bool = False,
) -> Optional[float]:
    if not isinstance(payload, dict):
        return None

    for key in keys:
        if key not in payload:
            continue
        raw = payload.get(key)
        if raw is None:
            continue
        val = _safe_float(raw, float("nan"))
        if not np.isfinite(val):
            continue
        if positive_only and val <= 0:
            continue
        return float(val)

    return None


def _extract_style_exposures(
    stock_info: Optional[Dict[str, Any]],
    financial: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """从 stock_info/financial 中提取行业、市值、beta 风格暴露（有则用，无则降级）。"""
    info = stock_info or {}
    fin = financial or {}

    industry = info.get("industry") or fin.get("industry")

    market_cap = None
    for key in (
        "market_cap",
        "total_market_cap",
        "total_mv",
        "circ_mv",
        "float_market_cap",
        "mkt_cap",
    ):
        market_cap = _safe_float(info.get(key), 0.0)
        if market_cap > 0:
            break
        market_cap = _safe_float(fin.get(key), 0.0)
        if market_cap > 0:
            break
    if market_cap is not None and market_cap <= 0:
        market_cap = None

    beta = None
    for key in ("beta", "beta_1y", "beta_250d", "beta_60d"):
        candidate = info.get(key, fin.get(key))
        if candidate is not None:
            beta = _safe_float(candidate, 0.0)
            break

    return {
        "industry": industry,
        "market_cap": market_cap,
        "beta": beta,
    }


def _limit_ratio_from_code(code: str) -> float:
    c = str(code or "").strip()
    for prefix in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if c.startswith(prefix):
            c = c[len(prefix):]
            break
    if c.startswith("300") or c.startswith("301") or c.startswith("688"):
        return 0.20
    return 0.10


def _build_tradability_mask_local(
    closes: np.ndarray,
    volumes: Optional[np.ndarray] = None,
    *,
    code: str = "",
    is_st: bool = False,
) -> np.ndarray:
    n = len(closes)
    mask = np.ones(n, dtype=bool)
    if n == 0:
        return mask

    if volumes is not None and len(volumes) == n:
        mask &= volumes > 0

    limit_ratio = 0.05 if is_st else _limit_ratio_from_code(code)
    tolerance = 0.002
    for i in range(1, n):
        prev = closes[i - 1]
        if prev <= 0:
            continue
        change = (closes[i] - prev) / prev
        if change >= limit_ratio - tolerance or change <= -(limit_ratio - tolerance):
            mask[i] = False
    return mask


def _compute_trade_return_with_costs(
    *,
    entry_price: float,
    exit_price: float,
    entry_volume: float,
    exit_volume: float,
    commission: float,
    slippage: float,
    slippage_calc: Optional[SlippageCalculator],
) -> Optional[Dict[str, float]]:
    if entry_price <= 0 or exit_price <= 0:
        return None

    commission = max(0.0, float(commission or 0.0))
    slippage = max(0.0, float(slippage or 0.0))
    order_size = 1.0

    if slippage_calc is not None:
        buy_slip = slippage_calc.calculate(
            price=float(entry_price),
            volume=float(entry_volume),
            order_size=order_size,
            is_buy=True,
        )
        sell_slip = slippage_calc.calculate(
            price=float(exit_price),
            volume=float(exit_volume),
            order_size=order_size,
            is_buy=False,
        )
        buy_exec = float(buy_slip.get("execution_price", entry_price))
        sell_exec = float(sell_slip.get("execution_price", exit_price))
        slip_buy_rate = max(0.0, (buy_exec - entry_price) / entry_price) if entry_price > 0 else 0.0
        slip_sell_rate = max(0.0, (exit_price - sell_exec) / exit_price) if exit_price > 0 else 0.0
        impact_cost_rate = float(slip_buy_rate + slip_sell_rate)
    else:
        buy_exec = float(entry_price * (1 + slippage))
        sell_exec = float(exit_price * (1 - slippage))
        impact_cost_rate = float(max(0.0, slippage * 2.0))

    net_entry = buy_exec * (1 + commission)
    net_exit = sell_exec * (1 - commission)
    if net_entry <= 0:
        return None

    net_return = float(net_exit / net_entry - 1.0)
    return {
        "net_return": net_return,
        "impact_cost_rate": impact_cost_rate,
        "transaction_cost_rate": float(impact_cost_rate + commission * 2.0),
    }


def _calculate_factor_value(
    factor: str,
    closes: list,
    financial: Optional[Dict[str, Any]] = None,
    stock_info: Optional[Dict[str, Any]] = None,
    period: int = DEFAULT_FACTOR_LOOKBACK,
) -> Optional[float]:
    factor_name = _normalize_factor_name(factor)

    if factor_name == "momentum":
        if len(closes) < 2:
            return None
        lookback = max(2, min(int(period), len(closes)))
        return float(factor_calculator.calculate_momentum(closes, period=lookback))

    if factor_name == "volatility":
        if len(closes) < 4:
            return None
        lookback = max(3, min(int(period), len(closes) - 1))
        try:
            vol = float(factor_calculator.calculate_volatility(closes, period=lookback))
            if np.isfinite(vol):
                return vol
        except Exception:
            vol = None

        # Fallback: realized volatility over log-return approximation window.
        window = np.array(closes[-(lookback + 1) :], dtype=np.float64)
        if window.size < 3:
            return None
        prev = window[:-1]
        curr = window[1:]
        valid = prev > 0
        if int(np.sum(valid)) < 2:
            return None
        rets = (curr[valid] - prev[valid]) / prev[valid]
        if rets.size < 2:
            return None
        return float(np.std(rets, ddof=1) * np.sqrt(252.0))

    if factor_name == "trend":
        if len(closes) < 3:
            return None
        lookback = max(3, min(int(period), len(closes)))
        return float(factor_calculator.calculate_trend_factor(closes, period=lookback))

    if factor_name == "reversal":
        if len(closes) < 2:
            return None
        lookback = max(2, min(int(period), len(closes), 10))
        return float(factor_calculator.calculate_reversal(closes, period=lookback))

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

    if factor_name == "growth":
        if not financial:
            return None
        revenue_growth = _first_valid_float(financial, REVENUE_GROWTH_KEYS)
        profit_growth = _first_valid_float(financial, PROFIT_GROWTH_KEYS)
        if revenue_growth is None and profit_growth is None:
            return None
        return float(factor_calculator.calculate_growth_factor(revenue_growth, profit_growth))

    if factor_name == "size":
        market_cap = _first_valid_float(stock_info, MARKET_CAP_KEYS, positive_only=True)
        if market_cap is None:
            market_cap = _first_valid_float(financial, MARKET_CAP_KEYS, positive_only=True)
        if market_cap is None:
            return None
        return float(factor_calculator.calculate_size_factor(market_cap))

    return None


async def run_factor_ic_analysis(
    codes: list,
    factor: str,
    period: int = 20,
    enable_neutralization: bool = True,
    bootstrap_n: int = 1000,
    bootstrap_confidence: float = 0.95,
) -> Dict[str, Any]:
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

    if not codes:
        return fail("codes is required")

    lookback_period = max(2, int(period))
    db = get_db()
    factor_values = []
    future_returns = []
    industries = []
    market_caps = []
    betas = []
    stats_counter = {
        "input_codes": len(codes),
        "processed": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_no_factor_value": 0,
            "skipped_invalid_return": 0,
            "style_info_available": 0,
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

        stock_info = None
        try:
            stock_info = await db.get_stock_info(code)
        except Exception:
            stock_info = None

        factor_value = _calculate_factor_value(
            factor_name,
            closes[:lookback_period],
            financial=financial,
            stock_info=stock_info,
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
        styles = _extract_style_exposures(stock_info, financial)
        factor_values.append(float(factor_value))
        future_returns.append(float(future_return))
        industries.append(styles.get("industry"))
        market_caps.append(styles.get("market_cap"))
        betas.append(styles.get("beta"))

        if (
            styles.get("industry") is not None
            or styles.get("market_cap") is not None
            or styles.get("beta") is not None
        ):
            stats_counter["style_info_available"] += 1
        stats_counter["processed"] += 1

    sample_size = len(factor_values)
    if sample_size < 10:
        return fail(
            f"Not enough valid data for IC calculation: sample_size={sample_size}, "
            f"required>=10, stats={stats_counter}"
        )

    dual_ic = ICFactorAnalyzer.calculate_ic_dual(
        factor_values=factor_values,
        forward_returns=future_returns,
        industry=industries,
        market_cap=market_caps,
        beta=betas,
        enable_neutralization=bool(enable_neutralization),
    )
    rank_ic = float(dual_ic.get("rank_ic", 0.0))
    rank_p_value = float(dual_ic.get("rank_p_value", 1.0))
    bootstrap_n = max(200, min(10_000, int(bootstrap_n or 1000)))
    bootstrap_confidence = max(0.80, min(0.999, float(bootstrap_confidence or 0.95)))

    # --- P0-B: Bootstrap IC 置信区间 ---
    fv_arr = np.array(factor_values, dtype=np.float64)
    fr_arr = np.array(future_returns, dtype=np.float64)
    try:
        boot_rank = bootstrap_ic_ci(
            fv_arr,
            fr_arr,
            method="spearman",
            n_bootstrap=bootstrap_n,
            confidence=bootstrap_confidence,
            seed=42,
        )
        boot_normal = bootstrap_ic_ci(
            fv_arr,
            fr_arr,
            method="pearson",
            n_bootstrap=bootstrap_n,
            confidence=bootstrap_confidence,
            seed=42,
        )
    except Exception:
        boot_rank = {
            "ic": rank_ic,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "se": 0.0,
            "n_bootstrap": 0,
            "sample_size": sample_size,
            "confidence": bootstrap_confidence,
        }
        boot_normal = {
            "ic": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "se": 0.0,
            "n_bootstrap": 0,
            "sample_size": sample_size,
            "confidence": bootstrap_confidence,
        }

    # --- P0-B: 改进 IC_IR ---
    # Bootstrap SE 提供了 IC 的标准误差，IC_IR = IC / SE(IC)
    # 当 Bootstrap SE 可用且 > 0 时使用，否则回退到截面代理
    boot_se = boot_rank.get("se", 0.0)
    if boot_se > 1e-10:
        ic_ir = float(rank_ic / boot_se)
    else:
        # 回退: 截面代理 (backward compatibility)
        ic_ir = float(rank_ic * np.sqrt(sample_size))

    win_count = sum(
        1
        for factor_value, future_return in zip(factor_values, future_returns)
        if (factor_value >= 0 and future_return >= 0) or (factor_value < 0 and future_return < 0)
    )
    win_rate = win_count / sample_size if sample_size > 0 else 0.0

    return ok(
        {
            "factor": factor_name,
            # backward compatible fields
            "ic": rank_ic,
            "ic_ir": ic_ir,
            "p_value": rank_p_value,
            "significant": bool(rank_p_value < 0.05),
            # dual IC fields
            "normal_ic": float(dual_ic.get("normal_ic", 0.0)),
            "rank_ic": rank_ic,
            "normal_p_value": float(dual_ic.get("normal_p_value", 1.0)),
            "rank_p_value": rank_p_value,
            "sample_size": sample_size,
            "period": lookback_period,
            "win_rate": float(win_rate),
            # P0-B: Bootstrap 置信区间
            "bootstrap_ci": {
                "rank_ic": {
                    "ic": boot_rank.get("ic", rank_ic),
                    "ci_lower": boot_rank.get("ci_lower", 0.0),
                    "ci_upper": boot_rank.get("ci_upper", 0.0),
                    "se": boot_rank.get("se", 0.0),
                    "confidence": boot_rank.get("confidence", 0.95),
                },
                "normal_ic": {
                    "ic": boot_normal.get("ic", 0.0),
                    "ci_lower": boot_normal.get("ci_lower", 0.0),
                    "ci_upper": boot_normal.get("ci_upper", 0.0),
                    "se": boot_normal.get("se", 0.0),
                    "confidence": boot_normal.get("confidence", 0.95),
                },
                "n_bootstrap": boot_rank.get("n_bootstrap", 0),
                "ic_ir_method": "bootstrap_se" if boot_se > 1e-10 else "cross_sectional_proxy",
            },
            "data_window": {
                "lookback_bars": lookback_period + 30,
                "forward_period": lookback_period,
            },
            "stats": stats_counter,
            "neutralization": dual_ic.get("neutralization", {}),
            "source_chain": [
                "db.get_klines",
                "db.get_financials(optional)",
                "db.get_stock_info(optional)",
                "factor_analysis.calculate_ic_dual",
                "validation.bootstrap_ic_ci",
            ],
            "params": {
                "enable_neutralization": bool(enable_neutralization),
                "bootstrap_n": bootstrap_n,
                "bootstrap_confidence": bootstrap_confidence,
            },
        }
    )


async def run_factor_group_backtest(
    codes: list,
    factor: str,
    groups: int = 5,
    holding_days: int = 20,
    factor_lookback: int = DEFAULT_FACTOR_LOOKBACK,
    commission: float = 0.0003,
    slippage: float = 0.0,
    slippage_model: str = "",
    tradability_filter: bool = False,
    is_st: bool = False,
    rebalance_step: int = 0,
    max_periods: int = 0,
) -> Dict[str, Any]:
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

    if not codes:
        return fail("codes is required")

    groups = max(2, int(groups))
    holding_days = max(1, int(holding_days))
    factor_lookback = max(2, int(factor_lookback))
    commission = max(0.0, float(commission or 0.0))
    slippage = max(0.0, float(slippage or 0.0))
    tradability_filter = _to_bool(tradability_filter, False)
    is_st = _to_bool(is_st, False)
    rebalance_step = max(1, int(rebalance_step or holding_days))
    max_periods = max(0, int(max_periods or 0))

    db = get_db()
    per_code_data: Dict[str, Dict[str, Any]] = {}
    period_results: List[Dict[str, Any]] = []
    long_short_returns: List[float] = []
    group_return_series: Dict[int, List[float]] = {i + 1: [] for i in range(groups)}
    group_stock_counts: Dict[int, List[int]] = {i + 1: [] for i in range(groups)}
    impact_cost_rates: List[float] = []
    transaction_cost_rates: List[float] = []

    slippage_model_name = str(slippage_model or "").strip().lower()
    slippage_calc = None
    if slippage_model_name in _SLIPPAGE_MODEL_MAP:
        slippage_calc = SlippageCalculator(_SLIPPAGE_MODEL_MAP[slippage_model_name])

    stats_counter = {
        "input_codes": len(codes),
        "processed_codes": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_no_future_window": 0,
        "skipped_no_factor_value": 0,
        "skipped_invalid_return": 0,
        "skipped_untradable": 0,
        "periods_total": 0,
        "periods_effective": 0,
        "candidate_signals": 0,
        "filled_signals": 0,
    }
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]
    fetch_bars = max(factor_lookback + holding_days * 8 + 5, 120)

    for code in codes:
        klines = await db.get_klines(code, limit=fetch_bars)
        if not klines or len(klines) < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        closes = [k.get("close") for k in klines if isinstance(k, dict) and k.get("close") is not None]
        if len(closes) < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        closes = list(reversed([float(c) for c in closes]))
        volumes_raw = [k.get("volume", 0) for k in klines if isinstance(k, dict) and k.get("close") is not None]
        if len(volumes_raw) == len(closes):
            volumes = list(reversed([float(v or 0.0) for v in volumes_raw]))
        else:
            volumes = [0.0] * len(closes)

        financial = None
        if requires_financials:
            financial = _latest_financial_row(await db.get_financials(code, limit=1))
            if not financial:
                stats_counter["skipped_no_financials"] += 1
                continue

        stock_info = None
        try:
            stock_info = await db.get_stock_info(code)
        except Exception:
            stock_info = None

        tradability_mask = None
        if tradability_filter:
            tradability_mask = _build_tradability_mask_local(
                np.array(closes, dtype=np.float64),
                np.array(volumes, dtype=np.float64),
                code=code,
                is_st=is_st,
            )

        per_code_data[code] = {
            "closes": closes,
            "volumes": volumes,
            "financial": financial,
            "stock_info": stock_info,
            "tradability_mask": tradability_mask,
        }
        stats_counter["processed_codes"] += 1

    if len(per_code_data) < groups * 2:
        return fail(
            f"Not enough stocks for grouping: valid_codes={len(per_code_data)}, required>={groups * 2}, stats={stats_counter}"
        )

    min_series_len = min(len(v["closes"]) for v in per_code_data.values())
    start_t = factor_lookback - 1
    end_t = min_series_len - 1 - holding_days
    if end_t <= start_t:
        return fail(
            f"Not enough history for rolling grouped backtest: start_t={start_t}, end_t={end_t}, stats={stats_counter}"
        )

    period_indices = list(range(start_t, end_t + 1, rebalance_step))
    if max_periods > 0:
        period_indices = period_indices[-max_periods:]
    stats_counter["periods_total"] = len(period_indices)

    for t in period_indices:
        period_stock_data = []
        for code, pdata in per_code_data.items():
            closes = pdata["closes"]
            volumes = pdata["volumes"]
            financial = pdata["financial"]
            stock_info = pdata["stock_info"]

            if len(closes) <= t + holding_days:
                stats_counter["skipped_no_future_window"] += 1
                continue

            window = closes[t - factor_lookback + 1 : t + 1]
            factor_value = _calculate_factor_value(
                factor_name,
                window,
                financial=financial,
                stock_info=stock_info,
                period=min(factor_lookback, len(window)),
            )
            if factor_value is None or np.isnan(factor_value):
                stats_counter["skipped_no_factor_value"] += 1
                continue

            entry_idx = t
            exit_idx = t + holding_days
            entry_price = closes[entry_idx]
            exit_price = closes[exit_idx]
            if entry_price <= 0 or exit_price <= 0:
                stats_counter["skipped_invalid_return"] += 1
                continue

            stats_counter["candidate_signals"] += 1
            tradability_mask = pdata.get("tradability_mask")
            if tradability_filter and isinstance(tradability_mask, np.ndarray):
                entry_tradable = bool(tradability_mask[entry_idx]) if entry_idx < len(tradability_mask) else False
                exit_tradable = bool(tradability_mask[exit_idx]) if exit_idx < len(tradability_mask) else False
                if not (entry_tradable and exit_tradable):
                    stats_counter["skipped_untradable"] += 1
                    continue

            costed = _compute_trade_return_with_costs(
                entry_price=float(entry_price),
                exit_price=float(exit_price),
                entry_volume=float(volumes[entry_idx]) if entry_idx < len(volumes) else 0.0,
                exit_volume=float(volumes[exit_idx]) if exit_idx < len(volumes) else 0.0,
                commission=commission,
                slippage=slippage,
                slippage_calc=slippage_calc,
            )
            if not costed:
                stats_counter["skipped_invalid_return"] += 1
                continue

            stats_counter["filled_signals"] += 1
            impact_cost_rates.append(float(costed["impact_cost_rate"]))
            transaction_cost_rates.append(float(costed["transaction_cost_rate"]))
            period_stock_data.append(
                {
                    "code": code,
                    "factor_value": float(factor_value),
                    "return": float(costed["net_return"]),
                }
            )

        if len(period_stock_data) < groups * 2:
            continue

        period_stock_data.sort(key=lambda x: x["factor_value"])
        group_size = max(1, len(period_stock_data) // groups)
        period_group_returns = []
        for i in range(groups):
            start_idx = i * group_size
            end_idx = start_idx + group_size if i < groups - 1 else len(period_stock_data)
            group_stocks = period_stock_data[start_idx:end_idx]
            if not group_stocks:
                period_group_returns.append({"group": i + 1, "avg_return": 0.0, "stock_count": 0})
                continue

            avg_return = float(np.mean([s["return"] for s in group_stocks]))
            period_group_returns.append({"group": i + 1, "avg_return": avg_return, "stock_count": len(group_stocks)})
            group_return_series[i + 1].append(avg_return)
            group_stock_counts[i + 1].append(len(group_stocks))

        period_long_short = float(period_group_returns[-1]["avg_return"] - period_group_returns[0]["avg_return"])
        long_short_returns.append(period_long_short)
        period_results.append(
            {
                "period_index": int(t),
                "rebalance_window": {"entry_index": int(t), "exit_index": int(t + holding_days)},
                "long_short_return": period_long_short,
                "group_returns": period_group_returns,
                "stock_count": len(period_stock_data),
            }
        )
        stats_counter["periods_effective"] += 1

    if not long_short_returns:
        return fail(f"No effective rebalance periods generated, stats={stats_counter}")

    equity_curve = [1.0]
    for period_ret in long_short_returns:
        equity_curve.append(float(equity_curve[-1] * (1.0 + period_ret)))

    equity_arr = np.array(equity_curve, dtype=np.float64)
    peak = np.maximum.accumulate(equity_arr)
    drawdown = (peak - equity_arr) / np.where(peak > 0, peak, 1.0)
    max_drawdown = float(np.max(drawdown)) if drawdown.size > 0 else 0.0

    total_return = float(equity_curve[-1] - 1.0)
    total_days = max(1, holding_days * len(long_short_returns))
    annual_return = float((1.0 + total_return) ** (252.0 / total_days) - 1.0) if (1.0 + total_return) > 0 else -1.0

    returns_arr = np.array(long_short_returns, dtype=np.float64)
    mean_ret = float(np.mean(returns_arr)) if returns_arr.size > 0 else 0.0
    std_ret = float(np.std(returns_arr, ddof=1)) if returns_arr.size > 1 else 0.0
    sharpe_ratio = float((mean_ret / std_ret) * np.sqrt(252.0 / holding_days)) if std_ret > 0 else 0.0
    win_rate = float(np.sum(returns_arr > 0) / returns_arr.size) if returns_arr.size > 0 else 0.0

    group_returns = []
    for i in range(1, groups + 1):
        grets = group_return_series.get(i, [])
        gcounts = group_stock_counts.get(i, [])
        group_returns.append(
            {
                "group": i,
                "avg_return": float(np.mean(grets)) if grets else 0.0,
                "stock_count": int(np.mean(gcounts)) if gcounts else 0,
            }
        )

    candidate_signals = int(stats_counter.get("candidate_signals", 0))
    filled_signals = int(stats_counter.get("filled_signals", 0))
    fill_ratio = float(filled_signals / candidate_signals) if candidate_signals > 0 else 0.0
    untradable_ratio = float(
        stats_counter.get("skipped_untradable", 0) / candidate_signals
    ) if candidate_signals > 0 else 0.0

    return ok(
        {
            "factor": factor_name,
            "groups": groups,
            "holding_days": holding_days,
            "factor_lookback": factor_lookback,
            "group_returns": group_returns,
            "period_group_results": period_results,
            "period_long_short_returns": [float(v) for v in long_short_returns],
            "equity_curve": [float(v) for v in equity_curve],
            "long_short_return": float(mean_ret),
            "period_long_short_mean": float(mean_ret),
            "total_stocks": len(per_code_data),
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "costs": {
                "commission": float(commission),
                "slippage": float(slippage),
                "slippage_model": slippage_model_name if slippage_calc is not None else "",
                "avg_transaction_cost_rate": float(np.mean(transaction_cost_rates)) if transaction_cost_rates else 0.0,
                "avg_impact_cost_rate": float(np.mean(impact_cost_rates)) if impact_cost_rates else 0.0,
            },
            "tradability": {
                "enabled": bool(tradability_filter),
                "candidate_signals": candidate_signals,
                "filled_signals": filled_signals,
                "fill_ratio": fill_ratio,
                "untradable_ratio": untradable_ratio,
            },
            "stats": stats_counter,
            "source_chain": [
                "db.get_klines",
                "db.get_financials(optional)",
                "db.get_stock_info(optional)",
                "slippage(optional)",
                "tradability_filter(optional)",
                "numpy-grouping",
            ],
            "notes": "Grouped factor backtest uses rolling rebalances; max_drawdown is computed from the realized long-short equity curve.",
        }
    )


async def _build_factor_return_panels(
    codes: List[str],
    factor_name: str,
    db,
    *,
    factor_lookback: int,
    forward_period: int,
    panel_periods: int,
) -> Dict[str, Any]:
    """构建 OOS 验证所需的二维面板：factor_panel / return_panel。"""
    per_code_factors: Dict[str, List[float]] = {}
    per_code_returns: Dict[str, List[float]] = {}
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]
    stats = {
        "input_codes": len(codes),
        "processed_codes": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_short_series": 0,
    }

    fetch_bars = max(80, panel_periods + factor_lookback + forward_period + 20)

    for code in codes:
        klines = await db.get_klines(code, limit=fetch_bars)
        if not klines or len(klines) < (factor_lookback + forward_period + 5):
            stats["skipped_no_kline"] += 1
            continue

        closes = [k.get("close") for k in klines if isinstance(k, dict) and k.get("close") is not None]
        if len(closes) < (factor_lookback + forward_period + 5):
            stats["skipped_no_kline"] += 1
            continue

        # 数据库通常最新在前，反转到时间正序
        closes = list(reversed([float(c) for c in closes]))

        financial = None
        if requires_financials:
            financial = _latest_financial_row(await db.get_financials(code, limit=1))
            if not financial:
                stats["skipped_no_financials"] += 1
                continue

        stock_info = None
        try:
            stock_info = await db.get_stock_info(code)
        except Exception:
            stock_info = None

        factors_one: List[float] = []
        returns_one: List[float] = []

        start_t = factor_lookback - 1
        end_t = len(closes) - 1 - forward_period
        for t in range(start_t, end_t + 1):
            window = closes[t - factor_lookback + 1 : t + 1]
            fv = _calculate_factor_value(
                factor_name,
                window,
                financial=financial,
                stock_info=stock_info,
                period=min(factor_lookback, len(window)),
            )
            p0 = closes[t]
            p1 = closes[t + forward_period]
            if fv is None or np.isnan(fv) or p0 <= 0:
                continue
            ret = (p1 - p0) / p0
            if not np.isfinite(ret):
                continue
            factors_one.append(float(fv))
            returns_one.append(float(ret))

        if len(factors_one) < max(30, panel_periods // 2):
            stats["skipped_short_series"] += 1
            continue

        per_code_factors[code] = factors_one
        per_code_returns[code] = returns_one
        stats["processed_codes"] += 1

    if len(per_code_factors) < 5:
        return fail(f"Not enough valid codes for panel build, stats={stats}")

    common_len = min(len(v) for v in per_code_factors.values())
    common_len = min(common_len, panel_periods)
    if common_len < 30:
        return fail(f"Panel periods too short after alignment: {common_len}, stats={stats}")

    used_codes = sorted(per_code_factors.keys())
    factor_panel = np.array([per_code_factors[c][-common_len:] for c in used_codes], dtype=np.float64).T
    return_panel = np.array([per_code_returns[c][-common_len:] for c in used_codes], dtype=np.float64).T

    return ok(
        {
            "factor_panel": factor_panel,
            "return_panel": return_panel,
            "codes": used_codes,
            "periods": int(common_len),
            "stats": stats,
        }
    )


async def run_factor_oos_validation(
    codes: List[str],
    factor: str,
    *,
    factor_lookback: int = 20,
    forward_period: int = 20,
    panel_periods: int = 180,
    wf_train_window: int = 60,
    wf_test_window: int = 20,
    wf_step: Optional[int] = None,
    kfold_n_folds: int = 5,
    kfold_purge_gap: int = 5,
    bootstrap_n: int = 1000,
    bootstrap_confidence: float = 0.95,
) -> Dict[str, Any]:
    """P0-A: 统一样本外验证工具（Walk-Forward + Purged KFold + Bootstrap CI）。"""
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")
    if not codes:
        return fail("codes is required")

    db = get_db()
    panel_resp = await _build_factor_return_panels(
        codes=codes,
        factor_name=factor_name,
        db=db,
        factor_lookback=max(2, int(factor_lookback)),
        forward_period=max(1, int(forward_period)),
        panel_periods=max(60, int(panel_periods)),
    )
    if not panel_resp.get("success"):
        return panel_resp

    pdata = panel_resp.get("data", {})
    factor_panel = pdata["factor_panel"]
    return_panel = pdata["return_panel"]

    pipeline = FactorValidationPipeline(
        wf_train_window=max(20, int(wf_train_window)),
        wf_test_window=max(5, int(wf_test_window)),
        wf_step=(None if wf_step in (None, 0) else int(wf_step)),
        kfold_n_folds=max(3, int(kfold_n_folds)),
        kfold_purge_gap=max(0, int(kfold_purge_gap)),
        bootstrap_n=max(200, int(bootstrap_n)),
        bootstrap_confidence=max(0.80, min(0.999, float(bootstrap_confidence))),
    )
    report = pipeline.run(
        factor_panel=factor_panel,
        return_panel=return_panel,
        factor_name=factor_name,
    )

    return ok(
        {
            "factor": factor_name,
            "validation_report": report,
            "panel_info": {
                "n_periods": int(pdata.get("periods", 0)),
                "n_stocks": int(len(pdata.get("codes", []))),
                "codes": pdata.get("codes", []),
                "factor_lookback": int(factor_lookback),
                "forward_period": int(forward_period),
            },
            "stats": pdata.get("stats", {}),
            "source_chain": [
                "db.get_klines",
                "db.get_financials(optional)",
                "db.get_stock_info(optional)",
                "validation.FactorValidationPipeline.run",
            ],
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
                "sub_factors": meta.get("sub_factors", []),
                "aliases": meta.get("aliases", []),
                "status": "supported",
            }
            for name, meta in SUPPORTED_FACTORS.items()
            if category_key in ("all", meta["category"])
        ]
        return ok({
            "factors": factors,
            "count": len(factors),
            "supported_factors": sorted(SUPPORTED_FACTORS.keys()),
            "total_categories": len(SUPPORTED_FACTORS),
            "note": "Factor library includes 8 categories: fundamental(4), technical(3), risk(1).",
        })

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

            stock_info = None
            try:
                stock_info = await db.get_stock_info(code)
            except Exception:
                stock_info = None

            value = _calculate_factor_value(
                factor_name,
                closes,
                financial=financial,
                stock_info=stock_info,
                period=DEFAULT_FACTOR_LOOKBACK,
            )
            if value is None or np.isnan(value):
                if factor_name == "growth":
                    return fail(
                        "Failed to calculate factor: growth (missing growth fields, expected one of "
                        f"{', '.join(REVENUE_GROWTH_KEYS)} or {', '.join(PROFIT_GROWTH_KEYS)})"
                    )
                if factor_name == "size":
                    return fail(
                        "Failed to calculate factor: size (missing market cap in stock_info/financials, expected one of "
                        f"{', '.join(MARKET_CAP_KEYS)})"
                    )
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
    async def calculate_factor_ic(
        codes: list,
        factor: str,
        period: int = 20,
        enable_neutralization: bool = True,
        bootstrap_n: int = 1000,
        bootstrap_confidence: float = 0.95,
    ):
        """Calculate dual information coefficient (Normal IC + Rank IC) by cross-section."""
        try:
            return await run_factor_ic_analysis(
                codes=codes,
                factor=factor,
                period=period,
                enable_neutralization=enable_neutralization,
                bootstrap_n=bootstrap_n,
                bootstrap_confidence=bootstrap_confidence,
            )
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def backtest_factor(
        codes: list,
        factor: str,
        groups: int = 5,
        holding_days: int = 20,
        commission: float = 0.0003,
        slippage: float = 0.0,
        slippage_model: str = "",
        tradability_filter: bool = False,
        is_st: bool = False,
        rebalance_step: int = 0,
        max_periods: int = 0,
    ):
        """Run grouped factor backtest on a stock universe."""
        try:
            return await run_factor_group_backtest(
                codes=codes,
                factor=factor,
                groups=groups,
                holding_days=holding_days,
                factor_lookback=DEFAULT_FACTOR_LOOKBACK,
                commission=commission,
                slippage=slippage,
                slippage_model=slippage_model,
                tradability_filter=tradability_filter,
                is_st=is_st,
                rebalance_step=rebalance_step,
                max_periods=max_periods,
            )
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def validate_factor_oos(
        codes: list,
        factor: str,
        factor_lookback: int = 20,
        forward_period: int = 20,
        panel_periods: int = 180,
        wf_train_window: int = 60,
        wf_test_window: int = 20,
        wf_step: int = 0,
        kfold_n_folds: int = 5,
        kfold_purge_gap: int = 5,
        bootstrap_n: int = 1000,
        bootstrap_confidence: float = 0.95,
    ):
        """P0-A: Unified OOS validation (Walk-Forward + Purged KFold + Bootstrap CI)."""
        try:
            return await run_factor_oos_validation(
                codes=codes,
                factor=factor,
                factor_lookback=factor_lookback,
                forward_period=forward_period,
                panel_periods=panel_periods,
                wf_train_window=wf_train_window,
                wf_test_window=wf_test_window,
                wf_step=(None if int(wf_step or 0) == 0 else int(wf_step)),
                kfold_n_folds=kfold_n_folds,
                kfold_purge_gap=kfold_purge_gap,
                bootstrap_n=bootstrap_n,
                bootstrap_confidence=bootstrap_confidence,
            )
        except Exception as e:
            return fail(str(e))
