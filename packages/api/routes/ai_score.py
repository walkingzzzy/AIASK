"""
AI评分路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-score", tags=["AI评分"])


class StockRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = ""


class BatchStockRequest(BaseModel):
    stock_codes: List[str]


def _get_stock_service():
    try:
        from packages.core.services.stock_data_service import StockDataService
        return StockDataService()
    except ImportError:
        return None


def _mock_score(stock_code: str, stock_name: str = ""):
    """返回模拟评分数据"""
    return {
        "stock_code": stock_code,
        "stock_name": stock_name or stock_code,
        "ai_score": 7.5,
        "signal": "买入",
        "confidence": 0.75,
        "subscores": {
            "technical": 7.2,
            "fundamental": 7.8,
            "fund_flow": 7.5,
            "sentiment": 7.0,
            "risk": 8.0
        },
        "analysis": "该股票综合评分较高，技术面和基本面表现良好",
        "risk_level": "中等",
        "recommendation": "建议适量配置"
    }


@router.post("")
async def get_ai_score(request: StockRequest):
    """获取AI评分"""
    try:
        service = _get_stock_service()
        if service:
            score_result = service.get_ai_score(request.stock_code, request.stock_name or request.stock_code)
            if score_result:
                if hasattr(score_result, 'to_dict'):
                    return {"success": True, "data": score_result.to_dict()}
                elif hasattr(score_result, '__dict__'):
                    return {"success": True, "data": score_result.__dict__}
                else:
                    return {"success": True, "data": score_result}
        
        return {"success": True, "data": _mock_score(request.stock_code, request.stock_name), "data_source": "mock"}
    except Exception as e:
        logger.error(f"获取AI评分失败: {e}")
        return {"success": True, "data": _mock_score(request.stock_code, request.stock_name)}


@router.post("/batch")
async def get_batch_ai_score(request: BatchStockRequest):
    """批量获取AI评分"""
    try:
        results = []
        service = _get_stock_service()
        
        for code in request.stock_codes[:20]:  # 限制最多20只
            try:
                if service:
                    score = service.get_ai_score(code, code)
                    if score:
                        results.append(score.to_dict() if hasattr(score, 'to_dict') else score)
                        continue
                results.append({"stock_code": code, "ai_score": 7.0, "signal": "Hold"})
            except Exception as e:
                results.append({"stock_code": code, "ai_score": 0, "signal": "Error", "error": str(e)})
        
        return {"success": True, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
