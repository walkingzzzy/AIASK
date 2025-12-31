"""
数据层集成测试
"""
import pytest

from packages.core.data_layer.sources.base_adapter import StockQuote, DailyBar, FinancialData
from packages.core.data_layer.sources.akshare_adapter import AKShareAdapter
from packages.core.data_layer.sources.source_aggregator import DataSourceAggregator, get_data_source
from packages.core.data_layer.cache.cache_manager import CacheManager, get_cache_manager
from packages.core.data_layer.quality.validator import DataValidator


class TestBaseDataClasses:
    """测试基础数据类"""

    def test_stock_quote_creation(self):
        """测试StockQuote创建"""
        quote = StockQuote(
            code="600519",
            name="贵州茅台",
            price=1850.0,
            change=25.0,
            change_pct=1.37,
            volume=1000000,
            amount=1850000000,
            high=1860.0,
            low=1830.0,
            open=1840.0,
            pre_close=1825.0,
            timestamp="2024-12-09 15:00:00",
        )
        assert quote.code == "600519"
        assert quote.price == 1850.0

    def test_daily_bar_creation(self):
        """测试DailyBar创建"""
        bar = DailyBar(
            date="20241209",
            open=1840.0,
            high=1860.0,
            low=1830.0,
            close=1850.0,
            volume=1000000,
            amount=1850000000,
        )
        assert bar.date == "20241209"
        assert bar.close == 1850.0

    def test_financial_data_creation(self):
        """测试FinancialData创建"""
        financial = FinancialData(
            code="600519",
            pe=25.0,
            pb=8.5,
            market_cap=2300000000000,
            roe=31.2,
            gross_margin=91.5,
            net_margin=52.3,
            revenue_growth=15.0,
            profit_growth=18.0,
            debt_ratio=25.0,
            report_date="20240930",
        )
        assert financial.code == "600519"
        assert financial.roe == 31.2


class TestAKShareAdapter:
    """测试AKShare适配器"""

    @pytest.fixture
    def adapter(self):
        return AKShareAdapter()

    def test_adapter_initialization(self, adapter):
        """测试适配器初始化"""
        assert adapter.name == "akshare"
        assert adapter.priority == 100

    @pytest.mark.integration
    def test_get_realtime_quote(self, adapter):
        """测试获取实时行情（需要网络）"""
        quote = adapter.get_realtime_quote("600519")
        if quote:
            assert quote.code == "600519"
            assert quote.price > 0

    @pytest.mark.integration
    def test_get_daily_bars(self, adapter):
        """测试获取日线数据（需要网络）"""
        bars = adapter.get_daily_bars("600519", "20241101", "20241201")
        if bars:
            assert len(bars) > 0
            assert all(isinstance(b, DailyBar) for b in bars)

    @pytest.mark.integration
    def test_get_financial_data(self, adapter):
        """测试获取财务数据（需要网络）"""
        financial = adapter.get_financial_data("600519")
        if financial:
            assert financial.code == "600519"


class TestDataSourceAggregator:
    """测试数据源聚合器"""

    @pytest.fixture
    def aggregator(self):
        return DataSourceAggregator()

    def test_aggregator_initialization(self, aggregator):
        """测试聚合器初始化"""
        assert len(aggregator._adapters) > 0

    def test_get_available_adapters(self, aggregator):
        """测试获取可用适配器"""
        adapters = aggregator.get_available_adapters()
        assert isinstance(adapters, list)

    def test_get_status(self, aggregator):
        """测试获取状态"""
        status = aggregator.get_status()
        assert "total_adapters" in status
        assert "adapters" in status

    def test_singleton_pattern(self):
        """测试单例模式"""
        source1 = get_data_source()
        source2 = get_data_source()
        assert source1 is source2


class TestCacheManager:
    """测试缓存管理器"""

    @pytest.fixture
    def cache(self):
        return CacheManager()

    def test_cache_set_get(self, cache):
        """测试缓存设置和获取"""
        cache.set("test_key", {"value": 123}, ttl=60)
        result = cache.get("test_key")
        assert result == {"value": 123}

    def test_cache_miss(self, cache):
        """测试缓存未命中"""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_cache_delete(self, cache):
        """测试缓存删除"""
        cache.set("delete_key", "value", ttl=60)
        cache.delete("delete_key")
        result = cache.get("delete_key")
        assert result is None

    def test_cache_stats(self, cache):
        """测试缓存统计"""
        stats = cache.get_stats()
        assert "memory_size" in stats
        assert "hits" in stats
        assert "misses" in stats

    def test_singleton_pattern(self):
        """测试单例模式"""
        cache1 = get_cache_manager()
        cache2 = get_cache_manager()
        assert cache1 is cache2


class TestDataValidator:
    """测试数据验证器"""

    @pytest.fixture
    def validator(self):
        return DataValidator()

    def test_validate_quote_valid(self, validator):
        """测试有效行情验证"""
        quote = StockQuote(
            code="600519",
            name="贵州茅台",
            price=1850.0,
            change=25.0,
            change_pct=1.37,
            volume=1000000,
            amount=1850000000,
            high=1860.0,
            low=1830.0,
            open=1840.0,
            pre_close=1825.0,
            timestamp="2024-12-09 15:00:00",
        )
        is_valid, errors = validator.validate_quote(quote)
        assert is_valid
        assert len(errors) == 0

    def test_validate_quote_invalid_price(self, validator):
        """测试无效价格验证"""
        quote = StockQuote(
            code="600519",
            name="贵州茅台",
            price=-100.0,  # 无效价格
            change=25.0,
            change_pct=1.37,
            volume=1000000,
            amount=1850000000,
            high=1860.0,
            low=1830.0,
            open=1840.0,
            pre_close=1825.0,
            timestamp="2024-12-09 15:00:00",
        )
        is_valid, errors = validator.validate_quote(quote)
        assert not is_valid
        assert len(errors) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not integration"])
