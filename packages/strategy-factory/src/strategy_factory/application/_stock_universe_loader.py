"""Shared paginated stock-universe loading helpers."""

from __future__ import annotations

import inspect
from typing import Any


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return max(0, int(default))


async def load_stock_universe_rows(
    db,
    *,
    limit: int,
    page_size: int,
    start_offset: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load stock-universe rows page by page until exhausted or the requested cap is reached."""

    requested_limit = max(1, _coerce_non_negative_int(limit, 1))
    effective_page_size = max(1, min(_coerce_non_negative_int(page_size, requested_limit), requested_limit))
    current_offset = max(0, _coerce_non_negative_int(start_offset, 0))
    list_stock_universe = getattr(db, "list_stock_universe", None)

    meta: dict[str, Any] = {
        "available": callable(list_stock_universe),
        "requested_limit": requested_limit,
        "page_size": effective_page_size,
        "start_offset": current_offset,
        "pages_loaded": 0,
        "loaded_count": 0,
        "raw_loaded_count": 0,
        "next_offset": current_offset,
        "exhausted": False,
        "truncated": False,
        "complete": False,
    }
    if not callable(list_stock_universe):
        return [], meta

    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    while meta["raw_loaded_count"] < requested_limit:
        fetch_limit = min(effective_page_size, requested_limit - int(meta["raw_loaded_count"]))
        result = list_stock_universe(limit=fetch_limit, offset=current_offset)
        if inspect.isawaitable(result):
            result = await result
        try:
            page_rows = [dict(item or {}) for item in list(result or []) if isinstance(item, dict)]
        except Exception:
            page_rows = []

        meta["pages_loaded"] = int(meta["pages_loaded"]) + 1
        page_count = len(page_rows)
        if page_count <= 0:
            meta["exhausted"] = True
            break

        meta["raw_loaded_count"] = int(meta["raw_loaded_count"]) + page_count
        for index, row in enumerate(page_rows):
            code = str((row or {}).get("code") or "").strip()
            dedupe_key = code or f"row:{current_offset + index}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            rows.append(row)

        current_offset += page_count
        meta["next_offset"] = current_offset
        if page_count < fetch_limit:
            meta["exhausted"] = True
            break

    meta["loaded_count"] = len(rows)
    meta["truncated"] = bool(meta["raw_loaded_count"] >= requested_limit and not meta["exhausted"])
    meta["complete"] = bool(meta["exhausted"])
    return rows, meta
