    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_task_evidence_event ON strategy_factory_task_evidence(event_id, theme_code, created_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_market_internals (
            id INTEGER PRIMARY KEY,
            snapshot_date TEXT NOT NULL UNIQUE,
            engine TEXT DEFAULT 'local_db_rule_v1',
            symbol_count INTEGER DEFAULT 0,
            trend_up_count INTEGER DEFAULT 0,
            trend_down_count INTEGER DEFAULT 0,
            avg_return_5d REAL DEFAULT 0,
            avg_return_20d REAL DEFAULT 0,
            avg_volume_ratio REAL DEFAULT 1,
            breadth_score REAL DEFAULT 0,
            margin_proxy_5d_change_pct REAL DEFAULT 0,
            hot_sectors TEXT DEFAULT '[]',
            cold_sectors TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_market_internals_date ON strategy_factory_market_internals(snapshot_date DESC);"
    )
