from ._schema_market_common import _run_market_migration_once, logger


async def init_market_tables_phase_7(conn) -> None:
    await conn.execute(
        """
        ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS execution_semantic_mode TEXT;
        ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS action_source TEXT;
        ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS event_action TEXT;
        ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS action_reason TEXT;
        ALTER TABLE strategy_signals ADD COLUMN IF NOT EXISTS signal_metadata JSONB DEFAULT '{}'::jsonb;

        CREATE INDEX IF NOT EXISTS idx_strategy_signals_semantic_mode
            ON strategy_signals(execution_semantic_mode, signal_date DESC);
        CREATE INDEX IF NOT EXISTS idx_strategy_signals_action_source
            ON strategy_signals(action_source, signal_date DESC);

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
        """
    )

    await conn.execute(
        """
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
        """
    )

    await _run_market_migration_once(
        conn,
        "strategy_signals_action_metadata_backfill_v1",
        """
        UPDATE strategy_signals
        SET execution_semantic_mode = COALESCE(
                execution_semantic_mode,
                NULLIF(signal_metadata->>'execution_semantic_mode', '')
            ),
            action_source = COALESCE(
                action_source,
                NULLIF(signal_metadata->>'action_source', '')
            ),
            event_action = COALESCE(
                event_action,
                NULLIF(signal_metadata->>'event_action', '')
            ),
            action_reason = COALESCE(
                action_reason,
                NULLIF(signal_metadata->>'action_reason', '')
            )
        WHERE signal_metadata IS NOT NULL;
        """,
    )
    logger.info("Market tables phase 7 initialized")
