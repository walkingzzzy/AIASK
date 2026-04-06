"""
Strategy table DDL — strategies, incubation, risk, vector, factory, etc.

All ~25 strategy tables are created via a single entry point:

    await init_strategy_tables(conn, pgvector_enabled)

The function is idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
pgvector-specific DDL (vector columns) is gated by the ``pgvector_enabled`` flag.
"""

import logging

logger = logging.getLogger(__name__)


async def init_strategy_tables(conn, pgvector_enabled: bool = False) -> None:
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
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, signal_date, code)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_signals_strategy
            ON strategy_signals(strategy_id, signal_date DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_signals_date
            ON strategy_signals(signal_date DESC);
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
            summary JSONB DEFAULT '{}'::jsonb,
            stages JSONB DEFAULT '{}'::jsonb,
            snapshot_summary JSONB DEFAULT '{}'::jsonb,
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_runs_started_at ON strategy_factory_runs(started_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_runs_status ON strategy_factory_runs(status, started_at DESC);"
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

    # Incubation accounts & metrics
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_incubation_accounts (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT NOT NULL,
            stage TEXT DEFAULT 'warmup',
            status TEXT DEFAULT 'active',
            source_run_id TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            bound_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, account_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_incubation_accounts_sid
            ON strategy_incubation_accounts(strategy_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_incubation_accounts_acct
            ON strategy_incubation_accounts(account_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_incubation_metrics (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT,
            metric_date DATE NOT NULL,
            stage TEXT DEFAULT 'warmup',
            total_value DOUBLE PRECISION,
            cash DOUBLE PRECISION,
            market_value DOUBLE PRECISION,
            nav DOUBLE PRECISION,
            daily_return DOUBLE PRECISION,
            max_drawdown DOUBLE PRECISION,
            sharpe_ratio DOUBLE PRECISION,
            hit_rate_5d DOUBLE PRECISION,
            forward_ic_5d DOUBLE PRECISION,
            forward_sharpe_5d DOUBLE PRECISION,
            total_signals INTEGER DEFAULT 0,
            total_orders INTEGER DEFAULT 0,
            total_trades INTEGER DEFAULT 0,
            turnover_rate DOUBLE PRECISION,
            exposure_rate DOUBLE PRECISION,
            alpha_decay DOUBLE PRECISION,
            drift_score DOUBLE PRECISION,
            blockers JSONB DEFAULT '[]'::jsonb,
            risk_flags JSONB DEFAULT '[]'::jsonb,
            decision TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id, metric_date)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_incubation_metrics_sid
            ON strategy_incubation_metrics(strategy_id, metric_date DESC);

        CREATE TABLE IF NOT EXISTS strategy_incubation_pipeline_snapshots (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT,
            pipeline_stage TEXT DEFAULT 'warmup',
            pipeline_status TEXT DEFAULT 'collecting',
            observed_days INTEGER DEFAULT 0,
            promote_streak INTEGER DEFAULT 0,
            halt_streak INTEGER DEFAULT 0,
            latest_decision TEXT,
            readiness_score DOUBLE PRECISION DEFAULT 0,
            next_action TEXT,
            auto_review BOOLEAN DEFAULT FALSE,
            auto_promoted BOOLEAN DEFAULT FALSE,
            blockers JSONB DEFAULT '[]'::jsonb,
            risk_flags JSONB DEFAULT '[]'::jsonb,
            summary JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            task_run_id INTEGER,
            source TEXT DEFAULT 'system',
            evaluated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_incubation_pipeline_snapshots_sid
            ON strategy_incubation_pipeline_snapshots(strategy_id, evaluated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_incubation_pipeline_snapshots_status
            ON strategy_incubation_pipeline_snapshots(pipeline_status, evaluated_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_runtime_risk_events (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT,
            severity TEXT NOT NULL,
            event_type TEXT NOT NULL,
            action TEXT,
            status TEXT DEFAULT 'open',
            title TEXT,
            reason TEXT,
            payload JSONB DEFAULT '{}'::jsonb,
            detected_at TIMESTAMPTZ DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_runtime_risk_events_sid
            ON strategy_runtime_risk_events(strategy_id, detected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_runtime_risk_events_status
            ON strategy_runtime_risk_events(status, severity, detected_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_runtime_controls (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT,
            control_mode TEXT NOT NULL DEFAULT 'active',
            status TEXT NOT NULL DEFAULT 'active',
            source TEXT DEFAULT 'system',
            trigger_event_type TEXT,
            reason TEXT,
            action_summary JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            activated_at TIMESTAMPTZ DEFAULT NOW(),
            released_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(strategy_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_runtime_controls_mode
            ON strategy_runtime_controls(control_mode, updated_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_runtime_risk_snapshots (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT,
            posture_level TEXT DEFAULT 'safe',
            escalation_level INTEGER DEFAULT 0,
            control_mode TEXT DEFAULT 'active',
            open_event_count INTEGER DEFAULT 0,
            critical_open_count INTEGER DEFAULT 0,
            warning_open_count INTEGER DEFAULT 0,
            recommended_action TEXT,
            recovery_eligible BOOLEAN DEFAULT FALSE,
            blockers JSONB DEFAULT '[]'::jsonb,
            summary JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            task_run_id INTEGER,
            source TEXT DEFAULT 'system',
            evaluated_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_runtime_risk_snapshots_sid
            ON strategy_runtime_risk_snapshots(strategy_id, evaluated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_runtime_risk_snapshots_posture
            ON strategy_runtime_risk_snapshots(posture_level, evaluated_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_runtime_alerts (
            alert_id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT,
            alert_key TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            status TEXT NOT NULL DEFAULT 'open',
            title TEXT,
            message TEXT,
            escalation_level INTEGER DEFAULT 0,
            channels JSONB DEFAULT '[]'::jsonb,
            related_event_ids JSONB DEFAULT '[]'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            source TEXT DEFAULT 'system',
            acknowledged_by TEXT,
            acknowledged_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_runtime_alerts_sid
            ON strategy_runtime_alerts(strategy_id, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_runtime_alerts_key
            ON strategy_runtime_alerts(alert_key, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_promotion_reviews (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            account_id TEXT,
            review_source TEXT DEFAULT 'system',
            stage TEXT DEFAULT 'incubating',
            status TEXT NOT NULL DEFAULT 'watch',
            recommendation TEXT,
            score DOUBLE PRECISION DEFAULT 0,
            blockers JSONB DEFAULT '[]'::jsonb,
            risk_flags JSONB DEFAULT '[]'::jsonb,
            summary JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            reviewed_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_promotion_reviews_sid
            ON strategy_promotion_reviews(strategy_id, reviewed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_promotion_reviews_status
            ON strategy_promotion_reviews(status, reviewed_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_projection_snapshots (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            projection_type TEXT NOT NULL DEFAULT 'strategy_state',
            aggregate_version INTEGER DEFAULT 0,
            current_status TEXT,
            runtime_control_mode TEXT,
            timeline_count INTEGER DEFAULT 0,
            projection JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            task_run_id INTEGER,
            source TEXT DEFAULT 'system',
            rebuilt_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_projection_snapshots_sid
            ON strategy_projection_snapshots(strategy_id, rebuilt_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_projection_snapshots_type
            ON strategy_projection_snapshots(projection_type, rebuilt_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_vector_profiles (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
            index_name TEXT DEFAULT 'strategy_behavior',
            collection_name TEXT DEFAULT 'strategy_behavior_embeddings',
            profile_type TEXT NOT NULL,
            vector_method TEXT NOT NULL,
            model_id TEXT DEFAULT 'strategy_behavior_v1',
            metric TEXT DEFAULT 'cosine',
            vector_dim INTEGER DEFAULT 0,
            embedding JSONB DEFAULT '[]'::jsonb,
            signature TEXT,
            backend TEXT DEFAULT 'index',
            index_version TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_profiles_sid
            ON strategy_vector_profiles(strategy_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_profiles_type
            ON strategy_vector_profiles(profile_type, vector_method, created_at DESC);

        CREATE TABLE IF NOT EXISTS vector_index_registry (
            id SERIAL PRIMARY KEY,
            index_name TEXT NOT NULL,
            backend TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'building',
            profile_type TEXT,
            vector_method TEXT,
            metric TEXT DEFAULT 'cosine',
            sample_count INTEGER DEFAULT 0,
            index_version TEXT NOT NULL,
            metadata JSONB DEFAULT '{}'::jsonb,
            built_at TIMESTAMPTZ,
            activated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(index_name, index_version)
        );
        CREATE INDEX IF NOT EXISTS idx_vector_index_registry_name
            ON vector_index_registry(index_name, created_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_vector_index_snapshots (
            id SERIAL PRIMARY KEY,
            index_name TEXT NOT NULL,
            index_version TEXT NOT NULL,
            collection_name TEXT DEFAULT 'strategy_behavior_embeddings',
            status TEXT NOT NULL DEFAULT 'building',
            profile_type TEXT,
            vector_method TEXT,
            model_id TEXT DEFAULT 'strategy_behavior_v1',
            metric TEXT DEFAULT 'cosine',
            backend TEXT DEFAULT 'index',
            profile_count INTEGER DEFAULT 0,
            bucket_count INTEGER DEFAULT 0,
            vector_dim INTEGER DEFAULT 0,
            centroids JSONB DEFAULT '[]'::jsonb,
            index_params JSONB DEFAULT '{}'::jsonb,
            metrics JSONB DEFAULT '{}'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            task_run_id INTEGER,
            source TEXT DEFAULT 'system',
            built_at TIMESTAMPTZ,
            activated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE strategy_vector_index_snapshots ADD COLUMN IF NOT EXISTS index_params JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE strategy_vector_index_snapshots ADD COLUMN IF NOT EXISTS metrics JSONB DEFAULT '{}'::jsonb;
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_snapshots_name
            ON strategy_vector_index_snapshots(index_name, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_snapshots_name_version
            ON strategy_vector_index_snapshots(index_name, index_version, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_snapshots_status
            ON strategy_vector_index_snapshots(status, created_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_vector_index_items (
            id SERIAL PRIMARY KEY,
            index_name TEXT NOT NULL,
            index_version TEXT NOT NULL,
            collection_name TEXT DEFAULT 'strategy_behavior_embeddings',
            profile_id INTEGER,
            strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
            profile_type TEXT,
            vector_method TEXT,
            model_id TEXT DEFAULT 'strategy_behavior_v1',
            metric TEXT DEFAULT 'cosine',
            vector_dim INTEGER DEFAULT 0,
            bucket_id TEXT,
            coarse_score DOUBLE PRECISION DEFAULT 0,
            embedding JSONB DEFAULT '[]'::jsonb,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(index_name, index_version, profile_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_items_lookup
            ON strategy_vector_index_items(index_name, index_version, bucket_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_vector_index_items_sid
            ON strategy_vector_index_items(strategy_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_generation_experiments (
            id SERIAL PRIMARY KEY,
            experiment_id TEXT NOT NULL UNIQUE,
            strategy_id TEXT REFERENCES strategies(id) ON DELETE SET NULL,
            parent_strategy_id TEXT REFERENCES strategies(id) ON DELETE SET NULL,
            generated_strategy_id TEXT REFERENCES strategies(id) ON DELETE SET NULL,
            task_run_id INTEGER,
            source TEXT NOT NULL,
            generator_type TEXT NOT NULL,
            optimizer_type TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            hypothesis TEXT,
            prompt TEXT,
            parameters JSONB DEFAULT '{}'::jsonb,
            strategy_spec JSONB DEFAULT '{}'::jsonb,
            evaluation JSONB DEFAULT '{}'::jsonb,
            result JSONB DEFAULT '{}'::jsonb,
            parent_experiment_id TEXT,
            artifact_id TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE strategy_generation_experiments
            ADD COLUMN IF NOT EXISTS parent_strategy_id TEXT REFERENCES strategies(id) ON DELETE SET NULL;
        ALTER TABLE strategy_generation_experiments
            ADD COLUMN IF NOT EXISTS generated_strategy_id TEXT REFERENCES strategies(id) ON DELETE SET NULL;
        ALTER TABLE strategy_generation_experiments
            ADD COLUMN IF NOT EXISTS task_run_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_strategy_generation_experiments_status
            ON strategy_generation_experiments(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_generation_experiments_parent_sid
            ON strategy_generation_experiments(parent_strategy_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_generation_experiments_generated_sid
            ON strategy_generation_experiments(generated_strategy_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_generation_experiments_task_run
            ON strategy_generation_experiments(task_run_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS strategy_task_runs (
            id SERIAL PRIMARY KEY,
            strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
            task_name TEXT NOT NULL,
            task_scope TEXT,
            task_key TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            trace_id TEXT,
            payload JSONB DEFAULT '{}'::jsonb,
            result JSONB DEFAULT '{}'::jsonb,
            error TEXT,
            started_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        );
        ALTER TABLE strategy_task_runs
            ADD COLUMN IF NOT EXISTS strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE;
        CREATE INDEX IF NOT EXISTS idx_strategy_task_runs_name
            ON strategy_task_runs(task_name, started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_task_runs_sid
            ON strategy_task_runs(strategy_id, started_at DESC);
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
        SET index_name = COALESCE(NULLIF(index_name, ''), metadata->>'index_name', 'strategy_behavior')
        WHERE index_name IS NULL OR index_name = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_profiles
        SET model_id = COALESCE(NULLIF(model_id, ''), metadata->>'model_id', 'strategy_behavior_v1')
        WHERE model_id IS NULL OR model_id = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_profiles
        SET collection_name = COALESCE(NULLIF(collection_name, ''), metadata->>'collection_name', 'strategy_behavior_embeddings')
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
        SET model_id = COALESCE(NULLIF(model_id, ''), metadata->>'model_id', 'strategy_behavior_v1')
        WHERE model_id IS NULL OR model_id = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_index_snapshots
        SET collection_name = COALESCE(NULLIF(collection_name, ''), metadata->>'collection_name', 'strategy_behavior_embeddings')
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
        SET model_id = COALESCE(NULLIF(model_id, ''), metadata->>'model_id', 'strategy_behavior_v1')
        WHERE model_id IS NULL OR model_id = '';
    """)
    await conn.execute("""
        UPDATE strategy_vector_index_items
        SET collection_name = COALESCE(NULLIF(collection_name, ''), metadata->>'collection_name', 'strategy_behavior_embeddings')
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

    # pgvector-specific tables (gated)
    if pgvector_enabled:
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
                embedding vector NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ DEFAULT NOW()
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
                embedding vector NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ DEFAULT NOW()
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
            SET model_id = COALESCE(NULLIF(model_id, ''), metadata->>'model_id', 'strategy_behavior_v1')
            WHERE model_id IS NULL OR model_id = '';
        """)
        await conn.execute("""
            UPDATE strategy_vector_profile_store
            SET collection_name = COALESCE(NULLIF(collection_name, ''), metadata->>'collection_name', 'strategy_behavior_embeddings')
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
            SET model_id = COALESCE(NULLIF(model_id, ''), metadata->>'model_id', 'strategy_behavior_v1')
            WHERE model_id IS NULL OR model_id = '';
        """)
        await conn.execute("""
            UPDATE strategy_vector_index_item_store
            SET collection_name = COALESCE(NULLIF(collection_name, ''), metadata->>'collection_name', 'strategy_behavior_embeddings')
            WHERE collection_name IS NULL OR collection_name = '';
        """)

    logger.info("Strategy tables initialized (pgvector=%s)", pgvector_enabled)
