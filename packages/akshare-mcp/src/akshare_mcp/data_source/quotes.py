"""
数据源管理 - 行情与K线方法

包含 get_realtime_quote、get_kline、_get_stock_name 等多源降级逻辑。
数据源优先级: Tushare Pro → Tushare legacy → eFinance/Baostock
"""

import datetime
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import redirect_stdout

from ..date_utils import format_date_dash, get_latest_trading_date
from ..utils import normalize_code, safe_float, safe_int, safe_stderr_print

_EFINANCE_TIMEOUT = float(os.getenv("EFINANCE_TIMEOUT", "12"))
_efinance_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="efinance")

logger = logging.getLogger(__name__)

try:
    import efinance as ef
except ImportError:
    ef = None

try:
    import tushare as ts  # 可选
except ImportError:  # pragma: no cover
    ts = None

try:
    from ..baostock_api import baostock_client
except (ImportError, Exception):
    baostock_client = None

# 本地 TDX 数据源（vipdoc + pytdx 兜底）
from .tdx_local import get_tdx_local_source as _get_tdx_local
# tqcenter 主路径（客户端在线时优先）
from . import tdx_tqcenter as _tqcenter


def _tdx_local_only() -> bool:
    return os.getenv("TDX_LOCAL_ONLY", "0") == "1"


def _keep_legacy_fallback() -> bool:
    """是否保留 Tushare/AKShare/eFinance/Baostock 作为最终兜底。

    默认 0：仅走 TDX（tqcenter → tdx_local）；
    设为 1 时保留旧降级链（仅在迁移过渡期使用）。
    """
    return os.getenv("DATA_SOURCE_KEEP_LEGACY_FALLBACK", "0") == "1"


def _to_tushare_ts_code(code: str) -> str:
    """Map a normalized stock code to the correct Tushare market suffix."""
    normalized = normalize_code(code)
    if normalized.startswith(("4", "8", "9")):
        return f"{normalized}.BJ"
    if normalized.startswith(("5", "6")) or normalized.startswith("11"):
        return f"{normalized}.SH"
    return f"{normalized}.SZ"


def _previous_business_day(current: datetime.date) -> datetime.date:
    value = current - datetime.timedelta(days=1)
    while value.weekday() >= 5:
        value -= datetime.timedelta(days=1)
    return value


def _expected_daily_kline_date(now: datetime.datetime | None = None) -> str:
    current = now or datetime.datetime.now()
    latest_trade_date = format_date_dash(get_latest_trading_date())
    if not latest_trade_date:
        return ""
    # 日线在交易时段通常仍停留在上一交易日收盘价，盘中不应视为陈旧。
    if current.strftime("%Y-%m-%d") == latest_trade_date and (current.hour, current.minute) < (16, 0):
        return _previous_business_day(current.date()).strftime("%Y-%m-%d")
    return latest_trade_date


class QuotesMixin:
    """行情与K线数据 Mixin"""

    # ---- 股票名称缓存 ----

    def _get_stock_name(self, code: str) -> str:
        """获取股票名称（带缓存），优先 Tushare stock_basic"""
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        code = normalize_code(code)
        if code in self._stock_name_cache:
            return self._stock_name_cache[code]
        # TDX_LOCAL_ONLY 模式下不调用网络
        if _tdx_local_only():
            return self._stock_name_cache.get(code, "")
        # 1. Tushare stock_basic（批量缓存）
        if self.ts_pro and not self._stock_name_cache:
            try:
                df = self.ts_pro.stock_basic(fields='ts_code,name')
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        c = str(row.get('ts_code', '')).split('.')[0]
                        n = str(row.get('name', '') or '')
                        if c and n:
                            self._stock_name_cache[c] = n
                    if code in self._stock_name_cache:
                        return self._stock_name_cache[code]
            except Exception:
                pass
        return self._stock_name_cache.get(code, '')

    # ---- 实时行情 ----

    def get_realtime_quote(self, code: str) -> dict:
        """获取实时行情。优先级：

        1. tqcenter (客户端在线 + 88 字段 snapshot 拼接)
        2. tdx_local (vipdoc/pytdx 兜底)
        3. 旧降级链 Tushare Pro → Tushare legacy → eFinance（仅当
           ``DATA_SOURCE_KEEP_LEGACY_FALLBACK=1`` 时启用）

        ``TDX_LOCAL_ONLY=1`` 等价于 ``DATA_SOURCE_KEEP_LEGACY_FALLBACK=0``，
        强制只用 TDX 任一来源。
        """
        code = normalize_code(code)

        # 0a. tqcenter 主路径（客户端实时行情 + 88 字段）
        try:
            tq_quote = _tqcenter.get_realtime_quote(code)
            if tq_quote and tq_quote.get("price") is not None:
                if not tq_quote.get("name"):
                    tq_quote["name"] = self._get_stock_name(code)
                return tq_quote
        except Exception as e:
            safe_stderr_print(f"[DataSource] tqcenter quote failed: {e}")

        # 0b. tdx_local 兜底（vipdoc 快照或 pytdx 公网）
        try:
            tdx_quote = _get_tdx_local().get_realtime_quote(code)
            if tdx_quote and tdx_quote.get("price") is not None:
                if not tdx_quote.get("name"):
                    tdx_quote["name"] = self._get_stock_name(code)
                return tdx_quote
        except Exception as e:
            safe_stderr_print(f"[DataSource] TDX local quote failed: {e}")

        if _tdx_local_only() or not _keep_legacy_fallback():
            return None

        # 1. Tushare Pro
        if self.ts_pro:
            try:
                ts_code = _to_tushare_ts_code(code)
                end_date = datetime.datetime.now().strftime("%Y%m%d")
                start_date = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y%m%d")
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

                turnover_rate = None
                try:
                    for days_back in range(5):
                        check_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime("%Y%m%d")
                        df_basic = self.ts_pro.daily_basic(ts_code=ts_code, start_date=check_date, end_date=check_date)
                        if df_basic is not None and not df_basic.empty:
                            turnover_rate = safe_float(df_basic.iloc[0].get("turnover_rate"))
                            if turnover_rate is not None:
                                break
                except Exception as e:
                    safe_stderr_print(f"[DataSource] Failed to get turnover_rate: {e}")

                if df is not None and not df.empty:
                    df = df.sort_values("trade_date")
                    row = df.iloc[-1]
                    price = safe_float(row.get("close"))
                    pre_close = safe_float(row.get("pre_close"))
                    change = safe_float(row.get("change"))
                    if change is None and price is not None and pre_close is not None:
                        change = price - pre_close
                    vol = safe_float(row.get("vol"))
                    amt = safe_float(row.get("amount"))
                    return {
                        "code": code,
                        "name": self._get_stock_name(code),
                        "price": price,
                        "change": change,
                        "changePercent": safe_float(row.get("pct_chg")),
                        "open": safe_float(row.get("open")),
                        "high": safe_float(row.get("high")),
                        "low": safe_float(row.get("low")),
                        "preClose": pre_close,
                        "volume": safe_int(vol * 100) if vol is not None else None,
                        "amount": amt * 1000 if amt is not None else None,
                        "turnoverRate": turnover_rate,
                        "source": "tushare_pro",
                    }
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare Pro quote failed: {e}")

        # 2. Tushare legacy
        try:
            df = ts.get_realtime_quotes(code)
            if df is not None and not df.empty:
                row = df.iloc[0]
                price = safe_float(row["price"])
                pre_close = safe_float(row["pre_close"])
                change = price - pre_close if price is not None and pre_close is not None else 0
                return {
                    "code": code,
                    "name": row["name"],
                    "price": price,
                    "change": change,
                    "changePercent": (change / pre_close) * 100 if pre_close else 0,
                    "open": safe_float(row["open"]),
                    "high": safe_float(row["high"]),
                    "low": safe_float(row["low"]),
                    "preClose": pre_close,
                    "volume": safe_int(row["volume"]),
                    "amount": safe_float(row["amount"]),
                    "turnoverRate": None,
                    "source": "tushare_legacy",
                }
        except Exception as e:
            safe_stderr_print(f"[DataSource] Tushare legacy quote failed: {e}")

        # 3. eFinance（限制超时）
        if ef is not None:
            try:
                future = _efinance_executor.submit(ef.stock.get_latest_quote, [code])
                df = future.result(timeout=_EFINANCE_TIMEOUT)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    name = row.get('名称') or row.get('股票名称') or ''
                    return {
                        "code": code,
                        "name": name,
                        "price": safe_float(row.get('最新价')),
                        "change": safe_float(row.get('涨跌额')),
                        "changePercent": safe_float(row.get('涨跌幅')),
                        "open": safe_float(row.get('今开')),
                        "high": safe_float(row.get('最高')),
                        "low": safe_float(row.get('最低')),
                        "preClose": safe_float(row.get('昨日收盘')),
                        "volume": safe_int(row.get('成交量')),
                        "amount": safe_float(row.get('成交额')),
                        "source": "efinance"
                    }
            except FuturesTimeoutError:
                safe_stderr_print(f"[DataSource] eFinance quote timed out (>{_EFINANCE_TIMEOUT}s) for {code}")
            except Exception as e:
                safe_stderr_print(f"[DataSource] eFinance quote failed: {e}")

        return None

    # ---- K线数据 ----

    def get_kline(self, code: str, period: str = "daily", limit: int = 100) -> list[dict]:
        """获取K线数据。优先级：

        1. 本地 SQLite 缓存 (kline_1d)
        2. tqcenter (客户端在线，覆盖日线/周线/月线/季/年/分钟)
        3. tdx_local (vipdoc 文件 / pytdx 公网)
        4. 旧降级链 Tushare Pro → legacy → Baostock → eFinance（仅当
           ``DATA_SOURCE_KEEP_LEGACY_FALLBACK=1``）
        """
        code = normalize_code(code)

        # 0. 本地 SQLite 优先（DB-first 策略）
        if period == "daily":
            try:
                from ..storage import get_db
                db = get_db()
                if hasattr(db, "get_klines_sync"):
                    local_rows = db.get_klines_sync(code, limit=limit)
                    if local_rows and len(local_rows) >= min(limit, 10):
                        return local_rows
                elif hasattr(db, "conn"):
                    conn = db.conn
                    cursor = conn.execute(
                        "SELECT time, code, open, high, low, close, volume, amount, turnover, change_pct "
                        "FROM kline_1d WHERE code = ? ORDER BY time DESC LIMIT ?",
                        (code, limit),
                    )
                    rows = cursor.fetchall()
                    if rows and len(rows) >= min(limit, 10):
                        results = []
                        for row in reversed(rows):
                            raw_date = str(row[0] or "")
                            # 截断为纯日期格式（兼容回测引擎）
                            date_str = raw_date[:10] if len(raw_date) >= 10 else raw_date
                            results.append({
                                "date": date_str,
                                "code": row[1],
                                "open": row[2],
                                "high": row[3],
                                "low": row[4],
                                "close": row[5],
                                "volume": row[6],
                                "amount": row[7],
                                "turnover": row[8],
                                "change_pct": row[9],
                                "source": "sqlite_local",
                            })
                        return results
            except Exception as e:
                safe_stderr_print(f"[DataSource] Local DB KLine read failed for {code}: {e}")

        # 1. tqcenter 主路径
        try:
            tq_rows = _tqcenter.get_kline(code, period=period, limit=limit)
            if tq_rows:
                return tq_rows
        except Exception as e:
            safe_stderr_print(f"[DataSource] tqcenter kline failed for {code}: {e}")

        # 2. tdx_local 兜底
        try:
            tdx_rows = _get_tdx_local().get_kline(code, period=period, limit=limit)
            if tdx_rows:
                return tdx_rows
        except Exception as e:
            safe_stderr_print(f"[DataSource] TDX local kline failed for {code}: {e}")

        if _tdx_local_only() or not _keep_legacy_fallback():
            return []

        # 1. Tushare Pro (仅日线)
        if self.ts_pro and period == 'daily':
            try:
                ts_code = _to_tushare_ts_code(code)
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                start_date = (datetime.datetime.now() - datetime.timedelta(days=limit * 2)).strftime('%Y%m%d')

                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    df = df.iloc[::-1].tail(limit)
                    results = []
                    for _, row in df.iterrows():
                        vol = safe_float(row.get("vol"))
                        amt = safe_float(row.get("amount"))
                        results.append({
                            "date": f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:]}",
                            "open": safe_float(row['open']),
                            "close": safe_float(row['close']),
                            "high": safe_float(row['high']),
                            "low": safe_float(row['low']),
                            "volume": safe_float(vol) if vol is not None else None,
                            "amount": amt * 1000 if amt is not None else None,
                            "change_pct": safe_float(row.get('pct_chg')),
                            "source": "tushare_pro"
                        })
                    latest_expected_date = _expected_daily_kline_date()
                    latest_result_date = str(results[-1].get("date") or "")
                    if latest_expected_date and latest_result_date and latest_result_date < latest_expected_date:
                        safe_stderr_print(
                            f"[DataSource] Tushare Pro KLine stale for {code}: "
                            f"latest={latest_result_date}, expected={latest_expected_date}, using stale data"
                        )
                    return results  # 始终返回 Tushare Pro 数据（即使 stale），避免 fallback 卡死
                else:
                    # Tushare Pro 无数据，直接返回空（不再 fallback 到可能卡死的 legacy/baostock）
                    return []
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare Pro KLine failed: {e}")

        # 2. Tushare legacy (仅日线) — 带超时保护
        if period == 'daily':
            try:
                import concurrent.futures
                def _fetch_legacy():
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        return ts.get_hist_data(code)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_fetch_legacy)
                    df = future.result(timeout=8)  # 8 秒超时
                if df is not None and not df.empty:
                    df = df.iloc[::-1].tail(limit)
                    results = []
                    for idx, row in df.iterrows():
                        results.append({
                            "date": str(idx),
                            "open": safe_float(row.get("open")),
                            "close": safe_float(row.get("close")),
                            "high": safe_float(row.get("high")),
                            "low": safe_float(row.get("low")),
                            "volume": safe_int(row.get("volume")),
                            "amount": None,
                            "source": "tushare_legacy",
                        })
                    return results
            except concurrent.futures.TimeoutError:
                safe_stderr_print(f"[DataSource] Tushare legacy KLine timeout for {code}")
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare legacy KLine failed: {e}")

        # 3. Baostock
        if baostock_client is not None:
            try:
                end_date = datetime.datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.datetime.now() - datetime.timedelta(days=limit * 1.5 + 30)).strftime("%Y-%m-%d")
                df_bs = baostock_client.get_history_k_data(code, start_date, end_date)
                if not df_bs.empty:
                    if "date" in df_bs.columns:
                        # Baostock may return rows newest-first; normalize to ascending before truncation.
                        df_bs = df_bs.sort_values("date")
                    results = []
                    for _, row in df_bs.tail(limit).iterrows():
                        results.append({
                            "date": row["date"],
                            "open": safe_float(row["open"]),
                            "close": safe_float(row["close"]),
                            "high": safe_float(row["high"]),
                            "low": safe_float(row["low"]),
                            "volume": safe_int(row["volume"]),
                            "amount": safe_float(row["amount"]),
                            "turnover": safe_float(row.get("turn")),
                            "change_pct": safe_float(row.get("pctChg")),
                            "source": "baostock"
                        })
                    return results
            except Exception as e:
                safe_stderr_print(f"[DataSource] Baostock KLine failed: {e}")

        # 4. eFinance（限制超时，防止内部 5 次 HTTP 重试阻塞过久）
        if ef is not None:
            try:
                future = _efinance_executor.submit(ef.stock.get_quote_history, code)
                df = future.result(timeout=_EFINANCE_TIMEOUT)
                if df is not None and not df.empty:
                    results = []
                    for _, row in df.tail(limit).iterrows():
                        results.append({
                            "date": row["日期"],
                            "open": safe_float(row["开盘"]),
                            "close": safe_float(row["收盘"]),
                            "high": safe_float(row["最高"]),
                            "low": safe_float(row["最低"]),
                            "volume": safe_int(row["成交量"]),
                            "amount": safe_float(row["成交额"]),
                            "source": "efinance"
                        })
                    return results
            except FuturesTimeoutError:
                safe_stderr_print(f"[DataSource] eFinance KLine timed out (>{_EFINANCE_TIMEOUT}s) for {code}")
            except Exception as e:
                safe_stderr_print(f"[DataSource] eFinance KLine failed: {e}")

        return []
