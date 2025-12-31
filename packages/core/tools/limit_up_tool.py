"""
涨停分析工具
提供涨停数据查询、原因分析、连板预测等功能的CrewAI工具
"""
from typing import Dict, Any, List, Optional
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..limit_up.limit_up_analyzer import (
    LimitUpAnalyzer,
    LimitUpStock,
    LimitUpReason,
    ContinuationPrediction
)

logger = logging.getLogger(__name__)


# ==================== 输入模型 ====================

class DailyLimitUpInput(BaseModel):
    """每日涨停查询输入"""
    date: str = Field(default="", description="日期，格式YYYYMMDD，默认今天")
    min_continuous: int = Field(default=1, description="最小连板天数，默认1")


class LimitUpReasonInput(BaseModel):
    """涨停原因分析输入"""
    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(default="", description="股票名称")


class ContinuationPredictInput(BaseModel):
    """连板预测输入"""
    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(default="", description="股票名称")


class LimitUpStatisticsInput(BaseModel):
    """涨停统计输入"""
    date: str = Field(default="", description="日期，格式YYYYMMDD")


# ==================== CrewAI工具 ====================

class DailyLimitUpTool(BaseTool):
    """
    每日涨停查询工具
    
    获取当日涨停股票列表，包括首板、连板等信息。
    """
    name: str = "daily_limit_up_query"
    description: str = """查询每日涨停股票列表。
    返回涨停股票的详细信息，包括：
    - 股票代码和名称
    - 涨停时间和类型（首板/连板）
    - 连板天数
    - 换手率和成交额
    - 涨停原因和所属概念
    - 封单金额
    可以筛选连板股票。
    """
    args_schema: type[BaseModel] = DailyLimitUpInput
    
    def _run(self, date: str = "", min_continuous: int = 1) -> str:
        """执行查询"""
        try:
            analyzer = LimitUpAnalyzer()
            
            if min_continuous > 1:
                stocks = analyzer.get_continuous_limit_up(min_continuous)
                title = f"连板股票（{min_continuous}板及以上）"
            else:
                stocks = analyzer.get_daily_limit_up(date if date else None)
                title = "今日涨停股票"
            
            if not stocks:
                return "未获取到涨停数据"
            
            output = f"""
🔥 {title}

【涨停统计】
- 涨停总数：{len(stocks)}只
- 首板：{sum(1 for s in stocks if s.continuous_days == 1)}只
- 连板：{sum(1 for s in stocks if s.continuous_days >= 2)}只
- 最高连板：{max(s.continuous_days for s in stocks)}板

【涨停列表】
"""
            # 按连板数排序
            stocks.sort(key=lambda x: x.continuous_days, reverse=True)
            
            for i, stock in enumerate(stocks[:20], 1):
                board_emoji = "🔴" * min(stock.continuous_days, 5)
                output += f"{i}. {board_emoji} {stock.stock_name}({stock.stock_code})\n"
                output += f"   {stock.limit_up_type} | 换手{stock.turnover_rate:.1f}% | 成交{stock.amount:.1f}亿\n"
                if stock.limit_up_reason:
                    output += f"   原因：{stock.limit_up_reason[:30]}\n"
                output += "\n"
            
            if len(stocks) > 20:
                output += f"... 还有{len(stocks) - 20}只涨停股票\n"
            
            return output
            
        except Exception as e:
            logger.error(f"涨停查询失败: {e}")
            return f"涨停查询失败: {str(e)}"


class LimitUpReasonTool(BaseTool):
    """
    涨停原因分析工具
    
    分析个股涨停的原因。
    """
    name: str = "limit_up_reason_analysis"
    description: str = """分析个股涨停原因。
    输入涨停股票代码，返回：
    - 主要涨停原因
    - 原因类型（概念题材/业绩驱动/并购重组等）
    - 相关概念
    - 分析说明
    """
    args_schema: type[BaseModel] = LimitUpReasonInput
    
    def _run(self, stock_code: str, stock_name: str = "") -> str:
        """分析涨停原因"""
        try:
            analyzer = LimitUpAnalyzer()
            reason = analyzer.analyze_limit_up_reason(stock_code, stock_name)
            
            output = f"""
📊 {reason.stock_name or stock_code} 涨停原因分析

【主要原因】
{reason.primary_reason}

【原因类型】
{reason.reason_type}

【相关概念】
{', '.join(reason.related_concepts) if reason.related_concepts else '无'}

【分析说明】
{reason.analysis}

【置信度】
{reason.confidence:.0%}
"""
            return output
            
        except Exception as e:
            logger.error(f"涨停原因分析失败: {e}")
            return f"涨停原因分析失败: {str(e)}"


class ContinuationPredictTool(BaseTool):
    """
    连板预测工具
    
    预测涨停股票的连板概率。
    """
    name: str = "continuation_prediction"
    description: str = """预测涨停股票的连板概率。
    输入涨停股票代码，返回：
    - 当前连板数
    - 连板概率预测
    - 影响因子分析
    - 风险等级
    - 操作建议
    """
    args_schema: type[BaseModel] = ContinuationPredictInput
    
    def _run(self, stock_code: str, stock_name: str = "") -> str:
        """预测连板"""
        try:
            analyzer = LimitUpAnalyzer()
            prediction = analyzer.predict_continuation(stock_code, stock_name)
            
            # 概率条形图
            prob_bar = "█" * int(prediction.continuation_prob * 10) + "░" * (10 - int(prediction.continuation_prob * 10))
            
            output = f"""
🎯 {prediction.stock_name or stock_code} 连板预测

【当前状态】
- 连板天数：{prediction.current_continuous}板
- 连板概率：{prediction.continuation_prob:.0%} [{prob_bar}]
- 预测结论：{prediction.prediction}

【影响因子】
"""
            for factor in prediction.factors:
                output += f"- {factor['name']}：{factor['value']} → {factor['impact']}\n"
            
            output += f"""
【风险评估】
- 风险等级：{prediction.risk_level}

【操作建议】
{prediction.suggestion}

⚠️ 风险提示：连板股票波动剧烈，以上预测仅供参考，不构成投资建议。
"""
            return output
            
        except Exception as e:
            logger.error(f"连板预测失败: {e}")
            return f"连板预测失败: {str(e)}"


class LimitUpStatisticsTool(BaseTool):
    """
    涨停统计工具
    
    统计涨停市场数据。
    """
    name: str = "limit_up_statistics"
    description: str = """获取涨停市场统计数据。
    返回：
    - 涨停总数、首板数、连板数
    - 平均换手率
    - 热门概念板块
    - 最高连板数
    """
    args_schema: type[BaseModel] = LimitUpStatisticsInput
    
    def _run(self, date: str = "") -> str:
        """获取统计"""
        try:
            analyzer = LimitUpAnalyzer()
            stats = analyzer.get_limit_up_statistics(date if date else None)
            
            output = f"""
📈 涨停市场统计

【基本数据】
- 涨停总数：{stats['total']}只
- 首板数量：{stats['first_limit']}只
- 连板数量：{stats['continuous']}只
- 炸板数量：{stats['broken']}只
- 最高连板：{stats['max_continuous']}板
- 平均换手：{stats['avg_turnover']:.1f}%

【热门概念】
"""
            for i, concept in enumerate(stats['hot_concepts'], 1):
                output += f"{i}. {concept['name']}：{concept['count']}只涨停\n"
            
            if not stats['hot_concepts']:
                output += "暂无数据\n"
            
            # 市场情绪判断
            if stats['total'] > 100:
                mood = "🔥 市场情绪火热，涨停潮涌现"
            elif stats['total'] > 50:
                mood = "📈 市场情绪偏暖，赚钱效应尚可"
            elif stats['total'] > 20:
                mood = "😐 市场情绪一般，注意控制仓位"
            else:
                mood = "❄️ 市场情绪低迷，建议观望为主"
            
            output += f"\n【市场情绪】\n{mood}\n"
            
            return output
            
        except Exception as e:
            logger.error(f"涨停统计失败: {e}")
            return f"涨停统计失败: {str(e)}"


class HotConceptTool(BaseTool):
    """
    热门概念追踪工具
    
    追踪涨停股票的热门概念。
    """
    name: str = "hot_concept_tracking"
    description: str = """追踪涨停股票的热门概念板块。
    分析当日涨停股票所属概念，找出最热门的题材方向。
    """
    args_schema: type[BaseModel] = LimitUpStatisticsInput
    
    def _run(self, date: str = "") -> str:
        """追踪热门概念"""
        try:
            analyzer = LimitUpAnalyzer()
            stocks = analyzer.get_daily_limit_up(date if date else None)
            
            if not stocks:
                return "未获取到涨停数据"
            
            # 统计概念
            concept_stocks = {}
            for stock in stocks:
                concepts = [stock.concept] if stock.concept else []
                if stock.limit_up_reason:
                    # 从涨停原因中提取概念
                    for hot in analyzer.HOT_CONCEPTS:
                        if hot in stock.limit_up_reason:
                            concepts.append(hot)
                
                for concept in concepts:
                    if concept:
                        if concept not in concept_stocks:
                            concept_stocks[concept] = []
                        concept_stocks[concept].append(stock)
            
            # 排序
            sorted_concepts = sorted(
                concept_stocks.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )
            
            output = """
🔥 今日热门概念追踪

"""
            for i, (concept, stocks_list) in enumerate(sorted_concepts[:10], 1):
                output += f"【{i}. {concept}】涨停{len(stocks_list)}只\n"
                for stock in stocks_list[:3]:
                    board = f"{stock.continuous_days}板" if stock.continuous_days > 1 else "首板"
                    output += f"   - {stock.stock_name}({stock.stock_code}) {board}\n"
                if len(stocks_list) > 3:
                    output += f"   ... 还有{len(stocks_list) - 3}只\n"
                output += "\n"
            
            return output
            
        except Exception as e:
            logger.error(f"热门概念追踪失败: {e}")
            return f"热门概念追踪失败: {str(e)}"


# ==================== 便捷函数 ====================

def get_limit_up_tools() -> List[BaseTool]:
    """获取所有涨停分析工具"""
    return [
        DailyLimitUpTool(),
        LimitUpReasonTool(),
        ContinuationPredictTool(),
        LimitUpStatisticsTool(),
        HotConceptTool()
    ]
