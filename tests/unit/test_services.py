"""
服务层集成测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from packages.core.services.stock_data_service import (
    StockDataService,
    get_stock_service,
)
from packages.core.scoring.ai_score.score_calculator import AIScoreResult


class TestStockDataService:
    """测试股票数据服务"""

    @pytest.fixture
    def mock_data_source(self):
        """模拟数据源"""
        mock = Mock()
        # 模拟实时行情
        mock.get_realtime_quote.return_value = Mock(
            stock_code="600519",
            stock_name="贵州茅台",
            price=1850.0,
            change=25.0,
            change_pct=1.37,
            volume=50000,
            amount=925000000,
            high=1860.0,
            low=1830.0,
            open=1835.0,
            prev_close=1825.0,
            volume_ratio=1.2,
            timestamp="2024-12-09 15:00:00",
        )
        # 模拟日线数据
        mock.get_daily_bars.return_value = [
            Mock(
                date="2024-12-01",
                open=1800.0,
                high=1820.0,
                low=1790.0,
                close=1810.0,
                volume=40000,
            ),
            Mock(
                date="2024-12-02",
                open=1810.0,
                high=1830.0,
                low=1805.0,
                close=1825.0,
                volume=45000,
            ),
        ]
        # 模拟财务数据
        mock.get_financial_data.return_value = Mock(
            stock_code="600519",
            pe=25.3,
            pb=8.5,
            roe=31.2,
            gross_margin=91.5,
            revenue_growth=15.2,
            profit_growth=18.5,
            pe_percentile=75,
        )
        mock.health_check_all.return_value = {"akshare": "healthy"}
        return mock

    @pytest.fixture
    def mock_cache(self):
        """模拟缓存"""
        mock = Mock()
        mock.get.return_value = None  # 默认缓存未命中
        mock.set.return_value = True
        mock.get_stats.return_value = {"hits": 0, "misses": 0}
        return mock

    @pytest.fixture
    def service(self, mock_data_source, mock_cache):
        """创建服务实例"""
        return StockDataService(
            data_source=mock_data_source, cache_manager=mock_cache
        )

    # ==================== 行情数据测试 ====================

    def test_get_realtime_quote(self, service, mock_data_source):
        """测试获取实时行情"""
        result = service.get_realtime_quote("600519")

        assert result is not None
        assert result["stock_code"] == "600519"
        mock_data_source.get_realtime_quote.assert_called_once_with("600519")

    def test_get_realtime_quote_with_cache(self, service, mock_cache):
        """测试缓存命中"""
        cached_data = {"stock_code": "600519", "price": 1850.0}
        mock_cache.get.return_value = cached_data

        result = service.get_realtime_quote("600519", use_cache=True)

        assert result == cached_data

    def test_get_realtime_quote_no_cache(self, service, mock_data_source):
        """测试不使用缓存"""
        result = service.get_realtime_quote("600519", use_cache=False)

        assert result is not None
        mock_data_source.get_realtime_quote.assert_called()

    def test_get_daily_bars(self, service, mock_data_source):
        """测试获取日线数据"""
        result = service.get_daily_bars("600519", days=30)

        assert result is not None
        assert isinstance(result, pd.DataFrame)
        mock_data_source.get_daily_bars.assert_called_once()

    def test_get_financial_data(self, service, mock_data_source):
        """测试获取财务数据"""
        result = service.get_financial_data("600519")

        assert result is not None
        assert result["pe"] == 25.3
        mock_data_source.get_financial_data.assert_called_once_with("600519")

    # ==================== 技术指标测试 ====================

    def test_calculate_indicators(self, service):
        """测试计算技术指标"""
        # 需要足够的数据来计算指标
        with patch.object(service, "get_daily_bars") as mock_bars:
            # 创建足够的测试数据
            dates = pd.date_range("2024-01-01", periods=120)
            mock_df = pd.DataFrame(
                {
                    "date": dates,
                    "open": [100 + i * 0.1 for i in range(120)],
                    "high": [102 + i * 0.1 for i in range(120)],
                    "low": [98 + i * 0.1 for i in range(120)],
                    "close": [101 + i * 0.1 for i in range(120)],
                    "volume": [10000 + i * 100 for i in range(120)],
                }
            )
            mock_bars.return_value = mock_df

            result = service.calculate_indicators("600519")

            assert result is not None
            assert "ma5" in result
            assert "ma10" in result
            assert "ma20" in result
            assert "rsi" in result
            assert "close" in result

    def test_calculate_indicators_empty_data(self, service):
        """测试空数据计算指标"""
        with patch.object(service, "get_daily_bars") as mock_bars:
            mock_bars.return_value = None

            result = service.calculate_indicators("600519")

            assert result is None

    # ==================== AI评分测试 ====================

    def test_get_ai_score(self, service):
        """测试获取AI评分"""
        with patch.object(service, "_collect_score_data") as mock_collect:
            mock_collect.return_value = {
                "close": 1850.0,
                "ma5": 1840.0,
                "ma10": 1830.0,
                "ma20": 1820.0,
                "rsi": 55,
                "pe": 25.3,
                "roe": 31.2,
                "pe_percentile": 75,
                "market_breadth": 0.6,
                "volatility": 0.02,
                "beta": 1.0,
                "max_drawdown": 0.1,
            }

            result = service.get_ai_score("600519", "贵州茅台")

            assert result is not None
            assert isinstance(result, AIScoreResult)
            assert 1 <= result.ai_score <= 10

    def test_get_ai_score_no_data(self, service):
        """测试无数据时获取AI评分"""
        with patch.object(service, "_collect_score_data") as mock_collect:
            mock_collect.return_value = None

            result = service.get_ai_score("600519", "贵州茅台")

            assert result is None

    def test_get_score_explanation(self, service):
        """测试获取评分解释"""
        with patch.object(service, "get_ai_score") as mock_score:
            mock_score.return_value = AIScoreResult(
                stock_code="600519",
                stock_name="贵州茅台",
                ai_score=7.5,
                signal="Buy",
                confidence=0.8,
                beat_market_probability=0.65,
                subscores={
                    "technical": {"score": 7.0, "weight": 0.25, "details": {}},
                    "fundamental": {"score": 8.0, "weight": 0.30, "details": {}},
                    "fund_flow": {"score": 7.5, "weight": 0.25, "details": {}},
                    "sentiment": {"score": 6.5, "weight": 0.10, "details": {}},
                    "risk": {"score": 7.0, "weight": 0.10, "details": {}},
                },
                top_factors=[],
                risks=[],
                updated_at="2024-12-09 15:00:00",
            )

            result = service.get_score_explanation("600519", "贵州茅台")

            assert result is not None
            assert result.stock_code == "600519"

    # ==================== 批量操作测试 ====================

    def test_batch_get_ai_scores(self, service):
        """测试批量获取AI评分"""
        with patch.object(service, "get_ai_score") as mock_score:
            mock_score.return_value = AIScoreResult(
                stock_code="600519",
                stock_name="贵州茅台",
                ai_score=7.5,
                signal="Buy",
                confidence=0.8,
                beat_market_probability=0.65,
                subscores={},
                top_factors=[],
                risks=[],
                updated_at="2024-12-09",
            )

            results = service.batch_get_ai_scores(
                ["600519", "000858"], {"600519": "贵州茅台", "000858": "五粮液"}
            )

            assert len(results) == 2

    def test_get_top_stocks(self, service):
        """测试获取评分最高股票"""
        with patch.object(service, "batch_get_ai_scores") as mock_batch:
            mock_batch.return_value = [
                AIScoreResult(
                    stock_code="600519",
                    stock_name="贵州茅台",
                    ai_score=8.5,
                    signal="Strong Buy",
                    confidence=0.9,
                    beat_market_probability=0.75,
                    subscores={},
                    top_factors=[],
                    risks=[],
                    updated_at="2024-12-09",
                ),
                AIScoreResult(
                    stock_code="000858",
                    stock_name="五粮液",
                    ai_score=7.2,
                    signal="Buy",
                    confidence=0.8,
                    beat_market_probability=0.6,
                    subscores={},
                    top_factors=[],
                    risks=[],
                    updated_at="2024-12-09",
                ),
            ]

            results = service.get_top_stocks(["600519", "000858"], top_n=2)

            assert len(results) == 2
            assert results[0].ai_score >= results[1].ai_score

    # ==================== 健康检查测试 ====================

    def test_health_check(self, service):
        """测试健康检查"""
        result = service.health_check()

        assert "data_source" in result
        assert "cache" in result
        assert result["status"] == "healthy"


class TestServiceSingleton:
    """测试服务单例"""

    def test_get_stock_service_singleton(self):
        """测试获取服务单例"""
        # 重置单例
        import packages.core.services.stock_data_service as svc_module

        svc_module._service_instance = None

        service1 = get_stock_service()
        service2 = get_stock_service()

        assert service1 is service2


class TestDataCollection:
    """测试数据收集"""

    @pytest.fixture
    def service(self):
        """创建服务实例"""
        mock_source = Mock()
        mock_cache = Mock()
        mock_cache.get.return_value = None
        return StockDataService(data_source=mock_source, cache_manager=mock_cache)

    def test_collect_score_data(self, service):
        """测试收集评分数据"""
        with patch.object(service, "get_realtime_quote") as mock_quote:
            with patch.object(service, "calculate_indicators") as mock_ind:
                with patch.object(service, "get_financial_data") as mock_fin:
                    mock_quote.return_value = {"price": 1850.0, "volume_ratio": 1.2}
                    mock_ind.return_value = {
                        "ma5": 1840.0,
                        "rsi": 55,
                        "close": 1850.0,
                    }
                    mock_fin.return_value = {"pe": 25.3, "roe": 31.2}

                    result = service._collect_score_data("600519")

                    assert result is not None
                    assert "close" in result
                    assert "pe" in result
                    assert "pe_percentile" in result  # 默认值


class TestCacheIntegration:
    """测试缓存集成"""

    def test_cache_ttl_config(self):
        """测试缓存TTL配置"""
        assert StockDataService.CACHE_TTL["realtime"] == 30
        assert StockDataService.CACHE_TTL["daily"] == 3600
        assert StockDataService.CACHE_TTL["financial"] == 86400
        assert StockDataService.CACHE_TTL["indicators"] == 300
        assert StockDataService.CACHE_TTL["ai_score"] == 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
