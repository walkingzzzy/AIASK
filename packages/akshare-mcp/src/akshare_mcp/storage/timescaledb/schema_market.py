"""
Market data table DDL — kline, financials, portfolios, alerts, etc.

All ~30 market-data tables are created via a single entry point:

    await init_market_tables(conn)

The function is idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
"""

from ._schema_market_common import logger, _run_market_migration_once
from ._schema_market_phase_1 import init_market_tables_phase_1
from ._schema_market_phase_2 import init_market_tables_phase_2
from ._schema_market_phase_3 import init_market_tables_phase_3
from ._schema_market_phase_4 import init_market_tables_phase_4


async def init_market_tables(conn) -> None:
    """Create / migrate all market-data tables."""
    await init_market_tables_phase_1(conn)
    await init_market_tables_phase_2(conn)
    await init_market_tables_phase_3(conn)
    await init_market_tables_phase_4(conn)
    logger.info("Market tables initialized")
