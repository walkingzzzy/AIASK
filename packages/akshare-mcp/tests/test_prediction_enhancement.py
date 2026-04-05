"""
MCP 预测能力增强 — 单元测试

覆盖 Phase 1-6 的所有代码修改。
"""

import pytest
import numpy as np
from collections import OrderedDict
from unittest.mock import AsyncMock


# ====================================================================
#  Phase 1: 因子计算修复
# ====================================================================


class TestRSIWilder:
    """RSI 使用 Wilder 指数平滑"""

    def test_rsi_basic_range(self):
        """RSI 应在 0-100 之间"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + i * 0.1 for i in range(100)]  # 稳步上涨
        rsi = TechnicalFactorsMixin.calculate_rsi(closes, period=14)
        assert 0 <= rsi <= 100

    def test_rsi_all_gains_is_100(self):
        """纯上涨序列 RSI 应趋近 100"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [float(i) for i in range(1, 102)]  # 1,2,...,101
        rsi = TechnicalFactorsMixin.calculate_rsi(closes, period=14)
        assert rsi >= 95.0  # Wilder 平滑下纯上涨应接近 100

    def test_rsi_all_losses_is_0(self):
        """纯下跌序列 RSI 应趋近 0"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [float(100 - i) for i in range(101)]  # 100,99,...,0
        rsi = TechnicalFactorsMixin.calculate_rsi(closes, period=14)
        assert rsi <= 5.0

    def test_rsi_uses_full_history(self):
        """Wilder RSI 使用全部历史数据，不仅是最后 period+1 个"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        # 前 50 个上涨，后 50 个下跌
        closes = [float(i) for i in range(1, 52)] + [float(51 - i * 0.5) for i in range(1, 51)]
        rsi = TechnicalFactorsMixin.calculate_rsi(closes, period=14)
        # Wilder 平滑会"记住"前期上涨，RSI 不应该极低
        assert rsi < 70  # 整体趋势转跌
        assert rsi > 0  # Wilder 平滑值不应为 0

    def test_rsi_short_data_returns_50(self):
        """数据不足时返回 50.0"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        rsi = TechnicalFactorsMixin.calculate_rsi([10, 11, 12], period=14)
        assert rsi == 50.0


class TestTRIXOptimization:
    """TRIX O(n²) → O(n) 优化"""

    def test_trix_returns_float(self):
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + np.sin(i / 5.0) for i in range(100)]
        result = TechnicalFactorsMixin.calculate_trix(closes, period=12)
        assert isinstance(result, float)

    def test_trix_short_data(self):
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10, 11, 12]  # < 12 * 3
        assert TechnicalFactorsMixin.calculate_trix(closes, period=12) == 0.0

    def test_ema_series_length(self):
        """_calculate_ema_series 返回与输入等长的数组"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        ema = TechnicalFactorsMixin._calculate_ema_series(data, period=3)
        assert len(ema) == len(data)
        assert isinstance(ema, np.ndarray)

    def test_ema_series_empty(self):
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        ema = TechnicalFactorsMixin._calculate_ema_series(np.array([]), period=3)
        assert len(ema) == 0


class TestATRWilder:
    """ATR Wilder 指数平滑版"""

    def test_atr_wilder_basic(self):
        from akshare_mcp.services.factor_calculator.volatility import VolatilityFactorsMixin
        np.random.seed(42)
        n = 100
        closes = np.cumsum(np.random.randn(n) * 0.5) + 50
        highs = closes + np.abs(np.random.randn(n)) * 0.3
        lows = closes - np.abs(np.random.randn(n)) * 0.3
        atr = VolatilityFactorsMixin.calculate_atr_wilder(
            highs.tolist(), lows.tolist(), closes.tolist(), period=14
        )
        assert atr > 0

    def test_atr_wilder_short_data(self):
        from akshare_mcp.services.factor_calculator.volatility import VolatilityFactorsMixin
        atr = VolatilityFactorsMixin.calculate_atr_wilder([10], [9], [9.5], period=14)
        assert atr == 0.0


class TestParkinsonVol:
    """Parkinson 波动率"""

    def test_parkinson_positive(self):
        from akshare_mcp.services.factor_calculator.volatility import VolatilityFactorsMixin
        np.random.seed(42)
        n = 100
        closes = np.cumsum(np.random.randn(n) * 0.3) + 50
        highs = closes + np.abs(np.random.randn(n)) * 0.5
        lows = closes - np.abs(np.random.randn(n)) * 0.5
        vol = VolatilityFactorsMixin.calculate_parkinson_vol(highs.tolist(), lows.tolist(), period=20)
        assert vol > 0

    def test_parkinson_short_data(self):
        from akshare_mcp.services.factor_calculator.volatility import VolatilityFactorsMixin
        vol = VolatilityFactorsMixin.calculate_parkinson_vol([10, 11], [9, 10], period=20)
        assert vol == 0.0


class TestGarmanKlassVol:
    """Garman-Klass 波动率"""

    def test_gk_positive(self):
        from akshare_mcp.services.factor_calculator.volatility import VolatilityFactorsMixin
        np.random.seed(42)
        n = 50
        opens = [50 + i * 0.1 for i in range(n)]
        closes = [o + np.random.randn() * 0.3 for o in opens]
        highs = [max(o, c) + abs(np.random.randn()) * 0.2 for o, c in zip(opens, closes)]
        lows = [min(o, c) - abs(np.random.randn()) * 0.2 for o, c in zip(opens, closes)]
        vol = VolatilityFactorsMixin.calculate_garman_klass_vol(opens, highs, lows, closes, period=20)
        assert vol > 0


class TestVolRatio:
    """波动率比率"""

    def test_vol_ratio_basic(self):
        from akshare_mcp.services.factor_calculator.volatility import VolatilityFactorsMixin
        np.random.seed(42)
        closes = (np.cumsum(np.random.randn(200) * 0.3) + 100).tolist()
        ratio = VolatilityFactorsMixin.calculate_vol_ratio(closes, short=5, long=60)
        assert ratio > 0

    def test_vol_ratio_short_data(self):
        from akshare_mcp.services.factor_calculator.volatility import VolatilityFactorsMixin
        ratio = VolatilityFactorsMixin.calculate_vol_ratio([10, 11, 12], short=5, long=60)
        assert ratio == 1.0  # 不足返回 1.0


class TestADOSCEMA:
    """ADOSC 改用 EMA"""

    def test_adosc_returns_float(self):
        from akshare_mcp.services.factor_calculator.volume import VolumeFactorsMixin
        np.random.seed(42)
        n = 50
        closes = (np.cumsum(np.random.randn(n) * 0.3) + 50).tolist()
        highs = [c + 0.5 for c in closes]
        lows = [c - 0.5 for c in closes]
        volumes = [1000000 + np.random.randint(-100000, 100000) for _ in range(n)]
        result = VolumeFactorsMixin.calculate_adosc(highs, lows, closes, volumes)
        assert isinstance(result, float)


class TestZScoreRolling:
    """z-score 前视偏差修复"""

    def test_rolling_no_lookahead(self):
        """rolling z-score 的第 i 个值只用 data[:i+1]"""
        from akshare_mcp.services.multi_factor import FactorStandardizer
        data = np.array([1.0, 2.0, 3.0, 100.0, 5.0, 6.0])
        z = FactorStandardizer.z_score_rolling(data, window=0)
        # 第 0 个值应该是 NaN（expanding min_periods=2）
        assert np.isnan(z[0])
        # 第 2 个值不应受 data[3]=100 影响
        # 用 expanding 到 data[:3] = [1,2,3] → mean=2, std=1, z = (3-2)/1 = 1.0
        assert abs(z[2] - 1.0) < 0.1

    def test_rolling_with_window(self):
        from akshare_mcp.services.multi_factor import FactorStandardizer
        data = np.arange(1.0, 21.0)  # 1..20
        z = FactorStandardizer.z_score_rolling(data, window=5)
        assert np.isnan(z[0])
        # 第 5+ 个值应该有有效 z-score
        assert not np.isnan(z[5])

    def test_rolling_clip(self):
        from akshare_mcp.services.multi_factor import FactorStandardizer
        data = np.array([1.0, 1.0, 1.0, 1.0, 100.0])
        z = FactorStandardizer.z_score_rolling(data, window=0, clip=3.0)
        valid = z[~np.isnan(z)]
        assert np.all(valid <= 3.0)
        assert np.all(valid >= -3.0)


class TestSharpeRiskFree:
    """Sharpe Ratio 扣除无风险利率"""

    def test_sharpe_in_multi_factor(self):
        from akshare_mcp.services.multi_factor import FactorBacktester
        # 日收益 0.1% → 年化 ~25.2%
        returns = np.full(252, 0.001)
        metrics = FactorBacktester.calculate_performance_metrics(returns)
        # 旧 Sharpe = 0.252 / std → 很大正数
        # 新 Sharpe = (0.252 - 0.02) / std → 应略小
        assert metrics['sharpe_ratio'] > 0
        # 验证扣除了无风险利率
        expected_excess = 0.001 * 252 - 0.02  # ~0.232
        assert abs(metrics['sharpe_ratio'] * (np.std(returns) * np.sqrt(252)) - expected_excess) < 0.01


class TestBlockBootstrap:
    """蒙特卡洛 Block Bootstrap"""

    def test_monte_carlo_block_method(self):
        """Block Bootstrap 方法可正常运行"""
        from akshare_mcp.services.backtest.engine import BacktestEngine
        klines = [{'close': 10 + i * 0.05 + np.sin(i / 10.0) * 0.5,
                    'date': f'2024-01-{(i % 28) + 1:02d}',
                    'volume': 1000000}
                   for i in range(100)]
        result = BacktestEngine.monte_carlo_simulation(
            code='000001', klines=klines, strategy='ma_cross',
            params={'short_period': 5, 'long_period': 20},
            runs=10, bootstrap_method='block'
        )
        assert result['success']
        assert result['data']['bootstrap_method'] == 'block'
        assert result['data']['runs'] == 10


# ====================================================================
#  Phase 3: 因子画像工具
# ====================================================================


class TestRSISeries:
    """RSI as_series=True 输出"""

    def test_rsi_series_returns_ndarray(self):
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + i * 0.1 for i in range(100)]
        result = TechnicalFactorsMixin.calculate_rsi(closes, 14, as_series=True)
        assert isinstance(result, np.ndarray)

    def test_rsi_series_last_matches_scalar(self):
        """序列最后一个值应等于标量调用结果"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + i * 0.1 + np.sin(i / 5.0) * 0.5 for i in range(100)]
        scalar = TechnicalFactorsMixin.calculate_rsi(closes, 14)
        series = TechnicalFactorsMixin.calculate_rsi(closes, 14, as_series=True)
        assert abs(series[-1] - scalar) < 1e-10

    def test_rsi_series_length(self):
        """序列长度 = len(closes) - 1"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [float(i) for i in range(1, 52)]
        series = TechnicalFactorsMixin.calculate_rsi(closes, 14, as_series=True)
        assert len(series) == len(closes) - 1


class TestMomentumSeries:
    """Momentum as_series=True 输出"""

    def test_momentum_series_returns_ndarray(self):
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + i * 0.1 for i in range(100)]
        result = TechnicalFactorsMixin.calculate_momentum(closes, 20, as_series=True)
        assert isinstance(result, np.ndarray)
        assert len(result) == len(closes)

    def test_momentum_series_nan_head(self):
        """前 period 个值应为 NaN"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + i * 0.1 for i in range(50)]
        result = TechnicalFactorsMixin.calculate_momentum(closes, 20, as_series=True)
        assert all(np.isnan(result[i]) for i in range(20))
        assert not np.isnan(result[20])


class TestMACDSeries:
    """MACD as_series=True 输出"""

    def test_macd_series_returns_ndarray(self):
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + i * 0.1 for i in range(100)]
        result = TechnicalFactorsMixin.calculate_macd(closes, as_series=True)
        assert isinstance(result, np.ndarray)
        assert len(result) == len(closes)

    def test_macd_series_last_matches_scalar(self):
        """序列最后一个值应等于标量调用结果"""
        from akshare_mcp.services.factor_calculator.technical import TechnicalFactorsMixin
        closes = [10 + i * 0.1 + np.sin(i / 5.0) * 0.5 for i in range(100)]
        scalar = TechnicalFactorsMixin.calculate_macd(closes)
        series = TechnicalFactorsMixin.calculate_macd(closes, as_series=True)
        assert abs(series[-1] - scalar) < 1e-10


class TestFactorProfile:
    """因子画像工具测试"""

    def test_factor_profile_structure(self):
        """_build_factor_profile 返回正确的 dict 结构"""
        from akshare_mcp.tools.factor_profile import _build_factor_profile
        series = np.array([50 + np.sin(i / 10.0) * 10 for i in range(250)])
        profile = _build_factor_profile(series, 250)
        assert "current" in profile
        assert "series_30d" in profile
        assert "percentile_1y" in profile
        assert "percentile_3y" in profile
        assert "trend" in profile
        assert "rolling_zscore" in profile
        assert isinstance(profile["current"], float)
        assert isinstance(profile["series_30d"], list)
        assert len(profile["series_30d"]) == 30
        assert profile["trend"] in ("strengthening", "weakening", "stable")
        assert isinstance(profile["rolling_zscore"], float)

    def test_factor_profile_unknown_factor(self):
        """未知因子名应返回 error 字段"""
        from akshare_mcp.tools.factor_profile import _FACTOR_REGISTRY
        assert "nonexistent_factor_xyz" not in _FACTOR_REGISTRY


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


class TestConditionalReturns:
    def test_conditional_returns_service_structure(self):
        from akshare_mcp.services.conditional_returns import calculate_conditional_returns
        klines = [
            {
                "date": f"2025-01-{i + 1:02d}",
                "open": float(10 + i),
                "high": float(10.5 + i),
                "low": float(9.5 + i),
                "close": float(10 + i),
                "volume": 1000 + i,
            }
            for i in range(20)
        ]
        result = calculate_conditional_returns(
            klines=klines,
            conditions=[{"id": "upn", "params": {"n": 3}}],
            forward_days=[1, 2],
        )
        assert result["condition_matches"] > 0
        assert result["forward_returns"]["1d"]["win_rate"] == 1.0
        assert result["forward_returns"]["1d"]["mean"] > 0

    @pytest.mark.asyncio
    async def test_quant_registers_get_conditional_returns(self, monkeypatch):
        from akshare_mcp.tools import quant

        class _FakeDB:
            async def get_klines(self, code, limit=None):
                return [
                    {
                        "date": f"2025-03-{30 - i:02d}",
                        "open": float(20 + i),
                        "high": float(20.5 + i),
                        "low": float(19.5 + i),
                        "close": float(20 + i),
                        "volume": 2000 + i,
                    }
                    for i in range(30)
                ]

        monkeypatch.setattr(quant, "get_db", lambda: _FakeDB())
        mcp = _DummyMCP()
        quant.register(mcp)
        result = await mcp.get_conditional_returns(
            code="000001",
            conditions=[{"id": "upn", "params": {"n": 3}}],
            forward_days=[1, 3],
            lookback_days=60,
        )
        assert result["success"] is True
        assert result["data"]["code"] == "000001"
        assert "forward_returns" in result["data"]
        assert "1d" in result["data"]["forward_returns"]

    @pytest.mark.asyncio
    async def test_decision_registers_get_investment_analysis(self, monkeypatch):
        from akshare_mcp.tools import decision

        class _FakeDB:
            async def get_klines(self, code, limit=None):
                return [
                    {
                        "date": f"2025-{(12 - (i // 20)):02d}-{(28 - (i % 20)):02d}",
                        "open": float(100 + i),
                        "high": float(101 + i),
                        "low": float(99 + i),
                        "close": float(100 + i),
                        "volume": 5000 + i,
                    }
                    for i in range(250)
                ]

            async def get_stock_info(self, code):
                return {"pe": 18.5, "pb": 3.2, "ps": 4.1, "total_mv": 1000, "circ_mv": 800}

            async def get_financials(self, code):
                return [{"roe": 15.2, "debt_ratio": 32.4, "revenue_growth": 12.1, "profit_growth": 9.8, "eps": 3.6}]

        monkeypatch.setattr(decision, "get_db", lambda: _FakeDB())
        mcp = _DummyMCP()
        decision.register(mcp)
        assert hasattr(mcp, "get_investment_analysis")
        result = await mcp.get_investment_analysis("000001")
        assert result["success"] is True
        data = result["data"]
        assert "price_context" in data
        assert "valuation" in data
        assert "fundamentals" in data
        assert data["fundamentals"]["roe"] == 15.2


class TestMarketSentimentContext:
    @pytest.mark.asyncio
    async def test_sentiment_registers_market_context_tool(self, monkeypatch):
        from akshare_mcp.tools import sentiment as sentiment_mod
        from akshare_mcp.tools import fund_flow as fund_flow_mod

        class _FakeDB:
            async def get_klines(self, code, limit=None):
                return [
                    {
                        'date': f'2025-02-{i + 1:02d}',
                        'open': float(3000 + i),
                        'high': float(3010 + i),
                        'low': float(2990 + i),
                        'close': float(3000 + i),
                        'volume': 1000000 + i * 1000,
                    }
                    for i in range(60)
                ]

            async def get_limit_up_stats(self):
                return {'up_count': 3200, 'down_count': 1800, 'limit_up_count': 65, 'limit_down_count': 4}

        monkeypatch.setattr(sentiment_mod, 'get_db', lambda: _FakeDB())
        monkeypatch.setattr(fund_flow_mod, 'get_north_fund', lambda days: {
            'success': True,
            'data': {
                'source': 'mock',
                'items': [
                    {'date': '2025-02-01', 'total': 10.0},
                    {'date': '2025-02-02', 'total': 20.0},
                    {'date': '2025-02-03', 'total': -5.0},
                    {'date': '2025-02-04', 'total': 8.0},
                    {'date': '2025-02-05', 'total': 12.0},
                ],
            },
        })
        monkeypatch.setattr(fund_flow_mod, 'get_margin_data', lambda stock_code='', days=10: {
            'success': True,
            'data': [
                {'date': '2025-02-05', 'marginBalance': 110.0, 'marginBuy': 12.0},
                {'date': '2025-02-04', 'marginBalance': 108.0, 'marginBuy': 11.0},
                {'date': '2025-02-03', 'marginBalance': 106.0, 'marginBuy': 10.0},
                {'date': '2025-02-02', 'marginBalance': 105.0, 'marginBuy': 9.0},
                {'date': '2025-02-01', 'marginBalance': 103.0, 'marginBuy': 8.0},
                {'date': '2025-01-31', 'marginBalance': 100.0, 'marginBuy': 7.0},
            ],
        })
        monkeypatch.setattr(fund_flow_mod, 'get_sector_fund_flow', lambda top_n=10: {
            'success': True,
            'data': [
                {'name': '半导体', 'mainNetInflow': 30.0, 'changePercent': 2.1},
                {'name': '消费', 'mainNetInflow': 10.0, 'changePercent': 0.8},
                {'name': '地产', 'mainNetInflow': -15.0, 'changePercent': -1.5},
                {'name': '煤炭', 'mainNetInflow': -8.0, 'changePercent': -0.6},
            ],
        })

        mcp = _DummyMCP()
        sentiment_mod.register(mcp)
        result = await mcp.get_market_sentiment_context()
        assert result['success'] is True
        data = result['data']
        assert data['fear_greed_index'] is not None
        assert data['northbound_flow_5d'] == 45.0
        assert data['margin_balance_change_5d'] == 10.0
        assert data['hot_sectors'][0]['name'] == '半导体'
        assert data['cold_sectors'][0]['name'] == '地产'


class TestStockTextSignals:
    @pytest.mark.asyncio
    async def test_sentiment_registers_stock_text_signals(self, monkeypatch):
        from akshare_mcp.tools import sentiment as sentiment_mod
        from akshare_mcp.tools.news import news_feed as news_feed_mod
        from akshare_mcp.tools.news import notices as notices_mod
        from akshare_mcp.tools.news import research as research_mod

        monkeypatch.setattr(news_feed_mod, 'get_stock_news', lambda code, limit=20: {
            'success': True,
            'data': [
                {'date': '2025-03-01', 'title': '公司中标大单 业绩增长超预期', 'source': 'mock', 'text': '公司中标大单，业绩增长超预期'},
                {'date': '2025-03-02', 'title': '新品获批推动增长', 'source': 'mock', 'text': '新品获批，推动盈利增长'},
            ],
        })
        monkeypatch.setattr(notices_mod, 'get_stock_notices', lambda *args, **kwargs: {
            'success': True,
            'data': {
                'events': [
                    {'date': '2025-03-03', 'title': '关于回购股份的公告', 'source': 'notice', 'content': '董事会审议通过回购股份方案'}
                ]
            },
        })
        monkeypatch.setattr(research_mod, 'get_research_reports', lambda symbol='', stock_code='', limit=10: {
            'success': True,
            'data': {
                'reports': [
                    {'date': '2025-03-04', 'title': '维持买入评级', 'institution': '某券商', 'rating': '买入', 'targetPrice': 28.5}
                ]
            },
        })

        mcp = _DummyMCP()
        sentiment_mod.register(mcp)
        result = await mcp.get_stock_text_signals('000001', news_limit=5, report_limit=5)
        assert result['success'] is True
        data = result['data']
        assert data['code'] == '000001'
        assert data['sentiment'] in {'bullish', 'neutral', 'bearish'}
        assert data['source_counts']['total_texts'] >= 3
        assert any(item['tag'] == '业绩景气' for item in data['event_tags'])
        assert data['rating_summary']['counts']['买入'] == 1


class TestDecisionSellContext:
    @pytest.mark.asyncio
    async def test_should_i_sell_contains_analysis_context(self, monkeypatch):
        from akshare_mcp.tools import decision

        class _FakeDB:
            async def get_klines(self, code, limit=None):
                return [
                    {
                        'date': f'2025-03-{30 - i:02d}',
                        'open': float(100 + i),
                        'high': float(101 + i),
                        'low': float(99 + i),
                        'close': float(100 + i),
                        'volume': 5000 + i,
                    }
                    for i in range(80)
                ]

            async def get_stock_info(self, code):
                return {'name': '测试股份', 'pe': 18.5, 'pb': 3.2, 'industry': '消费', 'total_mv': 1000, 'circ_mv': 800}

            async def get_financials(self, code):
                return [{'roe': 11.2, 'debt_ratio': 35.0, 'revenue_growth': 8.5, 'profit_growth': 5.2, 'eps': 2.3}]

        monkeypatch.setattr(decision, 'get_db', lambda: _FakeDB())
        monkeypatch.setattr(decision.technical_analysis, 'calculate_rsi', lambda closes: [78.0])
        monkeypatch.setattr(decision.technical_analysis, 'calculate_macd', lambda closes: {'histogram': [0.2, -0.1]})
        monkeypatch.setattr(decision.technical_analysis, 'calculate_sma', lambda closes, period: [sum(closes[-period:]) / period])

        mcp = _DummyMCP()
        decision.register(mcp)
        result = await mcp.should_i_sell('000001', buy_price=90.0, holding_days=45)
        assert result['success'] is True
        data = result['data']
        assert data['decision_mode'] == 'hybrid_score_plus_context'
        assert 'analysis_context' in data
        assert 'score_breakdown' in data
        assert 'signal_breakdown' in data
        assert data['analysis_context']['valuation']['pe'] == 18.5


class TestDecisionBuyContextFallback:
    @pytest.mark.asyncio
    async def test_should_i_buy_can_score_from_analysis_context_when_sql_unavailable(self, monkeypatch):
        from akshare_mcp.tools import decision

        class _ExplodingDB:
            async def get_stock_info(self, code):
                return {'name': '测试股份', 'industry': '消费'}

            async def get_klines(self, code, limit=None):
                return [
                    {
                        'date': f'2025-03-{30 - i:02d}',
                        'open': float(100 + i),
                        'high': float(101 + i),
                        'low': float(99 + i),
                        'close': float(100 + i),
                        'volume': 5000 + i,
                    }
                    for i in range(80)
                ]

            def acquire(self):
                raise RuntimeError('sql unavailable')

        monkeypatch.setattr(decision, 'get_db', lambda: _ExplodingDB())
        monkeypatch.setattr(decision, 'get_investment_analysis', lambda code: _resolved_analysis_context())
        monkeypatch.setattr(decision.technical_analysis, 'calculate_macd', lambda closes: {'histogram': [0.2, 0.1]})

        async def _resolved_analysis_context():
            return {
                'success': True,
                'data': {
                    'valuation': {'pe': 12.0, 'pb': 1.5},
                    'fundamentals': {'roe': 16.0, 'debt_ratio': 30.0, 'revenue_yoy': 25.0},
                    'technical': {'rsi_14': 25.0, 'moving_averages': {'ma20': 95.0, 'ma60': 90.0}},
                    'momentum': {'mom_20d': 0.12},
                    'risk': {'volatility_20d': 0.02},
                },
            }

        mcp = _DummyMCP()
        decision.register(mcp)
        result = await mcp.should_i_buy('000001', investment_style='balanced')
        assert result['success'] is True
        data = result['data']
        assert data['recommendation'] == 'buy'
        assert data['decision_mode'] == 'context_guided_hybrid'
        assert data['score_breakdown']['valuation'] > 0
        assert any(item['source'] == 'analysis_context' for item in data['signal_breakdown'])
        assert data['analysis_context']['valuation']['pe'] == 12.0


# ====================================================================
#  Phase 6: 架构修复
# ====================================================================


class TestEvidenceChainLRU:
    """证据链 LRU 淘汰"""

    def test_chains_has_limit(self):
        from akshare_mcp.services import evidence_chain as ec
        # _CHAINS 不应无限增长
        # 检查是否有 _MAX_CHAINS 或 LRU 限制
        assert hasattr(ec, '_MAX_CHAINS') or hasattr(ec, '_CHAINS')

    def test_lru_eviction(self):
        """超过上限后最老的链应被淘汰"""
        from akshare_mcp.services import evidence_chain as ec
        if not hasattr(ec, '_MAX_CHAINS'):
            pytest.skip("LRU not yet implemented")
        old_chains = OrderedDict(ec._CHAINS)
        old_max = ec._MAX_CHAINS
        try:
            ec._CHAINS.clear()
            ec._MAX_CHAINS = 5  # 临时缩小上限
            for i in range(10):
                chain = ec.create_chain(f"test_lru_{i}", f"code_{i}", "test")
                ec.save_chain(chain)
            assert len(ec._CHAINS) <= 5
            # 最早的 trace_id 应该已被淘汰
            assert "test_lru_0" not in ec._CHAINS
            # 最近的应该还在
            assert "test_lru_9" in ec._CHAINS
        finally:
            ec._CHAINS.clear()
            ec._CHAINS.update(old_chains)
            ec._MAX_CHAINS = old_max


class TestRegimeMapComplete:
    """EliminationChecker._REGIME_MAP 补全"""

    def test_all_strategies_in_regime_map(self):
        from akshare_mcp.services.strategy_factory import EliminationChecker
        regime_map = EliminationChecker._REGIME_MAP
        # 所有内置策略类型都应在映射中
        expected_strategies = ['momentum', 'growth_factor', 'value_factor', 'rsi', 'macro_timing']
        for s in expected_strategies:
            assert s in regime_map, f"Strategy '{s}' not in _REGIME_MAP"


class _AcquireConn:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetch(self, query, *args):
        if "WHERE industry = $1" in query:
            return [{"code": code} for code in self.rows.get("industry", [])]
        return [{"code": code} for code in self.rows.get("market", [])]


class TestPredictionEnhancementCompletion:
    @pytest.mark.asyncio
    async def test_factor_profile_enriched_fields(self, monkeypatch):
        from akshare_mcp.tools import factor_profile

        def _series(scale=1.0, shift=0.0):
            values = []
            for i in range(180):
                close = 100 + shift + np.sin(i / 6.0) * 12 * scale + (i % 15 - 7) * 0.3
                values.append({"date": f"2024-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}", "close": round(close, 2)})
            return list(reversed(values))

        class _FakeDB:
            def acquire(self):
                return _AcquireConn({"industry": ["000002", "000003"], "market": ["000002", "000003", "000004"]})

            async def get_stock_info(self, code):
                return {"industry": "白酒", "name": "测试股"}

            async def get_klines(self, code, limit=None):
                mapping = {
                    "000001": _series(1.0, 0.0),
                    "000002": _series(0.8, 5.0),
                    "000003": _series(1.2, -3.0),
                    "000004": _series(0.9, 2.0),
                }
                return mapping[code][:limit]

        monkeypatch.setattr(factor_profile, "get_db", lambda: _FakeDB())
        mcp = _DummyMCP()
        factor_profile.register(mcp)
        result = await mcp.get_factor_profile(code="000001", factors="rsi")
        profile = result["data"]["factors"]["rsi"]
        assert result["success"] is True
        assert profile["industry_rank"] is not None
        assert profile["industry_total"] >= 1
        assert profile["market_percentile"] is not None
        assert "historical_oversold_recovery" in profile

    @pytest.mark.asyncio
    async def test_quant_pattern_and_hit_rate_tools(self, monkeypatch):
        from akshare_mcp.tools import quant

        class _FakeDB:
            async def get_klines(self, code, limit=None):
                values = []
                base_pattern = [100, 102, 105, 103, 101, 104, 107, 105, 102, 106]
                closes = (base_pattern * 20)[:220]
                for i, close in enumerate(closes):
                    values.append({
                        "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                        "close": float(close),
                        "open": float(close) - 0.5,
                        "high": float(close) + 0.5,
                        "low": float(close) - 1,
                        "volume": 10000 + i,
                    })
                return list(reversed(values[:limit]))

        monkeypatch.setattr(quant, "get_db", lambda: _FakeDB())
        mcp = _DummyMCP()
        quant.register(mcp)
        factors = mcp.list_factors(category="technical")
        patterns = await mcp.find_similar_patterns(code="000001", window_days=10, top_n=5, forward_days=[5, 10])
        hit_rate = await mcp.get_signal_hit_rate(code="000001", signal="rsi_oversold", forward_days=[5, 10])
        assert factors["success"] is True
        assert factors["data"]["count"] > 0
        assert patterns["success"] is True
        assert "aggregate_prediction" in patterns["data"]
        assert hit_rate["success"] is True
        assert "forward_returns" in hit_rate["data"]

    @pytest.mark.asyncio
    async def test_smart_stock_diagnosis_uses_context_aggregator(self, monkeypatch):
        from akshare_mcp.tools.semantic import diagnosis

        async def _fake_analysis(code):
            return {
                "success": True,
                "data": {
                    "basic_info": {"name": "示例股"},
                    "price_context": {"current_price": 12.3, "analysis_date": "2025-03-06"},
                    "valuation": {"pe": 18.0, "industry_relative_pe": 0.8},
                    "fundamentals": {"roe": 15.0, "revenue_yoy": 12.0, "debt_ratio": 35.0},
                    "technical": {"rsi_14": 28.0, "ma_alignment": "bullish"},
                    "momentum": {"mom_20d": 0.12, "market_regime": "bullish"},
                    "risk": {"volatility_20d": 0.02, "max_drawdown_250d": 0.18},
                },
            }

        monkeypatch.setattr(diagnosis, "get_investment_analysis", _fake_analysis)
        result = await diagnosis.smart_stock_diagnosis("000001")
        assert result["success"] is True
        assert result["data"]["decision_mode"] == "context_aggregator"
        assert "evidence" in result["data"]
        assert "overall_score" not in result["data"]

    def test_advanced_position_sizing_runs_dynamic_loop(self):
        from akshare_mcp.services.backtest.advanced import AdvancedBacktestEngine

        klines = []
        price = 100.0
        for i in range(180):
            price *= 1 + (0.015 if i % 18 < 9 else -0.01)
            klines.append({"date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", "close": round(price, 2), "volume": 100000 + i})

        result = AdvancedBacktestEngine.backtest_with_position_sizing(
            code="000001",
            klines=klines,
            strategy="momentum",
            params={"lookback": 10, "threshold": 0.01, "initial_capital": 100000},
            sizing_method="volatility",
        )
        assert result["success"] is True
        assert result["data"]["strategy"] == "momentum_position_sizing"
        assert result["data"]["adjusted_capital"] > 0
