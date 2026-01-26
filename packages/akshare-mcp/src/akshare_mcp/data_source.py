import os
import sys
import logging
from typing import Optional, Any
import datetime
from concurrent.futures import ThreadPoolExecutor

import akshare as ak
import baostock as bs
import tushare as ts
import efinance as ef
import pandas as pd

from .utils import (
    normalize_code, 
    safe_float, 
    safe_int, 
    ok, 
    fail, 
    format_period
)
from .baostock_api import baostock_client

class DataSourceManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataSourceManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.tushare_token = os.getenv("TUSHARE_TOKEN", "")
        self.ts_pro = None
        if self.tushare_token:
            try:
                ts.set_token(self.tushare_token)
                self.ts_pro = ts.pro_api()
            except Exception as e:
                print(f"[DataSource] Tushare init failed: {e}", file=sys.stderr)
        
        # efinance doesn't need init
        # baostock needs login (handled in baostock_api.py or lazy)

    def get_realtime_quote(self, code: str) -> dict:
        """
        Tier 1: Tushare (if available) -> Tier 2: AkShare -> Tier 3: eFinance -> Tier 4: Sina/Tencent (handled in TS or via simple request)
        """
        code = normalize_code(code)
        
        # 1. Try Tushare (Realtime is limited in free tier, but let's assume Pro)
        # Actually Tushare 'get_realtime_quotes' is old interface, might not need token.
        # ts.get_realtime_quotes() returns DataFrame
        try:
            # Tushare old interface for realtime (free)
            df = ts.get_realtime_quotes(code)
            if df is not None and not df.empty:
                row = df.iloc[0]
                price = safe_float(row['price'])
                pre_close = safe_float(row['pre_close'])
                change = price - pre_close if price and pre_close else 0
                return {
                    "code": code,
                    "name": row['name'],
                    "price": price,
                    "change": change,
                    "changePercent": (change/pre_close)*100 if pre_close else 0,
                    "open": safe_float(row['open']),
                    "high": safe_float(row['high']),
                    "low": safe_float(row['low']),
                    "preClose": pre_close,
                    "volume": safe_int(row['volume']),
                    "amount": safe_float(row['amount']),
                    "source": "tushare_legacy"
                }
        except Exception as e:
            print(f"[DataSource] Tushare quote failed: {e}", file=sys.stderr)

        # 2. Try AkShare (Eastmoney) - Existing logic moved here or called from here
        # For now, we reuse the robust logic in market.py, but here we can try a direct simple call
        try:
            df = ak.stock_zh_a_spot_em()
            # This is heavy if called every time. AkShare market.py handles caching.
            # So for realtime, maybe we stick to market.py's implementation being the caller,
            # OR we implement specific lightweight calls here.
            # Let's use efinances as it's fast.
            pass
        except Exception:
            pass

        # 3. Try eFinance
        try:
            # efinance.stock.get_quote_history is kline
            # efinance.stock.get_realtime_quotes() returns all?
            # get_quote_snapshot usually for single?
            # ef.stock.get_latest_quote(code) ?
            # ef.stock.get_realtime_quotes(code)
            df = ef.stock.get_realtime_quotes(code)
            if df is not None and not df.empty:
                row = df.iloc[0]
                # Columns: 代码, 名称, 涨跌幅, 最新价, 最高, 最低, 今开, 涨跌额, 换手率, 量比, 动态市盈率, 成交量, 成交额, 昨日收盘, 总市值, 流通市值, 行情时间 ...
                return {
                    "code": code,
                    "name": row['名称'],
                    "price": safe_float(row['最新价']),
                    "change": safe_float(row['涨跌额']),
                    "changePercent": safe_float(row['涨跌幅']),
                    "open": safe_float(row['今开']),
                    "high": safe_float(row['最高']),
                    "low": safe_float(row['最低']),
                    "preClose": safe_float(row['昨日收盘']),
                    "volume": safe_int(row['成交量']),
                    "amount": safe_float(row['成交额']),
                    "source": "efinance"
                }
        except Exception as e:
            print(f"[DataSource] eFinance quote failed: {e}", file=sys.stderr)

        return None

    def get_kline(self, code: str, period: str="daily", limit: int=100) -> list[dict]:
        """
        Tier 1: AkShare (Eastmoney) -> Tier 2: Tushare Pro -> Tier 3: Baostock -> Tier 4: eFinance
        """
        code = normalize_code(code)
        
        # 1. AkShare (Assuming it's called primarily by legacy tools, but we can wrap it)
        # ... logic similar to tools/market.py ...
        
        # 2. Tushare Pro (if token)
        if self.ts_pro and period == 'daily':
            try:
                # Need to convert code to Tushare format: 600519.SH
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                start_date = (datetime.datetime.now() - datetime.timedelta(days=limit*2)).strftime('%Y%m%d')
                
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    # Tushare returns desc order usually
                    df = df.iloc[::-1].tail(limit)
                    results = []
                    for _, row in df.iterrows():
                        results.append({
                            "date": f"{row['trade_date'][:4]}-{row['trade_date'][4:6]}-{row['trade_date'][6:]}",
                            "open": safe_float(row['open']),
                            "close": safe_float(row['close']),
                            "high": safe_float(row['high']),
                            "low": safe_float(row['low']),
                            "volume": safe_float(row['vol']), # TS vol is hand?
                            "amount": safe_float(row['amount']) * 1000, # TS amount is千
                            "source": "tushare_pro"
                        })
                    return results
            except Exception as e:
                print(f"[DataSource] Tushare KLine failed: {e}", file=sys.stderr)
        
        # 3. Baostock
        try:
             # Using existing wrapper
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
                         "source": "baostock"
                     })
                 return results
        except Exception as e:
            print(f"[DataSource] Baostock KLine failed: {e}", file=sys.stderr)

        # 4. eFinance
        # ef.stock.get_quote_history(code) returns all history
        try:
            df = ef.stock.get_quote_history(code)
            if df is not None and not df.empty:
                 # Columns: 股票代码, 股票名称, 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
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
            print(f"[DataSource] eFinance KLine failed: {e}", file=sys.stderr)
            
        return []

data_source = DataSourceManager()
