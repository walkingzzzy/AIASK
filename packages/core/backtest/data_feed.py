"""
回测数据源
将AKShare数据转换为backtrader格式
"""
from typing import Optional, List
from datetime import datetime
import logging

try:
    import backtrader as bt
    import pandas as pd
    HAS_BACKTRADER = True
except ImportError:
    HAS_BACKTRADER = False
    bt = None
    pd = None

try:
    import akshare as ak
except ImportError:
    ak = None

logger = logging.getLogger(__name__)


class AKShareDataFeed:
    """
    AKShare数据源适配器
    将AKShare数据转换为backtrader可用的格式
    """
    
    def __init__(self):
        if not HAS_BACKTRADER:
            logger.warning("backtrader未安装，回测功能不可用")
        if ak is None:
            logger.warning("akshare未安装，数据获取功能不可用")
    
    def get_data_feed(self, stock_code: str,
                      start_date: str,
                      end_date: str) -> Optional['bt.feeds.PandasData']:
        """
        获取backtrader数据源
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            
        Returns:
            backtrader PandasData对象
        """
        if not HAS_BACKTRADER:
            return None
        
        df = self._fetch_data(stock_code, start_date, end_date)
        if df is None or df.empty:
            return None
        
        # 转换为backtrader格式
        data = bt.feeds.PandasData(
            dataname=df,
            datetime=None,  # 使用索引作为日期
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume',
            openinterest=-1
        )
        
        return data
    
    def _fetch_data(self, stock_code: str,
                    start_date: str,
                    end_date: str) -> Optional['pd.DataFrame']:
        """从AKShare获取数据"""
        if ak is None:
            logger.error("akshare未安装，无法获取数据")
            return None
        
        try:
            # 获取日线数据
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                logger.warning(f"未获取到股票 {stock_code} 的数据")
                return None
            
            # 重命名列
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '最高': 'high',
                '最低': 'low',
                '收盘': 'close',
                '成交量': 'volume'
            })
            
            # 设置日期索引
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 只保留需要的列
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            return df
            
        except Exception as e:
            logger.error(f"获取数据失败 {stock_code}: {e}")
            return None
    
    def get_multiple_feeds(self, stock_codes: List[str],
                           start_date: str,
                           end_date: str) -> dict:
        """
        获取多只股票的数据源
        
        Returns:
            {stock_code: data_feed}
        """
        feeds = {}
        for code in stock_codes:
            feed = self.get_data_feed(code, start_date, end_date)
            if feed:
                feeds[code] = feed
        return feeds
