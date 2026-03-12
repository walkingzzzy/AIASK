"""Quant manager helpers: utility functions, sentiment analysis, factor analysis."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from ..fund_flow import get_north_fund, get_stock_fund_flow
from ..news.news_feed import get_stock_news
from ..news.notices import get_stock_notices
from ..news.research import get_research_reports

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentiment token lists
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Generic utility helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Sentiment scoring
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Numpy helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Alternative factors computation (sentiment + event + capital flow + north)
# ---------------------------------------------------------------------------


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
