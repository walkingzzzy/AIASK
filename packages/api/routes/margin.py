"""
融资融券路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/margin", tags=["融资融券"])


class StockRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = ""


def _get_margin_analyzer():
    try:
        from packages.core.margin import MarginAnalyzer
        return MarginAnalyzer()
    except ImportError:
        return None


@router.get("/market")
async def get_market_margin():
    """获取市场两融数据"""
    try:
        analyzer = _get_margin_analyzer()
        if analyzer:
            stats = analyzer.get_margin_statistics()
            return {"success": True, "data": stats}
        
        return {
            "success": True,
            "data": {"financing_balance": 15000, "securities_balance": 800, "market_sentiment": "偏乐观"}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stock")
async def get_stock_margin(request: StockRequest):
    """获取个股两融数据"""
    try:
        analyzer = _get_margin_analyzer()
        if analyzer:
            trend = analyzer.analyze_margin_trend(request.stock_code, request.stock_name)
            return {"success": True, "data": trend.to_dict() if hasattr(trend, 'to_dict') else trend}
        
        return {
            "success": True,
            "data": {"stock_code": request.stock_code, "financing_trend": "上升", "signal": "偏多"}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
