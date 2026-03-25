from types import SimpleNamespace

import pytest


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return dict(self._payload)


class _PromptDB:
    async def get_klines(self, code, limit=180):
        return [
            {"date": "2026-03-17", "open": 10.0, "high": 10.5, "low": 9.9, "close": 10.2, "volume": 1000, "amount": 2000.0},
            {"date": "2026-03-18", "open": 10.2, "high": 10.6, "low": 10.0, "close": 10.4, "volume": 1100, "amount": 2100.0},
            {"date": "2026-03-19", "open": 10.4, "high": 10.8, "low": 10.3, "close": 10.7, "volume": 1400, "amount": 2600.0},
            {"date": "2026-03-20", "open": 10.7, "high": 11.0, "low": 10.6, "close": 10.9, "volume": 1500, "amount": 2800.0},
            {"date": "2026-03-21", "open": 10.9, "high": 11.2, "low": 10.8, "close": 11.1, "volume": 1700, "amount": 3000.0},
        ] * 30

    async def get_financials(self, code, limit=4):
        return [
            {
                "roe": 18.2,
                "roa": 9.1,
                "gross_margin": 42.0,
                "debt_ratio": 0.31,
                "revenue_growth": 12.5,
                "profit_growth": 15.6,
            }
        ]

    async def get_stock_info(self, code):
        return {"pe_ratio": 21.5, "pb_ratio": 4.3, "price": 11.1}


class _FallbackDB(_PromptDB):
    pass


class _AcquireContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DbFirstPromptConn:
    async def fetch(self, query, *params):
        if "FROM vector_documents" in query:
            code = params[0]
            doc_types = set(params[1])
            if "news" in doc_types:
                return [{"id": 1, "doc_type": "news", "content": f"{code} 数据库新闻", "date": "2026-03-21"}]
            if "notice" in doc_types or "announcement" in doc_types:
                return [{"id": 2, "doc_type": "notice", "content": f"{code} 数据库公告", "date": "2026-03-20"}]
            if "research" in doc_types or "report" in doc_types:
                return []
        if "FROM research_reports" in query:
            code = params[0]
            return [
                {
                    "code": code,
                    "title": f"{code} 数据库研报",
                    "rating": "buy",
                    "target_price": 12.3,
                    "institution": "DB Broker",
                    "analyst": "Analyst A",
                    "publish_date": "2026-03-19",
                    "summary": "数据库研报摘要",
                    "pdf_url": "",
                }
            ]
        return []

    async def fetchrow(self, query, *params):
        if "FROM stock_fund_flow" in query:
            code = params[0]
            return {
                "code": code,
                "trade_date": "2026-03-21",
                "main_net_inflow": 888000.0,
                "super_large_net_inflow": 300000.0,
                "large_net_inflow": 200000.0,
                "middle_net_inflow": -50000.0,
                "small_net_inflow": -120000.0,
                "source": "stock_fund_flow",
            }
        return None


class _DbFirstPromptDB(_PromptDB):
    def __init__(self):
        self._conn = _DbFirstPromptConn()

    def acquire(self):
        return _AcquireContext(self._conn)


def test_factor_llm_config_falls_back_to_strategy_env(monkeypatch, tmp_path):
    from akshare_mcp.services.factor_llm_provider import FactorLLMConfig

    env_path = tmp_path / "empty.env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("AKSHARE_MCP_ENV", str(env_path))
    monkeypatch.delenv("FACTOR_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("FACTOR_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("FACTOR_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FACTOR_LLM_MODEL", raising=False)
    monkeypatch.delenv("FACTOR_LLM_TIMEOUT_SEC", raising=False)
    monkeypatch.setenv("FACTOR_LLM_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("STRATEGY_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("STRATEGY_LLM_API_KEY", "test-key")
    monkeypatch.setenv("STRATEGY_LLM_MODEL", "strategy-model")
    monkeypatch.setenv("STRATEGY_LLM_TIMEOUT_SEC", "66")

    config = FactorLLMConfig.from_env()

    assert config.enabled is True
    assert config.provider == "openai_compatible"
    assert config.base_url == "http://llm.local/v1"
    assert config.api_key == "test-key"
    assert config.model == "strategy-model"
    assert config.timeout_sec == 66.0


def test_factor_generation_payload_normalizes_holding_period_range():
    from akshare_mcp.services.factor_llm_provider import validate_factor_generation_payload

    payload = validate_factor_generation_payload(
        {
            "candidates": [
                {
                    "name": "volume_regime_shift",
                    "hypothesis": "成交量抬升后 alpha 切换。",
                    "family": "liquidity",
                    "inputs": ["close", "volume"],
                    "expression_dsl": "zscore(volume,20) * delta(close,5)",
                    "expected_holding_period": "10-20 trading days",
                    "expected_regime": ["trend"],
                    "complexity_hint": "medium",
                    "novelty_rationale": "测试 holding period 范围归一化。",
                }
            ]
        }
    )

    assert payload["candidates"][0]["expected_holding_period"] == 15


@pytest.mark.asyncio
async def test_factor_llm_provider_parses_json_payload():
    from akshare_mcp.services.factor_llm_provider import FactorLLMConfig, FactorLLMProvider
    from akshare_mcp.services.factor_prompt_builder import FactorMiningPrompt

    async def _fake_post(*args, **kwargs):
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": """```json
                            {
                              "candidates": [
                                {
                                  "name": "event_attention_reversal",
                                  "hypothesis": "事件密集但主力资金承接弱时短期存在反转。",
                                  "family": "event_reversal",
                                  "inputs": ["close", "volume", "main_net_inflow"],
                                  "expression_dsl": "zscore(volume,20) * -zscore(main_net_inflow,20) * -delta(close,5)",
                                  "expected_holding_period": 5,
                                  "expected_regime": ["high_event_density"],
                                  "complexity_hint": "medium",
                                  "novelty_rationale": "结合事件热度与资金承接。"
                                }
                              ],
                              "analysis": {"market_regime": "event-driven"},
                              "warnings": []
                            }
                            ```"""
                        }
                    }
                ],
                "usage": {"total_tokens": 321},
            }
        )

    provider = FactorLLMProvider(
        FactorLLMConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="http://llm.local/v1",
            api_key="test-key",
            model="test-factor-model",
            retry_count=0,
        )
    )
    provider._client = SimpleNamespace(post=_fake_post, aclose=lambda: None)
    prompt = FactorMiningPrompt(
        system_prompt="system",
        user_prompt="user",
        context_summary={},
        request_payload={},
        source_chain=[],
        schema_path="/tmp/factor_candidate.schema.json",
    )

    result = await provider.generate_candidates(prompt, candidate_count=1)

    assert result["candidate_count"] == 1
    assert result["provider"] == "openai_compatible"
    assert result["model"] == "test-factor-model"
    assert result["candidates"][0]["source_model"] == "test-factor-model"
    assert result["candidates"][0]["generation_trace"]["provider"] == "openai_compatible"


@pytest.mark.asyncio
async def test_factor_prompt_builder_builds_context(monkeypatch):
    import akshare_mcp.services.factor_prompt_builder as prompt_mod

    async def _fake_alt(db, code, lookback_days=30, limit=6):
        return (
            {
                "sentiment": {"score_raw": 0.3},
                "event": {"score_raw": 0.1},
                "capital_flow": {"score_raw": 0.2},
                "alternative_composite": {"score_raw": 0.25},
            },
            ["tools.news.*"],
        )

    monkeypatch.setattr(prompt_mod, "_compute_alternative_factors_for_code", _fake_alt)
    monkeypatch.setattr(prompt_mod, "get_stock_news", lambda code, limit=6: {"success": True, "data": [{"title": f"{code} 景气上行"}]})
    monkeypatch.setattr(prompt_mod, "get_stock_notices", lambda start_date, end_date, stock_code: {"success": True, "data": [{"title": f"{stock_code} 发布公告"}]})
    monkeypatch.setattr(prompt_mod, "get_research_reports", lambda code, limit=6: {"success": True, "data": [{"title": f"{code} 研究覆盖"}]})
    monkeypatch.setattr(prompt_mod, "get_stock_fund_flow", lambda code: {"success": True, "data": {"mainNetInflow": 1000000}})

    prompt = await prompt_mod.build_factor_mining_prompt(
        db=_PromptDB(),
        codes=["600519"],
        candidate_count=2,
    )

    from akshare_mcp.services.factor_candidate_compiler import SUPPORTED_FACTOR_FIELDS

    assert prompt.context_summary["codes"] == ["600519"]
    assert prompt.context_summary["rows"][0]["alternative_factors"]["alternative_composite_score"] == 0.25
    assert "candidates" in prompt.user_prompt
    assert "allowed_operators" in prompt.user_prompt
    assert sorted(prompt.request_payload["field_hints"]) == sorted(SUPPORTED_FACTOR_FIELDS)
    assert "event_score" not in prompt.request_payload["field_hints"]
    assert "non_dsl_context" in prompt.request_payload["context_rows"][0]
    assert "single-stock daily time-series frame" in prompt.user_prompt


@pytest.mark.asyncio
async def test_factor_prompt_builder_prefers_db_context_before_external(monkeypatch):
    import akshare_mcp.services.factor_prompt_builder as prompt_mod

    async def _fake_alt(db, code, lookback_days=30, limit=6):
        return ({"alternative_composite": {"score_raw": 0.42}}, ["db.vector_documents_legacy.news"])

    monkeypatch.setattr(prompt_mod, "_compute_alternative_factors_for_code", _fake_alt)
    monkeypatch.setattr(
        prompt_mod,
        "get_stock_news",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stock news fallback should not run")),
    )
    monkeypatch.setattr(
        prompt_mod,
        "get_stock_notices",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stock notices fallback should not run")),
    )
    monkeypatch.setattr(
        prompt_mod,
        "get_research_reports",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("research fallback should not run")),
    )
    monkeypatch.setattr(
        prompt_mod,
        "get_stock_fund_flow",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fund flow fallback should not run")),
    )

    prompt = await prompt_mod.build_factor_mining_prompt(
        db=_DbFirstPromptDB(),
        codes=["600519"],
        candidate_count=2,
    )

    row = prompt.context_summary["rows"][0]
    assert row["recent_headlines"]["news"][0] == "600519 数据库新闻"
    assert row["recent_headlines"]["notices"][0] == "600519 数据库公告"
    assert row["recent_headlines"]["research"][0] == "600519 数据库研报"
    assert row["fund_flow"]["mainNetInflow"] == 888000.0
    assert "db.research_reports" in prompt.source_chain
    assert "db.stock_fund_flow" in prompt.source_chain


@pytest.mark.asyncio
async def test_quant_manager_llm_factor_mining_falls_back_to_local_rule(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    from akshare_mcp.services.factor_prompt_builder import FactorMiningPrompt

    class _DisabledProvider:
        config = SimpleNamespace(provider="openai_compatible", model="")

        def is_enabled(self):
            return False

    async def _fake_prompt_builder(db, codes, **kwargs):
        return FactorMiningPrompt(
            system_prompt="system",
            user_prompt="user",
            context_summary={"codes": list(codes), "rows": []},
            request_payload={"codes": list(codes)},
            source_chain=["services.factor_prompt_builder"],
            schema_path="/tmp/factor_candidate.schema.json",
        )

    monkeypatch.setattr(quant_mod, "get_db", lambda: _FallbackDB())
    monkeypatch.setattr(quant_mod, "get_factor_llm_provider", lambda: _DisabledProvider())
    monkeypatch.setattr(quant_mod, "build_factor_mining_prompt", _fake_prompt_builder)

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    result = await mcp.quant_manager(
        action="llm_factor_mining",
        code="600519",
        kwargs={"candidate_count": 2, "persist_artifact": False},
    )

    assert result["success"] is True
    assert result["data"]["fallback_used"] is True
    assert result["data"]["generation_mode"] == "local_rule_fallback"
    assert len(result["data"]["candidates"]) >= 1
    assert result["data"]["candidates"][0]["source_model"] == "local_rule_fallback"


@pytest.mark.asyncio
async def test_quant_manager_llm_factor_mining_runs_startup_warmup(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    from akshare_mcp.services.factor_prompt_builder import FactorMiningPrompt

    class _DisabledProvider:
        config = SimpleNamespace(provider="openai_compatible", model="")

        def is_enabled(self):
            return False

    async def _fake_prompt_builder(db, codes, **kwargs):
        return FactorMiningPrompt(
            system_prompt="system",
            user_prompt="user",
            context_summary={"codes": list(codes), "rows": []},
            request_payload={"codes": list(codes)},
            source_chain=["services.factor_prompt_builder"],
            schema_path="/tmp/factor_candidate.schema.json",
        )

    warmup_calls = []

    async def _fake_warmup_runner(**kwargs):
        warmup_calls.append(dict(kwargs))
        return {
            "ok": True,
            "status": "completed",
            "task_type": kwargs.get("task_type"),
            "force": bool(kwargs.get("force")),
            "matched": 1,
            "executed": 1,
            "failed": 0,
            "executed_task_ids": ["sync_core_market_1"],
            "failed_schedule_ids": [],
            "schedules": [],
        }

    monkeypatch.setattr(quant_mod, "get_db", lambda: _FallbackDB())
    monkeypatch.setattr(quant_mod, "get_factor_llm_provider", lambda: _DisabledProvider())
    monkeypatch.setattr(quant_mod, "build_factor_mining_prompt", _fake_prompt_builder)
    monkeypatch.setattr(quant_mod, "run_runtime_data_warmup", _fake_warmup_runner)

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    result = await mcp.quant_manager(
        action="llm_factor_mining",
        code="600519",
        kwargs={"candidate_count": 2, "persist_artifact": False, "startup_warmup": True},
    )

    assert result["success"] is True
    assert len(warmup_calls) == 1
    assert warmup_calls[0]["task_type"] == "core_market,factor_context"
    assert result["data"]["startup_warmup"]["status"] == "completed"
    assert result["data"]["startup_warmup"]["executed"] == 1


@pytest.mark.asyncio
async def test_quant_manager_llm_factor_mining_filters_compiler_invalid_candidates(monkeypatch):
    import akshare_mcp.tools.managers.quant_manager as quant_mod
    from akshare_mcp.services.factor_prompt_builder import FactorMiningPrompt

    class _EnabledProvider:
        config = SimpleNamespace(provider="openai_compatible", model="gpt-test")

        def is_enabled(self):
            return True

        async def generate_candidates(self, prompt, candidate_count=2):
            return {
                "provider": "openai_compatible",
                "model": "gpt-test",
                "candidate_count": 2,
                "requested_candidate_count": candidate_count,
                "analysis": {},
                "warnings": [],
                "candidates": [
                    {
                        "name": "invalid_event_factor",
                        "hypothesis": "bad",
                        "family": "event",
                        "inputs": ["event_score"],
                        "expression_dsl": "rank(zscore(event_score))",
                        "expected_holding_period": 10,
                        "expected_regime": ["event"],
                        "complexity_hint": "low",
                        "novelty_rationale": "bad",
                        "source_model": "gpt-test",
                    },
                    {
                        "name": "valid_momentum_factor",
                        "hypothesis": "good",
                        "family": "momentum",
                        "inputs": ["momentum_20d", "volatility_20d"],
                        "expression_dsl": "zscore(momentum_20d, 20) - zscore(volatility_20d, 20)",
                        "expected_holding_period": 10,
                        "expected_regime": ["trend"],
                        "complexity_hint": "medium",
                        "novelty_rationale": "good",
                        "source_model": "gpt-test",
                    },
                ],
            }

    class _MemoryService:
        async def build_prompt_memory_context(self, **kwargs):
            return {}

        async def annotate_generated_candidates(self, candidates, codes=None):
            return {"candidates": list(candidates or []), "warnings": []}

        def apply_duplicate_policy(self, candidates, **kwargs):
            rows = list(candidates or [])
            return {
                "mode": "penalty",
                "kept_candidates": rows,
                "blocked_candidates": [],
                "summary": {
                    "mode": "penalty",
                    "input_count": len(rows),
                    "kept_count": len(rows),
                    "blocked_count": 0,
                    "blocked_ratio": 0.0,
                },
                "warnings": [],
            }

    async def _fake_prompt_builder(db, codes, **kwargs):
        return FactorMiningPrompt(
            system_prompt="system",
            user_prompt="user",
            context_summary={"codes": list(codes), "rows": []},
            request_payload={"codes": list(codes)},
            source_chain=["services.factor_prompt_builder"],
            schema_path="/tmp/factor_candidate.schema.json",
        )

    monkeypatch.setattr(quant_mod, "get_db", lambda: _FallbackDB())
    monkeypatch.setattr(quant_mod, "get_factor_llm_provider", lambda: _EnabledProvider())
    monkeypatch.setattr(quant_mod, "get_factor_research_memory_service", lambda: _MemoryService())
    monkeypatch.setattr(quant_mod, "build_factor_mining_prompt", _fake_prompt_builder)

    mcp = _DummyMCP()
    quant_mod.register_quant_manager(mcp)

    result = await mcp.quant_manager(
        action="llm_factor_mining",
        code="600519",
        kwargs={"candidate_count": 2, "persist_artifact": False, "allow_fallback": False},
    )

    assert result["success"] is True
    assert result["data"]["candidate_count"] == 1
    assert result["data"]["compiler_screening"]["rejected_count"] == 1
    assert result["data"]["candidates"][0]["name"] == "valid_momentum_factor"
    assert result["data"]["blocked_candidates"][0]["name"] == "invalid_event_factor"
    assert any("compiler_screen_rejected=" in item for item in result["data"]["warnings"])
