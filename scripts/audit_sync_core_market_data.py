#!/usr/bin/env python3
"""Audit and backfill core market data for strategy-factory runtime."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
AKSHARE_MCP_SRC = ROOT / "packages" / "akshare-mcp" / "src"
STRATEGY_FACTORY_SRC = ROOT / "packages" / "strategy-factory" / "src"

for path in (str(AKSHARE_MCP_SRC), str(STRATEGY_FACTORY_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from akshare_mcp.data_source import data_source  # noqa: E402
from akshare_mcp.env_loader import load_mcp_env  # noqa: E402
from akshare_mcp.storage import get_db, run_with_db_cleanup  # noqa: E402


INDEX_TS_MAP = {
    "sh000001": "000001.SH",
    "sh000300": "000300.SH",
    "sh000016": "000016.SH",
    "sh000905": "000905.SH",
    "sz399001": "399001.SZ",
    "sz399005": "399005.SZ",
    "sz399006": "399006.SZ",
}

DEFAULT_STOCK_CODES = ["600519", "000858", "601318", "000001"]
TUSHARE_IP_LIMIT_ERROR_HINTS = (
    "IP数量超限",
    "最大数量为2个",
)

def _parse_codes(raw: str | None, *, default: Iterable[str]) -> list[str]:
    if not raw:
        return [str(item).strip() for item in default if str(item).strip()]
    items = []
    for part in str(raw).replace(";", ",").split(","):
        token = str(part).strip()
        if token:
            items.append(token)
    return items


def _today_range(years: int) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=max(int(years), 1) * 365)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _stock_ts_code(code: str) -> str:
    normalized = str(code).strip()
    if normalized.startswith(("5", "6", "9")):
        return f"{normalized}.SH"
    return f"{normalized}.SZ"


def _print_section(title: str, payload) -> None:
    print(f"\n## {title}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _is_tushare_ip_limit_error(exc: Exception | str) -> bool:
    text = str(exc or "").strip()
    if not text:
        return False
    return any(hint in text for hint in TUSHARE_IP_LIMIT_ERROR_HINTS)


def _all_failures_are_tushare_ip_limit(failures: list[dict]) -> bool:
    if not failures:
        return False
    return all(_is_tushare_ip_limit_error((item or {}).get("error", "")) for item in failures)


def _audit_has_existing_rows(audit_rows: list[dict], codes: Iterable[str]) -> bool:
    normalized_codes = [str(code).strip() for code in codes if str(code).strip()]
    if not normalized_codes:
        return False
    row_map = {
        str((item or {}).get("code") or "").strip(): int((item or {}).get("count") or 0)
        for item in list(audit_rows or [])
    }
    return all(row_map.get(code, 0) > 0 for code in normalized_codes)


async def _audit_codes(db, codes: list[str]) -> list[dict]:
    rows = []
    async with db.acquire() as conn:
        for code in codes:
            record = await conn.fetchrow(
                """
                SELECT code, COUNT(*) AS cnt, MIN(time::date) AS min_date, MAX(time::date) AS max_date
                FROM kline_1d
                WHERE code = $1
                GROUP BY code
                """,
                str(code),
            )
            if record:
                rows.append(
                    {
                        "code": record["code"],
                        "count": int(record["cnt"] or 0),
                        "min_date": record["min_date"].isoformat() if record["min_date"] else None,
                        "max_date": record["max_date"].isoformat() if record["max_date"] else None,
                    }
                )
            else:
                rows.append({"code": str(code), "count": 0, "min_date": None, "max_date": None})
    return rows


async def _ensure_aux_market_tables(db) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS north_fund_flow (
                trade_date DATE PRIMARY KEY,
                north_money DOUBLE PRECISION,
                south_money DOUBLE PRECISION,
                net_amount DOUBLE PRECISION,
                ggt_ss DOUBLE PRECISION,
                ggt_sz DOUBLE PRECISION,
                hgt DOUBLE PRECISION,
                sgt DOUBLE PRECISION,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        await conn.execute("ALTER TABLE north_fund_flow ADD COLUMN IF NOT EXISTS ggt_ss DOUBLE PRECISION")
        await conn.execute("ALTER TABLE north_fund_flow ADD COLUMN IF NOT EXISTS ggt_sz DOUBLE PRECISION")
        await conn.execute("ALTER TABLE north_fund_flow ADD COLUMN IF NOT EXISTS hgt DOUBLE PRECISION")
        await conn.execute("ALTER TABLE north_fund_flow ADD COLUMN IF NOT EXISTS sgt DOUBLE PRECISION")
        await conn.execute("ALTER TABLE north_fund_flow ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()")

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS margin_market_flow (
                trade_date DATE NOT NULL,
                exchange_id TEXT NOT NULL DEFAULT 'SSE',
                rzye DOUBLE PRECISION,
                rzmre DOUBLE PRECISION,
                rzche DOUBLE PRECISION,
                rqye DOUBLE PRECISION,
                rqmcl DOUBLE PRECISION,
                rqyl DOUBLE PRECISION,
                rzrqye DOUBLE PRECISION,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (trade_date, exchange_id)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS margin_detail (
                trade_date DATE NOT NULL,
                ts_code TEXT NOT NULL,
                rzye DOUBLE PRECISION,
                rqye DOUBLE PRECISION,
                rzmre DOUBLE PRECISION,
                rqyl DOUBLE PRECISION,
                rzche DOUBLE PRECISION,
                rqchl DOUBLE PRECISION,
                rqmcl DOUBLE PRECISION,
                rzrqye DOUBLE PRECISION,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (trade_date, ts_code)
            )
            """
        )


async def _audit_market_aux(db) -> dict:
    async with db.acquire() as conn:
        north = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt, MIN(trade_date) AS min_d, MAX(trade_date) AS max_d FROM north_fund_flow"
        )
        margin_market = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt, MIN(trade_date) AS min_d, MAX(trade_date) AS max_d FROM margin_market_flow"
        )
        margin_detail = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt, MIN(trade_date) AS min_d, MAX(trade_date) AS max_d FROM margin_detail"
        )
    return {
        "north_fund_flow": {
            "count": int((north or {}).get("cnt") or 0) if north else 0,
            "min_date": north.get("min_d").isoformat() if north and north.get("min_d") else None,
            "max_date": north.get("max_d").isoformat() if north and north.get("max_d") else None,
        },
        "margin_market_flow": {
            "count": int((margin_market or {}).get("cnt") or 0) if margin_market else 0,
            "min_date": margin_market.get("min_d").isoformat() if margin_market and margin_market.get("min_d") else None,
            "max_date": margin_market.get("max_d").isoformat() if margin_market and margin_market.get("max_d") else None,
        },
        "margin_detail": {
            "count": int((margin_detail or {}).get("cnt") or 0) if margin_detail else 0,
            "min_date": margin_detail.get("min_d").isoformat() if margin_detail and margin_detail.get("min_d") else None,
            "max_date": margin_detail.get("max_d").isoformat() if margin_detail and margin_detail.get("max_d") else None,
        },
    }


def _convert_stock_daily(df, code: str) -> list[dict]:
    if df is None or df.empty:
        return []
    df = df.iloc[::-1]
    out = []
    for _, row in df.iterrows():
        trade_date = str(row.get("trade_date") or "")
        if len(trade_date) < 8:
            continue
        out.append(
            {
                "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                "code": code,
                "open": float(row.get("open") or 0.0),
                "high": float(row.get("high") or 0.0),
                "low": float(row.get("low") or 0.0),
                "close": float(row.get("close") or 0.0),
                "volume": int(float(row.get("vol") or 0.0) * 100),
                "amount": float(row.get("amount") or 0.0) * 1000,
                "change_pct": float(row.get("pct_chg")) if row.get("pct_chg") is not None else None,
            }
        )
    return out


def _convert_index_daily(df, db_code: str) -> list[dict]:
    if df is None or df.empty:
        return []
    df = df.iloc[::-1]
    out = []
    for _, row in df.iterrows():
        trade_date = str(row.get("trade_date") or "")
        if len(trade_date) < 8:
            continue
        out.append(
            {
                "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                "code": db_code,
                "open": float(row.get("open") or 0.0),
                "high": float(row.get("high") or 0.0),
                "low": float(row.get("low") or 0.0),
                "close": float(row.get("close") or 0.0),
                "volume": int(float(row.get("vol") or 0.0)),
                "amount": float(row.get("amount") or 0.0),
                "change_pct": float(row.get("pct_chg")) if row.get("pct_chg") is not None else None,
            }
        )
    return out


async def _sync_indices(db, *, start_date: str, end_date: str) -> dict:
    ts_pro = data_source.get_tushare_pro()
    if ts_pro is None:
        raise RuntimeError("Tushare Pro unavailable")
    result = {"codes": [], "saved_rows": 0, "fetched_rows": 0, "failed": []}
    for db_code, ts_code in INDEX_TS_MAP.items():
        try:
            df = ts_pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            rows = _convert_index_daily(df, db_code)
            saved = await db.save_klines(db_code, rows)
            result["codes"].append({"code": db_code, "ts_code": ts_code, "rows": len(rows), "saved": int(saved or 0)})
            result["saved_rows"] += int(saved or 0)
            result["fetched_rows"] += len(rows)
        except Exception as exc:
            result["failed"].append({"code": db_code, "ts_code": ts_code, "error": str(exc)})
    return result


async def _sync_stocks(db, *, stock_codes: list[str], start_date: str, end_date: str) -> dict:
    ts_pro = data_source.get_tushare_pro()
    if ts_pro is None:
        raise RuntimeError("Tushare Pro unavailable")
    result = {"codes": [], "saved_rows": 0, "fetched_rows": 0, "failed": []}
    for code in stock_codes:
        ts_code = _stock_ts_code(code)
        try:
            df = ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            rows = _convert_stock_daily(df, code)
            saved = await db.save_klines(code, rows)
            result["codes"].append({"code": code, "ts_code": ts_code, "rows": len(rows), "saved": int(saved or 0)})
            result["saved_rows"] += int(saved or 0)
            result["fetched_rows"] += len(rows)
        except Exception as exc:
            result["failed"].append({"code": code, "ts_code": ts_code, "error": str(exc)})
    return result


async def _sync_trading_calendar(db, *, years: list[int]) -> dict:
    del db
    sync_items = []
    for year in years:
        rows = data_source.get_trading_dates(start_time=f"{year}0101", end_time=f"{year}1231")
        sync_items.append(
            {
                "year": year,
                "success": bool(rows.get("success")),
                "count": len(list(rows.get("data") or [])) if isinstance(rows, dict) else 0,
                "source": rows.get("source") if isinstance(rows, dict) else None,
            }
        )
    return {"years": sync_items}


async def _sync_north_fund(db, *, days: int) -> dict:
    ts_pro = data_source.get_tushare_pro()
    if ts_pro is None:
        raise RuntimeError("Tushare Pro unavailable")
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=max(int(days), 1))).strftime("%Y%m%d")
    try:
        df = ts_pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
    except Exception as exc:
        if _is_tushare_ip_limit_error(exc):
            return {
                "days": days,
                "rows": 0,
                "start_date": start_date,
                "end_date": end_date,
                "skipped": True,
                "skip_reason": str(exc),
            }
        raise
    rows = 0
    async with db.acquire() as conn:
        for _, row in (df.iloc[::-1].iterrows() if df is not None and not df.empty else []):
            trade_date = str(row.get("trade_date") or "")
            if len(trade_date) < 8:
                continue
            d = datetime.strptime(trade_date[:8], "%Y%m%d").date()
            await conn.execute(
                """
                INSERT INTO north_fund_flow
                    (trade_date, north_money, south_money, net_amount, ggt_ss, ggt_sz, hgt, sgt, updated_at)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ON CONFLICT (trade_date) DO UPDATE SET
                    north_money = EXCLUDED.north_money,
                    south_money = EXCLUDED.south_money,
                    net_amount = EXCLUDED.net_amount,
                    ggt_ss = EXCLUDED.ggt_ss,
                    ggt_sz = EXCLUDED.ggt_sz,
                    hgt = EXCLUDED.hgt,
                    sgt = EXCLUDED.sgt,
                    updated_at = NOW()
                """,
                d,
                float(row.get("north_money")) if row.get("north_money") is not None else None,
                float(row.get("south_money")) if row.get("south_money") is not None else None,
                float(row.get("north_money")) if row.get("north_money") is not None else None,
                float(row.get("ggt_ss")) if row.get("ggt_ss") is not None else None,
                float(row.get("ggt_sz")) if row.get("ggt_sz") is not None else None,
                float(row.get("hgt")) if row.get("hgt") is not None else None,
                float(row.get("sgt")) if row.get("sgt") is not None else None,
            )
            rows += 1
    return {
        "days": days,
        "rows": rows,
        "start_date": start_date,
        "end_date": end_date,
        "skipped": False,
        "skip_reason": None,
    }


async def _sync_margin(db, *, days: int) -> dict:
    ts_pro = data_source.get_tushare_pro()
    if ts_pro is None:
        raise RuntimeError("Tushare Pro unavailable")
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=max(int(days), 1))).strftime("%Y%m%d")
    trading_dates_resp = data_source.get_trading_dates(start_time=start_date, end_time=end_date)
    trading_dates = list((trading_dates_resp or {}).get("data") or [])
    result = {
        "days": days,
        "trade_dates": len(trading_dates),
        "market_rows": 0,
        "detail_rows": 0,
        "failed_dates": [],
        "start_date": start_date,
        "end_date": end_date,
        "skipped": False,
        "skip_reason": None,
    }
    async with db.acquire() as conn:
        for trade_date in trading_dates:
            try:
                market_df = ts_pro.margin(trade_date=trade_date)
                if market_df is not None and not market_df.empty:
                    market_params = []
                    for _, row in market_df.iterrows():
                        d = datetime.strptime(str(row.get("trade_date") or trade_date)[:8], "%Y%m%d").date()
                        exchange_id = str(row.get("exchange_id") or "SSE").strip() or "SSE"
                        market_params.append(
                            (
                                d,
                                exchange_id,
                                float(row.get("rzye")) if row.get("rzye") is not None else None,
                                float(row.get("rzmre")) if row.get("rzmre") is not None else None,
                                float(row.get("rzche")) if row.get("rzche") is not None else None,
                                float(row.get("rqye")) if row.get("rqye") is not None else None,
                                float(row.get("rqmcl")) if row.get("rqmcl") is not None else None,
                                float(row.get("rqyl")) if row.get("rqyl") is not None else None,
                                float(row.get("rzrqye")) if row.get("rzrqye") is not None else None,
                            )
                        )
                        result["market_rows"] += 1
                    if market_params:
                        await conn.executemany(
                            """
                            INSERT INTO margin_market_flow
                                (trade_date, exchange_id, rzye, rzmre, rzche, rqye, rqmcl, rqyl, rzrqye, updated_at)
                            VALUES
                                ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                            ON CONFLICT (trade_date, exchange_id) DO UPDATE SET
                                rzye = EXCLUDED.rzye,
                                rzmre = EXCLUDED.rzmre,
                                rzche = EXCLUDED.rzche,
                                rqye = EXCLUDED.rqye,
                                rqmcl = EXCLUDED.rqmcl,
                                rqyl = EXCLUDED.rqyl,
                                rzrqye = EXCLUDED.rzrqye,
                                updated_at = NOW()
                            """,
                            market_params,
                        )
                detail_df = ts_pro.margin_detail(trade_date=trade_date)
                if detail_df is not None and not detail_df.empty:
                    detail_params = []
                    for _, row in detail_df.iterrows():
                        d = datetime.strptime(str(row.get("trade_date") or trade_date)[:8], "%Y%m%d").date()
                        ts_code = str(row.get("ts_code") or "").strip()
                        if not ts_code:
                            continue
                        detail_params.append(
                            (
                                d,
                                ts_code,
                                float(row.get("rzye")) if row.get("rzye") is not None else None,
                                float(row.get("rqye")) if row.get("rqye") is not None else None,
                                float(row.get("rzmre")) if row.get("rzmre") is not None else None,
                                float(row.get("rqyl")) if row.get("rqyl") is not None else None,
                                float(row.get("rzche")) if row.get("rzche") is not None else None,
                                float(row.get("rqchl")) if row.get("rqchl") is not None else None,
                                float(row.get("rqmcl")) if row.get("rqmcl") is not None else None,
                                float(row.get("rzrqye")) if row.get("rzrqye") is not None else None,
                            )
                        )
                        result["detail_rows"] += 1
                    if detail_params:
                        await conn.executemany(
                            """
                            INSERT INTO margin_detail
                                (trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye, updated_at)
                            VALUES
                                ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                            ON CONFLICT (trade_date, ts_code) DO UPDATE SET
                                rzye = EXCLUDED.rzye,
                                rqye = EXCLUDED.rqye,
                                rzmre = EXCLUDED.rzmre,
                                rqyl = EXCLUDED.rqyl,
                                rzche = EXCLUDED.rzche,
                                rqchl = EXCLUDED.rqchl,
                                rqmcl = EXCLUDED.rqmcl,
                                rzrqye = EXCLUDED.rzrqye,
                                updated_at = NOW()
                            """,
                            detail_params,
                        )
            except Exception as exc:
                if _is_tushare_ip_limit_error(exc):
                    result["skipped"] = True
                    result["skip_reason"] = str(exc)
                    result["failed_dates"] = []
                    return result
                result["failed_dates"].append({"trade_date": trade_date, "error": str(exc)})
    return result


async def _main(args) -> int:
    load_mcp_env(override=False)
    db = get_db()
    await _ensure_aux_market_tables(db)
    stock_codes = _parse_codes(args.stock_codes, default=DEFAULT_STOCK_CODES)
    audit_targets = list(dict.fromkeys(list(INDEX_TS_MAP.keys()) + list(stock_codes)))
    start_date, end_date = _today_range(args.years)

    before = await _audit_codes(db, audit_targets)
    _print_section("audit_before", before)
    _print_section("market_aux_before", await _audit_market_aux(db))

    calendar_result = await _sync_trading_calendar(db, years=[args.calendar_year, args.calendar_year + 1])
    _print_section("sync_calendar", calendar_result)

    index_result = await _sync_indices(db, start_date=start_date, end_date=end_date)
    _print_section("sync_indices", index_result)

    stock_result = await _sync_stocks(db, stock_codes=stock_codes, start_date=start_date, end_date=end_date)
    _print_section("sync_stocks", stock_result)

    north_result = await _sync_north_fund(db, days=args.north_days)
    _print_section("sync_north_fund", north_result)

    margin_result = await _sync_margin(db, days=args.margin_days)
    _print_section("sync_margin", margin_result)

    after = await _audit_codes(db, audit_targets)
    _print_section("audit_after", after)
    _print_section("market_aux_after", await _audit_market_aux(db))

    index_skipped = _all_failures_are_tushare_ip_limit(index_result["failed"]) and _audit_has_existing_rows(
        after,
        INDEX_TS_MAP.keys(),
    )
    stock_skipped = _all_failures_are_tushare_ip_limit(stock_result["failed"]) and _audit_has_existing_rows(
        after,
        stock_codes,
    )

    summary = {
        "years": args.years,
        "start_date": start_date,
        "end_date": end_date,
        "index_saved_rows": index_result["saved_rows"],
        "stock_saved_rows": stock_result["saved_rows"],
        "index_failures": len(index_result["failed"]),
        "index_skipped": index_skipped,
        "index_skip_reason": index_result["failed"][0]["error"] if index_skipped else None,
        "stock_failures": len(stock_result["failed"]),
        "stock_skipped": stock_skipped,
        "stock_skip_reason": stock_result["failed"][0]["error"] if stock_skipped else None,
        "north_fund_rows": north_result["rows"],
        "north_fund_skipped": bool(north_result.get("skipped")),
        "north_fund_skip_reason": north_result.get("skip_reason"),
        "margin_market_rows": margin_result["market_rows"],
        "margin_detail_rows": margin_result["detail_rows"],
        "margin_failed_dates": len(margin_result["failed_dates"]),
        "margin_skipped": bool(margin_result.get("skipped")),
        "margin_skip_reason": margin_result.get("skip_reason"),
        "target_stock_codes": stock_codes,
    }
    _print_section("summary", summary)
    index_ok = not index_result["failed"] or index_skipped
    stock_ok = not stock_result["failed"] or stock_skipped
    return 0 if index_ok and stock_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and backfill core market data")
    parser.add_argument("--years", type=int, default=5, help="history years to backfill")
    parser.add_argument(
        "--stock-codes",
        type=str,
        default=",".join(DEFAULT_STOCK_CODES),
        help="comma-separated stock codes to backfill",
    )
    parser.add_argument(
        "--calendar-year",
        type=int,
        default=datetime.now().year,
        help="base trading-calendar year to sync",
    )
    parser.add_argument("--north-days", type=int, default=365, help="days of north-fund history to sync")
    parser.add_argument("--margin-days", type=int, default=90, help="days of margin history to sync")
    args = parser.parse_args()
    return run_with_db_cleanup(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
