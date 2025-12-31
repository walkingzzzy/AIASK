"""
股票筛选路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/screener", tags=["股票筛选"])


class ScreeningRequest(BaseModel):
    conditions: Dict[str, Any]
    limit: int = 50


def _get_screener_service():
    try:
        from packages.core.services.stock_screener_service import StockScreenerService
        return StockScreenerService()
    except ImportError:
        return None


@router.post("/screen")
async def screen_stocks(request: ScreeningRequest):
    """股票筛选"""
    try:
        service = _get_screener_service()
        if service:
            results = service.screen(request.conditions, request.limit)
            return {"success": True, "data": results}
        return {
            "success": True,
            "data": [],
            "message": "筛选服务未加载"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def get_screening_strategies():
    """获取预设筛选策略"""
    return {
        "success": True,
        "data": [
            {
                "name": "低估值蓝筹",
                "description": "PE<15, PB<2, ROE>15%",
                "conditions": {"pe_max": 15, "pb_max": 2, "roe_min": 15}
            },
            {
                "name": "高成长",
                "description": "营收增长>30%, 净利润增长>30%",
                "conditions": {"revenue_growth_min": 30, "profit_growth_min": 30}
            },
            {
                "name": "强势股",
                "description": "近20日涨幅>20%, 成交量放大",
                "conditions": {"change_20d_min": 20, "volume_ratio_min": 1.5}
            },
            {
                "name": "超跌反弹",
                "description": "近20日跌幅>20%, RSI<30",
                "conditions": {"change_20d_max": -20, "rsi_max": 30}
            }
        ]
    }
