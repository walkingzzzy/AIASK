"""Read-only market temperature MCP tool."""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timedelta
from typing import Any

from ..services.market_temperature import build_market_temperature_snapshot
from ..storage import get_db
from .manager_protocol import ERR_INTERNAL, ERR_PARAM, fail_with_meta, ok_with_meta

TOOL_NAME = "get_market_temperature_snapshot"
REFRESH_TOOL_NAME = "refresh_market_temperature_snapshot_cache"
LIST_CACHE_TOOL_NAME = "list_market_temperature_snapshot_cache"
INDUSTRY_HISTORY_TOOL_NAME = "list_market_temperature_industry_history"
INDUSTRY_CONSTITUENTS_TOOL_NAME = "list_market_temperature_industry_constituents"
FORWARD_VALIDATION_TOOL_NAME = "get_market_temperature_forward_validation"


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return int(parsed)


def _first_safe_float(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _first_safe_int(default: int, *values: Any) -> int:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return int(parsed)
    return default


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _pct_change(latest: dict[str, Any], previous: dict[str, Any] | None) -> float | None:
    explicit = _safe_float(_first_present(latest, "change_pct", "pct_change"))
    if explicit is not None:
        return explicit
    close = _safe_float(latest.get("close"))
    prev_close = _safe_float((previous or {}).get("close"))
    if close is None or prev_close is None or prev_close <= 0:
        return None
    return (close - prev_close) / prev_close * 100.0


async def _build_stock_row(db: Any, stock: dict[str, Any], *, as_of: str | None, min_bars: int) -> dict[str, Any] | None:
    code = str(stock.get("code") or "").strip()
    if not code:
        return None
    try:
        klines = await db.get_klines(code, end_date=as_of, limit=max(21, int(min_bars or 20) + 1))
    except TypeError:
        klines = await db.get_klines(code, limit=max(21, int(min_bars or 20) + 1))
    except Exception:
        return None
    if not klines:
        return None
    latest = dict(klines[-1])
    previous = dict(klines[-2]) if len(klines) >= 2 else None
    closes = [_safe_float(row.get("close")) for row in klines[-20:]]
    close_values = [value for value in closes if value is not None]
    ma20 = sum(close_values) / len(close_values) if len(close_values) >= 20 else None
    return {
        "code": code,
        "name": stock.get("name") or stock.get("stock_name") or code,
        "industry": stock.get("industry") or stock.get("sector") or "",
        "date": latest.get("date") or latest.get("time"),
        "close": latest.get("close"),
        "pct_change": _pct_change(latest, previous),
        "ma20": ma20,
        "amount": latest.get("amount"),
        "turnover": latest.get("turnover"),
        "market_cap": stock.get("market_cap") or latest.get("market_cap") or latest.get("mkt_cap"),
    }


async def _load_stock_rows_from_db(db: Any, *, limit: int, as_of: str | None, min_bars: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    universe_limit = max(1, min(int(limit or 300), 1000))
    universe = await db.list_stock_universe(limit=universe_limit)
    semaphore = asyncio.Semaphore(16)

    async def guarded(stock: dict[str, Any]) -> dict[str, Any] | None:
        async with semaphore:
            return await _build_stock_row(db, stock, as_of=as_of, min_bars=min_bars)

    rows = await asyncio.gather(*(guarded(dict(stock or {})) for stock in universe))
    stock_rows = [row for row in rows if row is not None]
    return stock_rows, {
        "universe_limit": universe_limit,
        "universe_count": len(universe),
        "loaded_stock_rows": len(stock_rows),
        "missing_kline_rows": max(0, len(universe) - len(stock_rows)),
    }


def _bounded_top_n(value: int) -> int:
    return max(0, min(int(value or 0), 50))


def _sort_industries_by_temperature(industries: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    if reverse:
        return sorted(
            industries,
            key=lambda item: (
                _safe_float(item.get("temperature")) is not None,
                _safe_float(item.get("temperature")) if _safe_float(item.get("temperature")) is not None else -1.0,
                _safe_float(item.get("market_cap")) or 0.0,
            ),
            reverse=True,
        )
    return sorted(
        industries,
        key=lambda item: (
            _safe_float(item.get("temperature")) is None,
            _safe_float(item.get("temperature")) if _safe_float(item.get("temperature")) is not None else 101.0,
            -(_safe_float(item.get("market_cap")) or 0.0),
        ),
    )


def _snapshot_with_top_n(snapshot: dict[str, Any], top_n: int) -> dict[str, Any]:
    payload = dict(snapshot or {})
    industries = [dict(item or {}) for item in list(payload.get("industries") or [])]
    safe_top_n = _bounded_top_n(top_n)
    payload["industries"] = industries
    payload["hot_industries"] = _sort_industries_by_temperature(industries, reverse=True)[:safe_top_n]
    payload["cold_industries"] = _sort_industries_by_temperature(industries, reverse=False)[:safe_top_n]
    return payload


def _compact_cache_row(row: dict[str, Any], *, include_snapshot: bool = False) -> dict[str, Any]:
    snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    warnings = row.get("warnings") or quality.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = []
    payload = {
        "as_of": row.get("as_of") or snapshot.get("as_of"),
        "contract_version": row.get("contract_version") or snapshot.get("contract_version"),
        "market_temperature": _first_safe_float(row.get("market_temperature"), market.get("temperature")),
        "market_state": row.get("market_state") or market.get("state"),
        "stock_count": _first_safe_int(0, row.get("stock_count"), market.get("stock_count")),
        "industry_count": _first_safe_int(0, row.get("industry_count"), quality.get("industry_count")),
        "quality_status": row.get("quality_status") or quality.get("status"),
        "warnings": warnings,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    if include_snapshot:
        payload["snapshot"] = snapshot
    return payload


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_match_token(value: Any) -> str:
    return _safe_text(value).lower()


def _industry_matches(industry_row: dict[str, Any], query: str, *, match_mode: str) -> bool:
    needle = _normalize_match_token(query)
    if not needle:
        return True
    tokens = [
        _normalize_match_token(industry_row.get("code")),
        _normalize_match_token(industry_row.get("name")),
        _normalize_match_token(industry_row.get("industry")),
        _normalize_match_token(industry_row.get("industry_name")),
    ]
    if match_mode == "contains":
        return any(needle in token for token in tokens if token)
    return any(needle == token for token in tokens if token)


def _compact_industry_history_row(
    cache_row: dict[str, Any],
    industry_row: dict[str, Any],
    *,
    include_source_chain: bool = False,
) -> dict[str, Any]:
    snapshot = cache_row.get("snapshot") if isinstance(cache_row.get("snapshot"), dict) else {}
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    warnings = cache_row.get("warnings") or quality.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = []
    payload = {
        "as_of": cache_row.get("as_of") or snapshot.get("as_of") or industry_row.get("date"),
        "code": industry_row.get("code") or industry_row.get("industry_code") or "",
        "name": industry_row.get("name") or industry_row.get("industry") or "",
        "temperature": _safe_float(industry_row.get("temperature")),
        "state": industry_row.get("state"),
        "ma20_breadth": _safe_float(industry_row.get("ma20_breadth")),
        "advance_count": _safe_int(industry_row.get("advance_count")),
        "decline_count": _safe_int(industry_row.get("decline_count")),
        "flat_count": _safe_int(industry_row.get("flat_count")),
        "stock_count": _safe_int(industry_row.get("stock_count")),
        "market_cap_weight": _safe_float(industry_row.get("market_cap_weight")),
        "market_temperature": _first_safe_float(cache_row.get("market_temperature"), market.get("temperature")),
        "market_state": cache_row.get("market_state") or market.get("state"),
        "quality_status": cache_row.get("quality_status") or quality.get("status"),
        "warnings": warnings,
        "updated_at": cache_row.get("updated_at"),
    }
    if include_source_chain:
        payload["source_chain"] = [
            _safe_text(item)
            for item in list(snapshot.get("source_chain") or [])
            if _safe_text(item)
        ]
    return payload


def _stock_industry_matches(stock_row: dict[str, Any], query: str, *, match_mode: str) -> bool:
    needle = _normalize_match_token(query)
    if not needle:
        return False
    tokens = [
        _normalize_match_token(stock_row.get("industry_code")),
        _normalize_match_token(stock_row.get("sw_industry_code")),
        _normalize_match_token(stock_row.get("industry")),
        _normalize_match_token(stock_row.get("sector")),
        _normalize_match_token(stock_row.get("industry_name")),
        _normalize_match_token(stock_row.get("sw_industry")),
    ]
    if match_mode == "exact":
        return any(needle == token for token in tokens if token)
    return any(needle in token for token in tokens if token)


def _compact_industry_constituent_row(
    stock_row: dict[str, Any],
    *,
    include_source_chain: bool = False,
) -> dict[str, Any]:
    payload = {
        "code": _safe_text(stock_row.get("code")),
        "name": stock_row.get("name") or stock_row.get("stock_name") or _safe_text(stock_row.get("code")),
        "industry_code": stock_row.get("industry_code") or stock_row.get("sw_industry_code"),
        "industry": stock_row.get("industry") or stock_row.get("sector") or "",
        "sector": stock_row.get("sector") or stock_row.get("industry") or "",
        "market": stock_row.get("market"),
        "market_cap": _safe_float(stock_row.get("market_cap")),
        "pe_ratio": _safe_float(stock_row.get("pe_ratio")),
        "pb_ratio": _safe_float(stock_row.get("pb_ratio")),
        "list_date": stock_row.get("list_date"),
    }
    if include_source_chain:
        payload["source_chain"] = ["db.stocks"]
    return payload


def _parse_forward_horizons(value: Any) -> list[int]:
    raw_items = value
    if raw_items in (None, "", []):
        raw_items = [1, 3, 5]
    if isinstance(raw_items, str):
        raw_items = raw_items.replace(";", ",").split(",")
    if not isinstance(raw_items, (list, tuple, set)):
        raw_items = [raw_items]
    horizons: list[int] = []
    seen: set[int] = set()
    for item in raw_items:
        try:
            parsed = float(item)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(parsed):
            continue
        horizon = int(parsed)
        horizon = max(1, min(horizon, 20))
        if horizon in seen:
            continue
        seen.add(horizon)
        horizons.append(horizon)
    return horizons or [1, 3, 5]


def _market_snapshot_from_cache_row(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    quality = snapshot.get("quality") if isinstance(snapshot.get("quality"), dict) else {}
    return {
        "as_of": row.get("as_of") or snapshot.get("as_of"),
        "temperature": _first_safe_float(row.get("market_temperature"), market.get("temperature")),
        "state": row.get("market_state") or market.get("state") or "unknown",
        "avg_pct_change": _safe_float(market.get("avg_pct_change")),
        "weighted_pct_change": _safe_float(market.get("weighted_pct_change")),
        "quality_status": row.get("quality_status") or quality.get("status"),
        "warnings": row.get("warnings") or quality.get("warnings") or [],
    }


def _forward_target_value(row: dict[str, Any], target_field: str) -> float | None:
    if target_field == "avg_pct_change":
        return _safe_float(row.get("avg_pct_change"))
    if target_field == "temperature_delta":
        return _safe_float(row.get("temperature"))
    return _safe_float(row.get("weighted_pct_change"))


def _forward_window_return(
    rows: list[dict[str, Any]],
    start_index: int,
    horizon: int,
    *,
    target_field: str,
) -> float | None:
    if target_field == "temperature_delta":
        current = _safe_float(rows[start_index].get("temperature"))
        future_index = start_index + horizon
        if current is None or future_index >= len(rows):
            return None
        future = _safe_float(rows[future_index].get("temperature"))
        if future is None:
            return None
        return future - current

    values: list[float] = []
    for row in rows[start_index + 1:start_index + horizon + 1]:
        value = _forward_target_value(row, target_field)
        if value is not None:
            values.append(value)
    if len(values) < horizon:
        return None
    return sum(values)


def _parse_trade_date(value: Any) -> datetime | None:
    text = _safe_text(value)[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def _date_plus_days(value: Any, days: int) -> str | None:
    parsed = _parse_trade_date(value)
    if parsed is None:
        return None
    return (parsed + timedelta(days=max(1, int(days or 1)))).strftime("%Y-%m-%d")


def _compact_benchmark_bar(row: dict[str, Any]) -> dict[str, Any] | None:
    date_text = _safe_text(row.get("date") or row.get("time"))[:10]
    close = _safe_float(row.get("close"))
    if not date_text or close is None or close <= 0:
        return None
    return {"date": date_text, "close": close}


async def _load_benchmark_bars(
    db: Any,
    *,
    benchmark_code: str,
    start_date: str | None,
    end_date: str | None,
) -> list[dict[str, Any]]:
    code = _safe_text(benchmark_code) or "000300"
    readers = [getattr(db, "get_index_klines", None), getattr(db, "get_klines", None)]
    for reader in readers:
        if not callable(reader):
            continue
        try:
            rows = await reader(code, start_date=start_date, end_date=end_date)
        except TypeError:
            try:
                rows = await reader(code, limit=500)
            except TypeError:
                rows = await reader(code)
        except Exception:
            continue
        bars = []
        for raw_row in list(rows or []):
            try:
                row = dict(raw_row or {})
            except (TypeError, ValueError):
                continue
            bar = _compact_benchmark_bar(row)
            if bar is not None:
                bars.append(bar)
        if bars:
            bars.sort(key=lambda item: str(item.get("date") or ""))
            return bars
    return []


def _benchmark_forward_return(
    bars: list[dict[str, Any]],
    as_of: Any,
    horizon: int,
) -> tuple[float | None, dict[str, Any]]:
    date_text = _safe_text(as_of)[:10]
    if not date_text or not bars:
        return None, {}
    start_index = next(
        (index for index, bar in enumerate(bars) if str(bar.get("date") or "") >= date_text),
        None,
    )
    if start_index is None:
        return None, {}
    future_index = start_index + max(1, int(horizon or 1))
    if future_index >= len(bars):
        return None, {}
    current = _safe_float(bars[start_index].get("close"))
    future = _safe_float(bars[future_index].get("close"))
    if current is None or future is None or current <= 0:
        return None, {}
    return (future / current - 1.0) * 100.0, {
        "benchmark_as_of": bars[start_index].get("date"),
        "benchmark_forward_date": bars[future_index].get("date"),
        "benchmark_close": current,
        "benchmark_forward_close": future,
    }


def _state_direction_hit(state: str, forward_value: float, *, neutral_band_pct: float) -> bool:
    normalized = str(state or "unknown").strip().lower()
    if normalized in {"hot", "warm"}:
        return forward_value > 0
    if normalized in {"cold", "cool"}:
        return forward_value < 0
    if normalized == "neutral":
        return abs(forward_value) <= neutral_band_pct
    return False


def _summarize_forward_values(values: list[float], hits: list[bool], *, min_samples: int) -> dict[str, Any]:
    safe_values = [value for value in values if math.isfinite(value)]
    safe_hits = hits[: len(safe_values)]
    sample_n = len(safe_values)
    payload: dict[str, Any] = {
        "sample_n": sample_n,
        "direction_hits": sum(1 for item in safe_hits if item),
        "reliable": sample_n >= min_samples,
    }
    if sample_n:
        payload["avg_forward_return"] = sum(safe_values) / sample_n
        payload["hit_rate"] = payload["direction_hits"] / sample_n
        payload["min_forward_return"] = min(safe_values)
        payload["max_forward_return"] = max(safe_values)
    else:
        payload["avg_forward_return"] = None
        payload["hit_rate"] = None
        payload["min_forward_return"] = None
        payload["max_forward_return"] = None
    return payload


async def _cached_snapshot(db: Any, *, as_of: str | None, top_n: int) -> dict[str, Any] | None:
    reader = getattr(db, "get_market_temperature_snapshot_cache", None)
    if not callable(reader):
        return None
    cached = await reader(as_of)
    if not cached:
        return None
    snapshot = cached.get("snapshot") if isinstance(cached, dict) else None
    if not isinstance(snapshot, dict) or not snapshot:
        return None
    payload = _snapshot_with_top_n(snapshot, top_n)
    source_chain = [
        "market_temperature_snapshots",
        *[str(item) for item in list(payload.get("source_chain") or []) if str(item).strip()],
    ]
    payload["source_chain"] = source_chain
    quality = dict(payload.get("quality") or {})
    quality["cache_status"] = "hit"
    quality["cache_updated_at"] = cached.get("updated_at")
    payload["quality"] = quality
    payload["cache"] = {
        "status": "hit",
        "as_of": cached.get("as_of") or payload.get("as_of"),
        "updated_at": cached.get("updated_at"),
        "created_at": cached.get("created_at"),
        "source": "market_temperature_snapshots",
    }
    return payload


async def _compute_snapshot_from_db(
    db: Any,
    *,
    limit: int,
    top_n: int,
    as_of: str | None,
    min_bars: int,
    source_chain: list[str],
) -> tuple[dict[str, Any], bool]:
    stock_rows, load_quality = await _load_stock_rows_from_db(
        db,
        limit=limit,
        as_of=as_of,
        min_bars=min_bars,
    )
    snapshot = build_market_temperature_snapshot(
        stock_rows,
        as_of=as_of,
        top_n=top_n,
    )
    quality = dict(snapshot.get("quality") or {})
    quality.update(load_quality)
    degraded = quality.get("status") != "healthy" or bool(load_quality.get("missing_kline_rows"))
    if load_quality.get("universe_count") and load_quality.get("loaded_stock_rows") < load_quality.get("universe_count"):
        quality.setdefault("warnings", [])
        if "partial_kline_coverage" not in quality["warnings"]:
            quality["warnings"].append("partial_kline_coverage")
        quality["status"] = "degraded"
        degraded = True
    snapshot["quality"] = quality
    snapshot["source_chain"] = source_chain
    return snapshot, degraded


async def get_market_temperature_snapshot(
    limit: int = 300,
    top_n: int = 8,
    as_of: str | None = None,
    min_bars: int = 20,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Build a read-only market temperature snapshot from local SQLite data.

    The tool deliberately caps the default universe so it is safe for ad-hoc MCP
    calls. A full-market production path should persist daily snapshots during
    data sync and serve them directly.
    """

    started_at = time.perf_counter()
    source_chain = ["db.stocks", "db.kline_1d", "market_temperature.service"]
    try:
        db = get_db()
        if use_cache:
            cached_snapshot = await _cached_snapshot(db, as_of=as_of, top_n=top_n)
            if cached_snapshot is not None:
                quality = dict(cached_snapshot.get("quality") or {})
                return ok_with_meta(
                    cached_snapshot,
                    tool_name=TOOL_NAME,
                    action="snapshot",
                    started_at=started_at,
                    source_chain=cached_snapshot.get("source_chain") or ["market_temperature_snapshots"],
                    data_timestamp=cached_snapshot.get("as_of"),
                    cached=True,
                    extra_meta={
                        "degraded": quality.get("status") != "healthy",
                        "quality": quality,
                        "side_effect": {
                            "level": "read_only",
                            "target": "market_temperature_snapshot",
                            "confirmation_required": False,
                            "idempotent": True,
                        },
                    },
                )

        snapshot, degraded = await _compute_snapshot_from_db(
            db,
            limit=limit,
            top_n=top_n,
            as_of=as_of,
            min_bars=min_bars,
            source_chain=source_chain,
        )
        quality = dict(snapshot.get("quality") or {})
        return ok_with_meta(
            snapshot,
            tool_name=TOOL_NAME,
            action="snapshot",
            started_at=started_at,
            source_chain=source_chain,
            data_timestamp=snapshot.get("as_of"),
            extra_meta={
                "degraded": degraded,
                "quality": quality,
                "side_effect": {
                    "level": "read_only",
                    "target": "market_temperature_snapshot",
                    "confirmation_required": False,
                    "idempotent": True,
                },
            },
        )
    except Exception as exc:
        return fail_with_meta(
            str(exc),
            tool_name=TOOL_NAME,
            action="snapshot",
            started_at=started_at,
            source_chain=source_chain,
            error_code=ERR_INTERNAL,
            extra_meta={
                "degraded": True,
                "quality": {
                    "status": "failed",
                    "quality_flags": ["market_temperature_snapshot_failed"],
                },
            },
        )


async def refresh_market_temperature_snapshot_cache(
    limit: int = 1000,
    top_n: int = 20,
    as_of: str | None = None,
    min_bars: int = 20,
) -> dict[str, Any]:
    """Refresh the durable local market-temperature cache.

    This tool is explicit local-state mutation for data-sync jobs. The Agent
    finance-safe facade intentionally exposes only the read-only snapshot tool.
    """

    started_at = time.perf_counter()
    source_chain = ["db.stocks", "db.kline_1d", "market_temperature.service", "market_temperature_snapshots"]
    try:
        db = get_db()
        snapshot, degraded = await _compute_snapshot_from_db(
            db,
            limit=limit,
            top_n=top_n,
            as_of=as_of,
            min_bars=min_bars,
            source_chain=source_chain[:-1],
        )
        writer = getattr(db, "save_market_temperature_snapshot", None)
        if not callable(writer):
            raise RuntimeError("market temperature snapshot storage is unavailable")
        cached = await writer(
            snapshot,
            request={"limit": limit, "top_n": top_n, "as_of": as_of, "min_bars": min_bars},
            source_chain=source_chain,
        )
        saved_snapshot = dict(cached.get("snapshot") or snapshot)
        saved_snapshot["cache"] = {
            "status": "written",
            "as_of": cached.get("as_of") or saved_snapshot.get("as_of"),
            "updated_at": cached.get("updated_at"),
            "created_at": cached.get("created_at"),
            "source": "market_temperature_snapshots",
        }
        saved_snapshot["source_chain"] = source_chain
        quality = dict(saved_snapshot.get("quality") or {})
        quality["cache_status"] = "written"
        quality["cache_updated_at"] = cached.get("updated_at")
        saved_snapshot["quality"] = quality
        return ok_with_meta(
            saved_snapshot,
            tool_name=REFRESH_TOOL_NAME,
            action="refresh_cache",
            started_at=started_at,
            source_chain=source_chain,
            data_timestamp=saved_snapshot.get("as_of"),
            extra_meta={
                "degraded": degraded,
                "quality": quality,
                "side_effect": {
                    "level": "local_state",
                    "target": "market_temperature_snapshots",
                    "confirmation_required": False,
                    "idempotent": True,
                },
            },
        )
    except Exception as exc:
        return fail_with_meta(
            str(exc),
            tool_name=REFRESH_TOOL_NAME,
            action="refresh_cache",
            started_at=started_at,
            source_chain=source_chain,
            error_code=ERR_INTERNAL,
            extra_meta={
                "degraded": True,
                "quality": {
                    "status": "failed",
                    "quality_flags": ["market_temperature_snapshot_cache_refresh_failed"],
                },
                "side_effect": {
                    "level": "local_state",
                    "target": "market_temperature_snapshots",
                    "confirmation_required": False,
                    "idempotent": True,
                },
            },
        )


async def list_market_temperature_snapshot_cache(
    limit: int = 30,
    include_snapshot: bool = False,
) -> dict[str, Any]:
    """List compact metadata for durable market-temperature cache entries."""

    started_at = time.perf_counter()
    source_chain = ["market_temperature_snapshots"]
    try:
        db = get_db()
        reader = getattr(db, "list_market_temperature_snapshot_cache", None)
        if not callable(reader):
            raise RuntimeError("market temperature snapshot storage is unavailable")
        safe_limit = max(1, min(int(limit or 30), 365))
        rows = await reader(safe_limit)
        items = [
            _compact_cache_row(dict(row or {}), include_snapshot=bool(include_snapshot))
            for row in list(rows or [])
        ]
        payload = {
            "items": items,
            "count": len(items),
            "limit": safe_limit,
            "include_snapshot": bool(include_snapshot),
            "source_chain": source_chain,
        }
        return ok_with_meta(
            payload,
            tool_name=LIST_CACHE_TOOL_NAME,
            action="list_cache",
            started_at=started_at,
            source_chain=source_chain,
            data_timestamp=items[0].get("as_of") if items else None,
            cached=True,
            extra_meta={
                "degraded": False,
                "quality": {
                    "status": "available" if items else "empty",
                    "row_count": len(items),
                    "cache_status": "listed",
                },
                "side_effect": {
                    "level": "read_only",
                    "target": "market_temperature_snapshots",
                    "confirmation_required": False,
                    "idempotent": True,
                },
            },
        )
    except Exception as exc:
        return fail_with_meta(
            str(exc),
            tool_name=LIST_CACHE_TOOL_NAME,
            action="list_cache",
            started_at=started_at,
            source_chain=source_chain,
            error_code=ERR_INTERNAL,
            extra_meta={
                "degraded": True,
                "quality": {
                    "status": "failed",
                    "quality_flags": ["market_temperature_snapshot_cache_list_failed"],
                },
                "side_effect": {
                    "level": "read_only",
                    "target": "market_temperature_snapshots",
                    "confirmation_required": False,
                    "idempotent": True,
                },
            },
        )


async def list_market_temperature_industry_history(
    industry: str | None = None,
    limit: int = 120,
    top_n: int = 10,
    match_mode: str = "exact",
    include_source_chain: bool = False,
) -> dict[str, Any]:
    """List point-in-time industry temperature history from durable cache entries."""

    started_at = time.perf_counter()
    source_chain = ["market_temperature_snapshots", "market_temperature.industry_history"]
    try:
        db = get_db()
        reader = getattr(db, "list_market_temperature_snapshot_cache", None)
        if not callable(reader):
            raise RuntimeError("market temperature snapshot storage is unavailable")
        safe_limit = max(1, min(int(limit or 120), 365))
        safe_top_n = max(1, min(int(top_n or 10), 50))
        normalized_match_mode = str(match_mode or "exact").strip().lower()
        if normalized_match_mode not in {"exact", "contains"}:
            normalized_match_mode = "exact"
        query = _safe_text(industry)
        rows = await reader(safe_limit)
        items: list[dict[str, Any]] = []
        for raw_row in list(rows or []):
            row = dict(raw_row or {})
            snapshot = row.get("snapshot") if isinstance(row.get("snapshot"), dict) else {}
            industries = [
                dict(item or {})
                for item in list(snapshot.get("industries") or [])
                if isinstance(item, dict)
            ]
            matches = [
                item
                for item in industries
                if _industry_matches(item, query, match_mode=normalized_match_mode)
            ]
            if not query:
                matches = _sort_industries_by_temperature(matches, reverse=True)[:safe_top_n]
            for industry_row in matches:
                items.append(
                    _compact_industry_history_row(
                        row,
                        industry_row,
                        include_source_chain=bool(include_source_chain),
                    )
                )
        items.sort(key=lambda item: (str(item.get("as_of") or ""), str(item.get("name") or "")))
        payload = {
            "items": items,
            "count": len(items),
            "limit": safe_limit,
            "top_n": safe_top_n,
            "industry": query or None,
            "match_mode": normalized_match_mode,
            "include_source_chain": bool(include_source_chain),
            "source_chain": source_chain,
        }
        return ok_with_meta(
            payload,
            tool_name=INDUSTRY_HISTORY_TOOL_NAME,
            action="industry_history",
            started_at=started_at,
            source_chain=source_chain,
            data_timestamp=items[-1].get("as_of") if items else None,
            cached=True,
            extra_meta={
                "degraded": False,
                "quality": {
                    "status": "available" if items else "empty",
                    "row_count": len(items),
                    "cache_status": "listed",
                    "industry": query or None,
                },
                "side_effect": {
                    "level": "read_only",
                    "target": "market_temperature_snapshots",
                    "confirmation_required": False,
                    "idempotent": True,
                },
            },
        )
    except Exception as exc:
        return fail_with_meta(
            str(exc),
            tool_name=INDUSTRY_HISTORY_TOOL_NAME,
            action="industry_history",
            started_at=started_at,
            source_chain=source_chain,
            error_code=ERR_INTERNAL,
            extra_meta={
                "degraded": True,
                "quality": {
                    "status": "failed",
                    "quality_flags": ["market_temperature_industry_history_failed"],
                },
                "side_effect": {
                    "level": "read_only",
                    "target": "market_temperature_snapshots",
                    "confirmation_required": False,
                    "idempotent": True,
                },
            },
        )


async def list_market_temperature_industry_constituents(
    industry: str,
    limit: int = 200,
    offset: int = 0,
    match_mode: str = "contains",
    include_source_chain: bool = False,
) -> dict[str, Any]:
    """List local stock-universe constituents for one market-temperature industry."""

    started_at = time.perf_counter()
    source_chain = ["db.stocks", "market_temperature.industry_constituents"]
    query = _safe_text(industry)
    safe_limit = max(1, min(int(limit or 200), 1000))
    safe_offset = max(0, min(int(offset or 0), 10000))
    normalized_match_mode = str(match_mode or "contains").strip().lower()
    if normalized_match_mode not in {"exact", "contains"}:
        normalized_match_mode = "contains"
    side_effect = {
        "level": "read_only",
        "target": "stocks",
        "confirmation_required": False,
        "idempotent": True,
    }

    if not query:
        return fail_with_meta(
            "industry is required",
            tool_name=INDUSTRY_CONSTITUENTS_TOOL_NAME,
            action="industry_constituents",
            started_at=started_at,
            source_chain=source_chain,
            error_code=ERR_PARAM,
            extra_meta={
                "degraded": True,
                "quality": {
                    "status": "failed",
                    "quality_flags": ["market_temperature_industry_required"],
                },
                "side_effect": side_effect,
            },
        )

    try:
        db = get_db()
        reader = getattr(db, "list_stock_universe", None)
        if not callable(reader):
            raise RuntimeError("stock universe storage is unavailable")

        fetch_limit = min(10000, max(safe_offset + safe_limit * 5, safe_limit))
        try:
            rows = await reader(limit=fetch_limit, offset=0, industry=query)
        except TypeError:
            try:
                rows = await reader(limit=fetch_limit, offset=0)
            except TypeError:
                rows = await reader(limit=fetch_limit)

        candidates: list[dict[str, Any]] = []
        for raw_row in list(rows or []):
            try:
                candidates.append(dict(raw_row or {}))
            except (TypeError, ValueError):
                continue
        matches = [
            row
            for row in candidates
            if _stock_industry_matches(row, query, match_mode=normalized_match_mode)
        ]
        page = matches[safe_offset:safe_offset + safe_limit]
        items = [
            _compact_industry_constituent_row(
                row,
                include_source_chain=bool(include_source_chain),
            )
            for row in page
        ]
        payload = {
            "items": items,
            "count": len(items),
            "total_matches": len(matches),
            "limit": safe_limit,
            "offset": safe_offset,
            "industry": query,
            "match_mode": normalized_match_mode,
            "include_source_chain": bool(include_source_chain),
            "source_chain": source_chain,
        }
        return ok_with_meta(
            payload,
            tool_name=INDUSTRY_CONSTITUENTS_TOOL_NAME,
            action="industry_constituents",
            started_at=started_at,
            source_chain=source_chain,
            cached=True,
            extra_meta={
                "degraded": False,
                "quality": {
                    "status": "available" if items else "empty",
                    "row_count": len(items),
                    "total_matches": len(matches),
                    "industry": query,
                },
                "side_effect": side_effect,
            },
        )
    except Exception as exc:
        return fail_with_meta(
            str(exc),
            tool_name=INDUSTRY_CONSTITUENTS_TOOL_NAME,
            action="industry_constituents",
            started_at=started_at,
            source_chain=source_chain,
            error_code=ERR_INTERNAL,
            extra_meta={
                "degraded": True,
                "quality": {
                    "status": "failed",
                    "quality_flags": ["market_temperature_industry_constituents_failed"],
                },
                "side_effect": side_effect,
            },
        )


async def get_market_temperature_forward_validation(
    limit: int = 180,
    horizons: list[int] | str | int | None = None,
    target_field: str = "weighted_pct_change",
    benchmark_code: str | None = None,
    min_samples: int = 3,
    neutral_band_pct: float = 0.2,
    include_samples: bool = False,
) -> dict[str, Any]:
    """Build a read-only PIT forward-validation matrix from cached market-temperature snapshots."""

    started_at = time.perf_counter()
    source_chain = ["market_temperature_snapshots", "market_temperature.forward_validation"]
    side_effect = {
        "level": "read_only",
        "target": "market_temperature_snapshots",
        "confirmation_required": False,
        "idempotent": True,
    }
    try:
        db = get_db()
        reader = getattr(db, "list_market_temperature_snapshot_cache", None)
        if not callable(reader):
            raise RuntimeError("market temperature snapshot storage is unavailable")
        safe_limit = max(2, min(int(limit or 180), 365))
        safe_horizons = _parse_forward_horizons(horizons)
        requested_target = str(target_field or "weighted_pct_change").strip().lower() or "weighted_pct_change"
        normalized_target = requested_target
        quality_warnings: list[str] = []
        if normalized_target not in {"weighted_pct_change", "avg_pct_change", "temperature_delta", "benchmark_return"}:
            normalized_target = "weighted_pct_change"
            quality_warnings.append("unsupported_target_field_fallback_to_weighted_pct_change")
        safe_benchmark_code = _safe_text(benchmark_code) or ("000300" if normalized_target == "benchmark_return" else "")
        safe_min_samples = max(1, min(int(min_samples or 3), 100))
        safe_neutral_band = max(0.0, min(_safe_float(neutral_band_pct) or 0.0, 5.0))
        rows = await reader(min(365, safe_limit + max(safe_horizons)))
        market_rows = [
            _market_snapshot_from_cache_row(dict(row or {}))
            for row in list(rows or [])
        ]
        market_rows = [
            row
            for row in market_rows
            if _safe_text(row.get("as_of")) and _safe_float(row.get("temperature")) is not None
        ]
        market_rows.sort(key=lambda item: str(item.get("as_of") or ""))
        source_chain_for_response = list(source_chain)
        benchmark_bars: list[dict[str, Any]] = []
        benchmark_status = "not_requested"
        if normalized_target == "benchmark_return":
            start_date = str(market_rows[0].get("as_of") or "") if market_rows else None
            end_date = _date_plus_days(
                market_rows[-1].get("as_of") if market_rows else None,
                max(safe_horizons) * 7 + 14,
            )
            benchmark_bars = await _load_benchmark_bars(
                db,
                benchmark_code=safe_benchmark_code,
                start_date=start_date,
                end_date=end_date,
            )
            source_chain_for_response.append("db.kline_1d")
            if benchmark_bars:
                benchmark_status = "available"
            else:
                benchmark_status = "unavailable_fallback_to_weighted_pct_change"
                quality_warnings.append("benchmark_kline_unavailable")
                normalized_target = "weighted_pct_change"

        buckets: dict[str, dict[int, dict[str, list[Any]]]] = {}
        samples: list[dict[str, Any]] = []
        for index, row in enumerate(market_rows):
            state = str(row.get("state") or "unknown").strip().lower() or "unknown"
            for horizon in safe_horizons:
                sample_extra: dict[str, Any] = {}
                if normalized_target == "benchmark_return":
                    forward_value, sample_extra = _benchmark_forward_return(
                        benchmark_bars,
                        row.get("as_of"),
                        horizon,
                    )
                else:
                    forward_value = _forward_window_return(
                        market_rows,
                        index,
                        horizon,
                        target_field=normalized_target,
                    )
                if forward_value is None:
                    continue
                hit = _state_direction_hit(state, forward_value, neutral_band_pct=safe_neutral_band)
                bucket = buckets.setdefault(state, {}).setdefault(horizon, {"values": [], "hits": []})
                bucket["values"].append(forward_value)
                bucket["hits"].append(hit)
                if include_samples:
                    samples.append(
                        {
                            "as_of": row.get("as_of"),
                            "state": state,
                            "temperature": row.get("temperature"),
                            "horizon": horizon,
                            "forward_return": forward_value,
                            "direction_hit": hit,
                            "target_field": normalized_target,
                            **sample_extra,
                        }
                    )

        matrix: dict[str, dict[str, Any]] = {}
        for state, horizon_map in sorted(buckets.items()):
            matrix[state] = {}
            for horizon in safe_horizons:
                cell = horizon_map.get(horizon, {"values": [], "hits": []})
                matrix[state][f"{horizon}d"] = _summarize_forward_values(
                    [
                        value
                        for item in list(cell.get("values") or [])
                        if (value := _safe_float(item)) is not None
                    ],
                    [bool(item) for item in list(cell.get("hits") or [])],
                    min_samples=safe_min_samples,
                )

        sample_count = sum(
            int(cell.get("sample_n") or 0)
            for state_cells in matrix.values()
            for cell in state_cells.values()
        )
        payload = {
            "matrix": matrix,
            "states": sorted(matrix.keys()),
            "horizons": safe_horizons,
            "count": sample_count,
            "snapshot_count": len(market_rows),
            "limit": safe_limit,
            "target_field": normalized_target,
            "requested_target_field": requested_target,
            "benchmark_code": safe_benchmark_code or None,
            "benchmark_status": benchmark_status,
            "benchmark_bar_count": len(benchmark_bars),
            "min_samples": safe_min_samples,
            "neutral_band_pct": safe_neutral_band,
            "include_samples": bool(include_samples),
            "samples": samples[:500] if include_samples else [],
            "source_chain": source_chain_for_response,
        }
        return ok_with_meta(
            payload,
            tool_name=FORWARD_VALIDATION_TOOL_NAME,
            action="forward_validation",
            started_at=started_at,
            source_chain=source_chain_for_response,
            data_timestamp=market_rows[-1].get("as_of") if market_rows else None,
            cached=True,
            extra_meta={
                "degraded": len(market_rows) < max(safe_horizons) + safe_min_samples or bool(quality_warnings),
                "quality": {
                    "status": "available" if sample_count else "empty",
                    "row_count": sample_count,
                    "snapshot_count": len(market_rows),
                    "target_field": normalized_target,
                    "requested_target_field": requested_target,
                    "benchmark_status": benchmark_status,
                    "warnings": quality_warnings,
                },
                "side_effect": side_effect,
            },
        )
    except Exception as exc:
        return fail_with_meta(
            str(exc),
            tool_name=FORWARD_VALIDATION_TOOL_NAME,
            action="forward_validation",
            started_at=started_at,
            source_chain=source_chain,
            error_code=ERR_INTERNAL,
            extra_meta={
                "degraded": True,
                "quality": {
                    "status": "failed",
                    "quality_flags": ["market_temperature_forward_validation_failed"],
                },
                "side_effect": side_effect,
            },
        )


def register(mcp) -> None:
    mcp.tool()(get_market_temperature_snapshot)
    mcp.tool()(refresh_market_temperature_snapshot_cache)
    mcp.tool()(list_market_temperature_snapshot_cache)
    mcp.tool()(list_market_temperature_industry_history)
    mcp.tool()(list_market_temperature_industry_constituents)
    mcp.tool()(get_market_temperature_forward_validation)
