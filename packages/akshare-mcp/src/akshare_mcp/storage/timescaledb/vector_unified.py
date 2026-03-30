"""Unified vector storage mixin for market / quant / strategy derived objects."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any, Iterable, List, Optional


class VectorUnifiedMixin:
    """Generic vector archive / pgvector store / ANN governance helpers."""

    @staticmethod
    def _normalize_hybrid_query_text(value: Any) -> str:
        return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())

    @classmethod
    def _hybrid_query_terms(cls, value: Any) -> List[str]:
        text = cls._normalize_hybrid_query_text(value)
        if not text:
            return []
        split_terms = [
            item.strip()
            for item in re.split(r"[\s,;|/，。；、：:（）()\[\]【】]+", text)
            if item and item.strip()
        ]
        terms: list[str] = []
        seen: set[str] = set()
        for item in [text, *split_terms]:
            token = str(item or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            terms.append(token)
        if len(split_terms) <= 1 and len(text) >= 4:
            for width in (2, 3):
                if len(text) <= width:
                    continue
                for idx in range(len(text) - width + 1):
                    token = text[idx: idx + width].strip()
                    if len(token) < width or token in seen:
                        continue
                    seen.add(token)
                    terms.append(token)
                    if len(terms) >= 12:
                        return terms
        return terms[:12]

    @classmethod
    def _hybrid_lexical_score(cls, query_text: str, title: str, content: str) -> float:
        normalized_query = cls._normalize_hybrid_query_text(query_text)
        if not normalized_query:
            return 0.0
        haystack = cls._normalize_hybrid_query_text(f"{title or ''} {content or ''}").lower()
        title_text = cls._normalize_hybrid_query_text(title).lower()
        if not haystack:
            return 0.0
        normalized_query = normalized_query.lower()
        terms = [item.lower() for item in cls._hybrid_query_terms(normalized_query)]
        if not terms:
            return 0.0
        full_match = 1.0 if normalized_query in haystack else 0.0
        matched_terms = sum(1 for term in terms if term in haystack)
        matched_title_terms = sum(1 for term in terms if term in title_text)
        term_score = matched_terms / max(len(terms), 1)
        title_bonus = matched_title_terms / max(len(terms), 1)
        score = 0.6 * full_match + 0.3 * term_score + 0.1 * title_bonus
        return round(max(0.0, min(score, 1.0)), 6)

    @staticmethod
    def _hybrid_dense_score(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            return None
        return round(max(0.0, min(resolved, 1.0)), 6)

    @classmethod
    def _hybrid_score(
        cls,
        *,
        dense_score: Optional[float],
        lexical_score: Optional[float],
    ) -> Optional[float]:
        has_dense = dense_score is not None
        has_lexical = lexical_score is not None
        if not has_dense and not has_lexical:
            return None
        if has_dense and has_lexical:
            return round((float(dense_score) * 0.65) + (float(lexical_score) * 0.35), 6)
        if has_dense:
            return round(float(dense_score), 6)
        return round(float(lexical_score or 0.0), 6)

    def _decode_vector_collection(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    def _decode_unified_vector_profile(self, row: dict) -> dict:
        result = dict(row)
        result["embedding"] = self._decode_json_field(result.get("embedding_json"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    def _decode_unified_vector_snapshot(self, row: dict) -> dict:
        result = dict(row)
        result["index_params"] = self._decode_json_field(result.get("index_params"), {})
        result["metrics"] = self._decode_json_field(result.get("metrics"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    def _decode_unified_vector_item(self, row: dict) -> dict:
        result = dict(row)
        result["embedding"] = self._decode_json_field(result.get("embedding_json"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    def _decode_kline_pattern_window(self, row: dict) -> dict:
        result = dict(row)
        result["payload"] = self._decode_json_field(result.get("payload"), {})
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    @staticmethod
    def _vector_similarity(left: List[float], right: List[float], metric: str = "cosine") -> float:
        lv = [float(item) for item in list(left or [])]
        rv = [float(item) for item in list(right or [])]
        if not lv or not rv or len(lv) != len(rv):
            return 0.0
        normalized_metric = str(metric or "cosine").strip().lower()
        if normalized_metric in {"ip", "inner_product"}:
            return round(float(sum(l * r for l, r in zip(lv, rv))), 6)
        if normalized_metric in {"l2", "euclidean"}:
            distance = math.sqrt(sum((l - r) * (l - r) for l, r in zip(lv, rv)))
            return round(1.0 / (1.0 + float(distance)), 6)
        left_norm = math.sqrt(sum(item * item for item in lv))
        right_norm = math.sqrt(sum(item * item for item in rv))
        if left_norm <= 1e-12 or right_norm <= 1e-12:
            return 0.0
        return round(float(sum(l * r for l, r in zip(lv, rv)) / (left_norm * right_norm)), 6)

    @staticmethod
    def _normalize_embedding(values: Any) -> List[float]:
        resolved = [float(item) for item in list(values or [])]
        if not resolved:
            return []
        norm = math.sqrt(sum(item * item for item in resolved))
        if norm <= 1e-12:
            return []
        return [float(item / norm) for item in resolved]

    @staticmethod
    def _coerce_date_value(value: Any) -> Optional[date]:
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
    def _snapshot_bucket_rows(snapshot: Optional[dict]) -> List[dict]:
        metadata = dict((snapshot or {}).get("metadata") or {})
        return [dict(item or {}) for item in list(metadata.get("centroids") or []) if dict(item or {}).get("bucket_id")]

    @classmethod
    def _resolve_query_buckets(
        cls,
        snapshot: Optional[dict],
        query_embedding: List[float],
    ) -> tuple[Optional[str], List[str]]:
        bucket_rows = cls._snapshot_bucket_rows(snapshot)
        normalized_query = cls._normalize_embedding(query_embedding)
        if not bucket_rows or not normalized_query:
            return None, []
        index_params = dict((snapshot or {}).get("index_params") or {})
        neighbor_count = max(0, min(int(index_params.get("neighbor_count") or 2), 8))
        scored: list[tuple[str, float, list[str]]] = []
        for row in bucket_rows:
            bucket_id = str(row.get("bucket_id") or "").strip()
            centroid = cls._normalize_embedding(row.get("centroid") or [])
            if not bucket_id or not centroid or len(centroid) != len(normalized_query):
                continue
            scored.append(
                (
                    bucket_id,
                    cls._vector_similarity(normalized_query, centroid, metric="cosine"),
                    [str(item).strip() for item in list(row.get("neighbors") or []) if str(item).strip()],
                )
            )
        if not scored:
            return None, []
        scored.sort(key=lambda item: item[1], reverse=True)
        primary_bucket = scored[0][0]
        candidate_buckets = [primary_bucket]
        for neighbor in scored[0][2][:neighbor_count]:
            if neighbor not in candidate_buckets:
                candidate_buckets.append(neighbor)
        return primary_bucket, candidate_buckets

    @staticmethod
    def _kline_pattern_profile_type(
        *,
        window_size: int,
        vector_method: str,
        period: str = "daily",
        adjust: str = "",
    ) -> str:
        return "|".join(
            [
                str(vector_method or "returns").strip().lower(),
                str(period or "daily").strip().lower(),
                str(adjust or "").strip().lower(),
                str(int(window_size or 0)),
            ]
        )

    async def save_vector_collection(self, payload: dict) -> dict:
        item = dict(payload or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO vector_collections (
                    collection_name, entity_family, backend, metric, model_id, vector_dim,
                    normalization, status, active_version, metadata, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, NOW(), NOW())
                ON CONFLICT (collection_name) DO UPDATE SET
                    entity_family = EXCLUDED.entity_family,
                    backend = EXCLUDED.backend,
                    metric = EXCLUDED.metric,
                    model_id = EXCLUDED.model_id,
                    vector_dim = EXCLUDED.vector_dim,
                    normalization = EXCLUDED.normalization,
                    status = EXCLUDED.status,
                    active_version = COALESCE(EXCLUDED.active_version, vector_collections.active_version),
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                str(item.get("collection_name") or ""),
                str(item.get("entity_family") or "generic"),
                str(item.get("backend") or self.get_vector_backend()),
                str(item.get("metric") or "cosine"),
                str(item.get("model_id") or "unknown"),
                int(item.get("vector_dim") or 0),
                str(item.get("normalization") or "unit"),
                str(item.get("status") or "active"),
                item.get("active_version"),
                json.dumps(item.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_vector_collection(dict(row))

    async def get_vector_collection(self, collection_name: str) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM vector_collections WHERE collection_name = $1",
                str(collection_name or ""),
            )
        return self._decode_vector_collection(dict(row)) if row else None

    async def list_vector_collections(
        self,
        *,
        entity_family: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM vector_collections WHERE 1=1"
            params: list[Any] = []
            idx = 1
            if entity_family:
                sql += f" AND entity_family = ${idx}"
                params.append(entity_family)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY collection_name LIMIT ${idx}"
            params.append(max(1, min(int(limit or 100), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_vector_collection(dict(row)) for row in rows]

    async def save_vector_profile(self, profile: dict) -> dict:
        payload = dict(profile or {})
        embedding = payload.get("embedding") or []
        metadata = dict(payload.get("metadata") or {})
        collection_name = str(payload.get("collection_name") or "")
        if not collection_name:
            raise ValueError("collection_name is required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO vector_profiles (
                    collection_name, entity_type, entity_id, stock_code, profile_type, model_id,
                    vector_dim, metric, version, signature, status, embedding_json, metadata, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb, NOW(), NOW())
                ON CONFLICT (collection_name, entity_type, entity_id, model_id, version) DO UPDATE SET
                    stock_code = EXCLUDED.stock_code,
                    profile_type = EXCLUDED.profile_type,
                    vector_dim = EXCLUDED.vector_dim,
                    metric = EXCLUDED.metric,
                    signature = EXCLUDED.signature,
                    status = EXCLUDED.status,
                    embedding_json = EXCLUDED.embedding_json,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                collection_name,
                str(payload.get("entity_type") or "generic"),
                str(payload.get("entity_id") or ""),
                payload.get("stock_code"),
                payload.get("profile_type"),
                str(payload.get("model_id") or "unknown"),
                int(payload.get("vector_dim") or len(embedding)),
                str(payload.get("metric") or "cosine"),
                str(payload.get("version") or "v1"),
                payload.get("signature"),
                str(payload.get("status") or "active"),
                json.dumps(embedding, ensure_ascii=False, default=str),
                json.dumps(metadata, ensure_ascii=False, default=str),
            )
            if getattr(self, "supports_pgvector", lambda: False)():
                vector_literal = self._encode_pgvector(embedding)
                if vector_literal:
                    await conn.execute(
                        """
                        INSERT INTO vector_profile_store (
                            profile_id, collection_name, entity_type, entity_id, stock_code, profile_type, model_id,
                            vector_dim, metric, version, embedding, metadata, updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::vector, $12::jsonb, NOW())
                        ON CONFLICT (profile_id) DO UPDATE SET
                            collection_name = EXCLUDED.collection_name,
                            entity_type = EXCLUDED.entity_type,
                            entity_id = EXCLUDED.entity_id,
                            stock_code = EXCLUDED.stock_code,
                            profile_type = EXCLUDED.profile_type,
                            model_id = EXCLUDED.model_id,
                            vector_dim = EXCLUDED.vector_dim,
                            metric = EXCLUDED.metric,
                            version = EXCLUDED.version,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                        """,
                        dict(row).get("id"),
                        collection_name,
                        str(payload.get("entity_type") or "generic"),
                        str(payload.get("entity_id") or ""),
                        payload.get("stock_code"),
                        payload.get("profile_type"),
                        str(payload.get("model_id") or "unknown"),
                        int(payload.get("vector_dim") or len(embedding)),
                        str(payload.get("metric") or "cosine"),
                        str(payload.get("version") or "v1"),
                        vector_literal,
                        json.dumps(metadata, ensure_ascii=False, default=str),
                    )
        return self._decode_unified_vector_profile(dict(row))

    async def list_vector_profiles(
        self,
        *,
        collection_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        stock_code: Optional[str] = None,
        profile_type: Optional[str] = None,
        version: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM vector_profiles WHERE 1=1"
            params: list[Any] = []
            idx = 1
            for field, value in (
                ("collection_name", collection_name),
                ("entity_type", entity_type),
                ("entity_id", entity_id),
                ("stock_code", stock_code),
                ("profile_type", profile_type),
                ("version", version),
            ):
                if value:
                    sql += f" AND {field} = ${idx}"
                    params.append(value)
                    idx += 1
            sql += f" ORDER BY updated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 100), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_unified_vector_profile(dict(row)) for row in rows]

    async def search_vector_collection(
        self,
        *,
        collection_name: str,
        query_embedding: List[float],
        index_version: Optional[str] = None,
        version: Optional[str] = None,
        profile_type: Optional[str] = None,
        stock_code: Optional[str] = None,
        stock_codes: Optional[List[str]] = None,
        entity_id: Optional[str] = None,
        entity_ids: Optional[List[str]] = None,
        exclude_stock_code: Optional[str] = None,
        exclude_entity_id: Optional[str] = None,
        limit: int = 20,
        metric: str = "cosine",
    ) -> dict:
        resolved_collection = str(collection_name or "").strip()
        resolved_limit = max(1, min(int(limit or 20), 500))
        resolved_query_embedding = [float(item) for item in list(query_embedding or [])]
        if not resolved_collection or not resolved_query_embedding:
            return {
                "items": [],
                "collection_name": resolved_collection,
                "backend_used": "unavailable",
                "fallback_used": False,
                "fallback_reason": "empty_query",
                "active_version": None,
                "index_version": index_version,
                "profile_version": version,
            }

        collection = await self.get_vector_collection(resolved_collection)
        active_version = str((collection or {}).get("active_version") or "").strip() or None
        resolved_index_version = str(index_version or active_version or "").strip() or None
        snapshot = None
        resolved_profile_version = str(version or "").strip() or None
        if resolved_index_version:
            snapshots = await self.list_vector_index_snapshots(
                collection_name=resolved_collection,
                index_version=resolved_index_version,
                latest_only=True,
                limit=1,
            )
            snapshot = snapshots[0] if snapshots else None
            if snapshot and not resolved_profile_version:
                resolved_profile_version = (
                    str((snapshot.get("metadata") or {}).get("profile_version") or "").strip()
                    or str(snapshot.get("index_version") or "").strip()
                    or None
                )
        if not resolved_profile_version and resolved_index_version:
            resolved_profile_version = resolved_index_version

        resolved_entity_ids = [str(item).strip() for item in ([entity_id] if entity_id else list(entity_ids or [])) if str(item).strip()]
        allowed_stock_codes = {str(item).strip() for item in list(stock_codes or []) if str(item).strip()}
        allowed_entity_ids = set(resolved_entity_ids)
        if entity_id:
            allowed_entity_ids.add(str(entity_id).strip())
        query_bucket_id, candidate_bucket_ids = self._resolve_query_buckets(snapshot, resolved_query_embedding)

        ann_fallback_reason = None
        if resolved_index_version:
            try:
                index_rows = await self.search_vector_index_items_by_embedding(
                    query_embedding=resolved_query_embedding,
                    collection_name=resolved_collection,
                    index_version=resolved_index_version,
                    profile_type=profile_type,
                    stock_code=stock_code,
                    stock_codes=stock_codes,
                    entity_ids=resolved_entity_ids or None,
                    bucket_ids=candidate_bucket_ids or None,
                    exclude_stock_code=exclude_stock_code,
                    exclude_entity_id=exclude_entity_id,
                    limit=resolved_limit,
                    metric=metric,
                )
                if index_rows:
                    return {
                        "items": index_rows[:resolved_limit],
                        "collection_name": resolved_collection,
                        "backend_used": "pgvector_index_item",
                        "fallback_used": False,
                        "fallback_reason": None,
                        "active_version": active_version,
                        "index_version": resolved_index_version or resolved_profile_version,
                        "profile_version": resolved_profile_version,
                        "snapshot": snapshot,
                        "query_bucket_id": query_bucket_id,
                        "candidate_bucket_ids": candidate_bucket_ids,
                    }
                ann_fallback_reason = "index_item_empty_result"
            except Exception as exc:
                ann_fallback_reason = f"index_item_exception:{type(exc).__name__}"

        profile_fallback_reason = None
        try:
            dense_rows = await self.search_vector_profiles_by_embedding(
                query_embedding=resolved_query_embedding,
                collection_name=resolved_collection,
                version=resolved_profile_version,
                profile_type=profile_type,
                stock_code=stock_code,
                stock_codes=stock_codes,
                entity_ids=resolved_entity_ids or None,
                exclude_stock_code=exclude_stock_code,
                exclude_entity_id=exclude_entity_id,
                limit=resolved_limit,
                metric=metric,
            )
            if dense_rows:
                return {
                    "items": dense_rows[:resolved_limit],
                    "collection_name": resolved_collection,
                    "backend_used": "pgvector_profile",
                    "fallback_used": bool(ann_fallback_reason),
                    "fallback_reason": ann_fallback_reason,
                    "active_version": active_version,
                    "index_version": resolved_index_version or resolved_profile_version,
                    "profile_version": resolved_profile_version,
                    "snapshot": snapshot,
                    "query_bucket_id": query_bucket_id,
                    "candidate_bucket_ids": candidate_bucket_ids,
                }
            profile_fallback_reason = "pgvector_empty_result"
        except Exception as exc:
            profile_fallback_reason = f"pgvector_exception:{type(exc).__name__}"

        exact_rows: list[dict] = []
        if resolved_index_version:
            try:
                index_items = await self.list_vector_index_items(
                    collection_name=resolved_collection,
                    index_version=resolved_index_version,
                    bucket_ids=candidate_bucket_ids or None,
                    profile_type=profile_type,
                    stock_code=stock_code,
                    stock_codes=stock_codes,
                    entity_ids=resolved_entity_ids or None,
                    exclude_stock_code=exclude_stock_code,
                    exclude_entity_id=exclude_entity_id,
                    limit=max(100, min(resolved_limit * 20, 5000)),
                )
                for row in index_items:
                    candidate_stock_code = str(row.get("stock_code") or "").strip()
                    candidate_entity_id = str(row.get("entity_id") or "").strip()
                    if allowed_stock_codes and candidate_stock_code not in allowed_stock_codes:
                        continue
                    if allowed_entity_ids and candidate_entity_id not in allowed_entity_ids:
                        continue
                    if exclude_stock_code and candidate_stock_code == str(exclude_stock_code).strip():
                        continue
                    if exclude_entity_id and candidate_entity_id == str(exclude_entity_id).strip():
                        continue
                    exact_rows.append(
                        {
                            **row,
                            "similarity": self._vector_similarity(
                                resolved_query_embedding,
                                list(row.get("embedding") or []),
                                metric=metric,
                            ),
                        }
                    )
            except Exception:
                exact_rows = []

        if not exact_rows:
            rows = await self.list_vector_profiles(
                collection_name=resolved_collection,
                entity_type=None,
                entity_id=None,
                stock_code=stock_code,
                profile_type=profile_type,
                version=resolved_profile_version,
                limit=max(100, min(resolved_limit * 20, 5000)),
            )
            for row in rows:
                candidate_stock_code = str(row.get("stock_code") or "").strip()
                candidate_entity_id = str(row.get("entity_id") or "").strip()
                if allowed_stock_codes and candidate_stock_code not in allowed_stock_codes:
                    continue
                if allowed_entity_ids and candidate_entity_id not in allowed_entity_ids:
                    continue
                if exclude_stock_code and candidate_stock_code == str(exclude_stock_code).strip():
                    continue
                if exclude_entity_id and candidate_entity_id == str(exclude_entity_id).strip():
                    continue
                exact_rows.append(
                    {
                        **row,
                        "similarity": self._vector_similarity(
                            resolved_query_embedding,
                            list(row.get("embedding") or []),
                            metric=metric,
                        ),
                    }
                )

        exact_rows.sort(key=lambda item: float(item.get("similarity") or 0.0), reverse=True)
        return {
            "items": exact_rows[:resolved_limit],
            "collection_name": resolved_collection,
            "backend_used": "exact_json",
            "fallback_used": True,
            "fallback_reason": ann_fallback_reason or profile_fallback_reason or "pgvector_unavailable",
            "active_version": active_version,
            "index_version": resolved_index_version or resolved_profile_version,
            "profile_version": resolved_profile_version,
            "snapshot": snapshot,
            "query_bucket_id": query_bucket_id,
            "candidate_bucket_ids": candidate_bucket_ids,
        }

    async def save_vector_index_snapshot(self, snapshot: dict) -> dict:
        payload = dict(snapshot or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO vector_index_snapshots (
                    collection_name, index_version, status, model_id, profile_type, metric, vector_dim,
                    sample_count, bucket_count, index_params, metrics, metadata, built_at, activated_at, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12::jsonb, $13::timestamptz, $14::timestamptz, NOW())
                ON CONFLICT (collection_name, index_version) DO UPDATE SET
                    status = EXCLUDED.status,
                    model_id = EXCLUDED.model_id,
                    profile_type = EXCLUDED.profile_type,
                    metric = EXCLUDED.metric,
                    vector_dim = EXCLUDED.vector_dim,
                    sample_count = EXCLUDED.sample_count,
                    bucket_count = EXCLUDED.bucket_count,
                    index_params = EXCLUDED.index_params,
                    metrics = EXCLUDED.metrics,
                    metadata = EXCLUDED.metadata,
                    built_at = EXCLUDED.built_at,
                    activated_at = EXCLUDED.activated_at
                RETURNING *
                """,
                str(payload.get("collection_name") or ""),
                str(payload.get("index_version") or "v1"),
                str(payload.get("status") or "building"),
                str(payload.get("model_id") or "unknown"),
                payload.get("profile_type"),
                str(payload.get("metric") or "cosine"),
                int(payload.get("vector_dim") or 0),
                int(payload.get("sample_count") or 0),
                int(payload.get("bucket_count") or 0),
                json.dumps(payload.get("index_params") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metrics") or {}, ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                self._coerce_timestamp(payload.get("built_at")),
                self._coerce_timestamp(payload.get("activated_at")),
            )
            if payload.get("activated_at"):
                await conn.execute(
                    """
                    UPDATE vector_collections
                    SET active_version = $2,
                        updated_at = NOW()
                    WHERE collection_name = $1
                    """,
                    str(payload.get("collection_name") or ""),
                    str(payload.get("index_version") or "v1"),
                )
        return self._decode_unified_vector_snapshot(dict(row))

    async def save_kline_pattern_window(self, payload: dict) -> dict:
        item = dict(payload or {})
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO kline_pattern_windows (
                    window_uid, stock_code, end_date, start_date, period, adjust,
                    window_size, vector_method, metric, vector_dim,
                    forward_return_5d, forward_return_10d, forward_return_20d,
                    payload, metadata, created_at, updated_at
                )
                VALUES (
                    $1, $2, $3::date, $4::date, $5, $6,
                    $7, $8, $9, $10,
                    $11, $12, $13,
                    $14::jsonb, $15::jsonb, NOW(), NOW()
                )
                ON CONFLICT (window_uid) DO UPDATE SET
                    stock_code = EXCLUDED.stock_code,
                    end_date = EXCLUDED.end_date,
                    start_date = EXCLUDED.start_date,
                    period = EXCLUDED.period,
                    adjust = EXCLUDED.adjust,
                    window_size = EXCLUDED.window_size,
                    vector_method = EXCLUDED.vector_method,
                    metric = EXCLUDED.metric,
                    vector_dim = EXCLUDED.vector_dim,
                    forward_return_5d = EXCLUDED.forward_return_5d,
                    forward_return_10d = EXCLUDED.forward_return_10d,
                    forward_return_20d = EXCLUDED.forward_return_20d,
                    payload = EXCLUDED.payload,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                str(item.get("window_uid") or ""),
                str(item.get("stock_code") or ""),
                self._coerce_date_value(item.get("end_date")),
                self._coerce_date_value(item.get("start_date")),
                str(item.get("period") or "daily"),
                str(item.get("adjust") or ""),
                int(item.get("window_size") or 0),
                str(item.get("vector_method") or "returns"),
                str(item.get("metric") or "cosine"),
                int(item.get("vector_dim") or 0),
                item.get("forward_return_5d"),
                item.get("forward_return_10d"),
                item.get("forward_return_20d"),
                json.dumps(item.get("payload") or {}, ensure_ascii=False, default=str),
                json.dumps(item.get("metadata") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_kline_pattern_window(dict(row))

    async def list_kline_pattern_windows(
        self,
        *,
        stock_code: Optional[str] = None,
        period: Optional[str] = None,
        adjust: Optional[str] = None,
        vector_method: Optional[str] = None,
        window_size: Optional[int] = None,
        limit: int = 100,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM kline_pattern_windows WHERE 1=1"
            params: list[Any] = []
            idx = 1
            for field, value in (
                ("stock_code", stock_code),
                ("period", period),
                ("adjust", adjust),
                ("vector_method", vector_method),
            ):
                if value not in (None, ""):
                    sql += f" AND {field} = ${idx}"
                    params.append(value)
                    idx += 1
            if window_size is not None:
                sql += f" AND window_size = ${idx}"
                params.append(int(window_size))
                idx += 1
            sql += f" ORDER BY end_date DESC, updated_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 100), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_kline_pattern_window(dict(row)) for row in rows]

    async def list_vector_index_snapshots(
        self,
        *,
        collection_name: Optional[str] = None,
        index_version: Optional[str] = None,
        status: Optional[str] = None,
        latest_only: bool = False,
        limit: int = 100,
    ) -> List[dict]:
        async with self.acquire() as conn:
            where_parts = ["1=1"]
            params: list[Any] = []
            idx = 1
            if collection_name:
                where_parts.append(f"collection_name = ${idx}")
                params.append(collection_name)
                idx += 1
            if index_version:
                where_parts.append(f"index_version = ${idx}")
                params.append(index_version)
                idx += 1
            if status:
                where_parts.append(f"status = ${idx}")
                params.append(status)
                idx += 1
            where_sql = " AND ".join(where_parts)
            order_sql = "COALESCE(activated_at, built_at, created_at) DESC, id DESC"
            if latest_only:
                sql = f"""
                    WITH ranked AS (
                        SELECT *,
                               ROW_NUMBER() OVER (
                                   PARTITION BY collection_name, index_version
                                   ORDER BY {order_sql}
                               ) AS rn
                        FROM vector_index_snapshots
                        WHERE {where_sql}
                    )
                    SELECT *
                    FROM ranked
                    WHERE rn = 1
                    ORDER BY {order_sql}
                    LIMIT ${idx}
                """
            else:
                sql = f"""
                    SELECT *
                    FROM vector_index_snapshots
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT ${idx}
                """
            params.append(max(1, min(int(limit or 100), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_unified_vector_snapshot(dict(row)) for row in rows]

    async def replace_vector_index_items(self, collection_name: str, index_version: str, items: Iterable[dict]) -> dict:
        resolved_collection = str(collection_name or "")
        resolved_version = str(index_version or "v1")
        payloads = [dict(item or {}) for item in list(items or [])]
        async with self.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM vector_index_items WHERE collection_name = $1 AND index_version = $2",
                    resolved_collection,
                    resolved_version,
                )
                rows = []
                for payload in payloads:
                    rows.append(
                        (
                            resolved_collection,
                            resolved_version,
                            payload.get("profile_id"),
                            str(payload.get("entity_type") or "generic"),
                            str(payload.get("entity_id") or ""),
                            payload.get("stock_code"),
                            payload.get("profile_type"),
                            str(payload.get("model_id") or "unknown"),
                            str(payload.get("metric") or "cosine"),
                            int(payload.get("vector_dim") or len(payload.get("embedding") or [])),
                            payload.get("bucket_id"),
                            float(payload.get("coarse_score") or 0.0),
                            json.dumps(payload.get("embedding") or [], ensure_ascii=False, default=str),
                            json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                        )
                    )
                if rows:
                    await conn.executemany(
                        """
                        INSERT INTO vector_index_items (
                            collection_name, index_version, profile_id, entity_type, entity_id, stock_code,
                            profile_type, model_id, metric, vector_dim, bucket_id, coarse_score,
                            embedding_json, metadata, created_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14::jsonb, NOW())
                        ON CONFLICT (collection_name, index_version, profile_id) DO UPDATE SET
                            entity_type = EXCLUDED.entity_type,
                            entity_id = EXCLUDED.entity_id,
                            stock_code = EXCLUDED.stock_code,
                            profile_type = EXCLUDED.profile_type,
                            model_id = EXCLUDED.model_id,
                            metric = EXCLUDED.metric,
                            vector_dim = EXCLUDED.vector_dim,
                            bucket_id = EXCLUDED.bucket_id,
                            coarse_score = EXCLUDED.coarse_score,
                            embedding_json = EXCLUDED.embedding_json,
                            metadata = EXCLUDED.metadata
                        """,
                        rows,
                    )
                if getattr(self, "supports_pgvector", lambda: False)() and rows:
                    mapping_rows = await conn.fetch(
                        """
                        SELECT id, profile_id
                        FROM vector_index_items
                        WHERE collection_name = $1 AND index_version = $2
                        """,
                        resolved_collection,
                        resolved_version,
                    )
                    row_ids = {
                        str(dict(row).get("profile_id")): dict(row).get("id")
                        for row in mapping_rows
                        if dict(row).get("profile_id") is not None
                    }
                    store_rows = []
                    for payload in payloads:
                        vector_literal = self._encode_pgvector(payload.get("embedding") or [])
                        row_id = row_ids.get(str(payload.get("profile_id")))
                        if not vector_literal or row_id is None:
                            continue
                        store_rows.append(
                            (
                                row_id,
                                resolved_collection,
                                resolved_version,
                                payload.get("profile_id"),
                                str(payload.get("entity_type") or "generic"),
                                str(payload.get("entity_id") or ""),
                                payload.get("stock_code"),
                                payload.get("profile_type"),
                                str(payload.get("model_id") or "unknown"),
                                str(payload.get("metric") or "cosine"),
                                int(payload.get("vector_dim") or len(payload.get("embedding") or [])),
                                payload.get("bucket_id"),
                                vector_literal,
                                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                            )
                        )
                    if store_rows:
                        await conn.executemany(
                            """
                            INSERT INTO vector_index_item_store (
                                item_id, collection_name, index_version, profile_id, entity_type, entity_id,
                                stock_code, profile_type, model_id, metric, vector_dim, bucket_id, embedding, metadata, updated_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::vector, $14::jsonb, NOW())
                            ON CONFLICT (item_id) DO UPDATE SET
                                collection_name = EXCLUDED.collection_name,
                                index_version = EXCLUDED.index_version,
                                profile_id = EXCLUDED.profile_id,
                                entity_type = EXCLUDED.entity_type,
                                entity_id = EXCLUDED.entity_id,
                                stock_code = EXCLUDED.stock_code,
                                profile_type = EXCLUDED.profile_type,
                                model_id = EXCLUDED.model_id,
                                metric = EXCLUDED.metric,
                                vector_dim = EXCLUDED.vector_dim,
                                bucket_id = EXCLUDED.bucket_id,
                                embedding = EXCLUDED.embedding,
                                metadata = EXCLUDED.metadata,
                                updated_at = NOW()
                            """,
                            store_rows,
                        )
        return {"collection_name": resolved_collection, "index_version": resolved_version, "count": len(rows)}

    async def list_vector_index_items(
        self,
        *,
        collection_name: Optional[str] = None,
        index_version: Optional[str] = None,
        bucket_ids: Optional[List[str]] = None,
        profile_type: Optional[str] = None,
        stock_code: Optional[str] = None,
        stock_codes: Optional[List[str]] = None,
        entity_ids: Optional[List[str]] = None,
        exclude_stock_code: Optional[str] = None,
        exclude_entity_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM vector_index_items WHERE 1=1"
            params: list[Any] = []
            idx = 1
            if collection_name:
                sql += f" AND collection_name = ${idx}"
                params.append(collection_name)
                idx += 1
            if index_version:
                sql += f" AND index_version = ${idx}"
                params.append(index_version)
                idx += 1
            if bucket_ids:
                sql += f" AND bucket_id = ANY(${idx}::text[])"
                params.append([str(item) for item in bucket_ids])
                idx += 1
            if profile_type:
                sql += f" AND profile_type = ${idx}"
                params.append(str(profile_type))
                idx += 1
            if stock_code:
                sql += f" AND stock_code = ${idx}"
                params.append(stock_code)
                idx += 1
            if stock_codes:
                sql += f" AND stock_code = ANY(${idx}::text[])"
                params.append([str(item).strip() for item in list(stock_codes or []) if str(item).strip()])
                idx += 1
            if entity_ids:
                sql += f" AND entity_id = ANY(${idx}::text[])"
                params.append([str(item).strip() for item in list(entity_ids or []) if str(item).strip()])
                idx += 1
            if exclude_stock_code:
                sql += f" AND COALESCE(stock_code, '') != ${idx}"
                params.append(str(exclude_stock_code))
                idx += 1
            if exclude_entity_id:
                sql += f" AND entity_id != ${idx}"
                params.append(str(exclude_entity_id))
                idx += 1
            sql += f" ORDER BY coarse_score DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_unified_vector_item(dict(row)) for row in rows]

    async def ensure_vector_profile_pgvector_index(
        self,
        *,
        collection_name: str,
        version: str,
        vector_dim: int,
        profile_type: Optional[str] = None,
        metric: str = "cosine",
    ) -> Optional[str]:
        if not getattr(self, "supports_pgvector", lambda: False)():
            return None
        resolved_dim = int(vector_dim or 0)
        if resolved_dim <= 0:
            return None
        opclass = self._pgvector_opclass(metric)
        idx_name = self._pgvector_partial_index_name(
            "idx_vps_pg_hnsw",
            collection_name,
            version,
            resolved_dim,
            profile_type or "all",
            metric,
        )
        async with self.acquire() as conn:
            where_sql = "collection_name = %L AND version = %L AND vector_dim = %s"
            format_args: list[Any] = [
                idx_name,
                resolved_dim,
                opclass,
                str(collection_name or ""),
                str(version or ""),
                resolved_dim,
            ]
            if profile_type:
                where_sql += " AND profile_type = %L"
                format_args.append(str(profile_type))
            format_placeholders = ["$1::text", "$2::int", "$3::text", "$4::text", "$5::text", "$6::int"]
            if profile_type:
                format_placeholders.append(f"${len(format_args)}::text")
            sql = await conn.fetchval(
                f"""
                SELECT format(
                    'CREATE INDEX IF NOT EXISTS %I ON vector_profile_store USING hnsw ((embedding::vector(%s)) %s) WHERE {where_sql}',
                    {', '.join(format_placeholders)}
                )
                """,
                *format_args,
            )
            await conn.execute(sql)
        return idx_name

    async def ensure_vector_index_item_pgvector_index(
        self,
        *,
        collection_name: str,
        index_version: str,
        vector_dim: int,
        metric: str = "cosine",
    ) -> Optional[str]:
        if not getattr(self, "supports_pgvector", lambda: False)():
            return None
        resolved_dim = int(vector_dim or 0)
        if resolved_dim <= 0:
            return None
        opclass = self._pgvector_opclass(metric)
        idx_name = self._pgvector_partial_index_name(
            "idx_vis_pg_hnsw",
            collection_name,
            index_version,
            resolved_dim,
            metric,
        )
        async with self.acquire() as conn:
            sql = await conn.fetchval(
                """
                SELECT format(
                    'CREATE INDEX IF NOT EXISTS %I ON vector_index_item_store USING hnsw ((embedding::vector(%s)) %s) WHERE collection_name = %L AND index_version = %L AND vector_dim = %s',
                    $1::text, $2::int, $3::text, $4::text, $5::text, $6::int
                )
                """,
                idx_name,
                resolved_dim,
                opclass,
                str(collection_name or ""),
                str(index_version or ""),
                resolved_dim,
            )
            await conn.execute(sql)
        return idx_name

    async def list_vector_hnsw_indexes(
        self,
        *,
        collection_name: Optional[str] = None,
        index_version: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT schemaname, tablename, indexname, indexdef
                FROM pg_indexes
                WHERE tablename IN ('vector_profile_store', 'vector_index_item_store')
                  AND indexdef ILIKE '%USING hnsw%'
                ORDER BY tablename, indexname
                LIMIT $1
                """,
                max(1, min(int(limit or 200), 1000)),
            )
        items = [dict(row) for row in rows]
        def _fallback_sql_quote(value: Any) -> str:
            return "'" + str(value).replace("'", "''") + "'"

        sql_quote = getattr(self, "_sql_quote", _fallback_sql_quote)
        if collection_name:
            quoted = sql_quote(collection_name)
            items = [row for row in items if quoted in str(row.get("indexdef") or "")]
        if index_version:
            quoted = sql_quote(index_version)
            items = [row for row in items if quoted in str(row.get("indexdef") or "")]
        return items

    async def search_vector_profiles_by_embedding(
        self,
        *,
        query_embedding: List[float],
        collection_name: str,
        version: Optional[str] = None,
        profile_type: Optional[str] = None,
        stock_code: Optional[str] = None,
        stock_codes: Optional[List[str]] = None,
        entity_ids: Optional[List[str]] = None,
        exclude_stock_code: Optional[str] = None,
        exclude_entity_id: Optional[str] = None,
        limit: int = 20,
        metric: str = "cosine",
    ) -> List[dict]:
        if not getattr(self, "supports_pgvector", lambda: False)():
            return []
        vector_literal = self._encode_pgvector(query_embedding)
        dim = len(list(query_embedding or []))
        if not vector_literal or dim <= 0:
            return []
        distance_sql, similarity_sql = self._pgvector_distance_sql("ps.embedding", metric, dim)
        async with self.acquire() as conn:
            sql = f"""
                SELECT vp.*, {similarity_sql} AS similarity
                FROM vector_profile_store ps
                JOIN vector_profiles vp ON vp.id = ps.profile_id
                WHERE ps.collection_name = $2 AND ps.vector_dim = $3
            """
            params: list[Any] = [vector_literal, str(collection_name or ""), int(dim)]
            idx = 4
            if version:
                sql += f" AND ps.version = ${idx}"
                params.append(version)
                idx += 1
            if profile_type:
                sql += f" AND ps.profile_type = ${idx}"
                params.append(profile_type)
                idx += 1
            if stock_code:
                sql += f" AND ps.stock_code = ${idx}"
                params.append(stock_code)
                idx += 1
            if stock_codes:
                sql += f" AND ps.stock_code = ANY(${idx}::text[])"
                params.append([str(item).strip() for item in list(stock_codes or []) if str(item).strip()])
                idx += 1
            if entity_ids:
                sql += f" AND ps.entity_id = ANY(${idx}::text[])"
                params.append([str(item).strip() for item in list(entity_ids or []) if str(item).strip()])
                idx += 1
            if exclude_stock_code:
                sql += f" AND COALESCE(ps.stock_code, '') != ${idx}"
                params.append(str(exclude_stock_code))
                idx += 1
            if exclude_entity_id:
                sql += f" AND ps.entity_id != ${idx}"
                params.append(str(exclude_entity_id))
                idx += 1
            sql += f" ORDER BY {distance_sql} ASC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [{**self._decode_unified_vector_profile(dict(row)), "similarity": round(float(row.get("similarity") or 0.0), 6)} for row in rows]

    async def search_vector_index_items_by_embedding(
        self,
        *,
        query_embedding: List[float],
        collection_name: str,
        index_version: str,
        profile_type: Optional[str] = None,
        stock_code: Optional[str] = None,
        stock_codes: Optional[List[str]] = None,
        entity_ids: Optional[List[str]] = None,
        bucket_ids: Optional[List[str]] = None,
        exclude_stock_code: Optional[str] = None,
        exclude_entity_id: Optional[str] = None,
        limit: int = 80,
        metric: str = "cosine",
    ) -> List[dict]:
        if not getattr(self, "supports_pgvector", lambda: False)():
            return []
        vector_literal = self._encode_pgvector(query_embedding)
        dim = len(list(query_embedding or []))
        if not vector_literal or dim <= 0:
            return []
        distance_sql, similarity_sql = self._pgvector_distance_sql("iv.embedding", metric, dim)
        async with self.acquire() as conn:
            sql = f"""
                SELECT i.*, {similarity_sql} AS similarity
                FROM vector_index_item_store iv
                JOIN vector_index_items i ON i.id = iv.item_id
                WHERE iv.collection_name = $2 AND iv.index_version = $3 AND iv.vector_dim = $4
            """
            params: list[Any] = [vector_literal, str(collection_name or ""), str(index_version or "v1"), int(dim)]
            idx = 5
            if profile_type:
                sql += f" AND iv.profile_type = ${idx}"
                params.append(profile_type)
                idx += 1
            if stock_code:
                sql += f" AND iv.stock_code = ${idx}"
                params.append(stock_code)
                idx += 1
            if stock_codes:
                sql += f" AND iv.stock_code = ANY(${idx}::text[])"
                params.append([str(item).strip() for item in list(stock_codes or []) if str(item).strip()])
                idx += 1
            if entity_ids:
                sql += f" AND iv.entity_id = ANY(${idx}::text[])"
                params.append([str(item).strip() for item in list(entity_ids or []) if str(item).strip()])
                idx += 1
            if bucket_ids:
                sql += f" AND iv.bucket_id = ANY(${idx}::text[])"
                params.append([str(item).strip() for item in list(bucket_ids or []) if str(item).strip()])
                idx += 1
            if exclude_stock_code:
                sql += f" AND COALESCE(iv.stock_code, '') != ${idx}"
                params.append(str(exclude_stock_code))
                idx += 1
            if exclude_entity_id:
                sql += f" AND iv.entity_id != ${idx}"
                params.append(str(exclude_entity_id))
                idx += 1
            sql += f" ORDER BY {distance_sql} ASC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 80), 500)))
            rows = await conn.fetch(sql, *params)
        return [{**self._decode_unified_vector_item(dict(row)), "similarity": round(float(row.get("similarity") or 0.0), 6)} for row in rows]

    async def search_market_doc_chunks(
        self,
        *,
        query_text: Optional[str] = None,
        query_embedding: Optional[List[float]] = None,
        stock_code: Optional[str] = None,
        doc_types: Optional[List[str]] = None,
        start_date: Any = None,
        end_date: Any = None,
        limit: int = 10,
    ) -> List[dict]:
        normalized_query_text = self._normalize_hybrid_query_text(query_text)
        if normalized_query_text and not query_embedding:
            try:
                from ...services.text_embedding import get_strategy_text_embedding_service

                service = get_strategy_text_embedding_service()
                if service.is_enabled():
                    query_embedding = await service.embed_text(normalized_query_text)
            except Exception:
                query_embedding = None

        dense_rows: dict[str, dict] = {}
        if query_embedding:
            dense_result = await self.search_vector_collection(
                collection_name="market_doc_chunks",
                query_embedding=query_embedding,
                profile_type=doc_types[0] if len(list(doc_types or [])) == 1 else None,
                stock_code=stock_code,
                limit=max(10, min(int(limit or 10) * 3, 100)),
                metric="cosine",
            )
            for row in list((dense_result or {}).get("items") or []):
                dense_rows[str(row.get("entity_id") or "")] = row

        async with self.acquire() as conn:
            params: list[Any] = []
            where_clauses = ["1=1"]
            idx = 1
            if stock_code:
                where_clauses.append(f"c.stock_code = ${idx}")
                params.append(stock_code)
                idx += 1
            if doc_types:
                where_clauses.append(f"LOWER(COALESCE(c.doc_type, '')) = ANY(${idx}::text[])")
                params.append([str(item or "").strip().lower() for item in doc_types if str(item or "").strip()])
                idx += 1
            if start_date is not None:
                where_clauses.append(f"c.published_at >= ${idx}::timestamptz")
                params.append(self._coerce_timestamp(start_date))
                idx += 1
            if end_date is not None:
                where_clauses.append(f"c.published_at <= ${idx}::timestamptz")
                params.append(self._coerce_timestamp(end_date))
                idx += 1
            params.append(max(50, min(int(limit or 10) * 20, 500)))
            rows = await conn.fetch(
                f"""
                SELECT
                    d.doc_uid,
                    d.url,
                    d.author,
                    c.id,
                    c.doc_id,
                    c.chunk_no,
                    c.stock_code,
                    c.doc_type,
                    c.source,
                    c.title,
                    c.chunk_text,
                    c.published_at,
                    c.metadata,
                    d.doc_uid || ':' || c.chunk_no::text AS entity_id
                FROM market_doc_chunks c
                JOIN market_documents d ON d.id = c.doc_id
                WHERE {' AND '.join(where_clauses)}
                ORDER BY c.published_at DESC NULLS LAST, c.id DESC
                LIMIT ${len(params)}
                """,
                *params,
            )
        results = []
        for row in rows:
            payload = dict(row)
            entity_id = str(payload.get("entity_id") or "")
            dense = dense_rows.get(entity_id, {})
            dense_score = self._hybrid_dense_score(dense.get("similarity"))
            lexical_score = (
                self._hybrid_lexical_score(
                    normalized_query_text,
                    str(payload.get("title") or ""),
                    str(payload.get("chunk_text") or ""),
                )
                if normalized_query_text
                else None
            )
            hybrid_score = self._hybrid_score(dense_score=dense_score, lexical_score=lexical_score)
            if normalized_query_text and not dense_score and not (lexical_score and lexical_score > 0):
                continue
            results.append(
                {
                    "entity_id": entity_id,
                    "doc_uid": payload.get("doc_uid"),
                    "chunk_id": payload.get("id"),
                    "doc_id": payload.get("doc_id"),
                    "chunk_no": payload.get("chunk_no"),
                    "stock_code": payload.get("stock_code"),
                    "doc_type": payload.get("doc_type"),
                    "source": payload.get("source"),
                    "title": payload.get("title"),
                    "content": payload.get("chunk_text"),
                    "summary": str(payload.get("chunk_text") or "")[:240],
                    "url": payload.get("url"),
                    "author": payload.get("author"),
                    "published_at": payload.get("published_at"),
                    "metadata": self._decode_json_field(payload.get("metadata"), {}),
                    "dense_score": dense_score,
                    "lexical_score": lexical_score,
                    "hybrid_score": hybrid_score,
                    "similarity": hybrid_score if hybrid_score is not None else dense_score,
                }
            )
        if normalized_query_text or dense_rows:
            results.sort(
                key=lambda item: (
                    float(item.get("hybrid_score") or item.get("dense_score") or -1.0),
                    float(item.get("dense_score") or -1.0),
                    float(item.get("lexical_score") or -1.0),
                    item.get("published_at").isoformat() if hasattr(item.get("published_at"), "isoformat") else str(item.get("published_at") or ""),
                ),
                reverse=True,
            )
        return results[: max(1, min(int(limit or 10), 100))]

    async def search_kline_pattern_windows(
        self,
        *,
        query_embedding: List[float],
        window_size: int,
        vector_method: str = "returns",
        metric: str = "cosine",
        period: str = "daily",
        adjust: str = "",
        version: Optional[str] = None,
        stock_codes: Optional[List[str]] = None,
        exclude_stock_code: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        profile_type = self._kline_pattern_profile_type(
            window_size=window_size,
            vector_method=vector_method,
            period=period,
            adjust=adjust,
        )
        search_result = await self.search_vector_collection(
            collection_name="kline_pattern_embeddings",
            query_embedding=query_embedding,
            version=version,
            profile_type=profile_type,
            stock_codes=stock_codes,
            exclude_stock_code=exclude_stock_code,
            limit=max(10, min(int(limit or 10) * 8, 200)),
            metric=metric,
        )
        rows = list((search_result or {}).get("items") or [])
        if not rows:
            return []

        entity_ids = [str(row.get("entity_id") or "").strip() for row in rows if str(row.get("entity_id") or "").strip()]
        if not entity_ids:
            return []
        allowed_codes = {str(item).strip() for item in list(stock_codes or []) if str(item).strip()}
        excluded = str(exclude_stock_code or "").strip()
        async with self.acquire() as conn:
            window_rows = await conn.fetch(
                """
                SELECT *
                FROM kline_pattern_windows
                WHERE window_uid = ANY($1::text[])
                """,
                entity_ids,
            )
        window_map = {
            str(self._decode_kline_pattern_window(dict(row)).get("window_uid") or ""): self._decode_kline_pattern_window(dict(row))
            for row in window_rows
        }
        results: list[dict] = []
        for row in rows:
            window_uid = str(row.get("entity_id") or "").strip()
            window = dict(window_map.get(window_uid) or {})
            if not window:
                continue
            stock_code = str(window.get("stock_code") or "").strip()
            if allowed_codes and stock_code not in allowed_codes:
                continue
            if excluded and stock_code == excluded:
                continue
            metadata = dict(row.get("metadata") or {})
            payload = dict(window.get("payload") or {})
            results.append(
                {
                    "window_uid": window_uid,
                    "stock_code": stock_code,
                    "stock_name": metadata.get("stock_name") or payload.get("stock_name"),
                    "start_date": window.get("start_date"),
                    "end_date": window.get("end_date"),
                    "period": window.get("period"),
                    "adjust": window.get("adjust"),
                    "window_size": window.get("window_size"),
                    "vector_method": window.get("vector_method"),
                    "metric": window.get("metric"),
                    "vector_dim": window.get("vector_dim"),
                    "similarity": row.get("similarity"),
                    "forward_return_5d": window.get("forward_return_5d"),
                    "forward_return_10d": window.get("forward_return_10d"),
                    "forward_return_20d": window.get("forward_return_20d"),
                    "payload": payload,
                    "metadata": window.get("metadata") or {},
                }
            )
        results.sort(key=lambda item: float(item.get("similarity") or -1.0), reverse=True)
        return results[: max(1, min(int(limit or 10), 100))]
