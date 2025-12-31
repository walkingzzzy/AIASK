"""
LLM情绪分析器
使用大语言模型进行深度语义情绪分析
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging
import json
import asyncio
from enum import Enum

logger = logging.getLogger(__name__)


class SentimentIntensity(Enum):
    """情绪强度"""
    VERY_STRONG = "非常强烈"
    STRONG = "强烈"
    MODERATE = "中等"
    WEAK = "微弱"


@dataclass
class LLMSentimentResult:
    """LLM情绪分析结果"""
    text: str
    sentiment_score: float  # -1到1
    sentiment_label: str  # 看多/看空/中性
    intensity: str  # 情绪强度
    key_factors: List[str]  # 关键影响因素
    confidence: float  # 置信度
    reasoning: str  # 分析推理过程

    def to_dict(self) -> Dict:
        return {
            'sentiment_score': self.sentiment_score,
            'sentiment_label': self.sentiment_label,
            'intensity': self.intensity,
            'key_factors': self.key_factors,
            'confidence': self.confidence,
            'reasoning': self.reasoning
        }


class LLMSentimentAnalyzer:
    """
    LLM情绪分析器

    功能：
    1. 使用LLM进行深度语义分析
    2. 识别复杂情绪和隐含态度
    3. 提取关键影响因素
    4. 批量文本分析
    """

    def __init__(self, llm_client=None, model: str = "gpt-4"):
        """
        初始化LLM情绪分析器

        Args:
            llm_client: LLM客户端（OpenAI/Anthropic等）
            model: 模型名称
        """
        self.llm_client = llm_client
        self.model = model
        self._init_llm_client()

    def _init_llm_client(self):
        """初始化LLM客户端"""
        if self.llm_client is None:
            try:
                from openai import AsyncOpenAI
                import os
                api_key = os.getenv('OPENAI_API_KEY')
                if api_key:
                    self.llm_client = AsyncOpenAI(api_key=api_key)
                    logger.info("LLM客户端初始化成功")
                else:
                    logger.warning("未找到OPENAI_API_KEY，LLM情绪分析将不可用")
            except ImportError:
                logger.warning("未安装openai库，LLM情绪分析将不可用")

    def _build_sentiment_prompt(self, text: str) -> str:
        """构建情绪分析提示词"""
        prompt = f"""你是一位专业的股票市场情绪分析师。请分析以下文本的投资情绪。

文本内容：
{text}

请按照以下JSON格式返回分析结果：
{{
    "sentiment_score": <-1到1之间的浮点数，-1表示极度看空，0表示中性，1表示极度看多>,
    "sentiment_label": "<看多/看空/中性>",
    "intensity": "<非常强烈/强烈/中等/微弱>",
    "key_factors": [<影响情绪的关键因素列表>],
    "confidence": <0到1之间的置信度>,
    "reasoning": "<简要说明你的分析推理过程>"
}}

注意：
1. 考虑文本的语义、语气、上下文
2. 识别隐含的态度和情绪
3. 区分事实陈述和情绪表达
4. 评估信息的可信度和重要性
"""
        return prompt

    async def analyze_text(self, text: str) -> LLMSentimentResult:
        """
        分析单条文本的情绪

        Args:
            text: 文本内容

        Returns:
            LLMSentimentResult
        """
        if not self.llm_client:
            logger.warning("LLM客户端未初始化，返回默认结果")
            return self._get_default_result(text)

        try:
            prompt = self._build_sentiment_prompt(text)

            response = await self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的股票市场情绪分析师。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            content = response.choices[0].message.content
            result_dict = self._parse_llm_response(content)

            return LLMSentimentResult(
                text=text,
                sentiment_score=result_dict['sentiment_score'],
                sentiment_label=result_dict['sentiment_label'],
                intensity=result_dict['intensity'],
                key_factors=result_dict['key_factors'],
                confidence=result_dict['confidence'],
                reasoning=result_dict['reasoning']
            )

        except Exception as e:
            logger.error(f"LLM情绪分析失败: {e}")
            return self._get_default_result(text)

    async def analyze_batch(self, texts: List[str], max_concurrent: int = 5) -> List[LLMSentimentResult]:
        """
        批量分析文本情绪

        Args:
            texts: 文本列表
            max_concurrent: 最大并发数

        Returns:
            情绪分析结果列表
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_semaphore(text: str) -> LLMSentimentResult:
            async with semaphore:
                return await self.analyze_text(text)

        tasks = [analyze_with_semaphore(text) for text in texts]
        results = await asyncio.gather(*tasks)
        return results

    def _parse_llm_response(self, content: str) -> Dict:
        """解析LLM响应"""
        try:
            # 尝试提取JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                logger.warning("无法从LLM响应中提取JSON")
                return self._get_default_dict()
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return self._get_default_dict()

    def _get_default_result(self, text: str) -> LLMSentimentResult:
        """获取默认结果"""
        return LLMSentimentResult(
            text=text,
            sentiment_score=0.0,
            sentiment_label="中性",
            intensity="微弱",
            key_factors=[],
            confidence=0.3,
            reasoning="LLM分析不可用，返回默认结果"
        )

    def _get_default_dict(self) -> Dict:
        """获取默认字典"""
        return {
            'sentiment_score': 0.0,
            'sentiment_label': '中性',
            'intensity': '微弱',
            'key_factors': [],
            'confidence': 0.3,
            'reasoning': 'LLM分析失败'
        }

    def analyze_text_sync(self, text: str) -> LLMSentimentResult:
        """
        同步版本的情绪分析

        Args:
            text: 文本内容

        Returns:
            LLMSentimentResult
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，可以直接使用 asyncio.run
            return asyncio.run(self.analyze_text(text))
        else:
            # 已经在事件循环中，使用 run_coroutine_threadsafe
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.analyze_text(text))
                return future.result()

    def analyze_batch_sync(self, texts: List[str], max_concurrent: int = 5) -> List[LLMSentimentResult]:
        """
        同步版本的批量分析

        Args:
            texts: 文本列表
            max_concurrent: 最大并发数

        Returns:
            情绪分析结果列表
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.analyze_batch(texts, max_concurrent))
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.analyze_batch(texts, max_concurrent))
                return future.result()

