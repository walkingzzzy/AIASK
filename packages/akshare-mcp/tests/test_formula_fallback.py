"""TDX 公式回退 Pure Python 实现 - 单元测试"""
import sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages', 'akshare-mcp', 'src'))
random.seed(42)
_BASE_CLOSES = [10.0]
for _i in range(99):
    _BASE_CLOSES.append(round(_BASE_CLOSES[-1] * (1 + random.gauss(0.001, 0.02)), 2))
_BASE_HIGHS = [c * (1 + abs(random.gauss(0, 0.01))) for c in _BASE_CLOSES]
_BASE_LOWS = [c * (1 - abs(random.gauss(0, 0.01))) for c in _BASE_CLOSES]
_BASE_VOLUMES = [int(random.uniform(500000, 2000000)) for _ in range(100)]

class TestTdxSma:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import _tdx_sma
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _tdx_sma(data, 3, 1)
        assert len(result) == 5
        assert result[0] == 1.0
        expected_1 = (1 * 2.0 + 2 * 1.0) / 3
        assert abs(result[1] - expected_1) < 1e-10
    def test_empty(self):
        from akshare_mcp.services.technical_analysis import _tdx_sma
        assert _tdx_sma([], 3) == []
    def test_single(self):
        from akshare_mcp.services.technical_analysis import _tdx_sma
        assert _tdx_sma([5.0], 3) == [5.0]
    def test_m_equals_n(self):
        from akshare_mcp.services.technical_analysis import _tdx_sma
        data = [1.0, 2.0, 3.0, 4.0]
        result = _tdx_sma(data, 3, 3)
        for i in range(len(data)):
            assert abs(result[i] - data[i]) < 1e-10

class TestTRIX:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_trix(_BASE_CLOSES, n=12, m=20)
        assert 'TRIX' in result and 'MATRIX' in result
        assert len(result['TRIX']) == 100
    def test_short_data(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_trix([10.0, 11.0, 12.0], n=2, m=2)
        assert len(result['TRIX']) == 3

class TestDMA:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_dma_indicator(_BASE_CLOSES, short=10, long_period=50, m=10)
        assert 'DIF' in result and 'DIFMA' in result
        assert len(result['DIF']) == 100
    def test_dif_sign(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        up = [10.0 + i * 0.5 for i in range(100)]
        result = TA.calculate_dma_indicator(up, short=5, long_period=20, m=5)
        assert result['DIF'][-1] > 0

class TestEXPMA:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_expma(_BASE_CLOSES, n1=12, n2=50)
        assert 'EXP1' in result and 'EXP2' in result
        assert len(result['EXP1']) == 100
    def test_short_faster(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_expma(_BASE_CLOSES, n1=5, n2=50)
        last = _BASE_CLOSES[-1]
        assert abs(result['EXP1'][-1] - last) <= abs(result['EXP2'][-1] - last)

class TestDMI:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_dmi(_BASE_HIGHS, _BASE_LOWS, _BASE_CLOSES, n=14, m=6)
        assert all(k in result for k in ['PDI', 'MDI', 'ADX', 'ADXR'])
        assert len(result['PDI']) == 100
    def test_values_non_negative(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_dmi(_BASE_HIGHS, _BASE_LOWS, _BASE_CLOSES)
        for key in ['PDI', 'MDI', 'ADX']:
            for v in result[key][14:]:
                assert v >= -0.01, f"{key} has negative value: {v}"
    def test_short_data(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_dmi([10.0], [9.0], [9.5])
        assert result == {'PDI': [], 'MDI': [], 'ADX': [], 'ADXR': []}

class TestCR:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_cr_indicator(_BASE_HIGHS, _BASE_LOWS, _BASE_CLOSES, n=26)
        assert 'CR' in result and 'MA1' in result and 'MA2' in result
        assert len(result['CR']) == 100
    def test_cr_non_negative(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_cr_indicator(_BASE_HIGHS, _BASE_LOWS, _BASE_CLOSES)
        for v in result['CR'][26:]:
            assert v >= 0

class TestVR:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_vr_indicator(_BASE_CLOSES, _BASE_VOLUMES, n=26, m=6)
        assert 'VR' in result and 'MAVR' in result
        assert len(result['VR']) == 100
    def test_vr_non_negative(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_vr_indicator(_BASE_CLOSES, _BASE_VOLUMES)
        for v in result['VR'][26:]:
            assert v >= 0

class TestRSISeries:
    def test_basic(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_rsi_series(_BASE_CLOSES, period=14)
        assert isinstance(result, list)
        assert len(result) == 100
    def test_range(self):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis as TA
        result = TA.calculate_rsi_series(_BASE_CLOSES, period=6)
        for v in result[6:]:
            assert 0 <= v <= 100

class TestFallbackDispatch:
    def _calc(self, name, args_str=''):
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis
        t = TechnicalAnalysis()
        c, h, lo, vol = _BASE_CLOSES, _BASE_HIGHS, _BASE_LOWS, _BASE_VOLUMES
        a = [int(x.strip()) for x in args_str.split(',') if x.strip()] if args_str else []
        nm = name.upper()
        if nm == 'MACD':
            f, s, sig = (a + [12, 26, 9])[:3]
            r = t.calculate_macd(c, f, s, sig)
            return {'DIF': r['macd'], 'DEA': r['signal'], 'MACD': [x*2 for x in r['histogram']]}
        elif nm == 'KDJ':
            n, m1, m2 = (a + [9, 3, 3])[:3]
            r = t.calculate_kdj(h, lo, c, n, m1, m2)
            return {'K': r['k'], 'D': r['d'], 'J': r['j']}
        elif nm == 'RSI':
            n1, n2, n3 = (a + [6, 12, 24])[:3]
            return {'RSI1': t.calculate_rsi_series(c, n1), 'RSI2': t.calculate_rsi_series(c, n2), 'RSI3': t.calculate_rsi_series(c, n3)}
        elif nm == 'BOLL':
            n, p = (a + [20, 2])[:2]
            r = t.calculate_bollinger_bands(c, n, float(p))
            return {'BOLL': r['middle'], 'UB': r['upper'], 'LB': r['lower']}
        elif nm == 'TRIX':
            return t.calculate_trix(c, a[0] if a else 12)
        elif nm == 'DMA':
            sh, lp, m = (a + [10, 50, 10])[:3]
            return t.calculate_dma_indicator(c, sh, lp, m)
        elif nm == 'EXPMA':
            n1, n2 = (a + [12, 50])[:2]
            return t.calculate_expma(c, n1, n2)
        elif nm == 'DMI':
            n, m = (a + [14, 6])[:2]
            return t.calculate_dmi(h, lo, c, n, m)
        elif nm == 'CR':
            return t.calculate_cr_indicator(h, lo, c, a[0] if a else 26)
        elif nm == 'VR':
            return t.calculate_vr_indicator(c, vol, a[0] if a else 26)
        return None
    def test_macd(self):
        assert all(k in self._calc('MACD', '12,26,9') for k in ['DIF', 'DEA', 'MACD'])
    def test_kdj(self):
        assert all(k in self._calc('KDJ', '9,3,3') for k in ['K', 'D', 'J'])
    def test_rsi(self):
        assert all(k in self._calc('RSI', '6,12,24') for k in ['RSI1', 'RSI2', 'RSI3'])
    def test_boll(self):
        assert all(k in self._calc('BOLL', '20,2') for k in ['BOLL', 'UB', 'LB'])
    def test_trix(self):
        assert 'TRIX' in self._calc('TRIX', '12')
    def test_dma(self):
        assert all(k in self._calc('DMA', '10,50,10') for k in ['DIF', 'DIFMA'])
    def test_expma(self):
        assert all(k in self._calc('EXPMA', '12,50') for k in ['EXP1', 'EXP2'])
    def test_dmi(self):
        assert all(k in self._calc('DMI', '14,6') for k in ['PDI', 'MDI', 'ADX', 'ADXR'])
    def test_cr(self):
        assert 'CR' in self._calc('CR', '26')
    def test_vr(self):
        assert 'VR' in self._calc('VR', '26')
    def test_unsupported(self):
        assert self._calc('UNKNOWN') is None
