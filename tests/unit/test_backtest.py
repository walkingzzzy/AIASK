"""
回测系统测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


class TestBacktestResult:
    """BacktestResult测试"""
    
    def test_result_creation(self):
        """测试结果创建"""
        from packages.core.backtest.engine import BacktestResult
        
        result = BacktestResult(
            strategy_name="TestStrategy",
            stock_code="600519",
            start_date="20230101",
            end_date="20231231",
            initial_capital=100000,
            final_value=120000,
            total_return=0.2,
            annual_return=0.2,
            max_drawdown=0.1,
            sharpe_ratio=1.5,
            total_trades=20,
            winning_trades=12,
            losing_trades=8,
            win_rate=0.6
        )
        
        assert result.strategy_name == "TestStrategy"
        assert result.stock_code == "600519"
        assert result.total_return == 0.2
        assert result.win_rate == 0.6
    
    def test_result_to_dict(self):
        """测试转换为字典"""
        from packages.core.backtest.engine import BacktestResult
        
        result = BacktestResult(
            strategy_name="TestStrategy",
            stock_code="600519",
            start_date="20230101",
            end_date="20231231",
            initial_capital=100000,
            final_value=120000,
            total_return=0.2,
            annual_return=0.2
        )
        
        d = result.to_dict()
        
        assert d['strategy_name'] == "TestStrategy"
        assert d['total_return'] == "20.00%"
        assert d['final_value'] == 120000.0
    
    def test_result_summary(self):
        """测试生成摘要"""
        from packages.core.backtest.engine import BacktestResult
        
        result = BacktestResult(
            strategy_name="AIScoreStrategy",
            stock_code="600519",
            start_date="20230101",
            end_date="20231231",
            initial_capital=100000,
            final_value=125000,
            total_return=0.25,
            annual_return=0.25,
            max_drawdown=0.08,
            sharpe_ratio=1.8,
            total_trades=15,
            win_rate=0.6,
            profit_factor=1.5,
            benchmark_return=0.05,
            alpha=0.2
        )
        
        summary = result.summary()
        
        assert "AIScoreStrategy" in summary
        assert "600519" in summary
        assert "25.00%" in summary
        assert "回测报告" in summary


class TestBacktestEngine:
    """BacktestEngine测试"""
    
    def test_engine_creation(self):
        """测试引擎创建"""
        from packages.core.backtest.engine import BacktestEngine
        
        engine = BacktestEngine(initial_capital=200000)
        
        assert engine.initial_capital == 200000
        assert engine.data_feed is not None
    
    def test_mock_result_generation(self):
        """测试模拟结果生成"""
        from packages.core.backtest.engine import BacktestEngine
        
        engine = BacktestEngine()
        result = engine._mock_result(
            strategy_name="TestStrategy",
            stock_code="600519",
            start_date="20230101",
            end_date="20231231"
        )
        
        assert result.strategy_name == "TestStrategy"
        assert result.stock_code == "600519"
        assert result.initial_capital == 100000
        assert -0.2 <= result.total_return <= 0.4
    
    def test_calculate_days(self):
        """测试天数计算"""
        from packages.core.backtest.engine import BacktestEngine
        
        engine = BacktestEngine()
        
        days = engine._calculate_days("20230101", "20231231")
        assert days == 364
        
        days = engine._calculate_days("20230101", "20230201")
        assert days == 31


class TestRunBacktest:
    """run_backtest便捷函数测试"""
    
    def test_run_backtest_function(self):
        """测试便捷回测函数"""
        from packages.core.backtest.engine import run_backtest
        from packages.core.backtest.strategies import AIScoreStrategy
        
        result = run_backtest(
            strategy=AIScoreStrategy,
            stock_code="600519",
            start_date="20230101",
            end_date="20231231",
            initial_capital=100000
        )
        
        assert result is not None
        assert result.stock_code == "600519"
        assert result.strategy_name == "AIScoreStrategy"


class TestAKShareDataFeed:
    """AKShareDataFeed测试"""
    
    def test_data_feed_creation(self):
        """测试数据源创建"""
        from packages.core.backtest.data_feed import AKShareDataFeed
        
        feed = AKShareDataFeed()
        assert feed is not None
    
    def test_mock_data_generation(self):
        """测试模拟数据生成"""
        from packages.core.backtest.data_feed import AKShareDataFeed
        
        feed = AKShareDataFeed()
        df = feed._mock_data("20230101", "20230131")
        
        if df is not None:
            assert 'open' in df.columns
            assert 'high' in df.columns
            assert 'low' in df.columns
            assert 'close' in df.columns
            assert 'volume' in df.columns
            assert len(df) > 0


class TestStrategies:
    """策略测试"""
    
    def test_base_strategy_exists(self):
        """测试基础策略存在"""
        from packages.core.backtest.strategies import BaseStrategy
        
        assert BaseStrategy is not None
    
    def test_ai_score_strategy_exists(self):
        """测试AI评分策略存在"""
        from packages.core.backtest.strategies import AIScoreStrategy
        
        assert AIScoreStrategy is not None
    
    def test_momentum_strategy_exists(self):
        """测试动量策略存在"""
        from packages.core.backtest.strategies import MomentumStrategy
        
        assert MomentumStrategy is not None


class TestBacktestIntegration:
    """回测集成测试"""
    
    def test_full_backtest_flow(self):
        """测试完整回测流程"""
        from packages.core.backtest import (
            BacktestEngine,
            BacktestResult,
            AIScoreStrategy,
            AKShareDataFeed
        )
        
        # 创建引擎
        engine = BacktestEngine(initial_capital=100000)
        
        # 运行回测
        result = engine.run(
            strategy=AIScoreStrategy,
            stock_code="000001",
            start_date="20230101",
            end_date="20230630"
        )
        
        # 验证结果
        assert isinstance(result, BacktestResult)
        assert result.initial_capital == 100000
        assert result.final_value > 0
        
        # 生成报告
        summary = result.summary()
        assert len(summary) > 0
        
        # 转换字典
        d = result.to_dict()
        assert 'total_return' in d
    
    def test_multiple_strategies(self):
        """测试多策略回测"""
        from packages.core.backtest import BacktestEngine, AIScoreStrategy
        from packages.core.backtest.strategies import MomentumStrategy
        
        engine = BacktestEngine()
        
        # AI评分策略
        result1 = engine.run(
            strategy=AIScoreStrategy,
            stock_code="600519",
            start_date="20230101",
            end_date="20230630"
        )
        
        # 动量策略
        result2 = engine.run(
            strategy=MomentumStrategy,
            stock_code="600519",
            start_date="20230101",
            end_date="20230630"
        )
        
        assert result1.strategy_name == "AIScoreStrategy"
        assert result2.strategy_name == "MomentumStrategy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
