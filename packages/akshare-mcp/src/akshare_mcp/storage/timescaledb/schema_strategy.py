"""
Strategy table DDL — strategies, incubation, risk, vector, factory, etc.

All ~25 strategy tables are created via a single entry point:

    await init_strategy_tables(conn, pgvector_enabled)

The function is idempotent (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).
pgvector-specific DDL (vector columns) is gated by the ``pgvector_enabled`` flag.
"""

import logging

from akshare_mcp._fragment_loader import exec_block as _exec_block

logger = logging.getLogger(__name__)

_exec_block(
    globals(),
    'schema_strategy_parts',
    'async def init_strategy_tables(conn, pgvector_enabled: bool = False) -> None:\n',
    ['schema_definitions.py', 'queries.py', 'writes.py', 'mappers.py', 'schema_tail.py'],
    future_annotations=False,
)
