
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
            hit_rate_lcb_5d DOUBLE PRECISION,
            skill_lcb_5d DOUBLE PRECISION,
            effective_n_5d INTEGER,
            recent_hit_rate_5d DOUBLE PRECISION,
            recent_skill_lcb_5d DOUBLE PRECISION,
            stability_gap_5d DOUBLE PRECISION,
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

        CREATE TABLE IF NOT EXISTS governance_report_snapshots (
            id BIGSERIAL PRIMARY KEY,
            scope_type TEXT NOT NULL,
            scope_id TEXT,
            overall_status TEXT NOT NULL,
            issues JSONB DEFAULT '[]'::jsonb,
            payload_jsonb JSONB DEFAULT '{}'::jsonb,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_governance_report_snapshots_scope
            ON governance_report_snapshots(scope_type, scope_id, generated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_governance_report_snapshots_status
            ON governance_report_snapshots(overall_status, generated_at DESC);

        CREATE TABLE IF NOT EXISTS matching_engine_worker_state (
            engine_name TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            lease_until TIMESTAMPTZ,
            last_scan_at TIMESTAMPTZ,
            last_processed_order_id BIGINT,
            last_heartbeat_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

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
