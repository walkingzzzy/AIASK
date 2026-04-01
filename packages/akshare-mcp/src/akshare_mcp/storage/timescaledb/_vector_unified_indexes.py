"""Unified vector storage mixin for market / quant / strategy derived objects."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any, Iterable, List, Optional


class _VectorUnifiedIndexesMixin:
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
            index_params: Optional[dict] = None,
        ) -> Optional[str]:
            if not getattr(self, "supports_pgvector", lambda: False)():
                return None
            resolved_dim = int(vector_dim or 0)
            if resolved_dim <= 0:
                return None
            opclass = self._pgvector_opclass(metric)
            with_clause = self._pgvector_hnsw_with_clause(index_params)
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
                    with_clause,
                    str(collection_name or ""),
                    str(version or ""),
                    resolved_dim,
                ]
                if profile_type:
                    where_sql += " AND profile_type = %L"
                    format_args.append(str(profile_type))
                format_placeholders = ["$1::text", "$2::int", "$3::text", "$4::text", "$5::text", "$6::text", "$7::int"]
                if profile_type:
                    format_placeholders.append(f"${len(format_args)}::text")
                sql = await conn.fetchval(
                    f"""
                    SELECT format(
                        'CREATE INDEX IF NOT EXISTS %I ON vector_profile_store USING hnsw ((embedding::vector(%s)) %s)%s WHERE {where_sql}',
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
            index_params: Optional[dict] = None,
        ) -> Optional[str]:
            if not getattr(self, "supports_pgvector", lambda: False)():
                return None
            resolved_dim = int(vector_dim or 0)
            if resolved_dim <= 0:
                return None
            opclass = self._pgvector_opclass(metric)
            with_clause = self._pgvector_hnsw_with_clause(index_params)
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
                        'CREATE INDEX IF NOT EXISTS %I ON vector_index_item_store USING hnsw ((embedding::vector(%s)) %s)%s WHERE collection_name = %L AND index_version = %L AND vector_dim = %s',
                        $1::text, $2::int, $3::text, $4::text, $5::text, $6::text, $7::int
                    )
                    """,
                    idx_name,
                    resolved_dim,
                    opclass,
                    with_clause,
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
            index_params: Optional[dict] = None,
        ) -> List[dict]:
            if not getattr(self, "supports_pgvector", lambda: False)():
                return []
            vector_literal = self._encode_pgvector(query_embedding)
            dim = len(list(query_embedding or []))
            if not vector_literal or dim <= 0:
                return []
            distance_sql, similarity_sql = self._pgvector_distance_sql("ps.embedding", metric, dim)
            async with self.acquire() as conn:
                hnsw_params = self._resolve_pgvector_hnsw_params(index_params)
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
                if hasattr(conn, "transaction"):
                    async with conn.transaction():
                        await conn.execute(f"SET LOCAL hnsw.ef_search = {int(hnsw_params['ef_search'])}")
                        rows = await conn.fetch(sql, *params)
                else:
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
            index_params: Optional[dict] = None,
        ) -> List[dict]:
            if not getattr(self, "supports_pgvector", lambda: False)():
                return []
            vector_literal = self._encode_pgvector(query_embedding)
            dim = len(list(query_embedding or []))
            if not vector_literal or dim <= 0:
                return []
            distance_sql, similarity_sql = self._pgvector_distance_sql("iv.embedding", metric, dim)
            async with self.acquire() as conn:
                hnsw_params = self._resolve_pgvector_hnsw_params(index_params)
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
                if hasattr(conn, "transaction"):
                    async with conn.transaction():
                        await conn.execute(f"SET LOCAL hnsw.ef_search = {int(hnsw_params['ef_search'])}")
                        rows = await conn.fetch(sql, *params)
                else:
                    rows = await conn.fetch(sql, *params)
            return [{**self._decode_unified_vector_item(dict(row)), "similarity": round(float(row.get("similarity") or 0.0), 6)} for row in rows]
