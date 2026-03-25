import pytest


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


@pytest.mark.asyncio
async def test_should_i_buy_adds_pit_guard_prediction_quality_and_interval(monkeypatch):
    from akshare_mcp.tools import decision as decision_mod

    class _DecisionDB:
        async def get_stock_info(self, code):
            return {"name": "测试股份", "industry": "消费"}

        async def get_klines(self, code, limit=None):
            rows = []
            for i in range(120):
                day = i + 1
                month = 1 + (day - 1) // 28
                day_in_month = ((day - 1) % 28) + 1
                rows.append(
                    {
                        "date": f"2026-{month:02d}-{day_in_month:02d}",
                        "open": float(10 + i * 0.2),
                        "high": float(10.3 + i * 0.2),
                        "low": float(9.7 + i * 0.2),
                        "close": float(10 + i * 0.2),
                        "volume": 1000 + i * 10,
                    }
                )
            rows.reverse()
            return rows

    async def _analysis_context(_code):
        return {
            "success": True,
            "data": {
                "valuation": {"pe": 12.0, "pb": 1.6},
                "fundamentals": {"roe": 18.0, "debt_ratio": 28.0, "revenue_yoy": 22.0},
                "technical": {"rsi_14": 26.0, "moving_averages": {"ma20": 26.0, "ma60": 22.0}},
                "momentum": {"mom_20d": 0.15},
                "risk": {"volatility_20d": 0.015},
            },
        }

    monkeypatch.setattr(decision_mod, "get_db", lambda: _DecisionDB())
    monkeypatch.setattr(decision_mod, "get_investment_analysis", _analysis_context)
    monkeypatch.setattr(decision_mod.technical_analysis, "calculate_macd", lambda closes: {"histogram": [0.1, 0.2]})

    mcp = _DummyMCP()
    decision_mod.register(mcp)
    result = await mcp.should_i_buy("000001", investment_style="balanced", as_of="2026-04-20")

    assert result["success"] is True, result
    data = result["data"]
    assert data["pit_guard"]["active"] is True
    assert data["pit_guard"]["dropped_future_rows"] > 0
    assert data["analysis_date"] <= "2026-04-20"
    assert data["prediction_quality"]["method"] == "threshold_backtest_proxy"
    assert data["prediction_quality"]["support_samples"] > 0
    assert data["prediction_quality"]["sample_size"] == data["prediction_quality"]["support_samples"]
    assert data["prediction_quality"]["calibration_bucket"]
    assert data["prediction_quality"]["ece"] is not None
    assert data["prediction_quality"]["brier_score"] is not None
    assert data["offline_decision_baseline"]["method"] == "decision_threshold_bucket_backtest_proxy"
    assert data["offline_decision_baseline"]["recommendation"] == data["recommendation"]
    assert "benchmark_delta" in data["offline_decision_baseline"]
    assert data["prediction_interval"]["horizon_days"] == 10
    assert "lower_return" in data["prediction_interval"]
    assert "interval_width" in data["prediction_interval"]
    assert "observed_coverage" in data["prediction_interval"]
    assert result["meta"]["pit_guard"]["active"] is True


@pytest.mark.asyncio
async def test_compliance_manager_realtime_checks_can_block_limit_up(monkeypatch):
    from akshare_mcp.tools.managers import compliance_manager as compliance_mod

    monkeypatch.setattr(
        compliance_mod,
        "get_realtime_quote",
        lambda code: {
            "success": True,
            "data": {
                "code": code,
                "name": "测试股份",
                "price": 110.0,
                "preClose": 100.0,
                "source": "mock_quote",
            },
        },
    )
    monkeypatch.setattr(
        compliance_mod,
        "get_order_book",
        lambda code: {
            "success": True,
            "data": {
                "code": code,
                "source": "mock_book",
                "bids": [{"price": 109.9, "volume": 1000}],
                "asks": [{"price": 110.0, "volume": 0}],
            },
        },
    )

    mcp = _DummyMCP()
    compliance_mod.register_compliance_manager(mcp)
    result = await mcp.compliance_manager(
        action="check_order",
        params={"code": "600519", "direction": "buy", "quantity": 100, "price": 110.0},
    )

    assert result["success"] is True, result
    data = result["data"]
    assert data["blocked"] is True
    assert data["realtime"]["quote_available"] is True
    assert data["realtime"]["order_book_available"] is True
    assert data["realtime"]["at_limit_up"] is True
    assert data["checks"]["limit_up_down"] is False
    assert any("涨停" in item or "无法买入" in item for item in data["violations"])


@pytest.mark.asyncio
async def test_analyze_stock_sentiment_adds_historical_validation(monkeypatch):
    from akshare_mcp.tools import sentiment as sentiment_mod

    class _SentimentDB:
        async def get_klines(self, code, limit=None):
            rows = []
            for i in range(140):
                day = i + 1
                month = 1 + (day - 1) // 28
                day_in_month = ((day - 1) % 28) + 1
                rows.append(
                    {
                        "date": f"2026-{month:02d}-{day_in_month:02d}",
                        "open": float(20 + i * 0.3),
                        "high": float(20.4 + i * 0.3),
                        "low": float(19.8 + i * 0.3),
                        "close": float(20 + i * 0.3),
                        "volume": 10000 + i * 100,
                    }
                )
            return rows

    monkeypatch.setattr(sentiment_mod, "get_db", lambda: _SentimentDB())

    mcp = _DummyMCP()
    sentiment_mod.register(mcp)
    result = await mcp.analyze_stock_sentiment("000001")

    assert result["success"] is True, result
    data = result["data"]
    assert data["code"] == "000001"
    assert "historical_validation" in data
    assert data["historical_validation"]["method"] == "price_momentum_bucket_proxy"
    assert data["data_quality"]["price_history_points"] >= 100
    assert "headline_count" in data["data_quality"]
