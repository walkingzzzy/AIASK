"""
融资融券分析器
提供两融数据获取、趋势分析、个股两融详情等功能
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
import logging

try:
    import akshare as ak
    import pandas as pd
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None
    pd = None

logger = logging.getLogger(__name__)


class MarginSignal(Enum):
    """融资融券信号"""
    STRONG_BULLISH = "强烈看多"    # 融资大幅增加，融券减少
    BULLISH = "偏多"              # 融资增加
    NEUTRAL = "中性"              # 变化不大
    BEARISH = "偏空"              # 融券增加
    STRONG_BEARISH = "强烈看空"   # 融资大幅减少，融券增加


@dataclass
class MarginData:
    """融资融券数据"""
    date: str
    financing_balance: float      # 融资余额（亿元）
    financing_buy: float          # 融资买入额（亿元）
    financing_repay: float        # 融资偿还额（亿元）
    securities_balance: float     # 融券余额（亿元）
    securities_volume: float      # 融券余量（万股）
    total_balance: float          # 两融余额（亿元）
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StockMarginDetail:
    """个股融资融券详情"""
    stock_code: str
    stock_name: str
    date: str
    financing_balance: float      # 融资余额（亿元）
    financing_balance_ratio: float  # 融资余额占流通市值比例%
    financing_buy: float          # 融资买入额（亿元）
    financing_repay: float        # 融资偿还额（亿元）
    financing_net: float          # 融资净买入（亿元）
    securities_balance: float     # 融券余额（亿元）
    securities_volume: float      # 融券余量（万股）
    securities_sell: float        # 融券卖出量（万股）
    securities_repay: float       # 融券偿还量（万股）
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MarginTrend:
    """融资融券趋势分析"""
    stock_code: str = ""
    stock_name: str = ""
    period_days: int = 20
    
    # 融资趋势
    financing_trend: str = ""           # 上升/下降/震荡
    financing_change: float = 0.0       # 变化金额（亿元）
    financing_change_pct: float = 0.0   # 变化比例%
    financing_avg_daily: float = 0.0    # 日均净买入
    
    # 融券趋势
    securities_trend: str = ""
    securities_change: float = 0.0
    securities_change_pct: float = 0.0
    
    # 综合信号
    signal: str = "中性"
    signal_strength: float = 0.5        # 信号强度 0-1
    analysis: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


class MarginAnalyzer:
    """
    融资融券分析器
    
    功能：
    1. 获取市场整体两融数据
    2. 获取个股两融详情
    3. 分析两融趋势
    4. 生成两融信号
    """
    
    def __init__(self):
        self._cache = {}
    
    def get_market_margin(self, days: int = 30) -> List[MarginData]:
        """
        获取市场整体融资融券数据
        
        Args:
            days: 获取天数
            
        Returns:
            融资融券数据列表
        """
        if not HAS_AKSHARE:
            logger.error("akshare未安装，无法获取两融数据")
            return []
        
        try:
            # 获取沪深两市融资融券汇总
            df = ak.stock_margin_sse()  # 上交所
            
            if df is None or df.empty:
                logger.warning("未获取到市场两融数据")
                return []
            
            data_list = []
            for _, row in df.tail(days).iterrows():
                data_list.append(MarginData(
                    date=str(row.get('信用交易日期', '')),
                    financing_balance=self._safe_float(row.get('融资余额')) / 100000000,
                    financing_buy=self._safe_float(row.get('融资买入额')) / 100000000,
                    financing_repay=self._safe_float(row.get('融资偿还额')) / 100000000,
                    securities_balance=self._safe_float(row.get('融券余额')) / 100000000,
                    securities_volume=self._safe_float(row.get('融券余量')) / 10000,
                    total_balance=(self._safe_float(row.get('融资余额', 0)) + 
                                   self._safe_float(row.get('融券余额', 0))) / 100000000
                ))
            
            return data_list
            
        except Exception as e:
            logger.error(f"获取市场两融数据失败: {e}")
            return []
    
    def get_stock_margin(self, stock_code: str, 
                         days: int = 30) -> List[StockMarginDetail]:
        """
        获取个股融资融券数据
        
        Args:
            stock_code: 股票代码
            days: 获取天数
            
        Returns:
            个股两融数据列表
        """
        if not HAS_AKSHARE:
            logger.error("akshare未安装，无法获取两融数据")
            return []
        
        try:
            code = stock_code.split('.')[0] if '.' in stock_code else stock_code
            
            # 判断市场
            if code.startswith('6'):
                df = ak.stock_margin_detail_sse(code)
            else:
                df = ak.stock_margin_detail_szse(code)
            
            if df is None or df.empty:
                logger.warning(f"未获取到股票 {stock_code} 的两融数据")
                return []
            
            data_list = []
            for _, row in df.tail(days).iterrows():
                financing_buy = self._safe_float(row.get('融资买入额', 0))
                financing_repay = self._safe_float(row.get('融资偿还额', 0))
                
                data_list.append(StockMarginDetail(
                    stock_code=stock_code,
                    stock_name=str(row.get('标的证券简称', '')),
                    date=str(row.get('信用交易日期', '')),
                    financing_balance=self._safe_float(row.get('融资余额')) / 100000000,
                    financing_balance_ratio=self._safe_float(row.get('融资余额占流通市值比', 0)),
                    financing_buy=financing_buy / 100000000,
                    financing_repay=financing_repay / 100000000,
                    financing_net=(financing_buy - financing_repay) / 100000000,
                    securities_balance=self._safe_float(row.get('融券余额')) / 100000000,
                    securities_volume=self._safe_float(row.get('融券余量')) / 10000,
                    securities_sell=self._safe_float(row.get('融券卖出量', 0)) / 10000,
                    securities_repay=self._safe_float(row.get('融券偿还量', 0)) / 10000
                ))
            
            return data_list
            
        except Exception as e:
            logger.error(f"获取个股两融数据失败: {e}")
            return []
    
    def analyze_margin_trend(self, stock_code: str = "",
                              stock_name: str = "",
                              days: int = 20) -> MarginTrend:
        """
        分析融资融券趋势
        
        Args:
            stock_code: 股票代码（空则分析市场整体）
            stock_name: 股票名称
            days: 分析天数
            
        Returns:
            趋势分析结果
        """
        if stock_code:
            data_list = self.get_stock_margin(stock_code, days)
        else:
            data_list = self.get_market_margin(days)
        
        if len(data_list) < 2:
            return MarginTrend(
                stock_code=stock_code,
                stock_name=stock_name,
                period_days=days,
                analysis="数据不足，无法分析"
            )
        
        # 计算融资变化
        first_financing = data_list[0].financing_balance
        last_financing = data_list[-1].financing_balance
        financing_change = last_financing - first_financing
        financing_change_pct = (financing_change / first_financing * 100) if first_financing > 0 else 0
        
        # 计算融券变化
        first_securities = data_list[0].securities_balance
        last_securities = data_list[-1].securities_balance
        securities_change = last_securities - first_securities
        securities_change_pct = (securities_change / first_securities * 100) if first_securities > 0 else 0
        
        # 判断趋势
        if financing_change_pct > 5:
            financing_trend = "上升"
        elif financing_change_pct < -5:
            financing_trend = "下降"
        else:
            financing_trend = "震荡"
        
        if securities_change_pct > 10:
            securities_trend = "上升"
        elif securities_change_pct < -10:
            securities_trend = "下降"
        else:
            securities_trend = "震荡"
        
        # 计算日均净买入
        if hasattr(data_list[0], 'financing_net'):
            total_net = sum(d.financing_net for d in data_list if hasattr(d, 'financing_net'))
            avg_daily = total_net / len(data_list)
        else:
            avg_daily = financing_change / len(data_list)
        
        # 生成信号
        signal, strength = self._generate_signal(
            financing_change_pct, securities_change_pct, financing_trend
        )
        
        # 生成分析文本
        analysis = self._generate_analysis(
            stock_code, stock_name, financing_trend, securities_trend,
            financing_change, securities_change, signal
        )
        
        return MarginTrend(
            stock_code=stock_code,
            stock_name=stock_name,
            period_days=days,
            financing_trend=financing_trend,
            financing_change=round(financing_change, 2),
            financing_change_pct=round(financing_change_pct, 2),
            financing_avg_daily=round(avg_daily, 2),
            securities_trend=securities_trend,
            securities_change=round(securities_change, 2),
            securities_change_pct=round(securities_change_pct, 2),
            signal=signal,
            signal_strength=strength,
            analysis=analysis
        )
    
    def get_margin_ranking(self, top_n: int = 20, 
                           rank_by: str = "financing_balance") -> List[Dict]:
        """
        获取融资融券排名
        
        Args:
            top_n: 返回数量
            rank_by: 排名依据 (financing_balance/financing_net/securities_balance)
            
        Returns:
            排名列表
        """
        if not HAS_AKSHARE:
            logger.warning("akshare未安装，无法获取两融排名数据")
            return []
        
        try:
            df = ak.stock_margin_underlying_info_szse()
            
            if df is None or df.empty:
                logger.warning("未获取到两融排名数据")
                return []
            
            # 排序
            sort_col = {
                'financing_balance': '融资余额',
                'financing_net': '融资净买入',
                'securities_balance': '融券余额'
            }.get(rank_by, '融资余额')
            
            if sort_col in df.columns:
                df = df.sort_values(sort_col, ascending=False)
            
            ranking = []
            for i, (_, row) in enumerate(df.head(top_n).iterrows(), 1):
                ranking.append({
                    'rank': i,
                    'stock_code': str(row.get('证券代码', '')),
                    'stock_name': str(row.get('证券简称', '')),
                    'financing_balance': self._safe_float(row.get('融资余额', 0)) / 100000000,
                    'securities_balance': self._safe_float(row.get('融券余额', 0)) / 100000000
                })
            
            return ranking
            
        except Exception as e:
            logger.error(f"获取两融排名失败: {e}")
            return []
    
    def get_margin_statistics(self) -> Dict:
        """
        获取融资融券统计数据
        
        Returns:
            统计数据
        """
        market_data = self.get_market_margin(30)
        
        if not market_data:
            return {
                'error': '无法获取数据'
            }
        
        latest = market_data[-1]
        
        # 计算变化
        if len(market_data) >= 5:
            five_days_ago = market_data[-5]
            financing_5d_change = latest.financing_balance - five_days_ago.financing_balance
        else:
            financing_5d_change = 0
        
        if len(market_data) >= 20:
            twenty_days_ago = market_data[-20]
            financing_20d_change = latest.financing_balance - twenty_days_ago.financing_balance
        else:
            financing_20d_change = 0
        
        return {
            'date': latest.date,
            'financing_balance': round(latest.financing_balance, 2),
            'securities_balance': round(latest.securities_balance, 2),
            'total_balance': round(latest.total_balance, 2),
            'financing_5d_change': round(financing_5d_change, 2),
            'financing_20d_change': round(financing_20d_change, 2),
            'financing_buy_today': round(latest.financing_buy, 2),
            'market_sentiment': self._judge_market_sentiment(financing_5d_change, financing_20d_change)
        }
    
    def _generate_signal(self, financing_pct: float, 
                         securities_pct: float,
                         financing_trend: str) -> Tuple[str, float]:
        """生成两融信号"""
        # 融资增加+融券减少 = 看多
        # 融资减少+融券增加 = 看空
        
        score = 0.0
        
        # 融资变化贡献
        if financing_pct > 10:
            score += 0.4
        elif financing_pct > 5:
            score += 0.2
        elif financing_pct < -10:
            score -= 0.4
        elif financing_pct < -5:
            score -= 0.2
        
        # 融券变化贡献（反向）
        if securities_pct > 20:
            score -= 0.3
        elif securities_pct > 10:
            score -= 0.15
        elif securities_pct < -20:
            score += 0.3
        elif securities_pct < -10:
            score += 0.15
        
        # 判断信号
        if score >= 0.5:
            return MarginSignal.STRONG_BULLISH.value, min(score, 1.0)
        elif score >= 0.2:
            return MarginSignal.BULLISH.value, 0.5 + score
        elif score <= -0.5:
            return MarginSignal.STRONG_BEARISH.value, min(abs(score), 1.0)
        elif score <= -0.2:
            return MarginSignal.BEARISH.value, 0.5 + abs(score)
        else:
            return MarginSignal.NEUTRAL.value, 0.5
    
    def _generate_analysis(self, stock_code: str, stock_name: str,
                           financing_trend: str, securities_trend: str,
                           financing_change: float, securities_change: float,
                           signal: str) -> str:
        """生成分析文本"""
        target = f"{stock_name}({stock_code})" if stock_code else "市场整体"
        
        analysis = f"{target}两融分析：\n"
        
        # 融资分析
        if financing_change > 0:
            analysis += f"融资余额{financing_trend}，增加{abs(financing_change):.2f}亿元，"
            analysis += "显示市场做多意愿增强。"
        else:
            analysis += f"融资余额{financing_trend}，减少{abs(financing_change):.2f}亿元，"
            analysis += "显示市场做多意愿减弱。"
        
        # 融券分析
        if securities_change > 0:
            analysis += f"融券余额{securities_trend}，增加{abs(securities_change):.2f}亿元，"
            analysis += "空头力量有所增强。"
        elif securities_change < 0:
            analysis += f"融券余额{securities_trend}，减少{abs(securities_change):.2f}亿元，"
            analysis += "空头力量有所减弱。"
        
        # 综合判断
        analysis += f"\n综合信号：{signal}"
        
        return analysis
    
    def _judge_market_sentiment(self, change_5d: float, change_20d: float) -> str:
        """判断市场情绪"""
        if change_5d > 50 and change_20d > 100:
            return "积极做多"
        elif change_5d > 0 and change_20d > 0:
            return "偏乐观"
        elif change_5d < -50 and change_20d < -100:
            return "积极做空"
        elif change_5d < 0 and change_20d < 0:
            return "偏谨慎"
        else:
            return "观望"
    
    @staticmethod
    def _safe_float(value) -> float:
        """安全转换为float"""
        try:
            if pd is not None and pd.isna(value):
                return 0.0
            return float(value) if value else 0.0
        except (ValueError, TypeError):
            return 0.0


# 便捷函数
def get_margin_analyzer() -> MarginAnalyzer:
    """获取融资融券分析器实例"""
    return MarginAnalyzer()
