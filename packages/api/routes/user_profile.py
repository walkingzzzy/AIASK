"""
用户画像API路由
提供用户画像管理、行为追踪、个性化推荐等接口
"""
import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from packages.api.dependencies import get_profile_services

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user", tags=["用户画像"])


# ==================== 请求模型 ====================

class ProfileUpdateRequest(BaseModel):
    investment_style: Optional[str] = None
    risk_tolerance: Optional[int] = None
    focus_sectors: Optional[List[str]] = None
    avoided_sectors: Optional[List[str]] = None
    preferred_market_cap: Optional[str] = None
    knowledge_level: Optional[str] = None
    decision_speed: Optional[str] = None
    analysis_depth: Optional[str] = None
    preferred_data_types: Optional[List[str]] = None
    nickname: Optional[str] = None
    ai_personality: Optional[str] = None
    notification_enabled: Optional[bool] = None
    morning_brief_enabled: Optional[bool] = None


class BehaviorEventRequest(BaseModel):
    event_type: str
    data: Dict[str, Any] = {}
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    page: Optional[str] = None
    session_id: Optional[str] = None


class QueryTrackRequest(BaseModel):
    query: str
    intent: str
    stock_codes: List[str] = []
    success: bool = True


class DecisionTrackRequest(BaseModel):
    stock_code: str
    stock_name: str
    action: str
    reason: str
    price: float
    ai_suggested: bool = False


class FeedbackRequest(BaseModel):
    feedback_type: str
    is_positive: bool
    context: Dict[str, Any] = {}


class WatchlistUpdateRequest(BaseModel):
    watchlist: List[str]


class HoldingsUpdateRequest(BaseModel):
    holdings: List[str]


def _get_services():
    """获取用户画像服务"""
    services = get_profile_services()
    if not services:
        raise HTTPException(status_code=503, detail="用户画像服务不可用")
    return services


# ==================== 用户画像 ====================

@router.get("/profile")
async def get_profile(user_id: str = Query("default"), services=Depends(_get_services)):
    """获取用户画像"""
    try:
        profile = services["profile"].get_profile(user_id)
        return {"success": True, "data": profile.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户画像失败: {e}")
        raise HTTPException(status_code=500, detail="获取用户画像失败")


@router.put("/profile")
async def update_profile(
    request: ProfileUpdateRequest,
    user_id: str = Query("default"),
    services=Depends(_get_services)
):
    """更新用户画像"""
    try:
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        profile = services["profile"].update_profile(user_id, updates)
        return {"success": True, "data": profile.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新用户画像失败: {e}")
        raise HTTPException(status_code=500, detail="更新用户画像失败")


@router.get("/profile/preferences")
async def get_preferences(user_id: str = Query("default"), services=Depends(_get_services)):
    """获取用户偏好设置"""
    try:
        profile = services["profile"].get_profile(user_id)
        return {
            "success": True,
            "data": {
                "investment_style": profile.investment_style.value,
                "risk_tolerance": profile.risk_tolerance,
                "focus_sectors": profile.focus_sectors,
                "avoided_sectors": profile.avoided_sectors,
                "preferred_market_cap": profile.preferred_market_cap,
                "knowledge_level": profile.knowledge_level.value,
                "decision_speed": profile.decision_speed.value,
                "analysis_depth": profile.analysis_depth,
                "preferred_data_types": profile.preferred_data_types,
                "ai_personality": profile.ai_personality,
                "notification_enabled": profile.notification_enabled,
                "morning_brief_enabled": profile.morning_brief_enabled
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户偏好失败: {e}")
        raise HTTPException(status_code=500, detail="获取用户偏好失败")


# ==================== 行为追踪 ====================

@router.post("/behavior")
async def track_behavior(
    request: BehaviorEventRequest,
    user_id: str = Query("default"),
    services=Depends(_get_services)
):
    """追踪用户行为"""
    try:
        from packages.core.user_profile import BehaviorType
        event_type = BehaviorType(request.event_type)
        
        event = services["behavior"].track(
            user_id=user_id,
            event_type=event_type,
            data=request.data,
            stock_code=request.stock_code,
            stock_name=request.stock_name,
            page=request.page,
            session_id=request.session_id
        )
        
        return {"success": True, "data": {"event_id": event.id, "tracked_at": event.timestamp.isoformat()}}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的事件类型: {request.event_type}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追踪行为失败: {e}")
        raise HTTPException(status_code=500, detail="追踪行为失败")


@router.post("/behavior/query")
async def track_query(
    request: QueryTrackRequest,
    user_id: str = Query("default"),
    services=Depends(_get_services)
):
    """追踪查询行为"""
    try:
        event = services["behavior"].track_query(
            user_id=user_id,
            query=request.query,
            intent=request.intent,
            stock_codes=request.stock_codes,
            success=request.success
        )
        return {"success": True, "data": {"event_id": event.id}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追踪查询失败: {e}")
        raise HTTPException(status_code=500, detail="追踪查询失败")


@router.post("/behavior/decision")
async def track_decision(
    request: DecisionTrackRequest,
    user_id: str = Query("default"),
    services=Depends(_get_services)
):
    """追踪交易决策"""
    try:
        event = services["behavior"].track_decision(
            user_id=user_id,
            stock_code=request.stock_code,
            stock_name=request.stock_name,
            action=request.action,
            reason=request.reason,
            price=request.price,
            ai_suggested=request.ai_suggested
        )
        return {"success": True, "data": {"event_id": event.id}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追踪决策失败: {e}")
        raise HTTPException(status_code=500, detail="追踪决策失败")


@router.post("/behavior/feedback")
async def track_feedback(
    request: FeedbackRequest,
    user_id: str = Query("default"),
    services=Depends(_get_services)
):
    """追踪AI反馈"""
    try:
        event = services["behavior"].track_ai_feedback(
            user_id=user_id,
            feedback_type=request.feedback_type,
            is_positive=request.is_positive,
            context=request.context
        )
        return {"success": True, "data": {"event_id": event.id}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追踪反馈失败: {e}")
        raise HTTPException(status_code=500, detail="追踪反馈失败")


@router.get("/behavior/summary")
async def get_behavior_summary(
    user_id: str = Query("default"),
    days: int = Query(7, ge=1, le=90),
    services=Depends(_get_services)
):
    """获取行为摘要"""
    try:
        summary = services["behavior"].get_behavior_summary(user_id, days)
        return {"success": True, "data": summary}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取行为摘要失败: {e}")
        raise HTTPException(status_code=500, detail="获取行为摘要失败")


# ==================== 偏好学习 ====================

@router.post("/learn")
async def trigger_learning(user_id: str = Query("default"), services=Depends(_get_services)):
    """触发偏好学习"""
    try:
        profile = services["learner"].learn_from_events(user_id)
        return {
            "success": True,
            "data": {
                "investment_style": profile.investment_style.value,
                "style_scores": profile.style_scores,
                "focus_sectors": profile.focus_sectors,
                "knowledge_level": profile.knowledge_level.value
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"触发学习失败: {e}")
        raise HTTPException(status_code=500, detail="触发学习失败")


@router.get("/learning-insights")
async def get_learning_insights(user_id: str = Query("default"), services=Depends(_get_services)):
    """获取学习洞察"""
    try:
        insights = services["learner"].get_learning_insights(user_id)
        return {"success": True, "data": insights}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取学习洞察失败: {e}")
        raise HTTPException(status_code=500, detail="获取学习洞察失败")


# ==================== 个性化推荐 ====================

@router.get("/recommendations")
async def get_recommendations(
    user_id: str = Query("default"),
    limit: int = Query(10, ge=1, le=50),
    services=Depends(_get_services)
):
    """获取个性化股票推荐"""
    try:
        recommendations = services["recommendation"].get_personalized_stocks(user_id, limit)
        return {
            "success": True,
            "data": {
                "recommendations": [r.to_dict() for r in recommendations],
                "total": len(recommendations),
                "generated_at": datetime.utcnow().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取推荐失败: {e}")
        raise HTTPException(status_code=500, detail="获取推荐失败")


@router.get("/morning-brief")
async def get_morning_brief(user_id: str = Query("default"), services=Depends(_get_services)):
    """获取个性化早报"""
    try:
        brief = services["recommendation"].generate_morning_brief(user_id)
        return {"success": True, "data": brief.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取早报失败: {e}")
        raise HTTPException(status_code=500, detail="获取早报失败")


# ==================== 自选股和持仓 ====================

@router.put("/watchlist")
async def update_watchlist(
    request: WatchlistUpdateRequest,
    user_id: str = Query("default"),
    services=Depends(_get_services)
):
    """更新自选股列表"""
    try:
        profile = services["profile"].update_watchlist(user_id, request.watchlist)
        return {"success": True, "data": {"watchlist": profile.watchlist}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新自选股失败: {e}")
        raise HTTPException(status_code=500, detail="更新自选股失败")


@router.put("/holdings")
async def update_holdings(
    request: HoldingsUpdateRequest,
    user_id: str = Query("default"),
    services=Depends(_get_services)
):
    """更新持仓列表"""
    try:
        profile = services["profile"].update_holdings(user_id, request.holdings)
        return {"success": True, "data": {"holdings": profile.holdings}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新持仓失败: {e}")
        raise HTTPException(status_code=500, detail="更新持仓失败")


# ==================== 使用统计 ====================

@router.get("/stats")
async def get_usage_stats(user_id: str = Query("default"), services=Depends(_get_services)):
    """获取使用统计"""
    try:
        profile = services["profile"].get_profile(user_id)
        return {
            "success": True,
            "data": {
                "usage_stats": profile.usage_stats.to_dict(),
                "ai_relationship": profile.ai_relationship.to_dict(),
                "learning_progress": profile.learning_progress.to_dict()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取使用统计失败: {e}")
        raise HTTPException(status_code=500, detail="获取使用统计失败")


@router.get("/streak")
async def get_streak(user_id: str = Query("default"), services=Depends(_get_services)):
    """获取连续使用数据"""
    try:
        profile = services["profile"].get_profile(user_id)
        return {
            "success": True,
            "data": {
                "consecutive_days": profile.usage_stats.consecutive_days,
                "longest_streak": profile.usage_stats.longest_streak,
                "first_active_date": profile.usage_stats.first_active_date,
                "last_active_date": profile.usage_stats.last_active_date
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取连续使用数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取连续使用数据失败")
