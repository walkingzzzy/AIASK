
    await conn.execute("""
        ALTER TABLE strategy_incubation_metrics
        ADD COLUMN IF NOT EXISTS hit_rate_lcb_5d REAL;
        ALTER TABLE strategy_incubation_metrics
        ADD COLUMN IF NOT EXISTS skill_lcb_5d REAL;
        ALTER TABLE strategy_incubation_metrics
        ADD COLUMN IF NOT EXISTS effective_n_5d INTEGER;
        ALTER TABLE strategy_incubation_metrics
        ADD COLUMN IF NOT EXISTS recent_hit_rate_5d REAL;
        ALTER TABLE strategy_incubation_metrics
        ADD COLUMN IF NOT EXISTS recent_skill_lcb_5d REAL;
        ALTER TABLE strategy_incubation_metrics
        ADD COLUMN IF NOT EXISTS stability_gap_5d REAL;
    """)

    # Compat: backfill index_name for vector profiles
    await conn.execute("""
        ALTER TABLE strategy_vector_profiles
        ADD COLUMN IF NOT EXISTS index_name TEXT DEFAULT 'strategy_behavior';
    """)
    await conn.execute("""
        ALTER TABLE strategy_vector_profiles
        ADD COLUMN IF NOT EXISTS model_id TEXT DEFAULT 'strategy_behavior_v1';
    """)
    await conn.execute("""
        ALTER TABLE strategy_vector_profiles
        ADD COLUMN IF NOT EXISTS collection_name TEXT DEFAULT 'strategy_behavior_embeddings';
    """)
    await conn.execute("""
        UPDATE strategy_vector_profiles
        SET index_name = COALESCE(NULLIF(index_name, ''), json_extract(metadata, '$.index_name'), 'strategy_behavior')
        WHERE index_name IS NULL OR index_name = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_profiles
        SET model_id = COALESCE(NULLIF(model_id, ''), json_extract(metadata, '$.model_id'), 'strategy_behavior_v1')
        WHERE model_id IS NULL OR model_id = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_profiles
        SET collection_name = COALESCE(NULLIF(collection_name, ''), json_extract(metadata, '$.collection_name'), 'strategy_behavior_embeddings')
        WHERE collection_name IS NULL OR collection_name = '';
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_profiles_index_name
            ON strategy_vector_profiles(index_name, index_version, created_at DESC);
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_profiles_model
            ON strategy_vector_profiles(model_id, collection_name, index_version, created_at DESC);
    """)
    await conn.execute("""
        ALTER TABLE strategy_vector_index_snapshots
        ADD COLUMN IF NOT EXISTS model_id TEXT DEFAULT 'strategy_behavior_v1';
    """)
    await conn.execute("""
        ALTER TABLE strategy_vector_index_snapshots
        ADD COLUMN IF NOT EXISTS collection_name TEXT DEFAULT 'strategy_behavior_embeddings';
    """)
    await conn.execute("""
        UPDATE strategy_vector_index_snapshots
        SET model_id = COALESCE(NULLIF(model_id, ''), json_extract(metadata, '$.model_id'), 'strategy_behavior_v1')
        WHERE model_id IS NULL OR model_id = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_index_snapshots
        SET collection_name = COALESCE(NULLIF(collection_name, ''), json_extract(metadata, '$.collection_name'), 'strategy_behavior_embeddings')
        WHERE collection_name IS NULL OR collection_name = '';
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_snapshots_model
            ON strategy_vector_index_snapshots(model_id, collection_name, index_version, created_at DESC);
    """)
    await conn.execute("""
        ALTER TABLE strategy_vector_index_items
        ADD COLUMN IF NOT EXISTS model_id TEXT DEFAULT 'strategy_behavior_v1';
    """)
    await conn.execute("""
        ALTER TABLE strategy_vector_index_items
        ADD COLUMN IF NOT EXISTS collection_name TEXT DEFAULT 'strategy_behavior_embeddings';
    """)
    await conn.execute("""
        UPDATE strategy_vector_index_items
        SET model_id = COALESCE(NULLIF(model_id, ''), json_extract(metadata, '$.model_id'), 'strategy_behavior_v1')
        WHERE model_id IS NULL OR model_id = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_index_items
        SET collection_name = COALESCE(NULLIF(collection_name, ''), json_extract(metadata, '$.collection_name'), 'strategy_behavior_embeddings')
        WHERE collection_name IS NULL OR collection_name = '';
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_items_model
            ON strategy_vector_index_items(model_id, collection_name, index_version, created_at DESC);
    """)
    await conn.execute("""
        ALTER TABLE strategy_vector_index_snapshots
        DROP CONSTRAINT IF EXISTS strategy_vector_index_snapshots_index_name_index_version_key;
    """)

    # sqlite_python-specific tables (gated)
    if sqlite_python_enabled:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_vector_profile_store (
                profile_id INTEGER PRIMARY KEY REFERENCES strategy_vector_profiles(id) ON DELETE CASCADE,
                strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
                index_name TEXT NOT NULL DEFAULT 'strategy_behavior',
                collection_name TEXT NOT NULL DEFAULT 'strategy_behavior_embeddings',
                index_version TEXT,
                profile_type TEXT,
                vector_method TEXT,
                model_id TEXT DEFAULT 'strategy_behavior_v1',
                metric TEXT DEFAULT 'cosine',
                vector_dim INTEGER DEFAULT 0,
                embedding TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_strategy_vector_profile_store_lookup
                ON strategy_vector_profile_store(index_name, index_version, profile_type, vector_dim);
            CREATE INDEX IF NOT EXISTS idx_strategy_vector_profile_store_sid
                ON strategy_vector_profile_store(strategy_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS strategy_vector_index_item_store (
                item_id INTEGER PRIMARY KEY REFERENCES strategy_vector_index_items(id) ON DELETE CASCADE,
                index_name TEXT NOT NULL,
                index_version TEXT NOT NULL,
                collection_name TEXT NOT NULL DEFAULT 'strategy_behavior_embeddings',
                strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
                profile_id INTEGER,
                profile_type TEXT,
                vector_method TEXT,
                model_id TEXT DEFAULT 'strategy_behavior_v1',
                metric TEXT DEFAULT 'cosine',
                vector_dim INTEGER DEFAULT 0,
                embedding TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_item_store_lookup
                ON strategy_vector_index_item_store(index_name, index_version, profile_type, vector_dim);
            CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_item_store_sid
                ON strategy_vector_index_item_store(strategy_id, updated_at DESC);
        """)
        await conn.execute("""
            ALTER TABLE strategy_vector_profile_store
            ADD COLUMN IF NOT EXISTS model_id TEXT DEFAULT 'strategy_behavior_v1';
        """)
        await conn.execute("""
            ALTER TABLE strategy_vector_profile_store
            ADD COLUMN IF NOT EXISTS collection_name TEXT DEFAULT 'strategy_behavior_embeddings';
        """)
        await conn.execute("""
            UPDATE strategy_vector_profile_store
            SET model_id = COALESCE(NULLIF(model_id, ''), json_extract(metadata, '$.model_id'), 'strategy_behavior_v1')
            WHERE model_id IS NULL OR model_id = '';
        """)
        await conn.execute("""
            UPDATE strategy_vector_profile_store
            SET collection_name = COALESCE(NULLIF(collection_name, ''), json_extract(metadata, '$.collection_name'), 'strategy_behavior_embeddings')
            WHERE collection_name IS NULL OR collection_name = '';
        """)
        await conn.execute("""
            ALTER TABLE strategy_vector_index_item_store
            ADD COLUMN IF NOT EXISTS model_id TEXT DEFAULT 'strategy_behavior_v1';
        """)
        await conn.execute("""
            ALTER TABLE strategy_vector_index_item_store
            ADD COLUMN IF NOT EXISTS collection_name TEXT DEFAULT 'strategy_behavior_embeddings';
        """)
        await conn.execute("""
            UPDATE strategy_vector_index_item_store
            SET model_id = COALESCE(NULLIF(model_id, ''), json_extract(metadata, '$.model_id'), 'strategy_behavior_v1')
            WHERE model_id IS NULL OR model_id = '';
        """)
        await conn.execute("""
            UPDATE strategy_vector_index_item_store
            SET collection_name = COALESCE(NULLIF(collection_name, ''), json_extract(metadata, '$.collection_name'), 'strategy_behavior_embeddings')
            WHERE collection_name IS NULL OR collection_name = '';
        """)

    logger.info("Strategy tables initialized (sqlite_python=%s)", sqlite_python_enabled)
