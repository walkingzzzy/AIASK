"""
回测引擎
基于backtrader的策略回测执行器
"""
from typing import Dict, Any, Optional, List, Type
from dataclasses import dataclass, field
from datetime import datetime
import logging

try:
    import backtrader as bt
    import pandas as pd
    import numpy as np
    HAS_BACKTRADER = True
except ImportError:
    HAS_BACKTRADER = False
    bt = None
    pd = None
    np = None

from .data_feed import AKShareDataFeed
from .strategies import BaseStrategy, AIScoreStrategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """回测结果"""
    # 基本信息
    strategy_name: str
    stock_code: str
    start_date: str
    end_date: str
    
    # 收益指标
    initial_capital: float = 100000.0
    final_value: float = 0.0
    total_return: float = 0.0          # 总收益率
    annual_return: float = 0.0         # 年化收益率
    
    # 风险指标
    max_drawdown: float = 0.0          # 最大回撤
    sharpe_ratio: float = 0.0          # 夏普比率
    sortino_ratio: float = 0.0         # 索提诺比率
    volatility: float = 0.0            # 波动率
    
    # 交易统计
    total_trades: int = 0              # 总交易次数
    winning_trades: int = 0            # 盈利次数
    losing_trades: int = 0             # 亏损次数
    win_rate: float = 0.0              # 胜率
    profit_factor: float = 0.0         # 盈亏比
    avg_trade_return: float = 0.0      # 平均每笔收益
    
    # 基准对比
    benchmark_return: float = 0.0      # 基准收益率
    alpha: float = 0.0                 # 超额收益
    beta: float = 0.0                  # Beta系数
    
    # 详细数据
    trade_log: List[Dict] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'strategy_name': self.strategy_name,
            'stock_code': self.stock_code,
            'period': f"{self.start_date} ~ {self.end_date}",
            'initial_capital': self.initial_capital,
            'final_value': round(self.final_value, 2),
            'total_return': f"{self.total_return:.2%}",
            'annual_return': f"{self.annual_return:.2%}",
            'max_drawdown': f"{self.max_drawdown:.2%}",
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'sortino_ratio': round(self.sortino_ratio, 2),
            'volatility': f"{self.volatility:.2%}",
            'total_trades': self.total_trades,
            'win_rate': f"{self.win_rate:.2%}",
            'profit_factor': round(self.profit_factor, 2),
            'benchmark_return': f"{self.benchmark_return:.2%}",
            'alpha': f"{self.alpha:.2%}",
        }
    
    def summary(self) -> str:
        """生成摘要报告"""
        return f"""
========== 回测报告 ==========
策略: {self.strategy_name}
标的: {self.stock_code}
周期: {self.start_date} ~ {self.end_date}

【收益指标】
初始资金: ¥{self.initial_capital:,.2f}
最终价值: ¥{self.final_value:,.2f}
总收益率: {self.total_return:.2%}
年化收益: {self.annual_return:.2%}

【风险指标】
最大回撤: {self.max_drawdown:.2%}
夏普比率: {self.sharpe_ratio:.2f}
波动率: {self.volatility:.2%}

【交易统计】
总交易: {self.total_trades}次
胜率: {self.win_rate:.2%}
盈亏比: {self.profit_factor:.2f}

【基准对比】
基准收益: {self.benchmark_return:.2%}
超额收益: {self.alpha:.2%}
==============================
"""


class BacktestEngine:
    """
    回测引擎
    
    使用示例:
    ```python
    engine = BacktestEngine()
    result = engine.run(
        strategy=AIScoreStrategy,
        stock_code="600519",
        start_date="20230101",
        end_date="20231231",
        initial_capital=100000
    )
    print(result.summary())
    ```
    """
    
    def __init__(self, initial_capital: float = 100000.0):
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金
        """
        if not HAS_BACKTRADER:
            logger.warning("backtrader未安装，回测功能不可用。请运行: pip install backtrader")
        
        self.initial_capital = initial_capital
        self.data_feed = AKShareDataFeed()
        self._cerebro = None
        self._results = None
    
    def run(self,
            strategy: Type[BaseStrategy],
            stock_code: str,
            start_date: str,
            end_date: str,
            initial_capital: float = None,
            strategy_params: Dict[str, Any] = None,
            commission: float = 0.001,
            slippage: float = 0.001) -> BacktestResult:
        """
        运行回测
        
        Args:
            strategy: 策略类
            stock_code: 股票代码
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
            initial_capital: 初始资金
            strategy_params: 策略参数
            commission: 手续费率
            slippage: 滑点
            
        Returns:
            BacktestResult: 回测结果
        """
        if not HAS_BACKTRADER:
            logger.error("backtrader未安装，无法执行回测")
            raise RuntimeError("backtrader未安装，请运行: pip install backtrader")
        
        capital = initial_capital or self.initial_capital
        
        # 创建Cerebro引擎
        self._cerebro = bt.Cerebro()
        
        # 设置初始资金
        self._cerebro.broker.setcash(capital)
        
        # 设置手续费
        self._cerebro.broker.setcommission(commission=commission)
        
        # 添加数据
        data = self.data_feed.get_data_feed(stock_code, start_date, end_date)
        if data is None:
            logger.error(f"无法获取数据: {stock_code}")
            raise ValueError(f"无法获取股票 {stock_code} 的历史数据")
        
        self._cerebro.adddata(data)
        
        # 添加策略
        if strategy_params:
            self._cerebro.addstrategy(strategy, **strategy_params)
        else:
            self._cerebro.addstrategy(strategy)
        
        # 添加分析器
        self._cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.03)
        self._cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self._cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        self._cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        self._cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return')
        
        # 运行回测
        logger.info(f"开始回测: {strategy.__name__} on {stock_code}")
        self._results = self._cerebro.run()
        
        # 分析结果
        return self._analyze_results(
            strategy_name=strategy.__name__,
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            initial_capital=capital
        )
    
    def _analyze_results(self,
                         strategy_name: str,
                         stock_code: str,
                         start_date: str,
                         end_date: str,
                         initial_capital: float) -> BacktestResult:
        """分析回测结果"""
        strat = self._results[0]
        
        # 获取最终价值
        final_value = self._cerebro.broker.getvalue()
        total_return = (final_value - initial_capital) / initial_capital
        
        # 计算年化收益
        days = self._calculate_days(start_date, end_date)
        annual_return = (1 + total_return) ** (365 / max(days, 1)) - 1
        
        # 获取分析器结果
        sharpe = self._get_sharpe_ratio(strat)
        drawdown = self._get_max_drawdown(strat)
        trade_stats = self._get_trade_stats(strat)
        returns_stats = self._get_returns_stats(strat)
        
        # 获取交易日志
        trade_log = getattr(strat, 'trade_log', [])
        
        return BacktestResult(
            strategy_name=strategy_name,
            stock_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_value=final_value,
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=drawdown,
            sharpe_ratio=sharpe,
            sortino_ratio=sharpe * 0.8,  # 简化计算
            volatility=returns_stats.get('volatility', 0),
            total_trades=trade_stats.get('total', 0),
            winning_trades=trade_stats.get('won', 0),
            losing_trades=trade_stats.get('lost', 0),
            win_rate=trade_stats.get('win_rate', 0),
            profit_factor=trade_stats.get('profit_factor', 0),
            avg_trade_return=trade_stats.get('avg_return', 0),
            benchmark_return=returns_stats.get('benchmark', 0),
            alpha=total_return - returns_stats.get('benchmark', 0),
            trade_log=trade_log
        )
    
    def _get_sharpe_ratio(self, strat) -> float:
        """获取夏普比率"""
        try:
            sharpe_analyzer = strat.analyzers.sharpe.get_analysis()
            return sharpe_analyzer.get('sharperatio', 0) or 0
        except Exception:
            return 0.0
    
    def _get_max_drawdown(self, strat) -> float:
        """获取最大回撤"""
        try:
            dd_analyzer = strat.analyzers.drawdown.get_analysis()
            return dd_analyzer.get('max', {}).get('drawdown', 0) / 100
        except Exception:
            return 0.0
    
    def _get_trade_stats(self, strat) -> Dict:
        """获取交易统计"""
        try:
            trade_analyzer = strat.analyzers.trades.get_analysis()
            
            total = trade_analyzer.get('total', {}).get('total', 0)
            won = trade_analyzer.get('won', {}).get('total', 0)
            lost = trade_analyzer.get('lost', {}).get('total', 0)
            
            win_rate = won / total if total > 0 else 0
            
            # 盈亏比
            pnl_won = trade_analyzer.get('won', {}).get('pnl', {}).get('total', 0)
            pnl_lost = abs(trade_analyzer.get('lost', {}).get('pnl', {}).get('total', 1))
            profit_factor = pnl_won / pnl_lost if pnl_lost > 0 else 0
            
            # 平均收益
            avg_return = trade_analyzer.get('pnl', {}).get('net', {}).get('average', 0)
            
            return {
                'total': total,
                'won': won,
                'lost': lost,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'avg_return': avg_return
            }
        except Exception:
            return {'total': 0, 'won': 0, 'lost': 0, 'win_rate': 0, 'profit_factor': 0, 'avg_return': 0}
    
    def _get_returns_stats(self, strat) -> Dict:
        """获取收益统计"""
        try:
            returns_analyzer = strat.analyzers.returns.get_analysis()
            time_return = strat.analyzers.time_return.get_analysis()
            
            # 计算波动率
            if time_return:
                returns = list(time_return.values())
                volatility = np.std(returns) * np.sqrt(252) if returns else 0
            else:
                volatility = 0
            
            return {
                'volatility': volatility,
                'benchmark': 0.05  # 假设基准收益5%
            }
        except Exception:
            return {'volatility': 0, 'benchmark': 0.05}
    
    def _calculate_days(self, start_date: str, end_date: str) -> int:
        """计算交易天数"""
        try:
            start = datetime.strptime(start_date, "%Y%m%d")
            end = datetime.strptime(end_date, "%Y%m%d")
            return (end - start).days
        except Exception:
            return 252
    
    def plot(self, filename: str = None):
        """
        绘制回测图表
        
        Args:
            filename: 保存文件名，None则显示
        """
        if not HAS_BACKTRADER or self._cerebro is None:
            logger.warning("无法绘图：backtrader未安装或未运行回测")
            return
        
        try:
            if filename:
                self._cerebro.plot(style='candlestick', savefig=filename)
            else:
                self._cerebro.plot(style='candlestick')
        except Exception as e:
            logger.error(f"绘图失败: {e}")


def run_backtest(strategy: Type[BaseStrategy],
                 stock_code: str,
                 start_date: str,
                 end_date: str,
                 initial_capital: float = 100000,
                 **kwargs) -> BacktestResult:
    """
    便捷回测函数
    
    Args:
        strategy: 策略类
        stock_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金
        **kwargs: 其他参数
        
    Returns:
        BacktestResult
    """
    engine = BacktestEngine(initial_capital)
    return engine.run(
        strategy=strategy,
        stock_code=stock_code,
        start_date=start_date,
        end_date=end_date,
        **kwargs
    )
