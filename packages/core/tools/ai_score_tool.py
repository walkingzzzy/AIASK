"""
AI评分工具
为CrewAI Agent提供AI评分能力
"""
from typing import Type, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from packages.core.services.stock_data_service import get_stock_service


class AIScoreInput(BaseModel):
    """AI评分工具输入"""
    stock_code: str = Field(..., description="股票代码，如600519")
    stock_name: str = Field(default="", description="股票名称，可选")
    include_explanation: bool = Field(default=True, description="是否包含评分解释")


class AIScoreTool(BaseTool):
    """
    AI评分工具
    
    功能：
    - 获取股票AI综合评分（1-10分）
    - 获取买卖信号（Strong Buy/Buy/Hold/Sell/Strong Sell）
    - 获取跑赢市场概率
    - 获取评分解释和建议
    """
    
    name: str = "ai_score_tool"
    description: str = """
    获取股票的AI综合评分。
    
    评分维度：
    - 技术面（25%）：均线趋势、MACD、RSI等
    - 基本面（30%）：估值、盈利能力、成长性
    - 资金面（25%）：北向资金、主力资金
    - 情绪面（10%）：市场情绪
    - 风险（10%）：波动率、最大回撤
    
    返回：
    - AI评分（1-10分）
    - 买卖信号
    - 跑赢市场概率
    - 关键影响因子
    - 风险提示
    """
    args_schema: Type[BaseModel] = AIScoreInput
    
    def _run(self, stock_code: str, stock_name: str = "", 
             include_explanation: bool = True) -> str:
        """执行AI评分"""
        try:
            service = get_stock_service()
            
            # 获取AI评分
            score_result = service.get_ai_score(stock_code, stock_name)
            if not score_result:
                return f"无法获取{stock_code}的AI评分，请检查股票代码是否正确"
            
            # 构建输出
            output = []
            output.append(f"=== {score_result.stock_name}({score_result.stock_code}) AI评分 ===")
            output.append(f"综合评分：{score_result.ai_score}/10")
            output.append(f"买卖信号：{score_result.signal}")
            output.append(f"跑赢市场概率：{score_result.beat_market_probability*100:.0f}%")
            output.append(f"置信度：{score_result.confidence*100:.0f}%")
            
            # 分项评分
            output.append("\n【分项评分】")
            dimension_names = {
                'technical': '技术面',
                'fundamental': '基本面',
                'fund_flow': '资金面',
                'sentiment': '情绪面',
                'risk': '风险'
            }
            for name, data in score_result.subscores.items():
                dim_name = dimension_names.get(name, name)
                output.append(f"- {dim_name}：{data['score']}分（权重{int(data['weight']*100)}%）")
            
            # 关键因子
            if score_result.top_factors:
                output.append("\n【关键影响因子】")
                for factor in score_result.top_factors:
                    output.append(f"- {factor.get('factor', '')}（{factor.get('impact', '')}）")
            
            # 风险提示
            if score_result.risks:
                output.append("\n【风险提示】")
                for risk in score_result.risks:
                    output.append(f"- {risk}")
            
            # 评分解释
            if include_explanation:
                explanation = service.get_score_explanation(stock_code, stock_name)
                if explanation:
                    output.append(f"\n【投资建议】")
                    output.append(explanation.summary)
                    for suggestion in explanation.suggestions[:3]:
                        output.append(f"- {suggestion}")
            
            output.append(f"\n更新时间：{score_result.updated_at}")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"AI评分计算失败：{str(e)}"


class BatchAIScoreInput(BaseModel):
    """批量AI评分输入"""
    stock_codes: str = Field(..., description="股票代码列表，逗号分隔，如600519,000858,000333")
    top_n: int = Field(default=10, description="返回评分最高的N只股票")


class BatchAIScoreTool(BaseTool):
    """
    批量AI评分工具
    
    功能：
    - 批量计算多只股票的AI评分
    - 返回评分最高的股票
    """
    
    name: str = "batch_ai_score_tool"
    description: str = """
    批量获取多只股票的AI评分，并按评分排序。
    适用于股票筛选和比较场景。
    
    输入：股票代码列表（逗号分隔）
    输出：按AI评分排序的股票列表
    """
    args_schema: Type[BaseModel] = BatchAIScoreInput
    
    def _run(self, stock_codes: str, top_n: int = 10) -> str:
        """执行批量AI评分"""
        try:
            service = get_stock_service()
            
            # 解析股票代码
            codes = [c.strip() for c in stock_codes.split(',') if c.strip()]
            if not codes:
                return "请提供有效的股票代码列表"
            
            # 获取评分
            results = service.get_top_stocks(codes, top_n=top_n)
            
            if not results:
                return "无法获取股票评分"
            
            # 构建输出
            output = [f"=== AI评分排名（共{len(results)}只）==="]
            for i, score in enumerate(results, 1):
                output.append(
                    f"{i}. {score.stock_name}({score.stock_code}) "
                    f"评分:{score.ai_score} 信号:{score.signal} "
                    f"概率:{score.beat_market_probability*100:.0f}%"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            return f"批量评分失败：{str(e)}"
