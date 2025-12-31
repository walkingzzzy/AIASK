"""
风险监控路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/risk-monitor", tags=["风险监控"])


class ThresholdUpdateRequest(BaseModel):
    metric: str
    value: float


def _get_risk_monitor():
    try:
        from packages.core.risk_monitor import RiskMonitor
        return RiskMonitor()
    except ImportError:
        return None


@router.get("/check")
async def check_risk():
    """检查组合风险"""
    try:
        monitor = _get_risk_monitor()
        if monitor:
            alerts = monitor.check_all_risks()
            return {"success": True, "data": {"alerts": alerts, "risk_level": "normal"}}
        return {
            "success": True,
            "data": {
                "alerts": [],
                "risk_level": "normal",
                "message": "风险监控模块未加载"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_risk_metrics():
    """获取风险指标"""
    try:
        monitor = _get_risk_monitor()
        if monitor:
            metrics = monitor.get_risk_metrics()
            return {"success": True, "data": metrics}
        return {"success": True, "data": {"var": 0, "max_drawdown": 0, "sharpe_ratio": 0}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thresholds")
async def get_risk_thresholds():
    """获取风险阈值配置"""
    try:
        monitor = _get_risk_monitor()
        if monitor:
            thresholds = monitor.get_thresholds()
            return {"success": True, "data": thresholds}
        return {
            "success": True,
            "data": {"max_position_ratio": 0.3, "stop_loss_ratio": 0.1, "max_drawdown": 0.2}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/thresholds")
async def update_risk_threshold(request: ThresholdUpdateRequest):
    """更新风险阈值"""
    try:
        monitor = _get_risk_monitor()
        if monitor:
            monitor.update_threshold(request.metric, request.value)
            return {"success": True, "message": "阈值更新成功"}
        return {"success": False, "error": "风险监控模块未加载"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
