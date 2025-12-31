"""
自然语言查询工具
为CrewAI Agent提供自然语言理解能力
"""
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from packages.core.nlp_query.intent_parser import IntentParser, IntentType
from packages.core.nlp_query.query_executor import QueryExecutor


class NLPQueryInput(BaseModel):
    """NLP查询工具输入"""
    query: str = Field(..., description="用户的自然语言查询，如'找出PE低于20的股票'或'分析贵州茅台'")


class NLPQueryTool(BaseTool):
    """
    自然语言查询工具
    
    功能：
    - 解析用户自然语言查询意图
    - 支持股票筛选、个股分析、数据查询三种意图
    - 自动提取股票代码、指标、条件等实体
    """
    
    name: str = "nlp_query_tool"
    description: str = """
    解析并执行用户的自然语言查询。
    
    支持的查询类型：
    1. 股票筛选：找出PE低于20的股票、筛选ROE大于15%的股票
    2. 个股分析：分析贵州茅台、600519怎么样
    3. 数据查询：茅台的PE是多少、平安银行今天涨了多少
    
    自动识别：
    - 股票代码（如600519）
    - 股票名称（如贵州茅台、茅台）
    - 指标（PE、PB、ROE等）
    - 筛选条件（大于、小于、等于）
    """
    args_schema: Type[BaseModel] = NLPQueryInput
    
    def _run(self, query: str) -> str:
        """执行NLP查询"""
        try:
            # 解析意图
            parser = IntentParser()
            intent = parser.parse(query)
            
            # 执行查询
            executor = QueryExecutor()
            result = executor.execute(intent)
            
            # 构建输出
            output = []
            output.append(f"=== 查询解析 ===")
            output.append(f"原始查询：{intent.original_query}")
            output.append(f"识别意图：{self._intent_name(intent.intent_type)}")
            output.append(f"置信度：{intent.confidence*100:.0f}%")
            
            if intent.entities:
                output.append(f"\n【提取实体】")
                if intent.entities.get('stock_codes'):
                    output.append(f"股票代码：{', '.join(intent.entities['stock_codes'])}")
                if intent.entities.get('stock_name'):
                    output.append(f"股票名称：{intent.entities['stock_name']}")
                if intent.entities.get('metric'):
                    output.append(f"查询指标：{intent.entities['metric']}")
                if intent.entities.get('conditions'):
                    output.append(f"筛选条件：")
                    for c in intent.entities['conditions']:
                        output.append(f"  - {c['metric']} {c['operator']} {c['value']}")
            
            output.append(f"\n=== 查询结果 ===")
            if result.success:
                output.append(result.message)
                if result.data:
                    if isinstance(result.data, dict):
                        if 'results' in result.data:
                            output.append("\n【筛选结果】")
                            for item in result.data['results'][:10]:
                                output.append(f"- {item.get('name', '')}({item.get('code', '')})")
                        elif 'summary' in result.data:
                            output.append(f"\n{result.data['summary']}")
                        elif 'answer' in result.data:
                            output.append(f"\n{result.data['answer']}")
            else:
                output.append(f"查询失败：{result.message}")
            
            if result.suggestions:
                output.append(f"\n【建议】")
                for s in result.suggestions:
                    output.append(f"- {s}")
            
            return "\n".join(output)
            
        except Exception as e:
            return f"NLP查询失败：{str(e)}"
    
    def _intent_name(self, intent_type: IntentType) -> str:
        """获取意图名称"""
        names = {
            IntentType.STOCK_SCREENING: "股票筛选",
            IntentType.STOCK_ANALYSIS: "个股分析",
            IntentType.DATA_QUERY: "数据查询",
            IntentType.UNKNOWN: "未知"
        }
        return names.get(intent_type, "未知")
