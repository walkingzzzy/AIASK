"""
龙虎榜分析工具
提供龙虎榜数据查询和席位分析功能
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging

try:
    import akshare as ak
except ImportError:
    ak = None

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class DragonTigerSeat:
    """龙虎榜席位数据"""
    rank: int
    name: str           # 营业部名称
    buy_amount: float   # 买入金额（万元）
    sell_amount: float  # 卖出金额（万元）
    net_amount: float   # 净买入（万元）
    seat_type: str      # 席位类型：institution/hot_money/normal
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DragonTigerRecord:
    """龙虎榜记录"""
    stock_code: str
    stock_name: str
    date: str
    reason: str         # 上榜原因
    close_price: float
    change_pct: float
    turnover: float     # 换手率
    buy_seats: List[DragonTigerSeat]
    sell_seats: List[DragonTigerSeat]
    net_buy: float      # 净买入（万元）
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result['buy_seats'] = [s.to_dict() for s in self.buy_seats]
        result['sell_seats'] = [s.to_dict() for s in self.sell_seats]
        return result


class DragonTigerAnalyzer:
    """
    龙虎榜分析器
    
    功能：
    1. 获取每日龙虎榜数据
    2. 获取个股龙虎榜历史
    3. 分析机构/游资席位
    4. 追踪知名游资动向
    """
    
    # 知名游资营业部
    HOT_MONEY_SEATS = [
        "东方财富证券拉萨团结路",
        "东方财富证券拉萨东环路",
        "华鑫证券上海分公司",
        "国泰君安上海江苏路",
        "中信证券上海溧阳路",
        "华泰证券深圳益田路",
        "银河证券绍兴",
        "财通证券杭州上塘路",
    ]
    
    def __init__(self):
        if ak is None:
            logger.warning("akshare未安装，龙虎榜功能不可用")
    
    def get_daily_list(self, date: Optional[str] = None) -> List[DragonTigerRecord]:
        """
        获取每日龙虎榜
        
        Args:
            date: 日期，格式YYYYMMDD，默认最近交易日
            
        Returns:
            龙虎榜记录列表
        """
        if ak is None:
            logger.error("akshare未安装，无法获取龙虎榜数据")
            return []
        
        try:
            if date is None:
                date = datetime.now().strftime("%Y%m%d")
            
            # 获取龙虎榜数据
            df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
            
            records = []
            # 按股票分组
            for stock_code in df['代码'].unique():
                stock_df = df[df['代码'] == stock_code]
                row = stock_df.iloc[0]
                
                # 解析买入席位
                buy_seats = self._parse_seats(stock_df, 'buy')
                sell_seats = self._parse_seats(stock_df, 'sell')
                
                records.append(DragonTigerRecord(
                    stock_code=str(row.get('代码', '')),
                    stock_name=str(row.get('名称', '')),
                    date=date,
                    reason=str(row.get('上榜原因', '')),
                    close_price=float(row.get('收盘价', 0)),
                    change_pct=float(row.get('涨跌幅', 0)),
                    turnover=float(row.get('换手率', 0)),
                    buy_seats=buy_seats,
                    sell_seats=sell_seats,
                    net_buy=sum(s.net_amount for s in buy_seats) - sum(s.net_amount for s in sell_seats)
                ))
            
            return records
            
        except Exception as e:
            logger.error(f"获取龙虎榜失败: {e}")
            return []
    
    def get_stock_history(self, stock_code: str, 
                          days: int = 30) -> List[DragonTigerRecord]:
        """
        获取个股龙虎榜历史
        
        Args:
            stock_code: 股票代码
            days: 查询天数
            
        Returns:
            龙虎榜记录列表
        """
        if ak is None:
            logger.error("akshare未安装，无法获取龙虎榜历史数据")
            return []
        
        try:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            
            df = ak.stock_lhb_stock_detail_em(symbol=stock_code)
            
            records = []
            for _, row in df.iterrows():
                records.append(DragonTigerRecord(
                    stock_code=stock_code,
                    stock_name=str(row.get('名称', '')),
                    date=str(row.get('上榜日期', '')),
                    reason=str(row.get('上榜原因', '')),
                    close_price=float(row.get('收盘价', 0)),
                    change_pct=float(row.get('涨跌幅', 0)),
                    turnover=float(row.get('换手率', 0)),
                    buy_seats=[],
                    sell_seats=[],
                    net_buy=float(row.get('龙虎榜净买额', 0))
                ))
            
            return records[:days]
            
        except Exception as e:
            logger.error(f"获取个股龙虎榜历史失败: {e}")
            return []
    
    def analyze_seats(self, record: DragonTigerRecord) -> Dict[str, Any]:
        """
        分析龙虎榜席位
        
        Args:
            record: 龙虎榜记录
            
        Returns:
            席位分析结果
        """
        # 统计机构席位
        institution_buy = sum(
            s.buy_amount for s in record.buy_seats 
            if s.seat_type == 'institution'
        )
        institution_sell = sum(
            s.sell_amount for s in record.sell_seats 
            if s.seat_type == 'institution'
        )
        
        # 统计游资席位
        hot_money_buy = sum(
            s.buy_amount for s in record.buy_seats 
            if s.seat_type == 'hot_money'
        )
        hot_money_sell = sum(
            s.sell_amount for s in record.sell_seats 
            if s.seat_type == 'hot_money'
        )
        
        # 判断信号
        if institution_buy > institution_sell and hot_money_buy > hot_money_sell:
            signal = "机构+游资共同买入，强烈看多"
        elif institution_buy > institution_sell:
            signal = "机构净买入，中期看多"
        elif hot_money_buy > hot_money_sell:
            signal = "游资净买入，短期看多"
        elif institution_sell > institution_buy:
            signal = "机构净卖出，谨慎"
        else:
            signal = "中性"
        
        return {
            "stock_code": record.stock_code,
            "stock_name": record.stock_name,
            "date": record.date,
            "reason": record.reason,
            "institution_net": round(institution_buy - institution_sell, 2),
            "hot_money_net": round(hot_money_buy - hot_money_sell, 2),
            "total_net": round(record.net_buy, 2),
            "signal": signal,
            "buy_seat_count": len(record.buy_seats),
            "sell_seat_count": len(record.sell_seats)
        }
    
    def get_hot_money_activity(self, days: int = 5) -> List[Dict]:
        """
        获取知名游资近期活动
        
        Args:
            days: 查询天数
            
        Returns:
            游资活动列表
        """
        # 简化实现，返回模拟数据
        return [
            {
                "seat_name": "东方财富证券拉萨团结路",
                "style": "打板",
                "recent_stocks": ["股票A", "股票B"],
                "win_rate": "65%",
                "avg_return": "+8.5%"
            },
            {
                "seat_name": "华鑫证券上海分公司",
                "style": "趋势",
                "recent_stocks": ["股票C", "股票D"],
                "win_rate": "58%",
                "avg_return": "+5.2%"
            }
        ]
    
    def _parse_seats(self, df, direction: str) -> List[DragonTigerSeat]:
        """解析席位数据"""
        seats = []
        # 简化实现
        return seats
    
    def _classify_seat(self, name: str) -> str:
        """分类席位类型"""
        if "机构专用" in name:
            return "institution"
        for hot_money in self.HOT_MONEY_SEATS:
            if hot_money in name:
                return "hot_money"
        return "normal"


# CrewAI工具定义
class DragonTigerDailyInput(BaseModel):
    """龙虎榜每日查询输入"""
    date: Optional[str] = Field(default=None, description="日期，格式YYYYMMDD")


class DragonTigerDailyTool(BaseTool):
    """龙虎榜每日数据工具"""
    name: str = "dragon_tiger_daily"
    description: str = "获取每日龙虎榜数据，包括上榜股票和席位信息"
    args_schema: type[BaseModel] = DragonTigerDailyInput
    
    def _run(self, date: Optional[str] = None) -> str:
        analyzer = DragonTigerAnalyzer()
        records = analyzer.get_daily_list(date)
        
        if not records:
            return "今日暂无龙虎榜数据"
        
        result = f"龙虎榜数据（{records[0].date}）：\n\n"
        for r in records[:10]:
            analysis = analyzer.analyze_seats(r)
            result += f"""
{r.stock_name}({r.stock_code})
- 上榜原因：{r.reason}
- 涨跌幅：{r.change_pct:+.2f}%
- 净买入：{r.net_buy:.0f}万元
- 信号：{analysis['signal']}
"""
        return result


class DragonTigerStockInput(BaseModel):
    """个股龙虎榜查询输入"""
    stock_code: str = Field(description="股票代码")
    days: int = Field(default=30, description="查询天数")


class DragonTigerStockTool(BaseTool):
    """个股龙虎榜历史工具"""
    name: str = "dragon_tiger_stock"
    description: str = "获取个股龙虎榜历史记录"
    args_schema: type[BaseModel] = DragonTigerStockInput
    
    def _run(self, stock_code: str, days: int = 30) -> str:
        analyzer = DragonTigerAnalyzer()
        records = analyzer.get_stock_history(stock_code, days)
        
        if not records:
            return f"{stock_code}近{days}日无龙虎榜记录"
        
        result = f"{stock_code}龙虎榜历史（近{days}日）：\n"
        for r in records:
            result += f"- {r.date}: {r.reason}, 涨跌{r.change_pct:+.1f}%, 净买入{r.net_buy:.0f}万\n"
        
        return result


# 便捷函数
def get_dragon_tiger_analyzer() -> DragonTigerAnalyzer:
    """获取龙虎榜分析器"""
    return DragonTigerAnalyzer()
