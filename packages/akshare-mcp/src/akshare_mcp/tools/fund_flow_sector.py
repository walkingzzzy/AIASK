"""
fund_flow_sector.py
Sector (industry) and concept board fund-flow functions.
"""

import time
from typing import Any, Optional

import akshare as ak
import requests

from ..storage import get_db
from ..utils import fail, ok, parse_numeric, pick_value, safe_float
from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter

from .fund_flow_common import (
    _ProxyBypass,
    _RETRY_SLEEP_SECONDS,
    _SECTOR_FLOW_TIMEOUT_SECONDS,
    _SECTOR_FLOW_INDICATORS,
    _SECTOR_FLOW_CACHE_MAX_AGE,
    _SECTOR_FLOW_DISABLE_PROXY_ON_FAIL,
    _sector_flow_cache,
    _run_with_timeout,
    _run_storage_call_sync,
    _get_env_proxy,
    _load_sector_flow_cache,
    _save_sector_flow_cache,
)


# =====================
# Eastmoney direct fallback
# =====================

def _fetch_sector_flow_eastmoney(top_n: int) -> list[dict]:
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": top_n,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fs": "m:90+t:2",
            "fields": "f12,f14,f3,f62,f66,f184",
        }
        proxies = _get_env_proxy() or None
        response = requests.get(url, params=params, timeout=6, proxies=proxies)
        if response.status_code != 200:
            return []
        payload = response.json()
        items = payload.get("data", {}).get("diff", []) if isinstance(payload, dict) else []
        results: list[dict] = []
        for item in items:
            change_raw = parse_numeric(item.get("f3"))
            main_in = parse_numeric(item.get("f62"))
            main_out = parse_numeric(item.get("f66"))
            net_inflow = None
            if main_in is not None and main_out is not None:
                net_inflow = main_in - main_out
            results.append(
                {
                    "name": str(item.get("f14") or ""),
                    "changePercent": change_raw / 100 if change_raw is not None else None,
                    "mainNetInflow": net_inflow if net_inflow is not None else main_in,
                    "mainNetInflowPercent": parse_numeric(item.get("f184")),
                    "superLargeNetInflow": None,
                    "largeNetInflow": None,
                    "mediumNetInflow": None,
                    "smallNetInflow": None,
                }
            )
        return results
    except requests.exceptions.ProxyError:
        try:
            response = requests.get(url, params=params, timeout=6)
            if response.status_code != 200:
                return []
            payload = response.json()
            items = payload.get("data", {}).get("diff", []) if isinstance(payload, dict) else []
            results: list[dict] = []
            for item in items:
                change_raw = parse_numeric(item.get("f3"))
                main_in = parse_numeric(item.get("f62"))
                main_out = parse_numeric(item.get("f66"))
                net_inflow = None
                if main_in is not None and main_out is not None:
                    net_inflow = main_in - main_out
                results.append(
                    {
                        "name": str(item.get("f14") or ""),
                        "changePercent": change_raw / 100 if change_raw is not None else None,
                        "mainNetInflow": net_inflow if net_inflow is not None else main_in,
                        "mainNetInflowPercent": parse_numeric(item.get("f184")),
                        "superLargeNetInflow": None,
                        "largeNetInflow": None,
                        "mediumNetInflow": None,
                        "smallNetInflow": None,
                    }
                )
            return results
        except Exception:
            return []
    except Exception:
        return []


def _fetch_sector_flow_from_db(top_n: int) -> list[dict]:
    async def _load():
        db = get_db()
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT block_name, avg_change_pct, stock_count, total_amount
                FROM market_blocks
                WHERE block_type = 'industry' AND block_name IS NOT NULL AND block_name != ''
                ORDER BY updated_at DESC NULLS LAST, avg_change_pct DESC NULLS LAST
                LIMIT $1
                """,
                max(1, int(top_n)),
            )
        return [dict(row) for row in rows]

    try:
        rows = _run_storage_call_sync(_load, timeout=3.0)
    except Exception:
        return []

    results: list[dict] = []
    for row in list(rows or []):
        name = str(row.get("block_name") or "").strip()
        if not name:
            continue
        change_pct = safe_float(row.get("avg_change_pct"))
        # DB market_blocks 不提供主力净流入，退化为用涨跌幅作为热度代理，
        # 以便上层排序/冷热板块分析保持稳定响应。
        heat_proxy = change_pct if change_pct is not None else 0.0
        results.append(
            {
                "name": name,
                "changePercent": change_pct,
                "mainNetInflow": heat_proxy,
                "mainNetInflowPercent": None,
                "superLargeNetInflow": None,
                "largeNetInflow": None,
                "mediumNetInflow": None,
                "smallNetInflow": None,
                "stockCount": int(row.get("stock_count") or 0),
                "totalAmount": safe_float(row.get("total_amount")),
                "source": "db.market_blocks",
                "degraded": True,
            }
        )
    return results


# =====================
# Public: get_sector_fund_flow
# =====================

@cached(ttl=300.0)
def get_sector_fund_flow(top_n: int = 20) -> dict:
    """
    获取行业板块资金流向

    Args:
        top_n: 返回前N个板块，默认20
    """
    limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
    limiter.acquire()

    try:
        top_n = int(top_n)
        df = None
        last_error: Optional[Exception] = None

        cached_data = _sector_flow_cache.get("data")
        cached_ts = _sector_flow_cache.get("ts", 0.0)
        if cached_data and (time.time() - float(cached_ts)) <= _SECTOR_FLOW_CACHE_MAX_AGE:
            return ok(list(cached_data)[:top_n], cached=True)

        file_cached = _load_sector_flow_cache()
        if file_cached:
            _sector_flow_cache["data"] = file_cached
            _sector_flow_cache["ts"] = time.time()
            return ok(list(file_cached)[:top_n], cached=True)

        db_fallback = _fetch_sector_flow_from_db(top_n)
        if db_fallback:
            _sector_flow_cache["data"] = db_fallback
            _sector_flow_cache["ts"] = time.time()
            _save_sector_flow_cache(db_fallback)
            return ok(db_fallback, cached=True)

        direct_fallback = _fetch_sector_flow_eastmoney(top_n)
        if direct_fallback:
            _sector_flow_cache["data"] = direct_fallback
            _sector_flow_cache["ts"] = time.time()
            _save_sector_flow_cache(direct_fallback)
            return ok(direct_fallback)

        max_retries = 3
        indicators = _SECTOR_FLOW_INDICATORS or ["今日"]
        for _ in range(max_retries):
            for indicator in indicators:
                try:
                    df = _run_with_timeout(
                        lambda: ak.stock_sector_fund_flow_rank(indicator=indicator),
                        _SECTOR_FLOW_TIMEOUT_SECONDS,
                    )
                    if df is not None and not df.empty:
                        break
                except Exception as exc:
                    last_error = exc
                    df = None
                    if _RETRY_SLEEP_SECONDS > 0:
                        time.sleep(_RETRY_SLEEP_SECONDS)
            if df is not None and not df.empty:
                break

        # Proxy-bypass retry
        if (df is None or df.empty) and _SECTOR_FLOW_DISABLE_PROXY_ON_FAIL:
            if isinstance(last_error, requests.exceptions.ProxyError) or (
                last_error and "proxy" in str(last_error).lower()
            ):
                with _ProxyBypass():
                    for indicator in indicators:
                        try:
                            df = _run_with_timeout(
                                lambda: ak.stock_sector_fund_flow_rank(indicator=indicator),
                                _SECTOR_FLOW_TIMEOUT_SECONDS,
                            )
                            if df is not None and not df.empty:
                                break
                        except Exception as exc:
                            last_error = exc
                            df = None

        if df is None or df.empty:
            # Fallback: Eastmoney direct
            fallback = _fetch_sector_flow_eastmoney(top_n)
            if fallback:
                _sector_flow_cache["data"] = fallback
                _sector_flow_cache["ts"] = time.time()
                _save_sector_flow_cache(fallback)
                return ok(fallback)

            # DB fallback
            db_fallback = _fetch_sector_flow_from_db(top_n)
            if db_fallback:
                _sector_flow_cache["data"] = db_fallback
                _sector_flow_cache["ts"] = time.time()
                _save_sector_flow_cache(db_fallback)
                return ok(db_fallback, cached=True)

            # In-memory cache
            cached_data = _sector_flow_cache.get("data")
            cached_ts = _sector_flow_cache.get("ts", 0.0)
            if cached_data and (time.time() - float(cached_ts)) <= _SECTOR_FLOW_CACHE_MAX_AGE:
                return ok(list(cached_data)[:top_n], cached=True)

            # File cache
            file_cached = _load_sector_flow_cache()
            if file_cached:
                return ok(list(file_cached)[:top_n], cached=True)

            # Last resort: reuse concept fund flow
            try:
                concept = get_concept_fund_flow(top_n=top_n)
            except Exception as exc:
                concept = fail(exc)
            if concept.get("success") and concept.get("data"):
                return ok(concept["data"], cached=True)

            msg = str(last_error) if last_error else "接口返回为空"
            return fail(f"未获取到行业板块资金流向数据 (Retried {max_retries} times): {msg}")

        df = df.head(top_n)
        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "name": str(row.get("名称", "")),
                    "changePercent": safe_float(row.get("今日涨跌幅")),
                    "mainNetInflow": safe_float(row.get("主力净流入-净额")),
                    "mainNetInflowPercent": safe_float(row.get("主力净流入-净占比")),
                    "superLargeNetInflow": safe_float(row.get("超大单净流入-净额")),
                    "largeNetInflow": safe_float(row.get("大单净流入-净额")),
                    "mediumNetInflow": safe_float(row.get("中单净流入-净额")),
                    "smallNetInflow": safe_float(row.get("小单净流入-净额")),
                }
            )
        _sector_flow_cache["data"] = results
        _sector_flow_cache["ts"] = time.time()
        _save_sector_flow_cache(results)
        return ok(results)
    except Exception as e:
        cached_data = _sector_flow_cache.get("data")
        cached_ts = _sector_flow_cache.get("ts", 0.0)
        if cached_data and (time.time() - float(cached_ts)) <= _SECTOR_FLOW_CACHE_MAX_AGE:
            return ok(cached_data, cached=True)
        file_cached = _load_sector_flow_cache()
        if file_cached:
            return ok(file_cached, cached=True)
        return fail(f"系统错误: {e}")


# =====================
# Public: get_concept_fund_flow
# =====================

@cached(ttl=300.0)
def get_concept_fund_flow(top_n: int = 20) -> dict:
    """
    获取概念板块资金流向

    Args:
        top_n: 返回前N个板块，默认20
    """
    limiter = get_limiter("fund_flow", max_calls=3, period=1.0)
    limiter.acquire()

    try:
        top_n = int(top_n)
        df = ak.stock_fund_flow_concept(symbol="即时")
        if df is None or df.empty:
            return fail("未获取到概念板块资金流向数据")

        df = df.head(top_n)
        results: list[dict] = []
        for _, row in df.iterrows():
            name = pick_value(row, ["行业", "概念", "名称"]) or ""
            change = safe_float(pick_value(row, ["行业-涨跌幅", "阶段涨跌幅", "涨跌幅", "最新涨跌幅"]))
            net_inflow = safe_float(pick_value(row, ["净额", "主力净流入-净额", "主力净流入"]))
            inflow = safe_float(pick_value(row, ["流入资金"]))
            outflow = safe_float(pick_value(row, ["流出资金"]))
            results.append(
                {
                    "name": str(name),
                    "changePercent": change,
                    "mainNetInflow": net_inflow if net_inflow is not None else inflow,
                    "mainNetInflowPercent": None,
                    "inflow": inflow,
                    "outflow": outflow,
                }
            )
        return ok(results)
    except Exception as e:
        return fail(e)
