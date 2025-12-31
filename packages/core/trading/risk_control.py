"""
风险控制模块
提供交易风险管理和控制功能
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskLimit:
    """风险限制配置"""
    # 单笔交易限制
    max_single_trade_amount: float = 100000  # 单笔最大交易金额
    max_single_position_pct: float = 0.1  # 单个持仓最大占比

    # 日内交易限制
    max_daily_trades: int = 50  # 日内最大交易次数
    max_daily_loss: float = 50000  # 日内最大亏损
    max_daily_loss_pct: float = 0.05  # 日内最大亏损比例

    # 持仓限制
    max_total_position_pct: float = 0.8  # 最大总持仓比例
    max_stock_count: int = 20  # 最大持仓股票数量

    # 止损止盈
    default_stop_loss_pct: float = 0.05  # 默认止损比例
    default_take_profit_pct: float = 0.15  # 默认止盈比例

    # 杠杆限制
    max_leverage: float = 1.0  # 最大杠杆倍数


@dataclass
class RiskAlert:
    """风险警报"""
    level: RiskLevel
    type: str
    message: str
    timestamp: datetime
    data: Dict


class RiskController:
    """
    风险控制器

    功能：
    1. 交易前风险检查
    2. 持仓风险监控
    3. 止损止盈管理
    4. 风险预警
    """

    def __init__(self, limits: Optional[RiskLimit] = None):
        """
        初始化风险控制器

        Args:
            limits: 风险限制配置
        """
        self.limits = limits or RiskLimit()
        self.alerts: List[RiskAlert] = []

        # 交易统计
        self.daily_trades_count = 0
        self.daily_pnl = 0.0
        self.last_reset_date = datetime.now().date()

    def check_order(
        self,
        order_amount: float,
        stock_code: str,
        portfolio_value: float,
        current_positions: Dict[str, Dict]
    ) -> Tuple[bool, Optional[str]]:
        """
        检查订单是否符合风险控制要求

        Args:
            order_amount: 订单金额
            stock_code: 股票代码
            portfolio_value: 组合总价值
            current_positions: 当前持仓

        Returns:
            (是否通过, 拒绝原因)
        """
        # 重置日内统计
        self._reset_daily_stats_if_needed()

        # 1. 检查单笔交易金额
        if order_amount > self.limits.max_single_trade_amount:
            reason = f"单笔交易金额超限: {order_amount:.2f} > {self.limits.max_single_trade_amount:.2f}"
            self._add_alert(RiskLevel.HIGH, "ORDER_AMOUNT_EXCEEDED", reason)
            return False, reason

        # 2. 检查单个持仓占比
        position_pct = order_amount / portfolio_value
        if position_pct > self.limits.max_single_position_pct:
            reason = f"单个持仓占比超限: {position_pct:.2%} > {self.limits.max_single_position_pct:.2%}"
            self._add_alert(RiskLevel.HIGH, "POSITION_PCT_EXCEEDED", reason)
            return False, reason

        # 3. 检查日内交易次数
        if self.daily_trades_count >= self.limits.max_daily_trades:
            reason = f"日内交易次数超限: {self.daily_trades_count} >= {self.limits.max_daily_trades}"
            self._add_alert(RiskLevel.MEDIUM, "DAILY_TRADES_EXCEEDED", reason)
            return False, reason

        # 4. 检查日内亏损
        if self.daily_pnl < -self.limits.max_daily_loss:
            reason = f"日内亏损超限: {self.daily_pnl:.2f} < -{self.limits.max_daily_loss:.2f}"
            self._add_alert(RiskLevel.CRITICAL, "DAILY_LOSS_EXCEEDED", reason)
            return False, reason

        daily_loss_pct = abs(self.daily_pnl) / portfolio_value
        if self.daily_pnl < 0 and daily_loss_pct > self.limits.max_daily_loss_pct:
            reason = f"日内亏损比例超限: {daily_loss_pct:.2%} > {self.limits.max_daily_loss_pct:.2%}"
            self._add_alert(RiskLevel.CRITICAL, "DAILY_LOSS_PCT_EXCEEDED", reason)
            return False, reason

        # 5. 检查总持仓比例
        total_position_value = sum(pos['market_value'] for pos in current_positions.values())
        total_position_pct = (total_position_value + order_amount) / portfolio_value
        if total_position_pct > self.limits.max_total_position_pct:
            reason = f"总持仓比例超限: {total_position_pct:.2%} > {self.limits.max_total_position_pct:.2%}"
            self._add_alert(RiskLevel.HIGH, "TOTAL_POSITION_EXCEEDED", reason)
            return False, reason

        # 6. 检查持仓股票数量
        if stock_code not in current_positions and len(current_positions) >= self.limits.max_stock_count:
            reason = f"持仓股票数量超限: {len(current_positions)} >= {self.limits.max_stock_count}"
            self._add_alert(RiskLevel.MEDIUM, "STOCK_COUNT_EXCEEDED", reason)
            return False, reason

        return True, None

    def check_stop_loss(
        self,
        stock_code: str,
        current_price: float,
        cost_price: float,
        stop_loss_pct: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        检查是否触发止损

        Args:
            stock_code: 股票代码
            current_price: 当前价格
            cost_price: 成本价
            stop_loss_pct: 止损比例（可选）

        Returns:
            (是否触发, 亏损比例)
        """
        stop_loss_pct = stop_loss_pct or self.limits.default_stop_loss_pct
        loss_pct = (current_price - cost_price) / cost_price

        if loss_pct <= -stop_loss_pct:
            self._add_alert(
                RiskLevel.HIGH,
                "STOP_LOSS_TRIGGERED",
                f"{stock_code} 触发止损: {loss_pct:.2%}"
            )
            return True, loss_pct

        return False, loss_pct

    def check_take_profit(
        self,
        stock_code: str,
        current_price: float,
        cost_price: float,
        take_profit_pct: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        检查是否触发止盈

        Args:
            stock_code: 股票代码
            current_price: 当前价格
            cost_price: 成本价
            take_profit_pct: 止盈比例（可选）

        Returns:
            (是否触发, 盈利比例)
        """
        take_profit_pct = take_profit_pct or self.limits.default_take_profit_pct
        profit_pct = (current_price - cost_price) / cost_price

        if profit_pct >= take_profit_pct:
            self._add_alert(
                RiskLevel.LOW,
                "TAKE_PROFIT_TRIGGERED",
                f"{stock_code} 触发止盈: {profit_pct:.2%}"
            )
            return True, profit_pct

        return False, profit_pct

    def update_daily_pnl(self, pnl: float):
        """更新日内盈亏"""
        self._reset_daily_stats_if_needed()
        self.daily_pnl += pnl

    def increment_trade_count(self):
        """增加交易次数"""
        self._reset_daily_stats_if_needed()
        self.daily_trades_count += 1

    def _reset_daily_stats_if_needed(self):
        """如果需要，重置日内统计"""
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_trades_count = 0
            self.daily_pnl = 0.0
            self.last_reset_date = today
            logger.info("日内统计已重置")

    def _add_alert(self, level: RiskLevel, alert_type: str, message: str, data: Optional[Dict] = None):
        """添加风险警报"""
        alert = RiskAlert(
            level=level,
            type=alert_type,
            message=message,
            timestamp=datetime.now(),
            data=data or {}
        )
        self.alerts.append(alert)
        logger.warning(f"风险警报 [{level.value}] {alert_type}: {message}")

    def get_recent_alerts(self, hours: int = 24) -> List[RiskAlert]:
        """获取最近的风险警报"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alerts if alert.timestamp >= cutoff_time]

    def get_risk_stats(self) -> Dict:
        """获取风险统计信息"""
        recent_alerts = self.get_recent_alerts(24)

        return {
            'daily_trades_count': self.daily_trades_count,
            'daily_pnl': self.daily_pnl,
            'recent_alerts_count': len(recent_alerts),
            'critical_alerts_count': sum(1 for a in recent_alerts if a.level == RiskLevel.CRITICAL),
            'limits': {
                'max_single_trade_amount': self.limits.max_single_trade_amount,
                'max_daily_trades': self.limits.max_daily_trades,
                'max_daily_loss': self.limits.max_daily_loss,
                'max_total_position_pct': self.limits.max_total_position_pct
            }
        }
