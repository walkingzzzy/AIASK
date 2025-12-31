"""
自选股管理API路由
提供自选股的增删改查、分组管理等功能
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import json

from packages.core.data_layer.storage.user_data_db import UserDataDB

router = APIRouter(prefix="/api/watchlist", tags=["自选股管理"])

# 初始化数据库
db = UserDataDB("./data/user_data.db")


# ==================== 数据模型 ====================

class StockItem(BaseModel):
    """自选股项目"""
    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    group_id: Optional[str] = Field(None, description="所属分组ID")
    added_at: datetime = Field(default_factory=datetime.now, description="添加时间")
    notes: Optional[str] = Field(None, description="备注")
    tags: List[str] = Field(default_factory=list, description="标签")
    alert_price_high: Optional[float] = Field(None, description="价格上限提醒")
    alert_price_low: Optional[float] = Field(None, description="价格下限提醒")


class WatchlistGroup(BaseModel):
    """自选股分组"""
    id: str = Field(..., description="分组ID")
    name: str = Field(..., description="分组名称")
    description: Optional[str] = Field(None, description="分组描述")
    color: Optional[str] = Field(None, description="分组颜色")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    stock_count: int = Field(0, description="股票数量")


class AddStockRequest(BaseModel):
    """添加股票请求"""
    code: str
    name: Optional[str] = None
    group_id: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class UpdateStockRequest(BaseModel):
    """更新股票请求"""
    group_id: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None


class CreateGroupRequest(BaseModel):
    """创建分组请求"""
    name: str
    description: Optional[str] = None
    color: Optional[str] = None


class UpdateGroupRequest(BaseModel):
    """更新分组请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class BatchOperationRequest(BaseModel):
    """批量操作请求"""
    codes: List[str]
    operation: str  # 'add', 'remove', 'move'
    target_group_id: Optional[str] = None


def _row_to_stock_item(row: dict) -> StockItem:
    """将数据库行转换为StockItem"""
    tags = json.loads(row.get('tags') or '[]') if isinstance(row.get('tags'), str) else (row.get('tags') or [])
    return StockItem(
        code=row['stock_code'],
        name=row.get('stock_name') or row['stock_code'],
        group_id=row.get('group_id'),
        added_at=row.get('added_at') or datetime.now(),
        notes=row.get('notes'),
        tags=tags,
        alert_price_high=row.get('alert_price_high'),
        alert_price_low=row.get('alert_price_low')
    )


# ==================== API端点 ====================

@router.get("/stocks", response_model=List[StockItem])
async def get_watchlist_stocks(group_id: Optional[str] = None, tag: Optional[str] = None):
    """获取自选股列表"""
    rows = db.get_watchlist(group_id=group_id)
    stocks = [_row_to_stock_item(r) for r in rows]
    if tag:
        stocks = [s for s in stocks if tag in s.tags]
    return stocks


@router.post("/stocks", response_model=StockItem)
async def add_stock_to_watchlist(request: AddStockRequest):
    """添加股票到自选股"""
    existing = db.get_watchlist()
    if any(r['stock_code'] == request.code for r in existing):
        raise HTTPException(status_code=400, detail="股票已在自选股中")
    
    tags_str = json.dumps(request.tags) if request.tags else None
    db.add_watchlist_item(
        stock_code=request.code,
        stock_name=request.name or request.code,
        group_id=request.group_id or "default",
        notes=request.notes,
        tags=tags_str
    )
    
    rows = db.get_watchlist()
    row = next((r for r in rows if r['stock_code'] == request.code), None)
    return _row_to_stock_item(row)


@router.get("/stocks/{code}", response_model=StockItem)
async def get_watchlist_stock(code: str):
    """获取单个自选股详情"""
    rows = db.get_watchlist()
    row = next((r for r in rows if r['stock_code'] == code), None)
    if not row:
        raise HTTPException(status_code=404, detail="股票不在自选股中")
    return _row_to_stock_item(row)


@router.put("/stocks/{code}", response_model=StockItem)
async def update_watchlist_stock(code: str, request: UpdateStockRequest):
    """更新自选股信息"""
    rows = db.get_watchlist()
    if not any(r['stock_code'] == code for r in rows):
        raise HTTPException(status_code=404, detail="股票不在自选股中")
    
    kwargs = {}
    if request.group_id is not None:
        kwargs['group_id'] = request.group_id
    if request.notes is not None:
        kwargs['notes'] = request.notes
    if request.tags is not None:
        kwargs['tags'] = json.dumps(request.tags)
    if request.alert_price_high is not None:
        kwargs['alert_price_high'] = request.alert_price_high
    if request.alert_price_low is not None:
        kwargs['alert_price_low'] = request.alert_price_low
    
    if kwargs:
        db.update_watchlist_item(stock_code=code, **kwargs)
    
    rows = db.get_watchlist()
    row = next((r for r in rows if r['stock_code'] == code), None)
    return _row_to_stock_item(row)


@router.delete("/stocks/{code}")
async def remove_stock_from_watchlist(code: str):
    """从自选股中移除股票"""
    rows = db.get_watchlist()
    if not any(r['stock_code'] == code for r in rows):
        raise HTTPException(status_code=404, detail="股票不在自选股中")
    
    db.remove_watchlist_item(stock_code=code)
    return {"message": "股票已移除", "code": code}


@router.post("/stocks/batch")
async def batch_operation(request: BatchOperationRequest):
    """批量操作股票"""
    results = {"success": [], "failed": []}
    rows = db.get_watchlist()
    existing_codes = {r['stock_code'] for r in rows}
    
    for code in request.codes:
        try:
            if request.operation == "remove":
                if code in existing_codes:
                    db.remove_watchlist_item(stock_code=code)
                    results["success"].append(code)
                else:
                    results["failed"].append({"code": code, "reason": "不在自选股中"})
            elif request.operation == "move":
                if not request.target_group_id:
                    results["failed"].append({"code": code, "reason": "未指定目标分组"})
                elif code in existing_codes:
                    db.update_watchlist_item(stock_code=code, group_id=request.target_group_id)
                    results["success"].append(code)
                else:
                    results["failed"].append({"code": code, "reason": "不在自选股中"})
        except Exception as e:
            results["failed"].append({"code": code, "reason": str(e)})
    
    return results


# ==================== 分组管理 ====================

@router.get("/groups", response_model=List[WatchlistGroup])
async def get_watchlist_groups():
    """获取所有自选股分组"""
    groups = db.get_groups()
    watchlist = db.get_watchlist()
    
    # 计算每个分组的股票数量
    group_counts = {}
    for item in watchlist:
        gid = item.get('group_id', 'default')
        group_counts[gid] = group_counts.get(gid, 0) + 1
    
    result = []
    for g in groups:
        result.append(WatchlistGroup(
            id=g['id'],
            name=g['name'],
            description=g.get('description'),
            color=g.get('color', '#1890ff'),
            created_at=g.get('created_at') or datetime.now(),
            stock_count=group_counts.get(g['id'], 0)
        ))
    
    # 确保默认分组存在
    if not any(g['id'] == 'default' for g in groups):
        result.insert(0, WatchlistGroup(
            id="default",
            name="默认分组",
            description="默认自选股分组",
            color="#1890ff",
            stock_count=group_counts.get('default', 0)
        ))
    
    return result


@router.post("/groups", response_model=WatchlistGroup)
async def create_watchlist_group(request: CreateGroupRequest):
    """创建新的自选股分组"""
    groups = db.get_groups()
    if any(g['name'] == request.name for g in groups):
        raise HTTPException(status_code=400, detail="分组名称已存在")
    
    group_id = f"group_{len(groups)}_{int(datetime.now().timestamp())}"
    db.create_group(
        group_id=group_id,
        name=request.name,
        description=request.description,
        color=request.color or "#1890ff"
    )
    
    return WatchlistGroup(
        id=group_id,
        name=request.name,
        description=request.description,
        color=request.color or "#1890ff",
        stock_count=0
    )


@router.get("/groups/{group_id}", response_model=WatchlistGroup)
async def get_watchlist_group(group_id: str):
    """获取单个分组详情"""
    groups = db.get_groups()
    group = next((g for g in groups if g['id'] == group_id), None)
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    
    watchlist = db.get_watchlist(group_id=group_id)
    return WatchlistGroup(
        id=group['id'],
        name=group['name'],
        description=group.get('description'),
        color=group.get('color', '#1890ff'),
        created_at=group.get('created_at') or datetime.now(),
        stock_count=len(watchlist)
    )


@router.put("/groups/{group_id}", response_model=WatchlistGroup)
async def update_watchlist_group(group_id: str, request: UpdateGroupRequest):
    """更新分组信息"""
    groups = db.get_groups()
    if not any(g['id'] == group_id for g in groups):
        raise HTTPException(status_code=404, detail="分组不存在")
    
    if request.name:
        if any(g['id'] != group_id and g['name'] == request.name for g in groups):
            raise HTTPException(status_code=400, detail="分组名称已存在")
    
    kwargs = {}
    if request.name is not None:
        kwargs['name'] = request.name
    if request.description is not None:
        kwargs['description'] = request.description
    if request.color is not None:
        kwargs['color'] = request.color
    
    if kwargs:
        db.update_group(group_id=group_id, **kwargs)
    
    groups = db.get_groups()
    group = next(g for g in groups if g['id'] == group_id)
    watchlist = db.get_watchlist(group_id=group_id)
    
    return WatchlistGroup(
        id=group['id'],
        name=group['name'],
        description=group.get('description'),
        color=group.get('color', '#1890ff'),
        created_at=group.get('created_at') or datetime.now(),
        stock_count=len(watchlist)
    )


@router.delete("/groups/{group_id}")
async def delete_watchlist_group(group_id: str):
    """删除分组（分组内的股票会移到默认分组）"""
    if group_id == "default":
        raise HTTPException(status_code=400, detail="不能删除默认分组")
    
    groups = db.get_groups()
    if not any(g['id'] == group_id for g in groups):
        raise HTTPException(status_code=404, detail="分组不存在")
    
    db.delete_group(group_id=group_id)
    return {"message": "分组已删除", "group_id": group_id}


# ==================== 统计信息 ====================

@router.get("/stats")
async def get_watchlist_stats():
    """获取自选股统计信息"""
    watchlist = db.get_watchlist()
    groups = db.get_groups()
    
    # 按分组统计
    group_counts = {}
    tag_counts = {}
    for item in watchlist:
        gid = item.get('group_id', 'default')
        group_counts[gid] = group_counts.get(gid, 0) + 1
        tags = json.loads(item.get('tags') or '[]') if isinstance(item.get('tags'), str) else (item.get('tags') or [])
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    group_stats = []
    for g in groups:
        group_stats.append({
            "group_id": g['id'],
            "group_name": g['name'],
            "stock_count": group_counts.get(g['id'], 0)
        })
    
    return {
        "total_stocks": len(watchlist),
        "total_groups": len(groups),
        "group_stats": group_stats,
        "tag_stats": tag_counts,
        "last_updated": datetime.now()
    }
