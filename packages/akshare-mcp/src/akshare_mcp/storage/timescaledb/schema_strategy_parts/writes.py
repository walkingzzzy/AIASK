    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_task_evidence_event ON strategy_factory_task_evidence(event_id, theme_code, created_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_market_internals (
            id SERIAL PRIMARY KEY,
            snapshot_date DATE NOT NULL UNIQUE,
            engine TEXT DEFAULT 'local_db_rule_v1',
            symbol_count INTEGER DEFAULT 0,
            trend_up_count INTEGER DEFAULT 0,
            trend_down_count INTEGER DEFAULT 0,
            avg_return_5d DOUBLE PRECISION DEFAULT 0,
            avg_return_20d DOUBLE PRECISION DEFAULT 0,
            avg_volume_ratio DOUBLE PRECISION DEFAULT 1,
            breadth_score DOUBLE PRECISION DEFAULT 0,
            margin_proxy_5d_change_pct DOUBLE PRECISION DEFAULT 0,
            hot_sectors JSONB DEFAULT '[]'::jsonb,
            cold_sectors JSONB DEFAULT '[]'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_market_internals_date ON strategy_factory_market_internals(snapshot_date DESC);"
    )
