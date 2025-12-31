"""
洞察引擎数据模型
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class OpportunityType(str, Enum):
    """机会类型"""
    BUY_SIGNAL = "buy_signal"           # 买入信号
    SIMILAR_STOCK = "similar_stock"     # 相似股票推荐
    SECTOR_ROTATION = "sector_rotation" # 板块轮动
    BREAKOUT = "breakout"               # 突破形态
    OVERSOLD = "oversold"               # 超卖反弹
    FUND_INFLOW = "fund_inflow"         # 资金流入


class RiskType(str, Enum):
    """风险类型"""
    PRICE_DROP = "price_drop"           # 价格下跌
    VOLUME_ANOMALY = "volume_anomaly"   # 成交量异常
    NEWS_NEGATIVE = "news_negative"     # 负面新闻
    TECHNICAL_BREAKDOWN = "technical_breakdown"  # 技术破位
    FUND_OUTFLOW = "fund_outflow"       # 资金流出


class Urgency(str, Enum):
    """紧急程度"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(str, Enum):
    """严重程度"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class InsightType(str, Enum):
    """洞察类型"""
    MARKET_VIEW = "market_view"         # 市场观点
    STOCK_INSIGHT = "stock_insight"     # 个股洞察
    SECTOR_ANALYSIS = "sector_analysis" # 板块分析
    CORRELATION = "correlation"         # 关联分析
    TREND = "trend"                     # 趋势分析


@dataclass
class Opportunity:
    """投资机会"""
    id: str
    type: OpportunityType
    stock_code: str
    stock_name: str
    title: str
    reason: str
    confidence: float  # 0-1
    urgency: Urgency = Urgency.MEDIUM
    expected_return: Optional[float] = None
    detected_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['type'] = self.type.value
        result['urgency'] = self.urgency.value
        result['detected_at'] = self.detected_at.isoformat()
        if self.expires_at:
            result['expires_at'] = self.expires_at.isoformat()
        return result


@dataclass
class RiskAlert:
    """风险预警"""
    id: str
    type: RiskType
    stock_code: str
    stock_name: str
    title: str
    description: str
    severity: Severity
    suggested_action: str
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    detected_at: datetime = field(default_factory=datetime.now)
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['type'] = self.type.value
        result['severity'] = self.severity.value
        result['detected_at'] = self.detected_at.isoformat()
        return result


@dataclass
class Insight:
    """AI洞察"""
    id: str
    type: InsightType
    title: str
    content: str
    confidence: float  # 0-1
    stock_codes: List[str] = field(default_factory=list)
    supporting_data: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['type'] = self.type.value
        result['generated_at'] = self.generated_at.isoformat()
        return result


@dataclass
class UserProfile:
    """用户画像（简化版）"""
    user_id: str
    watchlist: List[str] = field(default_factory=list)
    holdings: List[str] = field(default_factory=list)
    investment_style: str = "balanced"  # conservative, balanced, aggressive
    risk_tolerance: int = 3  # 1-5
    focus_sectors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
