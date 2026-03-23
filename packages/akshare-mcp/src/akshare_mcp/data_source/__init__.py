"""
数据源管理模块

全局策略：数据源优先级为 Tushare → AkShare/公开数据源，失败后按序降级。

向后兼容：DataSourceManager 类通过 Mixin 组合所有子模块功能。
所有外部 import（如 from ..data_source import data_source）保持不变。
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor

import tushare as ts

from ..env_loader import load_mcp_env
from ..tushare_whitelist import load_tushare_whitelist
from ..utils import safe_stderr_print
from .quotes import QuotesMixin
from .market_data import MarketDataMixin

logger = logging.getLogger(__name__)


class DataSourceManager(QuotesMixin, MarketDataMixin):
    """
    数据源管理器 — 单例模式

    通过 Mixin 组合:
    - QuotesMixin: 多源实时行情、K线（Tushare → eFinance/Baostock）
    - MarketDataMixin: 交易日历、IPO、可转债、股本
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataSourceManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        # Tushare 初始化采用懒加载，确保脚本入口未显式加载 .env 时也可用。
        self.tushare_token = ""
        self.tushare_http_url = ""
        self.ts_pro = None
        self._ensure_tushare_ready(force_reload_env=True)

    def _ensure_tushare_ready(self, *, force_reload_env: bool = False):
        if force_reload_env or not str(self.tushare_token or "").strip():
            try:
                load_mcp_env(override=False, only_prefixes=("TUSHARE_",))
            except Exception:
                pass
            self.tushare_token = os.getenv("TUSHARE_TOKEN", "").strip()
            self.tushare_http_url = os.getenv("TUSHARE_HTTP_URL", "").strip()
        if self.ts_pro is not None or not self.tushare_token:
            return self.ts_pro
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
            safe_stderr_print(f"[DataSource] Tushare init failed: {e}")
            self.ts_pro = None
        return self.ts_pro

    # ---- Tushare 辅助方法 ----

    def get_tushare_pro(self):
        """获取 Tushare Pro API 实例"""
        return self._ensure_tushare_ready(force_reload_env=not bool(self.ts_pro))

    def get_tushare_http_url(self) -> str:
        """获取 Tushare HTTP URL"""
        if not self.tushare_http_url:
            self._ensure_tushare_ready(force_reload_env=True)
        return self.tushare_http_url

    def get_tushare_whitelist(self) -> set:
        """获取 Tushare 白名单"""
        return load_tushare_whitelist()


# 全局单例
data_source = DataSourceManager()


class DataSource:
    """便捷的数据源访问类，优先级 Tushare → AkShare/公开数据源"""

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
                    safe_stderr_print(f"[DataSource] Batch quote failed: {e}")
        return results

    def get_quote(self, code: str) -> dict:
        """获取单只股票实时行情"""
        return self.manager.get_realtime_quote(code)

    def get_kline(self, code: str, period: str = "daily", limit: int = 100) -> list[dict]:
        """获取K线数据"""
        return self.manager.get_kline(code, period, limit)


__all__ = [
    'DataSourceManager',
    'data_source',
    'DataSource',
]
