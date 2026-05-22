"""Public market text ingestion for SQLite vector search.

This module turns publicly accessible news / notices / research metadata into
the unified ``market_documents`` / ``market_doc_chunks`` / vector collections.
It intentionally stores public summaries and metadata, not paid report bodies.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import requests

from ..vector_collection_scope import normalize_market_doc_types, resolve_vector_collection_name

EASTMONEY_NEWS_URL = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.eastmoney.com/",
}


def _clean_text(value: Any, limit: int = 20000) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return ""
    return " ".join(text.split())[:limit]


def _positive_int(value: Any, default: int, *, minimum: int = 0, maximum: int = 5000) -> int:
    try:
        resolved = int(default if value is None or value == "" else value)
    except (TypeError, ValueError):
        resolved = int(default)
    return max(minimum, min(resolved, maximum))


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_codes(raw: Any) -> list[str]:
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple, set)) else str(raw).replace(";", ",").split(",")
    codes: list[str] = []
    seen: set[str] = set()
    for item in items:
        code = _clean_text(item, 20)
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def _parse_code_from_notice_url(url: Any) -> str:
    matched = re.search(r"/detail/(\d{6})/", str(url or ""))
    return matched.group(1) if matched else ""


def fetch_eastmoney_finance_news(limit: int) -> list[dict[str, Any]]:
    """Fetch public Eastmoney finance headlines and summaries."""

    resolved_limit = _positive_int(limit, 50, minimum=1, maximum=500)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    while len(items) < resolved_limit and page <= 10:
        page_size = min(50, max(1, resolved_limit - len(items)))
        params = {
            "client": "web",
            "biz": "web_news_col",
            "column": "350",
            "order": "1",
            "needInteractData": "0",
            "page_index": str(page),
            "page_size": str(page_size),
            "req_trace": f"{int(time.time() * 1000)}{random.randint(100, 999)}",
        }
        response = requests.get(EASTMONEY_NEWS_URL, params=params, headers=EASTMONEY_HEADERS, timeout=15)
        response.raise_for_status()
        payload = response.json()
        rows = ((payload.get("data") or {}).get("list") or []) if isinstance(payload, dict) else []
        if not rows:
            break
        for row in rows:
            title = _clean_text(row.get("title"), 500)
            summary = _clean_text(row.get("summary"), 4000)
            url = _clean_text(row.get("uniqueUrl") or row.get("url"), 1000)
            source_id = _clean_text(row.get("code"), 200) or url or title
            if not title or source_id in seen:
                continue
            seen.add(source_id)
            items.append(
                {
                    "doc_uid": f"eastmoney_news:{source_id}",
                    "title": title,
                    "summary": summary,
                    "content": " ".join(part for part in (title, summary) if part),
                    "date": _clean_text(row.get("showTime"), 40),
                    "published_at": _clean_text(row.get("showTime"), 40),
                    "source": _clean_text(row.get("mediaName"), 120) or "eastmoney_finance_news",
                    "url": url,
                    "provider": "eastmoney_finance_news",
                }
            )
            if len(items) >= resolved_limit:
                break
        page += 1
    return items


def _map_notice_item(item: dict[str, Any]) -> dict[str, Any]:
    code = _clean_text(item.get("code") or item.get("stock_code") or _parse_code_from_notice_url(item.get("url")), 20)
    title = _clean_text(item.get("title"), 500)
    notice_type = _clean_text(item.get("type") or item.get("notice_type"), 120)
    body = " ".join(part for part in (title, notice_type) if part)
    return {
        "doc_uid": _clean_text(item.get("url"), 1000) or f"eastmoney_notice:{code}:{item.get('date')}:{title}",
        "title": title,
        "summary": body,
        "content": body,
        "date": _clean_text(item.get("date"), 40),
        "published_at": _clean_text(item.get("date"), 40),
        "source": _clean_text(item.get("source"), 120) or "eastmoney_notice",
        "url": _clean_text(item.get("url"), 1000),
        "provider": "eastmoney_notice",
        "notice_type": notice_type,
        "code": code,
    }


def _map_research_item(item: dict[str, Any]) -> dict[str, Any]:
    title = _clean_text(item.get("title"), 500)
    institution = _clean_text(item.get("institution") or item.get("source"), 200)
    author = _clean_text(item.get("author") or item.get("analyst"), 200)
    rating = _clean_text(item.get("rating"), 120)
    summary = _clean_text(item.get("summary") or item.get("content") or item.get("text"), 4000)
    body_parts = [
        title,
        f"机构:{institution}" if institution else "",
        f"评级:{rating}" if rating else "",
        summary,
    ]
    return {
        "title": title,
        "summary": " ".join(part for part in body_parts[1:] if part),
        "content": " ".join(part for part in body_parts if part),
        "date": _clean_text(item.get("date") or item.get("publish_date"), 40),
        "published_at": _clean_text(item.get("date") or item.get("publish_date"), 40),
        "source": institution or "akshare_research_report_em",
        "url": _clean_text(item.get("url") or item.get("pdf_url"), 1000),
        "provider": "akshare_stock_research_report_em",
        "author": author,
        "rating": rating,
        "institution": institution,
    }


async def _insert_news_cache(db, rows: list[dict[str, Any]], *, stock_code: str, news_type: str) -> int:
    inserted = 0
    async with db.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_cache (
                id INTEGER PRIMARY KEY,
                stock_code TEXT,
                news_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                source TEXT,
                url TEXT,
                publish_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for item in rows:
            title = _clean_text(item.get("title"), 500)
            if not title:
                continue
            result = await conn.fetchval(
                """
                INSERT INTO news_cache (stock_code, news_type, title, content, source, url, publish_date, created_at)
                SELECT $1, $2, $3, $4, $5, $6, $7, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                    SELECT 1 FROM news_cache
                    WHERE COALESCE(stock_code, '') = COALESCE($1, '')
                      AND news_type = $2
                      AND title = $3
                      AND COALESCE(publish_date, '') = COALESCE($7, '')
                )
                RETURNING 1
                """,
                stock_code,
                news_type,
                title,
                _clean_text(item.get("content") or item.get("summary"), 4000),
                _clean_text(item.get("source"), 120),
                _clean_text(item.get("url"), 1000),
                _clean_text(item.get("date") or item.get("published_at"), 40),
            )
            if result:
                inserted += 1
    return inserted


async def _select_stock_universe(db, *, limit: int, extra_codes: list[str]) -> list[str]:
    resolved_limit = _positive_int(limit, 30, minimum=0, maximum=1000)
    codes: list[str] = []
    seen: set[str] = set()
    for code in extra_codes:
        if re.fullmatch(r"\d{6}", code) and code not in seen:
            seen.add(code)
            codes.append(code)
    if resolved_limit <= 0:
        return codes
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT stock_code
            FROM stocks
            WHERE stock_code IS NOT NULL AND length(stock_code) = 6
            ORDER BY COALESCE(market_cap, 0) DESC, stock_code ASC
            LIMIT $1
            """,
            max(1, resolved_limit * 2),
        )
    for row in rows:
        code = _clean_text(dict(row).get("stock_code"), 20)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
        if len(codes) >= resolved_limit:
            break
    return codes[:resolved_limit]


def _merge_saved_totals(target: dict[str, Any], saved: dict[str, Any]) -> None:
    for key in ("documents", "chunks", "embedded_chunks", "headline_labels"):
        target[key] = int(target.get(key) or 0) + int(saved.get(key) or 0)
    for key, value in dict(saved.get("profile_version_counts") or {}).items():
        bucket = target.setdefault("profile_version_counts", {})
        bucket[str(key)] = int(bucket.get(str(key)) or 0) + int(value or 0)
    for vector_dim in list(saved.get("vector_dims") or []):
        dims = target.setdefault("vector_dims", [])
        resolved_dim = int(vector_dim or 0)
        if resolved_dim > 0 and resolved_dim not in dims:
            dims.append(resolved_dim)


def _snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    qa = dict(snapshot.get("qa") or {})
    snap = dict(snapshot.get("snapshot") or {})
    return {
        "collection_name": snapshot.get("collection_name") or snap.get("collection_name"),
        "profile_type": snapshot.get("profile_type") or snap.get("profile_type"),
        "profile_version": snapshot.get("profile_version"),
        "index_version": snapshot.get("index_version") or snap.get("index_version"),
        "status": snapshot.get("status") or snap.get("status"),
        "degraded": bool(snapshot.get("degraded")),
        "quality_flags": list(snapshot.get("quality_flags") or []),
        "sample_count": int(snapshot.get("sample_count") or snap.get("sample_count") or 0),
        "items_count": int(snapshot.get("items_count") or (snap.get("metrics") or {}).get("items_count") or 0),
        "bucket_count": int(snapshot.get("bucket_count") or snap.get("bucket_count") or 0),
        "qa_status": qa.get("status"),
    }


async def _build_market_doc_snapshots(
    db,
    *,
    doc_types: list[str],
    activate: bool,
    dry_run: bool,
) -> list[dict[str, Any]]:
    if dry_run:
        return [
            {
                "collection_name": resolve_vector_collection_name("market_doc_chunks", doc_type),
                "profile_type": doc_type,
                "status": "skipped",
                "reason": "dry_run",
            }
            for doc_type in doc_types
        ]

    from .unified_vector_governance import build_vector_collection_snapshot

    snapshots: list[dict[str, Any]] = []
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT collection_name, profile_type, version, vector_dim, COUNT(*) AS rows
            FROM vector_profiles
            WHERE collection_name LIKE 'market_doc_chunks__%'
            GROUP BY collection_name, profile_type, version, vector_dim
            ORDER BY collection_name, version
            """
        )
    requested = {resolve_vector_collection_name("market_doc_chunks", doc_type) for doc_type in doc_types}
    for row in rows:
        item = dict(row)
        collection_name = str(item.get("collection_name") or "")
        if collection_name not in requested or int(item.get("rows") or 0) <= 0:
            continue
        snapshot = await build_vector_collection_snapshot(
            db,
            collection_name=collection_name,
            version=str(item.get("version") or "v1"),
            index_version=str(item.get("version") or "v1"),
            profile_type=str(item.get("profile_type") or "") or None,
            activate=activate,
            source="data_sync_manager.market_text_source_ingest",
        )
        snapshots.append(_snapshot_summary(snapshot))
    return snapshots


async def _load_final_counts(db) -> dict[str, Any]:
    async with db.acquire() as conn:
        docs = await conn.fetch(
            "SELECT doc_type, COUNT(*) AS rows FROM market_documents GROUP BY doc_type ORDER BY doc_type"
        )
        chunks = await conn.fetch(
            "SELECT doc_type, COUNT(*) AS rows FROM market_doc_chunks GROUP BY doc_type ORDER BY doc_type"
        )
        profiles = await conn.fetch(
            """
            SELECT collection_name, profile_type, version, vector_dim, COUNT(*) AS rows
            FROM vector_profiles
            WHERE collection_name LIKE 'market_doc_chunks__%'
            GROUP BY collection_name, profile_type, version, vector_dim
            ORDER BY collection_name
            """
        )
        fts_rows = await conn.fetchval("SELECT COUNT(*) FROM market_doc_chunks_fts")
        integrity = await conn.fetchval("PRAGMA integrity_check")
    return {
        "market_documents_by_type": [dict(row) for row in docs],
        "market_doc_chunks_by_type": [dict(row) for row in chunks],
        "market_doc_vector_profiles": [dict(row) for row in profiles],
        "fts_rows": int(fts_rows or 0),
        "integrity_check": integrity,
    }


async def run_market_text_source_ingest(
    db,
    *,
    stock_codes: Any = None,
    doc_types: Any = None,
    news_limit: Any = 50,
    notice_limit: Any = 80,
    notice_days: Any = 30,
    code_notice_limit: Any = 2,
    code_notice_code_limit: Any = 20,
    research_code_limit: Any = 30,
    research_per_code: Any = 2,
    chunk_size: Any = 1000,
    overlap: Any = 120,
    version: str = "v1",
    embed: Any = True,
    build_snapshot: Any = True,
    activate_snapshot: Any = True,
    allow_network: Any = True,
    dry_run: Any = False,
) -> dict[str, Any]:
    """Incrementally ingest public market text and rebuild vector snapshots."""

    requested_doc_types = normalize_market_doc_types(doc_types) or ["news", "notice", "research"]
    requested_codes = _normalize_codes(stock_codes)
    resolved_news_limit = _positive_int(news_limit, 50, minimum=0, maximum=1000)
    resolved_notice_limit = _positive_int(notice_limit, 80, minimum=0, maximum=1000)
    resolved_notice_days = _positive_int(notice_days, 30, minimum=1, maximum=365)
    resolved_code_notice_limit = _positive_int(code_notice_limit, 2, minimum=0, maximum=100)
    resolved_code_notice_code_limit = _positive_int(code_notice_code_limit, 20, minimum=0, maximum=1000)
    resolved_research_code_limit = _positive_int(research_code_limit, 30, minimum=0, maximum=1000)
    resolved_research_per_code = _positive_int(research_per_code, 2, minimum=0, maximum=50)
    resolved_chunk_size = _positive_int(chunk_size, 1000, minimum=200, maximum=4000)
    resolved_overlap = _positive_int(overlap, 120, minimum=0, maximum=1500)
    resolved_embed = _as_bool(embed, True)
    resolved_build_snapshot = _as_bool(build_snapshot, True)
    resolved_activate_snapshot = _as_bool(activate_snapshot, True)
    resolved_allow_network = _as_bool(allow_network, True)
    resolved_dry_run = _as_bool(dry_run, False)
    resolved_version = str(version or "v1").strip() or "v1"

    result: dict[str, Any] = {
        "doc_types": requested_doc_types,
        "args": {
            "stock_codes": requested_codes,
            "news_limit": resolved_news_limit,
            "notice_limit": resolved_notice_limit,
            "notice_days": resolved_notice_days,
            "code_notice_limit": resolved_code_notice_limit,
            "code_notice_code_limit": resolved_code_notice_code_limit,
            "research_code_limit": resolved_research_code_limit,
            "research_per_code": resolved_research_per_code,
            "chunk_size": resolved_chunk_size,
            "overlap": resolved_overlap,
            "version": resolved_version,
            "embed": resolved_embed,
            "build_snapshot": resolved_build_snapshot,
            "activate_snapshot": resolved_activate_snapshot,
            "allow_network": resolved_allow_network,
            "dry_run": resolved_dry_run,
        },
        "fetched": {},
        "saved": {},
        "snapshots": [],
        "errors": [],
        "quality_flags": [],
    }
    if not resolved_allow_network:
        result["quality_flags"].append("network_disabled")

    end_date = date.today()
    start_date = end_date - timedelta(days=resolved_notice_days)

    if "news" in requested_doc_types and resolved_news_limit > 0 and resolved_allow_network:
        try:
            news_items = fetch_eastmoney_finance_news(resolved_news_limit)
        except Exception as exc:
            news_items = []
            result["errors"].append({"source": "eastmoney_finance_news", "error": f"{type(exc).__name__}: {exc}"})
        result["fetched"]["news"] = len(news_items)
        if news_items:
            if resolved_dry_run:
                result["saved"]["news"] = {"candidate_docs": len(news_items), "dry_run": True}
            else:
                cache_rows = await _insert_news_cache(db, news_items, stock_code="MARKET", news_type="news")
                saved = await db.save_market_documents(
                    "MARKET",
                    "news",
                    news_items,
                    embed=resolved_embed,
                    chunk_size=resolved_chunk_size,
                    overlap=resolved_overlap,
                    version=resolved_version,
                )
                result["saved"]["news"] = {**saved, "news_cache_inserted": cache_rows}

    notice_codes: list[str] = []
    if "notice" in requested_doc_types and resolved_notice_limit > 0 and resolved_allow_network:
        from ..tools.news.notices import fetch_market_notice_head, get_stock_notices

        try:
            raw_notices = fetch_market_notice_head(
                start_date.isoformat(),
                end_date.isoformat(),
                max_items=resolved_notice_limit,
            )
        except Exception as exc:
            raw_notices = []
            result["errors"].append({"source": "eastmoney_notice_head", "error": f"{type(exc).__name__}: {exc}"})
        notice_items = [_map_notice_item(item) for item in raw_notices]
        notice_items = [item for item in notice_items if item.get("code") and item.get("title")]
        result["fetched"]["notice_head"] = len(notice_items)
        notices_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in notice_items:
            notices_by_code[str(item.get("code"))].append(item)
        notice_codes = list(notices_by_code.keys())
        notice_saved = {"documents": 0, "chunks": 0, "embedded_chunks": 0, "headline_labels": 0, "news_cache_inserted": 0}
        if resolved_dry_run:
            notice_saved["candidate_docs"] = len(notice_items)
        else:
            for code, items in notices_by_code.items():
                cache_rows = await _insert_news_cache(db, items, stock_code=code, news_type="notice")
                saved = await db.save_market_documents(
                    code,
                    "notice",
                    items,
                    embed=resolved_embed,
                    chunk_size=resolved_chunk_size,
                    overlap=resolved_overlap,
                    version=resolved_version,
                )
                _merge_saved_totals(notice_saved, saved)
                notice_saved["news_cache_inserted"] += int(cache_rows or 0)
        result["saved"]["notice_head"] = notice_saved

        universe = await _select_stock_universe(
            db,
            limit=resolved_code_notice_code_limit,
            extra_codes=requested_codes or notice_codes[:10],
        )
        code_notice_saved = {
            "fetched": 0,
            "documents": 0,
            "chunks": 0,
            "embedded_chunks": 0,
            "headline_labels": 0,
            "news_cache_inserted": 0,
            "failed_codes": [],
        }
        for code in universe:
            if resolved_code_notice_limit <= 0:
                break
            try:
                response = get_stock_notices(
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    stock_code=code,
                    types=["全部"],
                    prefer_db=False,
                )
                events = ((response.get("data") or {}).get("events") or []) if isinstance(response, dict) else []
                mapped = [_map_notice_item(item) for item in events[:resolved_code_notice_limit]]
                mapped = [item for item in mapped if item.get("title")]
                code_notice_saved["fetched"] += len(mapped)
                if mapped and not resolved_dry_run:
                    cache_rows = await _insert_news_cache(db, mapped, stock_code=code, news_type="notice")
                    saved = await db.save_market_documents(
                        code,
                        "notice",
                        mapped,
                        embed=resolved_embed,
                        chunk_size=resolved_chunk_size,
                        overlap=resolved_overlap,
                        version=resolved_version,
                    )
                    _merge_saved_totals(code_notice_saved, saved)
                    code_notice_saved["news_cache_inserted"] += int(cache_rows or 0)
            except Exception as exc:
                code_notice_saved["failed_codes"].append({"code": code, "error": f"{type(exc).__name__}: {exc}"})
        result["fetched"]["notice_universe"] = universe
        result["saved"]["code_notices"] = code_notice_saved

    if "research" in requested_doc_types and resolved_research_code_limit > 0 and resolved_research_per_code > 0 and resolved_allow_network:
        from ..tools.news.research import get_research_reports

        universe = await _select_stock_universe(
            db,
            limit=resolved_research_code_limit,
            extra_codes=requested_codes or notice_codes[:10],
        )
        research_saved = {
            "fetched": 0,
            "legacy_inserted": 0,
            "documents": 0,
            "chunks": 0,
            "embedded_chunks": 0,
            "headline_labels": 0,
            "failed_codes": [],
        }
        for code in universe:
            try:
                response = get_research_reports(code=code, limit=resolved_research_per_code, prefer_db=False)
                payload = response.get("data") if isinstance(response, dict) else {}
                rows = list((payload or {}).get("reports") or []) if isinstance(payload, dict) else []
                mapped = [_map_research_item(item) for item in rows[:resolved_research_per_code]]
                mapped = [item for item in mapped if item.get("title") or item.get("summary")]
                research_saved["fetched"] += len(mapped)
                if mapped and not resolved_dry_run:
                    legacy_inserted = await db.save_research_reports(code, mapped)
                    saved = await db.save_market_documents(
                        code,
                        "research",
                        mapped,
                        embed=resolved_embed,
                        chunk_size=resolved_chunk_size,
                        overlap=resolved_overlap,
                        version=resolved_version,
                    )
                    research_saved["legacy_inserted"] += int(legacy_inserted or 0)
                    _merge_saved_totals(research_saved, saved)
            except Exception as exc:
                research_saved["failed_codes"].append({"code": code, "error": f"{type(exc).__name__}: {exc}"})
        result["fetched"]["research_universe"] = universe
        result["saved"]["research"] = research_saved

    if resolved_build_snapshot:
        try:
            result["snapshots"] = await _build_market_doc_snapshots(
                db,
                doc_types=requested_doc_types,
                activate=resolved_activate_snapshot,
                dry_run=resolved_dry_run,
            )
        except Exception as exc:
            result["errors"].append({"source": "snapshot", "error": f"{type(exc).__name__}: {exc}"})

    try:
        result["final_counts"] = await _load_final_counts(db)
    except Exception as exc:
        result["errors"].append({"source": "final_counts", "error": f"{type(exc).__name__}: {exc}"})

    saved_docs = sum(
        int(value.get("documents") or value.get("candidate_docs") or 0)
        for value in dict(result.get("saved") or {}).values()
        if isinstance(value, dict)
    )
    embedded_chunks = sum(
        int(value.get("embedded_chunks") or 0)
        for value in dict(result.get("saved") or {}).values()
        if isinstance(value, dict)
    )
    result["totals"] = {
        "saved_docs": saved_docs,
        "embedded_chunks": embedded_chunks,
        "snapshots": len(result.get("snapshots") or []),
        "errors": len(result.get("errors") or []),
    }
    if result["errors"]:
        result["quality_flags"].append("source_errors_present")
    return result
