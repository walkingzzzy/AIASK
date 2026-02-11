"""
增强选股引擎 - 单元测试

测试范围:
  1. screen_engine.py 核心引擎（注册、评估、扫描）
  2. screen_conditions.py 所有条件分类
  3. 组合策略
  4. AND/OR 逻辑

运行: pytest tests/test_screen_engine.py -v
"""

import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages', 'akshare-mcp', 'src'))

from akshare_mcp.services.screen_engine import engine
# 导入条件库以触发注册
from akshare_mcp.services import screen_conditions  # noqa: F401


# ============== 测试数据生成 ==============

random.seed(42)


def make_klines(n=100, trend='up', volatility=0.02, start_price=10.0,
                start_volume=1000000):
    """生成模拟 K 线"""
    closes = [start_price]
    for i in range(n - 1):
        if trend == 'up':
            drift = 0.003
        elif trend == 'down':
            drift = -0.003
        else:
            drift = 0.0
        change = random.gauss(drift, volatility)
        closes.append(round(closes[-1] * (1 + change), 2))

    klines = []
    for i, c in enumerate(closes):
        h = round(c * (1 + abs(random.gauss(0, 0.008))), 2)
        l = round(c * (1 - abs(random.gauss(0, 0.008))), 2)
        o = round(c * (1 + random.gauss(0, 0.005)), 2)
        v = int(start_volume * (1 + random.gauss(0, 0.3)))
        klines.append({
            'date': f'2025-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}',
            'open': o, 'high': max(h, o, c), 'low': min(l, o, c),
            'close': c, 'volume': max(v, 100), 'amount': c * max(v, 100),
        })
    return klines


def make_upn_klines(n_up=5):
    """生成连续上涨 K 线"""
    closes = [10.0]
    for i in range(n_up):
        closes.append(round(closes[-1] * 1.03, 2))
    klines = []
    for i, c in enumerate(closes):
        klines.append({
            'date': f'2025-01-{i + 1:02d}',
            'open': round(c * 0.99, 2),
            'high': round(c * 1.01, 2),
            'low': round(c * 0.98, 2),
            'close': c,
            'volume': 1000000,
            'amount': c * 1000000,
        })
    return klines


def make_limit_up_klines(n_limit=2):
    """生成涨停 K 线"""
    base = 10.0
    klines = [{
        'date': '2025-01-01', 'open': base, 'high': base,
        'low': base, 'close': base, 'volume': 1000000, 'amount': base * 1000000,
    }]
    for i in range(n_limit):
        prev_close = klines[-1]['close']
        limit_price = round(prev_close * 1.1, 2)
        klines.append({
            'date': f'2025-01-{i + 2:02d}',
            'open': limit_price,
            'high': limit_price,
            'low': round(prev_close * 1.05, 2),
            'close': limit_price,
            'volume': 500000 if i > 0 else 1000000,
            'amount': limit_price * 500000,
        })
    return klines


# ============== 引擎核心测试 ==============

class TestScreenEngine:
    def test_list_conditions(self):
        conditions = engine.list_conditions()
        assert len(conditions) > 40, f"Expected 40+ conditions, got {len(conditions)}"

    def test_list_categories(self):
        categories = engine.list_categories()
        cat_ids = [c['id'] for c in categories]
        assert 'trend' in cat_ids
        assert 'indicator' in cat_ids
        assert 'volume' in cat_ids
        assert 'pattern' in cat_ids
        assert 'astock' in cat_ids
        assert 'composite' in cat_ids

    def test_list_conditions_by_category(self):
        trend_conds = engine.list_conditions('trend')
        assert all(c['category'] == 'trend' for c in trend_conds)
        assert len(trend_conds) > 5

    def test_evaluate_single(self):
        klines = make_upn_klines(5)
        result = engine.evaluate('upn', klines, {'n': 3})
        assert result is True

    def test_evaluate_fail(self):
        klines = make_klines(50, trend='down')
        result = engine.evaluate('upn', klines, {'n': 5})
        assert result is False

    def test_evaluate_multi_and(self):
        klines = make_upn_klines(5)
        result = engine.evaluate_multi(
            [{'id': 'upn', 'params': {'n': 3}}, {'id': 'upn', 'params': {'n': 2}}],
            klines,
            logic='AND'
        )
        assert result['match'] is True

    def test_evaluate_multi_or(self):
        klines = make_upn_klines(3)
        result = engine.evaluate_multi(
            [{'id': 'upn', 'params': {'n': 10}}, {'id': 'upn', 'params': {'n': 2}}],
            klines,
            logic='OR'
        )
        assert result['match'] is True

    def test_evaluate_multi_and_fail(self):
        klines = make_upn_klines(3)
        result = engine.evaluate_multi(
            [{'id': 'upn', 'params': {'n': 2}}, {'id': 'upn', 'params': {'n': 10}}],
            klines,
            logic='AND'
        )
        assert result['match'] is False

    def test_scan(self):
        stock_data = [
            {'code': '000001', 'name': 'A', 'klines': make_upn_klines(5)},
            {'code': '000002', 'name': 'B', 'klines': make_klines(50, trend='down')},
            {'code': '000003', 'name': 'C', 'klines': make_upn_klines(4)},
        ]
        matched = engine.scan(stock_data, ['upn'], 'AND', {'n': 3})
        codes = [m['code'] for m in matched]
        assert '000001' in codes
        assert '000003' in codes
        assert '000002' not in codes

    def test_unknown_condition(self):
        klines = make_klines(50)
        result = engine.evaluate('nonexistent_condition_xyz', klines)
        assert result is False


# ============== 趋势类条件测试 ==============

class TestTrendConditions:
    def test_upn(self):
        klines = make_upn_klines(5)
        assert engine.evaluate('upn', klines, {'n': 5}) is True
        assert engine.evaluate('upn', klines, {'n': 6}) is False

    def test_downn(self):
        closes = [10.0, 9.5, 9.0, 8.5, 8.0, 7.5]
        klines = []
        for i, c in enumerate(closes):
            klines.append({
                'date': f'2025-01-{i+1:02d}', 'open': c + 0.1,
                'high': c + 0.2, 'low': c - 0.1, 'close': c,
                'volume': 1000000, 'amount': c * 1000000,
            })
        assert engine.evaluate('downn', klines, {'n': 4}) is True

    def test_ma_bull(self):
        klines = make_klines(100, trend='up', volatility=0.005)
        result = engine.evaluate('ma_bull', klines)
        assert isinstance(result, bool)

    def test_new_high(self):
        klines = make_klines(30, trend='up', volatility=0.005)
        result = engine.evaluate('new_high', klines, {'n': 10})
        assert isinstance(result, bool)

    def test_golden_cross_ma(self):
        klines = make_klines(60, trend='up')
        result = engine.evaluate('golden_cross_ma', klines, {'short': 5, 'long': 20})
        assert isinstance(result, bool)


# ============== 技术指标类条件测试 ==============

class TestIndicatorConditions:
    def test_macd_golden_cross(self):
        klines = make_klines(60, trend='up')
        result = engine.evaluate('macd_golden_cross', klines)
        assert isinstance(result, bool)

    def test_macd_death_cross(self):
        klines = make_klines(60, trend='down')
        result = engine.evaluate('macd_death_cross', klines)
        assert isinstance(result, bool)

    def test_kdj_golden_cross(self):
        klines = make_klines(30)
        result = engine.evaluate('kdj_golden_cross', klines)
        assert isinstance(result, bool)

    def test_kdj_oversold(self):
        klines = make_klines(30, trend='down', volatility=0.03)
        result = engine.evaluate('kdj_oversold', klines)
        assert isinstance(result, bool)

    def test_rsi_oversold(self):
        klines = make_klines(30, trend='down', volatility=0.03)
        result = engine.evaluate('rsi_oversold', klines, {'period': 14, 'threshold': 30})
        assert isinstance(result, bool)

    def test_boll_squeeze(self):
        klines = make_klines(60, trend='flat', volatility=0.005)
        result = engine.evaluate('boll_squeeze', klines)
        assert isinstance(result, bool)

    def test_dmi_trend_strong(self):
        klines = make_klines(60, trend='up')
        result = engine.evaluate('dmi_trend_strong', klines)
        assert isinstance(result, bool)


# ============== 量价关系类条件测试 ==============

class TestVolumeConditions:
    def test_volume_breakout(self):
        klines = make_klines(30)
        klines[-1]['volume'] = klines[-1]['volume'] * 5
        klines[-1]['close'] = klines[-2]['close'] * 1.05
        result = engine.evaluate('volume_breakout', klines)
        assert result is True

    def test_volume_shrink(self):
        klines = make_klines(30)
        klines[-1]['volume'] = 100
        result = engine.evaluate('volume_shrink', klines)
        assert result is True

    def test_volume_price_up(self):
        klines = make_klines(10)
        for i in range(-3, 0):
            klines[i]['close'] = klines[i - 1]['close'] * 1.02
            klines[i]['volume'] = klines[i - 1]['volume'] * 1.3
        result = engine.evaluate('volume_price_up', klines, {'n': 3})
        assert result is True

    def test_volume_ratio_high(self):
        klines = make_klines(10)
        klines[-1]['volume'] = klines[-1]['volume'] * 5
        result = engine.evaluate('volume_ratio_high', klines, {'ratio': 2.0})
        assert result is True

    def test_turnover_rate_fallback(self):
        """无 turnoverRate 字段时的量比估算"""
        klines = make_klines(10)
        result = engine.evaluate('turnover_rate', klines, {'min': 0.0, 'max': 100.0})
        assert isinstance(result, bool)


# ============== K 线形态类条件测试 ==============

class TestPatternConditions:
    def test_pattern_hammer(self):
        klines = [{
            'date': '2025-01-01', 'open': 10.0, 'close': 10.1,
            'high': 10.12, 'low': 9.5, 'volume': 1000000, 'amount': 10000000,
        }]
        result = engine.evaluate('pattern_hammer', klines)
        assert result is True

    def test_pattern_shooting_star(self):
        klines = [{
            'date': '2025-01-01', 'open': 10.0, 'close': 9.9,
            'high': 10.6, 'low': 9.88, 'volume': 1000000, 'amount': 10000000,
        }]
        result = engine.evaluate('pattern_shooting_star', klines)
        assert result is True

    def test_pattern_engulfing_bull(self):
        klines = [
            {'date': '2025-01-01', 'open': 10.5, 'close': 10.0,
             'high': 10.6, 'low': 9.9, 'volume': 1000000, 'amount': 10000000},
            {'date': '2025-01-02', 'open': 9.9, 'close': 10.6,
             'high': 10.7, 'low': 9.8, 'volume': 1200000, 'amount': 12000000},
        ]
        result = engine.evaluate('pattern_engulfing_bull', klines)
        assert result is True

    def test_pattern_doji(self):
        klines = [{
            'date': '2025-01-01', 'open': 10.0, 'close': 10.01,
            'high': 10.3, 'low': 9.7, 'volume': 1000000, 'amount': 10000000,
        }]
        result = engine.evaluate('pattern_doji', klines)
        assert result is True

    def test_pattern_three_white(self):
        klines = [
            {'date': '2025-01-01', 'open': 10.0, 'close': 10.3,
             'high': 10.4, 'low': 9.9, 'volume': 1000000, 'amount': 10000000},
            {'date': '2025-01-02', 'open': 10.2, 'close': 10.6,
             'high': 10.7, 'low': 10.1, 'volume': 1000000, 'amount': 10000000},
            {'date': '2025-01-03', 'open': 10.5, 'close': 10.9,
             'high': 11.0, 'low': 10.4, 'volume': 1000000, 'amount': 10000000},
        ]
        result = engine.evaluate('pattern_three_white', klines)
        assert result is True

    def test_pattern_long_lower_shadow(self):
        klines = [{
            'date': '2025-01-01', 'open': 10.0, 'close': 10.1,
            'high': 10.15, 'low': 9.5, 'volume': 1000000, 'amount': 10000000,
        }]
        result = engine.evaluate('pattern_long_lower_shadow', klines, {'ratio': 2.0})
        assert result is True


# ============== A 股特色条件测试 ==============

class TestAStockConditions:
    def test_limit_up(self):
        klines = make_limit_up_klines(1)
        result = engine.evaluate('limit_up', klines)
        assert result is True

    def test_limit_down(self):
        klines = [
            {'date': '2025-01-01', 'open': 10.0, 'close': 10.0,
             'high': 10.0, 'low': 10.0, 'volume': 1000000, 'amount': 10000000},
            {'date': '2025-01-02', 'open': 9.1, 'close': 9.0,
             'high': 9.2, 'low': 9.0, 'volume': 1000000, 'amount': 9000000},
        ]
        result = engine.evaluate('limit_down', klines)
        assert result is True

    def test_continuous_limit_up(self):
        klines = make_limit_up_klines(3)
        assert engine.evaluate('continuous_limit_up', klines, {'n': 2}) is True
        assert engine.evaluate('continuous_limit_up', klines, {'n': 3}) is True
        assert engine.evaluate('continuous_limit_up', klines, {'n': 4}) is False

    def test_first_limit_up(self):
        klines = make_limit_up_klines(1)
        base = [{'date': '2024-12-31', 'open': 9.5, 'close': klines[0]['close'] * 0.97,
                 'high': 9.6, 'low': 9.4, 'volume': 1000000, 'amount': 9500000}]
        full = base + klines
        result = engine.evaluate('first_limit_up', full)
        assert result is True

    def test_big_yang(self):
        klines = [
            {'date': '2025-01-01', 'open': 10.0, 'close': 10.0,
             'high': 10.0, 'low': 10.0, 'volume': 1000000, 'amount': 10000000},
            {'date': '2025-01-02', 'open': 10.1, 'close': 10.8,
             'high': 10.9, 'low': 10.0, 'volume': 1500000, 'amount': 15000000},
        ]
        result = engine.evaluate('big_yang', klines, {'min_pct': 5})
        assert result is True

    def test_gap_up(self):
        klines = [
            {'date': '2025-01-01', 'open': 10.0, 'close': 10.0,
             'high': 10.2, 'low': 9.8, 'volume': 1000000, 'amount': 10000000},
            {'date': '2025-01-02', 'open': 10.5, 'close': 10.6,
             'high': 10.7, 'low': 10.4, 'volume': 1200000, 'amount': 12000000},
        ]
        result = engine.evaluate('gap_up', klines, {'min_gap_pct': 1})
        assert result is True


# ============== 组合策略测试 ==============

class TestCompositeStrategies:
    def test_composite_registered(self):
        """验证所有组合策略已注册"""
        composites = engine.list_conditions('composite')
        ids = [c['id'] for c in composites]
        expected = [
            'strong_breakout', 'bottom_reversal', 'trend_following',
            'vcp', 'momentum_burst', 'oversold_bounce',
            'macd_bull_start', 'limit_up_next_day', 'gap_breakout',
            'divergence_buy',
        ]
        for eid in expected:
            assert eid in ids, f"Composite strategy '{eid}' not registered"

    def test_composite_evaluate(self):
        """组合策略可以被评估（不报错）"""
        klines = make_klines(100)
        for cond in engine.list_conditions('composite'):
            result = engine.evaluate(cond['id'], klines)
            assert isinstance(result, bool), f"Composite '{cond['id']}' returned non-bool"
