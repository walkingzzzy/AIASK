"""
情绪分析路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentiment", tags=["情绪分析"])


class StockRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = ""


def _get_sentiment_analyzer():
    try:
        from packages.core.sentiment import SentimentAnalyzer
        return SentimentAnalyzer()
    except ImportError:
        return None


@router.post("/stock")
async def get_stock_sentiment(request: StockRequest):
    """获取个股情绪分析"""
    try:
        analyzer = _get_sentiment_analyzer()
        if analyzer:
            result = analyzer.analyze_stock(request.stock_code, request.stock_name)
            return {"success": True, "data": result.to_dict() if hasattr(result, 'to_dict') else result}
        
        return {
            "success": True,
            "data": {
                "stock_code": request.stock_code,
                "overall_score": 0.3,
                "sentiment_level": "偏多",
                "news_count": 15
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market")
async def get_market_sentiment():
    """获取市场整体情绪"""
    try:
        analyzer = _get_sentiment_analyzer()
        if analyzer:
            result = analyzer.analyze_market()
            return {"success": True, "data": result}
        
        return {
            "success": True,
            "data": {
                "overall_sentiment": "偏乐观",
                "fear_greed_index": 65,
                "hot_topics": ["人工智能", "新能源", "半导体"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
