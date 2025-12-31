"""
记忆叙述者
基于用户历史数据生成个性化的记忆叙述
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

from .character_config import AICharacter, AI_CHARACTER

logger = logging.getLogger(__name__)


@dataclass
class MemoryData:
    """记忆数据"""
    user_id: str
    first_active_date: Optional[str] = None
    total_days: int = 0
    total_queries: int = 0
    total_stocks_analyzed: int = 0
    concepts_learned: int = 0
    
    # 重要时刻
    first_profit_stock: Optional[str] = None
    first_profit_date: Optional[str] = None
    first_profit_percent: float = 0.0
    
    biggest_win_stock: Optional[str] = None
    biggest_win_percent: float = 0.0
    
    most_analyzed_stock: Optional[str] = None
    most_analyzed_count: int = 0
    
    # 进步数据
    accuracy_improvement: float = 0.0
    initial_accuracy: float = 0.0
    current_accuracy: float = 0.0


class MemoryNarrator:
    """
    记忆叙述者
    
    功能：
    1. 生成共同经历叙述
    2. 生成学习进步叙述
    3. 生成纪念日叙述
    4. 生成里程碑叙述
    """
    
    def __init__(self, character: AICharacter = None):
        """
        初始化记忆叙述者
        
        Args:
            character: AI人格配置
        """
        self.character = character or AI_CHARACTER
    
    def generate_shared_experience(self, memory: MemoryData) -> Optional[str]:
        """
        生成共同经历叙述
        
        Args:
            memory: 记忆数据
            
        Returns:
            叙述文本
        """
        narratives = []
        
        # 第一次盈利的记忆
        if memory.first_profit_stock and memory.first_profit_date:
            narratives.append(
                f"还记得{memory.first_profit_date}，您在{memory.first_profit_stock}上"
                f"获得了第一笔盈利（{memory.first_profit_percent:.1f}%）吗？那是个美好的开始！"
            )
        
        # 最大收益的记忆
        if memory.biggest_win_stock and memory.biggest_win_percent > 10:
            narratives.append(
                f"印象最深的是{memory.biggest_win_stock}那次，"
                f"收益达到了{memory.biggest_win_percent:.1f}%，您的分析很准确！"
            )
        
        # 最常分析的股票
        if memory.most_analyzed_stock and memory.most_analyzed_count > 10:
            narratives.append(
                f"您对{memory.most_analyzed_stock}情有独钟，"
                f"我们一起分析了{memory.most_analyzed_count}次。"
            )
        
        if narratives:
            import random
            return random.choice(narratives)
        
        return None
    
    def generate_learning_progress(self, memory: MemoryData) -> Optional[str]:
        """
        生成学习进步叙述
        
        Args:
            memory: 记忆数据
            
        Returns:
            叙述文本
        """
        narratives = []
        
        # 概念学习进度
        if memory.concepts_learned > 0:
            narratives.append(
                f"您已经学习了{memory.concepts_learned}个投资概念，"
                f"知识储备越来越丰富了！"
            )
        
        # 准确率提升
        if memory.accuracy_improvement > 5:
            narratives.append(
                f"对比最初，您的投资决策准确率提升了{memory.accuracy_improvement:.1f}%，"
                f"从{memory.initial_accuracy:.1f}%提升到了{memory.current_accuracy:.1f}%，进步明显！"
            )
        
        # 分析数量
        if memory.total_stocks_analyzed > 50:
            narratives.append(
                f"我们一起分析了{memory.total_stocks_analyzed}只股票，"
                f"您的分析经验越来越丰富了。"
            )
        
        # 查询数量
        if memory.total_queries > 100:
            narratives.append(
                f"您已经向我提问了{memory.total_queries}次，"
                f"每一次交流都让我更了解您的投资风格。"
            )
        
        if narratives:
            import random
            return random.choice(narratives)
        
        return None
    
    def generate_anniversary_narrative(self, memory: MemoryData) -> Optional[str]:
        """
        生成纪念日叙述
        
        Args:
            memory: 记忆数据
            
        Returns:
            叙述文本
        """
        if memory.total_days <= 0:
            return None
        
        # 特殊纪念日
        special_days = {
            7: "一周",
            30: "一个月",
            100: "100天",
            365: "一年"
        }
        
        for days, label in special_days.items():
            if memory.total_days == days:
                return self._generate_anniversary_message(memory, days, label)
        
        # 普通纪念日（每30天）
        if memory.total_days > 0 and memory.total_days % 30 == 0:
            months = memory.total_days // 30
            return self._generate_anniversary_message(memory, memory.total_days, f"{months}个月")
        
        return None
    
    def _generate_anniversary_message(self, memory: MemoryData, days: int, label: str) -> str:
        """生成纪念日消息"""
        messages = [
            f"🎉 今天是我们相识{label}的日子！",
            f"时间过得真快，我们已经一起走过了{label}。",
            f"不知不觉，{label}过去了，感谢您的陪伴！"
        ]
        
        import random
        base_message = random.choice(messages)
        
        # 添加统计信息
        stats = []
        if memory.total_queries > 0:
            stats.append(f"交流了{memory.total_queries}次")
        if memory.total_stocks_analyzed > 0:
            stats.append(f"分析了{memory.total_stocks_analyzed}只股票")
        if memory.concepts_learned > 0:
            stats.append(f"学习了{memory.concepts_learned}个概念")
        
        if stats:
            base_message += f"\n\n在这段时间里，我们{', '.join(stats)}。"
        
        base_message += "\n\n期待继续陪伴您的投资之旅！"
        
        return base_message
    
    def generate_milestone_narrative(self, milestone_type: str, 
                                      context: Dict[str, Any]) -> Optional[str]:
        """
        生成里程碑叙述
        
        Args:
            milestone_type: 里程碑类型
            context: 上下文
            
        Returns:
            叙述文本
        """
        milestones = {
            "first_query": "这是您的第一次提问，欢迎开始投资学习之旅！",
            "query_100": f"恭喜！您已经提问了100次，求知欲真强！",
            "query_500": f"500次提问达成！您是我最勤奋的学生之一。",
            "query_1000": f"1000次提问！您对投资的热情令人敬佩。",
            "stock_10": "您已经分析了10只股票，视野在逐渐扩大。",
            "stock_50": "50只股票分析完成，您的选股范围越来越广了。",
            "stock_100": "100只股票！您已经是经验丰富的分析师了。",
            "concept_10": "10个投资概念已掌握，基础知识越来越扎实。",
            "concept_30": "30个概念！您的投资知识体系正在形成。",
            "concept_50": "50个概念达成！您已经具备了专业投资者的知识储备。",
            "streak_7": "连续7天使用，坚持就是胜利！",
            "streak_30": "连续30天！您的毅力令人敬佩。",
            "streak_100": "100天连续使用！这份坚持一定会带来回报。",
            "first_profit": f"恭喜获得第一笔盈利！这是一个美好的开始。",
            "profit_10": "累计盈利10次，您的投资能力在稳步提升。",
            "accuracy_60": "决策准确率突破60%，您已经超过了大多数投资者。",
            "accuracy_70": "70%准确率！这是专业投资者的水平。"
        }
        
        return milestones.get(milestone_type)
    
    def generate_personalized_greeting(self, memory: MemoryData, 
                                        current_context: Dict = None) -> str:
        """
        生成个性化问候
        
        Args:
            memory: 记忆数据
            current_context: 当前上下文
            
        Returns:
            个性化问候
        """
        current_context = current_context or {}
        
        # 基础问候
        greeting = self.character.get_greeting({
            'consecutive_days': memory.total_days,
            'days_absent': current_context.get('days_absent', 0)
        })
        
        # 添加个性化内容
        additions = []
        
        # 纪念日
        anniversary = self.generate_anniversary_narrative(memory)
        if anniversary:
            additions.append(anniversary)
        
        # 学习进步
        if memory.total_days > 0 and memory.total_days % 7 == 0:
            progress = self.generate_learning_progress(memory)
            if progress:
                additions.append(progress)
        
        # 共同经历（偶尔提及）
        import random
        if random.random() < 0.1:  # 10%概率
            experience = self.generate_shared_experience(memory)
            if experience:
                additions.append(experience)
        
        if additions:
            greeting += "\n\n" + "\n\n".join(additions)
        
        return greeting
    
    def get_memory_summary(self, memory: MemoryData) -> Dict[str, Any]:
        """
        获取记忆摘要
        
        Args:
            memory: 记忆数据
            
        Returns:
            记忆摘要
        """
        return {
            "relationship_days": memory.total_days,
            "total_interactions": memory.total_queries,
            "stocks_analyzed": memory.total_stocks_analyzed,
            "concepts_learned": memory.concepts_learned,
            "highlights": {
                "first_profit": {
                    "stock": memory.first_profit_stock,
                    "date": memory.first_profit_date,
                    "percent": memory.first_profit_percent
                } if memory.first_profit_stock else None,
                "biggest_win": {
                    "stock": memory.biggest_win_stock,
                    "percent": memory.biggest_win_percent
                } if memory.biggest_win_stock else None,
                "favorite_stock": {
                    "stock": memory.most_analyzed_stock,
                    "count": memory.most_analyzed_count
                } if memory.most_analyzed_stock else None
            },
            "progress": {
                "accuracy_improvement": memory.accuracy_improvement,
                "initial_accuracy": memory.initial_accuracy,
                "current_accuracy": memory.current_accuracy
            }
        }
