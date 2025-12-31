"""公共Pydantic模型"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Generic, TypeVar
from datetime import datetime
import re

from packages.api.config import STOCK_CODE_PATTERN

T = TypeVar("T")


# ==================== 通用响应模型 ====================

class APIResponse(BaseModel, Generic[T]):
    """统一API响应格式"""
    success: bool = True
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    items: List[T]
    total: int
    page: int
    page_size: int
    has_more: bool


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==================== 股票相关模型 ====================

class StockCodeMixin(BaseModel):
    """股票代码验证混入"""
    stock_code: str

    @field_validator("stock_code")
    @classmethod
    def validate_stock_code(cls, v: str) -> str:
        if not re.match(STOCK_CODE_PATTERN, v):
            raise ValueError("股票代码格式无效，应为6位数字或6位数字.SH/.SZ")
        return v


class StockRequest(StockCodeMixin):
    """股票请求"""
    stock_name: Optional[str] = ""


class BatchStockRequest(BaseModel):
    """批量股票请求"""
    stock_codes: List[str]

    @field_validator("stock_codes")
    @classmethod
    def validate_codes(cls, v: List[str]) -> List[str]:
        pattern = re.compile(STOCK_CODE_PATTERN)
        invalid = [c for c in v if not pattern.match(c)]
        if invalid:
            raise ValueError(f"无效的股票代码: {', '.join(invalid)}")
        return v


# ==================== 分页参数 ====================

class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
