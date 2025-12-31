"""
健康检查API路由
提供各数据源和服务的健康状态检查
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["健康检查"])


# ==================== 数据源健康检查 ====================

@router.get("/datasources")
async def check_datasources():
    """
    检查各数据源状态
    
    返回 AKShare、Tushare、实时行情等数据源的可用性
    """
    try:
        results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "sources": {}
        }
        
        unhealthy_count = 0
        
        # 1. 检查AKShare数据源
        akshare_status = await _check_akshare()
        results["sources"]["akshare"] = akshare_status
        if not akshare_status["available"]:
            unhealthy_count += 1
        
        # 2. 检查Tushare数据源
        tushare_status = await _check_tushare()
        results["sources"]["tushare"] = tushare_status
        if not tushare_status["available"]:
            unhealthy_count += 1
        
        # 3. 检查实时行情数据源
        realtime_status = await _check_realtime_sources()
        results["sources"]["realtime"] = realtime_status
        if not realtime_status["available"]:
            unhealthy_count += 1
        
        # 4. 检查缓存服务
        cache_status = await _check_cache()
        results["sources"]["cache"] = cache_status
        
        # 计算总体状态
        total_sources = 3  # akshare, tushare, realtime
        if unhealthy_count == 0:
            results["overall_status"] = "healthy"
            results["message"] = "所有数据源正常"
        elif unhealthy_count < total_sources:
            results["overall_status"] = "degraded"
            results["message"] = f"{unhealthy_count}/{total_sources} 个数据源不可用"
        else:
            results["overall_status"] = "unhealthy"
            results["message"] = "所有数据源不可用"
        
        return {
            "success": True,
            "data": results
        }
        
    except Exception as e:
        logger.error(f"数据源健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasources/akshare")
async def check_akshare_detail():
    """检查AKShare数据源详情"""
    try:
        status = await _check_akshare(detailed=True)
        return {"success": True, "data": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasources/tushare")
async def check_tushare_detail():
    """检查Tushare数据源详情"""
    try:
        status = await _check_tushare(detailed=True)
        return {"success": True, "data": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasources/realtime")
async def check_realtime_detail():
    """检查实时行情数据源详情"""
    try:
        status = await _check_realtime_sources(detailed=True)
        return {"success": True, "data": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 辅助检查函数 ====================

async def _check_akshare(detailed: bool = False) -> Dict[str, Any]:
    """检查AKShare数据源"""
    result = {
        "name": "AKShare",
        "type": "historical_data",
        "available": False,
        "status": "unknown",
        "message": "",
        "last_check": datetime.now().isoformat()
    }
    
    try:
        import akshare as ak
        
        # 尝试获取简单数据验证连接
        try:
            # 获取一个简单的数据来验证
            df = ak.stock_zh_a_spot_em()
            if df is not None and len(df) > 0:
                result["available"] = True
                result["status"] = "healthy"
                result["message"] = f"连接正常，获取到 {len(df)} 条实时数据"
                
                if detailed:
                    result["sample_data_count"] = len(df)
                    result["version"] = getattr(ak, '__version__', 'unknown')
            else:
                result["status"] = "error"
                result["message"] = "返回数据为空"
        except Exception as e:
            result["status"] = "error"
            result["message"] = f"数据获取失败: {str(e)}"
            
    except ImportError:
        result["status"] = "not_installed"
        result["message"] = "AKShare未安装"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


async def _check_tushare(detailed: bool = False) -> Dict[str, Any]:
    """检查Tushare数据源"""
    result = {
        "name": "Tushare",
        "type": "financial_data",
        "available": False,
        "status": "unknown",
        "message": "",
        "configured": False,
        "last_check": datetime.now().isoformat()
    }
    
    # 检查API Token配置
    tushare_token = os.getenv("TUSHARE_TOKEN")
    if not tushare_token or tushare_token.startswith("your_"):
        result["status"] = "not_configured"
        result["message"] = "Tushare API Token 未配置"
        return result
    
    result["configured"] = True
    
    try:
        import tushare as ts
        
        ts.set_token(tushare_token)
        pro = ts.pro_api()
        
        # 尝试获取简单数据验证连接
        try:
            df = pro.trade_cal(exchange='SSE', start_date='20240101', end_date='20240110')
            if df is not None and len(df) > 0:
                result["available"] = True
                result["status"] = "healthy"
                result["message"] = "连接正常"
                
                if detailed:
                    result["version"] = getattr(ts, '__version__', 'unknown')
            else:
                result["status"] = "error"
                result["message"] = "返回数据为空"
        except Exception as e:
            error_msg = str(e)
            if "积分" in error_msg or "权限" in error_msg:
                result["status"] = "limited"
                result["message"] = "API访问受限（积分不足或权限不够）"
                result["available"] = True  # 部分可用
            else:
                result["status"] = "error"
                result["message"] = f"数据获取失败: {error_msg}"
            
    except ImportError:
        result["status"] = "not_installed"
        result["message"] = "Tushare未安装"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


async def _check_realtime_sources(detailed: bool = False) -> Dict[str, Any]:
    """检查实时行情数据源"""
    result = {
        "name": "实时行情",
        "type": "realtime_quote",
        "available": False,
        "status": "unknown",
        "message": "",
        "sources": {},
        "last_check": datetime.now().isoformat()
    }
    
    try:
        from packages.core.realtime import DataSourceManager
        
        manager = DataSourceManager()
        status_report = manager.get_overall_status()
        
        result["available"] = status_report.get("available_sources", 0) > 0
        result["status"] = status_report.get("overall_state", "unknown")
        result["message"] = status_report.get("message", "")
        result["sources"] = status_report.get("sources", {})
        result["primary_source"] = status_report.get("primary_source")
        result["primary_available"] = status_report.get("primary_available", False)
        
        if detailed:
            result["auto_reconnect_enabled"] = status_report.get("auto_reconnect_enabled", False)
            result["available_count"] = status_report.get("available_sources", 0)
            result["total_count"] = status_report.get("total_sources", 0)
        
    except ImportError as e:
        result["status"] = "not_installed"
        result["message"] = f"实时行情模块未安装: {e}"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


async def _check_cache() -> Dict[str, Any]:
    """检查缓存服务"""
    result = {
        "name": "缓存服务",
        "type": "cache",
        "available": False,
        "status": "unknown",
        "message": "",
        "last_check": datetime.now().isoformat()
    }
    
    try:
        from packages.core.data_layer.cache.cache_manager import get_cache_manager
        
        cache = get_cache_manager()
        stats = cache.stats()
        
        result["available"] = True
        result["status"] = "healthy"
        result["message"] = "缓存服务正常"
        result["stats"] = stats
        
    except ImportError:
        result["status"] = "not_installed"
        result["message"] = "缓存模块未安装"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


# ==================== 综合健康检查 ====================

@router.get("")
async def health_check():
    """
    综合健康检查
    
    检查API服务、数据库和关键组件的状态
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "components": {}
        }
        
        # API服务状态
        health_status["components"]["api"] = {
            "status": "healthy",
            "message": "API服务运行正常"
        }
        
        # 数据库状态
        try:
            from packages.core.data_layer.cache.cache_manager import get_cache_manager
            cache = get_cache_manager()
            cache.stats()
            health_status["components"]["database"] = {
                "status": "healthy",
                "message": "数据库连接正常"
            }
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "message": f"数据库连接失败: {str(e)}"
            }
            health_status["status"] = "degraded"
        
        # AI服务状态
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key and not api_key.startswith("your_"):
                health_status["components"]["ai_service"] = {
                    "status": "healthy",
                    "message": "AI服务已配置"
                }
            else:
                health_status["components"]["ai_service"] = {
                    "status": "degraded",
                    "message": "AI服务未配置，使用降级模式"
                }
        except Exception:
            health_status["components"]["ai_service"] = {
                "status": "unknown",
                "message": "无法检测AI服务状态"
            }
        
        return {
            "success": True,
            "data": health_status
        }
        
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "success": False,
            "data": {
                "status": "unhealthy",
                "error": str(e)
            }
        }
