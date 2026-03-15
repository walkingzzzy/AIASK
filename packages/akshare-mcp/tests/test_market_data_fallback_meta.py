import pytest
from akshare_mcp.data_source.market_data import MarketDataMixin
import akshare_mcp.data_source.market_data as market_data_mod


class _FakeSeries(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _FakeILoc:
    def __init__(self, row):
        self._row = _FakeSeries(row)

    def __getitem__(self, index):
        assert index == 0
        return self._row


class _FakeRowFrame:
    def __init__(self, row):
        self.empty = False
        self.iloc = _FakeILoc(row)


class _FakeDailyBasicFrame:
    empty = False

    def __init__(self, rows):
        self._rows = rows

    def head(self, count):
        self._head_rows = self._rows[:count]
        return self

    def iterrows(self):
        for idx, row in enumerate(getattr(self, '_head_rows', self._rows)):
            yield idx, row


class _StubMarketData(MarketDataMixin):
    def __init__(self, *, tdx_available=False, tq=None, ts_pro=None):
        self._tdx_available = tdx_available
        self._tq = tq
        self.ts_pro = ts_pro

    def is_tdx_available(self):
        return self._tdx_available

    def get_tdxquant(self):
        return self._tq

    def _convert_to_tdx_code(self, stock_code):
        return stock_code


def test_get_trading_dates_invalid_start_time_has_normalized_fallback_meta():
    ds = _StubMarketData()

    result = ds.get_trading_dates(start_time='2026-01-01')

    assert result['success'] is False
    assert result['source'] == 'none'
    assert result['asof_time']
    assert result['freshness_sec'] == 0.0
    assert 'fallback' in result['quality_flags']
    assert 'degraded' in result['quality_flags']
    assert 'invalid_request' in result['quality_flags']
    assert result['backend_requested'] == 'tdx'
    assert result['backend_used'] == 'none'
    assert result['fallback_used'] is True
    assert result['fallback_reason'] == 'invalid_start_time'
    assert result['latency_ms'] >= 0


def test_get_cb_info_tushare_fallback_has_normalized_meta():
    class _FakeTsPro:
        def cb_basic(self, ts_code):
            assert ts_code == '123039.SZ'
            return _FakeRowFrame({
                'stk_code': '300001',
                'conv_price': 12.3,
                'conv_start_date': '20260101',
                'maturity_date': '20310101',
                'issue_size': 8.8,
            })

    ds = _StubMarketData(ts_pro=_FakeTsPro())

    result = ds.get_cb_info('123039')

    assert result['success'] is True
    assert result['source'] == 'tushare_pro'
    assert result['asof_time']
    assert result['freshness_sec'] == 0.0
    assert result['quality_flags'] == ['fallback']
    assert result['backend_requested'] == 'tdx'
    assert result['backend_used'] == 'tushare_pro'
    assert result['fallback_used'] is True
    assert result['fallback_reason'] is None
    assert result['latency_ms'] >= 0
    assert result['data']['KZZCode'] == '123039'


def test_get_gb_info_akshare_fallback_has_normalized_meta(monkeypatch):
    class _FakeAkFrame:
        empty = False

        def __getitem__(self, key):
            if key == 'item':
                return ['流通股', '总股本']
            if key == 'value':
                return ['123.4', '456.7']
            raise KeyError(key)

    class _NoTsPro:
        def daily_basic(self, **kwargs):
            return None

    class _FakeAk:
        @staticmethod
        def stock_individual_info_em(symbol):
            assert symbol == '600519'
            return _FakeAkFrame()

    monkeypatch.setattr(market_data_mod, 'ak', _FakeAk)
    ds = _StubMarketData(ts_pro=_NoTsPro())

    result = ds.get_gb_info('600519', count=1)

    assert result['success'] is True
    assert result['source'] == 'akshare'
    assert result['asof_time']
    assert result['freshness_sec'] == 0.0
    assert result['quality_flags'] == ['fallback']
    assert result['backend_requested'] == 'tdx'
    assert result['backend_used'] == 'akshare'
    assert result['fallback_used'] is True
    assert result['fallback_reason'] is None
    assert result['latency_ms'] >= 0
    assert result['data'][0]['zgb'] == 456.7
