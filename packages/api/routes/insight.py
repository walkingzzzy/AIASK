"""
洞察引擎API路由
提供机会发现、风险预警、AI洞察等接口
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from packages.core.insight_engine import (
    OpportunityDetector,
    RiskDetector,
    InsightGenerator,
)
from packages.core.insight_engine.models import UserProfile

router = APIRouter(prefix="/insight", tags=["洞察引擎"])

# 初始化引擎
opportunity_detector = OpportunityDetector()
risk_detector = RiskDetector()
insight_generator = InsightGenerator()


# ==================== 请求模型 ====================

class UserProfileRequest(BaseModel):
    """用户画像请求"""
    user_id: str = "default"
    watchlist: List[str] = []
    holdings: List[str] = []
    investment_style: str = "balanced"
    risk_tolerance: int = 3
    focus_sectors: List[str] = []


class StockRequest(BaseModel):
    """股票请求"""
    stock_code: str
    stock_name: str = ""


# ==================== 机会发现 ====================

@router.post("/opportunities")
async def get_opportunities(profile: UserProfileRequest):
    """
    获取投资机会
    
    根据用户画像检测投资机会，包括：
    - 买入信号
    - 相似股票推荐
    - 板块轮动机会
    - 技术形态突破
    """
    try:
        user_profile = UserProfile(
            user_id=profile.user_id,
            watchlist=profile.watchlist,
            holdings=profile.holdings,
            investment_style=profile.investment_style,
            risk_tolerance=profile.risk_tolerance,
            focus_sectors=profile.focus_sectors
        )
        
        opportunities = opportunity_detector.detect_for_user(user_profile)
        
        return {
            "success": True,
            "data": {
                "opportunities": [o.to_dict() for o in opportunities],
                "total": len(opportunities),
                "generated_at": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/opportunities/{stock_code}")
async def get_stock_opportunities(
    stock_code: str,
    stock_name: str = Query("", description="股票名称")
):
    """获取单只股票的投资机会"""
    try:
        opportunities = opportunity_detector.detect_for_stock(stock_code, stock_name)
        
        return {
            "success": True,
            "data": {
                "stock_code": stock_code,
                "opportunities": [o.to_dict() for o in opportunities],
                "total": len(opportunities)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 风险预警 ====================

@router.post("/risks")
async def get_risks(profile: UserProfileRequest):
    """
    获取风险预警
    
    根据用户画像检测风险，包括：
    - 价格下跌风险
    - 成交量异常
    - 技术破位
    - 资金流出
    - 负面舆情
    """
    try:
        user_profile = UserProfile(
            user_id=profile.user_id,
            watchlist=profile.watchlist,
            holdings=profile.holdings,
            investment_style=profile.investment_style,
            risk_tolerance=profile.risk_tolerance,
            focus_sectors=profile.focus_sectors
        )
        
        alerts = risk_detector.detect_for_user(user_profile)
        
        return {
            "success": True,
            "data": {
                "alerts": [a.to_dict() for a in alerts],
                "total": len(alerts),
                "critical_count": len([a for a in alerts if a.severity.value == "critical"]),
                "warning_count": len([a for a in alerts if a.severity.value == "warning"]),
                "generated_at": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risks/{stock_code}")
async def get_stock_risks(
    stock_code: str,
    stock_name: str = Query("", description="股票名称"),
    is_holding: bool = Query(False, description="是否为持仓")
):
    """获取单只股票的风险预警"""
    try:
        alerts = risk_detector.detect_for_stock(stock_code, stock_name, is_holding)
        
        return {
            "success": True,
            "data": {
                "stock_code": stock_code,
                "alerts": [a.to_dict() for a in alerts],
                "total": len(alerts)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AI洞察 ====================

@router.post("/daily")
async def get_daily_insights(profile: UserProfileRequest):
    """
    获取每日AI洞察
    
    包括：
    - 市场观点
    - 个股洞察
    - 板块分析
    - 关联分析
    """
    try:
        user_profile = UserProfile(
            user_id=profile.user_id,
            watchlist=profile.watchlist,
            holdings=profile.holdings,
            investment_style=profile.investment_style,
            risk_tolerance=profile.risk_tolerance,
            focus_sectors=profile.focus_sectors
        )
        
        insights = insight_generator.generate_daily_insights(user_profile)
        
        return {
            "success": True,
            "data": {
                "insights": [i.to_dict() for i in insights],
                "total": len(insights),
                "generated_at": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{stock_code}")
async def get_stock_insights(
    stock_code: str,
    stock_name: str = Query("", description="股票名称")
):
    """获取单只股票的AI洞察"""
    try:
        insights = insight_generator.generate_for_stock(stock_code, stock_name)
        
        return {
            "success": True,
            "data": {
                "stock_code": stock_code,
                "insights": [i.to_dict() for i in insights],
                "total": len(insights)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 综合接口 ====================

@router.post("/summary")
async def get_insight_summary(profile: UserProfileRequest):
    """
    获取洞察摘要
    
    一次性返回机会、风险、洞察的汇总
    """
    try:
        user_profile = UserProfile(
            user_id=profile.user_id,
            watchlist=profile.watchlist,
            holdings=profile.holdings,
            investment_style=profile.investment_style,
            risk_tolerance=profile.risk_tolerance,
            focus_sectors=profile.focus_sectors
        )
        
        # 并行获取各类数据
        opportunities = opportunity_detector.detect_for_user(user_profile)
        alerts = risk_detector.detect_for_user(user_profile)
        insights = insight_generator.generate_daily_insights(user_profile)
        
        return {
            "success": True,
            "data": {
                "opportunities": {
                    "items": [o.to_dict() for o in opportunities[:5]],
                    "total": len(opportunities)
                },
                "risks": {
                    "items": [a.to_dict() for a in alerts[:5]],
                    "total": len(alerts),
                    "critical_count": len([a for a in alerts if a.severity.value == "critical"])
                },
                "insights": {
                    "items": [i.to_dict() for i in insights[:3]],
                    "total": len(insights)
                },
                "generated_at": datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
