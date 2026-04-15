import asyncio
import os

import asyncpg

from akshare_mcp.storage.timescaledb._schema_market_phase_1 import init_market_tables_phase_1
from akshare_mcp.storage.timescaledb._schema_market_phase_2 import init_market_tables_phase_2
from akshare_mcp.storage.timescaledb._schema_market_phase_3 import init_market_tables_phase_3
from akshare_mcp.storage.timescaledb._schema_market_phase_4 import init_market_tables_phase_4
from akshare_mcp.storage.timescaledb._schema_market_phase_5 import init_market_tables_phase_5
from akshare_mcp.storage.timescaledb._schema_market_phase_6 import init_market_tables_phase_6
from akshare_mcp.storage.timescaledb._schema_market_phase_7 import init_market_tables_phase_7
from akshare_mcp.storage.timescaledb.schema_strategy import init_strategy_tables
from akshare_mcp.storage.timescaledb.schema_vector import init_vector_tables


async def ensure_pgvector(conn) -> bool:
    enabled = False
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        enabled = True
    except Exception:
        try:
            enabled = bool(
                await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')",
                )
            )
        except Exception:
            enabled = False
    return enabled


async def main() -> None:
    conn = await asyncpg.connect(
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        database=os.getenv("DB_NAME", "postgres"),
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
    )

    try:
        pgvector_enabled = await ensure_pgvector(conn)
        await init_market_tables_phase_1(conn)
        await init_market_tables_phase_2(conn)
        await init_market_tables_phase_3(conn)
        await init_market_tables_phase_4(conn)
        await init_market_tables_phase_5(conn)
        await init_vector_tables(conn, pgvector_enabled)
        await init_strategy_tables(conn, pgvector_enabled)
        await init_market_tables_phase_6(conn)
        await init_market_tables_phase_7(conn)
        print(f"[mcp-schema-bootstrap] done pgvector={str(pgvector_enabled).lower()}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
