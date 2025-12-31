"""
Tushare数据源适配器
作为AKShare的备用数据源
"""
import os
import logging
from typing import Optional, List
from datetime import datetime

from .base_adapter import (
    BaseDataAdapter,
    StockQuote,
    DailyBar,
    FinancialData,
)

logger = logging.getLogger(__name__)

# 延迟导入tushare，避免未安装时报错
tushare = None


def _get_tushare():
    """延迟加载tushare"""
    global tushare
    if tushare is None:
        try:
            import tushare as ts

            token = os.getenv("TUSHARE_TOKEN", "")
            if token:
                ts.set_token(token)
            tushare = ts.pro_api() if token else None
        except ImportError:
            logger.warning("tushare未安装，请运行: pip install tushare")
            tushare = False
    return tushare if tushare else None


class TushareAdapter(BaseDataAdapter):
    """
    Tushare数据源适配器

    需要设置环境变量 TUSHARE_TOKEN
    获取token: https://tushare.pro/register
    """

    def __init__(self):
        super().__init__(name="tushare", priority=80)  # 优先级低于AKShare
        self._api = None

    @property
    def api(self):
        """获取tushare API实例"""
        if self._api is None:
            self._api = _get_tushare()
        return self._api

    def _normalize_code(self, stock_code: str) -> str:
        """
        标准化股票代码为Tushare格式

        600519 -> 600519.SH
        000001 -> 000001.SZ
        """
        code = stock_code.replace(".SH", "").replace(".SZ", "")
        if code.startswith("6"):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"

    def _extract_code(self, ts_code: str) -> str:
        """从Tushare代码提取纯数字代码"""
        return ts_code.split(".")[0] if "." in ts_code else ts_code

    def get_realtime_quote(self, stock_code: str) -> Optional[StockQuote]:
        """
        获取实时行情

        注意：Tushare实时行情需要较高积分，这里使用日线最新数据模拟
        """
        if not self.api:
            return None

        try:
            ts_code = self._normalize_code(stock_code)
            today = datetime.now().strftime("%Y%m%d")

            # 获取最新日线数据
            df = self.api.daily(ts_code=ts_code, start_date=today, end_date=today)

            if df is None or df.empty:
                # 如果今天没数据，获取最近一天
                df = self.api.daily(ts_code=ts_code, limit=1)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            # 获取股票名称
            stock_info = self.api.stock_basic(ts_code=ts_code, fields="name")
            name = stock_info.iloc[0]["name"] if not stock_info.empty else ""

            return StockQuote(
                code=self._extract_code(ts_code),
                name=name,
                price=float(row["close"]),
                change=float(row["change"]) if "change" in row else 0,
                change_pct=float(row["pct_chg"]) if "pct_chg" in row else 0,
                volume=int(row["vol"] * 100) if "vol" in row else 0,  # 手转股
                amount=float(row["amount"] * 1000) if "amount" in row else 0,  # 千元转元
                high=float(row["high"]),
                low=float(row["low"]),
                open=float(row["open"]),
                pre_close=float(row["pre_close"]) if "pre_close" in row else 0,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

        except Exception as e:
            self._record_error(f"获取实时行情失败: {e}")
            return None

    def get_daily_bars(
        self, stock_code: str, start_date: str, end_date: str
    ) -> Optional[List[DailyBar]]:
        """获取日线数据"""
        if not self.api:
            return None

        try:
            ts_code = self._normalize_code(stock_code)

            df = self.api.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

            if df is None or df.empty:
                return None

            bars = []
            for _, row in df.iterrows():
                bars.append(
                    DailyBar(
                        date=row["trade_date"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["vol"] * 100),  # 手转股
                        amount=float(row["amount"] * 1000),  # 千元转元
                    )
                )

            # 按日期升序排列
            bars.sort(key=lambda x: x.date)
            return bars

        except Exception as e:
            self._record_error(f"获取日线数据失败: {e}")
            return None

    def get_financial_data(self, stock_code: str) -> Optional[FinancialData]:
        """获取财务数据"""
        if not self.api:
            return None

        try:
            ts_code = self._normalize_code(stock_code)

            # 获取最新财务指标
            df = self.api.fina_indicator(ts_code=ts_code, limit=1)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            # 获取每日指标（PE、PB等）
            daily_basic = self.api.daily_basic(ts_code=ts_code, limit=1)
            pe = 0
            pb = 0
            market_cap = 0
            if daily_basic is not None and not daily_basic.empty:
                db_row = daily_basic.iloc[0]
                pe = float(db_row.get("pe", 0) or 0)
                pb = float(db_row.get("pb", 0) or 0)
                market_cap = float(db_row.get("total_mv", 0) or 0) * 10000  # 万元转元

            return FinancialData(
                code=self._extract_code(ts_code),
                pe=pe,
                pb=pb,
                market_cap=market_cap,
                roe=float(row.get("roe", 0) or 0),
                gross_margin=float(row.get("grossprofit_margin", 0) or 0),
                net_margin=float(row.get("netprofit_margin", 0) or 0),
                revenue_growth=float(row.get("or_yoy", 0) or 0),
                profit_growth=float(row.get("netprofit_yoy", 0) or 0),
                debt_ratio=float(row.get("debt_to_assets", 0) or 0),
                report_date=row.get("end_date", ""),
            )

        except Exception as e:
            self._record_error(f"获取财务数据失败: {e}")
            return None

    def get_stock_list(self, market: str = "all") -> Optional[List[dict]]:
        """获取股票列表"""
        if not self.api:
            return None

        try:
            # 获取所有上市股票
            df = self.api.stock_basic(
                exchange="", list_status="L", fields="ts_code,name,industry,market,list_date"
            )

            if df is None or df.empty:
                return None

            stocks = []
            for _, row in df.iterrows():
                ts_code = row["ts_code"]
                # 过滤市场
                if market == "sh" and not ts_code.endswith(".SH"):
                    continue
                if market == "sz" and not ts_code.endswith(".SZ"):
                    continue

                stocks.append(
                    {
                        "code": self._extract_code(ts_code),
                        "name": row["name"],
                        "industry": row.get("industry", ""),
                        "market": "SH" if ts_code.endswith(".SH") else "SZ",
                        "list_date": row.get("list_date", ""),
                    }
                )

            return stocks

        except Exception as e:
            self._record_error(f"获取股票列表失败: {e}")
            return None

    def health_check(self) -> bool:
        """健康检查"""
        if not self.api:
            self._is_available = False
            return False

        try:
            # 尝试获取交易日历
            df = self.api.trade_cal(exchange="SSE", limit=1)
            self._is_available = df is not None and not df.empty
            return self._is_available
        except Exception as e:
            self._record_error(f"健康检查失败: {e}")
            self._is_available = False
            return False
