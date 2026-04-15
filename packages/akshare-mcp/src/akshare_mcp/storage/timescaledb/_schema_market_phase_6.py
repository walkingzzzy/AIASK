from ._schema_market_common import _run_market_migration_once, logger


async def init_market_tables_phase_6(conn) -> None:
    await conn.execute(
        """
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS candidate_artifact_id TEXT;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS experiment_id TEXT;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS source_type TEXT;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS event_type TEXT;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS target_symbols JSONB DEFAULT '[]'::jsonb;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS direction TEXT;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS horizon_days INTEGER;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS raw_confidence DOUBLE PRECISION;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS calibrated_confidence DOUBLE PRECISION;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS freshness_ts TIMESTAMPTZ;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS proxy_only BOOLEAN DEFAULT FALSE;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS support_metric JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS doc_uid TEXT;
        ALTER TABLE strategy_candidate_evidence ADD COLUMN IF NOT EXISTS headline_label_id TEXT;

        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS candidate_artifact_id TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS experiment_id TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS applied_claim_id TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS applied_trade_step_id TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS source_type TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS direction TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS horizon_days INTEGER;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS signal_ts TIMESTAMPTZ;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS raw_confidence DOUBLE PRECISION;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS calibrated_confidence DOUBLE PRECISION;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS proxy_only BOOLEAN DEFAULT FALSE;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS doc_uid TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS headline_label_id TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS runtime_action_reason TEXT;
        ALTER TABLE strategy_signal_evidence ADD COLUMN IF NOT EXISTS runtime_action_source TEXT;

        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS entry_ts TIMESTAMPTZ;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS exit_ts TIMESTAMPTZ;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS entry_avg_price DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS exit_avg_price DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS gross_qty INTEGER;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS gross_return DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS net_return DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS gross_pnl DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS net_pnl DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS hold_days DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS exit_reason TEXT;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS mfe DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS mae DOUBLE PRECISION;
        ALTER TABLE strategy_trade_positions ADD COLUMN IF NOT EXISTS price_path_audit_status TEXT;

        CREATE TABLE IF NOT EXISTS market_headline_labels (
            label_id TEXT PRIMARY KEY,
            doc_id BIGINT REFERENCES market_documents(id) ON DELETE CASCADE,
            doc_uid TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            published_at TIMESTAMPTZ,
            headline TEXT,
            label TEXT NOT NULL,
            event_type TEXT,
            direction TEXT,
            horizon_days INTEGER,
            intensity TEXT,
            confidence DOUBLE PRECISION,
            keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_market_headline_labels_stock_time
            ON market_headline_labels(stock_code, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_market_headline_labels_doc_uid
            ON market_headline_labels(doc_uid, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_market_headline_labels_label
            ON market_headline_labels(label, published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_candidate_evidence_artifact
            ON strategy_candidate_evidence(candidate_artifact_id, experiment_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_signal_evidence_claim
            ON strategy_signal_evidence(signal_id, applied_claim_id, signal_date DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_signal_evidence_trade_step
            ON strategy_signal_evidence(signal_id, applied_trade_step_id, signal_date DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_trade_positions_roundtrip
            ON strategy_trade_positions(strategy_id, status, exit_ts DESC, updated_at DESC);
        """
    )

    await conn.execute(
        """
        ALTER TABLE strategy_signal_evidence
        DROP CONSTRAINT IF EXISTS strategy_signal_evidence_signal_id_evidence_id_key;
        """
    )
    await conn.execute(
        """
        DROP INDEX IF EXISTS ux_strategy_signal_evidence_signal_evidence_claim;
        """
    )
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_strategy_signal_evidence_signal_evidence_claim
            ON strategy_signal_evidence(
                signal_id,
                evidence_id,
                COALESCE(applied_claim_id, ''),
                COALESCE(applied_trade_step_id, '')
            );
        """
    )

    await _run_market_migration_once(
        conn,
        "strategy_candidate_evidence_native_backfill_v1",
        """
        UPDATE strategy_candidate_evidence
        SET candidate_artifact_id = COALESCE(
                candidate_artifact_id,
                NULLIF(payload->>'candidate_artifact_id', ''),
                NULLIF(payload->>'source_candidate_artifact_id', ''),
                NULLIF(payload->>'hypothesis_artifact_id', '')
            ),
            experiment_id = COALESCE(experiment_id, NULLIF(payload->>'experiment_id', '')),
            source_type = COALESCE(source_type, NULLIF(payload->>'source_type', ''), NULLIF(payload->>'evidence_type', '')),
            event_type = COALESCE(event_type, NULLIF(payload->>'event_type', '')),
            target_symbols = COALESCE(
                target_symbols,
                CASE
                    WHEN jsonb_typeof(payload->'target_symbols') = 'array' THEN payload->'target_symbols'
                    WHEN payload ? 'target_symbols' AND COALESCE(payload->>'target_symbols', '') <> '' THEN to_jsonb(ARRAY[payload->>'target_symbols'])
                    ELSE NULL
                END
            ),
            direction = COALESCE(direction, NULLIF(payload->>'direction', '')),
            horizon_days = COALESCE(horizon_days, NULLIF(payload->>'horizon_days', '')::int),
            raw_confidence = COALESCE(raw_confidence, NULLIF(payload->>'raw_confidence', '')::double precision),
            calibrated_confidence = COALESCE(calibrated_confidence, NULLIF(payload->>'calibrated_confidence', '')::double precision),
            freshness_ts = COALESCE(freshness_ts, NULLIF(payload->>'freshness_ts', '')::timestamptz),
            proxy_only = COALESCE(proxy_only, (payload->>'proxy_only')::boolean, FALSE),
            support_metric = COALESCE(
                support_metric,
                CASE WHEN jsonb_typeof(payload->'support_metric') IS NOT NULL THEN payload->'support_metric' ELSE NULL END
            ),
            doc_uid = COALESCE(doc_uid, NULLIF(payload->>'doc_uid', '')),
            headline_label_id = COALESCE(headline_label_id, NULLIF(payload->>'headline_label_id', ''))
        WHERE payload IS NOT NULL;
        """,
    )

    await _run_market_migration_once(
        conn,
        "strategy_signal_evidence_native_backfill_v1",
        """
        UPDATE strategy_signal_evidence
        SET candidate_artifact_id = COALESCE(
                candidate_artifact_id,
                NULLIF(payload->>'candidate_artifact_id', ''),
                NULLIF(payload->>'source_candidate_artifact_id', ''),
                NULLIF(payload->>'hypothesis_artifact_id', '')
            ),
            experiment_id = COALESCE(experiment_id, NULLIF(payload->>'experiment_id', '')),
            applied_claim_id = COALESCE(applied_claim_id, NULLIF(payload->>'applied_claim_id', '')),
            applied_trade_step_id = COALESCE(applied_trade_step_id, NULLIF(payload->>'applied_trade_step_id', '')),
            source_type = COALESCE(source_type, NULLIF(payload->>'source_type', ''), NULLIF(payload->>'evidence_type', '')),
            direction = COALESCE(direction, NULLIF(payload->>'direction', '')),
            horizon_days = COALESCE(horizon_days, NULLIF(payload->>'horizon_days', '')::int),
            signal_ts = COALESCE(signal_ts, NULLIF(payload->>'signal_ts', '')::timestamptz, signal_date::timestamptz),
            raw_confidence = COALESCE(raw_confidence, NULLIF(payload->>'raw_confidence', '')::double precision),
            calibrated_confidence = COALESCE(calibrated_confidence, NULLIF(payload->>'calibrated_confidence', '')::double precision),
            proxy_only = COALESCE(proxy_only, (payload->>'proxy_only')::boolean, FALSE),
            doc_uid = COALESCE(doc_uid, NULLIF(payload->>'doc_uid', '')),
            headline_label_id = COALESCE(headline_label_id, NULLIF(payload->>'headline_label_id', '')),
            runtime_action_reason = COALESCE(runtime_action_reason, NULLIF(payload->>'runtime_action_reason', '')),
            runtime_action_source = COALESCE(runtime_action_source, NULLIF(payload->>'runtime_action_source', ''))
        WHERE payload IS NOT NULL;
        """,
    )

    await _run_market_migration_once(
        conn,
        "strategy_trade_positions_roundtrip_backfill_v1",
        """
        UPDATE strategy_trade_positions
        SET entry_ts = COALESCE(entry_ts, opened_at),
            exit_ts = COALESCE(exit_ts, closed_at),
            entry_avg_price = COALESCE(entry_avg_price, entry_amount / NULLIF(entry_shares, 0)),
            exit_avg_price = COALESCE(exit_avg_price, exit_amount / NULLIF(exit_shares, 0)),
            gross_qty = COALESCE(gross_qty, GREATEST(COALESCE(entry_shares, 0), COALESCE(exit_shares, 0))),
            gross_pnl = COALESCE(gross_pnl, exit_amount - entry_amount),
            net_pnl = COALESCE(net_pnl, realized_pnl),
            gross_return = COALESCE(gross_return, (exit_amount - entry_amount) / NULLIF(entry_amount, 0)),
            net_return = COALESCE(net_return, realized_return),
            hold_days = COALESCE(
                hold_days,
                EXTRACT(EPOCH FROM (COALESCE(closed_at, NOW()) - COALESCE(opened_at, created_at))) / 86400.0
            ),
            exit_reason = COALESCE(
                exit_reason,
                CASE
                    WHEN status = 'closed' THEN 'filled_round_trip'
                    WHEN status = 'open' THEN 'position_open'
                    ELSE exit_reason
                END
            ),
            price_path_audit_status = COALESCE(
                price_path_audit_status,
                CASE
                    WHEN status = 'closed' THEN 'pending_refresh'
                    WHEN status = 'open' THEN 'open_position'
                    ELSE 'unknown'
                END
            );
        """,
    )
    logger.info("Market tables phase 6 initialized")
