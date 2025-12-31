"""
数据中心路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-center", tags=["数据中心"])


class DataQueryRequest(BaseModel):
    category: str
    fields: List[str]
    filters: Optional[Dict[str, Any]] = None
    limit: int = 100


class ExportRequest(BaseModel):
    category: str
    fields: List[str]
    format: str = "csv"
    filters: Optional[Dict[str, Any]] = None


def _get_data_manager():
    try:
        from packages.core.data_center import DataManager
        return DataManager()
    except ImportError:
        return None


@router.get("/categories")
async def get_data_categories():
    """获取数据类别"""
    return {
        "success": True,
        "data": [
            {"id": "stock_basic", "name": "股票基础数据", "description": "股票代码、名称、行业等"},
            {"id": "daily_quote", "name": "日线行情", "description": "开高低收、成交量等"},
            {"id": "financial", "name": "财务数据", "description": "财务报表、财务指标"},
            {"id": "valuation", "name": "估值数据", "description": "PE、PB、PS等估值指标"}
        ]
    }


@router.get("/statistics")
async def get_data_statistics():
    """获取数据统计"""
    try:
        manager = _get_data_manager()
        if manager:
            stats = manager.get_statistics()
            return {"success": True, "data": stats}
        return {
            "success": True,
            "data": {
                "total_stocks": 5000,
                "data_start_date": "2015-01-01",
                "last_update": "2024-01-01"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fields/{category}")
async def get_category_fields(category: str):
    """获取数据类别的可用字段"""
    fields_map = {
        "stock_basic": [
            {"name": "stock_code", "label": "股票代码", "type": "string"},
            {"name": "stock_name", "label": "股票名称", "type": "string"},
            {"name": "industry", "label": "所属行业", "type": "string"},
            {"name": "list_date", "label": "上市日期", "type": "date"}
        ],
        "daily_quote": [
            {"name": "date", "label": "日期", "type": "date"},
            {"name": "open", "label": "开盘价", "type": "float"},
            {"name": "high", "label": "最高价", "type": "float"},
            {"name": "low", "label": "最低价", "type": "float"},
            {"name": "close", "label": "收盘价", "type": "float"},
            {"name": "volume", "label": "成交量", "type": "int"},
            {"name": "amount", "label": "成交额", "type": "float"}
        ],
        "financial": [
            {"name": "report_date", "label": "报告期", "type": "date"},
            {"name": "revenue", "label": "营业收入", "type": "float"},
            {"name": "net_profit", "label": "净利润", "type": "float"},
            {"name": "roe", "label": "ROE", "type": "float"},
            {"name": "eps", "label": "每股收益", "type": "float"}
        ],
        "valuation": [
            {"name": "date", "label": "日期", "type": "date"},
            {"name": "pe", "label": "市盈率", "type": "float"},
            {"name": "pb", "label": "市净率", "type": "float"},
            {"name": "ps", "label": "市销率", "type": "float"},
            {"name": "market_cap", "label": "总市值", "type": "float"}
        ]
    }
    return {"success": True, "data": fields_map.get(category, [])}


@router.post("/query")
async def query_data(request: DataQueryRequest):
    """查询数据"""
    try:
        manager = _get_data_manager()
        if manager:
            data = manager.query(request.category, request.fields, request.filters, request.limit)
            return {"success": True, "data": data}
        return {"success": False, "error": "数据中心模块未加载"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
async def export_data(request: ExportRequest):
    """导出数据"""
    try:
        manager = _get_data_manager()
        if manager:
            file_path = manager.export(request.category, request.fields, request.format, request.filters)
            return {"success": True, "data": {"file_path": file_path}}
        return {"success": False, "error": "数据中心模块未加载"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
