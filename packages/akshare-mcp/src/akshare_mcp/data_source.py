"""
数据源管理模块

数据源优先级策略:
1. Tushare Pro (主要数据源) - 使用配置的 TUSHARE_TOKEN 和 TUSHARE_HTTP_URL
2. Tushare Legacy (备用) - 旧版 Tushare 接口
3. Baostock (备用) - 免费历史数据
4. eFinance (最后备用) - 东方财富数据

配置说明:
- TUSHARE_TOKEN: Tushare Pro API Token
- TUSHARE_HTTP_URL: Tushare API 地址 (支持自建/代理服务)
"""

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
from .tushare_whitelist import load_tushare_whitelist

class DataSourceManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataSourceManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.tushare_token = os.getenv("TUSHARE_TOKEN", "").strip()
        self.tushare_http_url = os.getenv("TUSHARE_HTTP_URL", "").strip()
        self.ts_pro = None
        if self.tushare_token:
            try:
                ts.set_token(self.tushare_token)
                self.ts_pro = ts.pro_api(self.tushare_token)
                if self.tushare_http_url:
                    try:
                        self.ts_pro._DataApi__token = self.tushare_token
                        self.ts_pro._DataApi__http_url = self.tushare_http_url.rstrip("/")
                    except Exception:
                        pass
            except Exception as e:
                print(f"[DataSource] Tushare init failed: {e}", file=sys.stderr)
        
        # efinance doesn't need init
        # baostock needs login (handled in baostock_api.py or lazy)

    def get_tushare_pro(self):
        return self.ts_pro

    def get_tushare_http_url(self) -> str:
        return self.tushare_http_url

    def get_tushare_whitelist(self) -> dict:
        return load_tushare_whitelist()

    def get_realtime_quote(self, code: str) -> dict:
        """
        数据源优先级: Tushare Pro (主要) -> Tushare Legacy -> eFinance (备用)
        """
        code = normalize_code(code)

        # 1. 优先使用 Tushare Pro (主要数据源)
        if self.ts_pro:
            try:
                ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
                end_date = datetime.datetime.now().strftime("%Y%m%d")
                start_date = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y%m%d")
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                # 获取换手率数据 - 尝试最近几个交易日
                turnover_rate = None
                try:
                    # 尝试最近5天的数据（包含周末）
                    for days_back in range(5):
                        check_date = (datetime.datetime.now() - datetime.timedelta(days=days_back)).strftime("%Y%m%d")
                        df_basic = self.ts_pro.daily_basic(
                            ts_code=ts_code,
                            start_date=check_date,
                            end_date=check_date
                        )
                        if df_basic is not None and not df_basic.empty:
                            turnover_rate = safe_float(df_basic.iloc[0].get("turnover_rate"))
                            if turnover_rate is not None:
                                break
                except Exception as e:
                    print(f"[DataSource] Failed to get turnover_rate: {e}", file=sys.stderr)
                
                if df is not None and not df.empty:
                    # Tushare returns desc order
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
                        "name": "",
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
                print(f"[DataSource] Tushare Pro quote failed: {e}", file=sys.stderr)

        # 2. 备用: Tushare legacy realtime
        try:
            df = ts.get_realtime_quotes(code)
            if df is not None and not df.empty:
                row = df.iloc[0]
                price = safe_float(row["price"])
                pre_close = safe_float(row["pre_close"])
                change = price - pre_close if price and pre_close else 0
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
                    "turnoverRate": None,  # Tushare legacy不提供换手率
                    "source": "tushare_legacy",
                }
        except Exception as e:
            print(f"[DataSource] Tushare legacy quote failed: {e}", file=sys.stderr)

        # 3. 最后备用: eFinance
        try:
            df = ef.stock.get_realtime_quotes(code)
            if df is not None and not df.empty:
                row = df.iloc[0]
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
        数据源优先级: Tushare Pro (主要) -> Tushare Legacy -> Baostock -> eFinance (备用)
        """
        code = normalize_code(code)
        
        # 1. 优先使用 Tushare Pro (主要数据源)
        if self.ts_pro and period == 'daily':
            try:
                # 转换为 Tushare 格式: 600519.SH
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                start_date = (datetime.datetime.now() - datetime.timedelta(days=limit*2)).strftime('%Y%m%d')
                
                df = self.ts_pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    # Tushare returns desc order usually
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
                            "source": "tushare_pro"
                        })
                    return results
            except Exception as e:
                print(f"[DataSource] Tushare Pro KLine failed: {e}", file=sys.stderr)

        # 2. 备用: Tushare legacy (仅日线)
        if period == 'daily':
            try:
                df = ts.get_hist_data(code)
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
                print(f"[DataSource] Tushare legacy KLine failed: {e}", file=sys.stderr)
        
        # 3. 备用: Baostock
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
                         "source": "baostock"
                     })
                 return results
        except Exception as e:
            print(f"[DataSource] Baostock KLine failed: {e}", file=sys.stderr)

        # 4. 最后备用: eFinance
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
            print(f"[DataSource] eFinance KLine failed: {e}", file=sys.stderr)
            
        return []

data_source = DataSourceManager()

class DataSource:
    """便捷的数据源访问类，使用 Tushare 作为主要数据源"""
    
    def __init__(self):
        self.manager = data_source
    
    async def get_batch_quotes(self, codes: list[str]) -> list[dict]:
        """批量获取实时行情"""
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self.manager.get_realtime_quote, code) for code in codes]
            for future in futures:
                try:
                    quote = future.result(timeout=10)
                    if quote:
                        results.append(quote)
                except Exception as e:
                    print(f"[DataSource] Batch quote failed: {e}", file=sys.stderr)
        return results
    
    def get_quote(self, code: str) -> dict:
        """获取单只股票实时行情"""
        return self.manager.get_realtime_quote(code)
    
    def get_kline(self, code: str, period: str = "daily", limit: int = 100) -> list[dict]:
        """获取K线数据"""
        return self.manager.get_kline(code, period, limit)
