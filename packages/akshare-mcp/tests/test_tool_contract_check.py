import importlib
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def _get_manager_callable(manager_name: str, register_module: str, register_func: str):
    module = importlib.import_module(register_module)
    register = getattr(module, register_func)
    mcp = _DummyMCP()
    register(mcp)
    return getattr(mcp, manager_name)


@pytest.mark.asyncio
async def test_execution_manager_contract(monkeypatch):
    import akshare_mcp.tools.managers.execution_manager as execution_mod

    monkeypatch.setattr(execution_mod, "_enrich_kwargs_with_realtime", lambda code, kwargs: kwargs)
    monkeypatch.setattr(execution_mod, "get_artifact_async", AsyncMock(return_value=None))
    monkeypatch.setattr(execution_mod, "list_artifacts_async", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        execution_mod,
        "register_artifact_async",
        AsyncMock(side_effect=lambda payload: dict(payload)),
    )
    monkeypatch.setattr(
        execution_mod,
        "evaluate_order_compliance",
        lambda code, direction, quantity_raw, price_raw=None: {
            "violations": [],
            "warnings": [],
            "checks": {"position_limit": True, "trading_hours": True},
            "order_amount": (float(quantity_raw or 0) * float(price_raw or 0)) if price_raw is not None else None,
        },
    )
    monkeypatch.setattr(execution_mod, "audit_event", lambda *args, **kwargs: None)

    execution_manager = _get_manager_callable(
        manager_name="execution_manager",
        register_module="akshare_mcp.tools.managers.execution_manager",
        register_func="register_execution_manager",
    )

    # P3: 运行时配置默认值
    cfg0 = await execution_manager(action="get_config", kwargs="{}")
    assert cfg0["success"] is True
    assert cfg0["data"]["soft_gate_config"]["default_profile"] == "balanced"

    cfg_structured = await execution_manager(action="get_config", params={})
    assert cfg_structured["success"] is True
    assert cfg_structured["data"]["soft_gate_config"]["default_profile"] == "balanced"

    created = await execution_manager(
        action="twap",
        kwargs='{"code":"600519","total_quantity":1000,"duration_minutes":60,"slices":6,"reference_price":1800}',
    )
    assert created["success"] is True
    data = created["data"]
    assert data["algorithm"] == "TWAP"
    assert data["total_quantity"] == 1000
    assert data["duration_minutes"] == 60
    assert "task_id" in data
    assert "cost_model" in data
    assert "assumptions" in data["cost_model"]
    assert "estimated" in data["cost_model"]
    assert "warnings" in data
    assert "soft_gate" in data
    assert data["soft_gate"]["enabled"] is True
    assert data["soft_gate"]["blocking"] is False
    assert data["soft_gate"]["profile"] == "balanced"
    assert data["soft_gate"]["thresholds"]["max_order_shares"] == 1_000_000
    assert data["soft_gate"]["warning_count"] == len(data["warnings"])

    # P3/P4: set_config（default_profile + default_threshold_overrides + code_profiles）
    set_cfg = await execution_manager(
        action="set_config",
        kwargs='{"default_profile":"conservative","default_threshold_overrides":{"max_order_shares":900000},"code_profiles":{"000001":"aggressive"}}',
    )
    assert set_cfg["success"] is True
    cfg1 = set_cfg["data"]["soft_gate_config"]
    assert cfg1["default_profile"] == "conservative"
    assert cfg1["default_threshold_overrides"]["max_order_shares"] == 900000
    assert cfg1["code_profiles"]["000001"] == "aggressive"

    # P4: merge_code_profiles=true 时增量更新而非整体覆盖
    merge_code_profiles_cfg = await execution_manager(
        action="set_config",
        kwargs='{"code_profiles":{"600519":"balanced"},"merge_code_profiles":true}',
    )
    assert merge_code_profiles_cfg["success"] is True
    cfg_merge_cp = merge_code_profiles_cfg["data"]["soft_gate_config"]
    assert cfg_merge_cp["code_profiles"]["000001"] == "aggressive"
    assert cfg_merge_cp["code_profiles"]["600519"] == "balanced"

    # P4: code_profiles 传 null 删除单个映射（增量模式）
    delete_by_null_cfg = await execution_manager(
        action="set_config",
        kwargs='{"code_profiles":{"600519":null},"merge_code_profiles":true}',
    )
    assert delete_by_null_cfg["success"] is True
    cfg_delete_null = delete_by_null_cfg["data"]["soft_gate_config"]
    assert "600519" not in cfg_delete_null["code_profiles"]

    # P4: remove_code_profiles 列表删除
    remove_code_profiles_cfg = await execution_manager(
        action="set_config",
        kwargs='{"remove_code_profiles":["000001"]}',
    )
    assert remove_code_profiles_cfg["success"] is True
    cfg_remove_cp = remove_code_profiles_cfg["data"]["soft_gate_config"]
    assert "000001" not in cfg_remove_cp["code_profiles"]

    # P4: merge_default_threshold_overrides=true 时局部合并
    merge_threshold_cfg = await execution_manager(
        action="set_config",
        kwargs='{"default_threshold_overrides":{"max_slice_shares":12345},"merge_default_threshold_overrides":true}',
    )
    assert merge_threshold_cfg["success"] is True
    cfg_merge_th = merge_threshold_cfg["data"]["soft_gate_config"]
    assert cfg_merge_th["default_threshold_overrides"]["max_order_shares"] == 900000
    assert cfg_merge_th["default_threshold_overrides"]["max_slice_shares"] == 12345

    # P4: remove_default_threshold_keys 删除指定阈值键
    remove_threshold_keys_cfg = await execution_manager(
        action="set_config",
        kwargs='{"remove_default_threshold_keys":["max_order_shares"]}',
    )
    assert remove_threshold_keys_cfg["success"] is True
    cfg_remove_th = remove_threshold_keys_cfg["data"]["soft_gate_config"]
    assert "max_order_shares" not in cfg_remove_th["default_threshold_overrides"]
    assert cfg_remove_th["default_threshold_overrides"]["max_slice_shares"] == 12345

    # 删除 code_profiles 后，回退到 default_profile
    fallback_profile_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":600000,"duration_minutes":8,"slices":10,"reference_price":10}',
    )
    assert fallback_profile_case["success"] is True
    fp = fallback_profile_case["data"]
    assert fp["soft_gate"]["profile"] == "conservative"

    # 为后续既有断言恢复到 P3 配置基线（避免新增 P4 删除语义影响）
    restore_cfg_for_legacy_assertions = await execution_manager(
        action="set_config",
        kwargs='{"default_profile":"conservative","default_threshold_overrides":{"max_order_shares":900000},"code_profiles":{"000001":"aggressive"}}',
    )
    assert restore_cfg_for_legacy_assertions["success"] is True
    restored = restore_cfg_for_legacy_assertions["data"]["soft_gate_config"]
    assert restored["default_threshold_overrides"]["max_order_shares"] == 900000
    assert restored["code_profiles"]["000001"] == "aggressive"

    # 缺省请求参数：应用 default_profile + default_threshold_overrides
    runtime_default_case = await execution_manager(
        action="twap",
        kwargs='{"code":"600519","total_quantity":600000,"duration_minutes":8,"slices":10,"reference_price":10}',
    )
    assert runtime_default_case["success"] is True
    rd = runtime_default_case["data"]
    assert rd["soft_gate"]["profile"] == "conservative"
    assert rd["soft_gate"]["thresholds"]["max_order_shares"] == 900000

    # code_profiles 覆盖 default_profile
    code_profile_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":600000,"duration_minutes":8,"slices":10,"reference_price":10}',
    )
    assert code_profile_case["success"] is True
    cp = code_profile_case["data"]
    assert cp["soft_gate"]["profile"] == "aggressive"

    # request 显式 profile 优先于 code_profiles/default_profile
    request_profile_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":600000,"duration_minutes":8,"slices":10,"reference_price":10,"soft_gate_profile":"balanced"}',
    )
    assert request_profile_case["success"] is True
    rp = request_profile_case["data"]
    assert rp["soft_gate"]["profile"] == "balanced"

    # request 显式阈值优先于 default_threshold_overrides
    request_threshold_case = await execution_manager(
        action="twap",
        kwargs='{"code":"600519","total_quantity":300000,"duration_minutes":8,"slices":10,"reference_price":10,"max_order_shares":100000}',
    )
    assert request_threshold_case["success"] is True
    rt = request_threshold_case["data"]
    assert rt["soft_gate"]["thresholds"]["max_order_shares"] == 100000

    bad_set_cfg = await execution_manager(action="set_config", kwargs='{"default_profile":"invalid"}')
    assert bad_set_cfg["success"] is False

    # 复位运行时配置，避免影响后续 P2 断言
    reset_cfg = await execution_manager(
        action="set_config",
        kwargs='{"default_profile":"balanced","default_threshold_overrides":{},"code_profiles":{}}',
    )
    assert reset_cfg["success"] is True

    created_with_artifact = await execution_manager(
        action="vwap",
        kwargs='{"code":"000001","total_quantity":500,"duration_minutes":30,"artifact_id":"art_test_001"}',
    )
    assert created_with_artifact["success"] is True
    data2 = created_with_artifact["data"]
    assert data2["artifact_id"] == "art_test_001"

    # P2: profile 阈值策略（conservative 更严格，aggressive 更宽松）
    conservative_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":700000,"duration_minutes":8,"slices":10,"reference_price":10,"soft_gate_profile":"conservative"}',
    )
    assert conservative_case["success"] is True
    cdata = conservative_case["data"]
    assert cdata["soft_gate"]["profile"] == "conservative"
    assert cdata["soft_gate"]["thresholds"]["max_order_shares"] == 500_000
    assert cdata["soft_gate"]["has_high_severity"] is True

    aggressive_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":700000,"duration_minutes":8,"slices":10,"reference_price":10,"soft_gate_profile":"aggressive"}',
    )
    assert aggressive_case["success"] is True
    adata = aggressive_case["data"]
    assert adata["soft_gate"]["profile"] == "aggressive"
    assert adata["soft_gate"]["thresholds"]["max_order_shares"] == 2_000_000
    assert adata["soft_gate"]["has_high_severity"] is False

    # P2: 显式阈值覆盖 profile 默认值（应优先于 profile）
    override_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":300000,"duration_minutes":8,"slices":10,"reference_price":10,"soft_gate_profile":"aggressive","max_order_shares":100000}',
    )
    assert override_case["success"] is True
    odata = override_case["data"]
    assert odata["soft_gate"]["profile"] == "aggressive"
    assert odata["soft_gate"]["thresholds"]["max_order_shares"] == 100000
    assert odata["soft_gate"]["has_high_severity"] is True

    # 软闸门高风险场景：大单 + 短时长，仍然不阻断
    created_high_risk = await execution_manager(
        action="vwap",
        kwargs='{"code":"000001","total_quantity":1500000,"duration_minutes":3}',
    )
    assert created_high_risk["success"] is True
    data3 = created_high_risk["data"]
    assert "warnings" in data3 and len(data3["warnings"]) > 0
    assert data3["soft_gate"]["enabled"] is True
    assert data3["soft_gate"]["blocking"] is False
    assert data3["soft_gate"]["has_high_severity"] is True


    # P4 扩展规则：非连续竞价时段提示
    session_risk_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":100000,"duration_minutes":20,"slices":4,"reference_price":10,"market_session":"auction"}',
    )
    assert session_risk_case["success"] is True
    sdata = session_risk_case["data"]
    assert any(w.get("type") == "market_session_risk" for w in sdata.get("warnings", []))

    # P4 扩展规则：参与率过高提示
    participation_risk_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":300000,"duration_minutes":10,"slices":2,"reference_price":10,"avg_minute_volume":50000,"max_participation_rate":0.2}',
    )
    assert participation_risk_case["success"] is True
    pdata = participation_risk_case["data"]
    assert any(w.get("type") == "participation_rate_high" for w in pdata.get("warnings", []))

    # P4 扩展规则：盘口深度冲击提示
    top_book_risk_case = await execution_manager(
        action="twap",
        kwargs='{"code":"000001","total_quantity":200000,"duration_minutes":10,"slices":2,"reference_price":10,"top_of_book_volume":40000,"max_top_book_ratio":0.3}',
    )
    assert top_book_risk_case["success"] is True
    tdata = top_book_risk_case["data"]
    assert any(w.get("type") == "top_book_impact_high" for w in tdata.get("warnings", []))

    # 新规则告警也应计入全局 summary 的分级分布
    summary_after_new_rules = await execution_manager(action="summary", kwargs="{}")
    assert summary_after_new_rules["success"] is True
    sev_after = summary_after_new_rules["data"]["warnings_by_severity"]
    assert isinstance(sev_after, dict)
    assert (sev_after.get("medium", 0) + sev_after.get("high", 0)) >= 1

    warn_profile_after = summary_after_new_rules["data"].get("warnings_by_profile", {})
    assert isinstance(warn_profile_after, dict)
    assert len(warn_profile_after) >= 1

    profile_dist_after = summary_after_new_rules["data"].get("soft_gate_profile_distribution", {})
    assert isinstance(profile_dist_after, dict)
    assert "balanced" in profile_dist_after and "conservative" in profile_dist_after and "aggressive" in profile_dist_after

    # 恢复一次全局 summary 变量，保持后续断言语义一致
    summary_all = summary_after_new_rules
    assert summary_all["success"] is True
    assert "warning_count" in summary_all["data"]
    assert "high_severity_task_count" in summary_all["data"]
    assert "soft_gate_profile_distribution" in summary_all["data"]
    assert "warnings_by_profile" in summary_all["data"]
    assert "warnings_by_severity" in summary_all["data"]
    sev_dist = summary_all["data"]["warnings_by_severity"]
    assert isinstance(sev_dist, dict)
    assert set(["low", "medium", "high"]).issubset(set(sev_dist.keys()))

    listed = await execution_manager(action="list", kwargs="{}")
    assert listed["success"] is True
    assert "tasks" in listed["data"]
    assert listed["data"]["count"] >= 1
    assert any(t.get("artifact_id") == "art_test_001" for t in listed["data"]["tasks"])
    assert all("warning_count" in t for t in listed["data"]["tasks"])
    assert all("has_high_severity" in t for t in listed["data"]["tasks"])

    summary = await execution_manager(action="summary", kwargs=f'{{"task_id":"{data["task_id"]}"}}')
    assert summary["success"] is True
    assert "task" in summary["data"]
    assert "lifecycle_count" in summary["data"]
    assert "warnings" in summary["data"]
    assert "soft_gate" in summary["data"]

    summary_all = await execution_manager(action="summary", kwargs="{}")
    assert summary_all["success"] is True
    assert "warning_count" in summary_all["data"]
    assert "high_severity_task_count" in summary_all["data"]
    assert "soft_gate_profile_distribution" in summary_all["data"]
    assert "warnings_by_profile" in summary_all["data"]
    assert "warnings_by_severity" in summary_all["data"]
    sev_dist = summary_all["data"]["warnings_by_severity"]
    assert isinstance(sev_dist, dict)
    assert set(["low", "medium", "high"]).issubset(set(sev_dist.keys()))


@pytest.mark.asyncio
async def test_compliance_manager_contract():
    compliance_manager = _get_manager_callable(
        manager_name="compliance_manager",
        register_module="akshare_mcp.tools.managers.compliance_manager",
        register_func="register_compliance_manager",
    )

    result = await compliance_manager(
        action="check_order",
        kwargs='{"code":"600519","direction":"buy","quantity":2000000,"price":100000}',
    )
    assert result["success"] is True
    data = result["data"]
    assert data["blocked"] is True
    assert data["passed"] is False
    assert isinstance(data["violations"], list)
    assert len(data["violations"]) > 0

    structured = await compliance_manager(
        action="check_order",
        params={"code": "600519", "direction": "buy", "quantity": 100, "price": 10},
    )
    assert structured["success"] is True
    assert str(structured["data"]["code"]).endswith("600519")
    assert structured["data"]["quantity"] == 100
    assert structured["data"]["blocked"] is False


@pytest.mark.asyncio
async def test_options_manager_contract():
    options_manager = _get_manager_callable(
        manager_name="options_manager",
        register_module="akshare_mcp.tools.managers.options_manager",
        register_func="register_options_manager",
    )

    result = await options_manager(action="list", kwargs='{"underlying":"510050","limit":20}')
    assert result["success"] is True
    data = result["data"]
    assert "options" in data
    assert isinstance(data["options"], list)
    assert "selectedExpiry" in data

    structured = await options_manager(action="list", params={"underlying": "510050", "limit": 10})
    assert structured["success"] is True
    assert "selectedExpiry" in structured["data"]


@pytest.mark.asyncio
async def test_options_manager_volatility_smirk_contract(monkeypatch):
    options_tool_module = importlib.import_module("akshare_mcp.tools.options")
    pricing_module = importlib.import_module("akshare_mcp.services.options_pricing")
    options_manager_module = importlib.import_module("akshare_mcp.tools.managers.options_manager")

    def _fake_chain(underlying: str, expiry_month: str = "", limit: int = 200):
        spot = 100.0
        expiry = expiry_month or "209912"
        time_to_maturity = options_manager_module._time_to_maturity_from_expiry_month(expiry)
        vols = {90.0: 0.18, 100.0: 0.20, 110.0: 0.24}
        options = []
        for strike, vol in vols.items():
            call_price = pricing_module.options_pricing.black_scholes(
                spot=spot,
                strike=strike,
                time_to_maturity=time_to_maturity,
                risk_free_rate=0.03,
                volatility=vol,
                option_type="call",
            )
            put_price = pricing_module.options_pricing.black_scholes(
                spot=spot,
                strike=strike,
                time_to_maturity=time_to_maturity,
                risk_free_rate=0.03,
                volatility=vol,
                option_type="put",
            )
            options.append({"type": "call", "expiryMonth": expiry, "strike": strike, "last": call_price})
            options.append({"type": "put", "expiryMonth": expiry, "strike": strike, "last": put_price})

        return {
            "success": True,
            "data": {
                "underlying": {"code": underlying, "price": spot},
                "selectedExpiry": [expiry],
                "options": options,
                "degraded": False,
            },
        }

    monkeypatch.setattr(options_tool_module, "get_option_chain", _fake_chain)

    options_manager = _get_manager_callable(
        manager_name="options_manager",
        register_module="akshare_mcp.tools.managers.options_manager",
        register_func="register_options_manager",
    )

    result = await options_manager(action="volatility_smirk", params={"underlying": "510050", "expiry_month": "209912"})
    assert result["success"] is True
    data = result["data"]
    assert data["point_count"] == 3
    assert len(data["curve"]) == 3
    assert data["atm_iv"] == pytest.approx(0.20, rel=0.1)


@pytest.mark.asyncio
async def test_quant_manager_factor_ic_history_accepts_structured_params(monkeypatch):
    quant_module = importlib.import_module("akshare_mcp.tools.managers.quant_manager")

    class _FakeQuantDb:
        async def get_factor_ic_history(self, factor_name, period, limit):
            assert factor_name == "momentum"
            assert period == "20"
            assert limit == 5
            return [{"ic_date": "2025-01-01", "ic_value": 0.12, "rank_ic": 0.1, "stock_count": 50}]

    monkeypatch.setattr(quant_module, "get_db", lambda: _FakeQuantDb())
    quant_manager = _get_manager_callable(
        manager_name="quant_manager",
        register_module="akshare_mcp.tools.managers.quant_manager",
        register_func="register_quant_manager",
    )

    result = await quant_manager(action="factor_ic_history", params={"factor_name": "momentum", "period": "20", "limit": 5})
    assert result["success"] is True
    assert result["data"]["factor_name"] == "momentum"
    assert result["data"]["count"] == 1
    assert result["data"]["history"][0]["ic_value"] == 0.12


@pytest.mark.asyncio
async def test_risk_manager_explainability_contract():
    risk_manager = _get_manager_callable(
        manager_name="risk_manager",
        register_module="akshare_mcp.tools.managers.risk_manager",
        register_func="register_risk_manager",
    )

    result = await risk_manager(
        action="risk_exposure",
        kwargs='{"codes":["600519","000858","000001"],"weights":[0.4,0.3,0.3],"portfolio_value":1000000}',
    )
    assert result["success"] is True
    data = result["data"]
    assert data["input_mode"] == "codes_weights"
    assert "explainability" in data
    explain = data["explainability"]
    assert "hhi" in explain
    assert "effective_positions" in explain
    assert "top3_weight_pct" in explain

    structured = await risk_manager(
        action="risk_exposure",
        params={"codes": ["600519", "000858"], "weights": [0.5, 0.5], "portfolio_value": 500000},
    )
    assert structured["success"] is True
    assert structured["data"]["input_mode"] == "codes_weights"


@pytest.mark.asyncio
@pytest.mark.filterwarnings(
    "ignore:Unverified HTTPS request is being made to host 'push2his\\.eastmoney\\.com'.*:urllib3.exceptions.InsecureRequestWarning"
)
async def test_insight_generate_report_contract(tmp_path):
    insight_manager = _get_manager_callable(
        manager_name="insight_manager",
        register_module="akshare_mcp.tools.managers.insight_manager",
        register_func="register_insight_manager",
    )

    out_dir = os.fspath(tmp_path / "reports")
    result = await insight_manager(
        action="generate_report",
        kwargs=(
            '{"report_type":"weekly","output_dir":"'
            + out_dir.replace("\\\\", "/")
            + '","data_window":"2026-01-01~2026-02-01","next_actions":["rebalance"]}'
        ),
    )
    assert result["success"] is True
    data = result["data"]
    artifacts = data["artifacts"]
    assert os.path.exists(artifacts["markdown"])
    assert "json" not in artifacts
    assert "required_fields" in data

    json_result = await insight_manager(
        action="generate_report",
        kwargs=(
            '{"report_type":"weekly","output_dir":"'
            + out_dir.replace("\\\\", "/")
            + '","include_json":true,"data_window":"2026-01-01~2026-02-01","next_actions":["rebalance"]}'
        ),
    )
    assert json_result["success"] is True
    json_artifacts = json_result["data"]["artifacts"]
    assert os.path.exists(json_artifacts["markdown"])
    assert os.path.exists(json_artifacts["json"])
    assert "required_fields" in data


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePerfConn:
    def __init__(self, row_by_id=None, row_by_artifact=None):
        self.row_by_id = row_by_id
        self.row_by_artifact = row_by_artifact

    async def fetchrow(self, query, *args):
        q = " ".join(str(query).split()).lower()
        if "where id = $1" in q:
            return self.row_by_id
        if "params like $1 or params like $2" in q:
            return self.row_by_artifact
        return None


class _FakePerfDB:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


@pytest.mark.asyncio
async def test_performance_manager_backtest_metrics_by_backtest_id(monkeypatch):
    module = importlib.import_module("akshare_mcp.tools.managers.performance_manager")

    fake_row = {
        "id": "bt_001",
        "code": "600519",
        "strategy": "ma_cross",
        "params": '{"artifact_id": "art_from_params"}',
        "start_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "end_date": datetime(2025, 2, 1, tzinfo=timezone.utc),
        "created_at": datetime(2025, 2, 2, tzinfo=timezone.utc),
        "initial_capital": 100000.0,
        "final_capital": 110000.0,
        "total_return": 0.10,
        "annual_return": 0.18,
        "max_drawdown": 0.05,
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.4,
        "win_rate": 0.6,
        "trades_count": 12,
    }

    monkeypatch.setattr(module, "get_db", lambda: _FakePerfDB(_FakePerfConn(row_by_id=fake_row)))

    perf = _get_manager_callable(
        manager_name="performance_manager",
        register_module="akshare_mcp.tools.managers.performance_manager",
        register_func="register_performance_manager",
    )

    result = await perf(action="backtest_metrics", kwargs='{"backtest_id":"bt_001"}')
    assert result["success"] is True
    data = result["data"]
    assert data["backtest_id"] == "bt_001"
    assert data["artifact_id"] == "art_from_params"
    assert data["strategy"] == "ma_cross"
    assert data["trades_count"] == 12


@pytest.mark.asyncio
async def test_performance_manager_backtest_metrics_by_artifact_id(monkeypatch):
    module = importlib.import_module("akshare_mcp.tools.managers.performance_manager")

    fake_row = {
        "id": "bt_002",
        "code": "000001",
        "strategy": "momentum",
        "params": "{'artifact_id': 'art_abc_002'}",
        "start_date": datetime(2025, 3, 1, tzinfo=timezone.utc),
        "end_date": datetime(2025, 4, 1, tzinfo=timezone.utc),
        "created_at": datetime(2025, 4, 2, tzinfo=timezone.utc),
        "initial_capital": 200000.0,
        "final_capital": 195000.0,
        "total_return": -0.025,
        "annual_return": -0.08,
        "max_drawdown": 0.12,
        "sharpe_ratio": -0.3,
        "sortino_ratio": -0.4,
        "win_rate": 0.45,
        "trades_count": 8,
    }

    monkeypatch.setattr(module, "get_db", lambda: _FakePerfDB(_FakePerfConn(row_by_artifact=fake_row)))

    perf = _get_manager_callable(
        manager_name="performance_manager",
        register_module="akshare_mcp.tools.managers.performance_manager",
        register_func="register_performance_manager",
    )

    result = await perf(action="backtest_metrics", kwargs='{"artifact_id":"art_abc_002"}')
    assert result["success"] is True
    data = result["data"]
    assert data["backtest_id"] == "bt_002"
    assert data["artifact_id"] == "art_abc_002"
    assert data["strategy"] == "momentum"
    assert data["trades_count"] == 8



class _FakeBacktestConn:
    def __init__(self):
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((str(query), args))
        return "OK"


class _FakeBacktestDB:
    def __init__(self, klines):
        self._klines = klines
        self.conn = _FakeBacktestConn()

    async def get_klines(self, code, limit=250):
        return self._klines[: int(limit)]

    async def save_klines(self, code, klines):
        return None

    def acquire(self):
        return _FakeAcquire(self.conn)


@pytest.mark.asyncio
async def test_smoke_backtest_to_execution_to_performance_by_artifact(monkeypatch):
    backtest_module = importlib.import_module("akshare_mcp.tools.managers.backtest_manager")
    service_module = importlib.import_module("akshare_mcp.services.backtest")
    perf_module = importlib.import_module("akshare_mcp.tools.managers.performance_manager")

    # 60条最小K线，满足 backtest_manager 对数据量的要求
    klines = [
        {"date": f"2025-01-{(i % 28) + 1:02d}", "open": 10 + i * 0.1, "high": 10.5 + i * 0.1, "low": 9.5 + i * 0.1, "close": 10 + i * 0.1, "volume": 100000 + i * 100}
        for i in range(60)
    ]

    monkeypatch.setattr(backtest_module, "get_db", lambda: _FakeBacktestDB(klines))
    monkeypatch.setattr(
        service_module.backtest_engine,
        "run_backtest",
        lambda **kwargs: {
            "success": True,
            "final_capital": 108000.0,
            "total_return": 0.08,
            "annual_return": 0.12,
            "max_drawdown": 0.06,
            "sharpe_ratio": 1.1,
            "trades_count": 9,
            "win_rate": 0.55,
        },
    )

    backtest_manager = _get_manager_callable(
        manager_name="backtest_manager",
        register_module="akshare_mcp.tools.managers.backtest_manager",
        register_func="register_backtest_manager",
    )
    execution_manager = _get_manager_callable(
        manager_name="execution_manager",
        register_module="akshare_mcp.tools.managers.execution_manager",
        register_func="register_execution_manager",
    )
    performance_manager = _get_manager_callable(
        manager_name="performance_manager",
        register_module="akshare_mcp.tools.managers.performance_manager",
        register_func="register_performance_manager",
    )

    run_result = await backtest_manager(
        action="run",
        kwargs='{"code":"600519","strategy":"ma_cross","artifact_id":"art_smoke_001","limit":120}',
    )
    assert run_result["success"] is True
    artifact_id = run_result["data"]["artifact_id"]
    assert artifact_id == "art_smoke_001"

    run_structured = await backtest_manager(
        action="run",
        params={"code": "600519", "strategy": "ma_cross", "artifact_id": "art_smoke_002", "limit": 120},
    )
    assert run_structured["success"] is True
    assert run_structured["data"]["artifact_id"] == "art_smoke_002"

    exec_result = await execution_manager(
        action="twap",
        kwargs='{"code":"600519","total_quantity":1000,"duration_minutes":30,"artifact_id":"art_smoke_001"}',
    )
    assert exec_result["success"] is True
    assert exec_result["data"]["artifact_id"] == artifact_id

    fake_perf_row = {
        "id": "bt_smoke_001",
        "code": "600519",
        "strategy": "ma_cross",
        "params": '{"artifact_id": "art_smoke_001"}',
        "start_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "end_date": datetime(2025, 2, 28, tzinfo=timezone.utc),
        "created_at": datetime(2025, 3, 1, tzinfo=timezone.utc),
        "initial_capital": 100000.0,
        "final_capital": 108000.0,
        "total_return": 0.08,
        "annual_return": 0.12,
        "max_drawdown": 0.06,
        "sharpe_ratio": 1.1,
        "sortino_ratio": 1.3,
        "win_rate": 0.55,
        "trades_count": 9,
    }
    monkeypatch.setattr(perf_module, "get_db", lambda: _FakePerfDB(_FakePerfConn(row_by_artifact=fake_perf_row)))

    perf_result = await performance_manager(
        action="backtest_metrics",
        kwargs='{"artifact_id":"art_smoke_001"}',
    )
    assert perf_result["success"] is True
    assert perf_result["data"]["artifact_id"] == artifact_id
    assert perf_result["data"]["backtest_id"] == "bt_smoke_001"
    assert perf_result["data"]["strategy"] == "ma_cross"
    assert perf_result["data"]["trades_count"] == 9
