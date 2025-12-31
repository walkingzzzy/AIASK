"""
EasyTrader券商适配器
基于easytrader库实现的券商接口
"""
from typing import Dict, List, Optional
import logging
from datetime import datetime

from .base_broker import (
    BaseBroker, Order, Position, Account,
    OrderType, OrderSide, OrderStatus
)

logger = logging.getLogger(__name__)


class EasyTraderBroker(BaseBroker):
    """
    EasyTrader券商适配器

    支持的券商：
    - 华泰证券
    - 国金证券
    - 银河证券
    - 等（取决于easytrader支持）
    """

    def __init__(self, config: Dict):
        """
        初始化EasyTrader适配器

        Args:
            config: 配置信息
                - broker: 券商名称 ('ht', 'gj', 'yh' 等)
                - account: 账号
                - password: 密码
                - comm_password: 通讯密码（可选）
        """
        super().__init__(config)
        self.user = None
        self.broker_name = config.get('broker', 'ht')

    def connect(self) -> bool:
        """连接券商"""
        try:
            import easytrader
        except ImportError:
            logger.error("需要安装easytrader: pip install easytrader")
            return False

        try:
            # 创建用户实例
            self.user = easytrader.use(self.broker_name)

            # 准备登录参数
            login_params = {
                'user': self.config.get('account'),
                'password': self.config.get('password')
            }

            # 添加通讯密码（如果有）
            if 'comm_password' in self.config:
                login_params['comm_password'] = self.config['comm_password']

            # 登录
            self.user.prepare(**login_params)

            self.is_connected = True
            logger.info(f"成功连接到券商: {self.broker_name}")
            return True

        except Exception as e:
            logger.error(f"连接券商失败: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """断开连接"""
        self.user = None
        self.is_connected = False
        logger.info("已断开券商连接")

    def get_account(self) -> Optional[Account]:
        """获取账户信息"""
        if not self.is_connected or not self.user:
            logger.error("未连接到券商")
            return None

        try:
            balance = self.user.balance

            # 解析账户信息
            account = Account(
                account_id=self.config.get('account', ''),
                total_assets=float(balance.get('总资产', 0)),
                available_cash=float(balance.get('可用金额', 0)),
                frozen_cash=float(balance.get('冻结金额', 0)),
                market_value=float(balance.get('持仓市值', 0)),
                profit_loss=float(balance.get('盈亏', 0)),
                profit_loss_pct=float(balance.get('盈亏比例', 0))
            )

            return account

        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            return None

    def get_positions(self) -> List[Position]:
        """获取持仓列表"""
        if not self.is_connected or not self.user:
            logger.error("未连接到券商")
            return []

        try:
            positions_data = self.user.position

            positions = []
            for pos_data in positions_data:
                position = Position(
                    stock_code=pos_data.get('证券代码', ''),
                    stock_name=pos_data.get('证券名称', ''),
                    quantity=int(pos_data.get('股票余额', 0)),
                    available_quantity=int(pos_data.get('可用余额', 0)),
                    cost_price=float(pos_data.get('成本价', 0)),
                    current_price=float(pos_data.get('当前价', 0)),
                    market_value=float(pos_data.get('市值', 0)),
                    profit_loss=float(pos_data.get('盈亏', 0)),
                    profit_loss_pct=float(pos_data.get('盈亏比例', 0))
                )
                positions.append(position)

            return positions

        except Exception as e:
            logger.error(f"获取持仓列表失败: {e}")
            return []

    def get_position(self, stock_code: str) -> Optional[Position]:
        """获取单个持仓"""
        positions = self.get_positions()
        for pos in positions:
            if pos.stock_code == stock_code:
                return pos
        return None

    def buy(
        self,
        stock_code: str,
        price: float,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT
    ) -> Optional[Order]:
        """买入股票"""
        if not self.is_connected or not self.user:
            logger.error("未连接到券商")
            return None

        try:
            # 执行买入
            result = self.user.buy(stock_code, price=price, amount=quantity)

            # 创建订单对象
            order = Order(
                order_id=str(result.get('entrust_no', '')),
                stock_code=stock_code,
                stock_name='',  # easytrader可能不返回股票名称
                side=OrderSide.BUY,
                order_type=order_type,
                price=price,
                quantity=quantity,
                status=OrderStatus.SUBMITTED
            )

            logger.info(f"买入订单已提交: {stock_code} {quantity}股 @{price}")
            return order

        except Exception as e:
            logger.error(f"买入失败: {e}")
            return None

    def sell(
        self,
        stock_code: str,
        price: float,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT
    ) -> Optional[Order]:
        """卖出股票"""
        if not self.is_connected or not self.user:
            logger.error("未连接到券商")
            return None

        try:
            # 执行卖出
            result = self.user.sell(stock_code, price=price, amount=quantity)

            # 创建订单对象
            order = Order(
                order_id=str(result.get('entrust_no', '')),
                stock_code=stock_code,
                stock_name='',
                side=OrderSide.SELL,
                order_type=order_type,
                price=price,
                quantity=quantity,
                status=OrderStatus.SUBMITTED
            )

            logger.info(f"卖出订单已提交: {stock_code} {quantity}股 @{price}")
            return order

        except Exception as e:
            logger.error(f"卖出失败: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        if not self.is_connected or not self.user:
            logger.error("未连接到券商")
            return False

        try:
            self.user.cancel_entrust(order_id)
            logger.info(f"订单已撤销: {order_id}")
            return True

        except Exception as e:
            logger.error(f"撤销订单失败: {e}")
            return False

    def get_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """获取订单列表"""
        if not self.is_connected or not self.user:
            logger.error("未连接到券商")
            return []

        try:
            orders_data = self.user.today_entrusts

            orders = []
            for order_data in orders_data:
                # 解析订单状态
                status_str = order_data.get('委托状态', '')
                order_status = self._parse_order_status(status_str)

                # 如果指定了状态过滤
                if status and order_status != status:
                    continue

                order = Order(
                    order_id=str(order_data.get('委托编号', '')),
                    stock_code=order_data.get('证券代码', ''),
                    stock_name=order_data.get('证券名称', ''),
                    side=OrderSide.BUY if order_data.get('买卖标志') == '买入' else OrderSide.SELL,
                    order_type=OrderType.LIMIT,  # easytrader默认限价单
                    price=float(order_data.get('委托价格', 0)),
                    quantity=int(order_data.get('委托数量', 0)),
                    filled_quantity=int(order_data.get('成交数量', 0)),
                    avg_price=float(order_data.get('成交均价', 0)),
                    status=order_status
                )
                orders.append(order)

            return orders

        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            return []

    def get_order(self, order_id: str) -> Optional[Order]:
        """获取单个订单"""
        orders = self.get_orders()
        for order in orders:
            if order.order_id == order_id:
                return order
        return None

    def _parse_order_status(self, status_str: str) -> OrderStatus:
        """解析订单状态"""
        status_map = {
            '已报': OrderStatus.SUBMITTED,
            '部成': OrderStatus.PARTIAL_FILLED,
            '已成': OrderStatus.FILLED,
            '已撤': OrderStatus.CANCELLED,
            '废单': OrderStatus.REJECTED
        }
        return status_map.get(status_str, OrderStatus.PENDING)
