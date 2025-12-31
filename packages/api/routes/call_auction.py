"""
集合竞价分析路由
"""
from fastapi import APIRouter, HTTPException, Query
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/call-auction", tags=["集合竞价"])


def _get_auction_analyzer():
    try:
        from packages.core.call_auction.auction_analyzer import CallAuctionAnalyzer
        return CallAuctionAnalyzer()
    except ImportError:
        return None


@router.get("/ranking")
async def get_auction_ranking(top_n: int = Query(50, ge=10, le=200)):
    """获取竞价排行榜"""
    analyzer = _get_auction_analyzer()
    
    if not analyzer:
        raise HTTPException(status_code=503, detail="集合竞价分析模块未加载，请检查系统配置")

    try:
        ranking = analyzer.get_auction_ranking(top_n=top_n)
        return {
            "success": True,
            "data": {
                "change_ranking": [
                    {
                        "stock_code": s.stock_code, "stock_name": s.stock_name,
                        "price": s.price, "change_pct": s.change_pct,
                        "volume": s.volume, "volume_ratio": s.volume_ratio
                    }
                    for s in ranking["change_ranking"]
                ],
                "volume_ranking": [
                    {
                        "stock_code": s.stock_code, "stock_name": s.stock_name,
                        "volume": s.volume, "amount": s.amount
                    }
                    for s in ranking["volume_ranking"]
                ],
                "abnormal_stocks": [
                    {
                        "stock_code": s.stock_code, "stock_name": s.stock_name,
                        "change_pct": s.change_pct, "volume_ratio": s.volume_ratio,
                        "big_order_amount": s.big_order_amount
                    }
                    for s in ranking["abnormal_stocks"]
                ]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{stock_code}")
async def analyze_auction_stock(stock_code: str):
    """分析个股竞价情况"""
    analyzer = _get_auction_analyzer()
    
    if not analyzer:
        raise HTTPException(status_code=503, detail="集合竞价分析模块未加载，请检查系统配置")

    try:
        analysis = analyzer.analyze_auction_stock(stock_code)
        return {"success": True, "data": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
