"""
大宗交易分析工具
提供大宗交易数据查询、分析等功能的CrewAI工具
"""
from typing import Dict, Any, List
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..block_trade.block_trade_analyzer import BlockTradeAnalyzer

logger = logging.getLogger(__name__)


# ==================== 输入模型 ====================

class DailyBlockTradeInput(BaseModel):
    """每日大宗交易查询输入"""
    date: str = Field(default="", description="日期，格式YYYYMMDD，默认最近交易日")


class StockBlockTradeInput(BaseModel):
    """个股大宗交易查询输入"""
    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(default="", description="股票名称")
    days: int = Field(default=30, description="查询天数")


class AbnormalTradeInput(BaseModel):
    """异常交易检测输入"""
    threshold_amount: float = Field(default=1.0, description="成交额阈值（亿元）")
    threshold_premium: float = Field(default=10.0, description="溢价率阈值%")


# ==================== CrewAI工具 ====================

class DailyBlockTradeTool(BaseTool):
    """
    每日大宗交易工具
    
    获取当日大宗交易数据和统计。
    """
    name: str = "daily_block_trade"
    description: str = """获取每日大宗交易数据。
    返回：
    - 成交笔数和总额
    - 溢价/折价成交统计
    - 成交额最大的交易
    - 机构席位交易
    """
    args_schema: type[BaseModel] = DailyBlockTradeInput
    
    def _run(self, date: str = "") -> str:
        """执行查询"""
        try:
            analyzer = BlockTradeAnalyzer()
            
            # 获取统计数据
            stats = analyzer.get_daily_statistics(date if date else None)
            
            # 获取机构交易
            institution_trades = analyzer.get_institution_trades()
            
            output = f"""
📊 大宗交易日报（{stats.date}）

【成交统计】
- 成交笔数：{stats.total_count}笔
- 成交总额：{stats.total_amount:.2f}亿元
- 溢价成交：{stats.premium_count}笔
- 折价成交：{stats.discount_count}笔
- 平均溢价率：{stats.avg_premium_rate:+.2f}%

【成交额Top5】
"""
            for i, trade in enumerate(stats.top_trades[:5], 1):
                premium_emoji = "📈" if trade['premium_rate'] > 0 else "📉"
                output += f"{i}. {trade['stock_name']}({trade['stock_code']})\n"
                output += f"   成交{trade['amount']/10000:.2f}亿 | {premium_emoji}溢价{trade['premium_rate']:+.2f}%\n"
            
            if institution_trades:
                output += f"\n【机构席位交易】共{len(institution_trades)}笔\n"
                for trade in institution_trades[:3]:
                    output += f"- {trade.stock_name}: 成交{trade.amount/10000:.2f}亿\n"
            
            return output
            
        except Exception as e:
            logger.error(f"大宗交易查询失败: {e}")
            return f"大宗交易查询失败: {str(e)}"


class StockBlockTradeTool(BaseTool):
    """
    个股大宗交易工具
    
    获取个股大宗交易历史和分析。
    """
    name: str = "stock_block_trade"
    description: str = """获取个股大宗交易数据。
    输入股票代码，返回：
    - 大宗交易次数和总额
    - 平均溢价率
    - 交易信号判断
    - 最近交易记录
    """
    args_schema: type[BaseModel] = StockBlockTradeInput
    
    def _run(self, stock_code: str, stock_name: str = "", days: int = 30) -> str:
        """执行查询"""
        try:
            analyzer = BlockTradeAnalyzer()
            
            # 获取汇总分析
            summary = analyzer.analyze_stock_block_trades(stock_code, stock_name, days)
            
            output = f"""
📊 {summary.stock_name or stock_code} 大宗交易分析（近{days}日）

【交易统计】
- 成交笔数：{summary.trade_count}笔
- 总成交量：{summary.total_volume:.2f}万股
- 总成交额：{summary.total_amount:.2f}亿元
- 平均溢价率：{summary.avg_premium_rate:+.2f}%
- 溢价成交：{summary.premium_trades}笔
- 折价成交：{summary.discount_trades}笔

【信号判断】
- 大宗交易信号：{summary.signal}

【最近交易记录】
"""
            for trade in summary.recent_trades[-5:]:
                premium_emoji = "📈" if trade['premium_rate'] > 0 else "📉"
                output += f"- {trade['trade_date']}: {premium_emoji}{trade['premium_rate']:+.2f}% 成交{trade['amount']/10000:.2f}亿\n"
            
            if not summary.recent_trades:
                output += "暂无交易记录\n"
            
            output += f"""
【分析说明】
{summary.analysis}
"""
            return output
            
        except Exception as e:
            logger.error(f"个股大宗交易查询失败: {e}")
            return f"个股大宗交易查询失败: {str(e)}"


class AbnormalBlockTradeTool(BaseTool):
    """
    异常大宗交易检测工具
    
    检测大额或异常溢价/折价的大宗交易。
    """
    name: str = "abnormal_block_trade"
    description: str = """检测异常大宗交易。
    检测大额成交或异常溢价/折价的交易，
    帮助发现潜在的机构动向或减持信号。
    """
    args_schema: type[BaseModel] = AbnormalTradeInput
    
    def _run(self, threshold_amount: float = 1.0, 
             threshold_premium: float = 10.0) -> str:
        """执行检测"""
        try:
            analyzer = BlockTradeAnalyzer()
            
            abnormal = analyzer.detect_abnormal_trades(threshold_amount, threshold_premium)
            
            if not abnormal:
                return f"未检测到异常大宗交易（阈值：成交额>{threshold_amount}亿 或 溢价率>{threshold_premium}%）"
            
            output = f"""
⚠️ 异常大宗交易检测

检测条件：成交额>{threshold_amount}亿 或 溢价率>{threshold_premium}%
检测到{len(abnormal)}笔异常交易：

"""
            for i, trade in enumerate(abnormal[:10], 1):
                amount_billion = trade.amount / 10000
                
                # 判断异常类型
                if amount_billion >= threshold_amount:
                    abnormal_type = "🔴大额交易"
                elif trade.premium_rate >= threshold_premium:
                    abnormal_type = "📈高溢价"
                else:
                    abnormal_type = "📉大幅折价"
                
                output += f"{i}. {abnormal_type} {trade.stock_name}({trade.stock_code})\n"
                output += f"   成交{amount_billion:.2f}亿 | 溢价{trade.premium_rate:+.2f}%\n"
                output += f"   买方：{trade.buyer[:20]}...\n" if len(trade.buyer) > 20 else f"   买方：{trade.buyer}\n"
            
            if len(abnormal) > 10:
                output += f"\n... 还有{len(abnormal) - 10}笔异常交易\n"
            
            output += """
💡 提示：
- 大额溢价成交可能表示机构看好
- 大幅折价成交可能存在减持压力
- 建议结合其他指标综合判断
"""
            return output
            
        except Exception as e:
            logger.error(f"异常交易检测失败: {e}")
            return f"异常交易检测失败: {str(e)}"


# ==================== 便捷函数 ====================

def get_block_trade_tools() -> List[BaseTool]:
    """获取所有大宗交易工具"""
    return [
        DailyBlockTradeTool(),
        StockBlockTradeTool(),
        AbnormalBlockTradeTool()
    ]
