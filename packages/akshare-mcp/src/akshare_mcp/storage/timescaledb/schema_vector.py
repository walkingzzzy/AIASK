"""Unified vector-layer schema for market / quant / strategy derived objects."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


async def _seed_vector_collection(
    conn,
    *,
    collection_name: str,
    entity_family: str,
    backend: str,
    metric: str,
    model_id: str,
    vector_dim: int,
    normalization: str = "unit",
    status: str = "active",
    metadata: dict | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO vector_collections (
            collection_name, entity_family, backend, metric, model_id,
            vector_dim, normalization, status, metadata, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW(), NOW())
        ON CONFLICT (collection_name) DO NOTHING
        """,
        collection_name,
        entity_family,
        backend,
        metric,
        model_id,
        int(vector_dim),
        normalization,
        status,
        json.dumps(metadata or {}, ensure_ascii=False, default=str),
    )


async def init_vector_tables(conn, pgvector_enabled: bool) -> None:
    """Create / migrate generic vector-layer tables."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_collections (
            id SERIAL PRIMARY KEY,
            collection_name TEXT NOT NULL UNIQUE,
            entity_family TEXT NOT NULL,
            backend TEXT NOT NULL DEFAULT 'pgvector',
            metric TEXT NOT NULL DEFAULT 'cosine',
            model_id TEXT NOT NULL,
            vector_dim INTEGER NOT NULL,
            normalization TEXT NOT NULL DEFAULT 'unit',
            status TEXT NOT NULL DEFAULT 'active',
            active_version TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_vector_collections_family
            ON vector_collections(entity_family, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vector_collections_model
            ON vector_collections(model_id, vector_dim, metric);

        CREATE TABLE IF NOT EXISTS vector_profiles (
            id BIGSERIAL PRIMARY KEY,
            collection_name TEXT NOT NULL REFERENCES vector_collections(collection_name) ON DELETE CASCADE,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            stock_code TEXT,
            profile_type TEXT,
            model_id TEXT NOT NULL,
            vector_dim INTEGER NOT NULL,
            metric TEXT NOT NULL DEFAULT 'cosine',
            version TEXT NOT NULL,
            signature TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (collection_name, entity_type, entity_id, model_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_vector_profiles_lookup
            ON vector_profiles(collection_name, version, profile_type, vector_dim, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vector_profiles_stock
            ON vector_profiles(stock_code, collection_name, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vector_profiles_signature
            ON vector_profiles(signature);
        CREATE INDEX IF NOT EXISTS idx_vector_profiles_metadata_gin
            ON vector_profiles USING GIN(metadata jsonb_path_ops);

        CREATE TABLE IF NOT EXISTS vector_index_snapshots (
            id BIGSERIAL PRIMARY KEY,
            collection_name TEXT NOT NULL REFERENCES vector_collections(collection_name) ON DELETE CASCADE,
            index_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'building',
            model_id TEXT NOT NULL,
            profile_type TEXT,
            metric TEXT NOT NULL DEFAULT 'cosine',
            vector_dim INTEGER NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0,
            bucket_count INTEGER NOT NULL DEFAULT 0,
            index_params JSONB NOT NULL DEFAULT '{}'::jsonb,
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            built_at TIMESTAMPTZ,
            activated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (collection_name, index_version)
        );
        CREATE INDEX IF NOT EXISTS idx_vector_index_snapshots_lookup
            ON vector_index_snapshots(collection_name, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vector_index_snapshots_model
            ON vector_index_snapshots(model_id, vector_dim, metric);

        CREATE TABLE IF NOT EXISTS vector_index_items (
            id BIGSERIAL PRIMARY KEY,
            collection_name TEXT NOT NULL REFERENCES vector_collections(collection_name) ON DELETE CASCADE,
            index_version TEXT NOT NULL,
            profile_id BIGINT REFERENCES vector_profiles(id) ON DELETE CASCADE,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            stock_code TEXT,
            profile_type TEXT,
            model_id TEXT NOT NULL,
            metric TEXT NOT NULL DEFAULT 'cosine',
            vector_dim INTEGER NOT NULL,
            bucket_id TEXT,
            coarse_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (collection_name, index_version, profile_id)
        );
        CREATE INDEX IF NOT EXISTS idx_vector_index_items_lookup
            ON vector_index_items(collection_name, index_version, bucket_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vector_index_items_stock
            ON vector_index_items(stock_code, collection_name, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vector_index_items_metadata_gin
            ON vector_index_items USING GIN(metadata jsonb_path_ops);

        CREATE TABLE IF NOT EXISTS market_documents (
            id BIGSERIAL PRIMARY KEY,
            doc_uid TEXT NOT NULL UNIQUE,
            stock_code TEXT,
            doc_type TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT,
            summary TEXT,
            body TEXT,
            url TEXT,
            author TEXT,
            published_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_market_documents_lookup
            ON market_documents(stock_code, doc_type, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_market_documents_source
            ON market_documents(source, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_market_documents_metadata_gin
            ON market_documents USING GIN(metadata jsonb_path_ops);

        CREATE TABLE IF NOT EXISTS market_doc_chunks (
            id BIGSERIAL PRIMARY KEY,
            doc_id BIGINT NOT NULL REFERENCES market_documents(id) ON DELETE CASCADE,
            chunk_no INTEGER NOT NULL,
            stock_code TEXT,
            doc_type TEXT NOT NULL,
            source TEXT NOT NULL,
            title TEXT,
            chunk_text TEXT NOT NULL,
            token_count INTEGER,
            char_count INTEGER,
            language TEXT DEFAULT 'zh',
            published_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (doc_id, chunk_no)
        );
        CREATE INDEX IF NOT EXISTS idx_market_doc_chunks_lookup
            ON market_doc_chunks(stock_code, doc_type, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_market_doc_chunks_doc
            ON market_doc_chunks(doc_id, chunk_no);
        CREATE INDEX IF NOT EXISTS idx_market_doc_chunks_source
            ON market_doc_chunks(source, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_market_doc_chunks_lexical
            ON market_doc_chunks
            USING GIN (
                to_tsvector('simple', COALESCE(title, '') || ' ' || COALESCE(chunk_text, ''))
            );

        CREATE TABLE IF NOT EXISTS kline_pattern_windows (
            id BIGSERIAL PRIMARY KEY,
            window_uid TEXT NOT NULL UNIQUE,
            stock_code TEXT NOT NULL,
            end_date DATE NOT NULL,
            start_date DATE NOT NULL,
            period TEXT NOT NULL DEFAULT 'daily',
            adjust TEXT NOT NULL DEFAULT '',
            window_size INTEGER NOT NULL,
            vector_method TEXT NOT NULL,
            metric TEXT NOT NULL DEFAULT 'cosine',
            vector_dim INTEGER NOT NULL,
            forward_return_5d DOUBLE PRECISION,
            forward_return_10d DOUBLE PRECISION,
            forward_return_20d DOUBLE PRECISION,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_kline_pattern_windows_lookup
            ON kline_pattern_windows(stock_code, period, adjust, end_date DESC);
        CREATE INDEX IF NOT EXISTS idx_kline_pattern_windows_method
            ON kline_pattern_windows(vector_method, window_size, vector_dim, end_date DESC);
        CREATE INDEX IF NOT EXISTS idx_kline_pattern_windows_metadata_gin
            ON kline_pattern_windows USING GIN(metadata jsonb_path_ops);
        """
    )

    if pgvector_enabled:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_profile_store (
                profile_id BIGINT PRIMARY KEY REFERENCES vector_profiles(id) ON DELETE CASCADE,
                collection_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                stock_code TEXT,
                profile_type TEXT,
                model_id TEXT NOT NULL,
                vector_dim INTEGER NOT NULL,
                metric TEXT NOT NULL DEFAULT 'cosine',
                version TEXT NOT NULL,
                embedding vector NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_vector_profile_store_lookup
                ON vector_profile_store(collection_name, version, profile_type, vector_dim, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_vector_profile_store_stock
                ON vector_profile_store(stock_code, collection_name, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_vector_profile_store_model
                ON vector_profile_store(model_id, vector_dim, metric, version);
            CREATE INDEX IF NOT EXISTS idx_vector_profile_store_metadata_gin
                ON vector_profile_store USING GIN(metadata jsonb_path_ops);

            CREATE TABLE IF NOT EXISTS vector_index_item_store (
                item_id BIGINT PRIMARY KEY REFERENCES vector_index_items(id) ON DELETE CASCADE,
                collection_name TEXT NOT NULL,
                index_version TEXT NOT NULL,
                profile_id BIGINT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                stock_code TEXT,
                profile_type TEXT,
                model_id TEXT NOT NULL,
                metric TEXT NOT NULL DEFAULT 'cosine',
                vector_dim INTEGER NOT NULL,
                bucket_id TEXT,
                embedding vector NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            ALTER TABLE vector_index_item_store
                ADD COLUMN IF NOT EXISTS bucket_id TEXT;
            CREATE INDEX IF NOT EXISTS idx_vector_index_item_store_lookup
                ON vector_index_item_store(collection_name, index_version, profile_type, vector_dim, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_vector_index_item_store_bucket_lookup
                ON vector_index_item_store(collection_name, index_version, bucket_id, profile_type, vector_dim, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_vector_index_item_store_stock
                ON vector_index_item_store(stock_code, collection_name, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_vector_index_item_store_metadata_gin
                ON vector_index_item_store USING GIN(metadata jsonb_path_ops);
            """
        )

    try:
        await _seed_vector_collection(
            conn,
            collection_name="market_doc_chunks",
            entity_family="document_chunk",
            backend="pgvector" if pgvector_enabled else "index",
            metric="cosine",
            model_id="text-embedding-3-small",
            vector_dim=1536,
            metadata={"domain": "market", "notes": "news-notice-research chunks"},
        )
        await _seed_vector_collection(
            conn,
            collection_name="kline_pattern_embeddings",
            entity_family="kline_pattern",
            backend="pgvector" if pgvector_enabled else "index",
            metric="cosine",
            model_id="price_volume_v1",
            vector_dim=120,
            metadata={"domain": "quant", "notes": "fixed-window pattern vectors"},
        )
        await _seed_vector_collection(
            conn,
            collection_name="stock_profile_embeddings",
            entity_family="stock_profile",
            backend="pgvector" if pgvector_enabled else "index",
            metric="cosine",
            model_id="stock-profile-v1",
            vector_dim=11,
            metadata={"domain": "market-quant", "notes": "derived stock profile vectors"},
        )
        await _seed_vector_collection(
            conn,
            collection_name="factor_candidate_embeddings",
            entity_family="factor_candidate",
            backend="pgvector" if pgvector_enabled else "index",
            metric="cosine",
            model_id="factor-memory-v1",
            vector_dim=128,
            metadata={"domain": "quant-research", "notes": "factor candidate memory"},
        )
        await _seed_vector_collection(
            conn,
            collection_name="strategy_behavior_embeddings",
            entity_family="strategy_behavior",
            backend="pgvector" if pgvector_enabled else "index",
            metric="cosine",
            model_id="strategy-behavior-v1",
            vector_dim=120,
            metadata={"domain": "strategy", "notes": "strategy behavior vectors"},
        )
    except Exception as exc:
        logger.warning("vector collection seed skipped: %s", exc)

    logger.info("Vector tables initialized (pgvector=%s)", pgvector_enabled)
