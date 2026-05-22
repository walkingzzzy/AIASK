"""股票列表工具"""

import sqlite3
from typing import Any

from ...utils import ok
from ...core.cache_manager import cached
from .helpers import get_stock_list_cached
from ...storage.sqlite.schema_base import default_sqlite_path


async def _stock_list_from_db(limit: int, offset: int) -> tuple[list[dict], int]:
    from ...storage import get_db

    db = get_db()
    async with db.acquire() as conn:
        cols_rows = await conn.fetch("SELECT name AS column_name FROM pragma_table_info('stocks')")
        columns = {str(row["column_name"]) for row in cols_rows or []}
        code_col = "stock_code" if "stock_code" in columns else ("code" if "code" in columns else "")
        name_col = "stock_name" if "stock_name" in columns else ("name" if "name" in columns else "")
        if not code_col:
            return [], 0

        select_name = f"{name_col} AS name" if name_col else "'' AS name"
        optional = []
        for col in ("industry", "sector", "market", "list_date", "market_cap", "pe_ratio", "pb_ratio"):
            if col in columns:
                optional.append(col)
        select_fields = [f"{code_col} AS code", select_name, *optional]
        total = await conn.fetchval(f"SELECT COUNT(*) FROM stocks WHERE {code_col} IS NOT NULL")
        rows = await conn.fetch(
            f"""
            SELECT {', '.join(select_fields)}
            FROM stocks
            WHERE {code_col} IS NOT NULL
            ORDER BY {code_col}
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return [dict(row) for row in rows or []], int(total or 0)


def _stock_list_from_sqlite(limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    path = default_sqlite_path()
    if not path.exists():
        return [], 0

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cols_rows = conn.execute("PRAGMA table_info('stocks')").fetchall()
        columns = {str(row["name"]) for row in cols_rows or []}
        code_col = "stock_code" if "stock_code" in columns else ("code" if "code" in columns else "")
        name_col = "stock_name" if "stock_name" in columns else ("name" if "name" in columns else "")
        if not code_col:
            return [], 0

        select_name = f"{name_col} AS name" if name_col else "'' AS name"
        optional = [
            col for col in ("industry", "sector", "market", "list_date", "market_cap", "pe_ratio", "pb_ratio")
            if col in columns
        ]
        select_fields = [f"{code_col} AS code", select_name, *optional]
        total = conn.execute(f"SELECT COUNT(*) FROM stocks WHERE {code_col} IS NOT NULL").fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT {', '.join(select_fields)}
            FROM stocks
            WHERE {code_col} IS NOT NULL
            ORDER BY {code_col}
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows or []], int(total or 0)
    finally:
        conn.close()


@cached(ttl=86400.0)  # 24h cache
def get_stock_list(limit: int = 500, offset: int = 0) -> dict:
    """获取A股股票列表，返回股票代码和名称。

    Examples:
        get_stock_list()
    """
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(int(limit or 500), 5000))
    try:
        data, _ = get_stock_list_cached()
        total = len(data)
        page = data[safe_offset:safe_offset + safe_limit]
        return ok({
            'stocks': page,
            'count': len(page),
            'total': total,
            'offset': safe_offset,
            'limit': safe_limit,
            'truncated': safe_offset + len(page) < total,
        })
    except Exception as e:
        fallback_reason = str(e)

    try:
        page, total = _stock_list_from_sqlite(safe_limit, safe_offset)
        response = ok({
            'stocks': page,
            'count': len(page),
            'total': total,
            'offset': safe_offset,
            'limit': safe_limit,
            'truncated': safe_offset + len(page) < total,
            'degraded': True,
            'fallback_used': True,
            'fallback_reason': fallback_reason,
        })
        response.update({
            'source': 'db.stocks' if page else 'none',
            'source_chain': ['market.stock_list', 'db.stocks'],
            'degraded': True,
            'fallback_used': True,
            'fallback_reason': fallback_reason,
        })
        meta = response.setdefault('meta', {})
        quality = meta.setdefault('quality', {})
        quality.update({
            'status': 'degraded',
            'source_chain': response['source_chain'],
            'fallback_used': True,
            'fallback_reason': fallback_reason,
            'backend_used': response['source'],
            'record_count': len(page),
        })
        meta['degraded'] = True
        meta['source_chain'] = response['source_chain']
        return response
    except Exception as db_exc:
        response = ok({
            'stocks': [],
            'count': 0,
            'total': 0,
            'offset': safe_offset,
            'limit': safe_limit,
            'truncated': False,
            'message': 'stock list providers unavailable',
            'degraded': True,
            'fallback_used': True,
            'fallback_reason': [fallback_reason, str(db_exc)],
        })
        response.update({
            'source': 'none',
            'source_chain': ['market.stock_list', 'db.stocks'],
            'degraded': True,
            'fallback_used': True,
            'fallback_reason': [fallback_reason, str(db_exc)],
        })
        meta = response.setdefault('meta', {})
        quality = meta.setdefault('quality', {})
        quality.update({
            'status': 'degraded',
            'source_chain': response['source_chain'],
            'fallback_used': True,
            'fallback_reason': response['fallback_reason'],
            'backend_used': 'none',
            'record_count': 0,
        })
        meta['degraded'] = True
        meta['source_chain'] = response['source_chain']
        return response
