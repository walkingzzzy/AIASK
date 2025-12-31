"""
响应增强器
根据用户画像和上下文增强AI响应
"""
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .character_config import AICharacter, AI_CHARACTER, PersonalityStyle

logger = logging.getLogger(__name__)


class ResponseEnhancer:
    """
    响应增强器
    
    功能：
    1. 根据用户知识水平调整术语
    2. 添加情感化表达
    3. 添加个性化称呼
    4. 根据上下文添加合适的收尾
    5. 添加风险提示
    """
    
    # 专业术语及其通俗解释
    TERM_EXPLANATIONS = {
        "PE": "市盈率（股价/每股收益）",
        "PB": "市净率（股价/每股净资产）",
        "ROE": "净资产收益率",
        "MACD": "指数平滑异同移动平均线",
        "KDJ": "随机指标",
        "RSI": "相对强弱指标",
        "布林带": "BOLL指标，用于判断股价波动区间",
        "金叉": "短期均线上穿长期均线，通常是买入信号",
        "死叉": "短期均线下穿长期均线，通常是卖出信号",
        "放量": "成交量明显增加",
        "缩量": "成交量明显减少",
        "北向资金": "通过沪港通、深港通流入A股的境外资金",
        "主力资金": "大额资金，通常指机构投资者的资金",
        "换手率": "股票在一定时间内的交易频率",
        "市值": "公司股票的总价值",
        "龙头股": "板块中表现最强、最具代表性的股票",
        "回调": "股价上涨后的短期下跌",
        "反弹": "股价下跌后的短期上涨",
        "支撑位": "股价下跌时可能获得支撑的价位",
        "压力位": "股价上涨时可能遇到阻力的价位",
    }
    
    # 知识水平对应的术语处理方式
    KNOWLEDGE_LEVEL_CONFIG = {
        "beginner": {
            "explain_terms": True,
            "simplify_numbers": True,
            "add_examples": True,
            "max_complexity": 1
        },
        "intermediate": {
            "explain_terms": False,
            "simplify_numbers": False,
            "add_examples": False,
            "max_complexity": 2
        },
        "advanced": {
            "explain_terms": False,
            "simplify_numbers": False,
            "add_examples": False,
            "max_complexity": 3
        }
    }
    
    def __init__(self, character: AICharacter = None):
        """
        初始化响应增强器
        
        Args:
            character: AI人格配置
        """
        self.character = character or AI_CHARACTER
    
    def enhance(self, 
                response: str, 
                user_profile: Dict[str, Any] = None,
                context: Dict[str, Any] = None) -> str:
        """
        增强响应
        
        Args:
            response: 原始响应
            user_profile: 用户画像
            context: 上下文信息
            
        Returns:
            增强后的响应
        """
        user_profile = user_profile or {}
        context = context or {}
        
        enhanced = response
        
        # 1. 根据用户知识水平调整术语
        knowledge_level = user_profile.get('knowledge_level', 'intermediate')
        enhanced = self._adjust_terminology(enhanced, knowledge_level)
        
        # 2. 添加个性化称呼
        nickname = user_profile.get('nickname')
        ai_style = user_profile.get('ai_personality', 'professional')
        if nickname and ai_style == 'friendly':
            enhanced = self._add_personalized_prefix(enhanced, nickname, ai_style)
        
        # 3. 根据上下文添加情感化表达
        market_condition = context.get('market_condition')
        if market_condition:
            enhanced = self._add_empathetic_expression(enhanced, market_condition, ai_style)
        
        # 4. 添加风险提示（如果涉及投资建议）
        if self._contains_investment_advice(enhanced):
            enhanced = self._add_risk_warning(enhanced, ai_style)
        
        # 5. 根据风格添加收尾
        enhanced = self._add_contextual_ending(enhanced, ai_style, context)
        
        return enhanced
    
    def _adjust_terminology(self, text: str, knowledge_level: str) -> str:
        """根据知识水平调整术语"""
        config = self.KNOWLEDGE_LEVEL_CONFIG.get(knowledge_level, 
                                                  self.KNOWLEDGE_LEVEL_CONFIG["intermediate"])
        
        if not config.get("explain_terms"):
            return text
        
        # 为初学者添加术语解释
        for term, explanation in self.TERM_EXPLANATIONS.items():
            # 使用正则匹配完整词
            pattern = rf'\b{re.escape(term)}\b'
            if re.search(pattern, text):
                # 只在第一次出现时添加解释
                text = re.sub(pattern, f"{term}（{explanation}）", text, count=1)
        
        return text
    
    def _add_personalized_prefix(self, text: str, nickname: str, style: str) -> str:
        """添加个性化称呼"""
        prefix = self.character.get_style_expression(style, "prefix", {"nickname": nickname})
        
        if prefix and not text.startswith(prefix):
            return prefix + text
        
        return text
    
    def _add_empathetic_expression(self, text: str, market_condition: str, style: str) -> str:
        """添加情感化表达"""
        empathy_phrases = {
            "volatile": {
                "professional": "当前市场波动较大，",
                "friendly": "市场有点动荡，别担心，",
                "concise": ""
            },
            "bullish": {
                "professional": "市场情绪积极，",
                "friendly": "市场氛围不错呢，",
                "concise": ""
            },
            "bearish": {
                "professional": "市场情绪偏谨慎，",
                "friendly": "市场有点低迷，但机会总会有的，",
                "concise": ""
            }
        }
        
        phrase = empathy_phrases.get(market_condition, {}).get(style, "")
        
        if phrase and not text.startswith(phrase):
            return phrase + text
        
        return text
    
    def _contains_investment_advice(self, text: str) -> bool:
        """检查是否包含投资建议"""
        advice_keywords = [
            "建议买入", "建议卖出", "建议持有", "可以考虑",
            "推荐", "看好", "看空", "加仓", "减仓", "止损",
            "目标价", "预期收益", "投资机会"
        ]
        
        return any(keyword in text for keyword in advice_keywords)
    
    def _add_risk_warning(self, text: str, style: str) -> str:
        """添加风险提示"""
        warning = self.character.get_style_expression(style, "risk_warning")
        
        if warning and warning not in text:
            return text + "\n\n" + warning
        
        return text
    
    def _add_contextual_ending(self, text: str, style: str, context: Dict) -> str:
        """添加上下文相关的收尾"""
        suffix = self.character.get_style_expression(style, "suffix", context)
        
        if suffix and not text.endswith(suffix):
            return text + suffix
        
        return text
    
    def simplify_for_beginner(self, text: str) -> str:
        """为初学者简化内容"""
        # 简化数字表达
        text = self._simplify_numbers(text)
        
        # 添加术语解释
        text = self._adjust_terminology(text, "beginner")
        
        return text
    
    def _simplify_numbers(self, text: str) -> str:
        """简化数字表达"""
        # 将大数字转换为更易读的形式
        def simplify_large_number(match):
            num = float(match.group(0).replace(',', ''))
            if num >= 100000000:
                return f"{num/100000000:.2f}亿"
            elif num >= 10000:
                return f"{num/10000:.2f}万"
            return match.group(0)
        
        # 匹配大数字
        text = re.sub(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', simplify_large_number, text)
        
        return text
    
    def add_learning_tip(self, text: str, concept: str) -> str:
        """添加学习提示"""
        if concept in self.TERM_EXPLANATIONS:
            tip = f"\n\n💡 **小知识**：{concept}是{self.TERM_EXPLANATIONS[concept]}，是投资分析中常用的指标。"
            return text + tip
        return text
