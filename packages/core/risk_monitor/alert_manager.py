"""
告警管理器
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .models import RiskAlert
from .notification import NotificationChannel

logger = logging.getLogger(__name__)


class AlertManager:
    """告警管理器"""

    def __init__(self, persistence_path: Optional[str] = None):
        self.alert_history: List[RiskAlert] = []
        self.notification_channels: List[NotificationChannel] = []
        self.max_history_size = 1000
        self.persistence_path = persistence_path
        
        # 如果指定了持久化路径，加载历史告警
        if self.persistence_path:
            self._load_alerts()

    def add_alert(self, alert: RiskAlert) -> None:
        """添加告警"""
        self.alert_history.append(alert)

        # 限制历史记录大小
        if len(self.alert_history) > self.max_history_size:
            self.alert_history = self.alert_history[-self.max_history_size:]

        # 持久化保存
        if self.persistence_path:
            self._save_alerts()

        # 发送通知
        self._send_notifications(alert)

    def add_alerts(self, alerts: List[RiskAlert]) -> None:
        """批量添加告警"""
        for alert in alerts:
            self.add_alert(alert)

    def get_recent_alerts(self, hours: int = 24) -> List[RiskAlert]:
        """获取最近的告警"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alert_history
            if alert.timestamp and alert.timestamp >= cutoff_time
        ]

    def get_alerts_by_stock(self, stock_code: str) -> List[RiskAlert]:
        """获取特定股票的告警"""
        return [
            alert for alert in self.alert_history
            if alert.stock_code == stock_code
        ]

    def clear_old_alerts(self, days: int = 7) -> int:
        """清理旧告警"""
        cutoff_time = datetime.now() - timedelta(days=days)
        original_count = len(self.alert_history)
        self.alert_history = [
            alert for alert in self.alert_history
            if alert.timestamp and alert.timestamp >= cutoff_time
        ]
        return original_count - len(self.alert_history)

    def register_notification_channel(self, channel: NotificationChannel) -> None:
        """注册通知渠道"""
        self.notification_channels.append(channel)

    def _send_notifications(self, alert: RiskAlert) -> None:
        """发送通知"""
        for channel in self.notification_channels:
            try:
                channel.send(alert)
            except Exception as e:
                print(f"Failed to send notification via {channel.__class__.__name__}: {e}")

    def get_alert_statistics(self) -> Dict[str, Any]:
        """获取告警统计"""
        if not self.alert_history:
            return {
                "total_alerts": 0,
                "by_type": {},
                "by_risk_level": {}
            }

        by_type = {}
        by_risk_level = {}

        for alert in self.alert_history:
            # 按类型统计
            alert_type = alert.alert_type.value
            by_type[alert_type] = by_type.get(alert_type, 0) + 1

            # 按风险等级统计
            risk_level = alert.risk_level.value
            by_risk_level[risk_level] = by_risk_level.get(risk_level, 0) + 1

        return {
            "total_alerts": len(self.alert_history),
            "by_type": by_type,
            "by_risk_level": by_risk_level
        }

    def _save_alerts(self) -> None:
        """持久化保存告警历史"""
        if not self.persistence_path:
            return
        try:
            path = Path(self.persistence_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = [alert.to_dict() for alert in self.alert_history]
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"保存告警历史失败: {e}")

    def _load_alerts(self) -> None:
        """加载告警历史"""
        if not self.persistence_path:
            return
        try:
            path = Path(self.persistence_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.alert_history = [RiskAlert.from_dict(d) for d in data]
                logger.info(f"加载了 {len(self.alert_history)} 条告警历史")
        except Exception as e:
            logger.error(f"加载告警历史失败: {e}")
