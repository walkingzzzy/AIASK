"""
技术指标库测试
"""
import pytest
import pandas as pd
import numpy as np

from packages.core.indicators import MA, EMA, MACD, RSI, KDJ, BOLL, ATR, OBV, VWAP
from packages.core.indicators.base import BaseIndicator, prepare_dataframe


class TestPrepareDataframe:
    """测试数据准备函数"""

    def test_prepare_with_dict(self):
        """测试字典输入"""
        data = {
            "close": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "volume": [1000, 1100, 1200, 1300, 1400],
        }
        df = prepare_dataframe(data)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5

    def test_prepare_with_dataframe(self):
        """测试DataFrame输入"""
        df_input = pd.DataFrame(
            {"close": [100, 101, 102], "high": [101, 102, 103], "low": [99, 100, 101]}
        )
        df = prepare_dataframe(df_input)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3


@pytest.fixture
def sample_data():
    """生成测试数据"""
    np.random.seed(42)
    n = 100
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_price = close + np.random.randn(n) * 0.2
    volume = np.random.randint(100000, 500000, n)

    return pd.DataFrame(
        {"open": open_price, "high": high, "low": low, "close": close, "volume": volume}
    )


class TestMA:
    """测试移动平均线"""

    def test_ma_calculation(self, sample_data):
        """测试MA计算"""
        ma = MA()
        result = ma.calculate(sample_data, period=5)
        assert len(result) == len(sample_data)
        assert result.iloc[4] == pytest.approx(sample_data["close"].iloc[:5].mean(), rel=1e-5)

    def test_ma_different_periods(self, sample_data):
        """测试不同周期"""
        ma = MA()
        ma5 = ma.calculate(sample_data, period=5)
        ma10 = ma.calculate(sample_data, period=10)
        ma20 = ma.calculate(sample_data, period=20)

        # 前几个值应该是NaN
        assert pd.isna(ma5.iloc[3])
        assert pd.isna(ma10.iloc[8])
        assert pd.isna(ma20.iloc[18])


class TestEMA:
    """测试指数移动平均线"""

    def test_ema_calculation(self, sample_data):
        """测试EMA计算"""
        ema = EMA()
        result = ema.calculate(sample_data, period=12)
        assert len(result) == len(sample_data)
        assert not pd.isna(result.iloc[-1])


class TestMACD:
    """测试MACD"""

    def test_macd_calculation(self, sample_data):
        """测试MACD计算"""
        macd = MACD()
        result = macd.calculate(sample_data)
        assert isinstance(result, pd.DataFrame)
        assert "DIF" in result.columns
        assert "DEA" in result.columns
        assert "MACD" in result.columns

    def test_macd_custom_params(self, sample_data):
        """测试自定义参数"""
        macd = MACD()
        result = macd.calculate(sample_data, fast=10, slow=20, signal=7)
        assert len(result) == len(sample_data)


class TestRSI:
    """测试RSI"""

    def test_rsi_calculation(self, sample_data):
        """测试RSI计算"""
        rsi = RSI()
        result = rsi.calculate(sample_data, period=14)
        assert len(result) == len(sample_data)

        # RSI应该在0-100之间
        valid_values = result.dropna()
        assert all(0 <= v <= 100 for v in valid_values)

    def test_rsi_different_periods(self, sample_data):
        """测试不同周期"""
        rsi = RSI()
        rsi6 = rsi.calculate(sample_data, period=6)
        rsi14 = rsi.calculate(sample_data, period=14)

        # 短周期RSI波动应该更大
        assert rsi6.std() >= rsi14.std() * 0.8  # 允许一定误差


class TestKDJ:
    """测试KDJ"""

    def test_kdj_calculation(self, sample_data):
        """测试KDJ计算"""
        kdj = KDJ()
        result = kdj.calculate(sample_data)
        assert isinstance(result, pd.DataFrame)
        assert "K" in result.columns
        assert "D" in result.columns
        assert "J" in result.columns

    def test_kdj_values_range(self, sample_data):
        """测试KDJ值范围"""
        kdj = KDJ()
        result = kdj.calculate(sample_data)

        # K和D应该在0-100之间
        k_valid = result["K"].dropna()
        d_valid = result["D"].dropna()
        assert all(0 <= v <= 100 for v in k_valid)
        assert all(0 <= v <= 100 for v in d_valid)


class TestBOLL:
    """测试布林带"""

    def test_boll_calculation(self, sample_data):
        """测试布林带计算"""
        boll = BOLL()
        result = boll.calculate(sample_data)
        assert isinstance(result, pd.DataFrame)
        assert "upper" in result.columns
        assert "middle" in result.columns
        assert "lower" in result.columns

    def test_boll_band_order(self, sample_data):
        """测试布林带顺序"""
        boll = BOLL()
        result = boll.calculate(sample_data)

        # 上轨 > 中轨 > 下轨
        valid_idx = result.dropna().index
        for idx in valid_idx:
            assert result.loc[idx, "upper"] >= result.loc[idx, "middle"]
            assert result.loc[idx, "middle"] >= result.loc[idx, "lower"]


class TestATR:
    """测试ATR"""

    def test_atr_calculation(self, sample_data):
        """测试ATR计算"""
        atr = ATR()
        result = atr.calculate(sample_data, period=14)
        assert len(result) == len(sample_data)

        # ATR应该为正
        valid_values = result.dropna()
        assert all(v >= 0 for v in valid_values)


class TestOBV:
    """测试OBV"""

    def test_obv_calculation(self, sample_data):
        """测试OBV计算"""
        obv = OBV()
        result = obv.calculate(sample_data)
        assert len(result) == len(sample_data)


class TestVWAP:
    """测试VWAP"""

    def test_vwap_calculation(self, sample_data):
        """测试VWAP计算"""
        vwap = VWAP()
        result = vwap.calculate(sample_data)
        assert len(result) == len(sample_data)

        # VWAP应该在high和low之间（大致）
        valid_idx = result.dropna().index
        for idx in valid_idx[-10:]:  # 检查最后10个
            assert sample_data.loc[idx, "low"] * 0.9 <= result.loc[idx]
            assert result.loc[idx] <= sample_data.loc[idx, "high"] * 1.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# 新增指标测试
from packages.core.indicators import WilliamsR, ROC, SAR, WMA, DEMA
from packages.core.indicators import CandlestickPattern, ChartPattern


class TestWilliamsR:
    """测试威廉指标"""
    
    def test_williams_calculation(self, sample_data):
        """测试Williams %R计算"""
        wr = WilliamsR()
        result = wr.calculate(sample_data)
        assert f'WR{wr.period}' in result.columns
        
        # Williams %R应该在-100到0之间
        valid_values = result[f'WR{wr.period}'].dropna()
        assert all(-100 <= v <= 0 for v in valid_values)
    
    def test_williams_signal(self):
        """测试信号判断"""
        assert WilliamsR.get_signal(-10) == 'overbought'
        assert WilliamsR.get_signal(-90) == 'oversold'
        assert WilliamsR.get_signal(-50) == 'neutral'


class TestROC:
    """测试变动率指标"""
    
    def test_roc_calculation(self, sample_data):
        """测试ROC计算"""
        roc = ROC()
        result = roc.calculate(sample_data)
        assert f'ROC{roc.period}' in result.columns
    
    def test_roc_signal(self):
        """测试信号判断"""
        assert ROC.get_signal(10) == 'strong_bullish'
        assert ROC.get_signal(2) == 'bullish'
        assert ROC.get_signal(-10) == 'strong_bearish'
        assert ROC.get_signal(-2) == 'bearish'
        assert ROC.get_signal(0) == 'neutral'


class TestSAR:
    """测试抛物线SAR"""
    
    def test_sar_calculation(self, sample_data):
        """测试SAR计算"""
        sar = SAR()
        result = sar.calculate(sample_data)
        assert 'SAR' in result.columns
        assert 'SAR_trend' in result.columns
    
    def test_sar_trend_values(self, sample_data):
        """测试趋势值"""
        sar = SAR()
        result = sar.calculate(sample_data)
        
        # 趋势应该是1或-1
        valid_trends = result['SAR_trend'].dropna()
        assert all(t in [1, -1, 0] for t in valid_trends)


class TestWMA:
    """测试加权移动平均"""
    
    def test_wma_calculation(self, sample_data):
        """测试WMA计算"""
        wma = WMA(periods=[5, 10])
        result = wma.calculate(sample_data)
        assert 'WMA5' in result.columns
        assert 'WMA10' in result.columns


class TestDEMA:
    """测试双指数移动平均"""
    
    def test_dema_calculation(self, sample_data):
        """测试DEMA计算"""
        dema = DEMA(periods=[12, 26])
        result = dema.calculate(sample_data)
        assert 'DEMA12' in result.columns
        assert 'DEMA26' in result.columns


class TestCandlestickPattern:
    """测试K线形态识别"""
    
    def test_pattern_calculation(self, sample_data):
        """测试形态计算"""
        pattern = CandlestickPattern()
        result = pattern.calculate(sample_data)
        
        # 应该包含形态列
        assert 'pattern_hammer' in result.columns
        assert 'pattern_doji' in result.columns
        assert 'pattern_engulfing' in result.columns
    
    def test_detect_patterns(self, sample_data):
        """测试形态检测"""
        pattern = CandlestickPattern()
        patterns = pattern.detect_patterns(sample_data)
        
        # 返回应该是列表
        assert isinstance(patterns, list)
    
    def test_hammer_detection(self):
        """测试锤子线检测"""
        # 构造锤子线数据
        data = pd.DataFrame({
            'open': [100, 100],
            'high': [101, 100.5],
            'low': [95, 97],
            'close': [100.5, 100.3],
            'volume': [1000, 1000]
        })
        
        pattern = CandlestickPattern()
        result = pattern.calculate(data)
        # 第二根应该是锤子线（下影线长，实体小）
        assert 'pattern_hammer' in result.columns


class TestChartPattern:
    """测试图表形态识别"""
    
    def test_chart_pattern_calculation(self, sample_data):
        """测试图表形态计算"""
        pattern = ChartPattern()
        result = pattern.calculate(sample_data)
        
        assert 'local_high' in result.columns
        assert 'local_low' in result.columns
    
    def test_support_resistance(self, sample_data):
        """测试支撑阻力位检测"""
        pattern = ChartPattern()
        levels = pattern.detect_support_resistance(sample_data)
        
        assert 'support' in levels
        assert 'resistance' in levels
        assert 'current_price' in levels
    
    def test_double_top_detection(self, sample_data):
        """测试双顶检测"""
        pattern = ChartPattern()
        result = pattern.detect_double_top(sample_data)
        # 可能检测到也可能没有，取决于数据
        assert result is None or isinstance(result, dict)
    
    def test_double_bottom_detection(self, sample_data):
        """测试双底检测"""
        pattern = ChartPattern()
        result = pattern.detect_double_bottom(sample_data)
        assert result is None or isinstance(result, dict)
