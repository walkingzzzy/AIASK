"""Quant manager: factor analysis and workflow orchestration."""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

import numpy as np

from ...services import get_artifact_async, list_artifacts_async, register_artifact
from ...data_source import data_source
from ...storage import get_db
from ...utils import fail, ok
from ..fund_flow import get_north_fund, get_stock_fund_flow
from ..news.news_feed import get_stock_news
from ..news.notices import get_stock_notices
from ..news.research import get_research_reports
from ..quant import (
    SUPPORTED_FACTORS,
    run_factor_group_backtest,
    run_factor_ic_analysis,
    run_factor_oos_validation,
)

logger = logging.getLogger(__name__)


POSITIVE_SENTIMENT_TOKENS = [
    "buy",
    "upgrade",
    "outperform",
    "\u5229\u597d",
    "\u4e0a\u8c03",
    "\u589e\u6301",
    "\u8d85\u9884\u671f",
    "\u7a81\u7834",
]

NEGATIVE_SENTIMENT_TOKENS = [
    "sell",
    "downgrade",
    "underperform",
    "\u5229\u7a7a",
    "\u4e0b\u8c03",
    "\u51cf\u6301",
    "\u4e0d\u53ca\u9884\u671f",
    "\u98ce\u9669",
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_code_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except Exception:
            pass
        return [x.strip() for x in text.split(",") if x.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _headline_sentiment_score(headlines: list[str]) -> tuple[float, dict]:
    if not headlines:
        return 0.0, {"positive_hits": 0, "negative_hits": 0, "coverage": 0.0}

    pos_hits = 0
    neg_hits = 0
    for title in headlines:
        text = str(title or "").lower()
        if not text:
            continue
        pos_hits += sum(1 for token in POSITIVE_SENTIMENT_TOKENS if token in text)
        neg_hits += sum(1 for token in NEGATIVE_SENTIMENT_TOKENS if token in text)

    total = len(headlines)
    score = (pos_hits - neg_hits) / max(total * 2, 1)
    coverage = (pos_hits + neg_hits) / max(total, 1)
    return float(_clip(score, -1.0, 1.0)), {
        "positive_hits": int(pos_hits),
        "negative_hits": int(neg_hits),
        "coverage": float(_clip(coverage, 0.0, 1.0)),
    }


def _extract_news_items(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    if not payload.get("success"):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        events = data.get("events")
        if isinstance(events, list):
            return [x for x in events if isinstance(x, dict)]
    return []


def _build_automl_features(closes: list[float], volumes: list[float], idx: int) -> dict[str, float] | None:
    if idx < 30 or idx >= len(closes):
        return None
    px = closes[idx]
    if px <= 0:
        return None

    p5 = closes[idx - 5]
    p10 = closes[idx - 10]
    p20 = closes[idx - 20]
    if p5 <= 0 or p10 <= 0 or p20 <= 0:
        return None

    ret_20 = []
    for j in range(idx - 19, idx + 1):
        prev = closes[j - 1]
        if prev <= 0:
            continue
        ret_20.append((closes[j] - prev) / prev)
    vol_20 = float(np.std(ret_20)) if len(ret_20) > 1 else 0.0

    ma5 = float(np.mean(closes[idx - 4: idx + 1]))
    ma20 = float(np.mean(closes[idx - 19: idx + 1]))
    ma_ratio = ((ma5 / ma20) - 1.0) if ma20 > 0 else 0.0

    gains = 0.0
    losses = 0.0
    for j in range(idx - 14 + 1, idx + 1):
        chg = closes[j] - closes[j - 1]
        if chg > 0:
            gains += chg
        else:
            losses -= chg
    avg_gain = gains / 14.0
    avg_loss = losses / 14.0
    if avg_loss <= 1e-12:
        rsi_14 = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_14 = 100.0 - (100.0 / (1.0 + rs))

    v5 = float(np.mean(volumes[idx - 4: idx + 1])) if idx >= 4 else 0.0
    v20 = float(np.mean(volumes[idx - 19: idx + 1])) if idx >= 19 else 0.0
    volume_ratio = (v5 / v20) if v20 > 0 else 1.0

    return {
        "mom_5d": float((px - p5) / p5),
        "mom_10d": float((px - p10) / p10),
        "mom_20d": float((px - p20) / p20),
        "volatility_20d": vol_20,
        "ma5_ma20_ratio": float(ma_ratio),
        "rsi_14": float((rsi_14 - 50.0) / 50.0),
        "volume_ratio_5_20": float(volume_ratio - 1.0),
    }


def _rank_transform(vec: np.ndarray) -> np.ndarray:
    n = len(vec)
    if n <= 1:
        return np.zeros(n, dtype=np.float64)
    order = np.argsort(vec)
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.linspace(-1.0, 1.0, n)
    return ranks


def _filter_quant_artifacts(artifacts: list[dict]) -> list[dict]:
    out = []
    for item in artifacts:
        strategy = str(item.get("strategy") or "").lower()
        if strategy.startswith("quant_") or strategy.startswith("feature_store"):
            out.append(item)
    return out


async def _compute_alternative_factors_for_code(
    db,
    code: str,
    lookback_days: int = 30,
    limit: int = 20,
) -> tuple[dict, list[str]]:
    code = str(code or "").strip()
    source_chain: list[str] = []
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=max(7, int(lookback_days)))

    news_payload = get_stock_news(code, limit=max(5, int(limit)))
    source_chain.append("tools.news.get_stock_news")
    notice_payload = get_stock_notices(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        stock_code=code,
    )
    source_chain.append("tools.news.get_stock_notices")
    research_payload = get_research_reports(code, limit=max(5, int(limit)))
    source_chain.append("tools.news.get_research_reports")
    flow_payload = get_stock_fund_flow(code)
    source_chain.append("tools.fund_flow.get_stock_fund_flow")
    north_payload = get_north_fund(days=max(5, min(int(lookback_days), 30)))
    source_chain.append("tools.fund_flow.get_north_fund")

    news_items = _extract_news_items(news_payload)
    notice_items = _extract_news_items(notice_payload)
    research_items = _extract_news_items(research_payload)

    headlines = []
    for item in news_items + notice_items + research_items:
        title = item.get("title")
        if title:
            headlines.append(str(title))

    sentiment_raw, sentiment_hits = _headline_sentiment_score(headlines)

    notice_count = len(notice_items)
    research_count = len(research_items)
    news_count = len(news_items)
    event_intensity = _clip(
        (notice_count * 1.2 + research_count * 0.8 + news_count * 0.3) / max(1.0, float(lookback_days)),
        0.0,
        1.0,
    )

    main_inflow = 0.0
    large_inflow = 0.0
    small_inflow = 0.0
    if isinstance(flow_payload, dict) and flow_payload.get("success") and isinstance(flow_payload.get("data"), dict):
        flow_data = flow_payload["data"]
        main_inflow = _safe_float(flow_data.get("mainNetInflow"), 0.0)
        large_inflow = _safe_float(flow_data.get("largeNetInflow"), 0.0) + _safe_float(
            flow_data.get("superLargeNetInflow"), 0.0
        )
        small_inflow = _safe_float(flow_data.get("smallNetInflow"), 0.0)

    capital_flow_raw = np.tanh(main_inflow / 5e8) if abs(main_inflow) > 0 else 0.0
    institutional_raw = np.tanh((large_inflow - small_inflow) / 5e8) if (large_inflow or small_inflow) else 0.0
    capital_behavior_raw = float(_clip(0.65 * capital_flow_raw + 0.35 * institutional_raw, -1.0, 1.0))

    north_flow_raw = 0.0
    if isinstance(north_payload, dict) and north_payload.get("success") and isinstance(north_payload.get("data"), list):
        rows = [r for r in north_payload["data"] if isinstance(r, dict)]
        if rows:
            tail = rows[-5:]
            totals = [_safe_float(x.get("total"), 0.0) for x in tail]
            north_flow_raw = float(np.tanh((np.mean(totals) if totals else 0.0) / 1e9))

    composite_raw = float(
        _clip(
            0.35 * sentiment_raw + 0.25 * (2.0 * event_intensity - 1.0) + 0.30 * capital_behavior_raw + 0.10 * north_flow_raw,
            -1.0,
            1.0,
        )
    )

    return (
        {
            "sentiment": {
                "score_raw": float(sentiment_raw),
                "score": float((sentiment_raw + 1.0) / 2.0),
                "news_count": news_count,
                "headline_count": len(headlines),
                "hits": sentiment_hits,
            },
            "event": {
                "score_raw": float(2.0 * event_intensity - 1.0),
                "score": float(event_intensity),
                "notice_count": notice_count,
                "research_count": research_count,
                "window_days": int(lookback_days),
            },
            "capital_flow": {
                "score_raw": float(capital_behavior_raw),
                "score": float((capital_behavior_raw + 1.0) / 2.0),
                "main_net_inflow": float(main_inflow),
                "large_net_inflow": float(large_inflow),
                "small_net_inflow": float(small_inflow),
                "north_flow_score_raw": float(north_flow_raw),
            },
            "alternative_composite": {
                "score_raw": float(composite_raw),
                "score": float((composite_raw + 1.0) / 2.0),
                "method": "weighted(sentiment,event,capital,north)",
            },
        },
        source_chain,
    )


async def _build_automl_dataset(
    db,
    codes: list[str],
    horizon_days: int,
    lookback_bars: int,
    include_alternative: bool,
    alt_lookback_days: int,
) -> tuple[list[dict], dict]:
    records: list[dict] = []
    stats = {
        "input_codes": len(codes),
        "processed_codes": 0,
        "skipped_no_kline": 0,
        "sample_count": 0,
    }
    fetch_bars = max(lookback_bars + horizon_days + 40, 120)

    for code in codes:
        klines = await db.get_klines(code, limit=fetch_bars)
        if not klines or len(klines) < max(60, horizon_days + 40):
            stats["skipped_no_kline"] += 1
            continue

        ordered = list(reversed([k for k in klines if isinstance(k, dict)]))  # oldest -> newest
        closes = [_safe_float(k.get("close"), 0.0) for k in ordered]
        volumes = [_safe_float(k.get("volume"), 0.0) for k in ordered]
        dates = [str(k.get("date") or k.get("trade_date") or "") for k in ordered]
        if len(closes) < max(60, horizon_days + 40):
            stats["skipped_no_kline"] += 1
            continue

        latest_financial = None
        try:
            financials = await db.get_financials(code, limit=1)
            if isinstance(financials, list) and financials:
                latest_financial = financials[0] if isinstance(financials[0], dict) else None
            elif isinstance(financials, dict):
                latest_financial = financials
        except Exception:
            latest_financial = None
        latest_financial = latest_financial or {}

        pe = _safe_float(latest_financial.get("pe_ratio"), 0.0)
        pb = _safe_float(latest_financial.get("pb_ratio"), 0.0)
        roe = _safe_float(latest_financial.get("roe"), 0.0)
        debt_ratio = _safe_float(latest_financial.get("debt_ratio"), 0.0)
        static_features = {
            "value_pe_inv": float(1.0 / pe) if pe > 0 else 0.0,
            "value_pb_inv": float(1.0 / pb) if pb > 0 else 0.0,
            "quality_roe": float(roe),
            "quality_debt_neg": float(-debt_ratio),
        }

        alt_features = {}
        if include_alternative:
            try:
                alt, _ = await _compute_alternative_factors_for_code(
                    db=db,
                    code=code,
                    lookback_days=alt_lookback_days,
                    limit=10,
                )
                alt_features = {
                    "alt_sentiment": _safe_float(alt.get("sentiment", {}).get("score_raw"), 0.0),
                    "alt_event": _safe_float(alt.get("event", {}).get("score_raw"), 0.0),
                    "alt_capital": _safe_float(alt.get("capital_flow", {}).get("score_raw"), 0.0),
                    "alt_composite": _safe_float(alt.get("alternative_composite", {}).get("score_raw"), 0.0),
                }
            except Exception:
                alt_features = {}

        for idx in range(30, len(closes) - horizon_days):
            px = closes[idx]
            future_px = closes[idx + horizon_days]
            if px <= 0 or future_px <= 0:
                continue
            base_features = _build_automl_features(closes, volumes, idx)
            if not base_features:
                continue
            target = (future_px - px) / px
            features = {**base_features, **static_features, **alt_features}
            records.append(
                {
                    "code": code,
                    "date": dates[idx] or f"t_{idx}",
                    "features": features,
                    "target": float(target),
                }
            )

        stats["processed_codes"] += 1

    records.sort(key=lambda x: str(x.get("date") or ""))
    stats["sample_count"] = len(records)
    return records, stats


def _fit_automl_model(records: list[dict], top_k_features: int, train_ratio: float, max_feature_corr: float) -> dict:
    if len(records) < 80:
        return {"success": False, "error": f"insufficient sample size: {len(records)} < 80"}

    feature_names = sorted(
        {
            key
            for row in records
            for key in (row.get("features") or {}).keys()
            if isinstance(key, str)
        }
    )
    if not feature_names:
        return {"success": False, "error": "no feature columns"}

    x_all = np.array(
        [[_safe_float((row.get("features") or {}).get(name), 0.0) for name in feature_names] for row in records],
        dtype=np.float64,
    )
    y_all = np.array([_safe_float(row.get("target"), 0.0) for row in records], dtype=np.float64)

    split = int(len(records) * _clip(train_ratio, 0.55, 0.9))
    split = max(50, min(split, len(records) - 20))
    x_train, x_test = x_all[:split], x_all[split:]
    y_train, y_test = y_all[:split], y_all[split:]
    if len(y_test) < 20:
        return {"success": False, "error": "test set too small"}

    mu = np.mean(x_train, axis=0)
    sigma = np.std(x_train, axis=0)
    sigma[sigma < 1e-12] = 1.0
    x_train_z = (x_train - mu) / sigma
    x_test_z = (x_test - mu) / sigma

    corr_scores = []
    for i, name in enumerate(feature_names):
        x_col = x_train_z[:, i]
        std_col = float(np.std(x_col))
        if std_col < 1e-8:
            continue
        corr = float(np.corrcoef(x_col, y_train)[0, 1])
        if np.isnan(corr):
            continue
        corr_scores.append((name, i, corr, abs(corr)))

    if not corr_scores:
        return {"success": False, "error": "all features degenerated"}

    corr_scores.sort(key=lambda x: x[3], reverse=True)
    selected: list[tuple[str, int, float]] = []
    for name, idx, corr, _ in corr_scores:
        allow = True
        for _, prev_idx, _ in selected:
            c = float(np.corrcoef(x_train_z[:, idx], x_train_z[:, prev_idx])[0, 1])
            if np.isnan(c):
                continue
            if abs(c) >= _clip(max_feature_corr, 0.5, 0.99):
                allow = False
                break
        if allow:
            selected.append((name, idx, corr))
        if len(selected) >= max(2, int(top_k_features)):
            break

    if len(selected) < 2:
        return {"success": False, "error": "not enough orthogonal features"}

    selected_idx = [x[1] for x in selected]
    selected_names = [x[0] for x in selected]
    raw_weights = np.array([x[2] for x in selected], dtype=np.float64)
    norm = np.sum(np.abs(raw_weights))
    if norm < 1e-8:
        raw_weights = np.ones_like(raw_weights) / len(raw_weights)
    else:
        raw_weights = raw_weights / norm

    x_test_sel = x_test_z[:, selected_idx]
    pred_linear = x_test_sel @ raw_weights
    rank_stack = np.vstack([_rank_transform(x_test_sel[:, j]) * np.sign(raw_weights[j]) for j in range(x_test_sel.shape[1])])
    pred_rank = np.mean(rank_stack, axis=0)
    pred = 0.6 * pred_linear + 0.4 * pred_rank

    ic = float(np.corrcoef(pred, y_test)[0, 1]) if len(y_test) > 2 else 0.0
    if np.isnan(ic):
        ic = 0.0
    hit_rate = float(np.mean((pred > 0) == (y_test > 0)))
    q = max(1, int(0.2 * len(pred)))
    order = np.argsort(pred)
    top_idx = order[-q:]
    bot_idx = order[:q]
    top_ret = float(np.mean(y_test[top_idx])) if len(top_idx) else 0.0
    bot_ret = float(np.mean(y_test[bot_idx])) if len(bot_idx) else 0.0
    long_short = float(top_ret - bot_ret)

    threshold_records = []
    for threshold in [0.0, float(np.percentile(pred, 60)), float(np.percentile(pred, 75))]:
        mask = pred >= threshold
        n = int(np.sum(mask))
        if n == 0:
            threshold_records.append(
                {"threshold": float(threshold), "sample_count": 0, "hit_rate": None, "avg_forward_return": None}
            )
            continue
        y_sel = y_test[mask]
        threshold_records.append(
            {
                "threshold": float(threshold),
                "sample_count": n,
                "hit_rate": float(np.mean(y_sel > 0)),
                "avg_forward_return": float(np.mean(y_sel)),
            }
        )

    return {
        "success": True,
        "selected_features": selected_names,
        "feature_weights": {name: float(w) for name, w in zip(selected_names, raw_weights)},
        "feature_importance_abs_corr": [
            {"feature": name, "train_corr": float(corr), "abs_corr": float(abs(corr))}
            for name, _, corr in selected
        ],
        "metrics": {
            "test_ic": float(ic),
            "hit_rate": float(hit_rate),
            "top_quantile_return": float(top_ret),
            "bottom_quantile_return": float(bot_ret),
            "long_short_return": float(long_short),
            "test_sample_count": int(len(y_test)),
        },
        "threshold_backtest": threshold_records,
        "train_test_split": {
            "train_samples": int(len(y_train)),
            "test_samples": int(len(y_test)),
            "train_ratio": float(split / len(records)),
        },
    }


def _select_anchor_factor(selected_features: list[str]) -> str:
    labels = [str(x).lower() for x in selected_features]
    if any("mom" in x for x in labels):
        return "momentum"
    if any("vol" in x for x in labels):
        return "volatility"
    if any("value" in x or "pe" in x or "pb" in x for x in labels):
        return "value"
    if any("quality" in x or "roe" in x or "debt" in x for x in labels):
        return "quality"
    return "momentum"


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

            def _with_meta(resp: dict, source_chain=None, data_timestamp: Optional[str] = None):
                if not isinstance(resp, dict):
                    return resp
                resp["meta"] = {
                    "trace_id": trace_id,
                    "tool_version": tool_version,
                    "data_timestamp": data_timestamp or datetime.now().strftime("%Y-%m-%d"),
                    "source_chain": source_chain or ["quant_manager"],
                    "cached": False,
                    "latency_ms": round((time.perf_counter() - start_time) * 1000, 2),
                    "as_of": as_of,
                    "adjust": adjust,
                    "price_source_policy": price_source_policy,
                    "explain": explain,
                    "strict_mode": strict_mode,
                }
                return resp

            def _ok(data: dict, source_chain=None, data_timestamp: Optional[str] = None):
                return _with_meta(ok(data), source_chain, data_timestamp)

            def _fail(message: str, source_chain=None, data_timestamp: Optional[str] = None):
                return _with_meta(fail(message), source_chain, data_timestamp)

            if action == "help":
                return _ok(
                    {
                        "supported_actions": {
                            "calculate_factors": "计算因子（需要 code）",
                            "alternative_factors": "P2 另类数据因子化（新闻/公告/研报/资金流）",
                            "factor_ic": "因子 IC 分析（需要 codes, factor）",
                            "backtest_factor": "因子分组回测（需要 codes, factor）",
                            "multi_factor_score": "多因子评分（需要 code）",
                            "automl_discovery": "P2 AutoML 因子发现（特征筛选+集成+OOS锚点验证）",
                            "feature_store": "P2 特征快照/实验追踪（snapshot|get|list）",
                            "replay_experiment": "P2 结果回放（基于 artifact_id 复跑并输出漂移）",
                            "help": "显示帮助信息",
                        }
                    }
                )

            elif action == "calculate_factors":
                if not code:
                    return _fail("需要提供股票代码（code）")

                factors = _kw.get("factors", ["momentum", "value", "quality"])
                supported_factors = {
                    "momentum",
                    "value",
                    "quality",
                    "volatility",
                    "liquidity",
                    "sentiment",
                    "event",
                    "capital_flow",
                    "alternative_composite",
                }
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

                requested_alt = any(
                    f in factors for f in ("sentiment", "event", "capital_flow", "alternative_composite")
                )
                if requested_alt:
                    alt_days = int(_kw.get("alt_lookback_days", 30) or 30)
                    alt_limit = int(_kw.get("alt_limit", 20) or 20)
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
                enable_neutralization = bool(_kw.get("enable_neutralization", True))
                bootstrap_n = int(_kw.get("bootstrap_n", 1000) or 1000)
                bootstrap_confidence = float(_kw.get("bootstrap_confidence", 0.95) or 0.95)

                if factor_name not in SUPPORTED_FACTORS:
                    return _fail(
                        f"Unsupported factor: {factor_name}. "
                        f"Supported: {sorted(SUPPORTED_FACTORS.keys())}"
                    )
                if not isinstance(codes, list) or not codes:
                    return _fail("需要提供股票列表（codes）")

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

                return _with_meta(
                    result,
                    source_chain=["db.get_klines", "db.get_financials(optional)", "factor_analysis_dual_ic", "bootstrap_ci"],
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

            elif action == "alternative_factors":
                codes = _as_code_list(_kw.get("codes"))
                if not codes and code:
                    codes = [code]
                if not codes:
                    return _fail("需要提供 code 或 codes")

                lookback_days = int(_kw.get("lookback_days", 30) or 30)
                limit = int(_kw.get("limit", 20) or 20)
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

                return _ok(
                    {
                        "codes": codes,
                        "count": len(result_rows),
                        "data_window": {"lookback_days": lookback_days, "limit_per_source": limit},
                        "rows": result_rows,
                    },
                    source_chain=source_chain or ["quant_manager.alternative_factors"],
                )

            elif action == "automl_discovery":
                codes = _as_code_list(_kw.get("codes"))
                if not codes:
                    return _fail("需要提供股票列表（codes）")

                horizon_days = int(_kw.get("horizon_days", 10) or 10)
                lookback_bars = int(_kw.get("lookback_bars", 160) or 160)
                top_k_features = int(_kw.get("top_k_features", 6) or 6)
                train_ratio = float(_kw.get("train_ratio", 0.7) or 0.7)
                max_feature_corr = float(_kw.get("max_feature_corr", 0.85) or 0.85)
                include_alternative = bool(_kw.get("include_alternative", True))
                alt_lookback_days = int(_kw.get("alt_lookback_days", 30) or 30)
                persist_artifact = bool(_kw.get("persist_artifact", True))
                run_anchor_oos = bool(_kw.get("run_anchor_oos", True))

                records, dataset_stats = await _build_automl_dataset(
                    db=db,
                    codes=codes,
                    horizon_days=max(3, min(30, horizon_days)),
                    lookback_bars=max(120, min(500, lookback_bars)),
                    include_alternative=include_alternative,
                    alt_lookback_days=max(7, min(120, alt_lookback_days)),
                )
                model_res = _fit_automl_model(
                    records=records,
                    top_k_features=max(2, min(15, top_k_features)),
                    train_ratio=_clip(train_ratio, 0.55, 0.9),
                    max_feature_corr=_clip(max_feature_corr, 0.5, 0.99),
                )
                if not model_res.get("success"):
                    return _fail(
                        model_res.get("error", "automl failed"),
                        source_chain=["db.get_klines", "numpy.feature_selection"],
                    )

                selected_features = model_res.get("selected_features", [])
                anchor_factor = _select_anchor_factor(selected_features)
                anchor_oos = None
                if run_anchor_oos:
                    try:
                        anchor_oos = await run_factor_oos_validation(
                            codes=codes,
                            factor=anchor_factor,
                            factor_lookback=20,
                            forward_period=max(5, min(20, horizon_days)),
                            panel_periods=180,
                            wf_train_window=60,
                            wf_test_window=20,
                            wf_step=20,
                            kfold_n_folds=5,
                            kfold_purge_gap=5,
                            bootstrap_n=600,
                            bootstrap_confidence=0.95,
                        )
                    except Exception as exc:
                        anchor_oos = fail(f"anchor_oos_failed: {exc}")

                artifact_id = f"quant_automl_{int(time.time())}_{uuid4().hex[:8]}"
                output = {
                    "artifact_id": artifact_id,
                    "codes": codes,
                    "dataset_stats": dataset_stats,
                    "selected_features": selected_features,
                    "feature_weights": model_res.get("feature_weights", {}),
                    "feature_importance_abs_corr": model_res.get("feature_importance_abs_corr", []),
                    "metrics": model_res.get("metrics", {}),
                    "threshold_backtest": model_res.get("threshold_backtest", []),
                    "train_test_split": model_res.get("train_test_split", {}),
                    "robust_constraints": {
                        "min_sample_required": 80,
                        "max_feature_corr": _clip(max_feature_corr, 0.5, 0.99),
                        "passed": bool(dataset_stats.get("sample_count", 0) >= 80),
                    },
                    "oos_anchor": {
                        "factor": anchor_factor,
                        "result": anchor_oos,
                    },
                    "params": {
                        "horizon_days": horizon_days,
                        "lookback_bars": lookback_bars,
                        "top_k_features": top_k_features,
                        "train_ratio": train_ratio,
                        "include_alternative": include_alternative,
                        "alt_lookback_days": alt_lookback_days,
                    },
                }

                if persist_artifact:
                    register_artifact(
                        {
                            "artifact_id": artifact_id,
                            "strategy": "quant_automl_discovery",
                            "strategy_version": "p2.v1",
                            "code": ",".join(codes[:5]),
                            "payload": output,
                            "created_at": datetime.now().isoformat(),
                        }
                    )

                return _ok(
                    output,
                    source_chain=[
                        "db.get_klines",
                        "db.get_financials",
                        "tools.news.*",
                        "tools.fund_flow.*",
                        "numpy.feature_selection_ensemble",
                        "quant.run_factor_oos_validation(anchor)",
                        "services.artifact_registry",
                    ],
                )

            elif action == "feature_store":
                op = str(_kw.get("op", "list") or "list").strip().lower()
                if op in {"snapshot", "create"}:
                    codes = _as_code_list(_kw.get("codes"))
                    if not codes and code:
                        codes = [code]
                    if not codes:
                        return _fail("feature_store snapshot 需要 code 或 codes")

                    factors = _kw.get(
                        "factors",
                        [
                            "momentum",
                            "value",
                            "quality",
                            "volatility",
                            "liquidity",
                            "sentiment",
                            "event",
                            "capital_flow",
                            "alternative_composite",
                        ],
                    )
                    snapshot_rows = []
                    for one_code in codes:
                        fac_res = await quant_manager(action="calculate_factors", code=one_code, factors=factors)
                        if fac_res.get("success"):
                            snapshot_rows.append(
                                {
                                    "code": one_code,
                                    "factors": fac_res.get("data", {}).get("factors", {}),
                                    "composite_score": fac_res.get("data", {}).get("composite_score"),
                                }
                            )

                    artifact_id = str(_kw.get("artifact_id") or f"feature_store_{int(time.time())}_{uuid4().hex[:8]}")
                    payload = {
                        "artifact_id": artifact_id,
                        "strategy": "feature_store_snapshot",
                        "strategy_version": "p2.v1",
                        "code": ",".join(codes[:5]),
                        "snapshot_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "codes": codes,
                        "factors": factors,
                        "rows": snapshot_rows,
                        "count": len(snapshot_rows),
                    }
                    register_artifact(payload)
                    return _ok(
                        {
                            "op": "snapshot",
                            "artifact_id": artifact_id,
                            "count": len(snapshot_rows),
                            "codes": codes,
                        },
                        source_chain=["quant_manager.calculate_factors", "services.artifact_registry"],
                    )

                if op in {"get", "detail"}:
                    artifact_id = str(_kw.get("artifact_id") or "").strip()
                    if not artifact_id:
                        return _fail("feature_store get 需要 artifact_id")
                    artifact = await get_artifact_async(artifact_id)
                    if not artifact:
                        return _fail(f"artifact not found: {artifact_id}")
                    return _ok(
                        {"op": "get", "artifact": artifact},
                        source_chain=["services.artifact_registry"],
                    )

                if op in {"list", "ls"}:
                    limit = int(_kw.get("limit", 20) or 20)
                    items = await list_artifacts_async(limit=max(1, min(200, limit)))
                    filtered = _filter_quant_artifacts(items if isinstance(items, list) else [])
                    return _ok(
                        {"op": "list", "items": filtered, "count": len(filtered)},
                        source_chain=["services.artifact_registry"],
                    )

                if op in {"track", "log"}:
                    artifact_id = str(_kw.get("artifact_id") or f"quant_exp_{int(time.time())}_{uuid4().hex[:8]}")
                    payload = {
                        "artifact_id": artifact_id,
                        "strategy": "quant_experiment",
                        "strategy_version": str(_kw.get("strategy_version") or "p2.v1"),
                        "code": str(_kw.get("code") or code or ""),
                        "name": str(_kw.get("name") or ""),
                        "params": _kw.get("params") if isinstance(_kw.get("params"), dict) else {},
                        "metrics": _kw.get("metrics") if isinstance(_kw.get("metrics"), dict) else {},
                        "notes": str(_kw.get("notes") or ""),
                        "tracked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    register_artifact(payload)
                    return _ok(
                        {"op": "track", "artifact_id": artifact_id},
                        source_chain=["services.artifact_registry"],
                    )

                return _fail("Unknown feature_store op. Supported: snapshot|get|list|track")

            elif action == "replay_experiment":
                artifact_id = str(_kw.get("artifact_id") or "").strip()
                if not artifact_id:
                    return _fail("需要 artifact_id")

                artifact = await get_artifact_async(artifact_id)
                if not artifact:
                    return _fail(f"artifact not found: {artifact_id}")

                strategy = str(artifact.get("strategy") or "").lower()
                payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else artifact
                if strategy != "quant_automl_discovery":
                    return _fail(f"artifact {artifact_id} is not quant_automl_discovery")

                params = payload.get("params", {}) if isinstance(payload, dict) else {}
                replay_codes = _as_code_list(payload.get("codes")) or _as_code_list(params.get("codes")) or _as_code_list(_kw.get("codes"))
                if not replay_codes:
                    return _fail("replay requires codes in artifact or kwargs")

                replay_action = await quant_manager(
                    action="automl_discovery",
                    kwargs={
                        "codes": replay_codes,
                        "horizon_days": params.get("horizon_days", 10),
                        "lookback_bars": params.get("lookback_bars", 160),
                        "top_k_features": params.get("top_k_features", 6),
                        "train_ratio": params.get("train_ratio", 0.7),
                        "include_alternative": params.get("include_alternative", True),
                        "alt_lookback_days": params.get("alt_lookback_days", 30),
                        "persist_artifact": False,
                        "run_anchor_oos": bool(_kw.get("run_anchor_oos", True)),
                    },
                )
                if not replay_action.get("success"):
                    return replay_action

                old_metrics = (payload.get("metrics") or {}) if isinstance(payload, dict) else {}
                new_metrics = replay_action.get("data", {}).get("metrics", {})
                metric_delta = {}
                for metric_name in ("test_ic", "hit_rate", "long_short_return"):
                    ov = _safe_float(old_metrics.get(metric_name), 0.0)
                    nv = _safe_float(new_metrics.get(metric_name), 0.0)
                    metric_delta[metric_name] = {"old": ov, "new": nv, "delta": float(nv - ov)}

                return _ok(
                    {
                        "artifact_id": artifact_id,
                        "replay_metrics": new_metrics,
                        "metric_delta": metric_delta,
                        "replay_result": replay_action.get("data"),
                    },
                    source_chain=["services.artifact_registry", "quant_manager.automl_discovery"],
                )

            elif action == "batch_compute_factors":
                # Batch compute and persist factor values + IC for multiple stocks
                codes = _kw.get("codes", [])
                if not isinstance(codes, list) or not codes:
                    return _fail("codes (list of stock codes) is required")
                factors = _kw.get("factors", ["momentum", "value", "quality"])
                persist = bool(_kw.get("persist", True))
                compute_ic = bool(_kw.get("compute_ic", True))
                period = int(_kw.get("period", 20) or 20)

                supported = {"momentum", "value", "quality", "volatility", "liquidity"}
                unknown = [f for f in factors if f not in supported]
                if unknown:
                    return _fail(f"Unsupported factors for batch: {unknown}. Supported: {sorted(supported)}")

                db = get_db()
                results = {}
                errors = []
                today = datetime.now().date()

                for stock_code in codes[:200]:  # cap at 200
                    try:
                        klines = await db.get_klines(stock_code, limit=252)
                        if not klines:
                            klines_data = data_source.get_kline(stock_code, period="daily", limit=252)
                            klines = [
                                {"date": k.get("date"), "open": k.get("open"), "high": k.get("high"),
                                 "low": k.get("low"), "close": k.get("close"),
                                 "volume": k.get("volume"), "amount": k.get("amount", 0)}
                                for k in (klines_data or [])
                            ]
                        if not klines:
                            errors.append({"code": stock_code, "error": "no kline data"})
                            continue

                        closes = [k.get("close") for k in klines if isinstance(k, dict) and k.get("close") is not None]
                        if len(closes) < 20:
                            errors.append({"code": stock_code, "error": "insufficient data"})
                            continue

                        financials = await db.get_financials(stock_code, limit=4)
                        latest_fin = {}
                        if isinstance(financials, list) and financials:
                            latest_fin = financials[0] if isinstance(financials[0], dict) else {}
                        elif isinstance(financials, dict):
                            latest_fin = financials

                        fv = {}
                        if "momentum" in factors:
                            m20 = (closes[-1] - closes[-20]) / closes[-20] if len(closes) >= 20 and closes[-20] else 0.0
                            m60 = (closes[-1] - closes[-60]) / closes[-60] if len(closes) >= 60 and closes[-60] else 0.0
                            fv["momentum"] = float((m20 + m60) / 2.0)
                        if "value" in factors:
                            pe = float(latest_fin.get("pe_ratio", 0) or 0)
                            pb = float(latest_fin.get("pb_ratio", 0) or 0)
                            fv["value"] = float((1.0 / pe if pe > 0 else 0) + (1.0 / pb if pb > 0 else 0)) / 2.0
                        if "quality" in factors:
                            roe = float(latest_fin.get("roe", 0) or 0)
                            fv["quality"] = float(roe / 30.0 if roe > 0 else 0)
                        if "volatility" in factors:
                            prices = np.array(closes, dtype=float)
                            rets = np.diff(prices) / prices[:-1]
                            fv["volatility"] = float(1.0 / (np.std(rets) * np.sqrt(252))) if len(rets) > 1 and np.std(rets) > 0 else 0.0
                        if "liquidity" in factors:
                            volumes = [float(k.get("volume", 0) or 0) for k in klines[-20:]]
                            fv["liquidity"] = float(np.mean(volumes)) if volumes else 0.0

                        results[stock_code] = fv

                        if persist and fv:
                            await db.save_factor_values(stock_code, today, fv)
                    except Exception as e:
                        errors.append({"code": stock_code, "error": str(e)})

                # Compute cross-sectional IC if requested
                # IC = corr(factor_value[t-period], return[t-period → t])
                # We use lagged factor values paired with subsequent realized returns
                ic_results = {}
                if compute_ic and len(results) >= 10:
                    for fname in factors:
                        factor_vals = []
                        forward_rets = []
                        for stock_code, fv in results.items():
                            if fname not in fv:
                                continue
                            try:
                                klines = await db.get_klines(stock_code, limit=period + 60)
                                if not klines or len(klines) < period + 20:
                                    continue
                                closes = [float(k.get("close", 0) or 0) for k in klines]
                                # Lagged factor: compute factor from data ending period days ago
                                lagged_closes = closes[:-(period)]
                                if len(lagged_closes) < 20 or not lagged_closes[-20]:
                                    continue
                                # Compute lagged factor value
                                if fname == "momentum":
                                    m20 = (lagged_closes[-1] - lagged_closes[-20]) / lagged_closes[-20] if len(lagged_closes) >= 20 and lagged_closes[-20] else 0.0
                                    lagged_fv = float(m20)
                                elif fname == "volatility":
                                    lp = np.array(lagged_closes[-60:] if len(lagged_closes) >= 60 else lagged_closes, dtype=float)
                                    lr = np.diff(lp) / lp[:-1]
                                    lagged_fv = float(1.0 / (np.std(lr) * np.sqrt(252))) if len(lr) > 1 and np.std(lr) > 0 else 0.0
                                elif fname == "liquidity":
                                    lagged_vols = [float(k.get("volume", 0) or 0) for k in klines[:-(period)][-20:]]
                                    lagged_fv = float(np.mean(lagged_vols)) if lagged_vols else 0.0
                                else:
                                    # For value/quality that depend on financials, use current factor value as proxy
                                    lagged_fv = fv[fname]
                                # Forward return: from lagged point to now
                                c_lagged = closes[-(period + 1)]
                                c_now = closes[-1]
                                if c_lagged and c_now:
                                    factor_vals.append(lagged_fv)
                                    forward_rets.append((c_now - c_lagged) / c_lagged)
                            except Exception:
                                continue

                        if len(factor_vals) >= 10:
                            from ...services.factor_calculator.analysis import AnalysisFactorsMixin
                            ic_data = AnalysisFactorsMixin.calculate_factor_ic(factor_vals, forward_rets)
                            ic_val = ic_data.get("ic", 0.0)
                            rank_ic = ic_data.get("rank_ic", 0.0)
                            ic_results[fname] = {"ic": ic_val, "rank_ic": rank_ic, "sample_size": len(factor_vals)}
                            if persist:
                                await db.save_factor_ic(fname, str(period), today, ic_val, rank_ic, len(factor_vals))

                return _ok({
                    "computed_count": len(results),
                    "error_count": len(errors),
                    "errors": errors[:10],
                    "factors": factors,
                    "ic": ic_results,
                    "persisted": persist,
                }, source_chain=["db.get_klines", "db.save_factor_values", "db.save_factor_ic"])

            elif action == "factor_ic_history":
                factor_name = str(_kw.get("factor_name", "")).strip()
                period = str(_kw.get("period", "20"))
                limit = min(max(int(_kw.get("limit", 60)), 1), 500)
                if not factor_name:
                    return _fail("factor_name is required")
                db = get_db()
                rows = await db.get_factor_ic_history(factor_name, period, limit)
                return _ok({
                    "factor_name": factor_name,
                    "period": period,
                    "history": [
                        {
                            "date": str(r.get("ic_date", "")),
                            "ic_value": r.get("ic_value"),
                            "rank_ic": r.get("rank_ic"),
                            "stock_count": r.get("stock_count"),
                        }
                        for r in rows
                    ],
                    "count": len(rows),
                })

            elif action == "scheduler_status":
                from ...services.factor_scheduler import get_factor_scheduler
                scheduler = get_factor_scheduler()
                return _ok(scheduler.status())

            elif action == "scheduler_run_now":
                from ...services.factor_scheduler import get_factor_scheduler
                scheduler = get_factor_scheduler()
                result = await scheduler.run_once()
                return _ok(result or {"message": "run completed"})

            return _fail(
                "Unknown action: {action}. Supported: help, calculate_factors, alternative_factors, "
                "factor_ic, backtest_factor, multi_factor_score, automl_discovery, feature_store, "
                "replay_experiment, batch_compute_factors, factor_ic_history, scheduler_status, scheduler_run_now"
                .format(action=action)
            )
        except Exception as e:
            return _fail(str(e))
