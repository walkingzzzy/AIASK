"""
数据源管理 - 行情与K线方法

包含 get_realtime_quote、get_kline、_get_stock_name 等多源降级逻辑。
数据源优先级: TDX → Tushare Pro → Tushare legacy → eFinance/Baostock
"""

import datetime
import io
import logging
from contextlib import redirect_stdout

from ..utils import normalize_code, safe_float, safe_int, safe_stderr_print

logger = logging.getLogger(__name__)

try:
    import efinance as ef
except ImportError:
    ef = None

import tushare as ts

try:
    from ..baostock_api import baostock_client
except (ImportError, Exception):
    baostock_client = None


class QuotesMixin:
    """行情与K线数据 Mixin"""

    # ---- 股票名称缓存 ----

    def _get_stock_name(self, code: str) -> str:
        """获取股票名称（带缓存），优先 TDX → Tushare stock_basic"""
        if not hasattr(self, '_stock_name_cache'):
            self._stock_name_cache = {}
        code = normalize_code(code)
        if code in self._stock_name_cache:
            return self._stock_name_cache[code]
        # 1. TDX
        if self.is_tdx_available():
            try:
                info = self.get_stock_info_tdxquant(code)
                if info and info.get('name'):
                    self._stock_name_cache[code] = info['name']
                    return info['name']
            except Exception:
                pass
        # 2. Tushare stock_basic（批量缓存）
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
        """获取实时行情，数据源优先级: TDX → Tushare Pro → Tushare legacy → eFinance"""
        code = normalize_code(code)

        # 0. TdxQuant
        if self.is_tdx_available():
            result = self._get_quote_tdxquant(code)
            if result:
                if not result.get('name'):
                    result['name'] = self._get_stock_name(code)
                return result

        # 1. Tushare Pro
        if self.ts_pro:
            try:
                ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
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

        # 3. eFinance
        if ef is not None:
            try:
                df = ef.stock.get_latest_quote([code])
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
            except Exception as e:
                safe_stderr_print(f"[DataSource] eFinance quote failed: {e}")

        return None

    # ---- K线数据 ----

    def get_kline(self, code: str, period: str = "daily", limit: int = 100) -> list[dict]:
        """获取K线数据，数据源优先级: TDX → Tushare Pro → Tushare legacy → Baostock → eFinance"""
        code = normalize_code(code)

        # 0. TdxQuant
        if self.is_tdx_available():
            result = self._get_kline_tdxquant(code, period, limit)
            if result:
                return result

        # 1. Tushare Pro (仅日线)
        if self.ts_pro and period == 'daily':
            try:
                ts_code = f"{code}.SH" if code.startswith(('6', '5')) else f"{code}.SZ"
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
                    return results
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare Pro KLine failed: {e}")

        # 2. Tushare legacy (仅日线)
        if period == 'daily':
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    df = ts.get_hist_data(code)
                legacy_stdout = buf.getvalue().strip()
                if legacy_stdout:
                    safe_stderr_print(f"[DataSource] Tushare legacy stdout: {legacy_stdout}")
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
            except Exception as e:
                safe_stderr_print(f"[DataSource] Tushare legacy KLine failed: {e}")

        # 3. Baostock
        if baostock_client is not None:
            try:
                end_date = datetime.datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.datetime.now() - datetime.timedelta(days=limit * 1.5 + 30)).strftime("%Y-%m-%d")
                df_bs = baostock_client.get_history_k_data(code, start_date, end_date)
                if not df_bs.empty:
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

        # 4. eFinance
        if ef is not None:
            try:
                df = ef.stock.get_quote_history(code)
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
            except Exception as e:
                safe_stderr_print(f"[DataSource] eFinance KLine failed: {e}")

        return []
