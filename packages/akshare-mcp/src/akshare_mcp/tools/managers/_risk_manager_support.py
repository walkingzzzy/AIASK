"""Risk manager tools: VaR, stress test, and exposure analysis."""

from __future__ import annotations

import numpy as np
import time
from typing import Any

from ...storage import get_db
from ...utils import normalize_code
from ..manager_protocol import fail_with_meta, normalize_manager_payload, ok_with_meta

from .risk_mgr_helpers import (
    _classify_size_bucket,
    _empty_stress_payload,
    _empty_var_payload,
    _first_float,
    _format_pct,
    _liquidity_level,
    _normalize_kwargs,
    _parse_codes_weights,
    _parse_dict_param,
    _parse_list_param,
    _safe_float,
    _safe_portfolio_id,
)

def _extract_holding_code(holding: dict) -> str:
    return normalize_code(
        str(
            holding.get("code")
            or holding.get("stock_code")
            or holding.get("symbol")
            or ""
        )
    )

def _extract_holding_shares(holding: dict) -> float:
    raw = holding.get("shares")
    if raw is None:
        raw = holding.get("quantity")
    if raw is None:
        raw = holding.get("qty")
    return float(raw or 0)

async def _load_portfolio_holdings(conn, portfolio_id: Any) -> list[dict]:
    rows = await conn.fetch("SELECT * FROM holdings WHERE portfolio_id = $1", portfolio_id)
    holdings = []
    for row in rows:
        item = dict(row)
        code = _extract_holding_code(item)
        shares = _extract_holding_shares(item)
        if not code or shares <= 0:
            continue
        holdings.append({**item, "code": code, "shares": shares})
    return holdings

async def _get_klines_with_fallback(db, code: str, limit: int) -> list[dict]:
    try:
        klines = await db.get_klines(code, limit=limit)
        if klines:
            return klines, ["db.get_klines"]
    except Exception:
        pass

    try:
        from ..market import get_kline

        res = await get_kline(code, "daily", limit)
        if res.get("success") and isinstance(res.get("data"), list):
            return res["data"], ["tools.market.get_kline"]
    except Exception:
        pass
    return [], []

async def _get_stock_info_with_fallback(db, code: str) -> dict:
    try:
        payload = await db.get_stock_info(code)
        if isinstance(payload, dict):
            return payload, ["db.get_stock_info"]
    except Exception:
        pass
    return {}, []

async def _get_financials_with_fallback(db, code: str):
    try:
        payload = await db.get_financials(code, limit=1)
        if isinstance(payload, (list, dict)):
            return payload, ["db.get_financials"]
    except Exception:
        pass
    return [], []

def _dedupe_chain(values: list[str]) -> list[str]:
    chain = []
    seen = set()
    for value in values:
        label = str(value or "").strip()
        if not label or label in seen:
            continue
        chain.append(label)
        seen.add(label)
    return chain
