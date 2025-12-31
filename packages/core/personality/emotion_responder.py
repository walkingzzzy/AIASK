"""
情绪响应器
根据市场状况和用户情况生成情绪化响应
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

from .character_config import AICharacter, AI_CHARACTER

logger = logging.getLogger(__name__)


@dataclass
class EmotionContext:
    """情绪上下文"""
    market_change: float = 0.0          # 市场涨跌幅
    user_profit: float = 0.0            # 用户盈亏
    consecutive_days: int = 0           # 连续使用天数
    win_streak: int = 0                 # 连胜次数
    loss_streak: int = 0                # 连亏次数
    concepts_learned: int = 0           # 学习概念数
    days_since_last_visit: int = 0      # 距上次访问天数
    stock_name: Optional[str] = None    # 相关股票名称
    stock_code: Optional[str] = None    # 相关股票代码


class EmotionResponder:
    """
    情绪响应器
    
    功能：
    1. 检测需要情绪响应的场景
    2. 生成适当的情绪化响应
    3. 提供安慰、鼓励、提醒等情感支持
    """
    
    # 情绪触发阈值
    THRESHOLDS = {
        "market_crash": -3.0,           # 市场大跌
        "market_surge": 3.0,            # 市场大涨
        "user_big_profit": 10.0,        # 用户大赚
        "user_big_loss": -10.0,         # 用户大亏
        "win_streak": 3,                # 连胜
        "loss_streak": 3,               # 连亏
        "learning_milestone": 10,       # 学习里程碑
        "long_absence": 7,              # 长时间未访问
        "anniversary_days": [7, 30, 100, 365]  # 纪念日
    }
    
    def __init__(self, character: AICharacter = None):
        """
        初始化情绪响应器
        
        Args:
            character: AI人格配置
        """
        self.character = character or AI_CHARACTER
    
    def detect_emotion_triggers(self, context: EmotionContext) -> List[str]:
        """
        检测情绪触发器
        
        Args:
            context: 情绪上下文
            
        Returns:
            触发的情绪类型列表
        """
        triggers = []
        
        # 市场情绪
        if context.market_change <= self.THRESHOLDS["market_crash"]:
            triggers.append("market_crash")
        elif context.market_change >= self.THRESHOLDS["market_surge"]:
            triggers.append("market_surge")
        
        # 用户盈亏
        if context.user_profit >= self.THRESHOLDS["user_big_profit"]:
            triggers.append("user_profit")
        elif context.user_profit <= self.THRESHOLDS["user_big_loss"]:
            triggers.append("user_loss")
        
        # 连胜/连亏
        if context.win_streak >= self.THRESHOLDS["win_streak"]:
            triggers.append("consecutive_wins")
        elif context.loss_streak >= self.THRESHOLDS["loss_streak"]:
            triggers.append("consecutive_losses")
        
        # 学习里程碑
        if context.concepts_learned >= self.THRESHOLDS["learning_milestone"]:
            if context.concepts_learned % 10 == 0:  # 每10个概念
                triggers.append("learning_milestone")
        
        # 长时间未访问
        if context.days_since_last_visit >= self.THRESHOLDS["long_absence"]:
            triggers.append("long_absence")
        
        # 纪念日
        if context.consecutive_days in self.THRESHOLDS["anniversary_days"]:
            triggers.append("anniversary")
        
        return triggers
    
    def generate_response(self, trigger: str, context: EmotionContext) -> Optional[str]:
        """
        生成情绪响应
        
        Args:
            trigger: 触发类型
            context: 情绪上下文
            
        Returns:
            情绪响应文本
        """
        context_dict = self._context_to_dict(context)
        
        # 使用人格配置获取响应
        response = self.character.get_emotion_response(trigger, context_dict)
        
        if response:
            return response
        
        # 如果人格配置中没有，使用默认响应
        return self._get_default_response(trigger, context_dict)
    
    def generate_all_responses(self, context: EmotionContext) -> List[str]:
        """
        生成所有触发的情绪响应
        
        Args:
            context: 情绪上下文
            
        Returns:
            情绪响应列表
        """
        triggers = self.detect_emotion_triggers(context)
        responses = []
        
        for trigger in triggers:
            response = self.generate_response(trigger, context)
            if response:
                responses.append(response)
        
        return responses
    
    def get_comfort_message(self, loss_percent: float, stock_name: str = None) -> str:
        """
        获取安慰消息
        
        Args:
            loss_percent: 亏损百分比
            stock_name: 股票名称
            
        Returns:
            安慰消息
        """
        if loss_percent <= -20:
            severity = "severe"
        elif loss_percent <= -10:
            severity = "moderate"
        else:
            severity = "mild"
        
        messages = {
            "severe": [
                "投资路上难免有波折，重要的是从中学习。让我们一起分析原因，避免下次再犯同样的错误。",
                "亏损确实让人难受，但请记住，很多成功的投资者都经历过类似的挫折。关键是保持冷静，理性决策。",
                "这次的亏损是一次宝贵的经验。让我们复盘一下，看看哪里可以改进。"
            ],
            "moderate": [
                "市场波动是正常的，不必过于担心。让我们看看是否需要调整策略。",
                "短期的亏损不代表长期的失败。保持耐心，坚持您的投资逻辑。",
                "这个回撤在可接受范围内。让我们分析一下后续走势。"
            ],
            "mild": [
                "小幅波动很正常，不必太在意。",
                "市场有涨有跌，保持平常心。",
                "这点回撤不算什么，继续关注基本面。"
            ]
        }
        
        import random
        message = random.choice(messages[severity])
        
        if stock_name:
            message = f"关于{stock_name}，" + message
        
        return message
    
    def get_encouragement_message(self, achievement: str, context: Dict = None) -> str:
        """
        获取鼓励消息
        
        Args:
            achievement: 成就类型
            context: 上下文
            
        Returns:
            鼓励消息
        """
        context = context or {}
        
        messages = {
            "first_profit": [
                "恭喜您获得第一笔盈利！这是一个好的开始，继续保持！",
                "太棒了！第一次盈利的感觉一定很好。记住这个时刻，它证明您的分析是有效的。"
            ],
            "streak_milestone": [
                f"连续{context.get('days', 7)}天使用，您的坚持令人敬佩！",
                f"第{context.get('days', 7)}天打卡成功！坚持就是胜利！"
            ],
            "learning_progress": [
                f"您已经学习了{context.get('count', 10)}个投资概念，知识储备越来越丰富！",
                f"学习进度喜人！{context.get('count', 10)}个概念已掌握，您正在成为更专业的投资者。"
            ],
            "accuracy_improvement": [
                f"您的投资决策准确率提升了{context.get('improvement', 10)}%，进步明显！",
                "数据显示您的分析能力在稳步提升，继续保持！"
            ],
            "risk_control": [
                "您的风险控制做得很好，这是长期盈利的关键。",
                "看得出您很注重风险管理，这是成熟投资者的表现。"
            ]
        }
        
        import random
        return random.choice(messages.get(achievement, ["继续加油！"]))
    
    def get_warning_message(self, warning_type: str, context: Dict = None) -> str:
        """
        获取警示消息
        
        Args:
            warning_type: 警示类型
            context: 上下文
            
        Returns:
            警示消息
        """
        context = context or {}
        
        messages = {
            "overconfidence": [
                "连续盈利固然可喜，但请保持谨慎。市场永远存在不确定性。",
                "提醒您：过度自信是投资的大敌。保持冷静，理性决策。"
            ],
            "chasing_high": [
                "追高有风险，建议等待回调再考虑入场。",
                "股价已经涨了不少，此时追入风险较大，建议谨慎。"
            ],
            "panic_selling": [
                "市场下跌时容易恐慌，但往往这时候卖出是最差的选择。让我们冷静分析。",
                "恐慌性抛售往往会错过反弹机会。建议先冷静下来，再做决定。"
            ],
            "concentration_risk": [
                "您的持仓过于集中，建议适当分散投资以降低风险。",
                "单一股票仓位过重，风险较大。考虑分散一下？"
            ],
            "frequent_trading": [
                "频繁交易会增加成本，也容易受情绪影响。建议减少交易频率。",
                "最近交易有点频繁，手续费也是成本哦。"
            ]
        }
        
        import random
        return random.choice(messages.get(warning_type, ["请注意风险。"]))
    
    def _context_to_dict(self, context: EmotionContext) -> Dict[str, Any]:
        """将EmotionContext转换为字典"""
        return {
            "market_change": context.market_change,
            "profit_pct": abs(context.user_profit),
            "loss_pct": abs(context.user_profit),
            "streak": context.win_streak or context.loss_streak,
            "days": context.consecutive_days,
            "count": context.concepts_learned,
            "stock_name": context.stock_name or "该股票",
            "stock_code": context.stock_code or ""
        }
    
    def _get_default_response(self, trigger: str, context: Dict) -> Optional[str]:
        """获取默认响应"""
        defaults = {
            "market_crash": "市场波动较大，建议保持冷静，理性分析。",
            "market_surge": "市场表现强势，但也要注意风险。",
            "user_profit": f"恭喜盈利{context.get('profit_pct', 0):.1f}%！",
            "user_loss": "投资有风险，让我们一起分析原因。",
            "consecutive_wins": "连续判断正确，但请保持谨慎。",
            "consecutive_losses": "别灰心，让我们一起复盘改进。",
            "learning_milestone": "学习进步明显，继续加油！",
            "long_absence": "欢迎回来！让我为您更新最新情况。",
            "anniversary": f"我们已经相识{context.get('days', 0)}天了！"
        }
        
        return defaults.get(trigger)
