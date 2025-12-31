"""
研报数据模型
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ReportType(Enum):
    """研报类型"""
    COMPANY = "公司研报"
    INDUSTRY = "行业研报"
    STRATEGY = "策略研报"
    MACRO = "宏观研报"
    FIXED_INCOME = "固收研报"


class Rating(Enum):
    """评级"""
    STRONG_BUY = "强烈推荐"
    BUY = "推荐"
    HOLD = "中性"
    SELL = "减持"
    STRONG_SELL = "卖出"


@dataclass
class ResearchReport:
    """研报"""
    report_id: str
    title: str
    report_type: ReportType
    author: str
    institution: str
    publish_date: datetime
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    industry: Optional[str] = None
    rating: Optional[Rating] = None
    target_price: Optional[float] = None
    summary: str = ""
    content: str = ""
    tags: List[str] = None
    url: Optional[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "report_type": self.report_type.value,
            "author": self.author,
            "institution": self.institution,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "industry": self.industry,
            "rating": self.rating.value if self.rating else None,
            "target_price": self.target_price,
            "summary": self.summary,
            "tags": self.tags,
            "url": self.url
        }


@dataclass
class ReportSummary:
    """研报摘要统计"""
    total_count: int
    by_type: Dict[str, int]
    by_rating: Dict[str, int]
    recent_reports: List[ResearchReport]
    hot_stocks: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_count": self.total_count,
            "by_type": self.by_type,
            "by_rating": self.by_rating,
            "recent_reports": [r.to_dict() for r in self.recent_reports],
            "hot_stocks": self.hot_stocks
        }
