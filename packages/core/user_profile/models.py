"""
用户画像数据模型
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class InvestmentStyle(str, Enum):
    """投资风格"""
    VALUE = "value"           # 价值投资
    GROWTH = "growth"         # 成长投资
    MOMENTUM = "momentum"     # 动量投资
    SWING = "swing"           # 波段交易
    QUANT = "quant"           # 量化投资


class KnowledgeLevel(str, Enum):
    """知识水平"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class DecisionSpeed(str, Enum):
    """决策速度"""
    FAST = "fast"
    DELIBERATE = "deliberate"


class BehaviorType(str, Enum):
    """行为类型"""
    QUERY = "query"                   # 查询
    STOCK_VIEW = "stock_view"         # 查看股票
    STOCK_ADD = "stock_add"           # 添加自选
    STOCK_REMOVE = "stock_remove"     # 移除自选
    AI_CHAT = "ai_chat"               # AI对话
    AI_FEEDBACK = "ai_feedback"       # AI反馈
    OPPORTUNITY_CLICK = "opportunity_click"  # 点击机会
    RISK_CLICK = "risk_click"         # 点击风险
    INSIGHT_VIEW = "insight_view"     # 查看洞察
    TRADE_DECISION = "trade_decision" # 交易决策
    PAGE_VIEW = "page_view"           # 页面浏览
    FEATURE_USE = "feature_use"       # 功能使用


@dataclass
class BehaviorEvent:
    """行为事件"""
    id: str
    user_id: str
    type: BehaviorType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    
    # 可选的上下文信息
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    page: Optional[str] = None
    session_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['type'] = self.type.value
        result['timestamp'] = self.timestamp.isoformat()
        return result


@dataclass
class QueryHistoryItem:
    """查询历史项"""
    query: str
    intent: str
    timestamp: datetime
    stock_codes: List[str] = field(default_factory=list)
    success: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'query': self.query,
            'intent': self.intent,
            'timestamp': self.timestamp.isoformat(),
            'stock_codes': self.stock_codes,
            'success': self.success
        }


@dataclass
class DecisionHistoryItem:
    """决策历史项"""
    stock_code: str
    stock_name: str
    action: str  # buy, sell, hold
    reason: str
    price_at_decision: float
    timestamp: datetime
    ai_suggested: bool = False
    outcome: Optional[str] = None  # profit, loss, pending
    profit_percent: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'stock_code': self.stock_code,
            'stock_name': self.stock_name,
            'action': self.action,
            'reason': self.reason,
            'price_at_decision': self.price_at_decision,
            'timestamp': self.timestamp.isoformat(),
            'ai_suggested': self.ai_suggested,
            'outcome': self.outcome,
            'profit_percent': self.profit_percent
        }


@dataclass
class LearningProgress:
    """学习进度"""
    learned_concepts: List[str] = field(default_factory=list)
    concepts_to_learn: List[str] = field(default_factory=list)
    quiz_scores: Dict[str, float] = field(default_factory=dict)
    total_learning_time: int = 0  # 分钟
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AIRelationship:
    """AI关系数据"""
    trust_level: float = 50.0           # 信任度 0-100
    suggestion_follow_rate: float = 0.0  # 建议采纳率
    total_suggestions: int = 0
    followed_suggestions: int = 0
    feedback_count: int = 0
    positive_feedback: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def update_follow_rate(self):
        if self.total_suggestions > 0:
            self.suggestion_follow_rate = self.followed_suggestions / self.total_suggestions


@dataclass
class UsageStats:
    """使用统计"""
    total_queries: int = 0
    total_sessions: int = 0
    total_time_minutes: int = 0
    consecutive_days: int = 0
    longest_streak: int = 0
    first_active_date: Optional[str] = None
    last_active_date: Optional[str] = None
    active_hours: List[int] = field(default_factory=list)  # 活跃时段
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserProfile:
    """完整用户画像"""
    user_id: str
    
    # === 基本偏好 ===
    investment_style: InvestmentStyle = InvestmentStyle.GROWTH
    risk_tolerance: int = 3  # 1-5, 1保守 5激进
    focus_sectors: List[str] = field(default_factory=list)
    avoided_sectors: List[str] = field(default_factory=list)
    preferred_market_cap: str = "all"  # large, mid, small, all
    
    # === 知识维度 ===
    knowledge_level: KnowledgeLevel = KnowledgeLevel.INTERMEDIATE
    learning_progress: LearningProgress = field(default_factory=LearningProgress)
    
    # === 时间维度 ===
    preferred_active_hours: List[int] = field(default_factory=lambda: [9, 10, 14, 15])
    preferred_report_time: str = "08:30"
    timezone: str = "Asia/Shanghai"
    
    # === 决策维度 ===
    decision_speed: DecisionSpeed = DecisionSpeed.DELIBERATE
    analysis_depth: str = "detailed"  # quick, detailed
    preferred_data_types: List[str] = field(default_factory=lambda: ["technical", "fundamental"])
    
    # === 历史数据 ===
    watchlist: List[str] = field(default_factory=list)
    holdings: List[str] = field(default_factory=list)
    query_history: List[QueryHistoryItem] = field(default_factory=list)
    decision_history: List[DecisionHistoryItem] = field(default_factory=list)
    
    # === 投资风格评分（用于学习） ===
    style_scores: Dict[str, float] = field(default_factory=lambda: {
        "value": 0, "growth": 0, "momentum": 0, "swing": 0, "quant": 0
    })
    
    # === AI关系 ===
    ai_relationship: AIRelationship = field(default_factory=AIRelationship)
    
    # === 使用统计 ===
    usage_stats: UsageStats = field(default_factory=UsageStats)
    
    # === 个性化设置 ===
    nickname: Optional[str] = None
    ai_personality: str = "professional"  # professional, friendly, concise
    notification_enabled: bool = True
    morning_brief_enabled: bool = True
    
    # === 元数据 ===
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'investment_style': self.investment_style.value,
            'risk_tolerance': self.risk_tolerance,
            'focus_sectors': self.focus_sectors,
            'avoided_sectors': self.avoided_sectors,
            'preferred_market_cap': self.preferred_market_cap,
            'knowledge_level': self.knowledge_level.value,
            'learning_progress': self.learning_progress.to_dict(),
            'preferred_active_hours': self.preferred_active_hours,
            'preferred_report_time': self.preferred_report_time,
            'timezone': self.timezone,
            'decision_speed': self.decision_speed.value,
            'analysis_depth': self.analysis_depth,
            'preferred_data_types': self.preferred_data_types,
            'watchlist': self.watchlist,
            'holdings': self.holdings,
            'query_history': [q.to_dict() for q in self.query_history[-50:]],  # 最近50条
            'decision_history': [d.to_dict() for d in self.decision_history[-50:]],
            'style_scores': self.style_scores,
            'ai_relationship': self.ai_relationship.to_dict(),
            'usage_stats': self.usage_stats.to_dict(),
            'nickname': self.nickname,
            'ai_personality': self.ai_personality,
            'notification_enabled': self.notification_enabled,
            'morning_brief_enabled': self.morning_brief_enabled,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        """从字典创建用户画像"""
        profile = cls(user_id=data.get('user_id', 'default'))
        
        if 'investment_style' in data:
            profile.investment_style = InvestmentStyle(data['investment_style'])
        if 'risk_tolerance' in data:
            profile.risk_tolerance = data['risk_tolerance']
        if 'focus_sectors' in data:
            profile.focus_sectors = data['focus_sectors']
        if 'avoided_sectors' in data:
            profile.avoided_sectors = data['avoided_sectors']
        if 'knowledge_level' in data:
            profile.knowledge_level = KnowledgeLevel(data['knowledge_level'])
        if 'decision_speed' in data:
            profile.decision_speed = DecisionSpeed(data['decision_speed'])
        if 'watchlist' in data:
            profile.watchlist = data['watchlist']
        if 'holdings' in data:
            profile.holdings = data['holdings']
        if 'nickname' in data:
            profile.nickname = data['nickname']
        if 'ai_personality' in data:
            profile.ai_personality = data['ai_personality']
            
        return profile
