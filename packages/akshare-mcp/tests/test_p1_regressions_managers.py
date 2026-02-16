import pytest

import akshare_mcp.tools.managers.execution_manager as em
import akshare_mcp.tools.macro as macro_tool
import akshare_mcp.tools.managers.macro_manager as mm
import akshare_mcp.tools.managers.options_manager as om


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


@pytest.mark.asyncio
async def test_p1_options_implied_volatility_market_price_alias():
    mcp = _DummyMCP()
    om.register_options_manager(mcp)

    r = await mcp.options_manager(
        action='implied_volatility',
        market_price=5.0,  # 兼容别名
        spot=100,
        strike=100,
        time_to_maturity=0.25,
        risk_free_rate=0.03,
        option_type='call',
    )

    assert r['success'] is True
    assert 'iv_value' in r['data']


@pytest.mark.asyncio
async def test_p1_options_calculate_price_validation_errors():
    mcp = _DummyMCP()
    om.register_options_manager(mcp)

    bad_type = await mcp.options_manager(action='calculate_price', option_type='bad')
    assert bad_type['success'] is False
    assert 'call 或 put' in (bad_type.get('error') or '')

    bad_vol = await mcp.options_manager(action='calculate_price', volatility=0)
    assert bad_vol['success'] is False
    assert 'volatility 必须大于 0' in (bad_vol.get('error') or '')

    bad_numeric = await mcp.options_manager(action='calculate_price', spot='abc')
    assert bad_numeric['success'] is False
    assert '必须为数字' in (bad_numeric.get('error') or '')


@pytest.mark.asyncio
async def test_p1_options_expiry_date_past_should_fail():
    mcp = _DummyMCP()
    om.register_options_manager(mcp)

    r = await mcp.options_manager(
        action='implied_volatility',
        option_price=5,
        spot=100,
        strike=100,
        expiry_date='2000-01-01',
        option_type='call',
    )
    assert r['success'] is False
    assert '剩余期限必须大于 0' in (r.get('error') or '')


@pytest.mark.asyncio
async def test_p1_macro_indicator_scope_single_and_multi(monkeypatch):
    mcp = _DummyMCP()
    mm.register_macro_manager(mcp)

    # 强制走 fallback，避免依赖外部数据源
    monkeypatch.setattr(macro_tool, 'get_macro_indicator', lambda indicator, limit=5: {'success': False, 'data': []})

    single = await mcp.macro_manager(action='get_indicators', indicator='cpi')
    assert single['success'] is True
    assert single['data']['indicator_type'] == 'cpi'
    assert single['data']['data'] is not None

    multi = await mcp.macro_manager(action='get_indicators', indicators=['cpi', 'pmi'])
    assert multi['success'] is True
    assert multi['data']['requested_indicators'] == ['cpi', 'pmi']
    assert set(multi['data']['data'].keys()) == {'cpi', 'pmi'}


@pytest.mark.asyncio
async def test_p1_macro_unknown_and_default_compat(monkeypatch):
    mcp = _DummyMCP()
    mm.register_macro_manager(mcp)

    monkeypatch.setattr(macro_tool, 'get_macro_indicator', lambda indicator, limit=5: {'success': False, 'data': []})

    unknown = await mcp.macro_manager(action='get_indicators', indicator='unknown_xxx')
    assert unknown['success'] is True
    assert unknown['data']['indicator_type'] == 'unknown_xxx'
    assert unknown['data']['data'] is None
    assert unknown['data']['source'] == 'none'

    default_case = await mcp.macro_manager(action='get_indicators')
    assert default_case['success'] is True
    assert default_case['data']['indicator_type'] == 'gdp'


@pytest.mark.asyncio
async def test_p1_execution_soft_gate_extended_rules_and_summary():
    mcp = _DummyMCP()
    em.register_execution_manager(mcp)

    # 避免跨测试污染：清理任务并恢复默认配置
    em._EXECUTION_TASKS.clear()
    reset_cfg = await mcp.execution_manager(
        action="set_config",
        kwargs='{"default_profile":"balanced","default_threshold_overrides":{},"code_profiles":{}}',
    )
    assert reset_cfg["success"] is True

    session_case = await mcp.execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":100000,"duration_minutes":20,"slices":4,"reference_price":10,"market_session":"auction"}',
    )
    assert session_case["success"] is True
    assert any(w.get("type") == "market_session_risk" for w in session_case["data"].get("warnings", []))

    participation_case = await mcp.execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":300000,"duration_minutes":10,"slices":2,"reference_price":10,"avg_minute_volume":50000,"max_participation_rate":0.2}',
    )
    assert participation_case["success"] is True
    assert any(w.get("type") == "participation_rate_high" for w in participation_case["data"].get("warnings", []))

    top_book_case = await mcp.execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":200000,"duration_minutes":10,"slices":2,"reference_price":10,"top_of_book_volume":40000,"max_top_book_ratio":0.3}',
    )
    assert top_book_case["success"] is True
    assert any(w.get("type") == "top_book_impact_high" for w in top_book_case["data"].get("warnings", []))

    summary_all = await mcp.execution_manager(action="summary", kwargs="{}")
    assert summary_all["success"] is True
    data = summary_all["data"]
    assert "warnings_by_severity" in data and isinstance(data["warnings_by_severity"], dict)
    assert (data["warnings_by_severity"].get("medium", 0) + data["warnings_by_severity"].get("high", 0)) >= 1
    assert "warnings_by_profile" in data and isinstance(data["warnings_by_profile"], dict)
    assert "soft_gate_profile_distribution" in data and isinstance(data["soft_gate_profile_distribution"], dict)
    assert set(["balanced", "conservative", "aggressive"]).issubset(
        set(data["soft_gate_profile_distribution"].keys())
    )

    # 收尾清理，避免影响其他文件
    em._EXECUTION_TASKS.clear()
    _ = await mcp.execution_manager(
        action="set_config",
        kwargs='{"default_profile":"balanced","default_threshold_overrides":{},"code_profiles":{}}',
    )


