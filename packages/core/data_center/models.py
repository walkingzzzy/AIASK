"""
数据中心数据模型
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DataCategory(Enum):
    """数据类别"""
    MARKET = "市场行情"
    FINANCIAL = "财务数据"
    FUND_FLOW = "资金流向"
    TECHNICAL = "技术指标"
    SENTIMENT = "市场情绪"
    RESEARCH = "研报数据"


class ExportFormat(Enum):
    """导出格式"""
    CSV = "csv"
    EXCEL = "xlsx"
    JSON = "json"


@dataclass
class DataQuery:
    """数据查询请求"""
    category: DataCategory
    stock_codes: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    fields: Optional[List[str]] = None
    limit: int = 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "stock_codes": self.stock_codes,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "fields": self.fields,
            "limit": self.limit
        }


@dataclass
class DataExport:
    """数据导出任务"""
    export_id: str
    query: DataQuery
    format: ExportFormat
    status: str
    file_path: Optional[str] = None
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "export_id": self.export_id,
            "query": self.query.to_dict(),
            "format": self.format.value,
            "status": self.status,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message
        }


@dataclass
class DataStatistics:
    """数据统计"""
    category: DataCategory
    total_records: int
    date_range: Dict[str, str]
    stock_count: int
    last_update: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "total_records": self.total_records,
            "date_range": self.date_range,
            "stock_count": self.stock_count,
            "last_update": self.last_update.isoformat() if self.last_update else None
        }
