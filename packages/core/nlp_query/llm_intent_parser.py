"""
基于LLM的意图解析器
使用大语言模型进行深度语义理解
"""
import json
import logging
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .intent_parser import IntentType, QueryIntent
from .stock_database import get_stock_database

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM配置"""
    api_key: str
    model: str = "gpt-4"
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 1000


class LLMIntentParser:
    """
    基于LLM的意图解析器

    使用大语言模型进行深度语义理解，支持：
    1. 复杂自然语言查询
    2. 全A股股票识别
    3. 多条件组合查询
    4. 上下文理解
    """

    SYSTEM_PROMPT = """你是一个专业的A股市场分析助手，负责理解用户的股票查询意图。

你的任务是将用户的自然语言查询解析为结构化的查询意图。

## 意图类型
1. stock_screening - 股票筛选
   - 用户想要根据条件筛选股票
   - 例如："找出PE低于20的股票"、"推荐ROE大于15%的股票"

2. stock_analysis - 个股分析
   - 用户想要分析某只具体股票
   - 例如："分析贵州茅台"、"宁德时代怎么样"

3. data_query - 数据查询
   - 用户想要查询某只股票的具体数据
   - 例如："茅台的PE是多少"、"比亚迪今天涨了多少"

## 输出格式
请以JSON格式输出，包含以下字段：
{
    "intent_type": "stock_screening | stock_analysis | data_query",
    "confidence": 0.0-1.0,
    "entities": {
        "stock_codes": ["代码1", "代码2"],  // 识别到的股票代码
        "stock_names": ["名称1", "名称2"],  // 识别到的股票名称
        "conditions": [  // 筛选条件（仅stock_screening）
            {"metric": "pe", "operator": ">", "value": 20}
        ],
        "metric": "pe",  // 查询指标（仅data_query）
        "analysis_type": "comprehensive",  // 分析类型（仅stock_analysis）
        "time_range": "short",  // 时间范围
        "limit": 10,  // 返回数量限制
        "sort_by": "ai_score",  // 排序字段
        "sort_order": "desc"  // 排序方向
    },
    "normalized_query": "标准化后的查询",
    "explanation": "简短解释你的理解"
}

## 指标映射
- PE/市盈率 -> pe
- PB/市净率 -> pb
- ROE/净资产收益率 -> roe
- 营收增速/收入增长 -> revenue_growth
- 利润增速/净利润增长 -> profit_growth
- 市值 -> market_cap
- 股价/价格 -> price
- 涨跌幅 -> change_pct
- 成交量 -> volume
- AI评分/评分 -> ai_score

## 运算符映射
- 大于/高于/超过 -> >
- 小于/低于 -> <
- 等于 -> ==
- 不低于 -> >=
- 不超过 -> <=

请仔细分析用户查询，准确识别意图和实体。"""

    def __init__(self, config: Optional[LLMConfig] = None):
        """
        初始化LLM意图解析器

        Args:
            config: LLM配置，如果为None则从环境变量读取
        """
        if config is None:
            config = self._load_config_from_env()

        self.config = config
        self.stock_db = get_stock_database()
        self._client = None

    def _load_config_from_env(self) -> LLMConfig:
        """从环境变量加载配置"""
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL_NAME", "gpt-4")
        base_url = os.getenv("OPENAI_API_BASE")

        if not api_key:
            logger.warning("未设置OPENAI_API_KEY环境变量")

        return LLMConfig(
            api_key=api_key,
            model=model,
            base_url=base_url
        )

    def _get_client(self):
        """获取OpenAI客户端"""
        if self._client is None:
            try:
                from openai import OpenAI

                if self.config.base_url:
                    self._client = OpenAI(
                        api_key=self.config.api_key,
                        base_url=self.config.base_url
                    )
                else:
                    self._client = OpenAI(api_key=self.config.api_key)

            except ImportError:
                logger.error("OpenAI库未安装，请运行: pip install openai")
                raise

        return self._client

    def parse(self, query: str, context: Optional[List[Dict]] = None) -> QueryIntent:
        """
        解析用户查询

        Args:
            query: 用户输入的自然语言查询
            context: 对话上下文（可选）

        Returns:
            QueryIntent: 解析后的查询意图
        """
        try:
            # 使用LLM解析
            llm_result = self._parse_with_llm(query, context)

            # 增强实体识别（使用股票数据库）
            llm_result = self._enhance_entities(llm_result, query)

            # 转换为QueryIntent
            return self._convert_to_query_intent(llm_result, query)

        except Exception as e:
            logger.error(f"LLM解析失败: {e}，降级到规则匹配")
            # 降级到规则匹配
            from .intent_parser import IntentParser
            parser = IntentParser()
            return parser.parse(query)

    def _parse_with_llm(self, query: str, context: Optional[List[Dict]] = None) -> Dict:
        """
        使用LLM解析查询

        Args:
            query: 用户查询
            context: 对话上下文

        Returns:
            Dict: LLM解析结果
        """
        client = self._get_client()

        # 构建消息
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]

        # 添加上下文
        if context:
            for msg in context[-3:]:  # 最多保留最近3轮对话
                messages.append(msg)

        # 添加当前查询
        messages.append({
            "role": "user",
            "content": f"请解析以下查询：\n{query}"
        })

        # 调用LLM
        response = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            response_format={"type": "json_object"}
        )

        # 解析响应
        result_text = response.choices[0].message.content
        result = json.loads(result_text)

        logger.info(f"LLM解析结果: {result}")
        return result

    def _enhance_entities(self, llm_result: Dict, query: str) -> Dict:
        """
        增强实体识别

        使用股票数据库增强股票名称识别

        Args:
            llm_result: LLM解析结果
            query: 原始查询

        Returns:
            Dict: 增强后的结果
        """
        entities = llm_result.get("entities", {})
        stock_names = entities.get("stock_names", [])
        stock_codes = entities.get("stock_codes", [])

        # 将股票名称转换为代码
        for name in stock_names:
            code = self.stock_db.get_code_by_name(name)
            if code and code not in stock_codes:
                stock_codes.append(code)

        # 搜索查询中可能包含的股票名称
        all_stocks = self.stock_db.get_all_stocks()
        for code, name in all_stocks.items():
            if name in query and code not in stock_codes:
                stock_codes.append(code)
                if name not in stock_names:
                    stock_names.append(name)

        entities["stock_codes"] = stock_codes
        entities["stock_names"] = stock_names
        llm_result["entities"] = entities

        return llm_result

    def _convert_to_query_intent(self, llm_result: Dict, original_query: str) -> QueryIntent:
        """
        将LLM结果转换为QueryIntent

        Args:
            llm_result: LLM解析结果
            original_query: 原始查询

        Returns:
            QueryIntent: 查询意图
        """
        # 解析意图类型
        intent_type_str = llm_result.get("intent_type", "unknown")
        try:
            intent_type = IntentType(intent_type_str)
        except ValueError:
            intent_type = IntentType.UNKNOWN

        # 提取实体
        entities = llm_result.get("entities", {})

        # 提取置信度
        confidence = llm_result.get("confidence", 0.8)

        # 标准化查询
        normalized_query = llm_result.get("normalized_query", original_query)

        return QueryIntent(
            intent_type=intent_type,
            confidence=confidence,
            entities=entities,
            original_query=original_query,
            normalized_query=normalized_query
        )


def parse_query_with_llm(query: str,
                         context: Optional[List[Dict]] = None,
                         config: Optional[LLMConfig] = None) -> QueryIntent:
    """
    便捷函数：使用LLM解析查询

    Args:
        query: 用户查询
        context: 对话上下文
        config: LLM配置

    Returns:
        QueryIntent: 查询意图
    """
    parser = LLMIntentParser(config)
    return parser.parse(query, context)
