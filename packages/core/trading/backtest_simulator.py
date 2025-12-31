"""
回测交易模拟器
在回测中模拟真实交易
"""
from typing import Dict, Any, List
from datetime import datetime
import pandas as pd
from ..trading.trading_interface import (
    TradingInterface, Order, Position, OrderSide, OrderType, OrderStatus
)


class BacktestSimulator(TradingInterface):
    """回测交易模拟器"""

    def __init__(self, initial_capital: float = 1000000):
        super().__init__(account_id="backtest", is_simulation=True)
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.total_value = initial_capital
        self.trade_history: List[Dict[str, Any]] = []

    def _check_balance(self, required_amount: float) -> bool:
        """检查资金余额"""
        return self.cash >= required_amount

    def _submit_simulation_order(self, order: Order) -> bool:
        """提交模拟订单"""
        # 计算交易金额
        trade_amount = order.quantity * order.price
        commission = trade_amount * 0.0003  # 万三手续费

        if order.side == OrderSide.BUY:
            total_cost = trade_amount + commission
            if self.cash < total_cost:
                return False

            # 扣除资金
            self.cash -= total_cost

            # 更新订单
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_price = order.price
            order.commission = commission

        else:  # SELL
            # 增加资金
            self.cash += trade_amount - commission

            # 更新订单
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_price = order.price
            order.commission = commission

        # 更新持仓
        self._update_position(order)

        # 记录交易
        self.trade_history.append({
            'timestamp': order.created_at,
            'stock_code': order.stock_code,
            'side': order.side.value,
            'quantity': order.quantity,
            'price': order.price,
            'commission': commission,
            'cash': self.cash
        })

        return True

    def update_market_value(self, prices: Dict[str, float]):
        """
        更新市值

        Args:
            prices: 股票代码 -> 当前价格
        """
        position_value = 0

        for stock_code, position in self.positions.items():
            current_price = prices.get(stock_code, position.avg_cost)
            position.current_price = current_price
            position.market_value = position.quantity * current_price
            position.profit_loss = position.market_value - position.quantity * position.avg_cost
            position.profit_loss_pct = (position.profit_loss / (position.quantity * position.avg_cost) * 100
                                       if position.quantity > 0 else 0)

            position_value += position.market_value

        self.total_value = self.cash + position_value

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取回测绩效指标"""
        total_return = (self.total_value - self.initial_capital) / self.initial_capital * 100

        # 计算交易统计
        trades = pd.DataFrame(self.trade_history)
        if len(trades) > 0:
            total_trades = len(trades)
            total_commission = trades['commission'].sum()
        else:
            total_trades = 0
            total_commission = 0

        return {
            'initial_capital': self.initial_capital,
            'final_value': self.total_value,
            'total_return': total_return,
            'cash': self.cash,
            'position_value': self.total_value - self.cash,
            'total_trades': total_trades,
            'total_commission': total_commission,
            'positions': len(self.positions)
        }


class BacktestEngine:
    """回测引擎"""

    def __init__(self, initial_capital: float = 1000000):
        self.simulator = BacktestSimulator(initial_capital)
        self.equity_curve: List[Dict[str, Any]] = []

    def run_backtest(
        self,
        strategy_func,
        price_data: pd.DataFrame,
        score_data: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        运行回测

        Args:
            strategy_func: 策略函数
            price_data: 价格数据
            score_data: 评分数据

        Returns:
            回测结果
        """
        dates = sorted(price_data['date'].unique())

        for date in dates:
            # 获取当日数据
            daily_prices = price_data[price_data['date'] == date]
            daily_scores = score_data[score_data['date'] == date]

            # 更新市值
            prices_dict = dict(zip(daily_prices['stock_code'], daily_prices['close']))
            self.simulator.update_market_value(prices_dict)

            # 执行策略
            for _, score_row in daily_scores.iterrows():
                stock_code = score_row['stock_code']
                ai_score = score_row['ai_score']

                price_row = daily_prices[daily_prices['stock_code'] == stock_code]
                if len(price_row) == 0:
                    continue

                current_price = price_row.iloc[0]['close']

                # 调用策略
                strategy_func(
                    self.simulator,
                    stock_code,
                    ai_score,
                    current_price
                )

            # 记录权益曲线
            self.equity_curve.append({
                'date': date,
                'total_value': self.simulator.total_value,
                'cash': self.simulator.cash,
                'position_value': self.simulator.total_value - self.simulator.cash
            })

        # 返回回测结果
        return {
            'performance': self.simulator.get_performance_metrics(),
            'equity_curve': self.equity_curve,
            'trades': self.simulator.trade_history,
            'final_positions': [
                {
                    'stock_code': p.stock_code,
                    'quantity': p.quantity,
                    'avg_cost': p.avg_cost,
                    'current_price': p.current_price,
                    'profit_loss': p.profit_loss,
                    'profit_loss_pct': p.profit_loss_pct
                }
                for p in self.simulator.get_positions()
            ]
        }