"""
东方财富数据源适配器
作为备用数据源，通过AKShare的东方财富接口获取数据
"""
from typing import Optional, List
from datetime import datetime
import logging

from .base_adapter import BaseDataAdapter, StockQuote, DailyBar, FinancialData

try:
    import akshare as ak
    import pandas as pd
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None
    pd = None

logger = logging.getLogger(__name__)


class EastMoneyAdapter(BaseDataAdapter):
    """
    东方财富数据源适配器
    
    通过AKShare的东方财富接口获取数据，作为备用数据源
    主要用于：
    - 实时行情
    - 资金流向
    - 龙虎榜数据
    """
    
    def __init__(self):
        super().__init__(name="eastmoney", priority=1)
        
        if not HAS_AKSHARE:
            logger.warning("akshare未安装，东方财富数据源不可用")
            self._is_available = False
    
    def get_realtime_quote(self, stock_code: str) -> Optional[StockQuote]:
        """
        获取实时行情
        
        Args:
            stock_code: 股票代码，如 600519.SH
            
        Returns:
            StockQuote对象或None
        """
        if not HAS_AKSHARE:
            return None
        
        try:
            # 转换代码格式
            code = self._convert_code(stock_code)
            
            # 使用东方财富实时行情接口
            df = ak.stock_zh_a_spot_em()
            
            if df is None or df.empty:
                return None
            
            # 查找对应股票
            row = df[df['代码'] == code]
            if row.empty:
                return None
            
            row = row.iloc[0]
            
            return StockQuote(
                stock_code=stock_code,
                stock_name=str(row.get('名称', '')),
                current_price=float(row.get('最新价', 0) or 0),
                change_percent=float(row.get('涨跌幅', 0) or 0),
                change_amount=float(row.get('涨跌额', 0) or 0),
                open_price=float(row.get('今开', 0) or 0),
                high_price=float(row.get('最高', 0) or 0),
                low_price=float(row.get('最低', 0) or 0),
                prev_close=float(row.get('昨收', 0) or 0),
                volume=int(row.get('成交量', 0) or 0),
                amount=float(row.get('成交额', 0) or 0),
                pe_ratio=float(row.get('市盈率-动态', 0) or 0) if row.get('市盈率-动态') else None,
                pb_ratio=float(row.get('市净率', 0) or 0) if row.get('市净率') else None,
                market_cap=float(row.get('总市值', 0) or 0) if row.get('总市值') else None,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"东方财富获取实时行情失败 {stock_code}: {e}")
            self._last_error = str(e)
            return None
    
    def get_daily_bars(self, stock_code: str, start_date: str, 
                       end_date: str) -> Optional[List[DailyBar]]:
        """
        获取日线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            
        Returns:
            DailyBar列表或None
        """
        if not HAS_AKSHARE:
            return None
        
        try:
            code = self._convert_code(stock_code)
            
            # 使用东方财富历史数据接口
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 前复权
            )
            
            if df is None or df.empty:
                return None
            
            bars = []
            for _, row in df.iterrows():
                bar = DailyBar(
                    date=str(row.get('日期', '')),
                    open=float(row.get('开盘', 0) or 0),
                    high=float(row.get('最高', 0) or 0),
                    low=float(row.get('最低', 0) or 0),
                    close=float(row.get('收盘', 0) or 0),
                    volume=int(row.get('成交量', 0) or 0),
                    amount=float(row.get('成交额', 0) or 0),
                    change_percent=float(row.get('涨跌幅', 0) or 0),
                    turnover=float(row.get('换手率', 0) or 0) if row.get('换手率') else None
                )
                bars.append(bar)
            
            return bars
            
        except Exception as e:
            logger.error(f"东方财富获取日线数据失败 {stock_code}: {e}")
            self._last_error = str(e)
            return None
    
    def get_financial_data(self, stock_code: str) -> Optional[FinancialData]:
        """
        获取财务数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            FinancialData对象或None
        """
        if not HAS_AKSHARE:
            return None
        
        try:
            code = self._convert_code(stock_code)
            
            # 获取财务指标
            df = ak.stock_financial_analysis_indicator(symbol=code)
            
            if df is None or df.empty:
                return None
            
            # 取最新一期数据
            latest = df.iloc[0] if len(df) > 0 else None
            if latest is None:
                return None
            
            return FinancialData(
                stock_code=stock_code,
                report_period=str(latest.get('日期', '')),
                eps=self._safe_float(latest.get('摊薄每股收益(元)')),
                roe=self._safe_float(latest.get('净资产收益率(%)')),
                gross_margin=self._safe_float(latest.get('销售毛利率(%)')),
                net_margin=self._safe_float(latest.get('销售净利率(%)')),
                debt_ratio=self._safe_float(latest.get('资产负债率(%)')),
                current_ratio=self._safe_float(latest.get('流动比率')),
                quick_ratio=self._safe_float(latest.get('速动比率'))
            )
            
        except Exception as e:
            logger.error(f"东方财富获取财务数据失败 {stock_code}: {e}")
            self._last_error = str(e)
            return None
    
    def get_stock_list(self, market: str = 'all') -> Optional['pd.DataFrame']:
        """
        获取股票列表
        
        Args:
            market: 市场类型 'SH'/'SZ'/'all'
            
        Returns:
            股票列表DataFrame或None
        """
        if not HAS_AKSHARE:
            return None
        
        try:
            df = ak.stock_zh_a_spot_em()
            
            if df is None or df.empty:
                return None
            
            # 筛选市场
            if market == 'SH':
                df = df[df['代码'].str.startswith('6')]
            elif market == 'SZ':
                df = df[df['代码'].str.startswith(('0', '3'))]
            
            # 标准化列名
            df = df.rename(columns={
                '代码': 'code',
                '名称': 'name',
                '最新价': 'price',
                '涨跌幅': 'change_pct',
                '总市值': 'market_cap'
            })
            
            return df[['code', 'name', 'price', 'change_pct', 'market_cap']]
            
        except Exception as e:
            logger.error(f"东方财富获取股票列表失败: {e}")
            self._last_error = str(e)
            return None
    
    def get_money_flow(self, stock_code: str) -> Optional[dict]:
        """
        获取资金流向数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            资金流向数据字典
        """
        if not HAS_AKSHARE:
            return None
        
        try:
            code = self._convert_code(stock_code)
            
            # 获取个股资金流向
            df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith('6') else "sz")
            
            if df is None or df.empty:
                return None
            
            latest = df.iloc[-1]
            
            return {
                'date': str(latest.get('日期', '')),
                'main_net_inflow': float(latest.get('主力净流入-净额', 0) or 0),
                'main_net_inflow_pct': float(latest.get('主力净流入-净占比', 0) or 0),
                'super_large_net': float(latest.get('超大单净流入-净额', 0) or 0),
                'large_net': float(latest.get('大单净流入-净额', 0) or 0),
                'medium_net': float(latest.get('中单净流入-净额', 0) or 0),
                'small_net': float(latest.get('小单净流入-净额', 0) or 0)
            }
            
        except Exception as e:
            logger.error(f"东方财富获取资金流向失败 {stock_code}: {e}")
            return None
    
    def _convert_code(self, stock_code: str) -> str:
        """转换股票代码格式"""
        # 移除后缀
        code = stock_code.split('.')[0]
        return code
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == '' or value == '--':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
