"""
龙虎榜路由
"""
import re
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime

from packages.api.config import STOCK_CODE_PATTERN

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dragon-tiger", tags=["龙虎榜"])


def validate_stock_code_optional(stock_code: Optional[str]) -> Optional[str]:
    """验证可选的股票代码"""
    if stock_code and not re.match(STOCK_CODE_PATTERN, stock_code):
        raise HTTPException(status_code=400, detail="股票代码格式无效")
    return stock_code


@router.get("")
async def get_dragon_tiger(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD"),
    type: str = Query("all", description="类型: all/buy/sell"),
    stock_code: Optional[str] = Query(None, description="股票代码筛选")
):
    """获取龙虎榜数据"""
    stock_code = validate_stock_code_optional(stock_code)
    try:
        try:
            import akshare as ak
            
            target_date = date.replace("-", "") if date else datetime.now().strftime("%Y%m%d")
            df = ak.stock_lhb_detail_em(date=target_date)
            
            if df is not None and not df.empty:
                result = df.to_dict(orient='records')
                if stock_code:
                    result = [r for r in result if r.get('代码', '').startswith(stock_code.split('.')[0])]
                return {"success": True, "data": result}
            return {"success": True, "data": []}
        except Exception as e:
            logger.warning(f"获取龙虎榜数据失败: {e}")
            return {
                "success": True,
                "data": [{
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "reason": "日涨幅偏离值达7%",
                    "buy_amount": 125000000,
                    "sell_amount": 98000000,
                    "net_amount": 27000000,
                    "date": date or datetime.now().strftime("%Y-%m-%d")
                }],
                "data_source": "mock"
            }
    except Exception as e:
        logger.error(f"获取龙虎榜失败: {e}")
        raise HTTPException(status_code=500, detail="获取龙虎榜数据失败")
