"""
自动交易接口框架
支持模拟交易和实盘交易（需券商接口）
"""
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import logging
import uuid

logger = logging.getLogger(__name__)

# 常量定义
MAX_SINGLE_ORDER_QUANTITY = 100000  # 单笔最大股票数量
COMMISSION_RATE = 0.0003  # 手续费率
COMMISSION_BUFFER = 1.001  # 手续费缓冲系数
DEFAULT_SIMULATION_BALANCE = 1000000.0  # 默认模拟资金100万


class TradingMode(Enum):
    """交易模式"""
    SIMULATION = "simulation"  # 模拟交易
    PAPER = "paper"           # 纸上交易（有券商连接但不实际下单）
    LIVE = "live"             # 实盘交易


class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"    # 限价单
    STOP = "stop"      # 止损单


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL_FILLED = "partial_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """交易订单"""
    order_id: str
    stock_code: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    commission: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    is_simulation: bool = True  # 标记是否为模拟订单

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'order_id': self.order_id,
            'stock_code': self.stock_code,
            'side': self.side.value,
            'order_type': self.order_type.value,
            'quantity': self.quantity,
            'price': self.price,
            'status': self.status.value,
            'filled_quantity': self.filled_quantity,
            'filled_price': self.filled_price,
            'commission': self.commission,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'is_simulation': self.is_simulation
        }


@dataclass
class Position:
    """持仓信息"""
    stock_code: str
    stock_name: str
    quantity: int
    available_quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    profit_loss: float
    profit_loss_pct: float
    is_simulation: bool = True  # 标记是否为模拟持仓
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class TradingAccountInfo:
    """交易账户信息"""
    account_id: str
    mode: TradingMode
    total_assets: float              # 总资产
    available_balance: float         # 可用资金
    frozen_balance: float            # 冻结资金
    market_value: float              # 持仓市值
    total_profit_loss: float         # 总盈亏
    total_profit_loss_pct: float     # 总盈亏比例
    is_broker_connected: bool        # 券商是否已连接
    broker_name: Optional[str]       # 券商名称
    last_sync_time: Optional[str]    # 最后同步时间
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'account_id': self.account_id,
            'mode': self.mode.value,
            'mode_display': self._get_mode_display(),
            'total_assets': self.total_assets,
            'available_balance': self.available_balance,
            'frozen_balance': self.frozen_balance,
            'market_value': self.market_value,
            'total_profit_loss': self.total_profit_loss,
            'total_profit_loss_pct': self.total_profit_loss_pct,
            'is_broker_connected': self.is_broker_connected,
            'broker_name': self.broker_name,
            'last_sync_time': self.last_sync_time
        }
    
    def _get_mode_display(self) -> str:
        """获取模式显示名称"""
        mode_names = {
            TradingMode.SIMULATION: '🎮 模拟交易',
            TradingMode.PAPER: '📝 纸上交易',
            TradingMode.LIVE: '💰 实盘交易'
        }
        return mode_names.get(self.mode, '未知模式')


class TradingInterface:
    """
    交易接口基类
    
    支持三种交易模式：
    1. SIMULATION（模拟交易）：完全模拟，无需券商配置
    2. PAPER（纸上交易）：连接券商获取数据，但不实际下单
    3. LIVE（实盘交易）：真实交易，需要券商配置
    """

    def __init__(self, account_id: str = None,
                 mode: TradingMode = TradingMode.SIMULATION,
                 initial_balance: float = DEFAULT_SIMULATION_BALANCE,
                 price_fetcher: Optional[Callable[[str], float]] = None,
                 is_simulation: bool = True):  # 保持向后兼容
        """
        初始化交易接口
        
        Args:
            account_id: 账户ID，模拟模式下自动生成
            mode: 交易模式
            initial_balance: 初始资金（仅模拟模式有效）
            price_fetcher: 获取实时价格的回调函数
            is_simulation: 是否模拟交易（向后兼容参数）
        """
        # 向后兼容：如果使用旧的is_simulation参数
        if is_simulation and mode == TradingMode.SIMULATION:
            self.mode = TradingMode.SIMULATION
        elif not is_simulation:
            self.mode = TradingMode.LIVE
        else:
            self.mode = mode
        
        self.account_id = account_id or f"SIM_{uuid.uuid4().hex[:8].upper()}"
        self.is_simulation = self.mode == TradingMode.SIMULATION
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self._price_fetcher = price_fetcher
        
        # 模拟账户资金管理
        self._simulation_balance = initial_balance if self.is_simulation else 0.0
        self._initial_balance = initial_balance
        self._frozen_balance = 0.0
        
        # 券商连接状态
        self._broker_connected = False
        self._broker_name = None
        
        logger.info(f"交易接口初始化完成 - 账户: {self.account_id}, 模式: {self.mode.value}")

    def _get_market_price(self, stock_code: str) -> float:
        """获取当前市场价格"""
        if self._price_fetcher:
            try:
                return self._price_fetcher(stock_code)
            except Exception as e:
                logger.warning(f"获取市场价格失败 {stock_code}: {e}")
        # 如果有持仓，使用持仓的当前价格
        if stock_code in self.positions:
            return self.positions[stock_code].current_price
        return 0.0

    def place_order(
        self,
        stock_code: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None
    ) -> Order:
        """
        下单

        Args:
            stock_code: 股票代码
            side: 买卖方向
            quantity: 数量
            order_type: 订单类型
            price: 价格（限价单必填）

        Returns:
            订单对象
        """
        # 生成订单ID
        order_id = f"{self.account_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        # 创建订单
        order = Order(
            order_id=order_id,
            stock_code=stock_code,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price
        )

        # 风控检查
        if not self._risk_check(order):
            order.status = OrderStatus.REJECTED
            logger.warning(f"订单被风控拒绝: {order_id}")
            return order

        # 提交订单
        if self.is_simulation:
            success = self._submit_simulation_order(order)
        else:
            success = self._submit_real_order(order)

        if success:
            order.status = OrderStatus.SUBMITTED
            self.orders[order_id] = order
            logger.info(f"订单提交成功: {order_id}")
        else:
            order.status = OrderStatus.REJECTED
            logger.error(f"订单提交失败: {order_id}")

        return order

    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if order_id not in self.orders:
            logger.warning(f"订单不存在: {order_id}")
            return False

        order = self.orders[order_id]

        if order.status not in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
            logger.warning(f"订单状态不允许撤单: {order_id}, status={order.status}")
            return False

        if self.is_simulation:
            success = self._cancel_simulation_order(order)
        else:
            success = self._cancel_real_order(order)

        if success:
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now().isoformat()
            logger.info(f"订单撤销成功: {order_id}")

        return success

    def get_positions(self) -> List[Position]:
        """获取持仓"""
        # 更新持仓价格和盈亏
        self._update_positions_price()
        return list(self.positions.values())

    def get_order(self, order_id: str) -> Optional[Order]:
        """查询订单"""
        return self.orders.get(order_id)

    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """查询订单列表"""
        orders = list(self.orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return orders
    
    def get_account_info(self) -> TradingAccountInfo:
        """
        获取账户信息
        
        Returns:
            TradingAccountInfo 包含账户详情和当前模式
        """
        # 更新持仓价格
        self._update_positions_price()
        
        # 计算持仓市值
        market_value = sum(p.market_value for p in self.positions.values())
        
        # 计算总资产
        if self.is_simulation:
            total_assets = self._simulation_balance + market_value
        else:
            total_assets = market_value  # 实盘需要从券商获取
        
        # 计算总盈亏
        total_profit_loss = sum(p.profit_loss for p in self.positions.values())
        total_cost = sum(p.quantity * p.avg_cost for p in self.positions.values())
        total_profit_loss_pct = (total_profit_loss / total_cost * 100) if total_cost > 0 else 0.0
        
        return TradingAccountInfo(
            account_id=self.account_id,
            mode=self.mode,
            total_assets=round(total_assets, 2),
            available_balance=round(self._simulation_balance if self.is_simulation else 0, 2),
            frozen_balance=round(self._frozen_balance, 2),
            market_value=round(market_value, 2),
            total_profit_loss=round(total_profit_loss, 2),
            total_profit_loss_pct=round(total_profit_loss_pct, 2),
            is_broker_connected=self._broker_connected,
            broker_name=self._broker_name,
            last_sync_time=datetime.now().isoformat() if self.is_simulation else None
        )
    
    def get_trading_status(self) -> Dict[str, Any]:
        """
        获取交易状态摘要（用于前端显示）
        
        Returns:
            包含交易模式和状态的字典
        """
        account_info = self.get_account_info()
        
        return {
            'mode': self.mode.value,
            'mode_display': account_info._get_mode_display(),
            'is_simulation': self.is_simulation,
            'is_broker_connected': self._broker_connected,
            'broker_name': self._broker_name,
            'account_id': self.account_id,
            'available_balance': account_info.available_balance,
            'market_value': account_info.market_value,
            'total_assets': account_info.total_assets,
            'positions_count': len(self.positions),
            'pending_orders_count': len([o for o in self.orders.values()
                                         if o.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]]),
            'warnings': self._get_trading_warnings()
        }
    
    def _get_trading_warnings(self) -> List[str]:
        """获取交易相关警告"""
        warnings = []
        
        if self.is_simulation:
            warnings.append("⚠️ 当前为模拟交易模式，所有交易均为虚拟操作")
        
        if not self._broker_connected and self.mode != TradingMode.SIMULATION:
            warnings.append("⚠️ 券商未连接，无法进行实盘交易")
        
        return warnings
    
    def _update_positions_price(self):
        """更新持仓的当前价格和盈亏"""
        for stock_code, position in self.positions.items():
            if self._price_fetcher:
                try:
                    current_price = self._price_fetcher(stock_code)
                    if current_price > 0:
                        position.current_price = current_price
                        position.market_value = position.quantity * current_price
                        position.profit_loss = (current_price - position.avg_cost) * position.quantity
                        position.profit_loss_pct = ((current_price - position.avg_cost) / position.avg_cost * 100) if position.avg_cost > 0 else 0
                except Exception as e:
                    logger.warning(f"更新持仓价格失败 {stock_code}: {e}")
    
    def reset_simulation(self, initial_balance: float = None):
        """
        重置模拟账户
        
        Args:
            initial_balance: 新的初始资金，默认使用原始金额
        """
        if not self.is_simulation:
            logger.warning("只有模拟模式可以重置")
            return False
        
        self._simulation_balance = initial_balance or self._initial_balance
        self._frozen_balance = 0.0
        self.positions.clear()
        self.orders.clear()
        
        logger.info(f"模拟账户已重置，初始资金: {self._simulation_balance}")
        return True

    def _risk_check(self, order: Order) -> bool:
        """风控检查"""
        # 1. 检查资金是否充足
        if order.side == OrderSide.BUY:
            # 市价单需要获取当前市场价格进行风控检查
            price = order.price
            if price is None or price == 0:
                price = self._get_market_price(order.stock_code)
            if price <= 0:
                logger.warning(f"无法获取价格进行风控检查: {order.stock_code}")
                return False
            required_amount = order.quantity * price * COMMISSION_BUFFER  # 含手续费
            if not self._check_balance(required_amount):
                logger.warning(f"资金不足: 需要{required_amount}")
                return False

        # 2. 检查持仓是否充足
        if order.side == OrderSide.SELL:
            position = self.positions.get(order.stock_code)
            if not position or position.available_quantity < order.quantity:
                logger.warning(f"持仓不足: {order.stock_code}")
                return False

        # 3. 检查单笔限额
        if order.quantity > MAX_SINGLE_ORDER_QUANTITY:
            logger.warning(f"单笔数量超限: {order.quantity}")
            return False

        return True

    def _check_balance(self, required_amount: float) -> bool:
        """检查资金余额（需实现）"""
        # 模拟交易默认通过
        return self.is_simulation

    def _submit_simulation_order(self, order: Order) -> bool:
        """提交模拟订单"""
        # 模拟订单立即成交
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        # 模拟交易获取实时价格作为成交价
        if order.price and order.price > 0:
            order.filled_price = order.price
        else:
            order.filled_price = self._get_market_price(order.stock_code)
        if order.filled_price <= 0:
            logger.warning(f"无法获取成交价格: {order.stock_code}")
            return False
        order.commission = order.filled_quantity * order.filled_price * COMMISSION_RATE

        # 更新持仓
        self._update_position(order)

        return True

    def _submit_real_order(self, order: Order) -> bool:
        """提交实盘订单（需对接券商接口）"""
        logger.warning("实盘交易接口未实现")
        return False

    def _cancel_simulation_order(self, order: Order) -> bool:
        """撤销模拟订单"""
        return True

    def _cancel_real_order(self, order: Order) -> bool:
        """撤销实盘订单（需对接券商接口）"""
        logger.warning("实盘交易接口未实现")
        return False

    def _update_position(self, order: Order):
        """更新持仓"""
        stock_code = order.stock_code

        if stock_code not in self.positions:
            self.positions[stock_code] = Position(
                stock_code=stock_code,
                stock_name="",
                quantity=0,
                available_quantity=0,
                avg_cost=0.0,
                current_price=0.0,
                market_value=0.0,
                profit_loss=0.0,
                profit_loss_pct=0.0
            )

        position = self.positions[stock_code]

        if order.side == OrderSide.BUY:
            # 买入更新
            total_cost = position.quantity * position.avg_cost + order.filled_quantity * order.filled_price
            position.quantity += order.filled_quantity
            position.available_quantity += order.filled_quantity
            position.avg_cost = total_cost / position.quantity if position.quantity > 0 else 0
        else:
            # 卖出更新
            position.quantity -= order.filled_quantity
            position.available_quantity -= order.filled_quantity

        # 如果持仓清空，删除记录
        if position.quantity == 0:
            del self.positions[stock_code]


class StrategyExecutor:
    """策略执行器"""

    def __init__(self, trading_interface: TradingInterface):
        self.trading = trading_interface

    def execute_ai_score_strategy(
        self,
        stock_code: str,
        ai_score: float,
        current_price: float,
        buy_threshold: float = 8.0,
        sell_threshold: float = 5.0
    ) -> Optional[Order]:
        """
        执行AI评分策略

        Args:
            stock_code: 股票代码
            ai_score: AI评分
            current_price: 当前价格
            buy_threshold: 买入阈值
            sell_threshold: 卖出阈值

        Returns:
            订单对象（如果触发交易）
        """
        # 检查是否持仓
        position = self.trading.positions.get(stock_code)

        # 买入信号
        if ai_score >= buy_threshold and not position:
            quantity = self._calculate_position_size(current_price)
            return self.trading.place_order(
                stock_code=stock_code,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=OrderType.LIMIT,
                price=current_price
            )

        # 卖出信号
        if ai_score <= sell_threshold and position:
            return self.trading.place_order(
                stock_code=stock_code,
                side=OrderSide.SELL,
                quantity=position.quantity,
                order_type=OrderType.LIMIT,
                price=current_price
            )

        return None

    def _calculate_position_size(self, price: float) -> int:
        """计算仓位大小"""
        # 简化版：固定金额10000元
        target_amount = 10000
        quantity = int(target_amount / price / 100) * 100  # 取整到100股
        return max(100, quantity)  # 最少100股