"""
决策追踪API路由
提供交易决策记录、复盘分析等功能
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from packages.core.data_layer.storage.user_data_db import UserDataDB

router = APIRouter(prefix="/decision", tags=["决策追踪"])

# 初始化数据库
_db = UserDataDB(db_path="./data/user_data.db")


# ==================== 数据模型 ====================

class DecisionAction(str, Enum):
    """决策操作类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class DecisionRecord(BaseModel):
    """决策记录"""
    id: str
    user_id: str
    stock_code: str
    stock_name: str
    action: DecisionAction
    reason: str
    price_at_decision: float
    current_price: Optional[float] = None
    profit_percent: Optional[float] = None
    is_correct: Optional[bool] = None
    ai_suggested: bool = False
    ai_confidence: Optional[float] = None
    timestamp: datetime


class DecisionCreateRequest(BaseModel):
    """创建决策请求"""
    stock_code: str
    stock_name: str
    action: DecisionAction
    reason: str
    price: float
    ai_suggested: bool = False
    ai_confidence: Optional[float] = None


class ReviewStats(BaseModel):
    """复盘统计"""
    total_decisions: int
    correct_decisions: int
    accuracy: float
    total_profit: float
    avg_profit: float
    ai_accuracy: float
    user_accuracy: float
    best_decision: Optional[Dict] = None
    worst_decision: Optional[Dict] = None


# ==================== API路由 ====================

@router.post("/record")
async def record_decision(
    request: DecisionCreateRequest,
    user_id: str = Query("default", description="用户ID")
):
    """
    记录交易决策
    """
    try:
        record_id = _db.add_decision_record(
            stock_code=request.stock_code,
            action=request.action.value,
            user_id=user_id,
            stock_name=request.stock_name,
            reason=request.reason,
            price_at_decision=request.price,
            ai_suggested=request.ai_suggested
        )
        
        return {
            "success": True,
            "data": {
                "id": str(record_id),
                "message": "决策已记录"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_decisions(
    user_id: str = Query("default", description="用户ID"),
    days: int = Query(30, description="查询天数"),
    limit: int = Query(50, description="返回数量限制")
):
    """
    获取决策列表
    """
    try:
        records = _db.get_decision_records(user_id=user_id, limit=limit)
        
        # 转换为API响应格式
        result = []
        for r in records:
            created_at = r.get('created_at')
            if isinstance(created_at, str):
                timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00')) if created_at else datetime.now()
            else:
                timestamp = created_at or datetime.now()
            
            # 按时间过滤
            cutoff = datetime.now() - timedelta(days=days)
            if timestamp.replace(tzinfo=None) < cutoff:
                continue
            
            price_at_decision = r.get('price_at_decision') or 0
            current_price = r.get('current_price')
            action = r.get('action', 'hold')
            
            # 计算收益
            profit_percent = None
            is_correct = None
            if current_price and price_at_decision:
                if action == 'buy':
                    profit_percent = (current_price - price_at_decision) / price_at_decision * 100
                elif action == 'sell':
                    profit_percent = (price_at_decision - current_price) / price_at_decision * 100
                else:
                    profit_percent = (current_price - price_at_decision) / price_at_decision * 100
                is_correct = profit_percent > 0
            
            result.append({
                "id": str(r.get('id')),
                "user_id": r.get('user_id', 'default'),
                "stock_code": r.get('stock_code'),
                "stock_name": r.get('stock_name'),
                "action": action,
                "reason": r.get('reason'),
                "price_at_decision": price_at_decision,
                "current_price": current_price,
                "profit_percent": profit_percent,
                "is_correct": is_correct,
                "ai_suggested": bool(r.get('ai_suggested')),
                "ai_confidence": None,
                "timestamp": timestamp.isoformat() if timestamp else None
            })
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_decision_stats(
    user_id: str = Query("default", description="用户ID"),
    days: int = Query(30, description="统计天数")
):
    """
    获取决策统计
    """
    try:
        records = _db.get_decision_records(user_id=user_id, limit=1000)
        
        # 按时间过滤并计算收益
        cutoff = datetime.now() - timedelta(days=days)
        filtered = []
        for r in records:
            created_at = r.get('created_at')
            if isinstance(created_at, str):
                timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00')) if created_at else datetime.now()
            else:
                timestamp = created_at or datetime.now()
            
            if timestamp.replace(tzinfo=None) < cutoff:
                continue
            
            price_at_decision = r.get('price_at_decision') or 0
            current_price = r.get('current_price')
            action = r.get('action', 'hold')
            
            profit_percent = None
            is_correct = None
            if current_price and price_at_decision:
                if action == 'buy':
                    profit_percent = (current_price - price_at_decision) / price_at_decision * 100
                elif action == 'sell':
                    profit_percent = (price_at_decision - current_price) / price_at_decision * 100
                else:
                    profit_percent = (current_price - price_at_decision) / price_at_decision * 100
                is_correct = profit_percent > 0
            
            filtered.append({
                **r,
                'profit_percent': profit_percent,
                'is_correct': is_correct,
                'timestamp': timestamp
            })
        
        if not filtered:
            return {
                "success": True,
                "data": ReviewStats(
                    total_decisions=0,
                    correct_decisions=0,
                    accuracy=0,
                    total_profit=0,
                    avg_profit=0,
                    ai_accuracy=0,
                    user_accuracy=0
                ).dict()
            }
        
        # 计算统计
        total = len(filtered)
        correct = sum(1 for d in filtered if d.get('is_correct'))
        total_profit = sum(d.get('profit_percent') or 0 for d in filtered)
        
        ai_decisions = [d for d in filtered if d.get('ai_suggested')]
        ai_correct = sum(1 for d in ai_decisions if d.get('is_correct'))
        
        user_decisions_only = [d for d in filtered if not d.get('ai_suggested')]
        user_correct = sum(1 for d in user_decisions_only if d.get('is_correct'))
        
        # 找最佳和最差决策
        sorted_by_profit = sorted(filtered, key=lambda x: x.get('profit_percent') or 0, reverse=True)
        best = sorted_by_profit[0] if sorted_by_profit else None
        worst = sorted_by_profit[-1] if sorted_by_profit else None
        
        stats = ReviewStats(
            total_decisions=total,
            correct_decisions=correct,
            accuracy=(correct / total * 100) if total > 0 else 0,
            total_profit=total_profit,
            avg_profit=(total_profit / total) if total > 0 else 0,
            ai_accuracy=(ai_correct / len(ai_decisions) * 100) if ai_decisions else 0,
            user_accuracy=(user_correct / len(user_decisions_only) * 100) if user_decisions_only else 0,
            best_decision=best,
            worst_decision=worst
        )
        
        return {
            "success": True,
            "data": stats.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{decision_id}/update")
async def update_decision(
    decision_id: str,
    current_price: float = Query(..., description="当前价格"),
    user_id: str = Query("default", description="用户ID")
):
    """
    更新决策的当前价格（暂不支持，需要扩展数据库方法）
    """
    raise HTTPException(status_code=501, detail="功能暂未实现")


@router.delete("/{decision_id}")
async def delete_decision(
    decision_id: str,
    user_id: str = Query("default", description="用户ID")
):
    """
    删除决策记录
    """
    try:
        _db.delete_decision_record(int(decision_id))
        return {
            "success": True,
            "message": "决策已删除"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-suggestions")
async def get_ai_suggestions(
    user_id: str = Query("default", description="用户ID"),
    days: int = Query(30, description="查询天数")
):
    """
    获取AI建议的历史记录和准确率
    """
    try:
        records = _db.get_decision_records(user_id=user_id, limit=1000)
        
        cutoff = datetime.now() - timedelta(days=days)
        ai_decisions = []
        
        for r in records:
            if not r.get('ai_suggested'):
                continue
            
            created_at = r.get('created_at')
            if isinstance(created_at, str):
                timestamp = datetime.fromisoformat(created_at.replace('Z', '+00:00')) if created_at else datetime.now()
            else:
                timestamp = created_at or datetime.now()
            
            if timestamp.replace(tzinfo=None) < cutoff:
                continue
            
            price_at_decision = r.get('price_at_decision') or 0
            current_price = r.get('current_price')
            action = r.get('action', 'hold')
            
            profit_percent = None
            is_correct = None
            if current_price and price_at_decision:
                if action == 'buy':
                    profit_percent = (current_price - price_at_decision) / price_at_decision * 100
                else:
                    profit_percent = (price_at_decision - current_price) / price_at_decision * 100
                is_correct = profit_percent > 0
            
            ai_decisions.append({
                "id": str(r.get('id')),
                "user_id": r.get('user_id', 'default'),
                "stock_code": r.get('stock_code'),
                "stock_name": r.get('stock_name'),
                "action": action,
                "reason": r.get('reason'),
                "price_at_decision": price_at_decision,
                "current_price": current_price,
                "profit_percent": profit_percent,
                "is_correct": is_correct,
                "ai_suggested": True,
                "ai_confidence": None,
                "timestamp": timestamp.isoformat() if timestamp else None
            })
        
        total = len(ai_decisions)
        correct = sum(1 for d in ai_decisions if d.get('is_correct'))
        
        return {
            "success": True,
            "data": {
                "total_suggestions": total,
                "correct_suggestions": correct,
                "accuracy": (correct / total * 100) if total > 0 else 0,
                "suggestions": ai_decisions[:20]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
