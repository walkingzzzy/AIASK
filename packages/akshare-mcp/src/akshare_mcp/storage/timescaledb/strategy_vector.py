"""TimescaleDB 适配器 — 策略向量 Mixin (vector archive / pgvector ANN / index management / health check)"""

import json
import logging
from datetime import timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


class StrategyVectorMixin:
    """向量存档 / pgvector ANN / HNSW 索引管理 / 健康检查"""

    # ------------------------------------------------------------------
    # vector profiles
    # ------------------------------------------------------------------

    def _decode_vector_profile(self, row: dict) -> dict:
        result = dict(row)
        result["embedding"] = self._decode_json_field(result.get("embedding"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_vector_profile(self, profile: dict) -> dict:
        payload = dict(profile or {})
        embedding = payload.get("embedding") or []
        index_name = self._resolve_vector_index_name(payload)
        metadata_json = json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str)
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_vector_profiles
                    (strategy_id, index_name, profile_type, vector_method, metric, vector_dim, embedding, signature,
                     backend, index_version, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11::jsonb, NOW(), NOW())
                RETURNING *
                """,
                payload.get("strategy_id"),
                index_name,
                str(payload.get("profile_type") or "behavior"),
                str(payload.get("vector_method") or "price_volume"),
                str(payload.get("metric") or "cosine"),
                int(payload.get("vector_dim") or len(embedding)),
                json.dumps(embedding, ensure_ascii=False, default=str),
                payload.get("signature"),
                str(payload.get("backend") or getattr(self, 'get_vector_backend', lambda: 'index')()),
                payload.get("index_version"),
                metadata_json,
            )
            if getattr(self, 'supports_pgvector', lambda: False)():
                vector_literal = self._encode_pgvector(embedding)
                if vector_literal:
                    await conn.execute(
                        """
                        INSERT INTO strategy_vector_profile_store
                            (profile_id, strategy_id, index_name, index_version, profile_type, vector_method, metric,
                             vector_dim, embedding, metadata, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, $10::jsonb, NOW())
                        ON CONFLICT (profile_id) DO UPDATE SET
                            strategy_id = EXCLUDED.strategy_id,
                            index_name = EXCLUDED.index_name,
                            index_version = EXCLUDED.index_version,
                            profile_type = EXCLUDED.profile_type,
                            vector_method = EXCLUDED.vector_method,
                            metric = EXCLUDED.metric,
                            vector_dim = EXCLUDED.vector_dim,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                        """,
                        dict(row).get('id'),
                        payload.get('strategy_id'),
                        index_name,
                        payload.get('index_version'),
                        str(payload.get('profile_type') or 'behavior'),
                        str(payload.get('vector_method') or 'price_volume'),
                        str(payload.get('metric') or 'cosine'),
                        int(payload.get('vector_dim') or len(embedding)),
                        vector_literal,
                        metadata_json,
                    )
        return self._decode_vector_profile(dict(row))

    async def list_strategy_vector_profiles(
        self,
        strategy_id: Optional[str] = None,
        profile_type: Optional[str] = None,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT id, strategy_id, index_name, profile_type, vector_method, metric, vector_dim, embedding, signature, backend, index_version, metadata, created_at, updated_at FROM strategy_vector_profiles WHERE 1=1"
            params: list = []
            idx = 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            if index_name:
                sql += f" AND index_name = ${idx}"
                params.append(index_name)
                idx += 1
            if profile_type:
                sql += f" AND profile_type = ${idx}"
                params.append(profile_type)
                idx += 1
            if index_version:
                sql += f" AND index_version = ${idx}"
                params.append(index_version)
                idx += 1
            sql += f" ORDER BY updated_at DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_vector_profile(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # vector index registry
    # ------------------------------------------------------------------

    def _decode_vector_index(self, row: dict) -> dict:
        result = dict(row)
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_vector_index_registry(self, entry: dict) -> dict:
        payload = dict(entry or {})
        built_at = self._coerce_timestamp(payload.get("built_at"))
        activated_at = self._coerce_timestamp(payload.get("activated_at"))
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO vector_index_registry
                    (index_name, backend, status, profile_type, vector_method, metric, sample_count,
                     index_version, metadata, built_at, activated_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::timestamptz, $11::timestamptz, NOW())
                ON CONFLICT (index_name, index_version) DO UPDATE SET
                    backend = EXCLUDED.backend,
                    status = EXCLUDED.status,
                    profile_type = EXCLUDED.profile_type,
                    vector_method = EXCLUDED.vector_method,
                    metric = EXCLUDED.metric,
                    sample_count = EXCLUDED.sample_count,
                    metadata = EXCLUDED.metadata,
                    built_at = EXCLUDED.built_at,
                    activated_at = EXCLUDED.activated_at
                RETURNING *
                """,
                str(payload.get("index_name") or "default"),
                str(payload.get("backend") or "index"),
                str(payload.get("status") or "building"),
                payload.get("profile_type"),
                payload.get("vector_method"),
                str(payload.get("metric") or "cosine"),
                int(payload.get("sample_count") or 0),
                str(payload.get("index_version") or "v1"),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                built_at,
                activated_at,
            )
        return self._decode_vector_index(dict(row))

    async def list_vector_index_registry(
        self,
        index_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM vector_index_registry WHERE 1=1"
            params: list = []
            idx = 1
            if index_name:
                sql += f" AND index_name = ${idx}"
                params.append(index_name)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_vector_index(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # vector index snapshots
    # ------------------------------------------------------------------

    def _decode_vector_index_snapshot(self, row: dict) -> dict:
        result = dict(row)
        result["centroids"] = self._decode_json_field(result.get("centroids"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def save_strategy_vector_index_snapshot(self, snapshot: dict) -> dict:
        payload = dict(snapshot or {})
        built_at = self._coerce_timestamp(payload.get("built_at"))
        activated_at = self._coerce_timestamp(payload.get("activated_at"))
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_vector_index_snapshots
                    (index_name, index_version, status, profile_type, vector_method, metric, backend,
                     profile_count, bucket_count, vector_dim, centroids, metadata, task_run_id, source,
                     built_at, activated_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13, $14, $15::timestamptz, $16::timestamptz, NOW())
                ON CONFLICT (index_name, index_version) DO UPDATE SET
                    status = EXCLUDED.status,
                    profile_type = EXCLUDED.profile_type,
                    vector_method = EXCLUDED.vector_method,
                    metric = EXCLUDED.metric,
                    backend = EXCLUDED.backend,
                    profile_count = EXCLUDED.profile_count,
                    bucket_count = EXCLUDED.bucket_count,
                    vector_dim = EXCLUDED.vector_dim,
                    centroids = EXCLUDED.centroids,
                    metadata = EXCLUDED.metadata,
                    task_run_id = EXCLUDED.task_run_id,
                    source = EXCLUDED.source,
                    built_at = EXCLUDED.built_at,
                    activated_at = EXCLUDED.activated_at
                RETURNING *
                """,
                str(payload.get("index_name") or "strategy_behavior"),
                str(payload.get("index_version") or "v1"),
                str(payload.get("status") or "building"),
                payload.get("profile_type"),
                payload.get("vector_method"),
                str(payload.get("metric") or "cosine"),
                str(payload.get("backend") or "index"),
                int(payload.get("profile_count") or 0),
                int(payload.get("bucket_count") or 0),
                int(payload.get("vector_dim") or 0),
                json.dumps(payload.get("centroids") or [], ensure_ascii=False, default=str),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                payload.get("task_run_id"),
                str(payload.get("source") or "system"),
                built_at,
                activated_at,
            )
        return self._decode_vector_index_snapshot(dict(row))

    async def get_latest_strategy_vector_index_snapshot(self, index_name: str = 'strategy_behavior') -> Optional[dict]:
        rows = await self.list_strategy_vector_index_snapshots(index_name=index_name, limit=1)
        return rows[0] if rows else None

    async def list_strategy_vector_index_snapshots(
        self,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_vector_index_snapshots WHERE 1=1"
            params: list = []
            idx = 1
            if index_name:
                sql += f" AND index_name = ${idx}"
                params.append(index_name)
                idx += 1
            if index_version:
                sql += f" AND index_version = ${idx}"
                params.append(index_version)
                idx += 1
            if status:
                sql += f" AND status = ${idx}"
                params.append(status)
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_vector_index_snapshot(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # vector index items (with pgvector store sync)
    # ------------------------------------------------------------------

    def _decode_vector_index_item(self, row: dict) -> dict:
        result = dict(row)
        result["embedding"] = self._decode_json_field(result.get("embedding"), [])
        result["metadata"] = self._decode_json_field(result.get("metadata"), {})
        return result

    async def replace_strategy_vector_index_items(self, index_name: str, index_version: str, items: List[dict]) -> dict:
        async with self.acquire() as conn:
            await conn.execute(
                "DELETE FROM strategy_vector_index_items WHERE index_name = $1 AND index_version = $2",
                str(index_name or 'strategy_behavior'),
                str(index_version or 'v1'),
            )
            inserted = 0
            for item in items or []:
                payload = dict(item or {})
                row = await conn.fetchrow(
                    """
                    INSERT INTO strategy_vector_index_items
                        (index_name, index_version, profile_id, strategy_id, profile_type, vector_method, metric,
                         vector_dim, bucket_id, coarse_score, embedding, metadata, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, NOW())
                    ON CONFLICT (index_name, index_version, profile_id) DO UPDATE SET
                        strategy_id = EXCLUDED.strategy_id,
                        profile_type = EXCLUDED.profile_type,
                        vector_method = EXCLUDED.vector_method,
                        metric = EXCLUDED.metric,
                        vector_dim = EXCLUDED.vector_dim,
                        bucket_id = EXCLUDED.bucket_id,
                        coarse_score = EXCLUDED.coarse_score,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                    RETURNING id
                    """,
                    str(index_name or 'strategy_behavior'),
                    str(index_version or 'v1'),
                    payload.get("profile_id"),
                    payload.get("strategy_id"),
                    payload.get("profile_type"),
                    payload.get("vector_method"),
                    str(payload.get("metric") or 'cosine'),
                    int(payload.get("vector_dim") or len(payload.get("embedding") or [])),
                    payload.get("bucket_id"),
                    float(payload.get("coarse_score") or 0.0),
                    json.dumps(payload.get("embedding") or [], ensure_ascii=False, default=str),
                    json.dumps(payload.get("metadata") or {}, ensure_ascii=False, default=str),
                )
                if getattr(self, 'supports_pgvector', lambda: False)():
                    vector_literal = self._encode_pgvector(payload.get('embedding') or [])
                    row_id = dict(row).get('id') if row else None
                    if vector_literal and row_id is not None:
                        await conn.execute(
                            """
                            INSERT INTO strategy_vector_index_item_store
                                (item_id, index_name, index_version, strategy_id, profile_id, profile_type, vector_method,
                                 metric, vector_dim, embedding, metadata, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector, $11::jsonb, NOW())
                            ON CONFLICT (item_id) DO UPDATE SET
                                index_name = EXCLUDED.index_name,
                                index_version = EXCLUDED.index_version,
                                strategy_id = EXCLUDED.strategy_id,
                                profile_id = EXCLUDED.profile_id,
                                profile_type = EXCLUDED.profile_type,
                                vector_method = EXCLUDED.vector_method,
                                metric = EXCLUDED.metric,
                                vector_dim = EXCLUDED.vector_dim,
                                embedding = EXCLUDED.embedding,
                                metadata = EXCLUDED.metadata,
                                updated_at = NOW()
                            """,
                            row_id,
                            str(index_name or 'strategy_behavior'),
                            str(index_version or 'v1'),
                            payload.get('strategy_id'),
                            payload.get('profile_id'),
                            payload.get('profile_type'),
                            payload.get('vector_method'),
                            str(payload.get('metric') or 'cosine'),
                            int(payload.get('vector_dim') or len(payload.get('embedding') or [])),
                            vector_literal,
                            json.dumps(payload.get('metadata') or {}, ensure_ascii=False, default=str),
                        )
                inserted += 1
        return {"index_name": str(index_name or 'strategy_behavior'), "index_version": str(index_version or 'v1'), "count": inserted}

    async def list_strategy_vector_index_items(
        self,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
        bucket_ids: Optional[List[str]] = None,
        strategy_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_vector_index_items WHERE 1=1"
            params: list = []
            idx = 1
            if index_name:
                sql += f" AND index_name = ${idx}"
                params.append(index_name)
                idx += 1
            if index_version:
                sql += f" AND index_version = ${idx}"
                params.append(index_version)
                idx += 1
            if bucket_ids:
                sql += f" AND bucket_id = ANY(${idx}::text[])"
                params.append([str(item) for item in bucket_ids])
                idx += 1
            if strategy_id:
                sql += f" AND strategy_id = ${idx}"
                params.append(strategy_id)
                idx += 1
            sql += f" ORDER BY coarse_score DESC, created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 5000)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_vector_index_item(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # pgvector ANN search
    # ------------------------------------------------------------------

    async def search_strategy_vector_profiles_by_embedding(
        self,
        query_embedding: List[float],
        profile_type: Optional[str] = None,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
        exclude_strategy_id: Optional[str] = None,
        limit: int = 20,
        metric: str = 'cosine',
    ) -> List[dict]:
        if not getattr(self, 'supports_pgvector', lambda: False)():
            return []
        vector_literal = self._encode_pgvector(query_embedding)
        dim = len(list(query_embedding or []))
        if not vector_literal or dim <= 0:
            return []
        distance_sql, similarity_sql = self._pgvector_distance_sql('pv.embedding', metric, dim)
        async with self.acquire() as conn:
            sql = f"""
                SELECT p.id, p.strategy_id, p.index_name, p.profile_type, p.vector_method, p.metric, p.vector_dim,
                       p.embedding, p.signature, p.backend, p.index_version, p.metadata, p.created_at, p.updated_at,
                       {similarity_sql} AS similarity
                FROM strategy_vector_profile_store pv
                JOIN strategy_vector_profiles p ON p.id = pv.profile_id
                WHERE pv.vector_dim = {int(dim)}
            """
            params: list = [vector_literal]
            idx = 2
            if index_name:
                sql += f" AND pv.index_name = ${idx}"
                params.append(index_name)
                idx += 1
            if index_version:
                sql += f" AND pv.index_version = ${idx}"
                params.append(index_version)
                idx += 1
            if profile_type:
                sql += f" AND pv.profile_type = ${idx}"
                params.append(profile_type)
                idx += 1
            if exclude_strategy_id:
                sql += f" AND pv.strategy_id <> ${idx}"
                params.append(exclude_strategy_id)
                idx += 1
            sql += f" ORDER BY {distance_sql} ASC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 20), 500)))
            rows = await conn.fetch(sql, *params)
        return [{**self._decode_vector_profile(dict(row)), 'similarity': round(float(row.get('similarity') or 0.0), 6)} for row in rows]

    async def search_strategy_vector_index_items_by_embedding(
        self,
        query_embedding: List[float],
        index_name: str,
        index_version: str,
        profile_type: Optional[str] = None,
        exclude_strategy_id: Optional[str] = None,
        limit: int = 80,
        metric: str = 'cosine',
    ) -> List[dict]:
        if not getattr(self, 'supports_pgvector', lambda: False)():
            return []
        vector_literal = self._encode_pgvector(query_embedding)
        dim = len(list(query_embedding or []))
        if not vector_literal or dim <= 0:
            return []
        distance_sql, similarity_sql = self._pgvector_distance_sql('iv.embedding', metric, dim)
        async with self.acquire() as conn:
            sql = f"""
                SELECT i.id, i.index_name, i.index_version, i.profile_id, i.strategy_id, i.profile_type, i.vector_method,
                       i.metric, i.vector_dim, i.bucket_id, i.coarse_score, i.embedding, i.metadata, i.created_at,
                       {similarity_sql} AS similarity
                FROM strategy_vector_index_item_store iv
                JOIN strategy_vector_index_items i ON i.id = iv.item_id
                WHERE iv.index_name = $2 AND iv.index_version = $3 AND iv.vector_dim = {int(dim)}
            """
            params: list = [vector_literal, str(index_name or 'strategy_behavior'), str(index_version or 'v1')]
            idx = 4
            if profile_type:
                sql += f" AND iv.profile_type = ${idx}"
                params.append(profile_type)
                idx += 1
            if exclude_strategy_id:
                sql += f" AND iv.strategy_id <> ${idx}"
                params.append(exclude_strategy_id)
                idx += 1
            sql += f" ORDER BY {distance_sql} ASC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 80), 500)))
            rows = await conn.fetch(sql, *params)
        return [{**self._decode_vector_index_item(dict(row)), 'similarity': round(float(row.get('similarity') or 0.0), 6)} for row in rows]

    # ------------------------------------------------------------------
    # HNSW index management
    # ------------------------------------------------------------------

    async def ensure_strategy_vector_index_item_pgvector_index(
        self,
        index_name: str,
        index_version: str,
        vector_dim: int,
        metric: str = 'cosine',
    ) -> Optional[str]:
        if not getattr(self, 'supports_pgvector', lambda: False)():
            return None
        resolved_dim = int(vector_dim or 0)
        if resolved_dim <= 0:
            return None
        opclass = self._pgvector_opclass(metric)
        idx_name = self._pgvector_partial_index_name('idx_svi_pg_hnsw', index_name, index_version, resolved_dim, metric)
        sql = f"""
            CREATE INDEX IF NOT EXISTS {idx_name}
            ON strategy_vector_index_item_store
            USING hnsw ((embedding::vector({resolved_dim})) {opclass})
            WHERE index_name = {self._sql_quote(index_name)}
              AND index_version = {self._sql_quote(index_version)}
              AND vector_dim = {resolved_dim}
        """
        async with self.acquire() as conn:
            await conn.execute(sql)
        return idx_name

    async def ensure_strategy_vector_profile_pgvector_index(
        self,
        index_name: str,
        index_version: str,
        vector_dim: int,
        profile_type: Optional[str] = None,
        metric: str = 'cosine',
    ) -> Optional[str]:
        if not getattr(self, 'supports_pgvector', lambda: False)():
            return None
        resolved_dim = int(vector_dim or 0)
        if resolved_dim <= 0:
            return None
        opclass = self._pgvector_opclass(metric)
        idx_name = self._pgvector_partial_index_name(
            'idx_svp_pg_hnsw',
            index_name,
            index_version,
            resolved_dim,
            profile_type or 'all',
            metric,
        )
        where_clauses = [
            f"index_name = {self._sql_quote(index_name)}",
            f"index_version = {self._sql_quote(index_version)}",
            f"vector_dim = {resolved_dim}",
        ]
        if profile_type:
            where_clauses.append(f"profile_type = {self._sql_quote(profile_type)}")
        sql = f"""
            CREATE INDEX IF NOT EXISTS {idx_name}
            ON strategy_vector_profile_store
            USING hnsw ((embedding::vector({resolved_dim})) {opclass})
            WHERE {' AND '.join(where_clauses)}
        """
        async with self.acquire() as conn:
            await conn.execute(sql)
        return idx_name

    async def list_strategy_vector_hnsw_indexes(
        self,
        index_name: Optional[str] = None,
        index_version: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT schemaname, tablename, indexname, indexdef
                FROM pg_indexes
                WHERE tablename IN ('strategy_vector_profile_store', 'strategy_vector_index_item_store')
                  AND indexdef ILIKE '%USING hnsw%'
                ORDER BY tablename, indexname
                LIMIT $1
                """,
                max(1, min(int(limit or 200), 1000)),
            )
        items = [dict(row) for row in rows]
        if index_name:
            quoted = self._sql_quote(index_name)
            items = [row for row in items if quoted in str(row.get('indexdef') or '')]
        if index_version:
            quoted = self._sql_quote(index_version)
            items = [row for row in items if quoted in str(row.get('indexdef') or '')]
        return items

    # ------------------------------------------------------------------
    # health check
    # ------------------------------------------------------------------

    async def get_strategy_vector_health(
        self,
        index_name: str = 'strategy_behavior',
        limit_versions: int = 20,
        include_hnsw_indexes: bool = False,
    ) -> dict:
        async with self.acquire() as conn:
            ext = await conn.fetchrow(
                "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"
            ) if getattr(self, 'supports_pgvector', lambda: False)() else None
            table_flags = {
                'strategy_vector_profiles': bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'strategy_vector_profiles')")),
                'strategy_vector_profile_store': bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'strategy_vector_profile_store')")),
                'strategy_vector_index_snapshots': bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'strategy_vector_index_snapshots')")),
                'strategy_vector_index_items': bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'strategy_vector_index_items')")),
                'strategy_vector_index_item_store': bool(await conn.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'strategy_vector_index_item_store')")),
            }
            counts = {
                'profiles': int(await conn.fetchval("SELECT COUNT(*) FROM strategy_vector_profiles WHERE index_name = $1", index_name) or 0),
                'profile_store': int(await conn.fetchval("SELECT COUNT(*) FROM strategy_vector_profile_store WHERE index_name = $1", index_name) or 0) if table_flags['strategy_vector_profile_store'] else 0,
                'index_snapshots': int(await conn.fetchval("SELECT COUNT(*) FROM strategy_vector_index_snapshots WHERE index_name = $1", index_name) or 0),
                'index_items': int(await conn.fetchval("SELECT COUNT(*) FROM strategy_vector_index_items WHERE index_name = $1", index_name) or 0),
                'index_item_store': int(await conn.fetchval("SELECT COUNT(*) FROM strategy_vector_index_item_store WHERE index_name = $1", index_name) or 0) if table_flags['strategy_vector_index_item_store'] else 0,
            }
            profile_store_count_sql = (
                "COALESCE((SELECT COUNT(*) FROM strategy_vector_profile_store ps WHERE ps.index_name = $1 AND ps.index_version = v.index_version), 0)"
                if table_flags['strategy_vector_profile_store']
                else "0"
            )
            index_item_store_count_sql = (
                "COALESCE((SELECT COUNT(*) FROM strategy_vector_index_item_store is2 WHERE is2.index_name = $1 AND is2.index_version = v.index_version), 0)"
                if table_flags['strategy_vector_index_item_store']
                else "0"
            )
            version_rows = await conn.fetch(
                f"""
                WITH versions AS (
                    SELECT index_version, MAX(last_seen) AS last_seen
                    FROM (
                        SELECT index_version, MAX(created_at) AS last_seen
                        FROM vector_index_registry
                        WHERE index_name = $1
                        GROUP BY index_version
                        UNION ALL
                        SELECT index_version, MAX(created_at) AS last_seen
                        FROM strategy_vector_index_snapshots
                        WHERE index_name = $1
                        GROUP BY index_version
                        UNION ALL
                        SELECT index_version, MAX(updated_at) AS last_seen
                        FROM strategy_vector_profiles
                        WHERE index_name = $1
                        GROUP BY index_version
                        UNION ALL
                        SELECT index_version, MAX(created_at) AS last_seen
                        FROM strategy_vector_index_items
                        WHERE index_name = $1
                        GROUP BY index_version
                    ) v
                    GROUP BY index_version
                )
                SELECT v.index_version,
                       v.last_seen,
                       r.status AS registry_status,
                       r.backend AS registry_backend,
                       r.sample_count,
                       s.status AS snapshot_status,
                       s.backend AS snapshot_backend,
                       s.profile_count,
                       s.bucket_count,
                       s.vector_dim,
                       COALESCE((SELECT COUNT(*) FROM strategy_vector_profiles p WHERE p.index_name = $1 AND p.index_version = v.index_version), 0) AS profile_rows,
                       {profile_store_count_sql} AS profile_store_rows,
                       COALESCE((SELECT COUNT(*) FROM strategy_vector_index_items i WHERE i.index_name = $1 AND i.index_version = v.index_version), 0) AS index_item_rows,
                       {index_item_store_count_sql} AS index_item_store_rows
                FROM versions v
                LEFT JOIN LATERAL (
                    SELECT * FROM vector_index_registry r
                    WHERE r.index_name = $1 AND r.index_version = v.index_version
                    ORDER BY COALESCE(r.activated_at, r.built_at, r.created_at) DESC
                    LIMIT 1
                ) r ON TRUE
                LEFT JOIN LATERAL (
                    SELECT * FROM strategy_vector_index_snapshots s
                    WHERE s.index_name = $1 AND s.index_version = v.index_version
                    ORDER BY COALESCE(s.activated_at, s.built_at, s.created_at) DESC
                    LIMIT 1
                ) s ON TRUE
                ORDER BY COALESCE(s.activated_at, s.built_at, r.activated_at, r.built_at, v.last_seen) DESC NULLS LAST
                LIMIT $2
                """,
                index_name,
                max(1, min(int(limit_versions or 20), 200)),
            )
            latest_snapshot = await conn.fetchrow(
                """
                SELECT index_name, index_version, status, profile_count, bucket_count, vector_dim, backend, built_at, activated_at, created_at
                FROM strategy_vector_index_snapshots
                WHERE index_name = $1
                ORDER BY COALESCE(activated_at, built_at, created_at) DESC
                LIMIT 1
                """,
                index_name,
            )
        hnsw_indexes = await self.list_strategy_vector_hnsw_indexes(index_name=index_name, limit=500) if include_hnsw_indexes else []
        latest_snapshot_dict = dict(latest_snapshot) if latest_snapshot else None
        latest_snapshot_version = str((latest_snapshot_dict or {}).get('index_version') or '')
        versions = [dict(row) for row in version_rows]

        def _version_sort_key(item: dict) -> tuple:
            last_seen = self._coerce_timestamp(item.get('last_seen'))
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            item['last_seen'] = last_seen
            version = str(item.get('index_version') or '')
            priority = 3
            if latest_snapshot_version and version == latest_snapshot_version:
                priority = 0
            elif str(item.get('snapshot_status') or '').lower() == 'active':
                priority = 1
            elif str(item.get('registry_status') or '').lower() == 'active':
                priority = 2
            return (priority, -(last_seen.astimezone(timezone.utc).timestamp() if last_seen else 0.0), version)

        versions.sort(key=_version_sort_key)
        return {
            'index_name': index_name,
            'backend': getattr(self, 'get_vector_backend', lambda: 'index')(),
            'pgvector_enabled': bool(getattr(self, 'supports_pgvector', lambda: False)()),
            'pgvector_extension': dict(ext) if ext else None,
            'tables': table_flags,
            'counts': counts,
            'latest_snapshot': latest_snapshot_dict,
            'versions': versions,
            'hnsw_indexes': hnsw_indexes,
            'hnsw_index_count': len(hnsw_indexes),
            'recommended_cleanup_versions': [item.get('index_version') for item in versions[1:] if item.get('index_version')],
        }

    # ------------------------------------------------------------------
    # cleanup
    # ------------------------------------------------------------------

    async def cleanup_strategy_vector_history(
        self,
        index_name: str = 'strategy_behavior',
        keep_versions: int = 1,
        dry_run: bool = True,
        cleanup_hnsw: bool = True,
        limit_versions: int = 200,
        protect_versions: Optional[List[str]] = None,
    ) -> dict:
        health = await self.get_strategy_vector_health(index_name=index_name, limit_versions=limit_versions, include_hnsw_indexes=cleanup_hnsw)
        versions = [item for item in list(health.get('versions') or []) if item.get('index_version')]
        latest_snapshot_version = str((health.get('latest_snapshot') or {}).get('index_version') or '').strip()
        keep_total = max(0, int(keep_versions or 0))
        protected: List[str] = []
        if latest_snapshot_version:
            protected.append(latest_snapshot_version)
        protected_limit = max(keep_total, 1 if latest_snapshot_version else 0)
        for item in versions:
            version = str(item.get('index_version') or '').strip()
            if not version or version in protected:
                continue
            if len(protected) >= protected_limit:
                break
            protected.append(version)
        protected.extend(str(item) for item in list(protect_versions or []) if str(item).strip())
        protected_set = {item for item in protected if item}
        target_versions = [item for item in versions if str(item.get('index_version')) not in protected_set]
        index_rows = list(health.get('hnsw_indexes') or []) if cleanup_hnsw else []
        indexes_to_drop = [
            row for row in index_rows
            if any(self._sql_quote(item.get('index_version')) in str(row.get('indexdef') or '') for item in target_versions)
        ]
        summary = {
            'index_name': index_name,
            'dry_run': bool(dry_run),
            'keep_versions': max(0, int(keep_versions or 0)),
            'protected_versions': sorted(protected_set),
            'target_versions': [item.get('index_version') for item in target_versions],
            'hnsw_indexes_to_drop': [row.get('indexname') for row in indexes_to_drop],
            'deleted': {
                'vector_index_registry': 0,
                'vector_index_snapshots': 0,
                'vector_profiles': 0,
                'vector_profile_store': 0,
                'vector_index_items': 0,
                'vector_index_item_store': 0,
                'hnsw_indexes': 0,
            },
            'version_details': target_versions,
        }
        if dry_run or not target_versions:
            return summary
        async with self.acquire() as conn:
            for item in target_versions:
                version = str(item.get('index_version') or '')
                if not version:
                    continue
                if cleanup_hnsw:
                    for row in indexes_to_drop:
                        if self._sql_quote(version) not in str(row.get('indexdef') or ''):
                            continue
                        await conn.execute(f"DROP INDEX IF EXISTS {row['indexname']}")
                        summary['deleted']['hnsw_indexes'] += 1
                if health.get('tables', {}).get('strategy_vector_index_item_store'):
                    summary['deleted']['vector_index_item_store'] += int((await conn.execute(
                        "DELETE FROM strategy_vector_index_item_store WHERE index_name = $1 AND index_version = $2",
                        index_name,
                        version,
                    )).split()[-1])
                summary['deleted']['vector_index_items'] += int((await conn.execute(
                    "DELETE FROM strategy_vector_index_items WHERE index_name = $1 AND index_version = $2",
                    index_name,
                    version,
                )).split()[-1])
                if health.get('tables', {}).get('strategy_vector_profile_store'):
                    summary['deleted']['vector_profile_store'] += int((await conn.execute(
                        "DELETE FROM strategy_vector_profile_store WHERE index_name = $1 AND index_version = $2",
                        index_name,
                        version,
                    )).split()[-1])
                summary['deleted']['vector_profiles'] += int((await conn.execute(
                    "DELETE FROM strategy_vector_profiles WHERE index_name = $1 AND index_version = $2",
                    index_name,
                    version,
                )).split()[-1])
                summary['deleted']['vector_index_snapshots'] += int((await conn.execute(
                    "DELETE FROM strategy_vector_index_snapshots WHERE index_name = $1 AND index_version = $2",
                    index_name,
                    version,
                )).split()[-1])
                summary['deleted']['vector_index_registry'] += int((await conn.execute(
                    "DELETE FROM vector_index_registry WHERE index_name = $1 AND index_version = $2",
                    index_name,
                    version,
                )).split()[-1])
        return summary
