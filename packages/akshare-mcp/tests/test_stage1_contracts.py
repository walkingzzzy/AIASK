import pytest
from unittest.mock import AsyncMock


def test_backtest_filter_last_report_contains_stage1_metrics():
    from akshare_mcp.services.strategy_factory.backtest_filter import BacktestFilter

    bf = BacktestFilter()
    candidates = [{
        'strategy_type': 'momentum',
        'backtest_result': {
            'passed': True,
            'queue_wait_ms': 1.2,
            'backtest_run_ms': 12.3,
            'code_run_ms_total': 20.0,
            'code_run_count': 2,
            'kline_cache_hit_count': 1,
            'evaluated_code_count': 2,
            'reasons': [],
            'thresholds': {'sharpe_min': 0.2},
            'layers': {'target': ['600519'], 'representative': ['600519']},
        },
        'backtest_metrics': {'sharpe_ratio': 0.8},
    }]

    report = bf._build_last_report(candidates, candidates, [])

    assert report['summary']['avg_candidate_ms'] == 12.3
    assert report['summary']['avg_code_ms'] == 10.0
    assert report['summary']['cache_hit_ratio'] == 0.5


@pytest.mark.asyncio
async def test_run_gated_filter_returns_structured_gate_report(monkeypatch):
    from akshare_mcp.services.strategy_factory.quality_gates import GateResult, run_gated_filter

    class _BacktestFilter:
        async def filter(self, candidates, _db):
            return [{**candidates[0], 'backtest_result': {'passed': True}}]

        def get_last_report(self):
            return {'summary': {'passed_count': 1}}

    async def _fake_gate_1_fast_screen(candidate, _db, *, kline_cache=None):
        return GateResult(
            passed=True,
            gate='gate_1',
            reasons=[],
            metrics={'tested_codes': ['600519'], 'sharpe_values': [1.2], 'avg_sharpe': 1.2},
        )

    monkeypatch.setattr(
        'akshare_mcp.services.strategy_factory.quality_gates.gate_1_fast_screen',
        _fake_gate_1_fast_screen,
    )

    db = AsyncMock()
    result = await run_gated_filter(
        [{'strategy_type': 'momentum', 'params': {'lookback': 20, 'threshold': 0.02}}],
        db,
        _BacktestFilter(),
    )

    assert result['summary']['gate_3_pending'] == 1
    assert result['quality_gate']['gate_2']['report']['summary']['passed_count'] == 1
    assert result['gate_report']['gate_3']['status'] == 'pending_submission_gate'
    assert result['gate_report']['final_decision']['stage'] == 'gate_2'


def test_vector_search_fallback_meta_is_normalized():
    from akshare_mcp.services.vector_search import VectorSearchEngine

    engine = VectorSearchEngine(backend='index', allow_fallback=True)
    engine.build_index = lambda **_kwargs: None
    engine.search_index = lambda **_kwargs: []

    klines = [
        {'close': 10.0, 'volume': 100.0},
        {'close': 10.5, 'volume': 120.0},
        {'close': 11.0, 'volume': 130.0},
    ]
    results = engine.find_similar_patterns(
        query_klines=klines,
        candidate_klines_dict={'600519': klines, '000001': klines},
        top_k=1,
    )

    assert len(results) == 1
    assert results[0]['backend_requested'] == 'index'
    assert results[0]['backend_used'] == 'python_fallback'
    assert results[0]['fallback_used'] is True
    assert results[0]['fallback_reason'] == 'index_empty_result'
    assert results[0]['latency_ms'] >= 0
    assert engine.last_meta['backend_used'] == 'python_fallback'

