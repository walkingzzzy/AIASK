"""
风险监控核心模块
"""
import uuid
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from .models import RiskAlert, RiskMetrics, RiskLevel, AlertType, RiskThreshold
from .alert_manager import AlertManager

# 默认配置文件名
DEFAULT_CONFIG_FILENAME = "risk_thresholds.json"


class RiskMonitor:
    """风险监控器"""

    def __init__(self, config_file: Optional[str] = None):
        self.alert_manager = AlertManager()

        # 配置文件路径：优先使用环境变量，其次使用传入参数，最后使用默认路径
        if config_file is None:
            config_file = os.environ.get('RISK_THRESHOLDS_CONFIG')
        
        if config_file is None:
            data_dir = Path(os.environ.get('DATA_DIR',
                           Path(__file__).parent.parent.parent.parent.parent / "data"))
            data_dir = Path(data_dir)
            data_dir.mkdir(exist_ok=True)
            config_file = str(data_dir / DEFAULT_CONFIG_FILENAME)

        self.config_file = config_file
        self.thresholds = self._load_thresholds()
        self.monitoring_active = False

    def _init_default_thresholds(self) -> Dict[str, RiskThreshold]:
        """初始化默认阈值"""
        return {
            "single_loss": RiskThreshold(
                name="单只股票亏损",
                threshold_value=-0.10,  # -10%
                alert_type=AlertType.POSITION_LOSS,
                description="单只股票亏损超过10%"
            ),
            "total_loss": RiskThreshold(
                name="总体亏损",
                threshold_value=-0.15,  # -15%
                alert_type=AlertType.POSITION_LOSS,
                description="组合总体亏损超过15%"
            ),
            "concentration": RiskThreshold(
                name="持仓集中度",
                threshold_value=0.30,  # 30%
                alert_type=AlertType.CONCENTRATION,
                description="单只股票占比超过30%"
            ),
            "price_drop": RiskThreshold(
                name="单日跌幅",
                threshold_value=-0.05,  # -5%
                alert_type=AlertType.PRICE_DROP,
                description="单日跌幅超过5%"
            )
        }

    def _load_thresholds(self) -> Dict[str, RiskThreshold]:
        """从文件加载阈值配置"""
        try:
            if Path(self.config_file).exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    thresholds = {}
                    for key, value in data.items():
                        thresholds[key] = RiskThreshold(
                            name=value['name'],
                            threshold_value=value['threshold_value'],
                            alert_type=AlertType(value['alert_type']),
                            description=value['description'],
                            enabled=value.get('enabled', True)
                        )
                    return thresholds
        except Exception as e:
            print(f"加载阈值配置失败: {e}")

        # 如果加载失败或文件不存在，使用默认值并保存
        default_thresholds = self._init_default_thresholds()
        self._save_thresholds(default_thresholds)
        return default_thresholds

    def _save_thresholds(self, thresholds: Optional[Dict[str, RiskThreshold]] = None):
        """保存阈值配置到文件"""
        if thresholds is None:
            thresholds = self.thresholds

        try:
            data = {}
            for key, threshold in thresholds.items():
                data[key] = {
                    'name': threshold.name,
                    'threshold_value': threshold.threshold_value,
                    'alert_type': threshold.alert_type.value,
                    'description': threshold.description,
                    'enabled': threshold.enabled
                }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存阈值配置失败: {e}")

    def check_portfolio_risk(self, positions: List[Dict[str, Any]]) -> List[RiskAlert]:
        """
        检查组合风险

        Args:
            positions: 持仓列表

        Returns:
            风险告警列表
        """
        alerts = []

        if not positions:
            return alerts

        # 计算总市值
        total_value = sum(p.get('market_value', 0) for p in positions)
        total_cost = sum(p.get('cost', 0) for p in positions)

        # 检查总体亏损
        if total_cost > 0:
            total_loss_pct = (total_value - total_cost) / total_cost
            threshold = self.thresholds["total_loss"]
            if threshold.enabled and total_loss_pct < threshold.threshold_value:
                alert = RiskAlert(
                    alert_id=str(uuid.uuid4()),
                    alert_type=AlertType.POSITION_LOSS,
                    risk_level=RiskLevel.HIGH,
                    title="组合总体亏损告警",
                    message=f"组合总体亏损{total_loss_pct:.2%}，超过阈值{threshold.threshold_value:.2%}",
                    current_value=total_loss_pct,
                    threshold_value=threshold.threshold_value
                )
                alerts.append(alert)

        # 检查单只股票风险
        for position in positions:
            stock_code = position.get('stock_code')
            stock_name = position.get('stock_name', stock_code)
            profit_loss_pct = position.get('profit_loss_pct', 0)
            market_value = position.get('market_value', 0)

            # 单只亏损检查
            threshold = self.thresholds["single_loss"]
            if threshold.enabled and profit_loss_pct < threshold.threshold_value:
                alert = RiskAlert(
                    alert_id=str(uuid.uuid4()),
                    alert_type=AlertType.POSITION_LOSS,
                    risk_level=RiskLevel.MEDIUM,
                    title=f"{stock_name}亏损告警",
                    message=f"{stock_name}({stock_code})亏损{profit_loss_pct:.2%}",
                    stock_code=stock_code,
                    stock_name=stock_name,
                    current_value=profit_loss_pct,
                    threshold_value=threshold.threshold_value
                )
                alerts.append(alert)

            # 持仓集中度检查
            if total_value > 0:
                concentration = market_value / total_value
                threshold = self.thresholds["concentration"]
                if threshold.enabled and concentration > threshold.threshold_value:
                    alert = RiskAlert(
                        alert_id=str(uuid.uuid4()),
                        alert_type=AlertType.CONCENTRATION,
                        risk_level=RiskLevel.MEDIUM,
                        title=f"{stock_name}持仓集中",
                        message=f"{stock_name}({stock_code})占比{concentration:.2%}，建议分散投资",
                        stock_code=stock_code,
                        stock_name=stock_name,
                        current_value=concentration,
                        threshold_value=threshold.threshold_value
                    )
                    alerts.append(alert)

        return alerts

    def calculate_risk_metrics(self, positions: List[Dict[str, Any]]) -> RiskMetrics:
        """计算风险指标"""
        if not positions:
            return RiskMetrics(
                portfolio_value=0,
                total_loss=0,
                loss_percentage=0,
                max_single_loss=0,
                concentration_risk=0,
                volatility=0,
                risk_level=RiskLevel.LOW
            )

        total_value = sum(p.get('market_value', 0) for p in positions)
        total_cost = sum(p.get('cost', 0) for p in positions)
        total_loss = total_value - total_cost
        loss_pct = total_loss / total_cost if total_cost > 0 else 0

        # 最大单只亏损
        max_single_loss = min([p.get('profit_loss_pct', 0) for p in positions], default=0)

        # 持仓集中度（最大单只占比）
        concentration = max([p.get('market_value', 0) / total_value for p in positions], default=0) if total_value > 0 else 0

        # 简单波动率估算
        volatility = 0.0

        # 风险等级评估
        risk_level = self._assess_risk_level(loss_pct, max_single_loss, concentration)

        return RiskMetrics(
            portfolio_value=total_value,
            total_loss=total_loss,
            loss_percentage=loss_pct,
            max_single_loss=max_single_loss,
            concentration_risk=concentration,
            volatility=volatility,
            risk_level=risk_level
        )

    def _assess_risk_level(self, loss_pct: float, max_single_loss: float, concentration: float) -> RiskLevel:
        """评估风险等级"""
        if loss_pct < -0.20 or max_single_loss < -0.15 or concentration > 0.50:
            return RiskLevel.CRITICAL
        elif loss_pct < -0.10 or max_single_loss < -0.10 or concentration > 0.30:
            return RiskLevel.HIGH
        elif loss_pct < -0.05 or max_single_loss < -0.05 or concentration > 0.20:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def update_threshold(self, threshold_name: str, new_value: float) -> bool:
        """更新阈值并持久化"""
        if threshold_name in self.thresholds:
            self.thresholds[threshold_name].threshold_value = new_value
            self._save_thresholds()
            return True
        return False

    def get_all_thresholds(self) -> List[Dict[str, Any]]:
        """获取所有阈值配置"""
        return [t.to_dict() for t in self.thresholds.values()]
