"""Quant factor tools."""

import asyncio
import os
import time
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
    # ── 技术类扩展 ──
    "mom_1d": {
        "category": "technical",
        "description": "1日动量",
        "requires_financials": False,
        "sub_factors": ["return_1d"],
        "aliases": ["daily_return"],
    },
    "mom_5d": {
        "category": "technical",
        "description": "5日动量",
        "requires_financials": False,
        "sub_factors": ["return_5d"],
        "aliases": ["weekly_momentum"],
    },
    "mom_10d": {
        "category": "technical",
        "description": "10日动量",
        "requires_financials": False,
        "sub_factors": ["return_10d"],
        "aliases": ["biweekly_momentum"],
    },
    "mom_60d": {
        "category": "technical",
        "description": "60日动量",
        "requires_financials": False,
        "sub_factors": ["return_60d"],
        "aliases": ["quarterly_momentum"],
    },
    "rsi_14": {
        "category": "technical",
        "description": "14日RSI",
        "requires_financials": False,
        "sub_factors": ["rsi"],
        "aliases": ["rsi", "relative_strength"],
    },
    "rsi_6": {
        "category": "technical",
        "description": "6日RSI",
        "requires_financials": False,
        "sub_factors": ["rsi_short"],
        "aliases": ["rsi_fast"],
    },
    "macd_signal": {
        "category": "technical",
        "description": "MACD信号线",
        "requires_financials": False,
        "sub_factors": ["macd", "signal_line"],
        "aliases": ["macd"],
    },
    "macd_histogram": {
        "category": "technical",
        "description": "MACD柱状图",
        "requires_financials": False,
        "sub_factors": ["macd_hist"],
        "aliases": ["macd_bar"],
    },
    "willr_14": {
        "category": "technical",
        "description": "14日威廉指标",
        "requires_financials": False,
        "sub_factors": ["williams_r"],
        "aliases": ["williams_r", "wr"],
    },
    "cci_20": {
        "category": "technical",
        "description": "20日CCI",
        "requires_financials": False,
        "sub_factors": ["cci"],
        "aliases": ["commodity_channel"],
    },
    "mfi_14": {
        "category": "technical",
        "description": "14日资金流量指标",
        "requires_financials": False,
        "sub_factors": ["money_flow"],
        "aliases": ["money_flow_index"],
    },
    "stoch_k": {
        "category": "technical",
        "description": "随机指标K值",
        "requires_financials": False,
        "sub_factors": ["stochastic_k"],
        "aliases": ["kdj_k"],
    },
    "stoch_d": {
        "category": "technical",
        "description": "随机指标D值",
        "requires_financials": False,
        "sub_factors": ["stochastic_d"],
        "aliases": ["kdj_d"],
    },
    "roc_10": {
        "category": "technical",
        "description": "10日变动率",
        "requires_financials": False,
        "sub_factors": ["rate_of_change"],
        "aliases": ["roc"],
    },
    "roc_20": {
        "category": "technical",
        "description": "20日变动率",
        "requires_financials": False,
        "sub_factors": ["rate_of_change_20"],
        "aliases": ["roc_monthly"],
    },
    # ── 波动类扩展 ──
    "vol_5d": {
        "category": "risk",
        "description": "5日波动率",
        "requires_financials": False,
        "sub_factors": ["realized_vol_5d"],
        "aliases": ["short_vol"],
    },
    "vol_10d": {
        "category": "risk",
        "description": "10日波动率",
        "requires_financials": False,
        "sub_factors": ["realized_vol_10d"],
        "aliases": ["biweekly_vol"],
    },
    "vol_60d": {
        "category": "risk",
        "description": "60日波动率",
        "requires_financials": False,
        "sub_factors": ["realized_vol_60d"],
        "aliases": ["quarterly_vol"],
    },
    "atr_14": {
        "category": "risk",
        "description": "14日ATR",
        "requires_financials": False,
        "sub_factors": ["average_true_range"],
        "aliases": ["atr"],
    },
    "atr_20": {
        "category": "risk",
        "description": "20日ATR",
        "requires_financials": False,
        "sub_factors": ["average_true_range_20"],
        "aliases": ["atr_monthly"],
    },
    "bollinger_width": {
        "category": "risk",
        "description": "布林带宽度",
        "requires_financials": False,
        "sub_factors": ["boll_width"],
        "aliases": ["bband_width", "bb_width"],
    },
    "downside_vol": {
        "category": "risk",
        "description": "下行波动率",
        "requires_financials": False,
        "sub_factors": ["downside_deviation"],
        "aliases": ["downside_risk"],
    },
    # ── 量价类扩展 ──
    "volume_ratio": {
        "category": "volume",
        "description": "量比(5日/20日)",
        "requires_financials": False,
        "sub_factors": ["vol_ratio_5_20"],
        "aliases": ["vol_ratio"],
    },
    "obv_slope": {
        "category": "volume",
        "description": "OBV斜率",
        "requires_financials": False,
        "sub_factors": ["on_balance_volume_slope"],
        "aliases": ["obv_trend"],
    },
    "vwap_deviation": {
        "category": "volume",
        "description": "VWAP偏离度",
        "requires_financials": False,
        "sub_factors": ["vwap_dev"],
        "aliases": ["vwap_diff"],
    },
    "turnover_5d": {
        "category": "volume",
        "description": "5日换手率",
        "requires_financials": False,
        "sub_factors": ["turnover_rate_5d"],
        "aliases": ["short_turnover"],
    },
    "turnover_20d": {
        "category": "volume",
        "description": "20日换手率",
        "requires_financials": False,
        "sub_factors": ["turnover_rate_20d"],
        "aliases": ["monthly_turnover"],
    },
    # ── 基本面扩展 ──
    "pe_ttm": {
        "category": "fundamental",
        "description": "市盈率TTM",
        "requires_financials": True,
        "sub_factors": ["pe_ratio"],
        "aliases": ["pe", "price_earnings"],
    },
    "pb_mrq": {
        "category": "fundamental",
        "description": "市净率MRQ",
        "requires_financials": True,
        "sub_factors": ["pb_ratio"],
        "aliases": ["pb", "price_book"],
    },
    "ps_ttm": {
        "category": "fundamental",
        "description": "市销率TTM",
        "requires_financials": True,
        "sub_factors": ["ps_ratio"],
        "aliases": ["ps", "price_sales"],
    },
    "roe_ttm": {
        "category": "fundamental",
        "description": "净资产收益率TTM",
        "requires_financials": True,
        "sub_factors": ["roe"],
        "aliases": ["return_on_equity"],
    },
    "roa_ttm": {
        "category": "fundamental",
        "description": "总资产收益率TTM",
        "requires_financials": True,
        "sub_factors": ["roa"],
        "aliases": ["return_on_assets"],
    },
    "gross_margin": {
        "category": "fundamental",
        "description": "毛利率",
        "requires_financials": True,
        "sub_factors": ["gross_profit_margin"],
        "aliases": ["gpm"],
    },
    "net_margin": {
        "category": "fundamental",
        "description": "净利率",
        "requires_financials": True,
        "sub_factors": ["net_profit_margin"],
        "aliases": ["npm"],
    },
    "debt_to_equity": {
        "category": "fundamental",
        "description": "资产负债率",
        "requires_financials": True,
        "sub_factors": ["debt_ratio"],
        "aliases": ["leverage", "d_e_ratio"],
    },
    "revenue_growth_yoy": {
        "category": "fundamental",
        "description": "营收同比增长率",
        "requires_financials": True,
        "sub_factors": ["revenue_growth"],
        "aliases": ["sales_growth"],
    },
    "dividend_yield": {
        "category": "fundamental",
        "description": "股息率",
        "requires_financials": True,
        "sub_factors": ["div_yield"],
        "aliases": ["yield", "dps"],
    },
    # ── 另类因子 ──
    "sentiment_score": {
        "category": "alternative",
        "description": "情绪得分",
        "requires_financials": False,
        "sub_factors": ["news_sentiment", "social_sentiment"],
        "aliases": ["sentiment"],
    },
    "capital_flow": {
        "category": "alternative",
        "description": "资金流向得分",
        "requires_financials": False,
        "sub_factors": ["net_inflow", "main_force_flow"],
        "aliases": ["money_flow"],
    },
    "north_flow": {
        "category": "alternative",
        "description": "北向资金得分",
        "requires_financials": False,
        "sub_factors": ["northbound_net"],
        "aliases": ["northbound"],
    },
    "institutional_flow": {
        "category": "alternative",
        "description": "机构资金流向",
        "requires_financials": False,
        "sub_factors": ["inst_net_buy"],
        "aliases": ["institution_flow"],
    },
    "event_intensity": {
        "category": "alternative",
        "description": "事件强度",
        "requires_financials": False,
        "sub_factors": ["event_count", "event_impact"],
        "aliases": ["event_score"],
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


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() not in {"0", "false", "off", "no", "n"}


def _env_int(name: str, default: int, *, min_value: int = 1, max_value: int = 20) -> int:
    raw = os.getenv(name)
    try:
        val = int(str(raw).strip()) if raw is not None else int(default)
    except Exception:
        val = int(default)
    return max(min_value, min(max_value, val))


_QUANT_BATCH_FETCH_ENABLED = _env_flag("QUANT_BATCH_FETCH_ENABLED", True)
_QUANT_PREFETCH_CONCURRENCY = _env_int("QUANT_PREFETCH_CONCURRENCY", 8, min_value=1, max_value=20)
_QUANT_PERF_BREAKDOWN_ENABLED = _env_flag("QUANT_PERF_BREAKDOWN_ENABLED", True)

_PERF_STAGE_KEYS = ("fetch", "factor", "ic", "oos", "robust", "backtest", "serialize")


def _new_run_cache() -> Dict[str, Any]:
    return {
        "panels": {},
        "stats": {
            "panel_cache_hits": 0,
            "panel_cache_misses": 0,
            "duplicate_reads": 0,
        },
    }


def _new_perf_tracker(enabled: bool = True) -> Dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "timings": {k: 0.0 for k in _PERF_STAGE_KEYS},
    }


def _perf_add(perf: Dict[str, Any], stage: str, elapsed: float) -> None:
    if not isinstance(perf, dict):
        return
    if not bool(perf.get("enabled", False)):
        return
    if stage not in perf.get("timings", {}):
        return
    perf["timings"][stage] = float(perf["timings"][stage]) + max(0.0, float(elapsed))


def _get_or_build_market_panel(
    run_cache: Dict[str, Any],
    code: str,
    klines: List[Dict[str, Any]],
    *,
    chronological: bool,
    include_volume: bool = False,
    include_returns: bool = False,
) -> Dict[str, Any]:
    cache = run_cache.setdefault("panels", {})
    stats_meta = run_cache.setdefault(
        "stats",
        {"panel_cache_hits": 0, "panel_cache_misses": 0, "duplicate_reads": 0},
    )
    key = f"{str(code)}|c={int(chronological)}|v={int(include_volume)}|r={int(include_returns)}"

    cached = cache.get(key)
    if isinstance(cached, dict):
        stats_meta["panel_cache_hits"] = int(stats_meta.get("panel_cache_hits", 0)) + 1
        stats_meta["duplicate_reads"] = int(stats_meta.get("duplicate_reads", 0)) + 1
        return cached

    arrs = ICFactorAnalyzer.klines_to_ndarrays(
        klines=klines,
        chronological=chronological,
        include_volume=include_volume,
        include_returns=include_returns,
    )
    closes_arr = arrs.get("closes")
    if not isinstance(closes_arr, np.ndarray):
        closes_arr = np.asarray(closes_arr or [], dtype=np.float64)
    closes_arr = closes_arr.astype(np.float64, copy=False)

    panel = {
        "closes_arr": closes_arr,
        "closes": closes_arr.tolist(),
    }

    if include_volume:
        volumes_arr = arrs.get("volumes")
        if not isinstance(volumes_arr, np.ndarray):
            volumes_arr = np.asarray(volumes_arr or [], dtype=np.float64)
        volumes_arr = volumes_arr.astype(np.float64, copy=False)
        if volumes_arr.shape[0] != closes_arr.shape[0]:
            volumes_arr = np.zeros(closes_arr.shape[0], dtype=np.float64)
        panel["volumes_arr"] = volumes_arr
        panel["volumes"] = volumes_arr.tolist()

    if include_returns:
        returns_arr = arrs.get("returns")
        if not isinstance(returns_arr, np.ndarray):
            returns_arr = np.asarray(returns_arr or [], dtype=np.float64)
        returns_arr = returns_arr.astype(np.float64, copy=False)
        panel["returns_arr"] = returns_arr
        panel["returns"] = returns_arr.tolist()

    cache[key] = panel
    stats_meta["panel_cache_misses"] = int(stats_meta.get("panel_cache_misses", 0)) + 1
    return panel


def _build_perf_breakdown(
    perf: Dict[str, Any],
    *,
    prefetch_meta: Optional[Dict[str, Any]] = None,
    run_cache: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not bool((perf or {}).get("enabled", False)):
        return None

    timings_raw = (perf or {}).get("timings", {})
    timings = {k: round(float(timings_raw.get(k, 0.0)), 6) for k in _PERF_STAGE_KEYS}
    total_seconds = round(float(sum(timings.values())), 6)

    prefetch = prefetch_meta or {}
    memo_hits = prefetch.get("memo_hits") if isinstance(prefetch.get("memo_hits"), dict) else {}
    run_stats = (run_cache or {}).get("stats") if isinstance(run_cache, dict) else {}
    run_stats = run_stats if isinstance(run_stats, dict) else {}

    kline_req = int(prefetch.get("kline_batch_hits", 0)) + int(prefetch.get("kline_single_fetches", 0))
    stock_req = int(prefetch.get("stock_info_fetches", 0))
    fin_req = int(prefetch.get("financial_fetches", 0))
    total_req = int(kline_req + stock_req + fin_req)

    return {
        "enabled": True,
        "timings": timings,
        "total_seconds": total_seconds,
        "data_stats": {
            "request_counts": {
                "kline_requests": int(kline_req),
                "stock_info_requests": int(stock_req),
                "financial_requests": int(fin_req),
                "total_requests": int(total_req),
            },
            "batch_hits": {
                "kline_batch_hits": int(prefetch.get("kline_batch_hits", 0)),
                "kline_batch_used": bool(prefetch.get("kline_batch_used", False)),
            },
            "repeated_reads": {
                "prefetch_memo_hits": int(sum(int(v or 0) for v in memo_hits.values())) if memo_hits else 0,
                "panel_cache_hits": int(run_stats.get("panel_cache_hits", 0)),
                "duplicate_reads": int(run_stats.get("duplicate_reads", 0)),
            },
        },
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


def _normalize_codes_for_prefetch(codes: List[Any]) -> List[str]:
    seen = set()
    normalized: List[str] = []
    for code in codes or []:
        code_str = str(code or "").strip()
        if not code_str or code_str in seen:
            continue
        seen.add(code_str)
        normalized.append(code_str)
    return normalized


async def _prefetch_market_data(
    db: Any,
    codes: List[Any],
    *,
    need_financials: bool,
    kline_limit: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    fetch_concurrency: Optional[int] = None,
    memo: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """P0: 批量优先 + 并发回退的统一预取层，减少重复 DB 查询。"""
    code_list = _normalize_codes_for_prefetch(codes)
    cache = memo if isinstance(memo, dict) else {}
    concurrency = max(1, min(int(fetch_concurrency or _QUANT_PREFETCH_CONCURRENCY), 20))

    result: Dict[str, Dict[str, Any]] = {code: {} for code in code_list}
    meta: Dict[str, Any] = {
        "codes": len(code_list),
        "batch_enabled": bool(_QUANT_BATCH_FETCH_ENABLED),
        "fetch_concurrency": int(concurrency),
        "kline_batch_used": False,
        "kline_batch_hits": 0,
        "kline_single_fetches": 0,
        "stock_info_fetches": 0,
        "financial_fetches": 0,
        "memo_hits": {"klines": 0, "stock_info": 0, "financial": 0},
    }

    for code in code_list:
        cached = cache.get(code)
        if not isinstance(cached, dict):
            continue
        for key in ("klines", "stock_info", "financial"):
            if key in cached:
                result[code][key] = cached.get(key)
                meta["memo_hits"][key] += 1

    # 1) Kline：优先批量接口
    missing_klines = [c for c in code_list if "klines" not in result[c]]
    if missing_klines and _QUANT_BATCH_FETCH_ENABLED:
        batch_method = getattr(db, "get_klines_batch", None)
        if callable(batch_method):
            try:
                limit_arg = int(kline_limit) if int(kline_limit or 0) > 0 else None
                batch_rows = await batch_method(missing_klines, start_date, end_date, limit_arg)
                meta["kline_batch_used"] = True
                rows_dict = batch_rows if isinstance(batch_rows, dict) else {}
                for code in missing_klines:
                    rows = rows_dict.get(code, [])
                    if isinstance(rows, list) and rows:
                        result[code]["klines"] = rows
                        meta["kline_batch_hits"] += 1
            except Exception:
                pass

    # 2) Kline：并发回退
    missing_klines = [c for c in code_list if "klines" not in result[c]]
    if missing_klines:
        semaphore = asyncio.Semaphore(concurrency)

        async def _fetch_kline_one(code: str) -> tuple[str, List[Dict[str, Any]]]:
            async with semaphore:
                try:
                    if start_date is not None or end_date is not None:
                        rows = await db.get_klines(code, start_date, end_date, kline_limit)
                    else:
                        rows = await db.get_klines(code, limit=kline_limit)
                except Exception:
                    rows = []
                return code, rows if isinstance(rows, list) else []

        batch = await asyncio.gather(*[_fetch_kline_one(code) for code in missing_klines], return_exceptions=True)
        for item in batch:
            if isinstance(item, Exception):
                continue
            code, rows = item
            result[code]["klines"] = rows
            meta["kline_single_fetches"] += 1

    # 3) stock_info 并发获取（每个 run 内 memo 复用）
    missing_infos = [c for c in code_list if "stock_info" not in result[c]]
    if missing_infos:
        semaphore = asyncio.Semaphore(concurrency)

        async def _fetch_info_one(code: str) -> tuple[str, Any]:
            async with semaphore:
                try:
                    payload = await db.get_stock_info(code)
                except Exception:
                    payload = None
                return code, payload

        batch = await asyncio.gather(*[_fetch_info_one(code) for code in missing_infos], return_exceptions=True)
        for item in batch:
            if isinstance(item, Exception):
                continue
            code, payload = item
            result[code]["stock_info"] = payload
            meta["stock_info_fetches"] += 1

    # 4) financial 并发获取（仅在因子需要时）
    if need_financials:
        missing_fin = [c for c in code_list if "financial" not in result[c]]
        if missing_fin:
            semaphore = asyncio.Semaphore(concurrency)

            async def _fetch_fin_one(code: str) -> tuple[str, Optional[Dict[str, Any]]]:
                async with semaphore:
                    try:
                        payload = _latest_financial_row(await db.get_financials(code, limit=1))
                    except Exception:
                        payload = None
                    return code, payload

            batch = await asyncio.gather(*[_fetch_fin_one(code) for code in missing_fin], return_exceptions=True)
            for item in batch:
                if isinstance(item, Exception):
                    continue
                code, payload = item
                result[code]["financial"] = payload
                meta["financial_fetches"] += 1

    # 5) 标准化输出并写回 memo（同请求内复用）
    for code in code_list:
        code_data = result.setdefault(code, {})
        if "klines" not in code_data or not isinstance(code_data.get("klines"), list):
            code_data["klines"] = []
        if "stock_info" not in code_data:
            code_data["stock_info"] = None
        if "financial" not in code_data:
            code_data["financial"] = None

        bucket = cache.setdefault(code, {})
        bucket["klines"] = code_data["klines"]
        bucket["stock_info"] = code_data["stock_info"]
        bucket["financial"] = code_data["financial"]

    return {"data": result, "meta": meta}


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    alpha = 2.0 / (period + 1)
    result = np.empty_like(data)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


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

    # ── 短周期动量 ──
    if factor_name in ("mom_1d", "mom_5d", "mom_10d", "mom_60d"):
        period_map = {"mom_1d": 1, "mom_5d": 5, "mom_10d": 10, "mom_60d": 60}
        p = period_map[factor_name]
        if len(closes) < p + 1:
            return None
        return float((closes[-1] - closes[-(p + 1)]) / closes[-(p + 1)]) if closes[-(p + 1)] > 0 else None

    # ── RSI ──
    if factor_name in ("rsi_14", "rsi_6"):
        rsi_period = 14 if factor_name == "rsi_14" else 6
        if len(closes) < rsi_period + 1:
            return None
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(d, 0) for d in deltas[-rsi_period:]]
        losses = [max(-d, 0) for d in deltas[-rsi_period:]]
        avg_gain = sum(gains) / rsi_period
        avg_loss = sum(losses) / rsi_period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100.0 - 100.0 / (1.0 + rs))

    # ── MACD ──
    if factor_name in ("macd_signal", "macd_histogram"):
        if len(closes) < 26:
            return None
        arr = np.array(closes, dtype=np.float64)
        ema12 = _ema(arr, 12)
        ema26 = _ema(arr, 26)
        dif = ema12 - ema26
        dea = _ema(dif, 9)
        if factor_name == "macd_signal":
            return float(dea[-1])
        return float((dif[-1] - dea[-1]) * 2)

    # ── Williams %R ──
    if factor_name == "willr_14":
        if len(closes) < 14:
            return None
        window = closes[-14:]
        highest = max(window)
        lowest = min(window)
        if highest == lowest:
            return 0.0
        return float((highest - closes[-1]) / (highest - lowest) * -100)

    # ── CCI ──
    if factor_name == "cci_20":
        if len(closes) < 20:
            return None
        window = closes[-20:]
        tp = sum(window) / len(window)
        md = sum(abs(c - tp) for c in window) / len(window)
        if md == 0:
            return 0.0
        return float((closes[-1] - tp) / (0.015 * md))

    # ── Stochastic K/D ──
    if factor_name in ("stoch_k", "stoch_d"):
        if len(closes) < 14:
            return None
        window = closes[-14:]
        lowest = min(window)
        highest = max(window)
        if highest == lowest:
            return 50.0
        k = (closes[-1] - lowest) / (highest - lowest) * 100
        if factor_name == "stoch_k":
            return float(k)
        # D = 3-day SMA of K (approximate with last 3 K values)
        if len(closes) < 16:
            return float(k)
        k_vals = []
        for i in range(3):
            w = closes[-(14 + i):-i] if i > 0 else closes[-14:]
            lo, hi = min(w), max(w)
            k_vals.append((w[-1] - lo) / (hi - lo) * 100 if hi != lo else 50.0)
        return float(sum(k_vals) / len(k_vals))

    # ── ROC ──
    if factor_name in ("roc_10", "roc_20"):
        p = 10 if factor_name == "roc_10" else 20
        if len(closes) < p + 1:
            return None
        prev = closes[-(p + 1)]
        return float((closes[-1] - prev) / prev * 100) if prev > 0 else None

    # ── MFI (simplified, uses closes as proxy) ──
    if factor_name == "mfi_14":
        if len(closes) < 15:
            return None
        pos_flow = 0.0
        neg_flow = 0.0
        for i in range(-14, 0):
            if closes[i] > closes[i - 1]:
                pos_flow += closes[i]
            else:
                neg_flow += abs(closes[i])
        if neg_flow == 0:
            return 100.0
        mfr = pos_flow / neg_flow
        return float(100.0 - 100.0 / (1.0 + mfr))

    # ── 波动率变体 ──
    if factor_name in ("vol_5d", "vol_10d", "vol_60d"):
        period_map = {"vol_5d": 5, "vol_10d": 10, "vol_60d": 60}
        p = period_map[factor_name]
        if len(closes) < p + 1:
            return None
        window = np.array(closes[-(p + 1):], dtype=np.float64)
        prev = window[:-1]
        curr = window[1:]
        valid = prev > 0
        if int(np.sum(valid)) < 2:
            return None
        rets = (curr[valid] - prev[valid]) / prev[valid]
        return float(np.std(rets, ddof=1) * np.sqrt(252.0))

    # ── ATR (simplified, uses close-to-close) ──
    if factor_name in ("atr_14", "atr_20"):
        p = 14 if factor_name == "atr_14" else 20
        if len(closes) < p + 1:
            return None
        trs = [abs(closes[i] - closes[i - 1]) for i in range(len(closes) - p, len(closes))]
        return float(sum(trs) / len(trs))

    # ── Bollinger Width ──
    if factor_name == "bollinger_width":
        if len(closes) < 20:
            return None
        window = closes[-20:]
        ma = sum(window) / 20
        std = (sum((c - ma) ** 2 for c in window) / 20) ** 0.5
        if ma == 0:
            return 0.0
        return float(4 * std / ma)

    # ── Downside Vol ──
    if factor_name == "downside_vol":
        if len(closes) < 21:
            return None
        window = np.array(closes[-21:], dtype=np.float64)
        rets = (window[1:] - window[:-1]) / np.where(window[:-1] > 0, window[:-1], 1.0)
        neg_rets = rets[rets < 0]
        if len(neg_rets) < 2:
            return 0.0
        return float(np.std(neg_rets, ddof=1) * np.sqrt(252.0))

    # ── Volume-based (simplified, use closes as proxy) ──
    if factor_name == "volume_ratio":
        if len(closes) < 20:
            return None
        vol5 = sum(abs(closes[i] - closes[i - 1]) for i in range(-5, 0)) / 5
        vol20 = sum(abs(closes[i] - closes[i - 1]) for i in range(-20, 0)) / 20
        return float(vol5 / vol20) if vol20 > 0 else None

    if factor_name == "obv_slope":
        if len(closes) < 20:
            return None
        obv = 0.0
        obv_series = [0.0]
        for i in range(-19, 0):
            if closes[i] > closes[i - 1]:
                obv += 1
            elif closes[i] < closes[i - 1]:
                obv -= 1
            obv_series.append(obv)
        x = np.arange(len(obv_series), dtype=np.float64)
        y = np.array(obv_series, dtype=np.float64)
        slope = float(np.polyfit(x, y, 1)[0])
        return slope

    if factor_name == "vwap_deviation":
        if len(closes) < 20:
            return None
        vwap = sum(closes[-20:]) / 20
        return float((closes[-1] - vwap) / vwap) if vwap > 0 else None

    if factor_name in ("turnover_5d", "turnover_20d"):
        if len(closes) < 20:
            return None
        p = 5 if factor_name == "turnover_5d" else 20
        changes = [abs(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(-p, 0) if closes[i - 1] > 0]
        return float(sum(changes) / len(changes)) if changes else None

    # ── 基本面单指标 ──
    if factor_name == "pe_ttm":
        if not financial:
            return None
        return _safe_float(financial.get("pe_ratio"), None)

    if factor_name == "pb_mrq":
        if not financial:
            return None
        return _safe_float(financial.get("pb_ratio"), None)

    if factor_name == "ps_ttm":
        if not financial:
            return None
        return _safe_float(financial.get("ps_ratio"), None)

    if factor_name == "roe_ttm":
        if not financial:
            return None
        return _safe_float(financial.get("roe"), None)

    if factor_name == "roa_ttm":
        if not financial:
            return None
        return _safe_float(financial.get("roa"), None)

    if factor_name == "gross_margin":
        if not financial:
            return None
        return _safe_float(financial.get("gross_margin"), None)

    if factor_name == "net_margin":
        if not financial:
            return None
        return _safe_float(financial.get("net_margin"), None)

    if factor_name == "debt_to_equity":
        if not financial:
            return None
        return _safe_float(financial.get("debt_ratio"), None)

    if factor_name == "revenue_growth_yoy":
        if not financial:
            return None
        return _first_valid_float(financial, REVENUE_GROWTH_KEYS)

    if factor_name == "dividend_yield":
        if not financial:
            return None
        for key in ("dividend_yield", "div_yield", "dps_yield"):
            val = _safe_float(financial.get(key), 0.0)
            if val > 0:
                return val
        return None

    # ── 另类因子 (placeholder — return None, computed externally) ──
    if factor_name in ("sentiment_score", "capital_flow", "north_flow", "institutional_flow", "event_intensity"):
        return None

    return None


async def run_factor_ic_analysis(
    codes: list,
    factor: str,
    period: int = 20,
    enable_neutralization: bool = True,
    bootstrap_n: int = 1000,
    bootstrap_confidence: float = 0.95,
    include_perf_breakdown: bool = True,
) -> Dict[str, Any]:
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

    if not codes:
        return fail("codes is required")

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
    lookback_period = max(2, int(period))
    db = get_db()
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]

    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=lookback_period + 30,
    )
    _perf_add(perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    prefetch_meta = prefetch_resp.get("meta", {})

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

    factor_stage_start = time.perf_counter()
    for code in codes:
        code_key = str(code or "").strip()
        code_data = prefetched.get(code_key, {})
        klines = code_data.get("klines") or []
        if not klines or len(klines) < lookback_period + 5:
            stats_counter["skipped_no_kline"] += 1
            continue

        panel = _get_or_build_market_panel(
            run_cache=run_cache,
            code=code_key,
            klines=klines,
            chronological=False,
            include_volume=False,
            include_returns=True,
        )
        closes = panel.get("closes") or []
        if len(closes) < lookback_period + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        financial = code_data.get("financial")
        if requires_financials and not financial:
            stats_counter["skipped_no_financials"] += 1
            continue

        stock_info = code_data.get("stock_info")

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
    _perf_add(perf, "factor", time.perf_counter() - factor_stage_start)

    sample_size = len(factor_values)
    if sample_size < 10:
        return fail(
            f"Not enough valid data for IC calculation: sample_size={sample_size}, "
            f"required>=10, stats={stats_counter}"
        )

    ic_stage_start = time.perf_counter()
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
    _perf_add(perf, "ic", time.perf_counter() - ic_stage_start)

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

    serialize_start = time.perf_counter()
    payload = {
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
        "prefetch": prefetch_meta,
        "neutralization": dual_ic.get("neutralization", {}),
        "source_chain": [
            "quant.prefetch_market_data",
            "db.get_klines_batch(optional)",
            "db.get_klines(fallback)",
            "db.get_financials(optional)",
            "db.get_stock_info",
            "factor_analysis.calculate_ic_dual",
            "validation.bootstrap_ic_ci",
        ],
        "params": {
            "enable_neutralization": bool(enable_neutralization),
            "bootstrap_n": bootstrap_n,
            "bootstrap_confidence": bootstrap_confidence,
        },
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=prefetch_meta,
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)


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
    include_perf_breakdown: bool = True,
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

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
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
    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=fetch_bars,
    )
    _perf_add(perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    prefetch_meta = prefetch_resp.get("meta", {})

    factor_stage_start = time.perf_counter()
    for code in codes:
        code_key = str(code or "").strip()
        code_data = prefetched.get(code_key, {})
        klines = code_data.get("klines") or []
        if not klines or len(klines) < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        panel = _get_or_build_market_panel(
            run_cache=run_cache,
            code=code_key,
            klines=klines,
            chronological=True,
            include_volume=True,
            include_returns=True,
        )
        closes_arr = panel.get("closes_arr")
        volumes_arr = panel.get("volumes_arr")
        if not isinstance(closes_arr, np.ndarray) or closes_arr.shape[0] < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue
        if not isinstance(volumes_arr, np.ndarray) or volumes_arr.shape[0] != closes_arr.shape[0]:
            volumes_arr = np.zeros(closes_arr.shape[0], dtype=np.float64)

        financial = code_data.get("financial")
        if requires_financials and not financial:
            stats_counter["skipped_no_financials"] += 1
            continue

        stock_info = code_data.get("stock_info")

        tradability_mask = None
        if tradability_filter:
            tradability_mask = _build_tradability_mask_local(
                closes_arr,
                volumes_arr,
                code=code_key,
                is_st=is_st,
            )

        per_code_data[code_key] = {
            "closes_arr": closes_arr,
            "volumes_arr": volumes_arr,
            "financial": financial,
            "stock_info": stock_info,
            "tradability_mask": tradability_mask,
        }
        stats_counter["processed_codes"] += 1
    _perf_add(perf, "factor", time.perf_counter() - factor_stage_start)

    if len(per_code_data) < groups * 2:
        return fail(
            f"Not enough stocks for grouping: valid_codes={len(per_code_data)}, required>={groups * 2}, stats={stats_counter}"
        )

    min_series_len = min(int(v["closes_arr"].shape[0]) for v in per_code_data.values())
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

    backtest_stage_start = time.perf_counter()
    for t in period_indices:
        period_stock_data = []
        for code, pdata in per_code_data.items():
            closes = pdata["closes_arr"]
            volumes = pdata["volumes_arr"]
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
                period=min(factor_lookback, int(window.shape[0])),
            )
            if factor_value is None or np.isnan(factor_value):
                stats_counter["skipped_no_factor_value"] += 1
                continue

            entry_idx = t
            exit_idx = t + holding_days
            entry_price = float(closes[entry_idx])
            exit_price = float(closes[exit_idx])
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
                entry_price=entry_price,
                exit_price=exit_price,
                entry_volume=float(volumes[entry_idx]) if entry_idx < int(volumes.shape[0]) else 0.0,
                exit_volume=float(volumes[exit_idx]) if exit_idx < int(volumes.shape[0]) else 0.0,
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
    _perf_add(perf, "backtest", time.perf_counter() - backtest_stage_start)

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

    serialize_start = time.perf_counter()
    payload = {
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
            "prefetch": prefetch_meta,
            "source_chain": [
                "quant.prefetch_market_data",
                "db.get_klines_batch(optional)",
                "db.get_klines(fallback)",
                "db.get_financials(optional)",
                "db.get_stock_info",
                "slippage(optional)",
                "tradability_filter(optional)",
                "numpy-grouping",
            ],
            "notes": "Grouped factor backtest uses rolling rebalances; max_drawdown is computed from the realized long-short equity curve.",
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=prefetch_meta,
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)


async def _build_factor_return_panels(
    codes: List[str],
    factor_name: str,
    db,
    *,
    factor_lookback: int,
    forward_period: int,
    panel_periods: int,
    run_cache: Optional[Dict[str, Any]] = None,
    perf: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建 OOS 验证所需的二维面板：factor_panel / return_panel。"""
    local_run_cache = run_cache if isinstance(run_cache, dict) else _new_run_cache()
    local_perf = perf if isinstance(perf, dict) else _new_perf_tracker(False)
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
    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=fetch_bars,
    )
    _perf_add(local_perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    factor_stage_start = time.perf_counter()

    for code in codes:
        code_key = str(code or "").strip()
        code_data = prefetched.get(code_key, {})
        klines = code_data.get("klines") or []
        if not klines or len(klines) < (factor_lookback + forward_period + 5):
            stats["skipped_no_kline"] += 1
            continue

        panel = _get_or_build_market_panel(
            run_cache=local_run_cache,
            code=code_key,
            klines=klines,
            chronological=True,
            include_volume=False,
            include_returns=True,
        )
        closes_arr = panel.get("closes_arr")
        if not isinstance(closes_arr, np.ndarray) or closes_arr.shape[0] < (factor_lookback + forward_period + 5):
            stats["skipped_no_kline"] += 1
            continue

        financial = code_data.get("financial")
        if requires_financials and not financial:
            stats["skipped_no_financials"] += 1
            continue

        stock_info = code_data.get("stock_info")

        factors_one: List[float] = []
        returns_one: List[float] = []

        start_t = factor_lookback - 1
        end_t = int(closes_arr.shape[0]) - 1 - forward_period
        for t in range(start_t, end_t + 1):
            window = closes_arr[t - factor_lookback + 1 : t + 1]
            fv = _calculate_factor_value(
                factor_name,
                window,
                financial=financial,
                stock_info=stock_info,
                period=min(factor_lookback, int(window.shape[0])),
            )
            p0 = float(closes_arr[t])
            p1 = float(closes_arr[t + forward_period])
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

        per_code_factors[code_key] = factors_one
        per_code_returns[code_key] = returns_one
        stats["processed_codes"] += 1
    _perf_add(local_perf, "factor", time.perf_counter() - factor_stage_start)

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
            "prefetch": prefetch_resp.get("meta", {}),
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
    validation_parallel: bool = True,
    max_workers: Optional[int] = None,
    bootstrap_mode: str = "",
    include_perf_breakdown: bool = True,
) -> Dict[str, Any]:
    """P0-A: 统一样本外验证工具（Walk-Forward + Purged KFold + Bootstrap CI）。"""
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")
    if not codes:
        return fail("codes is required")

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
    db = get_db()
    panel_resp = await _build_factor_return_panels(
        codes=codes,
        factor_name=factor_name,
        db=db,
        factor_lookback=max(2, int(factor_lookback)),
        forward_period=max(1, int(forward_period)),
        panel_periods=max(60, int(panel_periods)),
        run_cache=run_cache,
        perf=perf,
    )
    if not panel_resp.get("success"):
        return panel_resp

    pdata = panel_resp.get("data", {})
    factor_panel = pdata["factor_panel"]
    return_panel = pdata["return_panel"]

    bootstrap_mode_norm = str(bootstrap_mode or "").strip().lower()
    pipeline_bootstrap_n: Optional[int]
    if bootstrap_mode_norm in {"fast", "full"}:
        # In mode-driven execution, let validation service resolve fast/full presets.
        pipeline_bootstrap_n = None
    else:
        pipeline_bootstrap_n = max(200, int(bootstrap_n))

    pipeline = FactorValidationPipeline(
        wf_train_window=max(20, int(wf_train_window)),
        wf_test_window=max(5, int(wf_test_window)),
        wf_step=(None if wf_step in (None, 0) else int(wf_step)),
        kfold_n_folds=max(3, int(kfold_n_folds)),
        kfold_purge_gap=max(0, int(kfold_purge_gap)),
        bootstrap_n=pipeline_bootstrap_n,
        bootstrap_confidence=max(0.80, min(0.999, float(bootstrap_confidence))),
        validation_parallel=bool(validation_parallel),
        max_workers=max_workers,
        bootstrap_mode=bootstrap_mode_norm or None,
    )
    oos_stage_start = time.perf_counter()
    report = pipeline.run(
        factor_panel=factor_panel,
        return_panel=return_panel,
        factor_name=factor_name,
        validation_parallel=bool(validation_parallel),
        max_workers=max_workers,
        bootstrap_mode=bootstrap_mode_norm or None,
    )
    _perf_add(perf, "oos", time.perf_counter() - oos_stage_start)

    serialize_start = time.perf_counter()
    payload = {
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
            "prefetch": pdata.get("prefetch", {}),
            "source_chain": [
                "quant.prefetch_market_data",
                "db.get_klines_batch(optional)",
                "db.get_klines(fallback)",
                "db.get_financials(optional)",
                "db.get_stock_info",
                "validation.FactorValidationPipeline.run",
            ],
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=pdata.get("prefetch", {}),
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)


# ── P2-2: 因子稳健性检验 ──────────────────────────────────

async def run_factor_robustness_check(
    codes: List[str],
    factor: str,
    windows: Optional[List[int]] = None,
    param_variations: Optional[List[int]] = None,
    include_perf_breakdown: bool = True,
) -> Dict[str, Any]:
    """P2-2: 多窗口 IC 稳定性 + 参数敏感性 + 子样本一致性。"""
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}")
    if not codes:
        return fail("codes is required")

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
    windows = windows or [5, 10, 20, 60]
    param_variations = param_variations or [10, 20, 40, 60]
    db = get_db()
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]
    max_lookback = max([20] + [int(w) for w in windows] + [int(p) for p in param_variations])
    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=max_lookback + 30,
    )
    _perf_add(perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    prefetch_meta = prefetch_resp.get("meta", {})

    # ── 辅助：单窗口截面 IC（复用预取数据） ──
    def _cross_section_ic(sub_codes: List[str], lookback: int) -> Dict[str, Any]:
        fv: List[float] = []
        fr: List[float] = []
        lb = max(2, int(lookback))
        for code in sub_codes:
            code_key = str(code or "").strip()
            code_data = prefetched.get(code_key, {})
            klines = code_data.get("klines") or []
            if not klines or len(klines) < lb + 5:
                continue
            panel = _get_or_build_market_panel(
                run_cache=run_cache,
                code=code_key,
                klines=klines,
                chronological=False,
                include_volume=False,
                include_returns=True,
            )
            closes_arr = panel.get("closes_arr")
            if not isinstance(closes_arr, np.ndarray) or closes_arr.shape[0] < lb + 2:
                continue
            financial = code_data.get("financial")
            if requires_financials and not financial:
                continue
            stock_info = code_data.get("stock_info")
            val = _calculate_factor_value(
                factor_name,
                closes_arr[:lb],
                financial=financial,
                stock_info=stock_info,
                period=lb,
            )
            if val is None or np.isnan(val):
                continue
            ci = min(lb - 1, int(closes_arr.shape[0]) - 2)
            fi = min(ci + lb, int(closes_arr.shape[0]) - 1)
            p0 = float(closes_arr[ci]) if ci >= 0 else 0.0
            if fi <= ci or p0 <= 0:
                continue
            fv.append(float(val))
            fr.append(float((float(closes_arr[fi]) - p0) / p0))

        n = len(fv)
        if n < 10:
            return {"ic": 0.0, "rank_ic": 0.0, "sample_size": n, "significant": False}
        ic = float(np.corrcoef(fv, fr)[0, 1])
        rank_ic = float(stats.spearmanr(fv, fr).statistic)
        p_val = float(stats.spearmanr(fv, fr).pvalue)
        return {
            "ic": ic,
            "rank_ic": rank_ic,
            "p_value": p_val,
            "sample_size": n,
            "significant": bool(p_val < 0.05),
        }

    robust_stage_start = time.perf_counter()
    # ── 1) 多窗口 IC 稳定性 ──
    multi_window_results = {}
    for w in windows:
        multi_window_results[str(w)] = _cross_section_ic(codes, int(w))

    ic_values = [v["rank_ic"] for v in multi_window_results.values() if v["sample_size"] >= 10]
    window_stability = (
        float(1.0 - (np.std(ic_values) / (abs(np.mean(ic_values)) + 1e-9)))
        if len(ic_values) >= 2
        else 0.0
    )
    window_stability = max(0.0, min(1.0, window_stability))

    # ── 2) 参数敏感性 ──
    param_results = {}
    for p in param_variations:
        param_results[str(p)] = _cross_section_ic(codes, int(p))

    param_ics = [v["rank_ic"] for v in param_results.values() if v["sample_size"] >= 10]
    param_stability = (
        float(1.0 - (np.std(param_ics) / (abs(np.mean(param_ics)) + 1e-9)))
        if len(param_ics) >= 2
        else 0.0
    )
    param_stability = max(0.0, min(1.0, param_stability))

    # ── 3) 子样本一致性（前半 vs 后半） ──
    half = len(codes) // 2
    if half >= 5:
        codes_a, codes_b = codes[:half], codes[half:]
        sub_a = _cross_section_ic(codes_a, 20)
        sub_b = _cross_section_ic(codes_b, 20)
        same_sign = (sub_a.get("rank_ic", 0.0) * sub_b.get("rank_ic", 0.0)) > 0
        diff = abs(float(sub_a.get("rank_ic", 0.0)) - float(sub_b.get("rank_ic", 0.0)))
        subsample_consistency = 1.0 if same_sign and diff < 0.05 else (0.5 if same_sign else 0.0)
        subsample_detail = {
            "sub_a": {"rank_ic": float(sub_a.get("rank_ic", 0.0)), "sample_size": int(sub_a.get("sample_size", 0))},
            "sub_b": {"rank_ic": float(sub_b.get("rank_ic", 0.0)), "sample_size": int(sub_b.get("sample_size", 0))},
            "same_sign": bool(same_sign),
            "ic_diff": round(diff, 4),
        }
    else:
        subsample_consistency = 0.0
        subsample_detail = {"note": "insufficient codes for sub-sample split (need >= 10)"}

    robustness_score = round((window_stability * 0.4 + param_stability * 0.3 + subsample_consistency * 0.3), 4)
    grade = "strong" if robustness_score >= 0.7 else ("moderate" if robustness_score >= 0.4 else "weak")
    _perf_add(perf, "robust", time.perf_counter() - robust_stage_start)

    serialize_start = time.perf_counter()
    payload = {
        "factor": factor_name,
        "robustness_score": robustness_score,
        "grade": grade,
        "multi_window_ic": {"results": multi_window_results, "stability": round(window_stability, 4)},
        "param_sensitivity": {"results": param_results, "stability": round(param_stability, 4)},
        "subsample_consistency": {"score": subsample_consistency, "detail": subsample_detail},
        "weights": {"multi_window": 0.4, "param_sensitivity": 0.3, "subsample": 0.3},
        "prefetch": prefetch_meta,
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=prefetch_meta,
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)


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
            "note": f"Factor library includes {len(SUPPORTED_FACTORS)} factors across categories: fundamental, technical, risk, volume, alternative.",
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
                if factor_name == "momentum":
                    return fail(
                        f"Failed to calculate factor: momentum (need >= 2 close prices, got {len(closes)})"
                    )
                if factor_name == "trend":
                    return fail(
                        f"Failed to calculate factor: trend (need >= 3 close prices, got {len(closes)})"
                    )
                if factor_name == "reversal":
                    return fail(
                        f"Failed to calculate factor: reversal (need >= 2 close prices, got {len(closes)})"
                    )
                if factor_name == "volatility":
                    return fail(
                        f"Failed to calculate factor: volatility (need >= 4 close prices with valid returns, got {len(closes)})"
                    )
                if factor_name == "value":
                    return fail(
                        "Failed to calculate factor: value (need positive pe_ratio, pb_ratio, or ps_ratio in financials)"
                    )
                if factor_name == "quality":
                    return fail(
                        "Failed to calculate factor: quality (need roe/debt_ratio in financials)"
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
        include_perf_breakdown: bool = True,
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
                include_perf_breakdown=include_perf_breakdown,
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
        include_perf_breakdown: bool = True,
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
                include_perf_breakdown=include_perf_breakdown,
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
        validation_parallel: bool = True,
        max_workers: int = 0,
        bootstrap_mode: str = "",
        include_perf_breakdown: bool = True,
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
                validation_parallel=validation_parallel,
                max_workers=(None if int(max_workers or 0) <= 0 else int(max_workers)),
                bootstrap_mode=bootstrap_mode,
                include_perf_breakdown=include_perf_breakdown,
            )
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def factor_robustness_check(
        codes: list,
        factor: str,
        windows: list = None,
        param_variations: list = None,
        include_perf_breakdown: bool = True,
    ):
        """P2-2: Factor robustness check — multi-window IC stability, parameter sensitivity, sub-sample consistency."""
        try:
            return await run_factor_robustness_check(
                codes=codes,
                factor=factor,
                windows=windows,
                param_variations=param_variations,
                include_perf_breakdown=include_perf_breakdown,
            )
        except Exception as e:
            return fail(str(e))
