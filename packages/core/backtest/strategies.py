"""
回测策略
包含基于AI评分的交易策略
"""
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging

try:
    import backtrader as bt
    HAS_BACKTRADER = True
except ImportError:
    HAS_BACKTRADER = False
    bt = None

logger = logging.getLogger(__name__)


if HAS_BACKTRADER:
    
    class BaseStrategy(bt.Strategy):
        """
        策略基类
        提供通用的交易逻辑和风险管理
        """
        
        params = (
            ('max_position_pct', 0.1),    # 单只股票最大仓位10%
            ('stop_loss_pct', 0.08),       # 止损8%
            ('take_profit_pct', 0.20),     # 止盈20%
            ('commission', 0.001),         # 手续费0.1%
            ('slippage', 0.001),           # 滑点0.1%
        )
        
        def __init__(self):
            self.order = None
            self.buy_price = None
            self.buy_date = None
            self.trade_log = []
        
        def log(self, txt, dt=None):
            """日志输出"""
            dt = dt or self.datas[0].datetime.date(0)
            logger.info(f'{dt.isoformat()} {txt}')
        
        def notify_order(self, order):
            """订单状态通知"""
            if order.status in [order.Submitted, order.Accepted]:
                return
            
            if order.status in [order.Completed]:
                if order.isbuy():
                    self.log(f'买入执行: 价格={order.executed.price:.2f}, '
                            f'数量={order.executed.size}, '
                            f'成本={order.executed.value:.2f}')
                    self.buy_price = order.executed.price
                    self.buy_date = self.datas[0].datetime.date(0)
                else:
                    self.log(f'卖出执行: 价格={order.executed.price:.2f}, '
                            f'数量={order.executed.size}')
            
            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log('订单取消/保证金不足/拒绝')
            
            self.order = None
        
        def notify_trade(self, trade):
            """交易完成通知"""
            if not trade.isclosed:
                return
            
            self.log(f'交易利润: 毛利={trade.pnl:.2f}, 净利={trade.pnlcomm:.2f}')
            self.trade_log.append({
                'date': self.datas[0].datetime.date(0).isoformat(),
                'pnl': trade.pnl,
                'pnlcomm': trade.pnlcomm
            })
        
        def check_stop_loss(self):
            """检查止损"""
            if self.position and self.buy_price:
                current_price = self.datas[0].close[0]
                loss_pct = (current_price - self.buy_price) / self.buy_price
                
                if loss_pct < -self.params.stop_loss_pct:
                    self.log(f'触发止损: 亏损{loss_pct*100:.1f}%')
                    return True
            return False
        
        def check_take_profit(self):
            """检查止盈"""
            if self.position and self.buy_price:
                current_price = self.datas[0].close[0]
                profit_pct = (current_price - self.buy_price) / self.buy_price
                
                if profit_pct > self.params.take_profit_pct:
                    self.log(f'触发止盈: 盈利{profit_pct*100:.1f}%')
                    return True
            return False
        
        def get_position_size(self):
            """计算仓位大小"""
            cash = self.broker.getcash()
            price = self.datas[0].close[0]
            max_value = cash * self.params.max_position_pct
            size = int(max_value / price / 100) * 100  # 整百股
            return max(size, 100)
    
    
    class AIScoreStrategy(BaseStrategy):
        """
        AI评分策略
        
        买入条件：
        - AI评分 >= buy_threshold
        - 信号为 Buy 或 Strong Buy
        
        卖出条件：
        - AI评分 < sell_threshold
        - 信号为 Sell 或 Strong Sell
        - 触发止损/止盈
        """
        
        params = (
            ('buy_threshold', 7.0),        # 买入阈值
            ('sell_threshold', 5.0),       # 卖出阈值
            ('score_func', None),          # AI评分函数
            ('rebalance_days', 5),         # 调仓周期（天）
        )
        
        def __init__(self):
            super().__init__()
            self.days_since_rebalance = 0
            self.current_score = None
            self.current_signal = None
        
        def next(self):
            """每个交易日执行"""
            # 检查是否有未完成订单
            if self.order:
                return
            
            # 检查止损止盈
            if self.position:
                if self.check_stop_loss() or self.check_take_profit():
                    self.order = self.close()
                    return
            
            # 调仓周期检查
            self.days_since_rebalance += 1
            if self.days_since_rebalance < self.params.rebalance_days:
                return
            
            self.days_since_rebalance = 0
            
            # 获取AI评分
            score_data = self._get_ai_score()
            if score_data is None:
                return
            
            self.current_score = score_data.get('ai_score', 5.0)
            self.current_signal = score_data.get('signal', 'Hold')
            
            self.log(f'AI评分: {self.current_score:.1f}, 信号: {self.current_signal}')
            
            # 交易逻辑
            if not self.position:
                # 无持仓，检查买入条件
                if self._should_buy():
                    size = self.get_position_size()
                    self.log(f'买入信号: 评分={self.current_score:.1f}')
                    self.order = self.buy(size=size)
            else:
                # 有持仓，检查卖出条件
                if self._should_sell():
                    self.log(f'卖出信号: 评分={self.current_score:.1f}')
                    self.order = self.close()
        
        def _get_ai_score(self) -> Optional[Dict]:
            """获取AI评分"""
            if self.params.score_func:
                try:
                    return self.params.score_func()
                except Exception as e:
                    logger.error(f"获取AI评分失败: {e}")
            
            # 模拟评分
            import random
            return {
                'ai_score': random.uniform(4, 9),
                'signal': random.choice(['Strong Buy', 'Buy', 'Hold', 'Sell'])
            }
        
        def _should_buy(self) -> bool:
            """判断是否应该买入"""
            if self.current_score >= self.params.buy_threshold:
                if self.current_signal in ['Strong Buy', 'Buy']:
                    return True
            return False
        
        def _should_sell(self) -> bool:
            """判断是否应该卖出"""
            if self.current_score < self.params.sell_threshold:
                return True
            if self.current_signal in ['Strong Sell', 'Sell']:
                return True
            return False
    
    
    class MomentumStrategy(BaseStrategy):
        """
        动量策略
        基于价格动量和成交量的简单策略
        """
        
        params = (
            ('momentum_period', 20),       # 动量周期
            ('volume_ma_period', 10),      # 成交量均线周期
            ('momentum_threshold', 0.05),  # 动量阈值5%
        )
        
        def __init__(self):
            super().__init__()
            # 计算动量
            self.momentum = bt.indicators.ROC(
                self.datas[0].close, 
                period=self.params.momentum_period
            )
            # 成交量均线
            self.volume_ma = bt.indicators.SMA(
                self.datas[0].volume,
                period=self.params.volume_ma_period
            )
        
        def next(self):
            if self.order:
                return
            
            # 止损止盈检查
            if self.position:
                if self.check_stop_loss() or self.check_take_profit():
                    self.order = self.close()
                    return
            
            # 动量和成交量条件
            momentum_pct = self.momentum[0] / 100
            volume_ratio = self.datas[0].volume[0] / self.volume_ma[0]
            
            if not self.position:
                # 买入条件：正动量 + 放量
                if momentum_pct > self.params.momentum_threshold and volume_ratio > 1.5:
                    size = self.get_position_size()
                    self.log(f'动量买入: 动量={momentum_pct*100:.1f}%, 量比={volume_ratio:.1f}')
                    self.order = self.buy(size=size)
            else:
                # 卖出条件：负动量
                if momentum_pct < -self.params.momentum_threshold:
                    self.log(f'动量卖出: 动量={momentum_pct*100:.1f}%')
                    self.order = self.close()

else:
    # backtrader未安装时的占位类
    class BaseStrategy:
        """占位类"""
        pass
    
    class AIScoreStrategy:
        """占位类"""
        pass
    
    class MomentumStrategy:
        """占位类"""
        pass
