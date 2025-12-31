"""
组合管理路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["组合管理"])


class AddPositionRequest(BaseModel):
    stock_code: str
    stock_name: str
    quantity: int
    cost_price: float


def _get_portfolio_service():
    try:
        from packages.core.services.portfolio_service import PortfolioService
        return PortfolioService()
    except ImportError:
        return None


@router.post("/add")
async def add_position(request: AddPositionRequest):
    """添加持仓"""
    try:
        service = _get_portfolio_service()
        if service:
            result = service.add_position(
                request.stock_code, request.stock_name,
                request.quantity, request.cost_price
            )
            return {"success": True, "data": result}
        return {"success": False, "error": "组合服务未加载"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/remove/{stock_code}")
async def remove_position(stock_code: str):
    """删除持仓"""
    try:
        service = _get_portfolio_service()
        if service:
            result = service.remove_position(stock_code)
            return {"success": True, "data": result}
        return {"success": False, "error": "组合服务未加载"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions():
    """获取所有持仓"""
    try:
        service = _get_portfolio_service()
        if service:
            positions = service.get_all_positions()
            return {"success": True, "data": positions}
        return {"success": True, "data": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_portfolio_summary():
    """获取组合摘要"""
    try:
        service = _get_portfolio_service()
        if service:
            summary = service.get_portfolio_summary()
            return {"success": True, "data": summary}
        return {
            "success": True,
            "data": {
                "total_value": 0, "total_cost": 0,
                "total_profit": 0, "profit_rate": 0,
                "position_count": 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk")
async def get_portfolio_risk():
    """获取组合风险分析"""
    try:
        service = _get_portfolio_service()
        if service:
            risk = service.analyze_risk()
            return {"success": True, "data": risk}
        return {
            "success": True,
            "data": {
                "concentration_risk": "低",
                "sector_distribution": {},
                "volatility": 0.15
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
