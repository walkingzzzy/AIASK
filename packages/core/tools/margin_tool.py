"""
融资融券分析工具
提供两融数据查询、趋势分析等功能的CrewAI工具
"""
from typing import Dict, Any, List
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..margin.margin_analyzer import MarginAnalyzer, MarginTrend

logger = logging.getLogger(__name__)


# ==================== 输入模型 ====================

class MarketMarginInput(BaseModel):
    """市场两融查询输入"""
    days: int = Field(default=20, description="查询天数")


class StockMarginInput(BaseModel):
    """个股两融查询输入"""
    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(default="", description="股票名称")
    days: int = Field(default=20, description="查询天数")


class MarginRankingInput(BaseModel):
    """两融排名查询输入"""
    top_n: int = Field(default=10, description="返回数量")
    rank_by: str = Field(default="financing_balance", description="排名依据")


# ==================== CrewAI工具 ====================

class MarketMarginTool(BaseTool):
    """
    市场融资融券工具
    
    获取市场整体两融数据和趋势分析。
    """
    name: str = "market_margin_analysis"
    description: str = """获取市场整体融资融券数据。
    返回：
    - 融资余额和变化趋势
    - 融券余额和变化趋势
    - 两融信号（看多/看空/中性）
    - 市场情绪判断
    """
    args_schema: type[BaseModel] = MarketMarginInput
    
    def _run(self, days: int = 20) -> str:
        """执行查询"""
        try:
            analyzer = MarginAnalyzer()
            
            # 获取统计数据
            stats = analyzer.get_margin_statistics()
            
            # 获取趋势分析
            trend = analyzer.analyze_margin_trend(days=days)
            
            output = f"""
📊 市场融资融券分析

【最新数据】（{stats.get('date', '')}）
- 融资余额：{stats.get('financing_balance', 0):.2f}亿元
- 融券余额：{stats.get('securities_balance', 0):.2f}亿元
- 两融余额：{stats.get('total_balance', 0):.2f}亿元
- 今日融资买入：{stats.get('financing_buy_today', 0):.2f}亿元

【变化趋势】（近{days}日）
- 融资趋势：{trend.financing_trend}
- 融资变化：{trend.financing_change:+.2f}亿元（{trend.financing_change_pct:+.2f}%）
- 日均净买入：{trend.financing_avg_daily:.2f}亿元
- 融券趋势：{trend.securities_trend}
- 融券变化：{trend.securities_change:+.2f}亿元

【信号判断】
- 两融信号：{trend.signal}
- 信号强度：{trend.signal_strength:.0%}
- 市场情绪：{stats.get('market_sentiment', '未知')}

【分析说明】
{trend.analysis}
"""
            return output
            
        except Exception as e:
            logger.error(f"市场两融分析失败: {e}")
            return f"市场两融分析失败: {str(e)}"


class StockMarginTool(BaseTool):
    """
    个股融资融券工具
    
    获取个股两融数据和趋势分析。
    """
    name: str = "stock_margin_analysis"
    description: str = """获取个股融资融券数据。
    输入股票代码，返回：
    - 融资余额和变化
    - 融券余额和变化
    - 融资净买入趋势
    - 两融信号判断
    """
    args_schema: type[BaseModel] = StockMarginInput
    
    def _run(self, stock_code: str, stock_name: str = "", days: int = 20) -> str:
        """执行查询"""
        try:
            analyzer = MarginAnalyzer()
            
            # 获取趋势分析
            trend = analyzer.analyze_margin_trend(stock_code, stock_name, days)
            
            # 获取最近数据
            data_list = analyzer.get_stock_margin(stock_code, 5)
            
            output = f"""
📊 {stock_name or stock_code} 融资融券分析

【趋势分析】（近{days}日）
- 融资趋势：{trend.financing_trend}
- 融资变化：{trend.financing_change:+.2f}亿元（{trend.financing_change_pct:+.2f}%）
- 日均净买入：{trend.financing_avg_daily:.2f}亿元
- 融券趋势：{trend.securities_trend}
- 融券变化：{trend.securities_change:+.2f}亿元

【信号判断】
- 两融信号：{trend.signal}
- 信号强度：{trend.signal_strength:.0%}

【最近5日数据】
"""
            for data in data_list[-5:]:
                output += f"- {data.date}: 融资{data.financing_balance:.2f}亿 净买入{data.financing_net:+.2f}亿\n"
            
            output += f"""
【分析说明】
{trend.analysis}
"""
            return output
            
        except Exception as e:
            logger.error(f"个股两融分析失败: {e}")
            return f"个股两融分析失败: {str(e)}"


class MarginRankingTool(BaseTool):
    """
    融资融券排名工具
    
    获取两融余额排名。
    """
    name: str = "margin_ranking"
    description: str = """获取融资融券排名。
    返回融资余额最高的股票列表。
    """
    args_schema: type[BaseModel] = MarginRankingInput
    
    def _run(self, top_n: int = 10, rank_by: str = "financing_balance") -> str:
        """执行查询"""
        try:
            analyzer = MarginAnalyzer()
            ranking = analyzer.get_margin_ranking(top_n, rank_by)
            
            rank_name = {
                'financing_balance': '融资余额',
                'financing_net': '融资净买入',
                'securities_balance': '融券余额'
            }.get(rank_by, '融资余额')
            
            output = f"📊 {rank_name}排名Top{top_n}\n\n"
            
            for item in ranking:
                output += f"{item['rank']}. {item['stock_name']}({item['stock_code']})\n"
                output += f"   融资余额：{item['financing_balance']:.2f}亿 | 融券余额：{item['securities_balance']:.2f}亿\n"
            
            return output
            
        except Exception as e:
            logger.error(f"两融排名查询失败: {e}")
            return f"两融排名查询失败: {str(e)}"


# ==================== 便捷函数 ====================

def get_margin_tools() -> List[BaseTool]:
    """获取所有融资融券工具"""
    return [
        MarketMarginTool(),
        StockMarginTool(),
        MarginRankingTool()
    ]
