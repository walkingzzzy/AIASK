"""AIASK stock radar service.

The radar is an event-discovery layer over the unified market text/event
storage. It keeps external ingest explicit and degraded when unavailable, and
stores only structured candidate snapshots rather than trading instructions.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .market_text_source_ingest import run_market_text_source_ingest


RADAR_EVENT_TYPES = {
    "major_contract",
    "ai_compute_cooperation",
    "robotics_order",
    "ma_restructuring",
    "private_placement",
    "buyback",
    "earnings_forecast_up",
    "state_owned_investment",
    "shareholder_reduction",
    "investigation",
    "inquiry_letter",
    "earnings_warning",
    "pledge_risk",
    "policy_news",
    "fund_flow_confirmation",
    "dragon_tiger_anomaly",
    "late_session_volume",
}

POSITIVE_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], float], ...] = (
    ("ai_compute_cooperation", ("AI", "人工智能", "算力", "大模型", "智算", "数据中心"), ("AI", "算力"), 0.88),
    ("robotics_order", ("机器人", "人形机器人", "工业机器人", "订单"), ("机器人",), 0.84),
    ("major_contract", ("重大合同", "签订合同", "中标", "项目合同", "订单", "采购合同", "销售合同"), ("重大合同",), 0.82),
    ("ma_restructuring", ("并购", "收购", "重大资产重组", "资产重组", "购买资产"), ("并购重组",), 0.80),
    ("private_placement", ("定增", "向特定对象发行", "非公开发行", "再融资"), ("定增",), 0.68),
    ("buyback", ("回购", "股份回购", "增持"), ("回购",), 0.72),
    ("earnings_forecast_up", ("业绩预增", "扭亏", "净利润增长", "业绩快报"), ("业绩",), 0.76),
    ("state_owned_investment", ("国资入股", "国有资本", "控股股东变更", "实际控制人变更"), ("国资",), 0.74),
    ("policy_news", ("政策", "方案", "规划", "指导意见", "通知", "支持"), ("政策",), 0.56),
)

RISK_RULES: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("shareholder_reduction", ("减持", "被动减持", "拟减持"), 0.82),
    ("investigation", ("立案", "调查", "证监会立案", "涉嫌违法", "行政处罚"), 0.92),
    ("inquiry_letter", ("问询函", "监管函", "关注函"), 0.70),
    ("earnings_warning", ("业绩预亏", "亏损", "业绩暴雷", "业绩预减", "商誉减值"), 0.88),
    ("pledge_risk", ("质押", "冻结", "司法冻结", "平仓风险"), 0.78),
)

TIER_WEIGHTS = {"tier_a": 1.0, "tier_b": 0.82, "tier_c": 0.5}
PDF_TEXT_LIMIT = 24_000
LLM_BODY_LIMIT = 8_000


def _clean(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())[:limit] if text else ""


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _positive_int(value: Any, default: int, *, minimum: int = 0, maximum: int = 1000) -> int:
    try:
        parsed = int(default if value is None or value == "" else value)
    except Exception:
        parsed = int(default)
    return max(minimum, min(parsed, maximum))


def _normalize_codes(raw: Any) -> list[str]:
    if raw is None:
        return []
    values = raw if isinstance(raw, (list, tuple, set)) else str(raw).replace(";", ",").split(",")
    out: list[str] = []
    for value in values:
        token = _clean(value, 40)
        if token and token not in out:
            out.append(token)
    return out


def _source_tier(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"tier_a", "official", "a"}:
        return "tier_a"
    if token in {"tier_b", "institutional", "b"}:
        return "tier_b"
    return "tier_c"


def _direction_for_event(event_type: str) -> str:
    if event_type in {rule[0] for rule in RISK_RULES}:
        return "negative"
    if event_type in {"policy_news"}:
        return "neutral"
    return "positive"


def _event_type_name(event_type: str) -> str:
    return {
        "major_contract": "重大合同",
        "ai_compute_cooperation": "AI/算力合作",
        "robotics_order": "机器人订单",
        "ma_restructuring": "并购重组",
        "private_placement": "定增",
        "buyback": "回购",
        "earnings_forecast_up": "业绩预增",
        "state_owned_investment": "国资入股",
        "shareholder_reduction": "减持",
        "investigation": "立案调查",
        "inquiry_letter": "问询函",
        "earnings_warning": "业绩预警",
        "pledge_risk": "质押风险",
        "policy_news": "政策新闻",
        "fund_flow_confirmation": "资金共振",
        "dragon_tiger_anomaly": "龙虎榜异动",
        "late_session_volume": "尾盘放量",
    }.get(event_type, event_type)


def _extract_amount_text(text: str) -> str:
    patterns = [
        r"(\d+(?:\.\d+)?\s*(?:亿元|亿|万元|万|元))",
        r"(\d+(?:\.\d+)?\s*(?:billion|million|RMB|CNY|USD))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1), 80)
    return ""


def _extract_counterparties(text: str) -> list[str]:
    patterns = [
        r"与([\u4e00-\u9fffA-Za-z0-9（）()·,\-]{2,40})(?:签订|合作|达成|共同)",
        r"向([\u4e00-\u9fffA-Za-z0-9（）()·,\-]{2,40})(?:发行|出售|销售|供应)",
    ]
    out: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            token = _clean(match, 80).strip("，。、;； ")
            if token and token not in out:
                out.append(token)
            if len(out) >= 5:
                return out
    return out


def _stock_code_from_doc(doc: dict[str, Any]) -> str:
    for key in ("stock_code", "code", "symbol"):
        raw = _clean(doc.get(key), 40)
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) == 6:
            return raw or digits
    return ""


def _bare_stock_code(value: Any) -> str:
    raw = _clean(value, 40)
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 6:
        return digits[:6]
    return raw.split(".", 1)[0].strip()


def _clamp_float(value: Any, default: float = 0.0, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    return max(minimum, min(parsed, maximum))


def _list_strings(value: Any, *, limit: int = 8, item_limit: int = 120) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]
    out: list[str] = []
    for item in raw_items:
        token = _clean(item, item_limit)
        if token and token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out


def _source_doc_uids_for_doc(doc: dict[str, Any]) -> list[str]:
    return [token for token in [_clean(doc.get("doc_uid") or doc.get("event_id"), 240)] if token]


def _is_positive_direction(extraction: dict[str, Any]) -> bool:
    return str(extraction.get("direction") or "").lower() in {"positive", "up", "bullish"}


def _is_negative_direction(extraction: dict[str, Any]) -> bool:
    return str(extraction.get("direction") or "").lower() in {"negative", "down", "bearish"}


def _extract_payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data", payload)
    else:
        data = payload
    if isinstance(data, dict):
        for key in ("items", "rows", "data", "results", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
        if any(key in data for key in ("code", "name", "mainNetInflow", "netAmount", "total")):
            return [dict(data)]
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, dict)]
    return []


def _numeric_from_keys(item: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.replace(",", "").replace("，", "").replace("%", "").strip()
            if not cleaned:
                continue
            value = cleaned
        try:
            return float(value)
        except Exception:
            continue
    return None


@dataclass(frozen=True)
class RadarExtraction:
    event_type: str
    direction: str
    importance_score: float
    sentiment_score: float
    themes: list[str]
    amount_text: str
    counterparties: list[str]
    risk_flags: list[str]
    summary: str
    confidence: float
    source_doc_uids: list[str]
    llm_status: str = "rules_only"
    status: str = "provisional"

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "direction": self.direction,
            "importance_score": round(float(self.importance_score), 4),
            "sentiment_score": round(float(self.sentiment_score), 4),
            "themes": list(self.themes),
            "amount_text": self.amount_text,
            "counterparties": list(self.counterparties),
            "risk_flags": list(self.risk_flags),
            "summary": self.summary,
            "confidence": round(float(self.confidence), 4),
            "source_doc_uids": list(self.source_doc_uids),
            "llm_status": self.llm_status,
            "status": self.status,
        }


def extract_radar_event(doc: dict[str, Any]) -> RadarExtraction | None:
    title = _clean(doc.get("title") or doc.get("event_name"), 300)
    summary = _clean(doc.get("summary") or doc.get("body") or doc.get("content") or title, 1200)
    text = f"{title} {summary}"
    if not text.strip():
        return None
    source_doc_uids = [token for token in [_clean(doc.get("doc_uid") or doc.get("event_id"), 240)] if token]

    risk_hits: list[tuple[str, float]] = []
    for event_type, keywords, importance in RISK_RULES:
        if any(keyword and keyword in text for keyword in keywords):
            risk_hits.append((event_type, importance))
    if risk_hits:
        event_type, importance = max(risk_hits, key=lambda item: item[1])
        risk_flags = [_event_type_name(item[0]) for item in risk_hits]
        return RadarExtraction(
            event_type=event_type,
            direction="negative",
            importance_score=importance,
            sentiment_score=-0.75,
            themes=[_event_type_name(event_type)],
            amount_text=_extract_amount_text(text),
            counterparties=_extract_counterparties(text),
            risk_flags=risk_flags,
            summary=summary or title,
            confidence=min(0.92, 0.6 + 0.08 * len(risk_hits)),
            source_doc_uids=source_doc_uids,
        )

    positive_hits: list[tuple[str, tuple[str, ...], float]] = []
    for event_type, keywords, themes, importance in POSITIVE_RULES:
        if any(keyword and keyword in text for keyword in keywords):
            positive_hits.append((event_type, themes, importance))
    if not positive_hits:
        return None
    event_type, themes, importance = max(positive_hits, key=lambda item: item[2])
    all_themes: list[str] = []
    for _, hit_themes, _ in positive_hits:
        for theme in hit_themes:
            if theme not in all_themes:
                all_themes.append(theme)
    direction = _direction_for_event(event_type)
    return RadarExtraction(
        event_type=event_type,
        direction=direction,
        importance_score=importance,
        sentiment_score=0.66 if direction == "positive" else 0.1,
        themes=all_themes or [_event_type_name(event_type)],
        amount_text=_extract_amount_text(text),
        counterparties=_extract_counterparties(text),
        risk_flags=[],
        summary=summary or title,
        confidence=min(0.9, 0.58 + 0.08 * len(positive_hits)),
        source_doc_uids=source_doc_uids,
    )


def _unwrap_llm_extraction(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    for key in ("results", "event", "events", "extraction", "radar_event"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            first = next((item for item in value if isinstance(item, dict)), None)
            if first:
                return dict(first)
    return raw


def _validated_llm_extraction(raw: dict[str, Any], fallback: RadarExtraction, doc: dict[str, Any]) -> dict[str, Any] | None:
    payload = _unwrap_llm_extraction(raw)
    if not payload:
        return None
    fallback_payload = fallback.as_dict()
    event_type = _clean(payload.get("event_type") or payload.get("type") or fallback.event_type, 120)
    if event_type not in RADAR_EVENT_TYPES:
        event_type = fallback.event_type
    direction = _clean(payload.get("direction") or fallback.direction, 40).lower()
    if direction not in {"positive", "negative", "neutral"}:
        direction = _direction_for_event(event_type)
    importance_score = _clamp_float(payload.get("importance_score"), fallback.importance_score)
    sentiment_score = _clamp_float(payload.get("sentiment_score"), fallback.sentiment_score, minimum=-1.0, maximum=1.0)
    confidence = _clamp_float(payload.get("confidence"), fallback.confidence)
    themes = _list_strings(payload.get("themes"), limit=8, item_limit=80) or list(fallback.themes)
    risk_flags = _list_strings(payload.get("risk_flags"), limit=8, item_limit=120) or list(fallback.risk_flags)
    if direction == "negative" and not risk_flags:
        risk_flags = [_event_type_name(event_type)]
    source_uids = _list_strings(payload.get("source_doc_uids"), limit=8, item_limit=240) or fallback.source_doc_uids
    for uid in _source_doc_uids_for_doc(doc):
        if uid not in source_uids:
            source_uids.append(uid)
    summary = _clean(payload.get("summary") or fallback.summary, 1200)
    return {
        **fallback_payload,
        "event_type": event_type,
        "direction": direction,
        "importance_score": importance_score,
        "sentiment_score": sentiment_score,
        "themes": themes,
        "amount_text": _clean(payload.get("amount_text") or fallback.amount_text, 160),
        "counterparties": _list_strings(payload.get("counterparties"), limit=8, item_limit=120) or list(fallback.counterparties),
        "risk_flags": risk_flags,
        "summary": summary,
        "confidence": confidence,
        "source_doc_uids": source_uids,
        "llm_status": "ok",
        "status": "verified" if confidence >= 0.75 else "extracted",
    }


async def enhance_radar_event_with_llm(doc: dict[str, Any], fallback: RadarExtraction) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        from .strategy_llm_provider import StrategyLLMRequestError, get_strategy_llm_provider
    except Exception as exc:
        extraction = fallback.as_dict()
        extraction["llm_status"] = "unavailable"
        extraction["status"] = "provisional"
        return extraction, {"status": "unavailable", "reason": "llm_provider_import_failed", "error": f"{type(exc).__name__}: {exc}"}

    provider = get_strategy_llm_provider()
    if not provider.is_enabled():
        extraction = fallback.as_dict()
        extraction["llm_status"] = "unavailable"
        extraction["status"] = "provisional"
        return extraction, {"status": "unavailable", "reason": "llm_provider_disabled"}

    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    pdf_meta = metadata.get("radar_pdf_parse") if isinstance(metadata.get("radar_pdf_parse"), dict) else {}
    pdf_text = _clean(pdf_meta.get("text"), LLM_BODY_LIMIT)
    body = _clean(doc.get("body") or doc.get("content") or doc.get("summary") or "", LLM_BODY_LIMIT)
    input_data = {
        "schema": "RadarEventExtraction",
        "allowed_event_types": sorted(RADAR_EVENT_TYPES),
        "title": _clean(doc.get("title") or doc.get("event_name"), 300),
        "summary": _clean(doc.get("summary"), 1200),
        "body": body,
        "pdf_text": pdf_text,
        "stock_code": _stock_code_from_doc(doc),
        "source": doc.get("source"),
        "source_tier": _source_tier(doc.get("source_tier")),
        "url": doc.get("url"),
        "rule_extraction": fallback.as_dict(),
        "requirements": {
            "fields": [
                "event_type",
                "direction",
                "importance_score",
                "sentiment_score",
                "themes",
                "amount_text",
                "counterparties",
                "risk_flags",
                "summary",
                "confidence",
                "source_doc_uids",
            ],
            "no_trade_instructions": True,
        },
    }
    system_prompt = (
        "You extract structured A-share disclosure/news events for an observation-only stock radar. "
        "Return JSON only. Do not include buy/sell/hold instructions. Keep evidence concise and respect source text."
    )
    try:
        raw = await provider.call_stage(
            stage_id="stock_radar_event_extraction",
            input_data=input_data,
            system_prompt=system_prompt,
            max_tokens=700,
            temperature=0.1,
            timeout_sec=float(os.getenv("AIASK_RADAR_LLM_TIMEOUT_SEC", "20") or 20),
        )
        validated = _validated_llm_extraction(raw, fallback, doc)
        if validated is None:
            extraction = fallback.as_dict()
            extraction["llm_status"] = "failed"
            extraction["status"] = "provisional"
            return extraction, {"status": "failed", "reason": "llm_output_invalid", "raw_keys": sorted(raw.keys()) if isinstance(raw, dict) else []}
        return validated, {"status": "ok"}
    except StrategyLLMRequestError as exc:
        extraction = fallback.as_dict()
        extraction["llm_status"] = "unavailable"
        extraction["status"] = "provisional"
        return extraction, {"status": "unavailable", "reason": "llm_request_failed", "metrics": dict(getattr(exc, "metrics", {}) or {})}
    except Exception as exc:
        extraction = fallback.as_dict()
        extraction["llm_status"] = "failed"
        extraction["status"] = "provisional"
        return extraction, {"status": "failed", "reason": "llm_exception", "error": f"{type(exc).__name__}: {exc}"}


def score_radar_candidate(
    *,
    extraction: dict[str, Any],
    source_tier: str,
    confirmations: dict[str, Any] | None = None,
    risk_flags: list[str] | None = None,
) -> dict[str, Any]:
    confirmations = dict(confirmations or {})
    risks = list(risk_flags or extraction.get("risk_flags") or [])
    event_importance = max(0.0, min(float(extraction.get("importance_score") or 0.0), 1.0)) * 40
    source_score = TIER_WEIGHTS.get(_source_tier(source_tier), 0.45) * 20

    fund_confirmed = bool(confirmations.get("fund_flow", {}).get("confirmed"))
    north_confirmed = bool(confirmations.get("north_fund", {}).get("confirmed"))
    dragon_confirmed = bool(confirmations.get("dragon_tiger", {}).get("confirmed"))
    capital_score = (8 if fund_confirmed else 0) + (5 if north_confirmed else 0) + (7 if dragon_confirmed else 0)
    capital_score = min(capital_score, 20)

    sector_heat = confirmations.get("sector_heat", {})
    try:
        sector_score = max(0.0, min(float(sector_heat.get("score") or 0.0), 1.0)) * 15
    except Exception:
        sector_score = 0.0

    risk_penalty = min(30.0, 10.0 * len(risks))
    for key in ("fund_flow", "north_fund", "dragon_tiger"):
        item = confirmations.get(key)
        if isinstance(item, dict) and item.get("conflict"):
            risk_penalty = min(30.0, risk_penalty + 5.0)
    if str(extraction.get("direction") or "").lower() in {"negative", "down", "bearish"}:
        risk_penalty = min(30.0, max(risk_penalty, 18.0))
    if str(extraction.get("status") or "").lower() == "provisional" and str(extraction.get("llm_status") or "") == "unavailable":
        risk_penalty = min(30.0, risk_penalty + 8.0)

    score = max(0.0, min(100.0, event_importance + source_score + capital_score + sector_score - risk_penalty))
    if score >= 80:
        tier = "alert"
    elif score >= 60:
        tier = "watch"
    elif score >= 40:
        tier = "observe"
    else:
        tier = "reject"
    return {
        "radar_score": round(score, 2),
        "tier": tier,
        "component_scores": {
            "event_importance": round(event_importance, 2),
            "source_credibility": round(source_score, 2),
            "capital_confirmation": round(capital_score, 2),
            "sector_heat": round(sector_score, 2),
            "risk_penalty": round(risk_penalty, 2),
        },
    }


def _high_confidence_candidate(candidate: dict[str, Any]) -> bool:
    extraction = candidate.get("extraction") if isinstance(candidate.get("extraction"), dict) else {}
    llm_status = str(extraction.get("llm_status") or "").strip().lower()
    status = str(extraction.get("status") or candidate.get("status") or "").strip().lower()
    try:
        confidence = float(extraction.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    if llm_status in {"", "unavailable", "rules_only", "failed", "fallback"}:
        return False
    if status in {"", "provisional", "degraded", "rejected"}:
        return False
    return confidence >= 0.75


def _safe_feed_name(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace(":", "_") or "rss"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{host}_{digest}"


def _rss_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        child = element.find(name)
        if child is not None and child.text:
            return _clean(child.text, 4000)
    return ""


def fetch_rss_feed_documents(feed_url: str, *, limit: int = 50, timeout: float = 12.0) -> list[dict[str, Any]]:
    response = requests.get(feed_url, timeout=timeout, headers={"User-Agent": "AIASK-StockRadar/1.0"})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows = root.findall(".//item")
    if not rows:
        rows = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    docs: list[dict[str, Any]] = []
    feed_name = _safe_feed_name(feed_url)
    for item in rows[: max(0, min(int(limit or 0), 200))]:
        title = _rss_text(item, ("title", "{http://www.w3.org/2005/Atom}title"))
        summary = _rss_text(
            item,
            ("description", "summary", "content", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"),
        )
        link = _rss_text(item, ("link", "{http://www.w3.org/2005/Atom}link"))
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            link = _clean(atom_link.attrib.get("href") or link, 1000)
        published_at = _rss_text(item, ("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"))
        if not title:
            continue
        original = link or f"{feed_url}:{title}:{published_at}"
        docs.append(
            {
                "doc_uid": f"rss:{feed_name}:{hashlib.sha1(original.encode('utf-8')).hexdigest()[:18]}",
                "title": title,
                "summary": summary or title,
                "content": " ".join(part for part in (title, summary[:800]) if part),
                "published_at": published_at,
                "date": published_at,
                "source": "rsshub",
                "source_tier": "tier_c",
                "provider": feed_name,
                "original_id": original[:240],
                "url": link,
                "reliability_score": 0.42,
                "metadata": {"feed_url": feed_url, "copyright_storage": "summary_only"},
            }
        )
    return docs


def _configured_rss_feeds() -> list[str]:
    raw = str(os.getenv("AIASK_RADAR_RSS_FEEDS") or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.replace("\n", ",").replace(";", ",").split(",") if item.strip()]


def _pdf_url_from_doc(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    for key in ("pdf_url", "url"):
        token = _clean(doc.get(key), 1000)
        if token:
            return token
    for key in ("pdf_url", "source_url", "url"):
        token = _clean(metadata.get(key), 1000)
        if token:
            return token
    return ""


def _looks_like_pdf_url(url: str) -> bool:
    if not url:
        return False
    path = (urlparse(url).path or url).lower()
    return path.endswith(".pdf") or ".pdf" in path


def _pdf_cache_dir() -> Path:
    raw = str(os.getenv("AIASK_RADAR_PDF_CACHE_DIR") or "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".aiask" / "stock-radar" / "pdfs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _download_pdf_file(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    max_bytes = _positive_int(os.getenv("AIASK_RADAR_PDF_MAX_BYTES"), 30 * 1024 * 1024, minimum=1024, maximum=120 * 1024 * 1024)
    cache_hint = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "AIASK-StockRadar/1.0"})
    response.raise_for_status()
    content = response.content or b""
    if len(content) > max_bytes:
        raise ValueError(f"pdf exceeds max bytes: {len(content)} > {max_bytes}")
    checksum = hashlib.sha256(content).hexdigest()
    path = _pdf_cache_dir() / f"{checksum[:32] or cache_hint}.pdf"
    if not path.exists():
        path.write_bytes(content)
    return {"local_pdf_path": str(path), "checksum": checksum, "bytes": len(content)}


def _parse_pdf_with_pymupdf(path: Path) -> dict[str, Any]:
    try:
        import fitz  # type: ignore
    except Exception as exc:
        return {"parser": "pymupdf", "status": "unavailable", "error": f"{type(exc).__name__}: {exc}", "text": "", "pages": 0}
    try:
        parts: list[str] = []
        with fitz.open(str(path)) as pdf:
            pages = int(getattr(pdf, "page_count", 0) or len(pdf))
            for page in pdf:
                parts.append(str(page.get_text("text") or ""))
                if sum(len(part) for part in parts) >= PDF_TEXT_LIMIT:
                    break
        text = _clean(" ".join(parts), PDF_TEXT_LIMIT)
        return {"parser": "pymupdf", "status": "ok" if text else "empty", "text": text, "pages": pages}
    except Exception as exc:
        return {"parser": "pymupdf", "status": "failed", "error": f"{type(exc).__name__}: {exc}", "text": "", "pages": 0}


def _parse_pdf_with_pdfplumber(path: Path) -> dict[str, Any]:
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        return {"parser": "pdfplumber", "status": "unavailable", "error": f"{type(exc).__name__}: {exc}", "text": "", "pages": 0}
    try:
        parts: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages:
                parts.append(str(page.extract_text() or ""))
                if sum(len(part) for part in parts) >= PDF_TEXT_LIMIT:
                    break
        text = _clean(" ".join(parts), PDF_TEXT_LIMIT)
        return {"parser": "pdfplumber", "status": "ok" if text else "empty", "text": text, "pages": pages}
    except Exception as exc:
        return {"parser": "pdfplumber", "status": "failed", "error": f"{type(exc).__name__}: {exc}", "text": "", "pages": 0}


def _parse_pdf_with_paddleocr(path: Path) -> dict[str, Any]:
    if not _as_bool(os.getenv("AIASK_RADAR_ENABLE_OCR"), False):
        return {"parser": "paddleocr", "status": "disabled", "reason": "ocr_disabled", "text": "", "pages": 0}
    try:
        import fitz  # type: ignore
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:
        return {"parser": "paddleocr", "status": "unavailable", "error": f"{type(exc).__name__}: {exc}", "text": "", "pages": 0}
    max_pages = _positive_int(os.getenv("AIASK_RADAR_OCR_MAX_PAGES"), 3, minimum=1, maximum=12)
    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="ch")
        parts: list[str] = []
        with tempfile.TemporaryDirectory(prefix="aiask_radar_ocr_") as tmpdir:
            with fitz.open(str(path)) as pdf:
                pages = min(int(getattr(pdf, "page_count", 0) or len(pdf)), max_pages)
                for page_idx in range(pages):
                    page = pdf.load_page(page_idx)
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    img_path = Path(tmpdir) / f"page_{page_idx}.png"
                    pix.save(str(img_path))
                    result = ocr.ocr(str(img_path), cls=True)
                    for block in result or []:
                        for line in block or []:
                            if isinstance(line, (list, tuple)) and len(line) >= 2:
                                text_part = line[1][0] if isinstance(line[1], (list, tuple)) and line[1] else ""
                                if text_part:
                                    parts.append(str(text_part))
                    if sum(len(part) for part in parts) >= PDF_TEXT_LIMIT:
                        break
        text = _clean(" ".join(parts), PDF_TEXT_LIMIT)
        return {"parser": "paddleocr", "status": "ok" if text else "empty", "text": text, "pages": max_pages, "ocr_used": True}
    except Exception as exc:
        return {"parser": "paddleocr", "status": "failed", "error": f"{type(exc).__name__}: {exc}", "text": "", "pages": 0}


def _extract_pdf_text_from_file(path: str | Path) -> dict[str, Any]:
    pdf_path = Path(path)
    attempts: list[dict[str, Any]] = []
    best_text = ""
    best_parser = ""
    best_pages = 0
    for parser in (_parse_pdf_with_pymupdf, _parse_pdf_with_pdfplumber):
        result = parser(pdf_path)
        attempts.append({key: value for key, value in result.items() if key != "text"})
        text = _clean(result.get("text"), PDF_TEXT_LIMIT)
        if len(text) > len(best_text):
            best_text = text
            best_parser = str(result.get("parser") or "")
            best_pages = int(result.get("pages") or best_pages or 0)
        if text and (len(text) / max(int(result.get("pages") or 1), 1)) >= 80:
            break
    density = round(len(best_text) / max(best_pages or 1, 1), 4)
    if best_text and density >= 80:
        return {
            "status": "ok",
            "parser": best_parser,
            "text": best_text,
            "pages": best_pages,
            "text_density": density,
            "parser_attempts": attempts,
        }
    ocr_result = _parse_pdf_with_paddleocr(pdf_path)
    attempts.append({key: value for key, value in ocr_result.items() if key != "text"})
    ocr_text = _clean(ocr_result.get("text"), PDF_TEXT_LIMIT)
    if len(ocr_text) > len(best_text):
        best_text = ocr_text
        best_parser = str(ocr_result.get("parser") or best_parser)
        best_pages = int(ocr_result.get("pages") or best_pages or 0)
        density = round(len(best_text) / max(best_pages or 1, 1), 4)
    if best_text:
        status = "ok" if str(ocr_result.get("status")) == "ok" else "degraded"
        return {
            "status": status,
            "reason": "low_text_density" if status == "degraded" else None,
            "parser": best_parser,
            "text": best_text,
            "pages": best_pages,
            "text_density": density,
            "ocr_status": ocr_result.get("status"),
            "parser_attempts": attempts,
        }
    unavailable = [item for item in attempts if item.get("status") == "unavailable"]
    return {
        "status": "degraded",
        "reason": "pdf_parser_unavailable" if len(unavailable) >= 2 else "pdf_text_empty",
        "parser": best_parser or "none",
        "text": "",
        "pages": best_pages,
        "text_density": 0.0,
        "ocr_status": ocr_result.get("status"),
        "parser_attempts": attempts,
    }


def _pdf_parse_status(doc: dict[str, Any], *, parse_pdf: bool, allow_network: bool) -> dict[str, Any]:
    url = _pdf_url_from_doc(doc)
    if not _looks_like_pdf_url(url):
        return {"status": "not_pdf"}
    if not parse_pdf:
        return {"status": "disabled", "url": url}
    if not allow_network:
        return {"status": "degraded", "reason": "network_disabled", "url": url}
    try:
        downloaded = _download_pdf_file(url)
        parsed = _extract_pdf_text_from_file(downloaded["local_pdf_path"])
        return {
            **parsed,
            "url": url,
            "local_pdf_path": downloaded["local_pdf_path"],
            "checksum": downloaded["checksum"],
            "bytes": downloaded["bytes"],
            "parser_order": ["pymupdf", "pdfplumber", "paddleocr"],
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "reason": "pdf_download_or_parse_failed",
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
            "parser_order": ["pymupdf", "pdfplumber", "paddleocr"],
        }


def _pdf_metadata_for_persist(pdf_status: dict[str, Any], checksum: Any = None) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            **pdf_status,
            "checksum": pdf_status.get("checksum") or checksum,
        }.items()
        if key not in {"text"} and value is not None
    }


async def _merge_document_metadata(db, doc_uid: str, metadata: dict[str, Any]) -> bool:
    handler = getattr(db, "merge_market_document_metadata", None)
    if not callable(handler):
        return False
    updated = await handler(doc_uid, metadata)
    return bool(updated)


async def _list_recent_market_documents(db, *, days: int, limit: int) -> list[dict[str, Any]]:
    since = (date.today() - timedelta(days=max(0, int(days or 0)))).isoformat()
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT doc_uid, stock_code, doc_type, source, source_tier, provider, original_id,
                   title, summary, body, url, published_at, fetched_at, checksum,
                   reliability_score, crawl_status, metadata
            FROM market_documents
            WHERE doc_type IN ('notice', 'news')
              AND COALESCE(substr(published_at, 1, 10), substr(fetched_at, 1, 10), '') >= $1
            ORDER BY COALESCE(published_at, fetched_at, created_at) DESC
            LIMIT $2
            """,
            since,
            max(1, min(int(limit or 200), 2000)),
        )
    docs: list[dict[str, Any]] = []
    decoder = getattr(db, "_decode_json_field", None)
    for row in rows:
        item = dict(row)
        if callable(decoder):
            item["metadata"] = decoder(item.get("metadata"), {})
        docs.append(item)
    return docs


async def _persist_rss_documents(db, docs: list[dict[str, Any]], *, embed: bool) -> dict[str, Any]:
    if not docs:
        return {"documents": 0, "feeds": 0}
    saved = await db.save_market_documents(
        "MARKET",
        "news",
        docs,
        embed=embed,
        chunk_size=1000,
        overlap=120,
        version="radar_v1",
    )
    try:
        from .market_event_sources import persist_normalized_events

        normalized = await persist_normalized_events(db, "MARKET", "news", docs)
    except Exception as exc:
        normalized = {"error": f"{type(exc).__name__}: {exc}"}
    return {**saved, "normalized_events": normalized}


def _candidate_event_id(doc: dict[str, Any], extraction: dict[str, Any]) -> str:
    basis = "|".join(
        [
            _clean(doc.get("doc_uid") or doc.get("event_id"), 240),
            _clean(extraction.get("event_type"), 120),
            _clean(doc.get("stock_code") or doc.get("code") or "MARKET", 40),
        ]
    )
    return f"radar_evt_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:24]}"


def _status_from_tool_payload(payload: dict[str, Any]) -> str:
    if payload.get("success") is False:
        return "degraded"
    if payload.get("degraded") or payload.get("fallback_used") or payload.get("fallback_reason"):
        return "degraded"
    return "ok"


def _provider_meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    quality = meta.get("quality") if isinstance(meta.get("quality"), dict) else {}
    return {
        "source": payload.get("source"),
        "source_chain": payload.get("source_chain") or quality.get("source_chain"),
        "fallback_reason": payload.get("fallback_reason") or quality.get("fallback_reason"),
        "degraded": bool(payload.get("degraded") or meta.get("degraded")),
        "error": payload.get("error"),
    }


def _fund_flow_confirmation(payload: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    items = _extract_payload_items(payload)
    item = items[0] if items else {}
    net = _numeric_from_keys(
        item,
        (
            "mainNetInflow",
            "main_net_inflow",
            "mainBuyNet",
            "net_inflow",
            "netAmount",
            "net_amount",
        ),
    )
    if not items or net is None:
        return {"status": "degraded", "confirmed": False, "reason": "fund_flow_empty_or_missing_net", **_provider_meta(payload)}
    positive = _is_positive_direction(extraction)
    negative = _is_negative_direction(extraction)
    confirmed = (positive and net > 0) or (negative and net < 0)
    conflict = (positive and net < 0) or (negative and net > 0)
    return {
        "status": _status_from_tool_payload(payload),
        "confirmed": bool(confirmed),
        "conflict": bool(conflict),
        "main_net_inflow": net,
        "source": item.get("source") or payload.get("source"),
        **_provider_meta(payload),
    }


def _north_fund_confirmation(payload: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    items = _extract_payload_items(payload)
    totals = [
        value
        for item in items[:3]
        if (value := _numeric_from_keys(item, ("total", "north_money", "net_amount", "netAmount"))) is not None
    ]
    if not totals:
        return {"status": "degraded", "confirmed": False, "reason": "north_fund_empty_or_missing_total", **_provider_meta(payload)}
    recent_total = sum(totals)
    positive = _is_positive_direction(extraction)
    negative = _is_negative_direction(extraction)
    confirmed = (positive and recent_total > 0) or (negative and recent_total < 0)
    conflict = (positive and recent_total < 0) or (negative and recent_total > 0)
    return {
        "status": _status_from_tool_payload(payload),
        "confirmed": bool(confirmed),
        "conflict": bool(conflict),
        "recent_total": recent_total,
        "days_used": len(totals),
        "market_wide": True,
        **_provider_meta(payload),
    }


def _dragon_tiger_confirmation(payload: dict[str, Any], symbol: str, extraction: dict[str, Any]) -> dict[str, Any]:
    bare = _bare_stock_code(symbol)
    items = _extract_payload_items(payload)
    matched = [item for item in items if not bare or _bare_stock_code(item.get("code") or item.get("stock_code")) == bare]
    if not matched:
        return {
            "status": "degraded" if payload.get("degraded") or not items else "ok",
            "confirmed": False,
            "reason": "dragon_tiger_no_symbol_match" if items else "dragon_tiger_empty",
            "alias_policy": "alias_mapping_only",
            **_provider_meta(payload),
        }
    net_total = sum(_numeric_from_keys(item, ("netAmount", "net_amount", "net_buy")) or 0.0 for item in matched)
    positive = _is_positive_direction(extraction)
    negative = _is_negative_direction(extraction)
    confirmed = (positive and net_total > 0) or (negative and net_total < 0)
    conflict = (positive and net_total < 0) or (negative and net_total > 0)
    return {
        "status": _status_from_tool_payload(payload),
        "confirmed": bool(confirmed),
        "conflict": bool(conflict),
        "net_amount": net_total,
        "rows": matched[:5],
        "alias_policy": "alias_mapping_only",
        **_provider_meta(payload),
    }


def _sector_heat_confirmation(sector_payload: dict[str, Any], concept_payload: dict[str, Any], themes: list[str]) -> dict[str, Any]:
    tokens = [token.lower() for token in _list_strings(themes, limit=12, item_limit=80)]
    if not tokens:
        return {"status": "degraded", "score": 0.0, "themes": [], "reason": "themes_empty"}
    rows = [*(_extract_payload_items(sector_payload)), *(_extract_payload_items(concept_payload))]
    if not rows:
        return {
            "status": "degraded",
            "score": 0.0,
            "themes": list(themes),
            "reason": "sector_concept_flow_empty",
            "sector": _provider_meta(sector_payload),
            "concept": _provider_meta(concept_payload),
        }
    matches: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        name = _clean(row.get("name") or row.get("block_name") or row.get("industry") or row.get("concept"), 120)
        name_lower = name.lower()
        if not name_lower or not any(token and (token in name_lower or name_lower in token) for token in tokens):
            continue
        net = _numeric_from_keys(row, ("mainNetInflow", "main_net_inflow", "net_amount", "netAmount", "totalAmount"))
        change = _numeric_from_keys(row, ("changePercent", "change_pct", "avg_change_pct"))
        positive_net = 1.0 if net is not None and net > 0 else 0.0
        rank_score = max(0.0, 1.0 - idx / max(len(rows), 1))
        change_score = 0.2 if change is not None and change > 0 else 0.0
        score = min(1.0, 0.45 + 0.35 * positive_net + 0.2 * rank_score + change_score)
        matches.append({"name": name, "score": round(score, 4), "main_net_inflow": net, "change_percent": change, "source": row.get("source")})
    if not matches:
        return {
            "status": "degraded" if sector_payload.get("degraded") or concept_payload.get("degraded") else "ok",
            "score": 0.0,
            "themes": list(themes),
            "reason": "theme_not_in_top_sector_concept_flow",
            "sector": _provider_meta(sector_payload),
            "concept": _provider_meta(concept_payload),
        }
    score = max(float(item["score"]) for item in matches)
    return {
        "status": "ok",
        "score": round(score, 4),
        "themes": list(themes),
        "matches": matches[:6],
        "sector": _provider_meta(sector_payload),
        "concept": _provider_meta(concept_payload),
    }


def _late_session_from_bars(rows: list[dict[str, Any]], extraction: dict[str, Any]) -> dict[str, Any]:
    if len(rows) < 8:
        return {"status": "disabled", "confirmed": False, "reason": "minute_line_insufficient_bars", "bars": len(rows)}

    def _time_of(row: dict[str, Any]) -> str:
        raw = _clean(row.get("trade_time") or row.get("time") or row.get("datetime") or row.get("date"), 32)
        return raw[-8:][:5] if ":" in raw else raw[-4:-2] + ":" + raw[-2:] if len(raw) >= 4 else raw

    late: list[dict[str, Any]] = []
    prev: list[dict[str, Any]] = []
    for row in rows:
        t = _time_of(row)
        if "14:30" <= t <= "15:00":
            late.append(row)
        elif "14:00" <= t < "14:30":
            prev.append(row)
    if not late or not prev:
        return {"status": "disabled", "confirmed": False, "reason": "late_session_window_unavailable", "bars": len(rows)}
    late_amount = sum(_numeric_from_keys(row, ("amount", "turnover", "money")) or 0.0 for row in late)
    prev_amount = sum(_numeric_from_keys(row, ("amount", "turnover", "money")) or 0.0 for row in prev)
    ratio = late_amount / prev_amount if prev_amount > 0 else 0.0
    first_close = _numeric_from_keys(late[0], ("close", "price"))
    last_close = _numeric_from_keys(late[-1], ("close", "price"))
    price_direction = 0.0 if first_close in {None, 0} or last_close is None else (last_close - first_close) / abs(first_close)
    confirmed = ratio >= 1.5 and ((_is_positive_direction(extraction) and price_direction >= 0) or (_is_negative_direction(extraction) and price_direction <= 0))
    return {
        "status": "ok",
        "confirmed": bool(confirmed),
        "amount_ratio": round(ratio, 4),
        "late_amount": late_amount,
        "previous_amount": prev_amount,
        "price_direction": round(price_direction, 6),
        "bars": len(rows),
    }


async def _late_session_confirmation(db: Any, symbol: str, extraction: dict[str, Any]) -> dict[str, Any]:
    bare = _bare_stock_code(symbol)
    if not bare or bare == "MARKET":
        return {"status": "disabled", "confirmed": False, "reason": "symbol_unavailable"}
    try:
        tables = (
            "stock_minute_bars",
            "minute_bars",
            "stock_minute_kline",
            "tdx_minute_kline",
            "tdx_minute_bars",
        )
        async with db.acquire() as conn:
            for table in tables:
                exists = await conn.fetchval("SELECT name FROM sqlite_master WHERE type = 'table' AND name = $1", table)
                if not exists:
                    continue
                columns = {str(row["name"]) for row in await conn.fetch(f"PRAGMA table_info({table})")}
                code_col = next((item for item in ("code", "stock_code", "symbol") if item in columns), None)
                time_col = next((item for item in ("trade_time", "time", "datetime", "date") if item in columns), None)
                if not code_col or not time_col:
                    continue
                rows = await conn.fetch(
                    f"""
                    SELECT *
                    FROM {table}
                    WHERE {code_col} = $1
                    ORDER BY {time_col} DESC
                    LIMIT 260
                    """,
                    bare,
                )
                if rows:
                    ordered = [dict(row) for row in reversed(rows)]
                    return {**_late_session_from_bars(ordered, extraction), "source": table}
        return {"status": "disabled", "confirmed": False, "reason": "minute_line_table_unavailable"}
    except Exception as exc:
        return {"status": "degraded", "confirmed": False, "reason": "minute_line_query_failed", "error": f"{type(exc).__name__}: {exc}"}


async def _confirmation_factors(db: Any, symbol: str, extraction: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "fund_flow": {"status": "degraded", "confirmed": False, "reason": "fund_flow_adapter_unavailable"},
        "north_fund": {"status": "degraded", "confirmed": False, "reason": "north_fund_adapter_unavailable"},
        "dragon_tiger": {"status": "degraded", "confirmed": False, "reason": "dragon_tiger_adapter_unavailable", "alias_policy": "alias_mapping_only"},
        "sector_heat": {"status": "degraded", "score": 0.0, "themes": list(extraction.get("themes") or []), "reason": "sector_heat_adapter_unavailable"},
    }
    if not symbol or symbol == "MARKET":
        return {
            **defaults,
            "late_session_volume": {"status": "disabled", "confirmed": False, "reason": "symbol_unavailable"},
            "symbol": symbol,
        }
    try:
        from akshare_mcp.tools import fund_flow as fund_flow_tools
    except Exception as exc:
        reason = f"fund_flow_tools_import_failed:{type(exc).__name__}"
        return {
            **{key: {**value, "reason": reason} for key, value in defaults.items()},
            "late_session_volume": await _late_session_confirmation(db, symbol, extraction),
            "symbol": symbol,
        }

    results = dict(defaults)
    bare = _bare_stock_code(symbol)
    try:
        payload = fund_flow_tools.get_stock_fund_flow(code=bare, prefer_db=True)
        results["fund_flow"] = _fund_flow_confirmation(payload if isinstance(payload, dict) else {}, extraction)
    except Exception as exc:
        results["fund_flow"] = {"status": "degraded", "confirmed": False, "reason": "fund_flow_failed", "error": f"{type(exc).__name__}: {exc}"}
    try:
        payload = fund_flow_tools.get_north_fund(days=3)
        results["north_fund"] = _north_fund_confirmation(payload if isinstance(payload, dict) else {}, extraction)
    except Exception as exc:
        results["north_fund"] = {"status": "degraded", "confirmed": False, "reason": "north_fund_failed", "error": f"{type(exc).__name__}: {exc}"}
    try:
        payload = fund_flow_tools.get_dragon_tiger(stock_code=bare)
        results["dragon_tiger"] = _dragon_tiger_confirmation(payload if isinstance(payload, dict) else {}, bare, extraction)
    except Exception as exc:
        results["dragon_tiger"] = {
            "status": "degraded",
            "confirmed": False,
            "reason": "dragon_tiger_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "alias_policy": "alias_mapping_only",
        }
    try:
        sector_payload = fund_flow_tools.get_sector_fund_flow(top_n=30)
    except Exception as exc:
        sector_payload = {"success": False, "error": f"{type(exc).__name__}: {exc}", "degraded": True}
    try:
        concept_payload = fund_flow_tools.get_concept_fund_flow(top_n=30)
    except Exception as exc:
        concept_payload = {"success": False, "error": f"{type(exc).__name__}: {exc}", "degraded": True}
    results["sector_heat"] = _sector_heat_confirmation(
        sector_payload if isinstance(sector_payload, dict) else {},
        concept_payload if isinstance(concept_payload, dict) else {},
        list(extraction.get("themes") or []),
    )
    results["late_session_volume"] = await _late_session_confirmation(db, symbol, extraction)
    results["symbol"] = symbol
    return {
        **results,
    }


def _source_chain(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "doc_uid": doc.get("doc_uid") or doc.get("event_id"),
            "source": doc.get("source"),
            "provider": doc.get("provider"),
            "source_tier": _source_tier(doc.get("source_tier")),
            "url": doc.get("url"),
            "published_at": doc.get("published_at"),
        }
    ]


async def run_stock_radar(
    db,
    *,
    mode: str = "dry_run",
    days: Any = 3,
    limit: Any = 80,
    stock_codes: Any = None,
    allow_network: Any = False,
    embed: Any = False,
    parse_pdf: Any = True,
    include_rss: Any = True,
    ingest_market_text: Any = True,
) -> dict[str, Any]:
    resolved_mode = _clean(mode or "dry_run", 80) or "dry_run"
    resolved_days = _positive_int(days, 3, minimum=1, maximum=10)
    resolved_limit = _positive_int(limit, 80, minimum=1, maximum=500)
    resolved_allow_network = _as_bool(allow_network, False)
    resolved_embed = _as_bool(embed, False)
    resolved_parse_pdf = _as_bool(parse_pdf, True)
    resolved_include_rss = _as_bool(include_rss, True)
    resolved_ingest = _as_bool(ingest_market_text, True)
    started_at = datetime.now(timezone.utc).isoformat()
    run = await db.upsert_stock_radar_run(
        {
            "mode": resolved_mode,
            "status": "running",
            "started_at": started_at,
            "summary": {
                "days": resolved_days,
                "limit": resolved_limit,
                "allow_network": resolved_allow_network,
                "stock_codes": _normalize_codes(stock_codes),
            },
            "degraded_flags": [] if resolved_allow_network else ["network_disabled"],
            "metadata": {"schema": "stock_radar_v1"},
        }
    )
    run_id = str(run.get("run_id") or "")
    degraded_flags: list[str] = [] if resolved_allow_network else ["network_disabled"]
    errors: list[dict[str, Any]] = []
    ingest_result: dict[str, Any] = {}
    rss_saved: dict[str, Any] = {}

    try:
        if resolved_ingest:
            ingest_result = await run_market_text_source_ingest(
                db,
                stock_codes=_normalize_codes(stock_codes),
                doc_types=["notice", "news"],
                news_limit=20,
                notice_limit=20,
                official_notice_limit=resolved_limit,
                notice_days=resolved_days,
                code_notice_limit=0,
                code_notice_code_limit=0,
                research_code_limit=0,
                embed=resolved_embed,
                build_snapshot=False,
                activate_snapshot=False,
                allow_network=resolved_allow_network,
                dry_run=False,
            )
            for error in list(ingest_result.get("errors") or []):
                errors.append(dict(error))
            if ingest_result.get("quality_flags"):
                degraded_flags.extend(str(item) for item in list(ingest_result.get("quality_flags") or []))

        rss_docs: list[dict[str, Any]] = []
        if resolved_include_rss:
            feeds = _configured_rss_feeds()
            if not feeds:
                degraded_flags.append("rss_feeds_not_configured")
            elif not resolved_allow_network:
                degraded_flags.append("rss_network_disabled")
            else:
                for feed in feeds:
                    try:
                        rss_docs.extend(fetch_rss_feed_documents(feed, limit=30))
                    except Exception as exc:
                        errors.append({"source": "rss", "feed_url": feed, "error": f"{type(exc).__name__}: {exc}"})
                rss_saved = await _persist_rss_documents(db, rss_docs, embed=resolved_embed)

        docs = await _list_recent_market_documents(db, days=resolved_days, limit=resolved_limit * 4)
        candidates: list[dict[str, Any]] = []
        for doc in docs:
            extraction_obj = extract_radar_event(doc)
            if extraction_obj is None:
                continue
            symbol = _stock_code_from_doc(doc) or "MARKET"
            if symbol == "MARKET" and extraction_obj.event_type not in {"policy_news"}:
                continue
            metadata = dict(doc.get("metadata") or {})
            pdf_status = _pdf_parse_status(doc, parse_pdf=resolved_parse_pdf, allow_network=resolved_allow_network)
            if pdf_status.get("status") in {"degraded", "disabled"}:
                degraded_flags.append(f"pdf_parse_{pdf_status.get('status')}")
            pdf_metadata = {
                "radar_pdf_parse": _pdf_metadata_for_persist(pdf_status, checksum=doc.get("checksum"))
            }
            if pdf_status.get("text") and not doc.get("body"):
                doc["body"] = _clean(pdf_status.get("text"), LLM_BODY_LIMIT)
            metadata.update(pdf_metadata)
            doc["metadata"] = {
                **metadata,
                "radar_pdf_parse": {
                    **pdf_metadata["radar_pdf_parse"],
                    "text": _clean(pdf_status.get("text"), LLM_BODY_LIMIT) if pdf_status.get("text") else "",
                },
            }
            if pdf_status.get("status") != "not_pdf":
                try:
                    if not await _merge_document_metadata(db, _clean(doc.get("doc_uid"), 240), pdf_metadata):
                        degraded_flags.append("pdf_metadata_persist_unavailable")
                except Exception as exc:
                    degraded_flags.append("pdf_metadata_persist_failed")
                    errors.append({"source": "market_documents", "error": f"{type(exc).__name__}: {exc}"})
            extraction, llm_meta = await enhance_radar_event_with_llm(doc, extraction_obj)
            if llm_meta and llm_meta.get("status") != "ok":
                degraded_flags.append("llm_unavailable_rules_only" if llm_meta.get("status") == "unavailable" else "llm_failed_rules_only")
                errors.append({"source": "llm", **llm_meta})
            confirmations = await _confirmation_factors(db, symbol, extraction)
            score = score_radar_candidate(
                extraction=extraction,
                source_tier=_source_tier(doc.get("source_tier")),
                confirmations=confirmations,
                risk_flags=list(extraction.get("risk_flags") or []),
            )
            event_id = _candidate_event_id(doc, extraction)
            candidate = await db.upsert_stock_radar_candidate(
                {
                    "run_id": run_id,
                    "symbol": symbol,
                    "stock_name": doc.get("stock_name") or "",
                    "tier": score["tier"],
                    "radar_score": score["radar_score"],
                    "event_id": event_id,
                    "event_type": extraction["event_type"],
                    "direction": extraction["direction"],
                    "summary": extraction["summary"],
                    "source_doc_uids": extraction["source_doc_uids"],
                    "source_chain": _source_chain(doc),
                    "extraction": {**extraction, "score": score},
                    "confirmations": confirmations,
                    "risk_flags": extraction.get("risk_flags") or [],
                    "push_status": "pending",
                }
            )
            candidates.append(candidate)
            if len(candidates) >= resolved_limit:
                break

        tier_counts: dict[str, int] = {}
        for candidate in candidates:
            tier = str(candidate.get("tier") or "unknown")
            tier_counts[tier] = int(tier_counts.get(tier) or 0) + 1
        completed = await db.upsert_stock_radar_run(
            {
                "run_id": run_id,
                "mode": resolved_mode,
                "status": "completed",
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "candidate_count": len(candidates),
                    "tier_counts": tier_counts,
                    "docs_scanned": len(docs),
                    "ingest": {
                        "totals": ingest_result.get("totals", {}),
                        "fetched": ingest_result.get("fetched", {}),
                    },
                    "rss": rss_saved,
                    "source_policy": "local_first_explicit_external_ingest",
                },
                "degraded_flags": sorted(dict.fromkeys(degraded_flags)),
                "error": None,
                "metadata": {
                    "event_types": sorted(RADAR_EVENT_TYPES),
                    "no_trade_instructions": True,
                    "allow_network": resolved_allow_network,
                },
            }
        )
        digest = await db.summarize_stock_radar(run_id=run_id, limit=20)
        return {
            "object": "stock_radar.run",
            "success": True,
            "data": {
                "run": completed,
                "candidates": candidates,
                "candidate_count": len(candidates),
                "tier_counts": tier_counts,
                "digest": digest,
                "degraded_flags": sorted(dict.fromkeys(degraded_flags)),
                "errors": errors,
            },
            "error": None,
        }
    except Exception as exc:
        failed = await db.upsert_stock_radar_run(
            {
                "run_id": run_id,
                "mode": resolved_mode,
                "status": "failed",
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "summary": {"errors": errors},
                "degraded_flags": sorted(dict.fromkeys(degraded_flags)),
                "error": f"{type(exc).__name__}: {exc}",
                "metadata": {"schema": "stock_radar_v1"},
            }
        )
        return {
            "object": "stock_radar.run",
            "success": False,
            "data": {"run": failed, "degraded_flags": sorted(dict.fromkeys(degraded_flags)), "errors": errors},
            "error": f"{type(exc).__name__}: {exc}",
            "error_code": "STOCK_RADAR_RUN_FAILED",
        }


async def stock_radar_status(db, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(params or {})
    return await db.summarize_stock_radar(
        run_id=_clean(payload.get("run_id"), 220) or None,
        limit=_positive_int(payload.get("limit"), 20, minimum=1, maximum=200),
    )


async def stock_radar_candidates(db, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(params or {})
    candidates = await db.list_stock_radar_candidates(
        run_id=_clean(payload.get("run_id"), 220) or None,
        tier=_clean(payload.get("tier"), 40) or None,
        symbol=_clean(payload.get("symbol") or payload.get("stock_code"), 40) or None,
        min_score=float(payload["min_score"]) if payload.get("min_score") not in {None, ""} else None,
        limit=_positive_int(payload.get("limit"), 100, minimum=1, maximum=500),
    )
    return {"object": "stock_radar.candidates", "status": "ready", "candidates": candidates, "count": len(candidates)}


async def stock_radar_digest(db, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(params or {})
    digest = await db.summarize_stock_radar(
        run_id=_clean(payload.get("run_id"), 220) or None,
        limit=_positive_int(payload.get("limit"), 20, minimum=1, maximum=100),
    )
    channels = payload.get("channels") or ["wecom", "telegram"]
    if isinstance(channels, str):
        channels = [item.strip() for item in channels.split(",") if item.strip()]
    preview = _clean(payload.get("message") or digest.get("digest_preview"), 4000)
    if _as_bool(payload.get("record_preview"), False):
        run = digest.get("latest_run") if isinstance(digest.get("latest_run"), dict) else {}
        await db.save_stock_radar_push_log(
            {
                "run_id": run.get("run_id"),
                "channel": "preview",
                "platform": ",".join(str(item) for item in list(channels or [])),
                "status": "preview",
                "message_preview": preview,
                "candidate_count": len(list(digest.get("candidates") or [])),
                "metadata": {"no_trade_instructions": True},
            }
        )
    logs = await db.list_stock_radar_push_logs(
        run_id=(digest.get("latest_run") or {}).get("run_id") if isinstance(digest.get("latest_run"), dict) else None,
        limit=20,
    )
    return {
        "object": "stock_radar.digest",
        "status": digest.get("status") or "unknown",
        "channels": list(channels or []),
        "digest_preview": preview,
        "candidates": list(digest.get("candidates") or []),
        "push_logs": logs,
        "disclaimer": "observation_pool_only_no_buy_sell_instruction",
    }


async def push_stock_radar_digest(db, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(params or {})
    digest = await stock_radar_digest(db, {**payload, "record_preview": False})
    channels = payload.get("channels") or digest.get("channels") or ["wecom", "telegram"]
    if isinstance(channels, str):
        channels = [item.strip() for item in channels.split(",") if item.strip()]
    run = (await db.summarize_stock_radar(run_id=_clean(payload.get("run_id"), 220) or None, limit=50)).get("latest_run") or {}
    message = _clean(payload.get("message") or digest.get("digest_preview"), 4000)
    dry_run = _as_bool(payload.get("dry_run"), True)
    candidates = list(digest.get("candidates") or [])
    high_confidence_count = sum(1 for candidate in candidates if isinstance(candidate, dict) and _high_confidence_candidate(candidate))
    blocked_reason = "" if dry_run or high_confidence_count > 0 else "high_confidence_candidate_required"
    logs = []
    for channel in list(channels or []):
        logs.append(
            await db.save_stock_radar_push_log(
                {
                    "run_id": run.get("run_id"),
                    "channel": channel,
                    "platform": channel,
                    "target": payload.get("target"),
                    "status": "preview" if dry_run else "blocked" if blocked_reason else "queued",
                    "message_preview": message,
                    "candidate_count": len(candidates),
                    "error": blocked_reason or None,
                    "metadata": {
                        "dry_run": dry_run,
                        "gateway_required": True,
                        "no_trade_instructions": True,
                        "high_confidence_candidate_count": high_confidence_count,
                        "blocked_reason": blocked_reason or None,
                    },
                }
            )
        )
    if blocked_reason:
        return {
            "object": "stock_radar.push_digest",
            "success": False,
            "data": {
                "dry_run": dry_run,
                "channels": list(channels or []),
                "message_preview": message,
                "push_logs": logs,
                "gateway_status": "blocked_requires_high_confidence_candidate",
                "high_confidence_candidate_count": high_confidence_count,
            },
            "error": "stock radar digest delivery requires high-confidence non-provisional extraction",
            "error_code": "STOCK_RADAR_PUSH_REQUIRES_HIGH_CONFIDENCE",
        }
    return {
        "object": "stock_radar.push_digest",
        "success": True,
        "data": {
            "dry_run": dry_run,
            "channels": list(channels or []),
            "message_preview": message,
            "push_logs": logs,
            "gateway_status": "preview_recorded" if dry_run else "queued_for_gateway_adapter",
            "high_confidence_candidate_count": high_confidence_count,
        },
        "error": None,
    }


async def schedule_stock_radar_update(_: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(params or {})
    return {
        "object": "stock_radar.schedule_update",
        "success": True,
        "data": {
            "status": "preview",
            "enabled": bool(payload.get("enabled", False)),
            "schedule": payload.get("schedule") or "manual",
            "jobs": [
                "daily_after_close_announcements",
                "intraday_news_fund_radar",
                "late_session_after_1430",
            ],
            "auto_push": False,
            "detail": "Schedule intent recorded as preview; external automation remains opt-in.",
        },
        "error": None,
    }


def run_stock_radar_sync(db, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_stock_radar(db, **kwargs))


__all__ = [
    "RADAR_EVENT_TYPES",
    "extract_radar_event",
    "fetch_rss_feed_documents",
    "push_stock_radar_digest",
    "run_stock_radar",
    "run_stock_radar_sync",
    "schedule_stock_radar_update",
    "score_radar_candidate",
    "stock_radar_candidates",
    "stock_radar_digest",
    "stock_radar_status",
]
