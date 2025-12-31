"""
研报中心API路由
提供研报检索、AI分析、评级统计等功能
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

router = APIRouter(prefix="/research", tags=["研报中心"])
logger = logging.getLogger(__name__)

# 初始化 ReportManager
_report_manager = None

def get_report_manager():
    """获取 ReportManager 实例"""
    global _report_manager
    if _report_manager is None:
        try:
            from packages.core.research_center.report_manager import ReportManager
            _report_manager = ReportManager()
        except Exception as e:
            logger.error(f"初始化 ReportManager 失败: {e}")
            return None
    return _report_manager


# ==================== 请求模型 ====================

class SearchRequest(BaseModel):
    """搜索请求"""
    keyword: Optional[str] = None
    stock_code: Optional[str] = None
    institution: Optional[str] = None
    rating: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 20


class AnalyzeRequest(BaseModel):
    """分析请求"""
    report_id: str
    analysis_type: str = "summary"  # summary, key_points, risk, target


# ==================== 研报API ====================

@router.get("/summary")
async def get_research_summary():
    """获取研报中心概览"""
    try:
        manager = get_report_manager()
        if not manager:
            return {
                "success": True,
                "data": {
                    "total_count": 0,
                    "by_rating": {},
                    "by_type": {},
                    "hot_stocks": [],
                    "recent_reports": [],
                    "update_time": datetime.now().isoformat()
                }
            }
        
        summary = manager.get_summary()
        return {
            "success": True,
            "data": {
                "total_count": summary.total_count,
                "by_rating": summary.by_rating,
                "by_type": summary.by_type,
                "hot_stocks": summary.hot_stocks,
                "recent_reports": [r.to_dict() for r in summary.recent_reports],
                "update_time": datetime.now().isoformat()
            }
        }
    except Exception as e:
        logger.error(f"获取研报概览失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_research(
    days: int = Query(7, description="最近天数"),
    limit: int = Query(20, description="返回数量")
):
    """获取最新研报"""
    try:
        manager = get_report_manager()
        if not manager:
            return {"success": True, "data": []}
        
        reports = manager.get_recent_reports(days=days, limit=limit)
        return {
            "success": True,
            "data": [r.to_dict() for r in reports]
        }
    except Exception as e:
        logger.error(f"获取最新研报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{stock_code}")
async def get_stock_research(
    stock_code: str,
    limit: int = Query(10, description="返回数量")
):
    """获取特定股票的研报"""
    try:
        manager = get_report_manager()
        if not manager:
            return {
                "success": True,
                "data": {
                    "stock_code": stock_code,
                    "reports": [],
                    "statistics": {
                        "total_reports": 0,
                        "rating_distribution": {},
                        "avg_target_price": None,
                        "max_target_price": None,
                        "min_target_price": None
                    }
                }
            }
        
        reports = manager.get_stock_reports(stock_code=stock_code, limit=limit)
        reports_data = [r.to_dict() for r in reports]
        
        # 评级分布
        rating_dist = {}
        for r in reports:
            if r.rating:
                rating_val = r.rating.value
                rating_dist[rating_val] = rating_dist.get(rating_val, 0) + 1
        
        # 目标价统计
        target_prices = [r.target_price for r in reports if r.target_price]
        
        return {
            "success": True,
            "data": {
                "stock_code": stock_code,
                "reports": reports_data,
                "statistics": {
                    "total_reports": len(reports),
                    "rating_distribution": rating_dist,
                    "avg_target_price": round(sum(target_prices) / len(target_prices), 2) if target_prices else None,
                    "max_target_price": max(target_prices) if target_prices else None,
                    "min_target_price": min(target_prices) if target_prices else None
                }
            }
        }
    except Exception as e:
        logger.error(f"获取股票研报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_research(request: SearchRequest):
    """搜索研报"""
    try:
        manager = get_report_manager()
        if not manager:
            return {"success": True, "data": []}
        
        start_date = datetime.fromisoformat(request.date_from) if request.date_from else None
        end_date = datetime.fromisoformat(request.date_to) if request.date_to else None
        
        reports = manager.search_reports(
            keyword=request.keyword,
            stock_code=request.stock_code,
            institution=request.institution,
            start_date=start_date,
            end_date=end_date,
            limit=request.limit
        )
        
        return {
            "success": True,
            "data": [r.to_dict() for r in reports]
        }
    except Exception as e:
        logger.error(f"搜索研报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports")
async def get_reports(
    limit: int = Query(20, description="返回数量"),
    offset: int = Query(0, description="偏移量")
):
    """获取研报列表"""
    try:
        manager = get_report_manager()
        if not manager:
            return {"success": True, "data": []}
        
        reports = manager.search_reports(limit=limit + offset)
        reports = reports[offset:offset + limit]
        
        return {
            "success": True,
            "data": [r.to_dict() for r in reports]
        }
    except Exception as e:
        logger.error(f"获取研报列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{report_id}")
async def get_report_detail(report_id: str):
    """获取研报详情"""
    try:
        manager = get_report_manager()
        if not manager:
            raise HTTPException(status_code=404, detail="研报服务不可用")
        
        report = manager.get_report_by_id(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="研报不存在")
        
        return {
            "success": True,
            "data": report.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取研报详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze_report(request: AnalyzeRequest):
    """AI分析研报"""
    try:
        manager = get_report_manager()
        if not manager:
            raise HTTPException(status_code=503, detail="研报服务不可用")
        
        report = manager.get_report_by_id(request.report_id)
        if not report:
            raise HTTPException(status_code=404, detail="研报不存在")
        
        # 基于真实研报数据返回分析结果
        analysis = {
            "report_id": request.report_id,
            "analysis_type": request.analysis_type,
            "generated_at": datetime.now().isoformat()
        }
        
        if request.analysis_type == "summary":
            analysis["result"] = {
                "executive_summary": report.summary or "暂无摘要",
                "key_thesis": [],
                "valuation_view": f"目标价: {report.target_price}" if report.target_price else "暂无目标价",
                "confidence_score": None
            }
        elif request.analysis_type == "key_points":
            analysis["result"] = {
                "financial_highlights": [],
                "business_updates": [],
                "management_guidance": []
            }
        elif request.analysis_type == "risk":
            analysis["result"] = {
                "identified_risks": [],
                "overall_risk_level": "未知",
                "risk_reward_ratio": "未知"
            }
        elif request.analysis_type == "target":
            analysis["result"] = {
                "current_price": None,
                "target_prices": {
                    "base_case": report.target_price
                } if report.target_price else {},
                "valuation_methods": [],
                "upside_potential": None,
                "time_horizon": "12个月"
            }
        
        return {"success": True, "data": analysis}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分析研报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/institutions")
async def get_institutions():
    """获取研究机构列表"""
    try:
        manager = get_report_manager()
        if not manager:
            return {"success": True, "data": []}
        
        # 从研报数据中统计机构
        institution_stats = {}
        for report in manager.reports:
            inst = report.institution
            if inst not in institution_stats:
                institution_stats[inst] = {"name": inst, "report_count": 0, "analysts": set()}
            institution_stats[inst]["report_count"] += 1
            if report.author:
                institution_stats[inst]["analysts"].add(report.author)
        
        institutions = [
            {
                "name": stats["name"],
                "report_count": stats["report_count"],
                "top_analysts": list(stats["analysts"])[:3]
            }
            for stats in institution_stats.values()
        ]
        
        return {"success": True, "data": institutions}
    except Exception as e:
        logger.error(f"获取机构列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ratings/trend")
async def get_rating_trend(
    stock_code: str = Query(..., description="股票代码"),
    months: int = Query(6, description="月数")
):
    """获取评级变化趋势"""
    try:
        manager = get_report_manager()
        if not manager:
            return {
                "success": True,
                "data": {
                    "stock_code": stock_code,
                    "trend": [],
                    "consensus": {"rating": None, "target_price": None, "analysts_count": 0}
                }
            }
        
        # 获取该股票的所有研报
        reports = manager.search_reports(stock_code=stock_code, limit=1000)
        
        # 按月统计
        trend = []
        for i in range(months):
            month_start = datetime.now().replace(day=1) - timedelta(days=30 * (months - i - 1))
            month_end = month_start + timedelta(days=30)
            
            month_reports = [
                r for r in reports
                if month_start <= r.publish_date < month_end
            ]
            
            buy_count = sum(1 for r in month_reports if r.rating and r.rating.value in ["强烈推荐", "推荐"])
            hold_count = sum(1 for r in month_reports if r.rating and r.rating.value == "中性")
            sell_count = sum(1 for r in month_reports if r.rating and r.rating.value in ["减持", "卖出"])
            
            target_prices = [r.target_price for r in month_reports if r.target_price]
            
            trend.append({
                "month": month_start.strftime("%Y-%m"),
                "buy": buy_count,
                "hold": hold_count,
                "sell": sell_count,
                "avg_target_price": round(sum(target_prices) / len(target_prices), 2) if target_prices else None
            })
        
        # 计算共识
        recent_reports = [r for r in reports if r.publish_date >= datetime.now() - timedelta(days=90)]
        target_prices = [r.target_price for r in recent_reports if r.target_price]
        
        return {
            "success": True,
            "data": {
                "stock_code": stock_code,
                "trend": trend,
                "consensus": {
                    "rating": None,
                    "target_price": round(sum(target_prices) / len(target_prices), 2) if target_prices else None,
                    "analysts_count": len(set(r.author for r in recent_reports if r.author))
                }
            }
        }
    except Exception as e:
        logger.error(f"获取评级趋势失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
