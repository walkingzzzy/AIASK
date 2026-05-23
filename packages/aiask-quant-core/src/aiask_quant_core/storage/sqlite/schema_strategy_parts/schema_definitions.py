    """Create / migrate all strategy-related tables.

    Args:
        conn: an async SQLite-compatible connection.
        sqlite_python_enabled: whether database-side vector search is enabled.
    """

    # 24. 策略超市表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            author_id TEXT DEFAULT 'default',
            strategy_type TEXT NOT NULL,
            params TEXT DEFAULT '{}',
            factor_weights TEXT DEFAULT '{}',
            status TEXT DEFAULT 'draft',
            tags TEXT DEFAULT '{}',
            backtest_artifact_id TEXT,
            subscriber_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);
        CREATE INDEX IF NOT EXISTS idx_strategies_type ON strategies(strategy_type);
        CREATE INDEX IF NOT EXISTS idx_strategies_author ON strategies(author_id);

        CREATE TABLE IF NOT EXISTS strategy_metrics (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            period TEXT DEFAULT 'all',
            total_return REAL,
            annual_return REAL,
            sharpe_ratio REAL,
            max_drawdown REAL,
            win_rate REAL,
            calmar_ratio REAL,
            trade_count INTEGER,
            computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, period)
        );

        CREATE TABLE IF NOT EXISTS strategy_reviews (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_reviews_strategy ON strategy_reviews(strategy_id);

        CREATE TABLE IF NOT EXISTS strategy_subscriptions (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            subscribed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_subs_user ON strategy_subscriptions(user_id);

        CREATE TABLE IF NOT EXISTS strategy_paper_sessions (
            id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            session_type TEXT NOT NULL DEFAULT 'personal_paper',
            source_strategy_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_used_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, strategy_id, session_type)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_paper_sessions_user
            ON strategy_paper_sessions(user_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_paper_sessions_strategy
            ON strategy_paper_sessions(strategy_id, updated_at DESC);
    """)

    # 28. 策略前向信号表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_signals (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            code TEXT NOT NULL,
            signal SMALLINT NOT NULL,
            score REAL,
            execution_semantic_mode TEXT,
            action_source TEXT,
            event_action TEXT,
            action_reason TEXT,
            signal_metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
        ADD COLUMN IF NOT EXISTS signal_metadata TEXT DEFAULT '{}';
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_signal_event_snapshots (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            code TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            latest_bar_date TEXT,
            latest_bar_signal SMALLINT NOT NULL DEFAULT 0,
            execution_semantic_mode TEXT,
            latest_event_index INTEGER,
            latest_event_date TEXT,
            latest_event_signal SMALLINT,
            latest_event_action TEXT,
            latest_event_action_source TEXT,
            latest_event_reason TEXT,
            latest_event_units REAL,
            latest_entry_date TEXT,
            latest_exit_date TEXT,
            event_count INTEGER NOT NULL DEFAULT 0,
            recent_events TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, code, as_of_date)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_signal_event_snapshots_lookup
            ON strategy_signal_event_snapshots(strategy_id, code, as_of_date DESC, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_signal_event_snapshots_strategy
            ON strategy_signal_event_snapshots(strategy_id, as_of_date DESC, updated_at DESC);
    """)
    await conn.execute("""
        DROP VIEW IF EXISTS strategy_signal_event_snapshots_latest;
        CREATE VIEW IF NOT EXISTS strategy_signal_event_snapshots_latest AS
        SELECT
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
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY strategy_id, code
                       ORDER BY as_of_date DESC, updated_at DESC, id DESC
                   ) AS rn
            FROM strategy_signal_event_snapshots
        )
        WHERE rn = 1;
    """)

    # 29. 前向收益验证表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_forward_returns (
            id INTEGER PRIMARY KEY,
            signal_id INTEGER NOT NULL,
            forward_days INTEGER NOT NULL,
            actual_return REAL,
            calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            parent_id TEXT,
            spawn_reason TEXT NOT NULL,
            birth_regime TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_lineage_sid ON strategy_lineage(strategy_id);")

    # 31. 策略淘汰日志
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_elimination_log (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            elimination_date TEXT NOT NULL,
            red_flags TEXT DEFAULT '[]',
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_elim_sid ON strategy_elimination_log(strategy_id);")

    # 32. 每日快照历史（策略工厂输入数据）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshot_history (
            id INTEGER PRIMARY KEY,
            snapshot_date TEXT NOT NULL UNIQUE,
            fear_greed_index INTEGER,
            fg_components TEXT DEFAULT '{}',
            factor_ic TEXT DEFAULT '{}',
            factor_ic_trend TEXT DEFAULT '{}',
            factor_research TEXT DEFAULT '{}',
            north_fund_3d_net REAL,
            margin_5d_change_pct REAL,
            hot_sectors TEXT DEFAULT '[]',
            cold_sectors TEXT DEFAULT '[]',
            listed_count INTEGER DEFAULT 0,
            category_counts TEXT DEFAULT '{}',
            summary TEXT DEFAULT '{}',
            completeness TEXT DEFAULT '{}',
            sources TEXT DEFAULT '{}',
            parameter_distribution_samples TEXT DEFAULT '[]',
            parameter_distribution_summary TEXT DEFAULT '{}',
            failure_reasons TEXT DEFAULT '[]',
            missing_fields TEXT DEFAULT '[]',
            degraded INTEGER DEFAULT FALSE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT '{}';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS completeness TEXT DEFAULT '{}';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS factor_research TEXT DEFAULT '{}';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS sources TEXT DEFAULT '{}';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS parameter_distribution_samples TEXT DEFAULT '[]';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS parameter_distribution_summary TEXT DEFAULT '{}';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS failure_reasons TEXT DEFAULT '[]';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS missing_fields TEXT DEFAULT '[]';
    """)
    await conn.execute("""
        ALTER TABLE daily_snapshot_history
        ADD COLUMN IF NOT EXISTS degraded INTEGER DEFAULT FALSE;
    """)

    # 33. 策略质检报告
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_quality_reports (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            report_type TEXT NOT NULL DEFAULT 'submission',
            passed INTEGER DEFAULT FALSE,
            summary TEXT DEFAULT '{}',
            quality_gate TEXT DEFAULT '{}',
            validation_report TEXT DEFAULT '{}',
            risk_report TEXT DEFAULT '{}',
            dedup_report TEXT DEFAULT '{}',
            backtest_metrics TEXT DEFAULT '{}',
            snapshot TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(strategy_id, report_type)
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_execution_audit_snapshots (
            strategy_id TEXT PRIMARY KEY REFERENCES strategies(id) ON DELETE CASCADE,
            snapshot_id TEXT NOT NULL UNIQUE,
            as_of_date TEXT,
            source_run_id TEXT,
            factory_run_id TEXT,
            correlation_id TEXT,
            trace_id TEXT,
            submission_lane TEXT,
            parent_task_run_id TEXT,
            source_action TEXT,
            verdict_status TEXT NOT NULL DEFAULT 'missing',
            verdict_reasons TEXT DEFAULT '[]',
            execution_hard_gate_passed INTEGER DEFAULT FALSE,
            verification TEXT DEFAULT '{}',
            acceptance TEXT DEFAULT '{}',
            audit_summary TEXT DEFAULT '{}',
            snapshot TEXT DEFAULT '{}',
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_closure_snapshots (
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            snapshot_type TEXT NOT NULL,
            snapshot_id TEXT NOT NULL UNIQUE,
            as_of_date TEXT,
            source_run_id TEXT,
            factory_run_id TEXT,
            correlation_id TEXT,
            trace_id TEXT,
            submission_lane TEXT,
            parent_task_run_id TEXT,
            source_action TEXT,
            snapshot TEXT DEFAULT '{}',
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(strategy_id, snapshot_type)
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_topn_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            as_of_date TEXT,
            trace_id TEXT,
            correlation_id TEXT,
            source_action TEXT,
            universe_count INTEGER DEFAULT 0,
            eligible_count INTEGER DEFAULT 0,
            topn_n INTEGER DEFAULT 20,
            selection_rules TEXT DEFAULT '{}',
            constituents TEXT DEFAULT '[]',
            portfolio_candidate_id TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_full_market_scores (
            id INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            as_of_date TEXT,
            trace_id TEXT,
            correlation_id TEXT,
            code TEXT NOT NULL,
            rank INTEGER NOT NULL,
            composite_score REAL DEFAULT 0,
            industry TEXT,
            market_cap REAL,
            component_scores TEXT DEFAULT '{}',
            family_candidates TEXT DEFAULT '[]',
            eligible INTEGER DEFAULT TRUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(run_id, code)
        );
    """)
