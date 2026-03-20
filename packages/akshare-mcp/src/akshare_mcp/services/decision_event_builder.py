"""Event/text context builder for unified decision."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from ..services.document_index import build_document_index
from ..services.event_extraction import extract_events
from ..services.llm_alpha import TextSignalPipeline
from ..tools.news.news_feed import get_stock_news
from ..tools.news.notices import get_stock_notices
from ..tools.news.research import get_research_reports
from ..utils import now_iso, resolve_security_code


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pick_text(item: dict[str, Any]) -> str:
    for key in ("text", "content", "summary", "title", "headline"):
        value = item.get(key)
        if value:
            return str(value).strip()
    return ""


async def build_event_context(
    code: str,
    *,
    news_limit: int = 12,
    notice_days: int = 30,
    report_limit: int = 6,
) -> dict[str, Any]:
    """Aggregate news/notices/research into a compact event context."""
    normalized_code = resolve_security_code(code)
    if not normalized_code:
        raise ValueError("需要提供股票代码")

    warnings: list[str] = []
    news_items: list[dict[str, Any]] = []
    notice_items: list[dict[str, Any]] = []
    report_items: list[dict[str, Any]] = []

    news_resp = await asyncio.to_thread(get_stock_news, normalized_code, max(1, int(news_limit)))
    if news_resp.get("success") and isinstance(news_resp.get("data"), list):
        news_items = [dict(item) for item in (news_resp.get("data") or []) if isinstance(item, dict)]
    else:
        warnings.append(f"stock_news:{news_resp.get('error', 'unknown')}")

    end_date = date.today()
    start_date = end_date - timedelta(days=max(1, int(notice_days)))
    notice_resp = await asyncio.to_thread(
        get_stock_notices,
        start_date.isoformat(),
        end_date.isoformat(),
        ["全部"],
        normalized_code,
    )
    if notice_resp.get("success") and isinstance(notice_resp.get("data"), dict):
        notice_items = [
            dict(item) for item in (notice_resp.get("data", {}).get("events") or []) if isinstance(item, dict)
        ]
    else:
        warnings.append(f"stock_notices:{notice_resp.get('error', 'unknown')}")

    report_resp = await asyncio.to_thread(get_research_reports, normalized_code, "", max(1, int(report_limit)))
    if report_resp.get("success"):
        report_data = report_resp.get("data")
        if isinstance(report_data, dict):
            report_items = [dict(item) for item in (report_data.get("reports") or []) if isinstance(item, dict)]
        elif isinstance(report_data, list):
            report_items = [dict(item) for item in report_data if isinstance(item, dict)]
    else:
        warnings.append(f"research_reports:{report_resp.get('error', 'unknown')}")

    merged_items: list[dict[str, Any]] = []
    for item in news_items[: max(1, int(news_limit))]:
        merged_items.append(
            {
                "type": "news",
                "date": item.get("date"),
                "title": item.get("title") or item.get("headline") or "",
                "source": item.get("source") or "stock_news",
                "text": _pick_text(item),
            }
        )
    for item in notice_items[: max(4, int(news_limit))]:
        merged_items.append(
            {
                "type": "notice",
                "date": item.get("date"),
                "title": item.get("title") or item.get("name") or "",
                "source": item.get("source") or "stock_notices",
                "text": _pick_text(item),
            }
        )
    for item in report_items[: max(1, int(report_limit))]:
        report_text = " ".join(
            str(value).strip()
            for value in [item.get("title"), item.get("rating"), item.get("institution")]
            if value
        ).strip()
        merged_items.append(
            {
                "type": "research",
                "date": item.get("date"),
                "title": item.get("title") or "",
                "source": item.get("institution") or "research_reports",
                "text": report_text,
                "rating": item.get("rating"),
                "target_price": item.get("targetPrice"),
            }
        )

    document_index = build_document_index(merged_items)
    documents = document_index.get("documents", [])
    texts = [item["text"] for item in documents if item.get("text")]
    text_signal = TextSignalPipeline.aggregate_signals(texts)
    extraction = extract_events(documents)
    event_tags = extraction.get("event_tags", [])
    event_summary = extraction.get("summary_counts", {})

    reasons: list[str] = []
    risks: list[str] = []
    score = 50.0 + float(text_signal.get("signal_score", 0.0) or 0.0) * 6.0

    sentiment = str(text_signal.get("sentiment") or "neutral")
    if sentiment == "bullish":
        score += 8.0
        reasons.append("文本信号整体偏利好")
    elif sentiment == "bearish":
        score -= 10.0
        risks.append("文本信号整体偏利空")

    hard_risk = False
    for item in event_tags:
        tag = str(item.get("tag") or "")
        if tag == "业绩景气":
            score += 5.0
            reasons.append("近阶段出现业绩景气类事件")
        if tag == "资本运作":
            score += 3.0
            reasons.append("存在回购或增持等资本运作线索")
        if tag == "监管风险":
            score -= 18.0
            hard_risk = sentiment == "bearish"
            risks.append("近阶段出现监管风险或处罚类标签")

    score = round(_clamp(score, 0.0, 100.0), 2)
    return {
        "code": normalized_code,
        "score": score,
        "sentiment": sentiment,
        "signal_score": float(text_signal.get("signal_score", 0.0) or 0.0),
        "positive_count": int(text_signal.get("positive_count", 0) or 0),
        "negative_count": int(text_signal.get("negative_count", 0) or 0),
        "evidence": text_signal.get("evidence", []),
        "event_tags": event_tags,
        "event_summary": event_summary,
        "hard_risk": hard_risk,
        "reasons": reasons,
        "risks": risks,
        "raw_texts": documents[:10],
        "warnings": warnings,
        "source_chain": [
            "decision_event_builder",
            "news.get_stock_news",
            "news.get_stock_notices",
            "news.get_research_reports",
            "services.llm_alpha.TextSignalPipeline",
            "services.event_extraction",
        ],
        "timestamp": now_iso(),
    }
