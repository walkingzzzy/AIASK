"""
偏好学习器
从用户行为中学习投资偏好
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from .models import (
    UserProfile, BehaviorEvent, BehaviorType,
    InvestmentStyle, KnowledgeLevel, DecisionSpeed
)
from .profile_service import ProfileService
from .behavior_tracker import BehaviorTracker

logger = logging.getLogger(__name__)


class PreferenceLearner:
    """
    偏好学习器
    
    功能：
    1. 从查询中学习关注点
    2. 从浏览中学习偏好板块
    3. 从决策中学习投资风格
    4. 从反馈中调整推荐
    """
    
    # 板块关键词映射
    SECTOR_KEYWORDS = {
        "科技": ["科技", "芯片", "半导体", "软件", "互联网", "AI", "人工智能", "云计算"],
        "消费": ["消费", "白酒", "食品", "饮料", "零售", "家电", "服装"],
        "医药": ["医药", "医疗", "生物", "疫苗", "创新药", "医疗器械"],
        "新能源": ["新能源", "光伏", "锂电", "储能", "风电", "电动车"],
        "金融": ["金融", "银行", "保险", "券商", "证券"],
        "地产": ["地产", "房地产", "物业"],
        "制造": ["制造", "机械", "汽车", "军工", "航空"],
    }
    
    # 投资风格特征
    STYLE_FEATURES = {
        InvestmentStyle.VALUE: {
            "keywords": ["价值", "低估", "PE", "PB", "股息", "分红", "基本面"],
            "holding_days_min": 30,
            "analysis_depth": "detailed"
        },
        InvestmentStyle.GROWTH: {
            "keywords": ["成长", "增长", "营收", "利润", "高增长", "赛道"],
            "holding_days_min": 14,
            "analysis_depth": "detailed"
        },
        InvestmentStyle.MOMENTUM: {
            "keywords": ["趋势", "动量", "突破", "新高", "强势"],
            "holding_days_min": 7,
            "analysis_depth": "quick"
        },
        InvestmentStyle.SWING: {
            "keywords": ["波段", "短线", "反弹", "超跌", "技术"],
            "holding_days_max": 7,
            "analysis_depth": "quick"
        },
        InvestmentStyle.QUANT: {
            "keywords": ["量化", "因子", "回测", "策略", "模型"],
            "analysis_depth": "detailed"
        }
    }
    
    def __init__(self, 
                 profile_service: ProfileService = None,
                 behavior_tracker: BehaviorTracker = None):
        """
        初始化偏好学习器
        
        Args:
            profile_service: 用户画像服务
            behavior_tracker: 行为追踪器
        """
        self.profile_service = profile_service or ProfileService()
        self.behavior_tracker = behavior_tracker or BehaviorTracker(self.profile_service)
    
    def learn_from_events(self, user_id: str, 
                          events: List[BehaviorEvent] = None) -> UserProfile:
        """
        从行为事件中学习偏好
        
        Args:
            user_id: 用户ID
            events: 行为事件列表（可选，默认获取最近事件）
            
        Returns:
            更新后的用户画像
        """
        if events is None:
            events = self.behavior_tracker.get_recent_events(user_id, hours=168)  # 7天
        
        profile = self.profile_service.get_profile(user_id)
        
        for event in events:
            if event.type == BehaviorType.QUERY:
                self._learn_from_query(profile, event)
            elif event.type == BehaviorType.STOCK_VIEW:
                self._learn_from_stock_view(profile, event)
            elif event.type == BehaviorType.TRADE_DECISION:
                self._learn_from_decision(profile, event)
            elif event.type == BehaviorType.AI_FEEDBACK:
                self._learn_from_feedback(profile, event)
            elif event.type == BehaviorType.OPPORTUNITY_CLICK:
                self._learn_from_opportunity_click(profile, event)
        
        # 更新投资风格
        self._update_investment_style(profile)
        
        # 更新知识水平
        self._update_knowledge_level(profile)
        
        self.profile_service.save_profile(profile)
        return profile
    
    def _learn_from_query(self, profile: UserProfile, event: BehaviorEvent):
        """从查询中学习"""
        query = event.data.get('query', '').lower()
        intent = event.data.get('intent', '')
        
        # 学习关注板块
        for sector, keywords in self.SECTOR_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                if sector not in profile.focus_sectors:
                    profile.focus_sectors.append(sector)
                    # 限制数量
                    if len(profile.focus_sectors) > 5:
                        profile.focus_sectors = profile.focus_sectors[-5:]
        
        # 学习投资风格
        for style, features in self.STYLE_FEATURES.items():
            if any(kw in query for kw in features['keywords']):
                profile.style_scores[style.value] = profile.style_scores.get(style.value, 0) + 1
        
        # 学习分析深度偏好
        if any(kw in query for kw in ['详细', '深入', '全面', '分析']):
            profile.analysis_depth = 'detailed'
        elif any(kw in query for kw in ['简单', '快速', '概要', '简述']):
            profile.analysis_depth = 'quick'
    
    def _learn_from_stock_view(self, profile: UserProfile, event: BehaviorEvent):
        """从股票浏览中学习"""
        stock_code = event.stock_code
        if not stock_code:
            return
        
        # 获取股票所属板块（这里简化处理，实际应该查询股票信息）
        sector = self._get_stock_sector(stock_code)
        if sector and sector not in profile.focus_sectors:
            # 如果多次浏览同一板块的股票，添加到关注板块
            profile.focus_sectors.append(sector)
            if len(profile.focus_sectors) > 5:
                profile.focus_sectors = profile.focus_sectors[-5:]
    
    def _learn_from_decision(self, profile: UserProfile, event: BehaviorEvent):
        """从交易决策中学习投资风格"""
        action = event.data.get('action', '')
        
        # 分析持仓周期（需要配合历史数据）
        # 这里简化处理，根据决策频率推断
        
        if action in ['buy', 'sell']:
            # 频繁交易 -> 波段/动量风格
            recent_decisions = [
                e for e in self.behavior_tracker.get_recent_events(
                    profile.user_id, 
                    event_type=BehaviorType.TRADE_DECISION,
                    hours=168
                )
            ]
            
            if len(recent_decisions) > 10:  # 一周超过10次决策
                profile.style_scores['swing'] = profile.style_scores.get('swing', 0) + 2
                profile.decision_speed = DecisionSpeed.FAST
            elif len(recent_decisions) < 3:  # 一周少于3次决策
                profile.style_scores['value'] = profile.style_scores.get('value', 0) + 1
                profile.decision_speed = DecisionSpeed.DELIBERATE
    
    def _learn_from_feedback(self, profile: UserProfile, event: BehaviorEvent):
        """从反馈中学习"""
        is_positive = event.data.get('is_positive', False)
        context = event.data.get('context', {})
        
        # 如果用户对某类建议给出正面反馈，增加相关偏好权重
        suggestion_type = context.get('suggestion_type', '')
        
        if is_positive:
            if 'technical' in suggestion_type:
                if 'technical' not in profile.preferred_data_types:
                    profile.preferred_data_types.append('technical')
            elif 'fundamental' in suggestion_type:
                if 'fundamental' not in profile.preferred_data_types:
                    profile.preferred_data_types.append('fundamental')
    
    def _learn_from_opportunity_click(self, profile: UserProfile, event: BehaviorEvent):
        """从机会点击中学习"""
        opportunity_type = event.data.get('type', '')
        
        # 根据点击的机会类型调整风格评分
        type_style_map = {
            'buy_signal': 'momentum',
            'similar_stock': 'growth',
            'sector_rotation': 'momentum',
            'breakout': 'swing',
            'oversold': 'swing',
            'fund_inflow': 'momentum'
        }
        
        if opportunity_type in type_style_map:
            style = type_style_map[opportunity_type]
            profile.style_scores[style] = profile.style_scores.get(style, 0) + 0.5
    
    def _update_investment_style(self, profile: UserProfile):
        """更新投资风格"""
        if not profile.style_scores:
            return
        
        # 选择得分最高的风格
        top_style = max(profile.style_scores.items(), key=lambda x: x[1])
        
        if top_style[1] > 3:  # 需要足够的数据支持
            try:
                profile.investment_style = InvestmentStyle(top_style[0])
            except ValueError:
                pass
    
    def _update_knowledge_level(self, profile: UserProfile):
        """更新知识水平"""
        # 基于查询复杂度和学习进度评估
        learned_count = len(profile.learning_progress.learned_concepts)
        query_count = profile.usage_stats.total_queries
        
        if learned_count > 20 or query_count > 500:
            profile.knowledge_level = KnowledgeLevel.ADVANCED
        elif learned_count > 5 or query_count > 100:
            profile.knowledge_level = KnowledgeLevel.INTERMEDIATE
        else:
            profile.knowledge_level = KnowledgeLevel.BEGINNER
    
    def _get_stock_sector(self, stock_code: str) -> Optional[str]:
        """获取股票所属板块（简化实现）"""
        # 实际应该查询股票信息服务
        # 这里根据股票代码前缀简单判断
        sector_map = {
            '600': '金融',  # 上证主板
            '601': '金融',
            '603': '制造',
            '688': '科技',  # 科创板
            '000': '消费',  # 深证主板
            '002': '制造',  # 中小板
            '300': '科技',  # 创业板
        }
        
        prefix = stock_code[:3]
        return sector_map.get(prefix)
    
    def get_learning_insights(self, user_id: str) -> Dict[str, Any]:
        """
        获取学习洞察
        
        Args:
            user_id: 用户ID
            
        Returns:
            学习洞察
        """
        profile = self.profile_service.get_profile(user_id)
        
        return {
            'investment_style': {
                'current': profile.investment_style.value,
                'scores': profile.style_scores,
                'confidence': self._calculate_style_confidence(profile)
            },
            'focus_sectors': profile.focus_sectors,
            'knowledge_level': profile.knowledge_level.value,
            'decision_speed': profile.decision_speed.value,
            'analysis_depth': profile.analysis_depth,
            'preferred_data_types': profile.preferred_data_types,
            'ai_trust_level': profile.ai_relationship.trust_level,
            'suggestion_follow_rate': profile.ai_relationship.suggestion_follow_rate
        }
    
    def _calculate_style_confidence(self, profile: UserProfile) -> float:
        """计算风格判断的置信度"""
        if not profile.style_scores:
            return 0.0
        
        total = sum(profile.style_scores.values())
        if total == 0:
            return 0.0
        
        top_score = max(profile.style_scores.values())
        return min(1.0, top_score / total * 2)  # 归一化到0-1
