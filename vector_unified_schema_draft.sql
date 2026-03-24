-- Unified vector layer schema draft
-- Date: 2026-03-24
-- Scope:
--   1. Generic vector collection governance
--   2. Generic profile archive + pgvector store
--   3. Snapshot / ANN item governance
--   4. Market document chunking support
--   5. K-line pattern window support
--
-- Notes:
--   - This is a draft for implementation planning, not an in-place migration script.
--   - HNSW indexes for each collection/version/dim should be created dynamically by service code.
--   - Existing strategy_vector_* tables can coexist during phase 1.

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------------
-- 1. Collection registry
-- ------------------------------------------------------------------

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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_vector_collections_metric
        CHECK (metric IN ('cosine', 'ip', 'l2')),
    CONSTRAINT chk_vector_collections_norm
        CHECK (normalization IN ('none', 'unit')),
    CONSTRAINT chk_vector_collections_dim
        CHECK (vector_dim > 0)
);

CREATE INDEX IF NOT EXISTS idx_vector_collections_family
    ON vector_collections(entity_family, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_collections_model
    ON vector_collections(model_id, vector_dim, metric);

-- ------------------------------------------------------------------
-- 2. Generic profile archive
-- ------------------------------------------------------------------

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
    CONSTRAINT chk_vector_profiles_metric
        CHECK (metric IN ('cosine', 'ip', 'l2')),
    CONSTRAINT chk_vector_profiles_dim
        CHECK (vector_dim > 0),
    CONSTRAINT uq_vector_profiles_unique
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

-- ------------------------------------------------------------------
-- 3. Generic pgvector store
-- ------------------------------------------------------------------

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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_vector_profile_store_metric
        CHECK (metric IN ('cosine', 'ip', 'l2')),
    CONSTRAINT chk_vector_profile_store_dim
        CHECK (vector_dim > 0)
);

CREATE INDEX IF NOT EXISTS idx_vector_profile_store_lookup
    ON vector_profile_store(collection_name, version, profile_type, vector_dim, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_profile_store_stock
    ON vector_profile_store(stock_code, collection_name, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_profile_store_model
    ON vector_profile_store(model_id, vector_dim, metric, version);

CREATE INDEX IF NOT EXISTS idx_vector_profile_store_metadata_gin
    ON vector_profile_store USING GIN(metadata jsonb_path_ops);

-- ------------------------------------------------------------------
-- 4. Snapshot / registry
-- ------------------------------------------------------------------

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
    CONSTRAINT uq_vector_index_snapshots
        UNIQUE (collection_name, index_version),
    CONSTRAINT chk_vector_index_snapshots_metric
        CHECK (metric IN ('cosine', 'ip', 'l2')),
    CONSTRAINT chk_vector_index_snapshots_dim
        CHECK (vector_dim > 0)
);

CREATE INDEX IF NOT EXISTS idx_vector_index_snapshots_lookup
    ON vector_index_snapshots(collection_name, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_index_snapshots_model
    ON vector_index_snapshots(model_id, vector_dim, metric);

-- ------------------------------------------------------------------
-- 5. ANN item archive
-- ------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS vector_index_items (
    id BIGSERIAL PRIMARY KEY,
    collection_name TEXT NOT NULL,
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
    CONSTRAINT uq_vector_index_items_unique
        UNIQUE (collection_name, index_version, profile_id),
    CONSTRAINT chk_vector_index_items_metric
        CHECK (metric IN ('cosine', 'ip', 'l2')),
    CONSTRAINT chk_vector_index_items_dim
        CHECK (vector_dim > 0)
);

CREATE INDEX IF NOT EXISTS idx_vector_index_items_lookup
    ON vector_index_items(collection_name, index_version, bucket_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_index_items_stock
    ON vector_index_items(stock_code, collection_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_index_items_metadata_gin
    ON vector_index_items USING GIN(metadata jsonb_path_ops);

-- ------------------------------------------------------------------
-- 6. ANN item pgvector store
-- ------------------------------------------------------------------

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
    embedding vector NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_vector_index_item_store_metric
        CHECK (metric IN ('cosine', 'ip', 'l2')),
    CONSTRAINT chk_vector_index_item_store_dim
        CHECK (vector_dim > 0)
);

CREATE INDEX IF NOT EXISTS idx_vector_index_item_store_lookup
    ON vector_index_item_store(collection_name, index_version, profile_type, vector_dim, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_index_item_store_stock
    ON vector_index_item_store(stock_code, collection_name, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_vector_index_item_store_metadata_gin
    ON vector_index_item_store USING GIN(metadata jsonb_path_ops);

-- ------------------------------------------------------------------
-- 7. Market document raw layer
-- ------------------------------------------------------------------

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

-- ------------------------------------------------------------------
-- 8. Market document chunk layer
-- ------------------------------------------------------------------

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
    CONSTRAINT uq_market_doc_chunks
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
        to_tsvector(
            'simple',
            COALESCE(title, '') || ' ' || COALESCE(chunk_text, '')
        )
    );

-- ------------------------------------------------------------------
-- 9. K-line pattern raw layer
-- ------------------------------------------------------------------

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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_kline_pattern_windows_metric
        CHECK (metric IN ('cosine', 'ip', 'l2')),
    CONSTRAINT chk_kline_pattern_windows_size
        CHECK (window_size > 1),
    CONSTRAINT chk_kline_pattern_windows_dim
        CHECK (vector_dim > 0)
);

CREATE INDEX IF NOT EXISTS idx_kline_pattern_windows_lookup
    ON kline_pattern_windows(stock_code, period, adjust, end_date DESC);

CREATE INDEX IF NOT EXISTS idx_kline_pattern_windows_method
    ON kline_pattern_windows(vector_method, window_size, vector_dim, end_date DESC);

CREATE INDEX IF NOT EXISTS idx_kline_pattern_windows_metadata_gin
    ON kline_pattern_windows USING GIN(metadata jsonb_path_ops);

-- ------------------------------------------------------------------
-- 10. Suggested collection seeds
-- ------------------------------------------------------------------

INSERT INTO vector_collections (
    collection_name,
    entity_family,
    backend,
    metric,
    model_id,
    vector_dim,
    normalization,
    status,
    metadata
)
VALUES
    (
        'market_doc_chunks',
        'document_chunk',
        'pgvector',
        'cosine',
        'text-embedding-3-small',
        1536,
        'unit',
        'active',
        '{"domain":"market","notes":"news-notice-research chunks"}'::jsonb
    ),
    (
        'kline_pattern_embeddings',
        'kline_pattern',
        'pgvector',
        'cosine',
        'price_volume_v1',
        120,
        'unit',
        'active',
        '{"domain":"quant","notes":"fixed-window pattern vectors"}'::jsonb
    ),
    (
        'stock_profile_embeddings',
        'stock_profile',
        'pgvector',
        'cosine',
        'stock-profile-v1',
        512,
        'unit',
        'active',
        '{"domain":"market-quant","notes":"derived stock profile vectors"}'::jsonb
    ),
    (
        'factor_candidate_embeddings',
        'factor_candidate',
        'pgvector',
        'cosine',
        'factor-memory-v1',
        512,
        'unit',
        'active',
        '{"domain":"quant-research","notes":"factor candidate memory"}'::jsonb
    ),
    (
        'strategy_behavior_embeddings',
        'strategy_behavior',
        'pgvector',
        'cosine',
        'strategy-behavior-v1',
        120,
        'unit',
        'active',
        '{"domain":"strategy","notes":"existing strategy vectors should migrate here"}'::jsonb
    )
ON CONFLICT (collection_name) DO NOTHING;

-- ------------------------------------------------------------------
-- 11. Example dynamic ANN indexes
-- ------------------------------------------------------------------

-- Example for market_doc_chunks / 1536 dim / cosine:
-- CREATE INDEX IF NOT EXISTS idx_vps_hnsw_market_doc_chunks_v1_1536_cosine
-- ON vector_profile_store
-- USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
-- WHERE collection_name = 'market_doc_chunks'
--   AND version = 'v1'
--   AND vector_dim = 1536;

-- Example for kline_pattern_embeddings / 120 dim / cosine:
-- CREATE INDEX IF NOT EXISTS idx_vps_hnsw_kline_patterns_v1_120_cosine
-- ON vector_profile_store
-- USING hnsw ((embedding::vector(120)) vector_cosine_ops)
-- WHERE collection_name = 'kline_pattern_embeddings'
--   AND version = 'v1'
--   AND vector_dim = 120;

-- Example ANN item store index:
-- CREATE INDEX IF NOT EXISTS idx_vis_hnsw_market_doc_chunks_v1_1536_cosine
-- ON vector_index_item_store
-- USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
-- WHERE collection_name = 'market_doc_chunks'
--   AND index_version = 'v1'
--   AND vector_dim = 1536;
