"""
券商适配器基类
定义统一的券商接口
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"  # 限价单


class OrderSide(Enum):
    """买卖方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "pending"  # 待提交
    SUBMITTED = "submitted"  # 已提交
    PARTIAL_FILLED = "partial_filled"  # 部分成交
    FILLED = "filled"  # 全部成交
    CANCELLED = "cancelled"  # 已撤销
    REJECTED = "rejected"  # 已拒绝
    FAILED = "failed"  # 失败


@dataclass
class Order:
    """订单"""
    order_id: str
    stock_code: str
    stock_name: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: int
    filled_quantity: int = 0
    avg_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    updated_at: datetime = None
    message: str = ""

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class Position:
    """持仓"""
    stock_code: str
    stock_name: str
    quantity: int  # 持仓数量
    available_quantity: int  # 可用数量
    cost_price: float  # 成本价
    current_price: float  # 当前价
    market_value: float  # 市值
    profit_loss: float  # 盈亏
    profit_loss_pct: float  # 盈亏比例


@dataclass
class Account:
    """账户信息"""
    account_id: str
    total_assets: float  # 总资产
    available_cash: float  # 可用资金
    frozen_cash: float  # 冻结资金
    market_value: float  # 持仓市值
    profit_loss: float  # 盈亏
    profit_loss_pct: float  # 盈亏比例


class BaseBroker(ABC):
    """
    券商适配器基类

    定义统一的券商接口，子类需要实现具体的交易逻辑
    """

    def __init__(self, config: Dict):
        """
        初始化券商适配器

        Args:
            config: 配置信息
        """
        self.config = config
        self.is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """
        连接券商

        Returns:
            是否连接成功
        """
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def get_account(self) -> Optional[Account]:
        """
        获取账户信息

        Returns:
            账户信息
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """
        获取持仓列表

        Returns:
            持仓列表
        """
        pass

    @abstractmethod
    def get_position(self, stock_code: str) -> Optional[Position]:
        """
        获取单个持仓

        Args:
            stock_code: 股票代码

        Returns:
            持仓信息
        """
        pass

    @abstractmethod
    def buy(
        self,
        stock_code: str,
        price: float,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT
    ) -> Optional[Order]:
        """
        买入股票

        Args:
            stock_code: 股票代码
            price: 价格
            quantity: 数量
            order_type: 订单类型

        Returns:
            订单信息
        """
        pass

    @abstractmethod
    def sell(
        self,
        stock_code: str,
        price: float,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT
    ) -> Optional[Order]:
        """
        卖出股票

        Args:
            stock_code: 股票代码
            price: 价格
            quantity: 数量
            order_type: 订单类型

        Returns:
            订单信息
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        撤销订单

        Args:
            order_id: 订单ID

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """
        获取订单列表

        Args:
            status: 订单状态过滤（可选）

        Returns:
            订单列表
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取单个订单

        Args:
            order_id: 订单ID

        Returns:
            订单信息
        """
        pass

    def is_market_open(self) -> bool:
        """
        检查市场是否开盘

        Returns:
            是否开盘
        """
        now = datetime.now()
        weekday = now.weekday()

        # 周末不开盘
        if weekday >= 5:
            return False

        # 检查交易时间
        current_time = now.time()
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()

        return (
            (morning_start <= current_time <= morning_end) or
            (afternoon_start <= current_time <= afternoon_end)
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(connected={self.is_connected})"
