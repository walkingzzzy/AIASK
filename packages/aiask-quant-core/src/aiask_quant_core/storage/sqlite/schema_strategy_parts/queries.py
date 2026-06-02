    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_quality_reports_sid ON strategy_quality_reports(strategy_id, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_execution_audit_snapshots_as_of ON strategy_execution_audit_snapshots(as_of_date DESC, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_execution_audit_snapshots_correlation ON strategy_execution_audit_snapshots(correlation_id, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_execution_audit_snapshots_factory_run ON strategy_execution_audit_snapshots(factory_run_id, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_closure_snapshots_as_of ON strategy_closure_snapshots(snapshot_type, as_of_date DESC, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_closure_snapshots_correlation ON strategy_closure_snapshots(correlation_id, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_closure_snapshots_factory_run ON strategy_closure_snapshots(factory_run_id, updated_at DESC);"
    )
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_factory_topn_snapshots_run_id ON strategy_factory_topn_snapshots(run_id);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_topn_snapshots_as_of ON strategy_factory_topn_snapshots(as_of_date DESC, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_topn_snapshots_correlation ON strategy_factory_topn_snapshots(correlation_id, updated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_full_market_scores_run_id ON strategy_factory_full_market_scores(run_id, rank ASC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_full_market_scores_snapshot ON strategy_factory_full_market_scores(snapshot_id, rank ASC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_full_market_scores_code ON strategy_factory_full_market_scores(code, as_of_date DESC);"
    )

    # 34. 策略状态事件（轻量 append-only 审计流）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_status_events (
            id INTEGER PRIMARY KEY,
            strategy_id TEXT NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
            from_status TEXT,
            to_status TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'status_change',
            actor_id TEXT DEFAULT 'system',
            reason TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            id INTEGER PRIMARY KEY,
            strategy_id TEXT REFERENCES strategies(id) ON DELETE CASCADE,
            aggregate_type TEXT NOT NULL DEFAULT 'strategy',
            aggregate_id TEXT,
            event_type TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            severity TEXT DEFAULT 'info',
            correlation_id TEXT,
            payload TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            id INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            elapsed_seconds REAL DEFAULT 0,
            execution_mode TEXT DEFAULT 'legacy_primary',
            engine_version TEXT DEFAULT 'strategy_factory.v2',
            parity_status TEXT,
            summary TEXT DEFAULT '{}',
            stages TEXT DEFAULT '{}',
            snapshot_summary TEXT DEFAULT '{}',
            artifact_refs TEXT DEFAULT '[]',
            parity_result TEXT DEFAULT '{}',
            error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
        "ALTER TABLE strategy_factory_runs ADD COLUMN IF NOT EXISTS artifact_refs TEXT DEFAULT '[]';"
    )
    await conn.execute(
        "ALTER TABLE strategy_factory_runs ADD COLUMN IF NOT EXISTS parity_result TEXT DEFAULT '{}';"
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
            id INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_version TEXT NOT NULL,
            payload_json TEXT DEFAULT '{}',
            payload_hash TEXT,
            storage_mode TEXT DEFAULT 'inline_json',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_run_artifacts_run_id ON strategy_factory_run_artifacts(run_id, created_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_run_artifacts_type ON strategy_factory_run_artifacts(artifact_type, created_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_scheduler_state (
            state_key TEXT PRIMARY KEY,
            payload_json TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_factory_scheduler_state_updated_at ON strategy_factory_scheduler_state(updated_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_dispatches (
            id INTEGER PRIMARY KEY,
            dispatch_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            execution_mode TEXT DEFAULT 'legacy_primary',
            requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            completed_at TEXT,
            run_id TEXT,
            message TEXT,
            error TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            id INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT DEFAULT 'macro',
            event_name TEXT NOT NULL,
            event_scope TEXT DEFAULT 'market',
            summary TEXT,
            direction TEXT DEFAULT 'neutral',
            intensity REAL DEFAULT 0,
            horizon TEXT DEFAULT 'swing_5_20d',
            confidence REAL DEFAULT 0,
            source_count INTEGER DEFAULT 0,
            source_types TEXT DEFAULT '[]',
            entities TEXT DEFAULT '[]',
            commodities TEXT DEFAULT '[]',
            regions TEXT DEFAULT '[]',
            themes TEXT DEFAULT '[]',
            evidence TEXT DEFAULT '{}',
            occurred_at TEXT,
            last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            id INTEGER PRIMARY KEY,
            theme_code TEXT NOT NULL UNIQUE,
            theme_name TEXT NOT NULL,
            parent_theme_code TEXT,
            description TEXT,
            direction_rule TEXT,
            aliases TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            active INTEGER DEFAULT TRUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_theme_definitions_active ON strategy_factory_theme_definitions(active, theme_code);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_company_theme_exposures (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            theme_code TEXT NOT NULL,
            exposure_type TEXT DEFAULT 'revenue',
            direction TEXT DEFAULT 'positive',
            exposure_score REAL DEFAULT 0,
            evidence TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
            id INTEGER PRIMARY KEY,
            event_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            theme_code TEXT NOT NULL DEFAULT '',
            direction TEXT DEFAULT 'positive',
            theme_score REAL DEFAULT 0,
            exposure_score REAL DEFAULT 0,
            price_confirm_score REAL DEFAULT 0,
            flow_confirm_score REAL DEFAULT 0,
            fundamental_confirm_score REAL DEFAULT 0,
            final_score REAL DEFAULT 0,
            rationale TEXT,
            evidence TEXT DEFAULT '{}',
            observed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
            id INTEGER PRIMARY KEY,
            task_key TEXT NOT NULL,
            event_id TEXT,
            theme_code TEXT DEFAULT '',
            symbol TEXT,
            evidence_type TEXT NOT NULL,
            weight REAL DEFAULT 0,
            evidence_payload TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_factory_task_evidence_task ON strategy_factory_task_evidence(task_key, created_at DESC);"
    )

    # =========================================================================
    # PR-1: 事件驱动主题联动 · 主题图 schema (2026-05-14)
    # =========================================================================

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_theme_nodes (
            theme_code TEXT PRIMARY KEY,
            theme_name TEXT NOT NULL,
            parent_theme_code TEXT,
            breadth TEXT NOT NULL DEFAULT 'medium',
            default_horizon TEXT NOT NULL DEFAULT 'swing_5_20d',
            aliases TEXT DEFAULT '[]',
            industry_tags TEXT DEFAULT '[]',
            description TEXT,
            shock_detection_profile TEXT NOT NULL DEFAULT 'fast',
            benchmark_index_code TEXT DEFAULT '000300',
            manual_locked INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_theme_nodes_active ON strategy_factory_theme_nodes(is_active, theme_code);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_theme_edges (
            edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_theme_code TEXT NOT NULL,
            target_theme_code TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            direction_sign INTEGER NOT NULL,
            magnitude_factor REAL NOT NULL DEFAULT 0.5,
            lag_days INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 0.5,
            confidence_source TEXT NOT NULL DEFAULT 'manual',
            manual_confidence_backup REAL,
            manual_magnitude_backup REAL,
            manual_locked INTEGER NOT NULL DEFAULT 0,
            last_regression_at TEXT,
            evidence TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            UNIQUE(source_theme_code, target_theme_code, relation_type)
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_theme_edges_source ON strategy_factory_theme_edges(source_theme_code) WHERE is_active = 1;"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_theme_edges_target ON strategy_factory_theme_edges(target_theme_code) WHERE is_active = 1;"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_event_injections (
            event_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            event_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            direction TEXT,
            confidence REAL NOT NULL,
            intensity REAL NOT NULL,
            horizon TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'theme',
            primary_themes TEXT NOT NULL DEFAULT '[]',
            rationale TEXT,
            evidence TEXT,
            valid_from TEXT NOT NULL,
            valid_until TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_review',
            operator_id TEXT,
            approver_id TEXT,
            approved_at TEXT,
            actual_outcome TEXT,
            outcome_notes TEXT,
            outcome_recorded_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_injections_status ON strategy_factory_event_injections(status, valid_until);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_injections_source ON strategy_factory_event_injections(source, created_at DESC);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_event_task_lineage (
            lineage_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dedupe_key TEXT,
            event_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            theme_code TEXT NOT NULL,
            impact_direction TEXT NOT NULL,
            impact_magnitude REAL NOT NULL,
            target_symbols TEXT NOT NULL DEFAULT '[]',
            target_count INTEGER NOT NULL,
            breadth_resolved TEXT NOT NULL,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            gate_1_passed INTEGER,
            gate_2_passed INTEGER,
            gate_3_passed INTEGER,
            strategies_submitted INTEGER DEFAULT 0
        );
    """)
    await conn.execute(
        "ALTER TABLE strategy_factory_event_task_lineage ADD COLUMN IF NOT EXISTS dedupe_key TEXT;"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_task_lineage_dedupe ON strategy_factory_event_task_lineage(dedupe_key);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_task_lineage_event ON strategy_factory_event_task_lineage(event_id, generated_at DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_task_lineage_task ON strategy_factory_event_task_lineage(task_id);"
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_theme_exposure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            theme_code TEXT NOT NULL,
            exposure_score REAL NOT NULL DEFAULT 0,
            industry_match_level INTEGER DEFAULT 0,
            name_match_score REAL DEFAULT 0,
            mainbz_match_score REAL DEFAULT 0,
            historical_beta REAL DEFAULT 0,
            evidence TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, theme_code)
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_theme_exposure_theme ON strategy_factory_theme_exposure(theme_code, exposure_score DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_theme_exposure_symbol ON strategy_factory_theme_exposure(symbol);"
    )

    # ---------------------------------------------------------------------
    # PR-B1 (2026-05-24): 事件驱动 outbox 消费状态旁路表
    #
    # 方案 §6 Phase 0 + §8 决议：v1 直接复用 strategy_domain_events 作为
    # append-only outbox 基底。但孵化工厂已经在该表上密集写入（intake/
    # hit_rate/accelerator/alert/feedback 五个 writer，生产 ~5,783 行），
    # 不应该给热写表加新列。改为独立旁路表，按 (event_id, theme_code,
    # target_symbols_signature) 维度记录消费状态：
    #
    #   - dedupe_key       : 上层（event_task_generator / publisher）算出的稳
    #                        定消费指纹，主键即去重边界。
    #   - source_event_id  : 关联到 strategy_factory_event_injections.event_id
    #                        或 strategy_domain_events.id（不强制外键，避免
    #                        循环依赖）。
    #   - status           : pending / processing / processed / failed / abandoned
    #   - attempts         : 当前重试次数（publisher 单 worker 串行扫描时累加）
    #   - last_error       : 最近一次失败原因
    #   - claimed_at / processed_at / failed_at : 时间审计三元组
    # 设计原则：
    #   - 不复制业务字段（event_name/intensity 等），始终通过 dedupe_key 反查源表
    #   - 主键 dedupe_key 让幂等约束在 SQLite 层强制
    #   - 不影响孵化工厂对 strategy_domain_events 的现有写入热路径
    # ---------------------------------------------------------------------
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_factory_event_outbox_state (
            dedupe_key TEXT PRIMARY KEY,
            source_event_id TEXT NOT NULL,
            theme_code TEXT,
            event_type TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            claimed_at TEXT,
            processed_at TEXT,
            failed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_outbox_state_status "
        "ON strategy_factory_event_outbox_state(status, created_at);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_outbox_state_source "
        "ON strategy_factory_event_outbox_state(source_event_id, status);"
    )
