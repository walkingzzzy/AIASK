"""
AKShare数据源适配器
基于现有a_stock_data_tool.py的实现进行封装
"""
from typing import Optional, List
from datetime import datetime, timedelta
import pandas as pd

from .base_adapter import (
    BaseDataAdapter, StockQuote, DailyBar, FinancialData
)

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False


class AKShareAdapter(BaseDataAdapter):
    """AKShare数据源适配器"""
    
    def __init__(self):
        super().__init__(name="akshare", priority=10)
        if not AKSHARE_AVAILABLE:
            self._is_available = False
            self._last_error = "akshare库未安装"
    
    def _parse_stock_code(self, stock_code: str) -> tuple:
        """
        解析股票代码
        
        Args:
            stock_code: 如 600519.SH 或 000001.SZ
            
        Returns:
            (纯代码, 市场标识)
        """
        if '.' in stock_code:
            code, market = stock_code.split('.')
            return code, market.upper()
        return stock_code, None
    
    def get_realtime_quote(self, stock_code: str) -> Optional[StockQuote]:
        """获取实时行情"""
        try:
            code, market = self._parse_stock_code(stock_code)
            
            # 尝试主数据源
            try:
                df = ak.stock_zh_a_spot_em()
            except Exception:
                df = ak.stock_zh_a_spot()
            
            if df is None or df.empty:
                return None
            
            # 查找股票
            stock_data = df[df['代码'] == code]
            if stock_data.empty:
                return None
            
            row = stock_data.iloc[0]
            
            return StockQuote(
                stock_code=stock_code,
                stock_name=str(row.get('名称', '')),
                current_price=self._safe_float(row.get('最新价')),
                change_percent=self._safe_float(row.get('涨跌幅')),
                change_amount=self._safe_float(row.get('涨跌额')),
                open_price=self._safe_float(row.get('今开')),
                high_price=self._safe_float(row.get('最高')),
                low_price=self._safe_float(row.get('最低')),
                prev_close=self._safe_float(row.get('昨收')),
                volume=self._safe_int(row.get('成交量')),
                amount=self._safe_float(row.get('成交额')),
                pe_ratio=self._safe_float(row.get('市盈率-动态')),
                pb_ratio=self._safe_float(row.get('市净率')),
                market_cap=self._safe_float(row.get('总市值')),
                timestamp=datetime.now()
            )
        except Exception as e:
            self._last_error = f"获取实时行情失败: {str(e)}"
            return None
    
    def get_daily_bars(self, stock_code: str, start_date: str,
                       end_date: str) -> Optional[List[DailyBar]]:
        """获取日线数据"""
        try:
            code, market = self._parse_stock_code(stock_code)
            
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            
            if df is None or df.empty:
                return None
            
            bars = []
            for _, row in df.iterrows():
                bars.append(DailyBar(
                    date=str(row['日期']),
                    open=self._safe_float(row['开盘']),
                    high=self._safe_float(row['最高']),
                    low=self._safe_float(row['最低']),
                    close=self._safe_float(row['收盘']),
                    volume=self._safe_int(row['成交量']),
                    amount=self._safe_float(row['成交额']),
                    change_percent=self._safe_float(row.get('涨跌幅')),
                    turnover=self._safe_float(row.get('换手率'))
                ))
            
            return bars
        except Exception as e:
            self._last_error = f"获取日线数据失败: {str(e)}"
            return None
    
    def get_financial_data(self, stock_code: str) -> Optional[FinancialData]:
        """获取财务数据"""
        try:
            code, market = self._parse_stock_code(stock_code)
            
            df = ak.stock_financial_analysis_indicator(symbol=code)
            
            if df is None or df.empty:
                return None
            
            latest = df.iloc[-1]
            
            return FinancialData(
                stock_code=stock_code,
                report_period=str(latest.get('报告期', '')),
                eps=self._safe_float(latest.get('每股收益')),
                roe=self._safe_float(latest.get('净资产收益率')),
                gross_margin=self._safe_float(latest.get('销售毛利率')),
                debt_ratio=self._safe_float(latest.get('资产负债率')),
                current_ratio=self._safe_float(latest.get('流动比率')),
                quick_ratio=self._safe_float(latest.get('速动比率')),
                revenue_growth=self._safe_float(latest.get('营业收入同比增长率')),
                profit_growth=self._safe_float(latest.get('净利润同比增长率'))
            )
        except Exception as e:
            self._last_error = f"获取财务数据失败: {str(e)}"
            return None
    
    def get_stock_list(self, market: str = 'all') -> Optional[pd.DataFrame]:
        """获取股票列表"""
        try:
            df = ak.stock_zh_a_spot_em()
            
            if df is None or df.empty:
                return None
            
            if market.upper() == 'SH':
                df = df[df['代码'].str.startswith('6')]
            elif market.upper() == 'SZ':
                df = df[~df['代码'].str.startswith('6')]
            
            return df[['代码', '名称']].copy()
        except Exception as e:
            self._last_error = f"获取股票列表失败: {str(e)}"
            return None
    
    def get_north_fund_flow(self) -> Optional[pd.DataFrame]:
        """获取北向资金流向"""
        try:
            df = ak.stock_hsgt_north_net_flow_in()
            return df
        except Exception as e:
            self._last_error = f"获取北向资金失败: {str(e)}"
            return None
    
    def get_sector_fund_flow(self) -> Optional[pd.DataFrame]:
        """获取行业资金流向"""
        try:
            df = ak.stock_sector_fund_flow_rank()
            return df
        except Exception as e:
            self._last_error = f"获取行业资金流向失败: {str(e)}"
            return None
    
    @staticmethod
    def _safe_float(value) -> float:
        """安全转换为float"""
        try:
            if pd.isna(value):
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    @staticmethod
    def _safe_int(value) -> int:
        """安全转换为int"""
        try:
            if pd.isna(value):
                return 0
            return int(value)
        except (ValueError, TypeError):
            return 0
