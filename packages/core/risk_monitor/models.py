"""
风险监控数据模型
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class RiskLevel(Enum):
    """风险等级"""
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    CRITICAL = "极高风险"


class AlertType(Enum):
    """告警类型"""
    PRICE_DROP = "价格下跌"
    POSITION_LOSS = "持仓亏损"
    CONCENTRATION = "持仓集中"
    VOLATILITY = "波动率异常"
    LIQUIDITY = "流动性风险"
    MARKET_CRASH = "市场暴跌"


@dataclass
class RiskThreshold:
    """风险阈值配置"""
    name: str
    threshold_value: float
    alert_type: AlertType
    enabled: bool = True
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "threshold_value": self.threshold_value,
            "alert_type": self.alert_type.value,
            "enabled": self.enabled,
            "description": self.description
        }


@dataclass
class RiskAlert:
    """风险告警"""
    alert_id: str
    alert_type: AlertType
    risk_level: RiskLevel
    title: str
    message: str
    stock_code: Optional[str] = None
    stock_name: Optional[str] = None
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "risk_level": self.risk_level.value,
            "title": self.title,
            "message": self.message,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


@dataclass
class RiskMetrics:
    """风险指标"""
    portfolio_value: float
    total_loss: float
    loss_percentage: float
    max_single_loss: float
    concentration_risk: float
    volatility: float
    risk_level: RiskLevel
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portfolio_value": self.portfolio_value,
            "total_loss": self.total_loss,
            "loss_percentage": self.loss_percentage,
            "max_single_loss": self.max_single_loss,
            "concentration_risk": self.concentration_risk,
            "volatility": self.volatility,
            "risk_level": self.risk_level.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
