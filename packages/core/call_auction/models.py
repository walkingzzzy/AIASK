"""
竞价监控数据模型
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict


@dataclass
class Alert:
    """
    预警信息数据类
    Attributes:
        stock_code: 股票代码
        stock_name: 股票名称
        alert_type: 预警类型（如：涨停预期、大单涌入、异动等）
        message: 预警消息
        priority: 优先级（1-5，5最高）
        timestamp: 预警时间戳
        data: 附加数据
    """
    stock_code: str
    stock_name: str
    alert_type: str
    message: str
    priority: int
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result
    
    def __str__(self) -> str:
        return f"[{self.alert_type}] {self.stock_code} {self.stock_name}: {self.message}"