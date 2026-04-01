"""Unified vector storage mixin for market / quant / strategy derived objects."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any, Iterable, List, Optional


class _VectorUnifiedStorageMixin:
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
                        index_params=dict((snapshot or {}).get("index_params") or {}),
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
                    index_params=dict((snapshot or {}).get("index_params") or {}),
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
