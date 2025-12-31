"""
竞价监控预警规则
"""
import statistics
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .models import Alert


class AlertRule(ABC):
    """
    预警规则基类Attributes:
        name: 规则名称
        condition: 条件函数（可选）
        priority: 优先级
        enabled: 是否启用
    """
    
    def __init__(self, 
                 name: str, 
                 condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
                 priority: int = 1,
                 enabled: bool = True):
        """
        初始化预警规则
        
        Args:
            name: 规则名称
            condition: 条件判断函数，接收数据字典，返回是否触发
            priority: 优先级（1-5，5最高）
            enabled: 是否启用该规则
        """
        self.name = name
        self.condition = condition
        self.priority = priority
        self.enabled = enabled
    
    @abstractmethod
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        """
        检查是否触发预警
        
        Args:
            data: 股票竞价数据字典
            
        Returns:
            触发预警时返回Alert对象，否则返回None
        """
        pass
    
    def _create_alert(self, stock_code: str, stock_name: str, alert_type: str,message: str, data: Dict[str, Any]) -> Alert:
        """创建预警对象的辅助方法"""
        return Alert(
            stock_code=stock_code,
            stock_name=stock_name,
            alert_type=alert_type,
            message=message,
            priority=self.priority,
            timestamp=datetime.now(),
            data=data
        )


class HighOpenRule(AlertRule):
    """
    高开预警规则
    当竞价涨幅超过阈值时触发
    """
    
    def __init__(self, threshold: float = 5.0, priority: int = 2):
        super().__init__(name="高开预警", priority=priority)
        self.threshold = threshold
    
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        if not self.enabled:
            return None
        change = data.get('auction_change', 0)
        if change >= self.threshold:
            return self._create_alert(
                stock_code=data.get('stock_code', ''),
                stock_name=data.get('stock_name', ''),
                alert_type='高开预警',
                message=f"竞价涨幅 {change:.2f}%，超过阈值 {self.threshold}%",
                data={'change': change, 'threshold': self.threshold}
            )
        return None


class LowOpenRule(AlertRule):
    """
    低开预警规则
    当竞价跌幅超过阈值时触发
    """
    
    def __init__(self, threshold: float = -5.0, priority: int = 2):
        super().__init__(name="低开预警", priority=priority)
        self.threshold = threshold
    
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        if not self.enabled:
            return None
        change = data.get('auction_change', 0)
        if change <= self.threshold:
            return self._create_alert(
                stock_code=data.get('stock_code', ''),
                stock_name=data.get('stock_name', ''),
                alert_type='低开预警',
                message=f"竞价跌幅 {change:.2f}%，超过阈值 {self.threshold}%",
                data={'change': change, 'threshold': self.threshold}
            )
        return None


class VolumeAnomalyRule(AlertRule):
    """
    成交量异常预警规则
    当竞价成交量超过前5日均量的指定倍数时触发
    """
    
    def __init__(self, multiplier: float = 2.0, priority: int = 3):
        super().__init__(name="成交量异常", priority=priority)
        self.multiplier = multiplier
    
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        if not self.enabled:
            return None
        volume_ratio = data.get('volume_ratio', 1.0)
        if volume_ratio >= self.multiplier:
            return self._create_alert(
                stock_code=data.get('stock_code', ''),
                stock_name=data.get('stock_name', ''),
                alert_type='成交量异常',
                message=f"量比 {volume_ratio:.2f}，超过阈值 {self.multiplier}倍",
                data={'volume_ratio': volume_ratio, 'multiplier': self.multiplier}
            )
        return None


class LimitUpExpectedRule(AlertRule):
    """
    涨停预期预警规则
    当竞价涨幅超过9%时触发，预示可能涨停
    """
    
    def __init__(self, threshold: float = 9.0, priority: int = 5):
        super().__init__(name="涨停预期", priority=priority)
        self.threshold = threshold
    
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        if not self.enabled:
            return None
        change = data.get('auction_change', 0)
        if change >= self.threshold:
            return self._create_alert(
                stock_code=data.get('stock_code', ''),
                stock_name=data.get('stock_name', ''),
                alert_type='涨停预期',
                message=f"竞价涨幅 {change:.2f}%，可能冲击涨停",
                data={'change': change, 'threshold': self.threshold}
            )
        return None


class LimitDownExpectedRule(AlertRule):
    """
    跌停预期预警规则
    当竞价跌幅超过-9%时触发，预示可能跌停
    """
    
    def __init__(self, threshold: float = -9.0, priority: int = 5):
        super().__init__(name="跌停预期", priority=priority)
        self.threshold = threshold
    
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        if not self.enabled:
            return None
        change = data.get('auction_change', 0)
        if change <= self.threshold:
            return self._create_alert(
                stock_code=data.get('stock_code', ''),
                stock_name=data.get('stock_name', ''),
                alert_type='跌停预期',
                message=f"竞价跌幅 {change:.2f}%，可能冲击跌停",
                data={'change': change, 'threshold': self.threshold}
            )
        return None


class BigOrderRule(AlertRule):
    """
    大单涌入预警规则
    当单笔净流入超过阈值时触发
    """
    
    def __init__(self, threshold: float = 1000000, priority: int = 4):
        super().__init__(name="大单涌入", priority=priority)
        self.threshold = threshold
    
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        if not self.enabled:
            return None
        net_inflow = data.get('net_inflow', 0)
        if net_inflow >= self.threshold:
            inflow_wan = net_inflow / 10000
            threshold_wan = self.threshold / 10000
            return self._create_alert(
                stock_code=data.get('stock_code', ''),
                stock_name=data.get('stock_name', ''),
                alert_type='大单涌入',
                message=f"净流入 {inflow_wan:.2f}万元，超过阈值 {threshold_wan:.2f}万",
                data={'net_inflow': net_inflow, 'threshold': self.threshold}
            )
        return None


class PriceVolatilityRule(AlertRule):
    """
    价格波动预警规则
    当竞价期间价格波动剧烈时触发
    """
    
    def __init__(self, volatility_threshold: float = 3.0, priority: int = 3):
        super().__init__(name="价格波动异常", priority=priority)
        self.volatility_threshold = volatility_threshold
        self._price_history: Dict[str, List[float]] = {}
    
    def update_price(self, stock_code: str, price: float) -> None:
        """更新价格历史"""
        if stock_code not in self._price_history:
            self._price_history[stock_code] = []
        self._price_history[stock_code].append(price)
        if len(self._price_history[stock_code]) > 20:
            self._price_history[stock_code] = self._price_history[stock_code][-20:]
    
    def check(self, data: Dict[str, Any]) -> Optional[Alert]:
        if not self.enabled:
            return None
        stock_code = data.get('stock_code', '')
        current_price = data.get('auction_price', 0)
        
        if current_price > 0:
            self.update_price(stock_code, current_price)
        
        prices = self._price_history.get(stock_code, [])
        if len(prices) < 5:
            return None
        
        try:
            mean_price = statistics.mean(prices[:-1])
            std_price = statistics.stdev(prices[:-1])
            if std_price > 0:
                z_score = abs(current_price - mean_price) / std_price
                if z_score >= self.volatility_threshold:
                    return self._create_alert(
                        stock_code=stock_code,
                        stock_name=data.get('stock_name', ''),
                        alert_type='价格波动异常',
                        message=f"价格波动剧烈，偏离度 {z_score:.2f}倍标准差",
                        data={
                            'current_price': current_price,
                            'mean_price': mean_price,
                            'std_price': std_price,
                            'z_score': z_score
                        }
                    )
        except statistics.StatisticsError:
            pass
        return None