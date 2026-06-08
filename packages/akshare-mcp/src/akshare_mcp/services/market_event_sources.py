"""Market event source normalization and Strategy Factory bridge.

This module turns public/paid market text metadata into auditable normalized
events. It deliberately separates source reliability from strategy generation:
Tier C media/news can support diagnostics, but only Tier A/B anchored events are
bridged into Strategy Factory event candidates.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import requests


SOURCE_TIER_A = "tier_a"
SOURCE_TIER_B = "tier_b"
SOURCE_TIER_C = "tier_c"
BRIDGE_SOURCE = "market_events_normalized"
CNINFO_ANNOUNCEMENT_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE_URL = "https://static.cninfo.com.cn/"
SSE_ANNOUNCEMENT_QUERY_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
SSE_STATIC_BASE_URL = "https://static.sse.com.cn/"


_TIER_DEFAULT_RELIABILITY = {
    SOURCE_TIER_A: 0.92,
    SOURCE_TIER_B: 0.82,
    SOURCE_TIER_C: 0.45,
}
_SINGLE_ANCHOR_CONFIDENCE_CAP = 0.65
_MULTI_SOURCE_CONFIDENCE_CAP = 0.92
_CONFLICT_CONFIDENCE_CAP = 0.55

_OFFICIAL_PROVIDER_TOKENS = (
    "cninfo",
    "sse",
    "szse",
    "bse",
    "csrc",
    "巨潮",
    "上交所",
    "深交所",
    "北交所",
    "证监会",
)
_PAID_PROVIDER_TOKENS = ("wind", "ifind", "choice", "tushare")


EVENT_TAXONOMY: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("earnings_forecast", ("业绩预告", "预增", "扭亏", "预减", "业绩快报", "年报", "季报", "earnings", "profit forecast"), "earnings", "up"),
    ("order_contract", ("中标", "签约", "订单", "合同", "项目", "order", "contract", "signs", "signed"), "order_contract", "up"),
    ("ma_restructuring", ("重大资产重组", "并购", "收购", "重组", "资产购买", "merger", "acquisition", "restructuring"), "restructuring", "up"),
    ("buyback_holding", ("回购", "增持", "减持", "buyback", "repurchase", "holding increase", "holding reduction"), "capital_action", "neutral"),
    ("refinancing", ("定增", "可转债", "配股", "融资", "refinancing", "private placement", "convertible bond"), "financing", "neutral"),
    ("regulatory_risk", ("立案", "调查", "处罚", "违规", "诉讼", "监管函", "警示函", "investigation", "penalty", "lawsuit", "regulatory"), "regulatory_risk", "down"),
    ("st_delist_suspend", ("ST", "*ST", "退市", "停牌", "复牌", "终止上市", "delisting", "suspension"), "listing_risk", "down"),
    ("product_approval", ("获批", "批准", "注册证", "临床", "产品发布", "技术突破", "approval", "approved", "clinical", "launch"), "product_approval", "up"),
    ("policy_industry", ("政策", "规划", "通知", "方案", "意见", "行业", "policy", "guideline", "industry"), "policy", "neutral"),
)


@dataclass(frozen=True)
class MarketEventSourceAdapter:
    name: str
    tier: str
    enabled: bool
    configured: bool
    reason: str = ""
    implemented: bool = True

    def status(self) -> dict[str, Any]:
        degraded = bool(self.enabled and (not self.configured or not self.implemented))
        return {
            "name": self.name,
            "tier": self.tier,
            "enabled": self.enabled,
            "configured": self.configured,
            "implemented": self.implemented,
            "degraded": degraded,
            "reason": self.reason,
        }


def build_market_event_source_adapters() -> list[MarketEventSourceAdapter]:
    """Return configured source adapters without making network calls."""

    def _cred(*names: str) -> bool:
        return any(str(os.getenv(name) or "").strip() for name in names)

    return [
        MarketEventSourceAdapter("cninfo", SOURCE_TIER_A, True, True),
        MarketEventSourceAdapter("sse", SOURCE_TIER_A, True, True),
        MarketEventSourceAdapter(
            "szse",
            SOURCE_TIER_A,
            True,
            False,
            "official source adapter pending; cninfo/sse are the active tier_a ingest paths",
            False,
        ),
        MarketEventSourceAdapter(
            "bse",
            SOURCE_TIER_A,
            True,
            False,
            "official source adapter pending; cninfo/sse are the active tier_a ingest paths",
            False,
        ),
        MarketEventSourceAdapter(
            "csrc",
            SOURCE_TIER_A,
            True,
            False,
            "official source adapter pending; cninfo is the active tier_a ingest path",
            False,
        ),
        MarketEventSourceAdapter(
            "wind",
            SOURCE_TIER_B,
            True,
            _cred("WIND_TOKEN", "WIND_ACCOUNT", "WIND_API_KEY"),
            "missing WIND_* credentials" if not _cred("WIND_TOKEN", "WIND_ACCOUNT", "WIND_API_KEY") else "paid source ingest adapter pending",
            False,
        ),
        MarketEventSourceAdapter(
            "ifind",
            SOURCE_TIER_B,
            True,
            _cred("IFIND_TOKEN", "IFIND_ACCOUNT", "IFIND_API_KEY"),
            "missing IFIND_* credentials" if not _cred("IFIND_TOKEN", "IFIND_ACCOUNT", "IFIND_API_KEY") else "paid source ingest adapter pending",
            False,
        ),
        MarketEventSourceAdapter(
            "choice",
            SOURCE_TIER_B,
            True,
            _cred("CHOICE_TOKEN", "CHOICE_ACCOUNT", "CHOICE_API_KEY"),
            "missing CHOICE_* credentials" if not _cred("CHOICE_TOKEN", "CHOICE_ACCOUNT", "CHOICE_API_KEY") else "paid source ingest adapter pending",
            False,
        ),
        MarketEventSourceAdapter(
            "tushare_pro",
            SOURCE_TIER_B,
            True,
            _cred("TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN"),
            "missing TUSHARE token" if not _cred("TUSHARE_TOKEN", "TUSHARE_PRO_TOKEN") else "paid source ingest adapter pending",
            False,
        ),
        MarketEventSourceAdapter("eastmoney", SOURCE_TIER_C, True, True),
        MarketEventSourceAdapter("akshare", SOURCE_TIER_C, True, True),
        MarketEventSourceAdapter("media_news", SOURCE_TIER_C, True, True),
    ]


def event_source_status() -> dict[str, Any]:
    adapters = [adapter.status() for adapter in build_market_event_source_adapters()]
    return {
        "adapters": adapters,
        "tier_counts": _count_by(adapters, "tier"),
        "degraded_count": sum(1 for item in adapters if item.get("degraded")),
    }


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        out[value] = int(out.get(value) or 0) + 1
    return out


def _clean(value: Any, limit: int = 1000) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())[:limit] if text else ""


def _clean_html(value: Any, limit: int = 1000) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return _clean(text, limit)


def _digits_code(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:6] if len(digits) >= 6 else ""


def _normalize_source_tier(value: Any, *, provider: Any = None, source: Any = None) -> str:
    token = str(value or "").strip().lower()
    if token in {"a", "official", "official_disclosure", SOURCE_TIER_A}:
        return SOURCE_TIER_A
    if token in {"b", "institutional", "paid", SOURCE_TIER_B}:
        return SOURCE_TIER_B
    if token in {"c", "media", "open_media", SOURCE_TIER_C}:
        return SOURCE_TIER_C
    provider_text = str(provider or source or "").strip().lower()
    if any(item in provider_text for item in _OFFICIAL_PROVIDER_TOKENS):
        return SOURCE_TIER_A
    if any(item in provider_text for item in _PAID_PROVIDER_TOKENS):
        return SOURCE_TIER_B
    return SOURCE_TIER_C


def _coerce_date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except Exception:
        pass
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text[:40]


def _millis_to_date_text(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return _coerce_date_text(value)
    if number <= 0:
        return ""
    try:
        return datetime.fromtimestamp(number / 1000, timezone.utc).date().isoformat()
    except Exception:
        return ""


def _cninfo_pdf_url(value: Any) -> str:
    path = _clean(value, 1000)
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return f"{CNINFO_STATIC_BASE_URL}{path.lstrip('/')}"


def _map_cninfo_announcement(row: dict[str, Any]) -> dict[str, Any] | None:
    code = _digits_code(row.get("secCode"))
    announcement_id = _clean(row.get("announcementId") or row.get("id"), 200)
    title = _clean_html(row.get("announcementTitle") or row.get("shortTitle"), 500)
    if not code or not title:
        return None
    published_at = _millis_to_date_text(row.get("announcementTime") or row.get("storageTime"))
    sec_name = _clean_html(row.get("secName") or row.get("tileSecName"), 120)
    notice_type = _clean_html(row.get("announcementTypeName") or row.get("announcementType"), 200)
    url = _cninfo_pdf_url(row.get("adjunctUrl"))
    original_id = announcement_id or _clean(url or f"{code}:{published_at}:{title}", 240)
    body = " ".join(part for part in (title, sec_name, notice_type) if part)
    return {
        "doc_uid": f"cninfo:{original_id}",
        "title": title,
        "summary": body,
        "content": body,
        "date": published_at,
        "published_at": published_at,
        "evidence_time": published_at,
        "source": "cninfo",
        "source_tier": SOURCE_TIER_A,
        "provider": "cninfo",
        "original_id": original_id,
        "reliability_score": _TIER_DEFAULT_RELIABILITY[SOURCE_TIER_A],
        "crawl_status": "ok",
        "url": url,
        "notice_type": notice_type,
        "code": code,
        "stock_code": code,
        "stock_name": sec_name,
        "cross_source_count": 1,
    }


def _sse_pdf_url(value: Any) -> str:
    path = _clean(value, 1000)
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return f"{SSE_STATIC_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _map_sse_announcement(row: dict[str, Any]) -> dict[str, Any] | None:
    code = _digits_code(row.get("SECURITY_CODE") or row.get("securityCode"))
    title = _clean_html(row.get("TITLE") or row.get("title"), 500)
    if not code or not title:
        return None
    published_at = _coerce_date_text(row.get("SSEDATE") or row.get("SSEDate") or row.get("ADDDATE"))
    sec_name = _clean_html(row.get("SECURITY_NAME") or row.get("securityName"), 120)
    notice_type = _clean_html(row.get("BULLETIN_TYPE") or row.get("BULLETIN_HEADING") or row.get("bulletinType"), 200)
    url = _sse_pdf_url(row.get("URL") or row.get("url"))
    original_id = _clean(row.get("BULLETIN_ID") or row.get("file_Serial") or url or f"{code}:{published_at}:{title}", 240)
    body = " ".join(part for part in (title, sec_name, notice_type) if part)
    return {
        "doc_uid": f"sse:{hashlib.sha1(original_id.encode('utf-8')).hexdigest()[:24]}",
        "title": title,
        "summary": body,
        "content": body,
        "date": published_at,
        "published_at": published_at,
        "evidence_time": published_at,
        "source": "sse",
        "source_tier": SOURCE_TIER_A,
        "provider": "sse",
        "original_id": original_id,
        "reliability_score": _TIER_DEFAULT_RELIABILITY[SOURCE_TIER_A],
        "crawl_status": "ok",
        "url": url,
        "notice_type": notice_type,
        "code": code,
        "stock_code": code,
        "stock_name": sec_name,
        "cross_source_count": 1,
    }


def fetch_cninfo_official_announcements(
    start_iso: str,
    end_iso: str,
    *,
    limit: int = 50,
    stock_codes: list[str] | None = None,
    timeout: float = 12.0,
) -> list[dict[str, Any]]:
    """Fetch official CNINFO disclosure metadata and map it into market docs."""

    resolved_limit = max(0, min(int(limit or 0), 500))
    if resolved_limit <= 0:
        return []
    codes = [_digits_code(code) for code in list(stock_codes or [])]
    codes = [code for code in dict.fromkeys(codes) if code]
    search_keys = codes or [""]
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        "Origin": "https://www.cninfo.com.cn",
    }
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for search_key in search_keys:
        page = 1
        while len(results) < resolved_limit and page <= 10:
            page_size = min(30, max(1, resolved_limit - len(results)))
            payload = {
                "pageNum": str(page),
                "pageSize": str(page_size),
                "column": "szse",
                "tabName": "fulltext",
                "plate": "",
                "stock": "",
                "searchkey": search_key,
                "secid": "",
                "category": "",
                "trade": "",
                "seDate": f"{start_iso}~{end_iso}",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }
            response = requests.post(CNINFO_ANNOUNCEMENT_QUERY_URL, data=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json() if response.text else {}
            announcements = list((data or {}).get("announcements") or [])
            if not announcements:
                break
            for row in announcements:
                if not isinstance(row, dict):
                    continue
                mapped = _map_cninfo_announcement(row)
                if not mapped:
                    continue
                if search_key and mapped.get("code") != search_key:
                    continue
                key = str(mapped.get("doc_uid") or mapped.get("url") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                results.append(mapped)
                if len(results) >= resolved_limit:
                    break
            total = int((data or {}).get("totalAnnouncement") or (data or {}).get("totalRecordNum") or 0)
            if len(announcements) < page_size or (total and page * page_size >= total):
                break
            page += 1
    return results


def fetch_sse_official_announcements(
    start_iso: str,
    end_iso: str,
    *,
    limit: int = 50,
    stock_codes: list[str] | None = None,
    timeout: float = 12.0,
) -> list[dict[str, Any]]:
    """Fetch official SSE disclosure metadata and map it into market docs."""

    resolved_limit = max(0, min(int(limit or 0), 500))
    if resolved_limit <= 0:
        return []
    codes = [_digits_code(code) for code in list(stock_codes or [])]
    codes = [code for code in dict.fromkeys(codes) if code]
    search_keys = codes or [""]
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
    }
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for product_id in search_keys:
        page = 1
        while len(results) < resolved_limit and page <= 10:
            page_size = min(30, max(1, resolved_limit - len(results)))
            params = {
                "isPagination": "true",
                "productId": product_id,
                "keyWord": "",
                "securityType": "0101,120100,020100,020200,120200",
                "reportType2": "",
                "reportType": "ALL",
                "beginDate": start_iso,
                "endDate": end_iso,
                "pageHelp.pageSize": str(page_size),
                "pageHelp.pageNo": str(page),
                "pageHelp.beginPage": str(page),
                "pageHelp.endPage": str(page),
                "_": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
            }
            response = requests.get(SSE_ANNOUNCEMENT_QUERY_URL, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            data = response.json() if response.text else {}
            page_help = data.get("pageHelp") if isinstance(data, dict) else {}
            rows = list((page_help or {}).get("data") or [])
            if not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                mapped = _map_sse_announcement(row)
                if not mapped:
                    continue
                if product_id and mapped.get("code") != product_id:
                    continue
                key = str(mapped.get("doc_uid") or mapped.get("url") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                results.append(mapped)
                if len(results) >= resolved_limit:
                    break
            total = int((page_help or {}).get("total") or (page_help or {}).get("totalCount") or 0)
            if len(rows) < page_size or (total and page * page_size >= total):
                break
            page += 1
    return results


def fetch_official_market_event_documents(
    start_iso: str,
    end_iso: str,
    *,
    limit: int = 50,
    stock_codes: list[str] | None = None,
    providers: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch official/open disclosure metadata with structured degradation."""

    requested = [str(item or "").strip().lower() for item in list(providers or ["cninfo", "sse", "szse", "bse", "csrc"])]
    requested = [item for item in dict.fromkeys(requested) if item]
    items: list[dict[str, Any]] = []
    sources: dict[str, dict[str, Any]] = {}
    for provider in requested:
        if provider == "cninfo":
            try:
                rows = fetch_cninfo_official_announcements(
                    start_iso,
                    end_iso,
                    limit=max(0, int(limit or 0)) - len(items),
                    stock_codes=stock_codes,
                )
                items.extend(rows)
                sources[provider] = {
                    "tier": SOURCE_TIER_A,
                    "status": "ok",
                    "fetched": len(rows),
                    "degraded": False,
                }
            except Exception as exc:
                sources[provider] = {
                    "tier": SOURCE_TIER_A,
                    "status": "degraded",
                    "fetched": 0,
                    "degraded": True,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            continue
        if provider == "sse":
            try:
                rows = fetch_sse_official_announcements(
                    start_iso,
                    end_iso,
                    limit=max(0, int(limit or 0)) - len(items),
                    stock_codes=stock_codes,
                )
                items.extend(rows)
                sources[provider] = {
                    "tier": SOURCE_TIER_A,
                    "status": "ok",
                    "fetched": len(rows),
                    "degraded": False,
                }
            except Exception as exc:
                sources[provider] = {
                    "tier": SOURCE_TIER_A,
                    "status": "degraded",
                    "fetched": 0,
                    "degraded": True,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            continue
        sources[provider] = {
            "tier": SOURCE_TIER_A,
            "status": "degraded",
            "fetched": 0,
            "degraded": True,
            "reason": "official_source_adapter_pending",
        }
    return {
        "items": items[: max(0, int(limit or 0))],
        "sources": sources,
        "degraded_count": sum(1 for item in sources.values() if item.get("degraded")),
    }


def _doc_uid(db: Any, stock_code: str, doc_type: str, item: dict[str, Any]) -> str:
    builder = getattr(db, "_build_market_doc_uid", None)
    if callable(builder):
        return str(builder(stock_code, doc_type, item))
    explicit = _clean(item.get("doc_uid") or item.get("url") or item.get("id"), 240)
    if explicit:
        return explicit
    basis = "|".join([stock_code, doc_type, _clean(item.get("title")), _clean(item.get("date"))])
    return f"mdoc_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:24]}"


def _extract_codes(stock_code: str, text: str, item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for raw in [stock_code, item.get("code"), item.get("stock_code"), item.get("symbol")]:
        token = "".join(ch for ch in str(raw or "") if ch.isdigit())
        if len(token) == 6:
            values.append(token)
    values.extend(re.findall(r"\b\d{6}\b", text))
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out[:20]


def _classify_event(title: str, text: str, doc_type: str, item: dict[str, Any]) -> tuple[str, str, str]:
    source_text = " ".join([title, text, _clean(item.get("notice_type") or item.get("type"), 120)])
    for event_type, keywords, theme_code, default_direction in EVENT_TAXONOMY:
        if any(keyword in source_text for keyword in keywords):
            direction = str(item.get("direction") or default_direction).strip().lower() or default_direction
            return event_type, theme_code, direction
    if str(doc_type or "").lower() in {"notice", "announcement"}:
        return "announcement", "announcement", str(item.get("direction") or "neutral").strip().lower() or "neutral"
    if str(doc_type or "").lower() == "research":
        return "research_rating", "research", _research_direction(item)
    return "market_news", "market_news", str(item.get("direction") or "neutral").strip().lower() or "neutral"


def _research_direction(item: dict[str, Any]) -> str:
    rating = str(item.get("rating") or "").strip()
    if any(token in rating for token in ("买入", "增持", "推荐", "强烈推荐")):
        return "up"
    if any(token in rating for token in ("卖出", "减持", "回避")):
        return "down"
    return "neutral"


def _reliability_score(source_tier: str, *, cross_source_count: int = 1, has_publish_time: bool = True) -> float:
    base = _TIER_DEFAULT_RELIABILITY.get(source_tier, 0.35)
    if cross_source_count > 1:
        base += min(0.08, 0.03 * (cross_source_count - 1))
    if not has_publish_time:
        base -= 0.2
    return round(max(0.0, min(base, 0.98)), 4)


def _event_status(source_tier: str, entity_codes: list[str], publish_time: str, reliability_score: float) -> tuple[str, str | None]:
    if not entity_codes:
        return "rejected", "missing_entity_codes"
    if not publish_time:
        return "degraded", "missing_publish_time"
    if source_tier in {SOURCE_TIER_A, SOURCE_TIER_B} and reliability_score >= 0.75:
        return "verified", None
    return "provisional", "news_only_or_low_tier_source"


def _unique_list(values: Any, *, limit: int = 50) -> list[str]:
    out: list[str] = []
    queue = list(values or []) if isinstance(values, (list, tuple, set)) else [values]
    while queue:
        value = queue.pop(0)
        if isinstance(value, (list, tuple, set)):
            queue[:0] = list(value)
            continue
        token = str(value or "").strip()
        if token and token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out


def _event_date_key(event: dict[str, Any]) -> str:
    for key in ("event_time", "publish_time", "evidence_time"):
        text = _coerce_date_text(event.get(key))
        if text:
            return text[:10]
    return "unknown_date"


_SIGNATURE_STOPWORDS = {
    "000001",
    "announcement",
    "announces",
    "company",
    "disclosure",
    "official",
    "says",
    "may",
    "from",
    "with",
    "about",
    "this",
    "that",
    "major",
}


def _title_keyword_signature(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "").strip().lower()
    theme_codes = _unique_list(event.get("theme_codes"), limit=3)
    if event_type and event_type not in {"announcement", "market_news"}:
        return "-".join([event_type, *theme_codes]) if theme_codes else event_type

    text = " ".join(
        [
            str(event.get("event_name") or ""),
            str(event.get("summary") or ""),
            " ".join(str(item or "") for item in list(event.get("theme_codes") or [])),
        ]
    ).lower()
    text = re.sub(r"\b\d{6}\b", " ", text)
    tokens = [
        token
        for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text)
        if len(token) >= 2 and token not in _SIGNATURE_STOPWORDS
    ]
    if not tokens:
        return str(event.get("event_type") or "event")
    return "-".join(sorted(dict.fromkeys(tokens))[:8])


def _event_signature(event: dict[str, Any]) -> str:
    entity_codes = ",".join(sorted(_unique_list(event.get("entity_codes"), limit=20))) or "unknown_entity"
    basis = "|".join(
        [
            entity_codes,
            str(event.get("event_type") or "event").strip().lower() or "event",
            _event_date_key(event),
            _title_keyword_signature(event),
        ]
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:24]


def _event_signature_value(event: dict[str, Any]) -> str:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    summary = metadata.get("validation_summary") if isinstance(metadata.get("validation_summary"), dict) else {}
    signature = str(metadata.get("event_signature") or summary.get("event_signature") or "").strip()
    return signature or _event_signature(event)


def _validation_summary_value(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    summary = metadata.get("validation_summary") if isinstance(metadata.get("validation_summary"), dict) else {}
    return dict(summary or {})


def _direction_bucket(value: Any) -> str:
    token = str(value or "neutral").strip().lower()
    if token in {"up", "positive", "bullish", "long"}:
        return "up"
    if token in {"down", "negative", "bearish", "short"}:
        return "down"
    return "neutral"


class MultiSourceEventValidator:
    """Validate occurrence and alpha confirmation without requiring new tables."""

    def validate(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for raw in [dict(item or {}) for item in list(events or []) if isinstance(item, dict)]:
            signature = _event_signature_value(raw)
            raw.setdefault("metadata", {})
            if isinstance(raw["metadata"], dict):
                raw["metadata"]["event_signature"] = signature
            grouped.setdefault(signature, []).append(raw)
        return [self._merge(signature, rows) for signature, rows in grouped.items()]

    def _merge(self, signature: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        primary = self._select_primary(rows)
        source_doc_uids = _unique_list([item.get("source_doc_uids") for item in rows], limit=100)
        provider_chain = _unique_list([item.get("provider_chain") for item in rows], limit=30)
        source_types = _unique_list([item.get("source_types") for item in rows], limit=30)
        entity_codes = _unique_list([item.get("entity_codes") for item in rows], limit=30)
        theme_codes = _unique_list([item.get("theme_codes") for item in rows], limit=20)
        official_anchor_count = max(
            self._summary_count(rows, "official_anchor_count"),
            self._summary_count(rows, "official_anchor_count") + self._new_raw_source_count(rows, SOURCE_TIER_A),
        )
        institutional_anchor_count = max(
            self._summary_count(rows, "institutional_anchor_count"),
            self._summary_count(rows, "institutional_anchor_count") + self._new_raw_source_count(rows, SOURCE_TIER_B),
        )
        media_confirm_count = max(
            self._summary_count(rows, "media_confirm_count"),
            self._summary_count(rows, "media_confirm_count") + self._new_raw_source_count(rows, SOURCE_TIER_C),
        )
        cross_source_count = max(
            len(provider_chain),
            len(source_doc_uids),
            *(max(1, int(item.get("cross_source_count") or _validation_summary_value(item).get("cross_source_count") or 1)) for item in rows),
            1,
        )
        directions = {_direction_bucket(item.get("direction")) for item in rows}
        conflict_count = max(
            1 if {"up", "down"}.issubset(directions) else 0,
            *(int(_validation_summary_value(item).get("conflict_count") or 0) for item in rows),
        )
        has_verified_anchor = official_anchor_count + institutional_anchor_count > 0
        has_invalid_core = any(str(item.get("status") or "").strip().lower() in {"rejected", "degraded"} for item in rows)

        if not entity_codes:
            occurrence_status = "rejected"
            alpha_status = "missing_entity_codes"
            status = "rejected"
            reject_reason = "missing_entity_codes"
            confidence_cap_reason = "missing_entity_codes"
        elif has_invalid_core and not has_verified_anchor:
            occurrence_status = str(primary.get("status") or "degraded")
            alpha_status = "source_degraded"
            status = str(primary.get("status") or "degraded")
            reject_reason = str(primary.get("reject_reason") or "source_degraded")
            confidence_cap_reason = reject_reason
        elif not has_verified_anchor:
            occurrence_status = "provisional"
            alpha_status = "news_only_rejected"
            status = "provisional"
            reject_reason = "news_only_or_low_tier_source"
            confidence_cap_reason = "news_only_requires_official_or_institutional_anchor"
        elif conflict_count:
            occurrence_status = "verified_conflicted"
            alpha_status = "conflicted"
            status = "verified"
            reject_reason = "direction_conflict"
            confidence_cap_reason = "direction_conflict"
        elif cross_source_count <= 1 and official_anchor_count + institutional_anchor_count == 1:
            occurrence_status = "verified_single_anchor"
            alpha_status = "single_anchor_unconfirmed"
            status = "verified"
            reject_reason = None
            confidence_cap_reason = "single_official_or_institutional_anchor"
        else:
            occurrence_status = "verified_multi_source"
            alpha_status = "confirmed"
            status = "verified"
            reject_reason = None
            confidence_cap_reason = None

        if conflict_count:
            direction = "neutral"
        else:
            direction = _direction_bucket(primary.get("direction"))

        if official_anchor_count:
            source_tier = SOURCE_TIER_A
        elif institutional_anchor_count:
            source_tier = SOURCE_TIER_B
        else:
            source_tier = SOURCE_TIER_C

        reliability = self._validated_reliability(
            rows,
            alpha_status=alpha_status,
            cross_source_count=cross_source_count,
        )
        event_id = f"mevt_{hashlib.sha1(signature.encode('utf-8')).hexdigest()[:24]}"
        checksum_basis = "|".join([signature, ",".join(source_doc_uids), ",".join(provider_chain)])
        validation_summary = {
            "event_signature": signature,
            "official_anchor_count": official_anchor_count,
            "institutional_anchor_count": institutional_anchor_count,
            "media_confirm_count": media_confirm_count,
            "cross_source_count": cross_source_count,
            "conflict_count": conflict_count,
            "provider_chain": list(provider_chain),
            "source_doc_uids": list(source_doc_uids),
            "occurrence_status": occurrence_status,
            "alpha_confirmation_status": alpha_status,
            "confidence_cap_reason": confidence_cap_reason,
        }
        metadata = dict(primary.get("metadata") or {})
        metadata.update(
            {
                "validation_summary": validation_summary,
                "event_signature": signature,
                "occurrence_status": occurrence_status,
                "alpha_confirmation_status": alpha_status,
                "confidence_cap_reason": confidence_cap_reason,
                "diagnostic_only": status != "verified" or alpha_status in {"news_only_rejected", "conflicted"},
            }
        )
        merged = dict(primary)
        merged.update(
            {
                "event_id": event_id,
                "event_anchor_id": event_id,
                "entity_codes": entity_codes,
                "theme_codes": theme_codes or list(primary.get("theme_codes") or []),
                "direction": direction,
                "source_doc_uids": source_doc_uids,
                "source_tier": source_tier,
                "source_types": source_types,
                "provider_chain": provider_chain,
                "reliability_score": reliability,
                "cross_source_count": cross_source_count,
                "status": status,
                "reject_reason": reject_reason,
                "checksum": hashlib.sha1(checksum_basis.encode("utf-8")).hexdigest(),
                "metadata": metadata,
            }
        )
        return merged

    @staticmethod
    def _summary_count(rows: list[dict[str, Any]], key: str) -> int:
        count = 0
        for item in rows:
            try:
                count = max(count, int(_validation_summary_value(item).get(key) or 0))
            except (TypeError, ValueError):
                continue
        return count

    @staticmethod
    def _new_raw_source_count(rows: list[dict[str, Any]], source_tier: str) -> int:
        existing_doc_uids = set(
            _unique_list(
                [
                    item.get("source_doc_uids")
                    for item in rows
                    if _validation_summary_value(item)
                ],
                limit=500,
            )
        )
        seen: set[str] = set()
        for item in rows:
            if _validation_summary_value(item):
                continue
            if str(item.get("source_tier") or "").lower() != source_tier:
                continue
            doc_uids = _unique_list(item.get("source_doc_uids"), limit=100)
            providers = _unique_list(item.get("provider_chain"), limit=30)
            for token in doc_uids or providers or [str(item.get("checksum") or item.get("event_id") or "")]:
                if token and token not in existing_doc_uids:
                    seen.add(token)
        return len(seen)

    @staticmethod
    def _select_primary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        tier_rank = {SOURCE_TIER_A: 3, SOURCE_TIER_B: 2, SOURCE_TIER_C: 1}
        return max(
            rows,
            key=lambda item: (
                tier_rank.get(str(item.get("source_tier") or "").lower(), 0),
                float(item.get("reliability_score") or 0.0),
                len(list(item.get("source_doc_uids") or [])),
            ),
        )

    @staticmethod
    def _validated_reliability(
        rows: list[dict[str, Any]],
        *,
        alpha_status: str,
        cross_source_count: int,
    ) -> float:
        max_score = max(float(item.get("reliability_score") or 0.0) for item in rows) if rows else 0.0
        if alpha_status == "single_anchor_unconfirmed":
            return round(min(max_score, _SINGLE_ANCHOR_CONFIDENCE_CAP), 4)
        if alpha_status == "confirmed":
            if any(str(item.get("source_tier") or "").lower() == SOURCE_TIER_A for item in rows):
                max_score = max(max_score, _TIER_DEFAULT_RELIABILITY[SOURCE_TIER_A])
            elif any(str(item.get("source_tier") or "").lower() == SOURCE_TIER_B for item in rows):
                max_score = max(max_score, _TIER_DEFAULT_RELIABILITY[SOURCE_TIER_B])
            uplifted = max_score + min(0.06, 0.025 * max(0, int(cross_source_count or 1) - 1))
            return round(min(uplifted, _MULTI_SOURCE_CONFIDENCE_CAP), 4)
        if alpha_status == "conflicted":
            return round(min(max_score, _CONFLICT_CONFIDENCE_CAP), 4)
        return round(min(max_score, 0.49), 4)


def normalize_market_text_events(
    db: Any,
    stock_code: str,
    doc_type: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in [dict(row or {}) for row in list(items or []) if isinstance(row, dict)]:
        title = _clean(item.get("title") or item.get("headline") or item.get("name"), 300)
        body = _clean(item.get("content") or item.get("text") or item.get("summary") or title, 4000)
        if not title and not body:
            continue
        source = _clean(item.get("source") or item.get("provider") or item.get("origin"), 160)
        provider = _clean(item.get("provider") or source or doc_type, 160)
        source_tier = _normalize_source_tier(item.get("source_tier"), provider=provider, source=source)
        publish_time = _coerce_date_text(item.get("published_at") or item.get("date") or item.get("time"))
        evidence_time = _coerce_date_text(item.get("evidence_time") or publish_time)
        doc_uid = _doc_uid(db, stock_code, doc_type, item)
        entity_codes = _extract_codes(stock_code, f"{title} {body}", item)
        event_type, theme_code, direction = _classify_event(title, body, doc_type, item)
        cross_source_count = int(item.get("cross_source_count") or 1)
        reliability = item.get("reliability_score")
        try:
            reliability = float(reliability)
        except (TypeError, ValueError):
            reliability = _reliability_score(
                source_tier,
                cross_source_count=cross_source_count,
                has_publish_time=bool(publish_time),
            )
        status, reject_reason = _event_status(source_tier, entity_codes, publish_time, float(reliability))
        if item.get("status"):
            status = str(item.get("status") or status).strip()
            reject_reason = item.get("reject_reason") or reject_reason
        checksum_basis = "|".join([event_type, title, publish_time, ",".join(entity_codes), doc_uid])
        checksum = str(item.get("checksum") or hashlib.sha1(checksum_basis.encode("utf-8")).hexdigest())
        event_id = str(item.get("event_id") or f"mevt_{hashlib.sha1(checksum.encode('utf-8')).hexdigest()[:24]}")
        summary = _clean(item.get("summary") or body or title, 600)
        events.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "event_name": title or event_type,
                "summary": summary,
                "entity_codes": entity_codes,
                "theme_codes": [theme_code],
                "direction": direction,
                "event_time": _coerce_date_text(item.get("event_time") or publish_time),
                "publish_time": publish_time,
                "evidence_time": evidence_time,
                "source_doc_uids": [doc_uid],
                "source_tier": source_tier,
                "source_types": [source or provider or doc_type],
                "provider_chain": [provider or source or doc_type],
                "reliability_score": float(reliability),
                "cross_source_count": cross_source_count,
                "status": status,
                "reject_reason": reject_reason,
                "freshness_status": "ok" if publish_time else "unknown",
                "event_anchor_id": event_id,
                "checksum": checksum,
                "metadata": {
                    "doc_type": doc_type,
                    "source": source,
                    "provider": provider,
                    "source_tier": source_tier,
                    "url": item.get("url"),
                    "diagnostic_only": status != "verified",
                },
            }
        )
    return events


async def persist_normalized_events(
    db: Any,
    stock_code: str,
    doc_type: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    validator = MultiSourceEventValidator()
    normalized_events = normalize_market_text_events(db, stock_code, doc_type, items)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in normalized_events:
        grouped.setdefault(_event_signature_value(event), []).append(event)

    events: list[dict[str, Any]] = []
    for signature, rows in grouped.items():
        existing = await _existing_normalized_events_for_signature(db, signature)
        events.extend(validator.validate([*existing, *rows]))

    counts = {"total": 0, "verified": 0, "provisional": 0, "degraded": 0, "rejected": 0}
    latest: list[dict[str, Any]] = []
    for event in events:
        if not hasattr(db, "upsert_market_event_normalized"):
            continue
        saved = await db.upsert_market_event_normalized(event)
        status = str(saved.get("status") or "unknown")
        counts["total"] += 1
        if status in counts:
            counts[status] += 1
        latest.append(
            {
                "event_id": saved.get("event_id"),
                "event_type": saved.get("event_type"),
                "status": status,
                "source_tier": saved.get("source_tier"),
                "entity_codes": list(saved.get("entity_codes") or []),
                "cross_source_count": int(saved.get("cross_source_count") or 0),
                "validation_summary": dict((saved.get("metadata") or {}).get("validation_summary") or {}),
            }
        )
    return {**counts, "latest": latest[:10]}


async def _existing_normalized_events_for_signature(db: Any, signature: str) -> list[dict[str, Any]]:
    list_events = getattr(db, "list_market_events_normalized", None)
    if not callable(list_events) or not signature:
        return []
    try:
        result = list_events(event_signature=signature, limit=50)
    except TypeError:
        try:
            result = list_events(limit=200)
        except TypeError:
            return []
    if hasattr(result, "__await__"):
        result = await result
    rows = [dict(item or {}) for item in list(result or []) if isinstance(item, dict)]
    return [row for row in rows if _event_signature_value(row) == signature]


def _bridge_direction(value: Any) -> str:
    token = str(value or "neutral").strip().lower()
    if token in {"up", "positive", "bullish"}:
        return "positive"
    if token in {"down", "negative", "bearish"}:
        return "negative"
    return "neutral"


def _validation_from_event(event: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(event.get("metadata") or {}) if isinstance(event.get("metadata"), dict) else {}
    summary = dict(metadata.get("validation_summary") or {})
    cross_source_count = int(event.get("cross_source_count") or summary.get("cross_source_count") or 1)
    alpha_status = str(
        metadata.get("alpha_confirmation_status")
        or summary.get("alpha_confirmation_status")
        or ""
    ).strip()
    occurrence_status = str(
        metadata.get("occurrence_status")
        or summary.get("occurrence_status")
        or ""
    ).strip()
    if not alpha_status:
        alpha_status = "single_anchor_unconfirmed" if cross_source_count <= 1 else "confirmed"
    if not occurrence_status:
        occurrence_status = "verified_single_anchor" if cross_source_count <= 1 else "verified_multi_source"
    conflict_count = int(summary.get("conflict_count") or 0)
    confidence_cap_reason = str(
        metadata.get("confidence_cap_reason")
        or summary.get("confidence_cap_reason")
        or ("single_official_or_institutional_anchor" if alpha_status == "single_anchor_unconfirmed" else "")
    ).strip() or None
    validation_summary = {
        **summary,
        "event_signature": metadata.get("event_signature") or summary.get("event_signature"),
        "occurrence_status": occurrence_status,
        "alpha_confirmation_status": alpha_status,
        "confidence_cap_reason": confidence_cap_reason,
        "cross_source_count": cross_source_count,
        "conflict_count": conflict_count,
    }
    return {
        "metadata": metadata,
        "validation_summary": validation_summary,
        "occurrence_status": occurrence_status,
        "alpha_confirmation_status": alpha_status,
        "confidence_cap_reason": confidence_cap_reason,
        "needs_alpha_confirmation": alpha_status == "single_anchor_unconfirmed",
        "conflict_count": conflict_count,
        "cross_source_count": cross_source_count,
    }


def _cap_bridge_reliability(reliability: float, alpha_status: str) -> float:
    if alpha_status == "single_anchor_unconfirmed":
        return round(min(float(reliability or 0.0), _SINGLE_ANCHOR_CONFIDENCE_CAP), 4)
    if alpha_status == "confirmed":
        return round(min(float(reliability or 0.0), _MULTI_SOURCE_CONFIDENCE_CAP), 4)
    if alpha_status == "conflicted":
        return round(min(float(reliability or 0.0), _CONFLICT_CONFIDENCE_CAP), 4)
    return round(min(float(reliability or 0.0), 0.49), 4)


async def bridge_normalized_events_to_strategy_factory(
    db: Any,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    if not all(
        hasattr(db, name)
        for name in ("list_market_events_normalized", "save_factory_event_cluster", "save_factory_event_signal")
    ):
        return {"enabled": False, "reason": "db_methods_unavailable", "bridged_events": 0, "signals": 0}

    events = await db.list_market_events_normalized(status="verified", limit=max(1, int(limit or 50)))
    bridged_events = 0
    diagnostic_events = 0
    signals = 0
    skipped = 0
    for event in events:
        source_tier = str(event.get("source_tier") or "")
        entity_codes = [str(code).strip() for code in list(event.get("entity_codes") or []) if str(code).strip()]
        if source_tier not in {SOURCE_TIER_A, SOURCE_TIER_B} or not entity_codes:
            skipped += 1
            continue
        validation = _validation_from_event(event)
        occurrence_status = str(validation.get("occurrence_status") or "").strip()
        alpha_status = str(validation.get("alpha_confirmation_status") or "").strip()
        if not occurrence_status.startswith("verified") or alpha_status in {"news_only_rejected", "source_degraded"}:
            skipped += 1
            continue
        if int(validation.get("conflict_count") or 0) > 0 or alpha_status == "conflicted":
            event_id = str(event.get("event_id") or "").strip()
            event_anchor_id = str(event.get("event_anchor_id") or event_id).strip()
            reliability = _cap_bridge_reliability(float(event.get("reliability_score") or 0.0), "conflicted")
            evidence = {
                "source": BRIDGE_SOURCE,
                "event_anchor_id": event_anchor_id,
                "source_doc_uids": list(event.get("source_doc_uids") or []),
                "source_tier": source_tier,
                "source_types": list(event.get("source_types") or []),
                "provider_chain": list(event.get("provider_chain") or []),
                "reliability_score": reliability,
                "normalized_event_status": event.get("status"),
                "evidence_time": event.get("evidence_time"),
                "verified_event_anchor": True,
                "validation_summary": dict(validation.get("validation_summary") or {}),
                "occurrence_status": occurrence_status,
                "alpha_confirmation_status": "conflicted",
                "confidence_cap_reason": validation.get("confidence_cap_reason") or "direction_conflict",
                "needs_alpha_confirmation": False,
                "conflict_count": int(validation.get("conflict_count") or 1),
                "diagnostic_only": True,
            }
            await db.save_factory_event_cluster(
                {
                    "event_id": event_id,
                    "event_type": event.get("event_type") or "announcement",
                    "event_name": event.get("event_name") or event_id,
                    "event_scope": "company",
                    "summary": event.get("summary") or event.get("event_name"),
                    "direction": "neutral",
                    "intensity": reliability,
                    "horizon": "diagnostic",
                    "confidence": reliability,
                    "source_count": int(validation.get("cross_source_count") or len(event.get("source_doc_uids") or []) or 1),
                    "source_types": [BRIDGE_SOURCE, *list(event.get("source_types") or [])],
                    "entities": entity_codes,
                    "themes": [],
                    "evidence": evidence,
                    "source_tier": source_tier,
                    "source_doc_uids": list(event.get("source_doc_uids") or []),
                    "provider_chain": list(event.get("provider_chain") or []),
                    "event_anchor_id": event_anchor_id,
                    "reliability_score": reliability,
                    "normalized_event_status": event.get("status"),
                    "validation_summary": dict(validation.get("validation_summary") or {}),
                    "occurrence_status": occurrence_status,
                    "alpha_confirmation_status": "conflicted",
                    "confidence_cap_reason": validation.get("confidence_cap_reason") or "direction_conflict",
                    "needs_alpha_confirmation": False,
                    "conflict_count": int(validation.get("conflict_count") or 1),
                    "occurred_at": event.get("event_time") or event.get("publish_time"),
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                    "status": "diagnostic",
                }
            )
            diagnostic_events += 1
            continue
        theme_codes = [str(code).strip() for code in list(event.get("theme_codes") or []) if str(code).strip()] or [
            str(event.get("event_type") or "announcement")
        ]
        event_id = str(event.get("event_id") or "").strip()
        event_anchor_id = str(event.get("event_anchor_id") or event_id).strip()
        direction = _bridge_direction(event.get("direction"))
        reliability = _cap_bridge_reliability(float(event.get("reliability_score") or 0.0), alpha_status)
        evidence = {
            "source": BRIDGE_SOURCE,
            "event_anchor_id": event_anchor_id,
            "source_doc_uids": list(event.get("source_doc_uids") or []),
            "source_tier": source_tier,
            "source_types": list(event.get("source_types") or []),
            "provider_chain": list(event.get("provider_chain") or []),
            "reliability_score": reliability,
            "normalized_event_status": event.get("status"),
            "evidence_time": event.get("evidence_time"),
            "verified_event_anchor": True,
            "validation_summary": dict(validation.get("validation_summary") or {}),
            "occurrence_status": occurrence_status,
            "alpha_confirmation_status": alpha_status,
            "confidence_cap_reason": validation.get("confidence_cap_reason"),
            "needs_alpha_confirmation": bool(validation.get("needs_alpha_confirmation")),
            "conflict_count": int(validation.get("conflict_count") or 0),
        }
        themes = [
            {
                "theme_code": theme_code,
                "theme_name": theme_code,
                "direction": direction,
                "target_symbols": entity_codes,
                "strategy_preferences": ["event_structure_breakout", "sector_rotation"],
                "preferred_strategy_types": ["event_structure_breakout", "sector_rotation"],
                "source_tier": source_tier,
                "event_anchor_id": event_anchor_id,
                "source_doc_uids": list(event.get("source_doc_uids") or []),
                "provider_chain": list(event.get("provider_chain") or []),
                "reliability_score": reliability,
                "evidence_time": event.get("evidence_time"),
                "verified_event_anchor": True,
                "validation_summary": dict(validation.get("validation_summary") or {}),
                "occurrence_status": occurrence_status,
                "alpha_confirmation_status": alpha_status,
                "confidence_cap_reason": validation.get("confidence_cap_reason"),
                "needs_alpha_confirmation": bool(validation.get("needs_alpha_confirmation")),
                "conflict_count": int(validation.get("conflict_count") or 0),
                "score_summary": {
                    "avg_final_score": reliability,
                    "max_final_score": reliability,
                    "top_symbols": entity_codes,
                },
            }
            for theme_code in theme_codes[:3]
        ]
        await db.save_factory_event_cluster(
            {
                "event_id": event_id,
                "event_type": event.get("event_type") or "announcement",
                "event_name": event.get("event_name") or event_id,
                "event_scope": "company",
                "summary": event.get("summary") or event.get("event_name"),
                "direction": direction,
                "intensity": reliability,
                "horizon": "swing_1_5d",
                "confidence": reliability,
                "source_count": int(validation.get("cross_source_count") or len(event.get("source_doc_uids") or []) or 1),
                "source_types": [BRIDGE_SOURCE, *list(event.get("source_types") or [])],
                "entities": entity_codes,
                "themes": themes,
                "evidence": evidence,
                "source_tier": source_tier,
                "source_doc_uids": list(event.get("source_doc_uids") or []),
                "provider_chain": list(event.get("provider_chain") or []),
                "event_anchor_id": event_anchor_id,
                "reliability_score": reliability,
                "normalized_event_status": event.get("status"),
                "validation_summary": dict(validation.get("validation_summary") or {}),
                "occurrence_status": occurrence_status,
                "alpha_confirmation_status": alpha_status,
                "confidence_cap_reason": validation.get("confidence_cap_reason"),
                "needs_alpha_confirmation": bool(validation.get("needs_alpha_confirmation")),
                "conflict_count": int(validation.get("conflict_count") or 0),
                "occurred_at": event.get("event_time") or event.get("publish_time"),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
                "status": "active",
            }
        )
        bridged_events += 1
        for code in entity_codes[:20]:
            for theme_code in theme_codes[:3]:
                await db.save_factory_event_signal(
                    {
                        "event_id": event_id,
                        "symbol": code,
                        "theme_code": theme_code,
                        "direction": direction,
                        "theme_score": reliability,
                        "exposure_score": reliability,
                        "price_confirm_score": 0.0,
                        "flow_confirm_score": 0.0,
                        "fundamental_confirm_score": reliability if event.get("event_type") in {"earnings_forecast", "research_rating"} else 0.0,
                        "final_score": reliability,
                        "rationale": event.get("summary") or event.get("event_name"),
                        "evidence": evidence,
                        "observed_at": event.get("evidence_time") or datetime.now(timezone.utc).isoformat(),
                    }
                )
                signals += 1
    return {
        "enabled": True,
        "bridged_events": bridged_events,
        "diagnostic_events": diagnostic_events,
        "signals": signals,
        "skipped": skipped,
        "source": BRIDGE_SOURCE,
    }


__all__ = [
    "BRIDGE_SOURCE",
    "MarketEventSourceAdapter",
    "build_market_event_source_adapters",
    "event_source_status",
    "fetch_cninfo_official_announcements",
    "fetch_sse_official_announcements",
    "fetch_official_market_event_documents",
    "normalize_market_text_events",
    "persist_normalized_events",
    "bridge_normalized_events_to_strategy_factory",
]
