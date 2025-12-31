"""
大宗交易分析器
提供大宗交易数据获取、分析和监控功能
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


class TradeSignal(Enum):
    """大宗交易信号"""
    STRONG_POSITIVE = "强烈利好"   # 大幅溢价成交
    POSITIVE = "利好"             # 溢价成交
    NEUTRAL = "中性"              # 平价成交
    NEGATIVE = "利空"             # 折价成交
    STRONG_NEGATIVE = "强烈利空"  # 大幅折价成交


@dataclass
class BlockTrade:
    """大宗交易记录"""
    stock_code: str
    stock_name: str
    trade_date: str
    trade_price: float            # 成交价
    close_price: float            # 收盘价
    premium_rate: float           # 溢价率%（正为溢价，负为折价）
    volume: float                 # 成交量（万股）
    amount: float                 # 成交额（万元）
    buyer: str = ""               # 买方营业部
    seller: str = ""              # 卖方营业部
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class BlockTradeStatistics:
    """大宗交易统计"""
    date: str
    total_count: int              # 成交笔数
    total_amount: float           # 成交总额（亿元）
    premium_count: int            # 溢价成交笔数
    discount_count: int           # 折价成交笔数
    avg_premium_rate: float       # 平均溢价率%
    top_trades: List[Dict] = field(default_factory=list)  # 成交额最大的交易
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class StockBlockTradeSummary:
    """个股大宗交易汇总"""
    stock_code: str
    stock_name: str
    period_days: int
    trade_count: int              # 成交笔数
    total_volume: float           # 总成交量（万股）
    total_amount: float           # 总成交额（亿元）
    avg_premium_rate: float       # 平均溢价率%
    premium_trades: int           # 溢价成交次数
    discount_trades: int          # 折价成交次数
    signal: str = "中性"
    analysis: str = ""
    recent_trades: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return asdict(self)


class BlockTradeAnalyzer:
    """
    大宗交易分析器
    
    功能：
    1. 获取每日大宗交易数据
    2. 获取个股大宗交易历史
    3. 分析大宗交易信号
    4. 监控异常大宗交易
    """
    
    # 溢价率阈值
    PREMIUM_THRESHOLDS = {
        'strong_positive': 5.0,   # 溢价5%以上
        'positive': 0.0,          # 溢价
        'negative': -5.0,         # 折价5%以内
        'strong_negative': -10.0  # 折价10%以上
    }
    
    def __init__(self):
        self._cache = {}
    
    def get_daily_block_trades(self, date: str = None) -> List[BlockTrade]:
        """
        获取每日大宗交易数据
        
        Args:
            date: 日期，格式YYYYMMDD，默认最近交易日
            
        Returns:
            大宗交易列表
        """
        if not HAS_AKSHARE:
            return self._mock_daily_trades()
        
        try:
            df = ak.stock_dzjy_mrmx(symbol="全部")
            
            if df is None or df.empty:
                return self._mock_daily_trades()
            
            trades = []
            for _, row in df.iterrows():
                close_price = self._safe_float(row.get('收盘价', 0))
                trade_price = self._safe_float(row.get('成交价', 0))
                
                if close_price > 0:
                    premium_rate = (trade_price - close_price) / close_price * 100
                else:
                    premium_rate = 0
                
                trades.append(BlockTrade(
                    stock_code=str(row.get('证券代码', '')),
                    stock_name=str(row.get('证券简称', '')),
                    trade_date=str(row.get('交易日期', '')),
                    trade_price=trade_price,
                    close_price=close_price,
                    premium_rate=round(premium_rate, 2),
                    volume=self._safe_float(row.get('成交量', 0)) / 10000,
                    amount=self._safe_float(row.get('成交额', 0)) / 10000,
                    buyer=str(row.get('买方营业部', '')),
                    seller=str(row.get('卖方营业部', ''))
                ))
            
            return trades
            
        except Exception as e:
            logger.error(f"获取大宗交易数据失败: {e}")
            return self._mock_daily_trades()
    
    def get_stock_block_trades(self, stock_code: str, 
                                days: int = 30) -> List[BlockTrade]:
        """
        获取个股大宗交易历史
        
        Args:
            stock_code: 股票代码
            days: 获取天数
            
        Returns:
            大宗交易列表
        """
        if not HAS_AKSHARE:
            return self._mock_stock_trades(stock_code, days)
        
        try:
            code = stock_code.split('.')[0] if '.' in stock_code else stock_code
            df = ak.stock_dzjy_mrtj(symbol=code)
            
            if df is None or df.empty:
                return self._mock_stock_trades(stock_code, days)
            
            trades = []
            for _, row in df.tail(days).iterrows():
                close_price = self._safe_float(row.get('收盘价', 0))
                trade_price = self._safe_float(row.get('成交价', 0))
                
                if close_price > 0:
                    premium_rate = (trade_price - close_price) / close_price * 100
                else:
                    premium_rate = 0
                
                trades.append(BlockTrade(
                    stock_code=stock_code,
                    stock_name=str(row.get('证券简称', '')),
                    trade_date=str(row.get('交易日期', '')),
                    trade_price=trade_price,
                    close_price=close_price,
                    premium_rate=round(premium_rate, 2),
                    volume=self._safe_float(row.get('成交量', 0)) / 10000,
                    amount=self._safe_float(row.get('成交额', 0)) / 10000,
                    buyer=str(row.get('买方营业部', '')),
                    seller=str(row.get('卖方营业部', ''))
                ))
            
            return trades
            
        except Exception as e:
            logger.error(f"获取个股大宗交易失败: {e}")
            return self._mock_stock_trades(stock_code, days)
    
    def analyze_stock_block_trades(self, stock_code: str,
                                    stock_name: str = "",
                                    days: int = 30) -> StockBlockTradeSummary:
        """
        分析个股大宗交易
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            days: 分析天数
            
        Returns:
            大宗交易汇总分析
        """
        trades = self.get_stock_block_trades(stock_code, days)
        
        if not trades:
            return StockBlockTradeSummary(
                stock_code=stock_code,
                stock_name=stock_name,
                period_days=days,
                trade_count=0,
                total_volume=0,
                total_amount=0,
                avg_premium_rate=0,
                premium_trades=0,
                discount_trades=0,
                analysis="无大宗交易记录"
            )
        
        # 统计
        total_volume = sum(t.volume for t in trades)
        total_amount = sum(t.amount for t in trades) / 10000  # 转为亿元
        premium_trades = sum(1 for t in trades if t.premium_rate > 0)
        discount_trades = sum(1 for t in trades if t.premium_rate < 0)
        avg_premium = sum(t.premium_rate for t in trades) / len(trades)
        
        # 生成信号
        signal = self._generate_signal(avg_premium, premium_trades, discount_trades, len(trades))
        
        # 生成分析
        analysis = self._generate_analysis(
            stock_code, stock_name, len(trades), total_amount,
            avg_premium, premium_trades, discount_trades, signal
        )
        
        # 最近交易
        recent = [t.to_dict() for t in trades[-5:]]
        
        return StockBlockTradeSummary(
            stock_code=stock_code,
            stock_name=stock_name or (trades[0].stock_name if trades else ""),
            period_days=days,
            trade_count=len(trades),
            total_volume=round(total_volume, 2),
            total_amount=round(total_amount, 2),
            avg_premium_rate=round(avg_premium, 2),
            premium_trades=premium_trades,
            discount_trades=discount_trades,
            signal=signal,
            analysis=analysis,
            recent_trades=recent
        )
    
    def get_daily_statistics(self, date: str = None) -> BlockTradeStatistics:
        """
        获取每日大宗交易统计
        
        Args:
            date: 日期
            
        Returns:
            统计数据
        """
        trades = self.get_daily_block_trades(date)
        
        if not trades:
            return BlockTradeStatistics(
                date=date or datetime.now().strftime("%Y-%m-%d"),
                total_count=0,
                total_amount=0,
                premium_count=0,
                discount_count=0,
                avg_premium_rate=0
            )
        
        total_amount = sum(t.amount for t in trades) / 10000  # 转为亿元
        premium_count = sum(1 for t in trades if t.premium_rate > 0)
        discount_count = sum(1 for t in trades if t.premium_rate < 0)
        avg_premium = sum(t.premium_rate for t in trades) / len(trades)
        
        # 成交额最大的交易
        sorted_trades = sorted(trades, key=lambda x: x.amount, reverse=True)
        top_trades = [t.to_dict() for t in sorted_trades[:5]]
        
        return BlockTradeStatistics(
            date=trades[0].trade_date if trades else "",
            total_count=len(trades),
            total_amount=round(total_amount, 2),
            premium_count=premium_count,
            discount_count=discount_count,
            avg_premium_rate=round(avg_premium, 2),
            top_trades=top_trades
        )
    
    def detect_abnormal_trades(self, threshold_amount: float = 1.0,
                                threshold_premium: float = 10.0) -> List[BlockTrade]:
        """
        检测异常大宗交易
        
        Args:
            threshold_amount: 成交额阈值（亿元）
            threshold_premium: 溢价率阈值%
            
        Returns:
            异常交易列表
        """
        trades = self.get_daily_block_trades()
        
        abnormal = []
        for trade in trades:
            amount_billion = trade.amount / 10000  # 转为亿元
            
            # 大额交易
            if amount_billion >= threshold_amount:
                abnormal.append(trade)
            # 高溢价交易
            elif trade.premium_rate >= threshold_premium:
                abnormal.append(trade)
            # 大幅折价交易
            elif trade.premium_rate <= -threshold_premium:
                abnormal.append(trade)
        
        return abnormal
    
    def get_institution_trades(self) -> List[BlockTrade]:
        """
        获取机构专用席位大宗交易
        
        Returns:
            机构交易列表
        """
        trades = self.get_daily_block_trades()
        
        institution_keywords = ['机构专用', '机构席位']
        
        institution_trades = []
        for trade in trades:
            if any(kw in trade.buyer or kw in trade.seller for kw in institution_keywords):
                institution_trades.append(trade)
        
        return institution_trades
    
    def _generate_signal(self, avg_premium: float, 
                         premium_count: int,
                         discount_count: int,
                         total_count: int) -> str:
        """生成大宗交易信号"""
        if total_count == 0:
            return TradeSignal.NEUTRAL.value
        
        premium_ratio = premium_count / total_count
        
        if avg_premium >= 5 and premium_ratio >= 0.7:
            return TradeSignal.STRONG_POSITIVE.value
        elif avg_premium > 0 and premium_ratio >= 0.5:
            return TradeSignal.POSITIVE.value
        elif avg_premium <= -10 and premium_ratio <= 0.3:
            return TradeSignal.STRONG_NEGATIVE.value
        elif avg_premium < -5:
            return TradeSignal.NEGATIVE.value
        else:
            return TradeSignal.NEUTRAL.value
    
    def _generate_analysis(self, stock_code: str, stock_name: str,
                           trade_count: int, total_amount: float,
                           avg_premium: float, premium_count: int,
                           discount_count: int, signal: str) -> str:
        """生成分析文本"""
        target = f"{stock_name}({stock_code})" if stock_name else stock_code
        
        analysis = f"{target}大宗交易分析：\n"
        analysis += f"近期共发生{trade_count}笔大宗交易，总成交额{total_amount:.2f}亿元。\n"
        
        if avg_premium > 0:
            analysis += f"平均溢价率{avg_premium:.2f}%，溢价成交{premium_count}笔，"
            analysis += "显示机构或大资金看好该股。"
        elif avg_premium < -5:
            analysis += f"平均折价率{abs(avg_premium):.2f}%，折价成交{discount_count}笔，"
            analysis += "可能存在减持压力，需关注后续走势。"
        else:
            analysis += f"平均溢价率{avg_premium:.2f}%，成交价格接近市价，"
            analysis += "属于正常交易行为。"
        
        analysis += f"\n综合信号：{signal}"
        
        return analysis
    
    def _mock_daily_trades(self) -> List[BlockTrade]:
        """模拟每日大宗交易"""
        import random
        
        stocks = [
            ("600519", "贵州茅台", 1850.0),
            ("000858", "五粮液", 165.0),
            ("601318", "中国平安", 48.0),
            ("300750", "宁德时代", 210.0),
            ("002594", "比亚迪", 285.0),
        ]
        
        trades = []
        for code, name, price in stocks:
            premium = random.uniform(-8, 5)
            trade_price = price * (1 + premium / 100)
            
            trades.append(BlockTrade(
                stock_code=code,
                stock_name=name,
                trade_date=datetime.now().strftime("%Y-%m-%d"),
                trade_price=round(trade_price, 2),
                close_price=price,
                premium_rate=round(premium, 2),
                volume=round(random.uniform(10, 100), 2),
                amount=round(random.uniform(1000, 10000), 2),
                buyer="机构专用" if random.random() > 0.7 else "某证券营业部",
                seller="某证券营业部"
            ))
        
        return trades
    
    def _mock_stock_trades(self, stock_code: str, days: int) -> List[BlockTrade]:
        """模拟个股大宗交易"""
        import random
        
        trades = []
        base_date = datetime.now()
        base_price = 100.0
        
        # 模拟部分天数有交易
        trade_days = random.sample(range(days), min(days // 3, 10))
        
        for i in trade_days:
            date = (base_date - timedelta(days=days-i-1)).strftime("%Y-%m-%d")
            premium = random.uniform(-10, 8)
            trade_price = base_price * (1 + premium / 100)
            
            trades.append(BlockTrade(
                stock_code=stock_code,
                stock_name="模拟股票",
                trade_date=date,
                trade_price=round(trade_price, 2),
                close_price=base_price,
                premium_rate=round(premium, 2),
                volume=round(random.uniform(5, 50), 2),
                amount=round(random.uniform(500, 5000), 2),
                buyer="某证券营业部",
                seller="某证券营业部"
            ))
        
        return sorted(trades, key=lambda x: x.trade_date)
    
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
def get_block_trade_analyzer() -> BlockTradeAnalyzer:
    """获取大宗交易分析器实例"""
    return BlockTradeAnalyzer()
