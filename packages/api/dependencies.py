"""依赖注入函数"""
import asyncio
import re
import logging
from functools import lru_cache
from typing import Optional
from fastapi import Depends, HTTPException, Query, Request

from packages.api.config import (
    DATABASE_PATH, STOCK_CODE_PATTERN,
    AI_SCORE_RATE_LIMIT, AI_SCORE_RATE_WINDOW
)

logger = logging.getLogger(__name__)


# ==================== 数据库依赖 ====================

@lru_cache()
def get_user_db():
    """获取用户数据库实例（单例）"""
    from packages.core.data_layer.storage.user_data_db import UserDataDB
    return UserDataDB(DATABASE_PATH)


async def get_db_async():
    """异步获取数据库连接"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_user_db)


# ==================== 服务依赖 ====================

@lru_cache()
def get_stock_service():
    """获取股票数据服务（单例）"""
    try:
        from packages.core.services.stock_data_service import StockDataService
        return StockDataService()
    except ImportError:
        logger.warning("StockDataService 不可用")
        return None


@lru_cache()
def get_valuation_services():
    """获取估值服务（单例）"""
    try:
        from packages.core.valuation.valuation_summary import ValuationSummary
        from packages.core.valuation.dcf_model import DCFValuation
        from packages.core.valuation.ddm_model import DDMValuation
        from packages.core.valuation.peg_model import PEGValuation
        return {
            "summary": ValuationSummary(),
            "dcf": DCFValuation(),
            "ddm": DDMValuation(),
            "peg": PEGValuation()
        }
    except ImportError:
        logger.warning("估值服务不可用")
        return None


@lru_cache()
def get_insight_services():
    """获取洞察服务（单例）"""
    try:
        from packages.core.insight_engine import (
            OpportunityDetector, RiskDetector, InsightGenerator
        )
        return {
            "opportunity": OpportunityDetector(),
            "risk": RiskDetector(),
            "insight": InsightGenerator()
        }
    except ImportError:
        logger.warning("洞察服务不可用")
        return None


@lru_cache()
def get_profile_services():
    """获取用户画像服务（单例）"""
    try:
        from packages.core.user_profile import (
            ProfileService, BehaviorTracker, PreferenceLearner, RecommendationEngine
        )
        profile_service = ProfileService()
        behavior_tracker = BehaviorTracker(profile_service)
        return {
            "profile": profile_service,
            "behavior": behavior_tracker,
            "learner": PreferenceLearner(profile_service, behavior_tracker),
            "recommendation": RecommendationEngine(profile_service)
        }
    except ImportError:
        logger.warning("用户画像服务不可用")
        return None


# ==================== 参数验证依赖 ====================

def validate_stock_code(stock_code: str = Query(..., description="股票代码")) -> str:
    """验证股票代码格式"""
    if not re.match(STOCK_CODE_PATTERN, stock_code):
        raise HTTPException(status_code=400, detail="股票代码格式无效")
    return stock_code


def get_pagination(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量")
):
    """获取分页参数"""
    return {"page": page, "page_size": page_size, "offset": (page - 1) * page_size}


# ==================== 限流依赖 ====================

class EndpointRateLimiter:
    """端点级别限流器"""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict = {}
    
    async def __call__(self, request: Request):
        import time
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - self.window_seconds
        
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        
        self.requests[client_ip] = [t for t in self.requests[client_ip] if t > window_start]
        
        if len(self.requests[client_ip]) >= self.max_requests:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        
        self.requests[client_ip].append(now)


# AI评分专用限流器
ai_score_limiter = EndpointRateLimiter(AI_SCORE_RATE_LIMIT, AI_SCORE_RATE_WINDOW)
