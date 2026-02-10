"""
数据源管理模块

全局策略：数据源优先级为 TDX → Tushare → akshare，失败后按序降级。

本模块内优先级（行情/K线等）:
1. TDX (TdxQuant) - 优先，需配置 TDX_ENABLED 与 TDX_PLUGIN_PATH
2. Tushare (Pro / Legacy) - TUSHARE_TOKEN + TUSHARE_HTTP_URL
3. akshare - 东方财富/新浪等（最后降级）

其他工具在调用本模块或自有多源时，统一约定：先 TDX，再 Tushare，再 akshare。

配置说明:
- TDX_ENABLED: 是否启用 TDX（true/false）；若已配置 TDX_PLUGIN_PATH 则建议为 true
- TDX_PLUGIN_PATH: TdxQuant 插件目录（必配以加载 TDX）
- TUSHARE_TOKEN: Tushare Pro API Token（降级源）
- TUSHARE_HTTP_URL: Tushare API 地址（可选，支持自建/代理）
"""

import os
import sys
import logging
import threading
from typing import Optional, Any
import datetime
from concurrent.futures import ThreadPoolExecutor

try:
    import akshare as ak
except ImportError:
    ak = None
try:
    import baostock as bs
except ImportError:
    bs = None
import tushare as ts
try:
    import efinance as ef
except ImportError:
    ef = None
import pandas as pd

from .utils import (
    normalize_code, 
    safe_float, 
    safe_int, 
    ok, 
    fail, 
    format_period
)
try:
    from .baostock_api import baostock_client
except (ImportError, Exception):
    baostock_client = None
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

        # TdxQuant 初始化（优先使用 TDX：若已配置插件路径则默认启用）
        self.tdx_plugin_path = os.getenv("TDX_PLUGIN_PATH", "").strip()
        _tdx_env = os.getenv("TDX_ENABLED", "").strip().lower()
        if _tdx_env in ("false", "0", "no"):
            self.tdx_enabled = False
        elif _tdx_env in ("true", "1", "yes"):
            self.tdx_enabled = True
        else:
            # 未显式设置时：配置了 TDX_PLUGIN_PATH 则默认启用 TDX
            self.tdx_enabled = bool(self.tdx_plugin_path)
        self.tdx_timeout = float(os.getenv("TDX_TIMEOUT", "5"))
        self.tq = None
        self._tdx_initialized = False
        self._tdx_init_failed = False  # 缓存初始化失败状态，避免重复尝试
        self._tdx_lock = threading.Lock()  # TDX 非线程安全，所有调用需串行化

        if self.tdx_enabled and self.tdx_plugin_path:
            self._init_tdxquant()

    def _init_tdxquant(self):
        """初始化 TdxQuant 模块"""
        try:
            if self.tdx_plugin_path not in sys.path:
                sys.path.insert(0, self.tdx_plugin_path)

            from tqcenter import tq
            self.tq = tq
            print("[DataSource] TdxQuant module loaded", file=sys.stderr)
        except UnicodeDecodeError as e:
            print(f"[DataSource] TdxQuant init failed (encoding error, check plugin files are UTF-8): {e}", file=sys.stderr)
            self.tq = None
        except Exception as e:
            print(f"[DataSource] TdxQuant init failed: {e}", file=sys.stderr)
            self.tq = None

    def _ensure_tdx_initialized(self) -> bool:
        """确保 TdxQuant 已初始化（懒加载），失败后间隔 60 秒可重试，支持内部重试"""
        if self.tq is None:
            return False
        if self._tdx_init_failed:
            # 允许 60 秒后重试（TDX 环境可能在 MCP 运行期间启动）
            import time
            if not hasattr(self, '_tdx_fail_time') or (time.time() - self._tdx_fail_time) < 60:
                return False
            # 超过 60 秒，重置失败标记，允许重试
            self._tdx_init_failed = False
        if not self._tdx_initialized:
            import os
            import time
            init_path = __file__
            if self.tdx_plugin_path and os.path.isdir(self.tdx_plugin_path):
                init_path = os.path.join(self.tdx_plugin_path, "mcp_strategy.py")

            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    self.tq.initialize(init_path)
                    self._tdx_initialized = True
                    if attempt > 1:
                        print(f"[DataSource] TdxQuant initialized (attempt {attempt})", file=sys.stderr)
                    else:
                        print("[DataSource] TdxQuant initialized", file=sys.stderr)
                    return True
                except Exception as e:
                    if attempt < max_retries:
                        wait = 0.5 * attempt
                        print(f"[DataSource] TdxQuant init attempt {attempt} failed: {e}, retrying in {wait}s...", file=sys.stderr)
                        time.sleep(wait)
                    else:
                        self._tdx_init_failed = True
                        self._tdx_fail_time = time.time()
                        print(f"[DataSource] TdxQuant initialize failed after {max_retries} attempts (will retry after 60s): {e}", file=sys.stderr)
                        return False
        return True

    def is_tdx_available(self) -> bool:
        """检查 TdxQuant 是否可用"""
        return self.tq is not None and self.tdx_enabled

    def get_tdxquant(self):
        """获取 TdxQuant 实例"""
        if self._ensure_tdx_initialized():
            return self.tq
        return None

    def get_tushare_pro(self):
        return self.ts_pro

    def get_tushare_http_url(self) -> str:
        return self.tushare_http_url

    def get_tushare_whitelist(self) -> dict:
        return load_tushare_whitelist()

    def _convert_to_tdx_code(self, code: str) -> str:
        """转换股票代码为 TdxQuant 格式: 600519 → 600519.SH, 510050 → 510050.SH"""
        code = normalize_code(code)
        # 6xx = 沪市主板, 5xx = 沪市ETF/基金
        if code.startswith(("6", "5")):
            return f"{code}.SH"
        elif code.startswith(("0", "3", "1")):
            # 0xx/3xx = 深市股票, 1xx = 深市ETF/可转债
            return f"{code}.SZ"
        else:
            return f"{code}.BJ"

    def _get_quote_tdxquant(self, code: str) -> Optional[dict]:
        """从 TdxQuant 获取实时行情（线程安全）"""
        tq = self.get_tdxquant()
        if tq is None:
            return None

        with self._tdx_lock:
            try:
                tdx_code = self._convert_to_tdx_code(code)
                snapshot = tq.get_market_snapshot(stock_code=tdx_code)

                if not snapshot or snapshot.get("ErrorId") != "0":
                    return None

                # 解析返回数据（基于实际API文档验证的字段名）
                price = safe_float(snapshot.get("Now", 0))
                pre_close = safe_float(snapshot.get("LastClose", 0))
                change = price - pre_close if price and pre_close else None
                change_pct = (change / pre_close * 100) if change and pre_close else None

                # 五档盘口数据（列表形式）
                buyp = snapshot.get("Buyp", [])
                buyv = snapshot.get("Buyv", [])
                sellp = snapshot.get("Sellp", [])
                sellv = snapshot.get("Sellv", [])

                return {
                    "code": code,
                    "name": "",  # snapshot 不返回股票名称
                    "price": price,
                    "change": change,
                    "changePercent": change_pct,
                    "open": safe_float(snapshot.get("Open", 0)),
                    "high": safe_float(snapshot.get("High", 0)) or safe_float(snapshot.get("Max", 0)),
                    "low": safe_float(snapshot.get("Low", 0)) or safe_float(snapshot.get("Min", 0)),
                    "preClose": pre_close,
                    "volume": safe_int(snapshot.get("Volume", 0)),
                    "amount": safe_float(snapshot.get("Amount", 0)),
                    "turnoverRate": None,
                    # 五档盘口
                    "bid1": safe_float(buyp[0]) if buyp else None,
                    "bid1Vol": safe_int(buyv[0]) if buyv else None,
                    "ask1": safe_float(sellp[0]) if sellp else None,
                    "ask1Vol": safe_int(sellv[0]) if sellv else None,
                    "bids": [{"price": safe_float(buyp[i]), "volume": safe_int(buyv[i])} for i in range(min(len(buyp), len(buyv), 5))],
                    "asks": [{"price": safe_float(sellp[i]), "volume": safe_int(sellv[i])} for i in range(min(len(sellp), len(sellv), 5))],
                    "source": "tdxquant",
                }
            except Exception as e:
                print(f"[DataSource] TdxQuant quote failed: {e}", file=sys.stderr)
                return None

    def _get_kline_tdxquant(self, code: str, period: str, limit: int) -> list[dict]:
        """从 TdxQuant 获取K线数据（线程安全：TDX 共享对象不支持并发）"""
        tq = self.get_tdxquant()
        if tq is None:
            return []

        with self._tdx_lock:
            try:
                # 周期映射
                period_map = {
                    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                    "60m": "1h", "1h": "1h", "daily": "1d", "weekly": "1w",
                    "1d": "1d", "1w": "1w", "1M": "1M", "monthly": "1M"
                }
                tdx_period = period_map.get(period, "1d")
                tdx_code = self._convert_to_tdx_code(code)

                data = tq.get_market_data(
                    stock_list=[tdx_code],
                    period=tdx_period,
                    count=limit,
                    dividend_type='none',
                    fill_data=True
                )

                if not data or "Close" not in data:
                    return []

                close_df = data.get("Close")
                if close_df is None or close_df.empty:
                    return []

                results = []
                for idx in close_df.index:
                    results.append({
                        "date": str(idx)[:10],
                        "open": safe_float(data["Open"].loc[idx, tdx_code]) if "Open" in data else None,
                        "close": safe_float(data["Close"].loc[idx, tdx_code]) if "Close" in data else None,
                        "high": safe_float(data["High"].loc[idx, tdx_code]) if "High" in data else None,
                        "low": safe_float(data["Low"].loc[idx, tdx_code]) if "Low" in data else None,
                        "volume": safe_int(data["Volume"].loc[idx, tdx_code]) if "Volume" in data else None,
                        "amount": safe_float(data["Amount"].loc[idx, tdx_code]) if "Amount" in data else None,
                        "source": "tdxquant",
                    })
                return results
            except Exception as e:
                print(f"[DataSource] TdxQuant kline failed: {e}", file=sys.stderr)
                return []

    def get_stock_info_tdxquant(self, code: str, field_list: list = None) -> Optional[dict]:
        """从 TdxQuant 获取股票基本信息

        Args:
            code: 股票代码 (如 600519)
            field_list: 字段列表，为空则返回全部字段

        Returns:
            dict: 股票基本信息，包含 source='tdxquant'
        """
        tq = self.get_tdxquant()
        if tq is None:
            return None

        try:
            tdx_code = self._convert_to_tdx_code(code)
            fields = field_list if field_list else []

            result = tq.get_stock_info(stock_code=tdx_code, field_list=fields)

            if not result or result.get("ErrorId") != "0":
                return None

            return {
                "code": code,
                "name": result.get("Name", ""),
                "industry": result.get("J_hy", ""),
                "listDate": result.get("J_start", ""),
                "totalShares": result.get("J_zgb", ""),
                "floatShares": result.get("ActiveCapital", ""),
                "province": result.get("J_addr", ""),
                "totalAssets": result.get("J_zzc", ""),
                "netAssets": result.get("J_jzc", ""),
                "eps": result.get("J_mgsy", ""),
                "bvps": result.get("J_mgjzc", ""),
                "belongHS300": result.get("BelongHS300", "") == "1",
                "belongHSGT": result.get("BelongHSGT", "") == "1",
                "isIndex": result.get("IsZS", "") == "1",
                "raw": result,
                "source": "tdxquant",
            }
        except Exception as e:
            print(f"[DataSource] TdxQuant get_stock_info failed: {e}", file=sys.stderr)
            return None

    def get_stock_info_priority_tdx(self, code: str) -> Optional[dict]:
        """
        优先从 TDX 获取股票信息，返回与 DB get_stock_info 同形：code, name, industry, pe_ratio, pb_ratio, market_cap, list_date。
        供估值/决策/诊断等工具在 DB 无该股票时回退使用。
        """
        info = self.get_stock_info_tdxquant(code)
        if not info:
            return None
        quote = self.get_realtime_quote(code)
        price = safe_float(quote.get("price")) if quote else None
        eps = safe_float(info.get("eps"))
        bvps = safe_float(info.get("bvps"))
        total_shares = safe_float(info.get("totalShares"))  # 通常为万股
        pe_ratio = (price / eps) if (price and eps and eps > 0) else None
        pb_ratio = (price / bvps) if (price and bvps and bvps > 0) else None
        market_cap = (price * total_shares * 10000) if (price and total_shares) else None
        list_date = info.get("listDate") or ""
        if list_date and len(list_date) >= 8:
            list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
        return {
            "code": code,
            "name": info.get("name") or "",
            "industry": info.get("industry") or "",
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "market_cap": market_cap,
            "list_date": list_date or None,
        }

    def get_divid_factors_tdxquant(self, code: str, start_time: str = "", end_time: str = "") -> list:
        """从 TdxQuant 获取除权除息因子数据

        Args:
            code: 股票代码 (如 600519)
            start_time: 起始时间 (YYYYMMDD)
            end_time: 结束时间 (YYYYMMDD)

        Returns:
            list: 除权除息记录列表
        """
        tq = self.get_tdxquant()
        if tq is None:
            return []

        try:
            tdx_code = self._convert_to_tdx_code(code)

            df = tq.get_divid_factors(
                stock_code=tdx_code,
                start_time=start_time,
                end_time=end_time
            )

            if df is None or df.empty:
                return []

            results = []
            for idx, row in df.iterrows():
                results.append({
                    "date": str(idx)[:10] if hasattr(idx, '__str__') else str(idx),
                    "type": safe_int(row.get("Type")),
                    "bonus": safe_float(row.get("Bonus")),  # 分红金额
                    "allotPrice": safe_float(row.get("AllotPrice")),  # 配股价格
                    "shareBonus": safe_float(row.get("ShareBonus")),  # 送股比例
                    "allotment": safe_float(row.get("Allotment")),  # 配股比例
                    "source": "tdxquant",
                })
            return results
        except Exception as e:
            print(f"[DataSource] TdxQuant get_divid_factors failed: {e}", file=sys.stderr)
            return []

    def get_sector_list_tdxquant(self) -> list:
        """从 TdxQuant 获取A股板块代码列表

        Returns:
            list: 板块代码列表 (如 ['880081.SH', '880082.SH', ...])
        """
        tq = self.get_tdxquant()
        if tq is None:
            return []

        try:
            result = tq.get_sector_list()
            if result is None:
                return []
            return result
        except Exception as e:
            print(f"[DataSource] TdxQuant get_sector_list failed: {e}", file=sys.stderr)
            return []

    def get_stock_list_in_sector_tdxquant(self, block_code: str, block_type: int = 0) -> list:
        """从 TdxQuant 获取板块成分股

        Args:
            block_code: 板块代码或名称 (如 '880081.SH' 或 '钛金属')
            block_type: 板块类型 (0=板块代码/名称, 1=自定义板块简称)

        Returns:
            list: 成分股代码列表 (如 ['600519.SH', '000001.SZ', ...])
        """
        tq = self.get_tdxquant()
        if tq is None:
            return []

        try:
            result = tq.get_stock_list_in_sector(block_code, block_type=block_type)
            if result is None:
                return []
            return result
        except Exception as e:
            print(f"[DataSource] TdxQuant get_stock_list_in_sector failed: {e}", file=sys.stderr)
            return []

    def subscribe_hq_tdxquant(self, stock_list: list, callback=None) -> dict:
        """订阅行情更新 (TdxQuant)

        Args:
            stock_list: 股票代码列表 (如 ['600519', '000001'])，最多100条
            callback: 回调函数，格式为 on_data(datas)

        Returns:
            dict: 订阅结果
        """
        tq = self.get_tdxquant()
        if tq is None:
            return {"success": False, "message": "TdxQuant 不可用"}

        try:
            # 转换代码格式
            tdx_codes = [self._convert_to_tdx_code(code) for code in stock_list[:100]]

            result = tq.subscribe_hq(stock_list=tdx_codes, callback=callback)

            if result and result.get("ErrorId") == "0":
                return {
                    "success": True,
                    "message": result.get("Error", "订阅成功"),
                    "run_id": result.get("run_id"),
                    "source": "tdxquant",
                }
            else:
                return {
                    "success": False,
                    "message": result.get("Error", "订阅失败") if result else "订阅失败",
                }
        except Exception as e:
            print(f"[DataSource] TdxQuant subscribe_hq failed: {e}", file=sys.stderr)
            return {"success": False, "message": str(e)}

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

    def get_realtime_quote(self, code: str) -> dict:
        """
        数据源优先级: TDX → Tushare → akshare
        """
        code = normalize_code(code)

        # 0. 优先使用 TdxQuant (真正实时数据)
        if self.is_tdx_available():
            result = self._get_quote_tdxquant(code)
            if result:
                # TDX snapshot 不返回 name，尝试补充
                if not result.get('name'):
                    result['name'] = self._get_stock_name(code)
                return result

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

        # 3. 最后备用: eFinance（单只行情用 get_latest_quote(stock_codes)，参数为 str 或 List[str]；get_realtime_quotes(fs) 为市场类型如'沪A'）
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
                print(f"[DataSource] eFinance quote failed: {e}", file=sys.stderr)

        return None

    def get_kline(self, code: str, period: str="daily", limit: int=100) -> list[dict]:
        """
        数据源优先级: TDX → Tushare → akshare
        """
        code = normalize_code(code)

        # 0. 优先使用 TdxQuant (支持分钟级K线)
        if self.is_tdx_available():
            result = self._get_kline_tdxquant(code, period, limit)
            if result:
                return result

        # 1. 优先使用 Tushare Pro (主要数据源)
        if self.ts_pro and period == 'daily':
            try:
                # 转换为 Tushare 格式: 600519.SH, 510050.SH
                ts_code = f"{code}.SH" if code.startswith(('6', '5')) else f"{code}.SZ"
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
                            "source": "baostock"
                        })
                    return results
            except Exception as e:
                print(f"[DataSource] Baostock KLine failed: {e}", file=sys.stderr)

        # 4. 最后备用: eFinance
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
                print(f"[DataSource] eFinance KLine failed: {e}", file=sys.stderr)
            
        return []

    # ============== Phase 3: 基础数据补充 ==============

    def get_trading_dates(
        self,
        market: str = "SH",
        start_time: str = "",
        end_time: str = "",
        count: int = -1
    ) -> dict:
        """
        获取交易日历

        Args:
            market: 市场代码 (暂固定为SH)
            start_time: 起始日期 (格式: YYYYMMDD)
            end_time: 结束日期 (格式: YYYYMMDD)
            count: 返回最近的count个交易日，-1表示全部

        Returns:
            dict: {"success": bool, "data": list, "source": str, "message": str}

        注意: TDX 需要先在客户端下载上证指数(999999)的盘后数据
        """
        # 1. 优先使用 TDX
        if self.is_tdx_available():
            try:
                tq = self.get_tdxquant()
                if tq:
                    result = tq.get_trading_dates(
                        market=market,
                        start_time=start_time,
                        end_time=end_time,
                        count=count
                    )
                    # TDX 返回 List[str]
                    if isinstance(result, list):
                        return {
                            "success": True,
                            "data": result,
                            "source": "tdx",
                            "message": f"获取到 {len(result)} 个交易日"
                        }
            except Exception as e:
                print(f"[DataSource] TDX get_trading_dates failed: {e}", file=sys.stderr)

        # 2. 降级到 Tushare Pro
        if self.ts_pro:
            try:
                # 转换日期格式
                start_date = start_time if start_time else None
                end_date = end_time if end_time else None

                df = self.ts_pro.trade_cal(
                    exchange='SSE',
                    start_date=start_date,
                    end_date=end_date,
                    is_open='1'
                )
                if df is not None and not df.empty:
                    dates = df['cal_date'].tolist()
                    if count > 0:
                        dates = dates[-count:]
                    return {
                        "success": True,
                        "data": dates,
                        "source": "tushare_pro",
                        "message": f"获取到 {len(dates)} 个交易日"
                    }
            except Exception as e:
                print(f"[DataSource] Tushare Pro trade_cal failed: {e}", file=sys.stderr)

        # 3. 降级到 AKShare
        if ak is not None:
            try:
                df = ak.tool_trade_date_hist_sina()
                if df is not None and not df.empty:
                    # 转换为 YYYYMMDD 格式
                    dates = [d.strftime('%Y%m%d') for d in df['trade_date'].tolist()]

                    # 过滤日期范围
                    if start_time:
                        dates = [d for d in dates if d >= start_time]
                    if end_time:
                        dates = [d for d in dates if d <= end_time]
                    if count > 0:
                        dates = dates[-count:]

                    return {
                        "success": True,
                        "data": dates,
                        "source": "akshare",
                        "message": f"获取到 {len(dates)} 个交易日"
                    }
            except Exception as e:
                print(f"[DataSource] AKShare trade_date failed: {e}", file=sys.stderr)

        return {"success": False, "data": [], "source": "none", "message": "所有数据源均失败"}

    def get_ipo_info(
        self,
        ipo_type: int = 0,
        ipo_date: int = 1
    ) -> dict:
        """
        获取新股/新债申购信息

        Args:
            ipo_type: 申购类型
                - 0: 新股申购信息
                - 1: 新发债信息
                - 2: 新股和新发债信息
            ipo_date: 日期范围
                - 0: 只获取今天信息
                - 1: 获取今天及以后信息

        Returns:
            dict: {"success": bool, "data": list, "source": str, "message": str}
        """
        # 1. 优先使用 TDX
        if self.is_tdx_available():
            try:
                tq = self.get_tdxquant()
                if tq:
                    result = tq.get_ipo_info(ipo_type=ipo_type, ipo_date=ipo_date)
                    if isinstance(result, list):
                        return {
                            "success": True,
                            "data": result,
                            "source": "tdx",
                            "message": f"获取到 {len(result)} 条申购信息"
                        }
            except Exception as e:
                print(f"[DataSource] TDX get_ipo_info failed: {e}", file=sys.stderr)

        # 2. 降级到 Tushare Pro (新股)
        if self.ts_pro and ipo_type in (0, 2):
            try:
                df = self.ts_pro.new_share(start_date='', end_date='')
                if df is not None and not df.empty:
                    today = datetime.datetime.now().strftime('%Y%m%d')
                    if ipo_date == 0:
                        df = df[df['ipo_date'] == today]
                    else:
                        # 包含未来 + 最近90天的IPO（避免周末/节假日/数据延迟返回空）
                        past_90 = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime('%Y%m%d')
                        df = df[df['ipo_date'] >= past_90]

                    data = df.to_dict('records')
                    return {
                        "success": True,
                        "data": data,
                        "source": "tushare_pro",
                        "message": f"获取到 {len(data)} 条新股申购信息"
                    }
            except Exception as e:
                print(f"[DataSource] Tushare Pro new_share failed: {e}", file=sys.stderr)

        # 3. 降级到 AKShare
        try:
            results = []

            # 新股申购
            if ipo_type in (0, 2):
                try:
                    df = ak.stock_xgsglb_em()
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            results.append({
                                "code": str(row.get("股票代码", "")),
                                "name": str(row.get("股票简称", "")),
                                "SGDate": str(row.get("申购日期", "")).replace("-", ""),
                                "SGPrice": str(row.get("发行价格", "")),
                                "type": "stock"
                            })
                except Exception:
                    pass

            # 可转债申购
            if ipo_type in (1, 2):
                try:
                    df = ak.bond_cb_jsl()
                    if df is not None and not df.empty:
                        today = datetime.datetime.now().strftime('%Y-%m-%d')
                        for _, row in df.iterrows():
                            sg_date = str(row.get("申购日期", ""))
                            if ipo_date == 0 and sg_date != today:
                                continue
                            if ipo_date == 1 and sg_date < today:
                                continue
                            results.append({
                                "code": str(row.get("转债代码", "")),
                                "name": str(row.get("转债名称", "")),
                                "SGDate": sg_date.replace("-", ""),
                                "SGPrice": "100.00",
                                "type": "bond"
                            })
                except Exception:
                    pass

            if results:
                return {
                    "success": True,
                    "data": results,
                    "source": "akshare",
                    "message": f"获取到 {len(results)} 条申购信息"
                }
        except Exception as e:
            print(f"[DataSource] AKShare IPO info failed: {e}", file=sys.stderr)

        return {"success": False, "data": [], "source": "none", "message": "所有数据源均失败"}

    def get_cb_info(self, stock_code: str) -> dict:
        """
        获取可转债基础信息

        Args:
            stock_code: 可转债代码 (如 123039.SZ 或 123039)

        Returns:
            dict: {"success": bool, "data": dict, "source": str, "message": str}

        返回字段说明:
            - KZZCode: 可转债代码
            - HSCode: 正股代码
            - ZGPrice: 转股价格
            - ZGDate: 转股日期
            - EndDate: 到期日期
            - RestScope: 剩余规模
        """
        if not stock_code:
            return {"success": False, "data": {}, "source": "none", "message": "股票代码不能为空"}

        # 1. 优先使用 TDX
        if self.is_tdx_available():
            try:
                tq = self.get_tdxquant()
                if tq:
                    # 转换代码格式
                    tdx_code = self._convert_to_tdx_code(stock_code)
                    result = tq.get_cb_info(stock_code=tdx_code)
                    if isinstance(result, dict) and result.get("KZZCode"):
                        return {
                            "success": True,
                            "data": result,
                            "source": "tdx",
                            "message": "获取可转债信息成功"
                        }
            except Exception as e:
                print(f"[DataSource] TDX get_cb_info failed: {e}", file=sys.stderr)

        # 2. 降级到 Tushare Pro
        if self.ts_pro:
            try:
                # 提取纯代码
                code = stock_code.split('.')[0] if '.' in stock_code else stock_code
                df = self.ts_pro.cb_basic(ts_code=f"{code}.SH") if code.startswith('11') else \
                     self.ts_pro.cb_basic(ts_code=f"{code}.SZ")

                if df is not None and not df.empty:
                    row = df.iloc[0]
                    data = {
                        "KZZCode": code,
                        "HSCode": str(row.get("stk_code", "")),
                        "ZGPrice": str(row.get("conv_price", "")),
                        "ZGDate": str(row.get("conv_start_date", "")),
                        "EndDate": str(row.get("maturity_date", "")),
                        "RestScope": str(row.get("issue_size", ""))
                    }
                    return {
                        "success": True,
                        "data": data,
                        "source": "tushare_pro",
                        "message": "获取可转债信息成功"
                    }
            except Exception as e:
                print(f"[DataSource] Tushare Pro cb_basic failed: {e}", file=sys.stderr)

        # 3. 降级到 AKShare
        try:
            df = ak.bond_cb_jsl()
            if df is not None and not df.empty:
                code = stock_code.split('.')[0] if '.' in stock_code else stock_code
                row = df[df['转债代码'] == code]
                if not row.empty:
                    row = row.iloc[0]
                    data = {
                        "KZZCode": code,
                        "HSCode": str(row.get("正股代码", "")),
                        "name": str(row.get("转债名称", "")),
                        "ZGPrice": str(row.get("转股价", "")),
                        "RestScope": str(row.get("剩余规模", ""))
                    }
                    return {
                        "success": True,
                        "data": data,
                        "source": "akshare",
                        "message": "获取可转债信息成功"
                    }
        except Exception as e:
            print(f"[DataSource] AKShare cb_info failed: {e}", file=sys.stderr)

        return {"success": False, "data": {}, "source": "none", "message": "所有数据源均失败"}

    def get_gb_info(
        self,
        stock_code: str,
        date_list: list = None,
        count: int = 1
    ) -> dict:
        """
        获取股本数据

        Args:
            stock_code: 股票代码 (如 600519 或 600519.SH)
            date_list: 日期数组 (格式: ['YYYYMMDD', ...])，须从小到大排序
            count: 日期有效个数

        Returns:
            dict: {"success": bool, "data": list, "source": str, "message": str}

        返回字段说明:
            - Date: 日期
            - ltgb: 流通股本
            - zgb: 总股本
        """
        if not stock_code:
            return {"success": False, "data": [], "source": "none", "message": "股票代码不能为空"}

        date_list = date_list or []

        # 1. 优先使用 TDX
        if self.is_tdx_available() and date_list:
            try:
                tq = self.get_tdxquant()
                if tq:
                    tdx_code = self._convert_to_tdx_code(stock_code)
                    result = tq.get_gb_info(
                        stock_code=tdx_code,
                        date_list=date_list,
                        count=count
                    )
                    if isinstance(result, list):
                        return {
                            "success": True,
                            "data": result,
                            "source": "tdx",
                            "message": f"获取到 {len(result)} 条股本数据"
                        }
            except Exception as e:
                print(f"[DataSource] TDX get_gb_info failed: {e}", file=sys.stderr)

        # 2. 降级到 Tushare Pro
        if self.ts_pro:
            try:
                code = normalize_code(stock_code)
                # 转换为 Tushare 格式
                if code.startswith('6'):
                    ts_code = f"{code}.SH"
                else:
                    ts_code = f"{code}.SZ"

                df = self.ts_pro.daily_basic(ts_code=ts_code, fields='ts_code,trade_date,total_share,float_share')
                if df is not None and not df.empty:
                    results = []
                    for _, row in df.head(count).iterrows():
                        results.append({
                            "Date": int(row['trade_date']),
                            "ltgb": float(row['float_share']) * 10000 if row['float_share'] else 0,  # 万股转股
                            "zgb": float(row['total_share']) * 10000 if row['total_share'] else 0
                        })
                    return {
                        "success": True,
                        "data": results,
                        "source": "tushare_pro",
                        "message": f"获取到 {len(results)} 条股本数据"
                    }
            except Exception as e:
                print(f"[DataSource] Tushare Pro daily_basic failed: {e}", file=sys.stderr)

        # 3. 降级到 AKShare
        try:
            code = normalize_code(stock_code)
            df = ak.stock_individual_info_em(symbol=code)
            if df is not None and not df.empty:
                # 从个股信息中提取股本数据
                info_dict = dict(zip(df['item'], df['value']))

                today = datetime.datetime.now().strftime('%Y%m%d')
                data = [{
                    "Date": int(today),
                    "ltgb": safe_float(info_dict.get("流通股", 0)),
                    "zgb": safe_float(info_dict.get("总股本", 0))
                }]
                return {
                    "success": True,
                    "data": data,
                    "source": "akshare",
                    "message": "获取到 1 条股本数据"
                }
        except Exception as e:
            print(f"[DataSource] AKShare stock_info failed: {e}", file=sys.stderr)

        return {"success": False, "data": [], "source": "none", "message": "所有数据源均失败"}

data_source = DataSourceManager()

class DataSource:
    """便捷的数据源访问类，优先级 TDX → Tushare → akshare"""
    
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
