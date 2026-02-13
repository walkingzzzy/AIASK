"""Quant manager: factor analysis and workflow orchestration."""

import json
import logging
import time
from typing import Optional

import numpy as np

from ...data_source import data_source
from ...storage import get_db
from ...utils import fail, ok
from ..quant import SUPPORTED_FACTORS, run_factor_group_backtest, run_factor_ic_analysis

logger = logging.getLogger(__name__)


def register_quant_manager(mcp):
    """Register quant manager tool."""

    @mcp.tool()
    async def quant_manager(action: str, code: Optional[str] = None, **kwargs):
        """Quant manager with unified action + kwargs protocol."""
        try:
            start_time = time.perf_counter()
            trace_id = f"quant_manager:{action}:{int(time.time() * 1000)}"
            tool_version = "v1.2"
            db = get_db()

            if kwargs.get("kwargs") and isinstance(kwargs.get("kwargs"), str):
                try:
                    extra = json.loads(kwargs.get("kwargs") or "{}")
                    if isinstance(extra, dict):
                        kwargs = {**kwargs, **extra}
                except Exception:
                    pass

            _kw = kwargs.get("kwargs") if isinstance(kwargs.get("kwargs"), dict) else kwargs

            as_of = _kw.get("as_of", "")
            adjust = _kw.get("adjust", "")
            price_source_policy = _kw.get("price_source_policy", "auto")
            explain = _kw.get("explain", True)
            strict_mode = _kw.get("strict_mode", False)
            code = code or _kw.get("code") or _kw.get("Code") or _kw.get("stock_code") or _kw.get("symbol")

            def _with_meta(resp: dict, source_chain=None):
                if not isinstance(resp, dict):
                    return resp
                resp["meta"] = {
                    "trace_id": trace_id,
                    "tool_version": tool_version,
                    "data_timestamp": "",
                    "source_chain": source_chain or [],
                    "cached": False,
                    "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                    "as_of": as_of,
                    "adjust": adjust,
                    "price_source_policy": price_source_policy,
                    "explain": explain,
                    "strict_mode": strict_mode,
                }
                return resp

            def _ok(data: dict, source_chain=None):
                return _with_meta(ok(data), source_chain)

            def _fail(message: str, source_chain=None):
                return _with_meta(fail(message), source_chain)

            if action == "help":
                return _ok(
                    {
                        "supported_actions": {
                            "calculate_factors": "计算因子（需要 code）",
                            "factor_ic": "因子 IC 分析（需要 codes, factor）",
                            "backtest_factor": "因子分组回测（需要 codes, factor）",
                            "multi_factor_score": "多因子评分（需要 code）",
                            "help": "显示帮助信息",
                        }
                    }
                )

            elif action == "calculate_factors":
                if not code:
                    return _fail("需要提供股票代码（code）")

                factors = _kw.get("factors", ["momentum", "value", "quality"])
                supported_factors = {"momentum", "value", "quality", "volatility", "liquidity"}
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

                closes = [k.get("close") for k in klines if isinstance(k, dict) and k.get("close") is not None]
                if len(closes) < 2:
                    return _fail("K线数据不足，无法计算因子", source_chain=source_chain)

                financials = await db.get_financials(code, limit=4)
                latest_financial = {}
                if isinstance(financials, list) and financials:
                    latest_financial = financials[0] if isinstance(financials[0], dict) else {}
                elif isinstance(financials, dict):
                    latest_financial = financials

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
                    pe_ratio = float(latest_financial.get("pe_ratio", 0) or 0)
                    pb_ratio = float(latest_financial.get("pb_ratio", 0) or 0)
                    ps_ratio = float(latest_financial.get("ps_ratio", 0) or 0)
                    pe_score = 1.0 / pe_ratio if pe_ratio > 0 else 0.0
                    pb_score = 1.0 / pb_ratio if pb_ratio > 0 else 0.0
                    ps_score = 1.0 / ps_ratio if ps_ratio > 0 else 0.0
                    value_score = (pe_score + pb_score + ps_score) / 3.0
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

                if factor_name not in SUPPORTED_FACTORS:
                    return _fail(
                        f"Unsupported factor: {factor_name}. "
                        f"Supported: {sorted(SUPPORTED_FACTORS.keys())}"
                    )
                if not isinstance(codes, list) or not codes:
                    return _fail("需要提供股票列表（codes）")

                result = await run_factor_ic_analysis(codes=codes, factor=factor_name, period=period)
                if result.get("success") and isinstance(result.get("data"), dict):
                    result["data"]["factor_name"] = result["data"].get("factor", factor_name)
                    result["data"]["description"] = "IC>0 表示因子与未来收益同向关联，IC<0 则反向"

                return _with_meta(
                    result,
                    source_chain=["db.get_klines", "db.get_financials(optional)", "scipy.spearmanr"],
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

            return _fail(
                f"Unknown action: {action}. Supported: help, calculate_factors, factor_ic, backtest_factor, multi_factor_score"
            )
        except Exception as e:
            return _fail(str(e))
