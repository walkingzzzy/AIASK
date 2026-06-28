import aiosqlite
from pathlib import Path

DB_PATH = Path.home() / ".aiask" / "desktop.db"


async def _column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return any(str(row["name"]) == column for row in rows)


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, ddl: str) -> None:
    if not await _column_exists(db, table, column):
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


async def _backfill_sort_order(db: aiosqlite.Connection, table: str) -> None:
    cursor = await db.execute(
        f"SELECT id FROM {table} WHERE sort_order IS NULL ORDER BY created_at ASC, updated_at ASC, id ASC"
    )
    rows = await cursor.fetchall()
    for index, row in enumerate(rows):
        await db.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (index, row["id"]))

async def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    db = await get_db()
    await db.execute("""CREATE TABLE IF NOT EXISTS threads (
        id TEXT PRIMARY KEY, title TEXT, description TEXT, status TEXT DEFAULT 'active',
        message_count INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT, user_id TEXT DEFAULT 'default')""")
    await db.execute("""CREATE TABLE IF NOT EXISTS mcp_servers (
        id TEXT PRIMARY KEY, name TEXT, command TEXT, args TEXT, env TEXT,
        enabled BOOLEAN DEFAULT 1, created_at TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS skills (
        id TEXT PRIMARY KEY, name TEXT, type TEXT, path TEXT, enabled BOOLEAN DEFAULT 1,
        config TEXT, created_at TEXT)""")
    await db.execute("""CREATE TABLE IF NOT EXISTS strategies (
        id TEXT PRIMARY KEY, name TEXT, type TEXT, description TEXT, stocks TEXT,
        config TEXT, status TEXT DEFAULT 'active', performance TEXT,
        created_at TEXT, updated_at TEXT, user_id TEXT DEFAULT 'default')""")
    await db.execute("""CREATE TABLE IF NOT EXISTS stock_pools (
        id TEXT PRIMARY KEY, name TEXT, description TEXT, stocks TEXT,
        created_at TEXT, updated_at TEXT, user_id TEXT DEFAULT 'default')""")
    await _ensure_column(db, "strategies", "sort_order", "INTEGER")
    await _ensure_column(db, "stock_pools", "sort_order", "INTEGER")
    await _backfill_sort_order(db, "strategies")
    await _backfill_sort_order(db, "stock_pools")
    await db.commit()
    await db.close()
