"""
通知渠道
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from .models import RiskAlert


class NotificationChannel(ABC):
    """通知渠道基类"""

    @abstractmethod
    def send(self, alert: RiskAlert) -> bool:
        """发送通知"""
        pass


class ConsoleNotification(NotificationChannel):
    """控制台通知"""

    def send(self, alert: RiskAlert) -> bool:
        """打印到控制台"""
        print(f"\n{'='*60}")
        print(f"[{alert.risk_level.value}] {alert.title}")
        print(f"时间: {alert.timestamp}")
        print(f"消息: {alert.message}")
        if alert.stock_code:
            print(f"股票: {alert.stock_name}({alert.stock_code})")
        if alert.current_value is not None:
            print(f"当前值: {alert.current_value:.2%}")
        if alert.threshold_value is not None:
            print(f"阈值: {alert.threshold_value:.2%}")
        print(f"{'='*60}\n")
        return True


class LogNotification(NotificationChannel):
    """日志通知"""

    def __init__(self, log_file: str = "risk_alerts.log"):
        self.log_file = log_file

    def send(self, alert: RiskAlert) -> bool:
        """写入日志文件"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"{alert.timestamp} | {alert.risk_level.value} | {alert.title} | {alert.message}\n")
            return True
        except Exception as e:
            print(f"Failed to write log: {e}")
            return False


class WebhookNotification(NotificationChannel):
    """Webhook通知"""

    def __init__(self, webhook_url: str, timeout: int = 10):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, alert: RiskAlert) -> bool:
        """发送到Webhook"""
        try:
            import requests

            payload = {
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type.value,
                "risk_level": alert.risk_level.value,
                "title": alert.title,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "stock_code": alert.stock_code,
                "stock_name": alert.stock_name,
                "current_value": alert.current_value,
                "threshold_value": alert.threshold_value
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                return True
            else:
                print(f"Webhook failed with status {response.status_code}: {response.text}")
                return False

        except ImportError:
            print("requests库未安装，无法发送Webhook通知")
            return False
        except Exception as e:
            print(f"Webhook发送失败: {e}")
            return False


class EmailNotification(NotificationChannel):
    """邮件通知"""

    def __init__(self, smtp_config: Dict[str, Any]):
        """
        Args:
            smtp_config: SMTP配置
                - host: SMTP服务器地址
                - port: SMTP端口
                - username: 发件人邮箱
                - password: 邮箱密码或授权码
                - from_addr: 发件人地址
                - to_addrs: 收件人地址列表
                - use_tls: 是否使用TLS (默认True)
        """
        self.smtp_config = smtp_config

    def send(self, alert: RiskAlert) -> bool:
        """发送邮件"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # 构建邮件内容
            msg = MIMEMultipart()
            msg['From'] = self.smtp_config.get('from_addr', self.smtp_config['username'])
            msg['To'] = ', '.join(self.smtp_config['to_addrs'])
            msg['Subject'] = f"[{alert.risk_level.value}] {alert.title}"

            # 邮件正文
            body = f"""
风险告警通知

告警类型: {alert.alert_type.value}
风险等级: {alert.risk_level.value}
告警时间: {alert.timestamp}

{alert.message}
"""
            if alert.stock_code:
                body += f"\n股票代码: {alert.stock_code}"
                body += f"\n股票名称: {alert.stock_name}"

            if alert.current_value is not None:
                body += f"\n当前值: {alert.current_value:.2%}"

            if alert.threshold_value is not None:
                body += f"\n阈值: {alert.threshold_value:.2%}"

            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            # 发送邮件
            use_tls = self.smtp_config.get('use_tls', True)
            server = smtplib.SMTP(
                self.smtp_config['host'],
                self.smtp_config['port']
            )

            if use_tls:
                server.starttls()

            server.login(
                self.smtp_config['username'],
                self.smtp_config['password']
            )

            server.send_message(msg)
            server.quit()

            return True

        except Exception as e:
            print(f"邮件发送失败: {e}")
            return False
