import akshare_mcp.services.strategy_factory.backtest_filter as legacy_backtest_filter

from strategy_factory.application.backtest_filter import BacktestFilter


def test_backtest_filter_reads_representative_stocks_from_legacy_shim(monkeypatch):
    monkeypatch.setattr(legacy_backtest_filter, "REPRESENTATIVE_STOCKS", ["600519", "000858"])

    evaluated_codes, target_codes, representative_codes, code_source = BacktestFilter._resolve_backtest_codes(
        {"strategy_type": "momentum", "params": {}}
    )

    assert evaluated_codes == ["600519", "000858"]
    assert target_codes == []
    assert representative_codes == ["600519", "000858"]
    assert code_source == "representative_only"
