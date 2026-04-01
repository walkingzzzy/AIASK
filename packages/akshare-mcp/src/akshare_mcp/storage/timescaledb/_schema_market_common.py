"""
Market data table DDL — kline, financials, portfolios, alerts, etc.

All ~30 market-data tables are created via a single entry point:

    await init_market_tables(conn)

The function is idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
"""

import logging

logger = logging.getLogger(__name__)
_MARKET_SCHEMA_MIGRATION_TABLE = "market_schema_migrations"


async def _create_hypertable_if_supported(conn, table_name: str, time_column: str = "time") -> None:
    """Best-effort Timescale hypertable promotion."""
    try:
        enabled = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_extension
                WHERE extname = 'timescaledb'
            )
            """
        )
        if not enabled:
            return
        await conn.execute(
            f"""
            SELECT create_hypertable(
                '{table_name}',
                '{time_column}',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
            """
        )
    except Exception as exc:
        logger.warning("create_hypertable skipped for %s: %s", table_name, exc)


async def _ensure_foreign_key(
    conn,
    *,
    table_name: str,
    constraint_name: str,
    definition: str,
) -> None:
    """Install NOT VALID foreign keys without breaking historical dirty data."""
    await conn.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{constraint_name}'
            ) THEN
                ALTER TABLE {table_name}
                ADD CONSTRAINT {constraint_name}
                {definition}
                NOT VALID;
            END IF;
        END $$;
        """
    )


async def _ensure_market_schema_migration_table(conn) -> None:
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_MARKET_SCHEMA_MIGRATION_TABLE} (
            migration_key TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )


async def _run_market_migration_once(conn, migration_key: str, statement: str) -> bool:
    await _ensure_market_schema_migration_table(conn)
    already_applied = await conn.fetchval(
        f"SELECT 1 FROM {_MARKET_SCHEMA_MIGRATION_TABLE} WHERE migration_key = $1",
        migration_key,
    )
    if already_applied:
        return False
    await conn.execute(statement)
    await conn.execute(
        f"""
        INSERT INTO {_MARKET_SCHEMA_MIGRATION_TABLE} (migration_key, applied_at)
        VALUES ($1, NOW())
        ON CONFLICT (migration_key) DO NOTHING
        """,
        migration_key,
    )
    return True
