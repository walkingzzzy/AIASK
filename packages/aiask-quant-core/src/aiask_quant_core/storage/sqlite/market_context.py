"""SQLite adapter mixin for factor/decision text context storage."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from aiask_quant_core.vector_collection_scope import resolve_dimension_scoped_version, resolve_vector_collection_name


logger = logging.getLogger(__name__)


class MarketContextMixin:
    """DB persistence helpers for news/notices/research/fund-flow context."""

    _SOURCE_TIER_ALIASES = {
        "a": "tier_a",
        "official": "tier_a",
        "official_disclosure": "tier_a",
        "tier_a": "tier_a",
        "b": "tier_b",
        "institutional": "tier_b",
        "paid": "tier_b",
        "tier_b": "tier_b",
        "c": "tier_c",
        "media": "tier_c",
        "open_media": "tier_c",
        "tier_c": "tier_c",
    }

    _SOURCE_TIER_DEFAULT_RELIABILITY = {
        "tier_a": 0.92,
        "tier_b": 0.82,
        "tier_c": 0.45,
    }

    @staticmethod
    def _coerce_context_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except Exception:
            pass
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 8:
            try:
                return date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}")
            except Exception:
                return None
        return None

    @staticmethod
    def _coerce_context_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_context_text(value: Any, *, max_len: int = 4000) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text[:max_len]

    @classmethod
    def _normalize_source_tier(cls, value: Any, *, provider: Any = None, source: Any = None) -> str:
        raw = str(value or "").strip().lower()
        if raw in cls._SOURCE_TIER_ALIASES:
            return cls._SOURCE_TIER_ALIASES[raw]
        provider_text = str(provider or source or "").strip().lower()
        if any(token in provider_text for token in ("cninfo", "sse", "szse", "bse", "csrc", "巨潮", "上交所", "深交所", "北交所", "证监会")):
            return "tier_a"
        if any(token in provider_text for token in ("wind", "ifind", "choice", "tushare")):
            return "tier_b"
        return "tier_c"

    @classmethod
    def _default_reliability_score(cls, source_tier: str) -> float:
        return cls._SOURCE_TIER_DEFAULT_RELIABILITY.get(str(source_tier or "").strip().lower(), 0.35)

    @classmethod
    def _pick_document_provider(cls, item: dict[str, Any], *, source: str = "") -> str:
        return cls._clean_context_text(
            item.get("provider") or item.get("data_provider") or item.get("origin") or source,
            max_len=120,
        )

    @classmethod
    def _pick_document_original_id(cls, item: dict[str, Any]) -> str:
        return cls._clean_context_text(
            item.get("original_id")
            or item.get("art_code")
            or item.get("announcement_id")
            or item.get("ann_id")
            or item.get("id")
            or item.get("code"),
            max_len=240,
        )

    @classmethod
    def _build_document_checksum(cls, item: dict[str, Any], *, title: str, body: str, url: str, published_at: datetime | None) -> str:
        explicit = cls._clean_context_text(item.get("checksum"), max_len=128)
        if explicit:
            return explicit
        basis = "|".join(
            [
                str(item.get("provider") or item.get("source") or ""),
                title or "",
                url or "",
                published_at.isoformat() if published_at else "",
                body[:4000] if body else "",
            ]
        )
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    @classmethod
    def _coerce_context_datetime(cls, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        raw = str(value or "").strip()
        if not raw:
            return None
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            pass
        parsed_date = cls._coerce_context_date(raw)
        return datetime.combine(parsed_date, datetime.min.time()) if parsed_date else None

    @staticmethod
    def _json_list(values: Any) -> list[Any]:
        if values is None:
            return []
        if isinstance(values, list):
            return values
        if isinstance(values, (tuple, set)):
            return list(values)
        text = str(values or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]

    @classmethod
    def _pick_document_content(cls, item: dict[str, Any]) -> str:
        for key in ("content", "text", "summary", "title", "headline", "name"):
            text = cls._clean_context_text(item.get(key))
            if text:
                return text
        return ""

    @classmethod
    def _pick_document_title(cls, item: dict[str, Any]) -> str:
        for key in ("title", "headline", "name", "summary"):
            text = cls._clean_context_text(item.get(key), max_len=240)
            if text:
                return text
        content = cls._pick_document_content(item)
        return cls._clean_context_text(content[:120], max_len=120)

    @classmethod
    def _pick_document_summary(cls, item: dict[str, Any]) -> str:
        for key in ("summary", "abstract", "description", "content", "text"):
            text = cls._clean_context_text(item.get(key), max_len=1000)
            if text:
                return text
        return ""

    @classmethod
    def _pick_document_body(cls, item: dict[str, Any]) -> str:
        for key in ("body", "content", "text", "summary", "title", "headline", "name"):
            text = cls._clean_context_text(item.get(key), max_len=20000)
            if text:
                return text
        return ""

    @classmethod
    def _pick_document_source(cls, doc_type: str, item: dict[str, Any]) -> str:
        source = cls._clean_context_text(item.get("source") or item.get("provider") or item.get("origin"), max_len=120)
        return source or str(doc_type or "unknown").strip().lower()

    @classmethod
    def _pick_document_url(cls, item: dict[str, Any]) -> str:
        return cls._clean_context_text(item.get("url") or item.get("link") or item.get("pdf_url"), max_len=1000)

    @classmethod
    def _build_market_doc_uid(cls, stock_code: str, doc_type: str, item: dict[str, Any]) -> str:
        explicit = cls._clean_context_text(
            item.get("doc_uid") or item.get("document_id") or item.get("id") or item.get("uuid"),
            max_len=200,
        )
        if explicit:
            return explicit
        url = cls._pick_document_url(item)
        if url:
            return url
        title = cls._pick_document_title(item)
        body = cls._pick_document_body(item)[:1000]
        published_at = cls._coerce_context_date(item.get("published_at") or item.get("date") or item.get("time"))
        basis = "|".join(
            [
                str(stock_code or "").strip(),
                str(doc_type or "").strip().lower(),
                title,
                published_at.isoformat() if published_at else "",
                body,
            ]
        )
        return f"mdoc_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _count_text_tokens(text: str) -> int:
        normalized = str(text or "").strip()
        if not normalized:
            return 0
        return len(normalized.split()) if " " in normalized else len(normalized)

    @classmethod
    def _chunk_document_text(
        cls,
        text: str,
        *,
        chunk_size: int = 800,
        overlap: int = 120,
    ) -> list[str]:
        normalized = " ".join(str(text or "").replace("\r", " ").split())
        if not normalized:
            return []
        resolved_chunk_size = max(200, int(chunk_size or 800))
        resolved_overlap = max(0, min(int(overlap or 120), resolved_chunk_size // 2))
        if len(normalized) <= resolved_chunk_size:
            return [normalized]
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + resolved_chunk_size)
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(normalized):
                break
            start = max(end - resolved_overlap, start + 1)
        return chunks

    @staticmethod
    def _headline_horizon_days(doc_type: str) -> int:
        normalized = str(doc_type or "").strip().lower()
        if normalized == "news":
            return 5
        if normalized == "notice":
            return 10
        if normalized == "research":
            return 20
        return 5

    @staticmethod
    def _headline_direction(label: str) -> str:
        normalized = str(label or "").strip().lower()
        if normalized == "bullish":
            return "up"
        if normalized == "bearish":
            return "down"
        return "flat"

    @classmethod
    def _build_headline_label_id(
        cls,
        *,
        doc_uid: str,
        headline: str,
        label: str,
        event_type: str | None,
    ) -> str:
        basis = "|".join([doc_uid, headline, label, str(event_type or "")])
        return f"hlabel_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:24]}"

    @classmethod
    def _extract_headline_label_rows(
        cls,
        stock_code: str,
        doc_type: str,
        item: dict[str, Any],
        *,
        doc_id: int | None,
        doc_uid: str,
        published_at: datetime | None,
    ) -> list[dict[str, Any]]:
        headline = cls._pick_document_title(item)
        if not headline:
            return []
        from aiask_quant_core.storage.runtime_hooks import (
            get_event_extractor,
            get_headline_sentiment_classifier,
        )

        summary = cls._pick_document_summary(item)
        body = cls._pick_document_body(item)
        classifier = get_headline_sentiment_classifier()
        extractor = get_event_extractor()
        label = classifier(headline) if callable(classifier) else "neutral"
        extraction = (
            extractor(
                [{"title": headline, "text": " ".join(part for part in [headline, summary, body[:200]] if part)}],
                top_n=1,
            )
            if callable(extractor)
            else {}
        )
        event_tags = list(extraction.get("event_tags") or [])
        event_type = str(event_tags[0].get("tag") or "").strip() if event_tags else None
        keywords = list(dict(extraction.get("keyword_hits") or {}).keys())[:8]
        keyword_count = len(keywords)
        intensity = "high" if keyword_count >= 3 else "medium" if keyword_count >= 1 else "low"
        confidence = min(0.95, 0.55 + keyword_count * 0.10)
        label_id = cls._build_headline_label_id(
            doc_uid=doc_uid,
            headline=headline,
            label=label,
            event_type=event_type,
        )
        payload = {
            "doc_uid": doc_uid,
            "headline": headline,
            "summary": summary,
            "source": item.get("source") or item.get("provider") or item.get("origin"),
            "event_tags": event_tags,
            "keyword_hits": dict(extraction.get("keyword_hits") or {}),
        }
        return [
            {
                "label_id": label_id,
                "doc_id": doc_id,
                "doc_uid": doc_uid,
                "stock_code": str(stock_code or "").strip(),
                "doc_type": str(doc_type or "").strip().lower(),
                "published_at": published_at,
                "headline": headline,
                "label": label,
                "event_type": event_type,
                "direction": cls._headline_direction(label),
                "horizon_days": cls._headline_horizon_days(doc_type),
                "intensity": intensity,
                "confidence": round(confidence, 4),
                "keywords": keywords,
                "payload": payload,
            }
        ]

    async def save_market_headline_labels(
        self,
        stock_code: str,
        doc_type: str,
        items: Iterable[dict[str, Any]],
        *,
        doc_uid_map: Optional[dict[str, tuple[int | None, datetime | None]]] = None,
    ) -> int:
        code = str(stock_code or "").strip()
        normalized_doc_type = str(doc_type or "").strip().lower()
        rows: list[dict[str, Any]] = []
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            doc_uid = self._build_market_doc_uid(code, normalized_doc_type, item)
            mapped = dict(doc_uid_map or {}).get(doc_uid) or (None, None)
            rows.extend(
                self._extract_headline_label_rows(
                    code,
                    normalized_doc_type,
                    item,
                    doc_id=mapped[0],
                    doc_uid=doc_uid,
                    published_at=mapped[1],
                )
            )
        if not rows:
            return 0
        inserted = 0
        async with self.acquire() as conn:
            for row in rows:
                result = await conn.fetchval(
                    """
                    INSERT INTO market_headline_labels (
                        label_id, doc_id, doc_uid, stock_code, doc_type, published_at, headline, label,
                        event_type, direction, horizon_days, intensity, confidence, keywords, payload, created_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8,
                        $9, $10, $11, $12, $13, $14, $15, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (label_id) DO UPDATE SET
                        doc_id = COALESCE(EXCLUDED.doc_id, market_headline_labels.doc_id),
                        published_at = COALESCE(EXCLUDED.published_at, market_headline_labels.published_at),
                        headline = COALESCE(EXCLUDED.headline, market_headline_labels.headline),
                        label = COALESCE(EXCLUDED.label, market_headline_labels.label),
                        event_type = COALESCE(EXCLUDED.event_type, market_headline_labels.event_type),
                        direction = COALESCE(EXCLUDED.direction, market_headline_labels.direction),
                        horizon_days = COALESCE(EXCLUDED.horizon_days, market_headline_labels.horizon_days),
                        intensity = COALESCE(EXCLUDED.intensity, market_headline_labels.intensity),
                        confidence = COALESCE(EXCLUDED.confidence, market_headline_labels.confidence),
                        keywords = COALESCE(EXCLUDED.keywords, market_headline_labels.keywords),
                        payload = COALESCE(EXCLUDED.payload, market_headline_labels.payload)
                    RETURNING 1
                    """,
                    row.get("label_id"),
                    row.get("doc_id"),
                    row.get("doc_uid"),
                    row.get("stock_code"),
                    row.get("doc_type"),
                    row.get("published_at"),
                    row.get("headline"),
                    row.get("label"),
                    row.get("event_type"),
                    row.get("direction"),
                    row.get("horizon_days"),
                    row.get("intensity"),
                    row.get("confidence"),
                    json.dumps(row.get("keywords") or [], ensure_ascii=False, default=str),
                    json.dumps(row.get("payload") or {}, ensure_ascii=False, default=str),
                )
                if result:
                    inserted += 1
        return inserted

    async def list_market_headline_labels(
        self,
        stock_code: str,
        *,
        doc_type: Optional[str] = None,
        label: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM market_headline_labels WHERE stock_code = $1"
            params: list[Any] = [str(stock_code or "").strip()]
            idx = 2
            if doc_type:
                sql += f" AND doc_type = ${idx}"
                params.append(str(doc_type).strip().lower())
                idx += 1
            if label:
                sql += f" AND label = ${idx}"
                params.append(str(label).strip().lower())
                idx += 1
            sql += f" ORDER BY published_at DESC NULLS LAST, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 2000)))
            rows = await conn.fetch(sql, *params)
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["keywords"] = self._decode_json_field(payload.get("keywords"), [])
            payload["payload"] = self._decode_json_field(payload.get("payload"), {})
            result.append(payload)
        return result

    def _decode_market_event_normalized(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row or {})
        for key in ("entity_codes", "theme_codes", "source_doc_uids", "source_types", "provider_chain"):
            payload[key] = self._decode_json_field(payload.get(key), [])
        payload["metadata"] = self._decode_json_field(payload.get("metadata"), {})
        return payload

    async def upsert_market_event_normalized(self, item: dict[str, Any]) -> dict[str, Any]:
        payload = dict(item or {})
        event_id = self._clean_context_text(payload.get("event_id"), max_len=200)
        event_type = self._clean_context_text(payload.get("event_type") or "other", max_len=120)
        event_name = self._clean_context_text(payload.get("event_name") or payload.get("summary"), max_len=300)
        if not event_id:
            basis = "|".join(
                [
                    event_type,
                    event_name,
                    str(payload.get("publish_time") or payload.get("evidence_time") or ""),
                    ",".join(str(item) for item in self._json_list(payload.get("source_doc_uids"))),
                ]
            )
            event_id = f"mevt_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:24]}"
        if not event_name:
            raise ValueError("event_name is required")
        source_tier = self._normalize_source_tier(payload.get("source_tier"))
        reliability_score = self._coerce_context_float(payload.get("reliability_score"))
        if reliability_score is None:
            reliability_score = self._default_reliability_score(source_tier)
        status = self._clean_context_text(payload.get("status") or "provisional", max_len=80) or "provisional"
        checksum = self._clean_context_text(payload.get("checksum"), max_len=128)
        if not checksum:
            checksum_basis = "|".join(
                [
                    event_type,
                    event_name,
                    str(payload.get("publish_time") or ""),
                    json.dumps(self._json_list(payload.get("source_doc_uids")), ensure_ascii=False, sort_keys=True),
                ]
            )
            checksum = hashlib.sha1(checksum_basis.encode("utf-8")).hexdigest()
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO market_events_normalized (
                    event_id, event_type, event_name, summary, entity_codes, theme_codes, direction,
                    event_time, publish_time, evidence_time, source_doc_uids, source_tier, source_types,
                    provider_chain, reliability_score, cross_source_count, status, reject_reason,
                    freshness_status, event_anchor_id, checksum, metadata, created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17, $18,
                    $19, $20, $21, $22, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (event_id) DO UPDATE SET
                    event_type = EXCLUDED.event_type,
                    event_name = EXCLUDED.event_name,
                    summary = EXCLUDED.summary,
                    entity_codes = EXCLUDED.entity_codes,
                    theme_codes = EXCLUDED.theme_codes,
                    direction = EXCLUDED.direction,
                    event_time = EXCLUDED.event_time,
                    publish_time = EXCLUDED.publish_time,
                    evidence_time = EXCLUDED.evidence_time,
                    source_doc_uids = EXCLUDED.source_doc_uids,
                    source_tier = EXCLUDED.source_tier,
                    source_types = EXCLUDED.source_types,
                    provider_chain = EXCLUDED.provider_chain,
                    reliability_score = EXCLUDED.reliability_score,
                    cross_source_count = EXCLUDED.cross_source_count,
                    status = EXCLUDED.status,
                    reject_reason = EXCLUDED.reject_reason,
                    freshness_status = EXCLUDED.freshness_status,
                    event_anchor_id = EXCLUDED.event_anchor_id,
                    checksum = EXCLUDED.checksum,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                event_id,
                event_type,
                event_name,
                self._clean_context_text(payload.get("summary"), max_len=1000) or None,
                json.dumps(self._json_list(payload.get("entity_codes")), ensure_ascii=False, default=str),
                json.dumps(self._json_list(payload.get("theme_codes")), ensure_ascii=False, default=str),
                self._clean_context_text(payload.get("direction") or "neutral", max_len=40) or "neutral",
                self._clean_context_text(payload.get("event_time"), max_len=80) or None,
                self._clean_context_text(payload.get("publish_time"), max_len=80) or None,
                self._clean_context_text(payload.get("evidence_time"), max_len=80) or None,
                json.dumps(self._json_list(payload.get("source_doc_uids")), ensure_ascii=False, default=str),
                source_tier,
                json.dumps(self._json_list(payload.get("source_types")), ensure_ascii=False, default=str),
                json.dumps(self._json_list(payload.get("provider_chain")), ensure_ascii=False, default=str),
                float(reliability_score),
                int(payload.get("cross_source_count") or 0),
                status,
                self._clean_context_text(payload.get("reject_reason"), max_len=500) or None,
                self._clean_context_text(payload.get("freshness_status") or "unknown", max_len=80) or "unknown",
                self._clean_context_text(payload.get("event_anchor_id") or event_id, max_len=200) or event_id,
                checksum,
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_market_event_normalized(dict(row))

    async def list_market_events_normalized(
        self,
        *,
        status: str | None = None,
        source_tier: str | None = None,
        event_type: str | None = None,
        event_signature: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        idx = 1
        if status:
            conditions.append(f"status = ${idx}")
            params.append(str(status).strip())
            idx += 1
        if source_tier:
            conditions.append(f"source_tier = ${idx}")
            params.append(self._normalize_source_tier(source_tier))
            idx += 1
        if event_type:
            conditions.append(f"event_type = ${idx}")
            params.append(str(event_type).strip())
            idx += 1
        if event_signature:
            conditions.append(f"json_extract(metadata, '$.event_signature') = ${idx}")
            params.append(str(event_signature).strip())
            idx += 1
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(max(1, min(int(limit or 100), 1000)))
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT *
                FROM market_events_normalized
                {where}
                ORDER BY evidence_time DESC, reliability_score DESC, updated_at DESC
                LIMIT ${idx}
                """,
                *params,
            )
        return [self._decode_market_event_normalized(dict(row)) for row in rows]

    async def count_market_events_normalized(self) -> dict[str, Any]:
        async with self.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM market_events_normalized") or 0
            by_status = await conn.fetch(
                """
                SELECT status, COUNT(*) AS count
                FROM market_events_normalized
                GROUP BY status
                ORDER BY status
                """
            )
            by_tier = await conn.fetch(
                """
                SELECT source_tier, COUNT(*) AS count
                FROM market_events_normalized
                GROUP BY source_tier
                ORDER BY source_tier
                """
            )
        return {
            "total": int(total or 0),
            "by_status": {str(row.get("status") or ""): int(row.get("count") or 0) for row in by_status},
            "by_source_tier": {str(row.get("source_tier") or ""): int(row.get("count") or 0) for row in by_tier},
        }

    async def save_market_documents(
        self,
        stock_code: str,
        doc_type: str,
        items: Iterable[dict[str, Any]],
        *,
        embed: bool = True,
        chunk_size: int = 800,
        overlap: int = 120,
        collection_name: str = "market_doc_chunks",
        version: str = "v1",
    ) -> dict[str, Any]:
        code = str(stock_code or "").strip()
        normalized_doc_type = str(doc_type or "").strip().lower()
        documents = [dict(item) for item in list(items or []) if isinstance(item, dict)]
        if not code or not normalized_doc_type or not documents:
            return {
                "documents": 0,
                "chunks": 0,
                "embedded_chunks": 0,
                "collection_name": resolve_vector_collection_name(collection_name, normalized_doc_type),
                "vector_status": "skipped",
                "degraded": False,
                "quality_flags": [],
                "vector_error": None,
                "embedding_attempted": 0,
                "embedding_coverage": 0.0,
            }
        resolved_collection_name = resolve_vector_collection_name(collection_name, normalized_doc_type)

        inserted_docs = 0
        inserted_chunks = 0
        inserted_labels = 0
        chunk_rows: list[dict[str, Any]] = []
        headline_rows: list[dict[str, Any]] = []
        quality_flags: list[str] = []
        vector_error: Optional[str] = None
        async with self.acquire() as conn:
            async with conn.transaction():
                for item in documents:
                    title = self._pick_document_title(item)
                    summary = self._pick_document_summary(item)
                    body = self._pick_document_body(item)
                    if not body:
                        continue
                    doc_uid = self._build_market_doc_uid(code, normalized_doc_type, item)
                    source = self._pick_document_source(normalized_doc_type, item)
                    provider = self._pick_document_provider(item, source=source)
                    source_tier = self._normalize_source_tier(item.get("source_tier"), provider=provider, source=source)
                    url = self._pick_document_url(item)
                    author = self._clean_context_text(item.get("author") or item.get("analyst"), max_len=200)
                    published_date = self._coerce_context_date(item.get("published_at") or item.get("date") or item.get("time"))
                    published_at = datetime.combine(published_date, datetime.min.time()) if published_date else None
                    fetched_at = self._coerce_context_datetime(item.get("fetched_at")) or datetime.now(timezone.utc)
                    checksum = self._build_document_checksum(item, title=title, body=body, url=url, published_at=published_at)
                    reliability_score = self._coerce_context_float(item.get("reliability_score"))
                    if reliability_score is None:
                        reliability_score = self._default_reliability_score(source_tier)
                    crawl_status = self._clean_context_text(item.get("crawl_status") or "ok", max_len=80) or "ok"
                    original_id = self._pick_document_original_id(item)
                    doc_meta = {
                        "doc_type": normalized_doc_type,
                        "source": source,
                        "source_tier": source_tier,
                        "provider": provider,
                        "original_id": original_id,
                        "checksum": checksum,
                        "reliability_score": round(float(reliability_score), 4),
                        "crawl_status": crawl_status,
                        "raw_title": item.get("title") or item.get("headline") or item.get("name"),
                        "raw_date": item.get("date") or item.get("time"),
                    }
                    row = await conn.fetchrow(
                        """
                        INSERT INTO market_documents (
                            doc_uid, stock_code, doc_type, source, source_tier, provider, original_id,
                            title, summary, body, url, author, published_at, fetched_at, checksum,
                            reliability_score, crawl_status, metadata, created_at, updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7,
                                $8, $9, $10, $11, $12, $13, $14, $15,
                                $16, $17, $18, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (doc_uid) DO UPDATE SET
                            stock_code = EXCLUDED.stock_code,
                            doc_type = EXCLUDED.doc_type,
                            source = EXCLUDED.source,
                            source_tier = EXCLUDED.source_tier,
                            provider = EXCLUDED.provider,
                            original_id = EXCLUDED.original_id,
                            title = EXCLUDED.title,
                            summary = EXCLUDED.summary,
                            body = EXCLUDED.body,
                            url = EXCLUDED.url,
                            author = EXCLUDED.author,
                            published_at = EXCLUDED.published_at,
                            fetched_at = EXCLUDED.fetched_at,
                            checksum = EXCLUDED.checksum,
                            reliability_score = EXCLUDED.reliability_score,
                            crawl_status = EXCLUDED.crawl_status,
                            metadata = EXCLUDED.metadata,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id, doc_uid
                        """,
                        doc_uid,
                        code,
                        normalized_doc_type,
                        source,
                        source_tier,
                        provider or None,
                        original_id or None,
                        title or None,
                        summary or None,
                        body,
                        url or None,
                        author or None,
                        published_at,
                        fetched_at,
                        checksum,
                        float(reliability_score),
                        crawl_status,
                        json.dumps(doc_meta, ensure_ascii=False, default=str),
                    )
                    if row:
                        inserted_docs += 1
                    doc_id = dict(row or {}).get("id")
                    if doc_id is None:
                        continue
                    headline_rows.extend(
                        self._extract_headline_label_rows(
                            code,
                            normalized_doc_type,
                            item,
                            doc_id=doc_id,
                            doc_uid=doc_uid,
                            published_at=published_at,
                        )
                    )
                    for headline_row in headline_rows[-1:]:
                        headline_inserted = await conn.fetchval(
                            """
                            INSERT INTO market_headline_labels (
                                label_id, doc_id, doc_uid, stock_code, doc_type, published_at, headline, label,
                                event_type, direction, horizon_days, intensity, confidence, keywords, payload, created_at
                            )
                            VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8,
                                $9, $10, $11, $12, $13, $14, $15, CURRENT_TIMESTAMP
                            )
                            ON CONFLICT (label_id) DO UPDATE SET
                                doc_id = COALESCE(EXCLUDED.doc_id, market_headline_labels.doc_id),
                                published_at = COALESCE(EXCLUDED.published_at, market_headline_labels.published_at),
                                headline = COALESCE(EXCLUDED.headline, market_headline_labels.headline),
                                label = COALESCE(EXCLUDED.label, market_headline_labels.label),
                                event_type = COALESCE(EXCLUDED.event_type, market_headline_labels.event_type),
                                direction = COALESCE(EXCLUDED.direction, market_headline_labels.direction),
                                horizon_days = COALESCE(EXCLUDED.horizon_days, market_headline_labels.horizon_days),
                                intensity = COALESCE(EXCLUDED.intensity, market_headline_labels.intensity),
                                confidence = COALESCE(EXCLUDED.confidence, market_headline_labels.confidence),
                                keywords = COALESCE(EXCLUDED.keywords, market_headline_labels.keywords),
                                payload = COALESCE(EXCLUDED.payload, market_headline_labels.payload)
                            RETURNING 1
                            """,
                            headline_row.get("label_id"),
                            headline_row.get("doc_id"),
                            headline_row.get("doc_uid"),
                            headline_row.get("stock_code"),
                            headline_row.get("doc_type"),
                            headline_row.get("published_at"),
                            headline_row.get("headline"),
                            headline_row.get("label"),
                            headline_row.get("event_type"),
                            headline_row.get("direction"),
                            headline_row.get("horizon_days"),
                            headline_row.get("intensity"),
                            headline_row.get("confidence"),
                            json.dumps(headline_row.get("keywords") or [], ensure_ascii=False, default=str),
                            json.dumps(headline_row.get("payload") or {}, ensure_ascii=False, default=str),
                        )
                        if headline_inserted:
                            inserted_labels += 1
                    await conn.execute("DELETE FROM market_doc_chunks WHERE doc_id = $1", doc_id)
                    chunks = self._chunk_document_text(body, chunk_size=chunk_size, overlap=overlap)
                    for chunk_no, chunk_text in enumerate(chunks):
                        chunk_meta = {
                            "doc_uid": doc_uid,
                            "url": url,
                            "author": author,
                            "summary": summary[:280] if summary else "",
                            "source_tier": source_tier,
                            "provider": provider,
                            "checksum": checksum,
                            "reliability_score": round(float(reliability_score), 4),
                        }
                        chunk_row = await conn.fetchrow(
                            """
                            INSERT INTO market_doc_chunks (
                                doc_id, chunk_no, stock_code, doc_type, source, title, chunk_text,
                                token_count, char_count, language, published_at, metadata, created_at, updated_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'zh', $10, $11, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            RETURNING id
                            """,
                            doc_id,
                            int(chunk_no),
                            code,
                            normalized_doc_type,
                            source,
                            title or None,
                            chunk_text,
                            self._count_text_tokens(chunk_text),
                            len(chunk_text),
                            published_at,
                            json.dumps(chunk_meta, ensure_ascii=False, default=str),
                        )
                        if chunk_row:
                            inserted_chunks += 1
                        chunk_rows.append(
                            {
                                "doc_id": doc_id,
                                "doc_uid": doc_uid,
                                "chunk_id": dict(chunk_row or {}).get("id"),
                                "chunk_no": int(chunk_no),
                                "stock_code": code,
                                "doc_type": normalized_doc_type,
                                "source": source,
                                "source_tier": source_tier,
                                "provider": provider,
                                "title": title,
                                "chunk_text": chunk_text,
                                "published_at": published_at,
                                "url": url,
                                "author": author,
                                "summary": summary,
                            }
                        )

        embedded_chunks = 0
        embedding_attempted = 0
        vector_status = "disabled" if not embed else "not_requested"
        degraded = False
        profile_version_counts: dict[str, int] = {}
        vector_dims: set[int] = set()
        if embed and chunk_rows and hasattr(self, "save_vector_profile"):
            try:
                from aiask_quant_core.storage.runtime_hooks import get_text_embedding_service_factory

                service_factory = get_text_embedding_service_factory()
                service = service_factory() if callable(service_factory) else None
                if service is not None and service.is_enabled():
                    vector_status = "running"
                    profile_type = normalized_doc_type
                    ensured_index_keys: set[tuple[str, int]] = set()
                    existing_collection = None
                    if hasattr(self, "get_vector_collection"):
                        try:
                            existing_collection = await self.get_vector_collection(resolved_collection_name)
                        except Exception:
                            existing_collection = None
                    for chunk in chunk_rows:
                        embedding_attempted += 1
                        if hasattr(service, "embed_text_with_info"):
                            embedding_result = await service.embed_text_with_info(str(chunk.get("chunk_text") or ""))
                            vector = list(dict(embedding_result or {}).get("embedding") or [])
                            embedding_provider = str(dict(embedding_result or {}).get("provider") or "")
                            requested_provider = str(dict(embedding_result or {}).get("requested_provider") or "")
                            fallback_used = bool(dict(embedding_result or {}).get("fallback_used"))
                            fallback_error = dict(embedding_result or {}).get("fallback_error")
                        else:
                            vector = await service.embed_text(str(chunk.get("chunk_text") or ""))
                            embedding_provider = ""
                            requested_provider = ""
                            fallback_used = False
                            fallback_error = None
                        if not vector:
                            degraded = True
                            if "empty_embedding" not in quality_flags:
                                quality_flags.append("empty_embedding")
                            continue
                        model_id = str(getattr(getattr(service, "config", None), "model", None) or "text-embedding-3-small")
                        vector_dim = len(vector)
                        vector_dims.add(int(vector_dim))
                        profile_version = resolve_dimension_scoped_version(version, vector_dim)
                        profile_version_counts[profile_version] = int(profile_version_counts.get(profile_version) or 0) + 1
                        collection_vector_dim = int(existing_collection.get("vector_dim") or 0) if isinstance(existing_collection, dict) else 0
                        collection_vector_dim = max(collection_vector_dim, int(vector_dim or 0))
                        await self.save_vector_collection(
                            {
                                "collection_name": resolved_collection_name,
                                "entity_family": "document_chunk",
                                "backend": self.get_vector_backend(),
                                "metric": "cosine",
                                "model_id": model_id,
                                "vector_dim": collection_vector_dim or vector_dim,
                                "normalization": "unit",
                                "status": "active",
                                "metadata": {
                                    "domain": "market",
                                    "doc_type": normalized_doc_type,
                                    "base_version": str(version or "v1"),
                                    "active_profile_versions": sorted(profile_version_counts.keys()),
                                },
                            }
                        )
                        existing_collection = {
                            **dict(existing_collection or {}),
                            "vector_dim": collection_vector_dim or vector_dim,
                            "model_id": model_id,
                        }
                        entity_id = f"{chunk.get('doc_uid')}:{chunk.get('chunk_no')}"
                        await self.save_vector_profile(
                            {
                                "collection_name": resolved_collection_name,
                                "entity_type": "market_doc_chunk",
                                "entity_id": entity_id,
                                "stock_code": chunk.get("stock_code"),
                                "profile_type": profile_type,
                                "model_id": model_id,
                                "vector_dim": vector_dim,
                                "metric": "cosine",
                                "version": profile_version,
                                "signature": hashlib.sha1(
                                    f"{entity_id}|{model_id}|{chunk.get('chunk_text')}".encode("utf-8")
                                ).hexdigest(),
                                "embedding": vector,
                                "metadata": {
                                    "doc_id": chunk.get("doc_id"),
                                    "chunk_id": chunk.get("chunk_id"),
                                    "chunk_no": chunk.get("chunk_no"),
                                    "doc_uid": chunk.get("doc_uid"),
                                    "doc_type": chunk.get("doc_type"),
                                    "source": chunk.get("source"),
                                    "source_tier": chunk.get("source_tier"),
                                    "provider": chunk.get("provider"),
                                    "title": chunk.get("title"),
                                    "published_at": chunk.get("published_at").isoformat() if isinstance(chunk.get("published_at"), datetime) else None,
                                    "url": chunk.get("url"),
                                    "author": chunk.get("author"),
                                    "base_version": str(version or "v1"),
                                    "profile_version": profile_version,
                                    "embedding_provider": embedding_provider or None,
                                    "requested_embedding_provider": requested_provider or None,
                                    "embedding_fallback_used": fallback_used,
                                    "embedding_fallback_error": fallback_error,
                                },
                            }
                        )
                        embedded_chunks += 1
                        index_key = (profile_version, int(vector_dim or 0))
                        if index_key not in ensured_index_keys and hasattr(self, "ensure_vector_profile_sqlite_python_index"):
                            await self.ensure_vector_profile_sqlite_python_index(
                                collection_name=resolved_collection_name,
                                version=profile_version,
                                vector_dim=vector_dim,
                                profile_type=profile_type,
                                metric="cosine",
                            )
                            ensured_index_keys.add(index_key)
                        if fallback_used:
                            degraded = True
                            if "embedding_provider_fallback_used" not in quality_flags:
                                quality_flags.append("embedding_provider_fallback_used")
                    if embedded_chunks >= len(chunk_rows):
                        vector_status = "ready"
                    else:
                        degraded = True
                        vector_status = "degraded"
                        if "partial_embedding_coverage" not in quality_flags:
                            quality_flags.append("partial_embedding_coverage")
                else:
                    degraded = True
                    vector_status = "degraded"
                    if "embedding_service_disabled" not in quality_flags:
                        quality_flags.append("embedding_service_disabled")
            except Exception as exc:
                degraded = True
                vector_status = "degraded"
                vector_error = f"{type(exc).__name__}: {exc}"
                if "vector_generation_failed" not in quality_flags:
                    quality_flags.append("vector_generation_failed")

        return {
            "documents": inserted_docs,
            "chunks": inserted_chunks,
            "embedded_chunks": embedded_chunks,
            "headline_labels": inserted_labels,
            "collection_name": resolved_collection_name,
            "vector_status": vector_status,
            "degraded": degraded,
            "quality_flags": quality_flags,
            "vector_error": vector_error,
            "embedding_attempted": embedding_attempted,
            "embedding_coverage": round(float(embedded_chunks) / float(max(len(chunk_rows), 1)), 6) if chunk_rows else 0.0,
            "profile_versions": sorted(profile_version_counts.keys()),
            "profile_version_counts": profile_version_counts,
            "vector_dims": sorted(vector_dims),
        }

    async def save_vector_documents(self, stock_code: str, doc_type: str, items: Iterable[dict[str, Any]]) -> int:
        # DEPRECATED: writes to the legacy `vector_documents` table.
        # Migrate callers to save_market_documents (unified vector schema).
        # See docs/data/vector-legacy-deprecation-plan.md — write path
        # scheduled to be removed by 2026-08-01.
        logger.warning(
            "[deprecation] save_vector_documents writing to legacy vector_documents "
            "table; migrate to market_documents by 2026-08-01 "
            "(see docs/data/vector-legacy-deprecation-plan.md)"
        )
        code = str(stock_code or "").strip()
        normalized_doc_type = str(doc_type or "").strip().lower()
        raw_items = [dict(item) for item in list(items or []) if isinstance(item, dict)]
        rows = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            content = self._pick_document_content(item)
            if not content:
                continue
            rows.append(
                (
                    code,
                    normalized_doc_type,
                    content,
                    self._coerce_context_date(item.get("date") or item.get("time")),
                )
            )

        if not code or not normalized_doc_type or not rows:
            return 0

        inserted = 0
        async with self.acquire() as conn:
            for row in rows:
                result = await conn.fetchval(
                    """
                    INSERT INTO vector_documents (stock_code, doc_type, content, date, created_at)
                    SELECT $1, $2, $3, $4, CURRENT_TIMESTAMP
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM vector_documents
                        WHERE stock_code = $1
                          AND doc_type = $2
                          AND content = $3
                          AND COALESCE(date, '1970-01-01') = COALESCE($4, '1970-01-01')
                    )
                    RETURNING 1
                    """,
                    *row,
                )
                if result:
                    inserted += 1
        if raw_items:
            try:
                await self.save_market_documents(code, normalized_doc_type, raw_items)
            except Exception as exc:
                # Best-effort double-write to market_documents — failure here
                # leaves the legacy table populated but the unified store
                # behind. Log loudly instead of silently swallowing so the
                # gap is visible to monitoring; the original transaction
                # for the legacy table has already committed.
                logger.warning(
                    "market_context: save_market_documents fallback failed for "
                    "code=%s doc_type=%s items=%d: %s",
                    code, normalized_doc_type, len(raw_items), exc, exc_info=True,
                )
        return inserted

    async def save_research_reports(self, stock_code: str, reports: Iterable[dict[str, Any]]) -> int:
        code = str(stock_code or "").strip()
        rows = []
        for item in list(reports or []):
            if not isinstance(item, dict):
                continue
            title = self._clean_context_text(item.get("title"), max_len=500)
            institution = self._clean_context_text(item.get("institution"), max_len=200)
            publish_date = self._coerce_context_date(item.get("date") or item.get("publish_date"))
            summary = self._clean_context_text(item.get("summary") or item.get("content") or item.get("text"))
            if not title and not summary:
                continue
            rows.append(
                (
                    code,
                    title,
                    self._clean_context_text(item.get("rating"), max_len=120),
                    self._coerce_context_float(item.get("targetPrice") or item.get("target_price")),
                    institution,
                    self._clean_context_text(item.get("author") or item.get("analyst"), max_len=200),
                    publish_date,
                    summary,
                    self._clean_context_text(item.get("url") or item.get("pdf_url"), max_len=1000),
                )
            )

        if not code or not rows:
            return 0

        inserted = 0
        async with self.acquire() as conn:
            for row in rows:
                result = await conn.fetchval(
                    """
                    INSERT INTO research_reports (
                        code, title, rating, target_price, institution, analyst, publish_date, summary, pdf_url, created_at
                    )
                    SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM research_reports
                        WHERE code = $1
                          AND COALESCE(title, '') = COALESCE($2, '')
                          AND COALESCE(institution, '') = COALESCE($5, '')
                          AND COALESCE(publish_date, '1970-01-01') = COALESCE($7, '1970-01-01')
                    )
                    RETURNING 1
                    """,
                    *row,
                )
                if result:
                    inserted += 1
        return inserted

    async def save_stock_fund_flow(
        self,
        stock_code: str,
        payload: dict[str, Any],
        *,
        trade_date: Any = None,
    ) -> int:
        code = str(stock_code or payload.get("code") or "").strip()
        if not code or not isinstance(payload, dict):
            return 0

        resolved_trade_date = self._coerce_context_date(trade_date or payload.get("tradeDate") or payload.get("trade_date")) or date.today()
        row = (
            code,
            resolved_trade_date,
            self._clean_context_text(payload.get("name"), max_len=200),
            self._coerce_context_float(payload.get("mainNetInflow") or payload.get("main_net_inflow") or payload.get("net_inflow")),
            self._coerce_context_float(payload.get("mainInflowPercent") or payload.get("main_inflow_percent")),
            self._coerce_context_float(payload.get("superLargeNetInflow") or payload.get("super_large_net_inflow")),
            self._coerce_context_float(payload.get("largeNetInflow") or payload.get("large_net_inflow")),
            self._coerce_context_float(payload.get("middleNetInflow") or payload.get("middle_net_inflow")),
            self._coerce_context_float(payload.get("smallNetInflow") or payload.get("small_net_inflow") or payload.get("retail_net_inflow")),
            self._clean_context_text(payload.get("source"), max_len=120),
        )

        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stock_fund_flow (
                    code, trade_date, name, main_net_inflow, main_inflow_percent,
                    super_large_net_inflow, large_net_inflow, middle_net_inflow,
                    small_net_inflow, source, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, CURRENT_TIMESTAMP)
                ON CONFLICT (code, trade_date) DO UPDATE SET
                    name = EXCLUDED.name,
                    main_net_inflow = EXCLUDED.main_net_inflow,
                    main_inflow_percent = EXCLUDED.main_inflow_percent,
                    super_large_net_inflow = EXCLUDED.super_large_net_inflow,
                    large_net_inflow = EXCLUDED.large_net_inflow,
                    middle_net_inflow = EXCLUDED.middle_net_inflow,
                    small_net_inflow = EXCLUDED.small_net_inflow,
                    source = EXCLUDED.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                *row,
            )
        return 1
