    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_quality_reports_sid ON strategy_quality_reports(strategy_id, updated_at DESC);"
    )

    # 34. 策略状态事件（轻量 append-only 审计流）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_status_events (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            from_status TEXT,
            to_status TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'status_change',
            actor_id TEXT DEFAULT 'system',
            reason TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_status_events_sid ON strategy_status_events(strategy_id, created_at DESC);"
    )
    await conn.execute("""
        UPDATE strategy_status_events SET from_status = 'listed' WHERE from_status = 'published';
    """)
    await conn.execute("""
        UPDATE strategy_status_events SET to_status = 'listed' WHERE to_status = 'published';
    """)
    await conn.execute("""
        DELETE FROM strategy_status_events
        WHERE event_type = 'status_change'
          AND from_status = 'listed'
          AND to_status = 'listed';
    """)

    # 34.1 策略领域事件（通用 append-only 事件流 / outbox 基础）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_domain_events (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
            aggregate_type TEXT NOT NULL DEFAULT 'strategy',
            aggregate_id TEXT,
            event_type TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            severity TEXT DEFAULT 'info',
            correlation_id TEXT,
            payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_domain_events_sid ON strategy_domain_events(strategy_id, created_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_domain_events_aggregate ON strategy_domain_events(aggregate_type, aggregate_id, created_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_domain_events_type ON strategy_domain_events(event_type, created_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_domain_events_correlation ON strategy_domain_events(correlation_id, created_at DESC);"
    )

    # 35. 策略工厂运行历史
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_runs (
            id SERIAL PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            elapsed_seconds DOUBLE PRECISION DEFAULT 0,
            execution_mode TEXT DEFAULT 'legacy_primary',
            engine_version TEXT DEFAULT 'strategy_factory.v2',
            parity_status TEXT,
            summary JSONB DEFAULT '{}'::jsonb,
            stages JSONB DEFAULT '{}'::jsonb,
            snapshot_summary JSONB DEFAULT '{}'::jsonb,
            artifact_refs JSONB DEFAULT '[]'::jsonb,
            parity_result JSONB DEFAULT '{}'::jsonb,
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "ALTER TABLE strategy_factory_runs ADD COLUMN IF NOT EXISTS execution_mode TEXT DEFAULT 'legacy_primary';"
    )
    await conn.execute(
        "ALTER TABLE strategy_factory_runs ADD COLUMN IF NOT EXISTS engine_version TEXT DEFAULT 'strategy_factory.v2';"
    )
    await conn.execute(
        "ALTER TABLE strategy_factory_runs ADD COLUMN IF NOT EXISTS parity_status TEXT;"
    )
    await conn.execute(
        "ALTER TABLE strategy_factory_runs ADD COLUMN IF NOT EXISTS artifact_refs JSONB DEFAULT '[]'::jsonb;"
    )
    await conn.execute(
        "ALTER TABLE strategy_factory_runs ADD COLUMN IF NOT EXISTS parity_result JSONB DEFAULT '{}'::jsonb;"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_runs_started_at ON strategy_factory_runs(started_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_runs_status ON strategy_factory_runs(status, started_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_runs_execution_mode ON strategy_factory_runs(execution_mode, started_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_run_artifacts (
            id SERIAL PRIMARY KEY,
            run_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_version TEXT NOT NULL,
            payload_json JSONB DEFAULT '{}'::jsonb,
            payload_hash TEXT,
            storage_mode TEXT DEFAULT 'inline_json',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_run_artifacts_run_id ON strategy_factory_run_artifacts(run_id, created_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_run_artifacts_type ON strategy_factory_run_artifacts(artifact_type, created_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_dispatches (
            id SERIAL PRIMARY KEY,
            dispatch_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            execution_mode TEXT DEFAULT 'legacy_primary',
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            run_id TEXT,
            message TEXT,
            error TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_dispatches_requested_at ON strategy_factory_dispatches(requested_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_dispatches_status ON strategy_factory_dispatches(status, requested_at DESC);"
    )

    # 35.1 策略工厂事件簇 / 主题 / 暴露 / 信号
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_event_clusters (
            id SERIAL PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT DEFAULT 'macro',
            event_name TEXT NOT NULL,
            event_scope TEXT DEFAULT 'market',
            summary TEXT,
            direction TEXT DEFAULT 'neutral',
            intensity DOUBLE PRECISION DEFAULT 0,
            horizon TEXT DEFAULT 'swing_5_20d',
            confidence DOUBLE PRECISION DEFAULT 0,
            source_count INTEGER DEFAULT 0,
            source_types JSONB DEFAULT '[]'::jsonb,
            entities JSONB DEFAULT '[]'::jsonb,
            commodities JSONB DEFAULT '[]'::jsonb,
            regions JSONB DEFAULT '[]'::jsonb,
            themes JSONB DEFAULT '[]'::jsonb,
            evidence JSONB DEFAULT '{}'::jsonb,
            occurred_at TIMESTAMPTZ,
            last_seen_at TIMESTAMPTZ DEFAULT NOW(),
            status TEXT DEFAULT 'active',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_event_clusters_status ON strategy_factory_event_clusters(status, last_seen_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_event_clusters_type ON strategy_factory_event_clusters(event_type, last_seen_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_theme_definitions (
            id SERIAL PRIMARY KEY,
            theme_code TEXT NOT NULL UNIQUE,
            theme_name TEXT NOT NULL,
            parent_theme_code TEXT,
            description TEXT,
            direction_rule TEXT,
            aliases JSONB DEFAULT '[]'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_theme_definitions_active ON strategy_factory_theme_definitions(active, theme_code);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_company_theme_exposures (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            theme_code TEXT NOT NULL,
            exposure_type TEXT DEFAULT 'revenue',
            direction TEXT DEFAULT 'positive',
            exposure_score DOUBLE PRECISION DEFAULT 0,
            evidence JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(symbol, theme_code, exposure_type)
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_company_theme_exposures_theme ON strategy_factory_company_theme_exposures(theme_code, exposure_score DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_company_theme_exposures_symbol ON strategy_factory_company_theme_exposures(symbol, updated_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_event_signals (
            id SERIAL PRIMARY KEY,
            event_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            theme_code TEXT NOT NULL DEFAULT '',
            direction TEXT DEFAULT 'positive',
            theme_score DOUBLE PRECISION DEFAULT 0,
            exposure_score DOUBLE PRECISION DEFAULT 0,
            price_confirm_score DOUBLE PRECISION DEFAULT 0,
            flow_confirm_score DOUBLE PRECISION DEFAULT 0,
            fundamental_confirm_score DOUBLE PRECISION DEFAULT 0,
            final_score DOUBLE PRECISION DEFAULT 0,
            rationale TEXT,
            evidence JSONB DEFAULT '{}'::jsonb,
            observed_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(event_id, symbol, theme_code)
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_event_signals_event ON strategy_factory_event_signals(event_id, final_score DESC, observed_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_event_signals_symbol ON strategy_factory_event_signals(symbol, observed_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_task_evidence (
            id SERIAL PRIMARY KEY,
            task_key TEXT NOT NULL,
            event_id TEXT,
            theme_code TEXT DEFAULT '',
            symbol TEXT,
            evidence_type TEXT NOT NULL,
            weight DOUBLE PRECISION DEFAULT 0,
            evidence_payload JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_task_evidence_task ON strategy_factory_task_evidence(task_key, created_at DESC);"
    )
