    """Create / migrate all strategy-related tables.

    Args:
        conn: an asyncpg connection (already acquired from the pool).
        pgvector_enabled: whether the pgvector extension is available.
    """

    # 24. 策略超市表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            author_id TEXT DEFAULT 'default',
            strategy_type TEXT NOT NULL,
            params JSONB DEFAULT '{}'::jsonb,
            factor_weights JSONB DEFAULT '{}'::jsonb,
            status TEXT DEFAULT 'draft',
            tags TEXT[] DEFAULT '{}',
            backtest_artifact_id TEXT,
            subscriber_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
        CREATE INDEX IF NOT EXISTS idx_strategies_type ON strategies(strategy_type);
        CREATE INDEX IF NOT EXISTS idx_strategies_author ON strategies(author_id);

        CREATE TABLE IF NOT EXISTS strategy_metrics (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            period TEXT DEFAULT 'all',
            total_return DOUBLE PRECISION,
            annual_return DOUBLE PRECISION,
            sharpe_ratio DOUBLE PRECISION,
            max_drawdown DOUBLE PRECISION,
            win_rate DOUBLE PRECISION,
            calmar_ratio DOUBLE PRECISION,
            trade_count INTEGER,
            computed_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, period)
        );

        CREATE TABLE IF NOT EXISTS strategy_reviews (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_reviews_strategy ON strategy_reviews(strategy_id);

        CREATE TABLE IF NOT EXISTS strategy_subscriptions (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            subscribed_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_subs_user ON strategy_subscriptions(user_id);
    """)

    # 28. 策略前向信号表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_signals (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            signal_date DATE NOT NULL,
            code TEXT NOT NULL,
            signal SMALLINT NOT NULL,
            score DOUBLE PRECISION,
            execution_semantic_mode TEXT,
            action_source TEXT,
            event_action TEXT,
            action_reason TEXT,
            signal_metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, signal_date, code)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_signals_strategy
            ON strategy_signals(strategy_id, signal_date DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_signals_date
            ON strategy_signals(signal_date DESC);
    """)
    await conn.execute("""
        ALTER TABLE strategy_signals
        ADD COLUMN IF NOT EXISTS execution_semantic_mode TEXT;
    """)
    await conn.execute("""
        ALTER TABLE strategy_signals
        ADD COLUMN IF NOT EXISTS action_source TEXT;
    """)
    await conn.execute("""
        ALTER TABLE strategy_signals
        ADD COLUMN IF NOT EXISTS event_action TEXT;
    """)
    await conn.execute("""
        ALTER TABLE strategy_signals
        ADD COLUMN IF NOT EXISTS action_reason TEXT;
    """)
    await conn.execute("""
        ALTER TABLE strategy_signals
        ADD COLUMN IF NOT EXISTS signal_metadata JSONB DEFAULT '{}'::jsonb;
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_signal_event_snapshots (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            code TEXT NOT NULL,
            as_of_date DATE NOT NULL,
            latest_bar_date DATE,
            latest_bar_signal SMALLINT NOT NULL DEFAULT 0,
            execution_semantic_mode TEXT,
            latest_event_index INTEGER,
            latest_event_date DATE,
            latest_event_signal SMALLINT,
            latest_event_action TEXT,
            latest_event_action_source TEXT,
            latest_event_reason TEXT,
            latest_event_units DOUBLE PRECISION,
            latest_entry_date DATE,
            latest_exit_date DATE,
            event_count INTEGER NOT NULL DEFAULT 0,
            recent_events JSONB DEFAULT '[]'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, code, as_of_date)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_signal_event_snapshots_lookup
            ON strategy_signal_event_snapshots(strategy_id, code, as_of_date DESC, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_signal_event_snapshots_strategy
            ON strategy_signal_event_snapshots(strategy_id, as_of_date DESC, updated_at DESC);
    """)
    await conn.execute("""
        CREATE OR REPLACE VIEW strategy_signal_event_snapshots_latest AS
        SELECT DISTINCT ON (strategy_id, code)
            id,
            strategy_id,
            code,
            as_of_date,
            latest_bar_date,
            latest_bar_signal,
            execution_semantic_mode,
            latest_event_index,
            latest_event_date,
            latest_event_signal,
            latest_event_action,
            latest_event_action_source,
            latest_event_reason,
            latest_event_units,
            latest_entry_date,
            latest_exit_date,
            event_count,
            recent_events,
            metadata,
            created_at,
            updated_at
        FROM strategy_signal_event_snapshots
        ORDER BY strategy_id, code, as_of_date DESC, updated_at DESC, id DESC;
    """)

    # 29. 前向收益验证表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_forward_returns (
            id SERIAL PRIMARY KEY,
            signal_id INTEGER NOT NULL,
            forward_days INTEGER NOT NULL,
            actual_return DOUBLE PRECISION,
            calculated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(signal_id, forward_days)
        );
        CREATE INDEX IF NOT EXISTS idx_signal_fwd_signal
            ON signal_forward_returns(signal_id);
    """)

    # 29.1 向后兼容：published -> listed 迁移
    await conn.execute("""
        UPDATE strategies SET status = 'listed' WHERE status = 'published';
    """)

    # 30. 策略血统表（策略工厂溯源）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_lineage (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            parent_id TEXT,
            spawn_reason TEXT NOT NULL,
            birth_regime JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_lineage_sid ON strategy_lineage(strategy_id);")

    # 31. 策略淘汰日志
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_elimination_log (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            elimination_date DATE NOT NULL,
            red_flags JSONB DEFAULT '[]'::jsonb,
            reason TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_elim_sid ON strategy_elimination_log(strategy_id);")

    # 32. 每日快照历史（策略工厂输入数据）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshot_history (
            id SERIAL PRIMARY KEY,
            snapshot_date DATE NOT NULL UNIQUE,
            fear_greed_index INTEGER,
            fg_components JSONB DEFAULT '{}'::jsonb,
            factor_ic JSONB DEFAULT '{}'::jsonb,
            factor_ic_trend JSONB DEFAULT '{}'::jsonb,
            factor_research JSONB DEFAULT '{}'::jsonb,
            north_fund_3d_net DOUBLE PRECISION,
            margin_5d_change_pct DOUBLE PRECISION,
            hot_sectors JSONB DEFAULT '[]'::jsonb,
            cold_sectors JSONB DEFAULT '[]'::jsonb,
            listed_count INTEGER DEFAULT 0,
            category_counts JSONB DEFAULT '{}'::jsonb,
            summary JSONB DEFAULT '{}'::jsonb,
            completeness JSONB DEFAULT '{}'::jsonb,
            sources JSONB DEFAULT '{}'::jsonb,
            failure_reasons JSONB DEFAULT '[]'::jsonb,
            missing_fields JSONB DEFAULT '[]'::jsonb,
            degraded BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS summary JSONB DEFAULT '{}'::jsonb;
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS completeness JSONB DEFAULT '{}'::jsonb;
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS factor_research JSONB DEFAULT '{}'::jsonb;
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '{}'::jsonb;
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS failure_reasons JSONB DEFAULT '[]'::jsonb;
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS missing_fields JSONB DEFAULT '[]'::jsonb;
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS degraded BOOLEAN DEFAULT FALSE;
    """)

    # 33. 策略质检报告
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_quality_reports (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            report_type TEXT NOT NULL DEFAULT 'submission',
            passed BOOLEAN DEFAULT FALSE,
            summary JSONB DEFAULT '{}'::jsonb,
            quality_gate JSONB DEFAULT '{}'::jsonb,
            validation_report JSONB DEFAULT '{}'::jsonb,
            risk_report JSONB DEFAULT '{}'::jsonb,
            dedup_report JSONB DEFAULT '{}'::jsonb,
            backtest_metrics JSONB DEFAULT '{}'::jsonb,
            snapshot JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, report_type)
        );
    """)
