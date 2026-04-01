"""StrategySubmitter tests extracted from the strategy-factory integration suite."""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock

from akshare_mcp.services.strategy_factory import StrategySubmitter

from ._strategy_factory_marketplace_helpers import _make_klines
from ._strategy_factory_test_support import _StrategyDB


class TestStrategySubmitter:
    @pytest.mark.asyncio
    async def test_submitter_persists_validation_and_risk_metrics(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "B", "total_score": 58.0, "recommendation": "Strong"}, "walk_forward": {"oos_rank_ic_mean": 0.04}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 2.1, "cvar_percent": 3.2, "stress_loss_percent": -20.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True}),
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "backtest_metrics": {"sharpe_ratio": 1.1, "total_return": 0.2, "max_drawdown": 0.12, "win_rate": 0.55, "trades_count": 8},
                "spawn_reason": "测试提交",
            }
        ], {"fg_level": "neutral"}, db)
        periods = [call.args[1] for call in db.save_strategy_metrics.await_args_list]
        assert result["passed_quality_gate"] == 1
        assert "backtest" in periods
        assert "validation" in periods
        assert "risk" in periods
        db.save_strategy_quality_report.assert_awaited_once()
        saved_report = db.save_strategy_quality_report.await_args.args[2]
        assert saved_report["passed"] is True
        assert saved_report["dedup_report"] == {}
        assert saved_report["summary"]["review_source"] == "strategy_factory_submit"
        assert saved_report["quality_gate"]["reason_codes"] == []

    @pytest.mark.asyncio
    async def test_submitter_persists_target_universe_into_strategy_params(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True}),
        )

        await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["688981", "002371"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["688981", "002371"]},
                "selection_logic": ["prefer semiconductor leaders"],
                "research_task": {"task_id": "task_chip", "opportunity_type": "sector_breakout"},
                "backtest_metrics": {"sharpe_ratio": 1.1, "total_return": 0.2, "max_drawdown": 0.12, "win_rate": 0.55, "trades_count": 8},
                "spawn_reason": "测试提交",
            }
        ], {"fg_level": "neutral"}, db)

        saved_strategy = db.save_strategy.await_args.args[0]
        assert saved_strategy["params"]["target_symbols"] == ["688981", "002371"]
        assert saved_strategy["params"]["stock_pool"]["symbols"] == ["688981", "002371"]
        assert saved_strategy["params"]["selection_logic"] == ["prefer semiconductor leaders"]
        assert saved_strategy["params"]["research_task"]["task_id"] == "task_chip"

    @pytest.mark.asyncio
    async def test_submitter_preserves_event_context_in_experiment_record(self, monkeypatch):
        submitter = StrategySubmitter()
        db = _StrategyDB()
        await db.save_strategy_generation_experiment({
            "experiment_id": "exp_evt_submit_1",
            "strategy_id": None,
            "parent_strategy_id": "parent_evt_1",
            "source": "strategy_factory:sector_breakout",
            "generator_type": "external_llm",
            "status": "generated",
            "evaluation": {"committee_review": {"final_score": 0.81}},
        })

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": False, "reason": "Insufficient kline data for quality gate"}),
        )

        result = await submitter.submit([
            {
                "experiment_id": "exp_evt_submit_1",
                "source": "strategy_factory:sector_breakout",
                "generator_type": "external_llm",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"metadata": {"target_symbols": ["601857", "600938"]}}},
                "target_symbols": ["601857", "600938"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601857", "600938"]},
                "selection_logic": ["follow geopolitics"],
                "research_scope": {"window": "20d"},
                "research_task": {
                    "task_id": "task_evt_oil",
                    "task_key": "event_theme:2026-03-09:evt_oil_1:upstream_oil_gas",
                    "task_source": "event_driven",
                    "event_id": "evt_oil_1",
                    "event_type": "geopolitics",
                    "theme_code": "upstream_oil_gas",
                    "theme": "event_theme_upstream_oil_gas",
                    "direction": "positive",
                    "horizon": "swing_5_20d",
                    "target_symbols": ["601857", "600938"],
                    "evidence_bundle": {
                        "event_id": "evt_oil_1",
                        "event_name": "中东战事升级",
                        "event_type": "geopolitics",
                        "event_summary": "中东局势升级提升原油供给扰动预期。",
                        "theme_code": "upstream_oil_gas",
                        "theme_name": "上游油气",
                        "direction": "positive",
                        "horizon": "swing_5_20d",
                        "signal_count": 2,
                        "supporting_reasons": ["油价中枢抬升", "供给扰动强化"],
                        "score_summary": {"avg_final_score": 0.87, "max_final_score": 0.93, "top_symbols": ["601857", "600938"]},
                    },
                },
                "spawn_reason": "事件驱动原型",
            }
        ], {"date": "2026-03-09", "fg_level": "greed", "fear_greed_index": 68}, db)

        saved = await db.get_strategy_generation_experiment("exp_evt_submit_1")

        assert result["created"] == 1
        assert result["passed_quality_gate"] == 0
        assert saved["parent_strategy_id"] == "parent_evt_1"
        assert saved["generated_strategy_id"] == result["strategies"][0]["strategy_id"]
        assert saved["evaluation"]["committee_review"]["final_score"] == 0.81
        assert saved["evaluation"]["research_task"]["event_id"] == "evt_oil_1"
        assert saved["evaluation"]["event_context"]["theme_code"] == "upstream_oil_gas"
        assert saved["strategy_spec"]["research_task"]["theme_code"] == "upstream_oil_gas"

    @pytest.mark.asyncio
    async def test_submitter_allows_provisional_incubation_for_external_llm_prototype(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "D", "total_score": 18.0, "recommendation": "Weak"}, "walk_forward": {"oos_rank_ic_mean": 0.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.8, "cvar_percent": 2.6, "stress_loss_percent": -18.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={
                "passed": True,
                "passed_strict": False,
                "provisional_pass": True,
                "reasons": [],
                "warnings": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
                "warning_codes": [
                    "validation_grade_d",
                    "provisional_skip:walk_forward_ic_ir",
                ],
            }),
        )

        result = await submitter.submit([
            {
                "name": "高股息防御切换",
                "strategy_type": "dsl_rule",
                "params": {"dsl": {"version": "1.0", "timeframe": "daily", "entry": {"any": [{"op": "gt", "left": {"field": "close"}, "right": {"indicator": "sma", "field": "close", "window": 20}}]}, "exit": {"any": [{"op": "lt", "left": {"field": "close"}, "right": {"indicator": "sma", "field": "close", "window": 20}}]}}},
                "backtest_metrics": {"sharpe_ratio": 0.22, "total_return": 0.08, "max_drawdown": 0.12, "win_rate": 0.51, "trades_count": 6},
                "spawn_reason": "外部 AI 原型提交",
                "tags": ["factory", "external_llm", "ai_generated"],
                "llm_prompt": {"system": "s", "user": "u"},
                "llm_response": {"provider": "openai_compatible", "model": "test-model"},
            }
        ], {"fg_level": "neutral"}, db)

        saved_report = db.save_strategy_quality_report.await_args.args[2]
        assert result["passed_quality_gate"] == 1
        assert result["gate_3_passed"] == 1
        assert result["gate_3_failed"] == 0
        assert result["gate_3_provisional_passed"] == 1
        assert result["gate_report"]["gate_3"]["status"] == "completed_submission_gate"
        assert result["gate_report"]["gate_3"]["provisional_passed_count"] == 1
        assert result["strategies"][0]["provisional_pass"] is True
        assert result["strategies"][0]["gate_3"]["provisional_pass"] is True
        assert saved_report["passed"] is True
        assert saved_report["quality_gate"]["provisional_pass"] is True
        assert "validation_grade_d" in saved_report["quality_gate"]["warning_codes"]


    @pytest.mark.asyncio
    async def test_submitter_aggregates_gate_3_failure_reasons(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "C", "total_score": 42.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.4, "cvar_percent": 2.0, "stress_loss_percent": -11.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={
                "passed": False,
                "reasons": ["Insufficient kline data for quality gate"],
                "reason_codes": ["insufficient_kline_data"],
            }),
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "backtest_metrics": {"sharpe_ratio": 0.31, "total_return": 0.09, "max_drawdown": 0.13, "win_rate": 0.48, "trades_count": 3},
                "spawn_reason": "Gate-3 失败统计测试",
            }
        ], {"fg_level": "neutral"}, db)

        assert result["passed_quality_gate"] == 0
        assert result["gate_3_passed"] == 0
        assert result["gate_3_failed"] == 1
        assert result["gate_3_provisional_passed"] == 0
        assert result["gate_3_failure_reason_topn"] == [
            {"reason_code": "insufficient_kline_data", "count": 1},
            {"reason_code": "factory_policy_backtest_trade_count_3_4", "count": 1},
        ]
        assert result["gate_report"]["final_decision"]["stage"] == "gate_3"
        assert result["strategies"][0]["gate_3"]["reason_codes"] == [
            "insufficient_kline_data",
            "factory_policy_backtest_trade_count_3_4",
        ]
        assert result["strategies"][0]["status"] == "rejected"
        assert result["strategies"][0]["passed"] is False
        assert result["strategies"][0]["provisional_pass"] is False
        assert result["strategies"][0]["reason_codes"] == [
            "insufficient_kline_data",
            "factory_policy_backtest_trade_count_3_4",
        ]
        assert result["strategies"][0]["warning_codes"] == []
        db.update_strategy_status.assert_awaited()
        status_call = db.update_strategy_status.await_args_list[-1]
        assert status_call.args[1] == "rejected"
        assert status_call.kwargs["reason"] == "quality_gate_failed"
        assert status_call.kwargs["metadata"]["quality_gate"]["reason_codes"] == [
            "insufficient_kline_data",
            "factory_policy_backtest_trade_count_3_4",
        ]

    @pytest.mark.asyncio
    async def test_shared_submission_gate_grants_provisional_incubation_for_factory_ai_strategy(self, monkeypatch):
        from types import SimpleNamespace
        from akshare_mcp.services.strategy_factory import submission_gate as submission_gate_mod

        class _DummyStrategy:
            def set_parameters(self, _params):
                return None

            def generate_signals(self, closes):
                return np.linspace(0.0, 1.0, len(closes))

        class _WalkForwardValidator:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_ir=0.0)

        class _PurgedKFoldCV:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_mean=0.03)

        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(n=160, base=10.0, trend=0.01, noise=0.001))

        monkeypatch.setattr(
            "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.get",
            lambda *_args, **_kwargs: _DummyStrategy,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.WalkForwardValidator",
            _WalkForwardValidator,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.PurgedKFoldCV",
            _PurgedKFoldCV,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.bootstrap_ic_ci",
            lambda *_args, **_kwargs: {"ci_lower": 0.01},
        )

        gate = await submission_gate_mod.run_submission_quality_gate(
            db,
            {
                "id": "factory_gate_1",
                "strategy_type": "dsl_rule",
                "params": {"lookback": 20},
                "tags": ["factory", "external_llm", "ai_generated"],
            },
            validation_report={"rating": {"grade": "D", "total_score": 18.0}},
            risk_report={"var_percent": 1.8, "cvar_percent": 2.6, "stress_loss_percent": -18.0},
            backtest_metrics={"sharpe_ratio": 0.22, "max_drawdown": 0.12, "trade_count": 2},
        )

        assert gate["passed"] is True
        assert gate["passed_strict"] is False
        assert gate["provisional_pass"] is True
        assert "validation_grade_d" in gate["warning_codes"]
        assert "walk_forward_ic_ir" in gate["statistical_checks_failed_names"]

    @pytest.mark.asyncio
    async def test_shared_submission_gate_allows_technical_fallback_for_degenerate_validation_stats(self, monkeypatch):
        from types import SimpleNamespace
        from akshare_mcp.services.strategy_factory import submission_gate as submission_gate_mod

        class _DummyStrategy:
            def __init__(self):
                self._params = {}

            def set_parameters(self, params):
                self._params = dict(params or {})

            def generate_signals(self, closes):
                lookback = float(self._params.get("lookback", 8) or 8)
                threshold = float(self._params.get("threshold", 0.003) or 0.003)
                base = np.diff(closes, prepend=closes[0]).astype(float)
                phase = np.linspace(0.0, np.pi * max(lookback * threshold * 220.0, 1.0), len(closes))
                return base + np.sin(phase)

        class _WalkForwardValidator:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_ir=0.0)

        class _PurgedKFoldCV:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_mean=0.0)

        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(n=160, base=10.0, trend=0.01, noise=0.001))

        monkeypatch.setattr(
            "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.get",
            lambda *_args, **_kwargs: _DummyStrategy,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.WalkForwardValidator",
            _WalkForwardValidator,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.PurgedKFoldCV",
            _PurgedKFoldCV,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.bootstrap_ic_ci",
            lambda *_args, **_kwargs: {"ci_lower": -0.03},
        )

        gate = await submission_gate_mod.run_submission_quality_gate(
            db,
            {
                "id": "factory_gate_technical_fallback",
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.002993},
                "tags": ["factory", "auto_generated", "ai_generated", "llm_proxy_fallback"],
            },
            validation_report={
                "rating": {
                    "grade": "D",
                    "total_score": 0.0,
                    "scores": {
                        "oos_ic": 0.0,
                        "oos_ir": 0.0,
                        "stability": 0.0,
                        "ci_significance": 0.0,
                        "positive_ratio": 0.0,
                    },
                },
                "walk_forward": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
                "purged_kfold": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
                "bootstrap_ci": {"sample_size": 0, "ci_lower": 0.0, "ci_upper": 0.0},
            },
            risk_report={"var_percent": 1.1201, "cvar_percent": 1.5402, "stress_loss_percent": -20.0},
            backtest_metrics={"sharpe_ratio": 0.6456, "max_drawdown": 0.1146, "trade_count": 18},
        )

        assert gate["passed"] is True
        assert gate["passed_strict"] is False
        assert gate["provisional_pass"] is True
        assert "validation_report_degenerate" in gate["warning_codes"]
        assert "provisional_path_technical_validation_fallback" in gate["warning_codes"]
        assert gate["statistical_checks_passed"] < 2
        assert "param_sensitivity" in gate["statistical_checks_failed_names"]

    @pytest.mark.asyncio
    async def test_shared_submission_gate_allows_factory_technical_fallback_without_ai_tags(self, monkeypatch):
        from types import SimpleNamespace
        from akshare_mcp.services.strategy_factory import submission_gate as submission_gate_mod

        class _DummyStrategy:
            def __init__(self):
                self._params = {}

            def set_parameters(self, params):
                self._params = dict(params or {})

            def generate_signals(self, closes):
                period = float(self._params.get("rsi_period", 6) or 6)
                base = np.diff(closes, prepend=closes[0]).astype(float)
                phase = np.linspace(0.0, np.pi * max(period / 4.0, 1.0), len(closes))
                return base + np.cos(phase)

        class _WalkForwardValidator:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_ir=0.0)

        class _PurgedKFoldCV:
            def __init__(self, *args, **kwargs):
                pass

            def validate(self, *_args, **_kwargs):
                return SimpleNamespace(oos_ic_mean=0.0)

        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(n=160, base=10.0, trend=0.01, noise=0.001))

        monkeypatch.setattr(
            "akshare_mcp.services.backtest.strategy_registry.StrategyRegistry.get",
            lambda *_args, **_kwargs: _DummyStrategy,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.WalkForwardValidator",
            _WalkForwardValidator,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.PurgedKFoldCV",
            _PurgedKFoldCV,
        )
        monkeypatch.setattr(
            "akshare_mcp.services.validation.bootstrap_ic_ci",
            lambda *_args, **_kwargs: {"ci_lower": -0.02},
        )

        gate = await submission_gate_mod.run_submission_quality_gate(
            db,
            {
                "id": "factory_gate_rsi_fallback",
                "strategy_type": "rsi",
                "params": {"rsi_period": 6, "oversold": 30, "overbought": 70},
                "tags": ["factory", "auto_generated", "rsi"],
            },
            validation_report={
                "rating": {
                    "grade": "D",
                    "total_score": 0.0,
                    "scores": {
                        "oos_ic": 0.0,
                        "oos_ir": 0.0,
                        "stability": 0.0,
                        "ci_significance": 0.0,
                        "positive_ratio": 0.0,
                    },
                },
                "walk_forward": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
                "purged_kfold": {"n_folds": 0, "oos_rank_ic_mean": 0.0, "oos_rank_ic_ir": 0.0},
                "bootstrap_ci": {"sample_size": 0, "ci_lower": 0.0, "ci_upper": 0.0},
            },
            risk_report={"var_percent": 1.1201, "cvar_percent": 1.5402, "stress_loss_percent": -20.0},
            backtest_metrics={"sharpe_ratio": 0.22, "max_drawdown": 0.14, "trade_count": 16},
        )

        assert gate["passed"] is True
        assert gate["provisional_pass"] is True
        assert "validation_report_degenerate" in gate["warning_codes"]

    @pytest.mark.asyncio
    async def test_submitter_passes_review_context_to_shared_submission_gate(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "B", "total_score": 82.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.2, "cvar_percent": 1.8, "stress_loss_percent": -12.0}),
        )
        gate_mock = AsyncMock(return_value={"passed": True, "reasons": []})
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            gate_mock,
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "backtest_metrics": {"sharpe_ratio": 0.61, "total_return": 0.19, "max_drawdown": 0.08, "trade_count": 3},
                "spawn_reason": "factory_context_test",
            }
        ], {"fg_level": "neutral"}, db)

        assert result["submitted"] == 1
        assert gate_mock.await_count == 1
        gate_kwargs = gate_mock.await_args.kwargs
        assert gate_kwargs["validation_report"]["rating"]["grade"] == "B"
        assert gate_kwargs["risk_report"]["var_percent"] == 1.2
        assert gate_kwargs["backtest_metrics"]["trade_count"] == 3
        assert gate_kwargs["backtest_metrics"]["trades_count"] is None

    @pytest.mark.asyncio
    async def test_submitter_reuses_existing_strategy_for_refresh_existing_candidate(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.get_strategy = AsyncMock(return_value={
            "id": "sid_existing_1",
            "name": "银行动量策略",
            "author_id": "strategy_factory",
            "strategy_type": "momentum",
            "status": "incubating",
            "params": {"lookback": 8, "threshold": 0.008, "target_symbols": ["601398", "601288", "600036"]},
            "factor_weights": {},
            "tags": ["factory", "momentum"],
        })
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()
        db.save_strategy_generation_experiment = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True, "passed_strict": True}),
        )

        result = await submitter.submit([
            {
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.008},
                "target_symbols": ["601398", "601288", "600036"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036"]},
                "research_task": {"task_source": "event_driven", "event_id": "evt_bank", "theme_code": "high_dividend_banks"},
                "source": "strategy_factory:sector_breakout",
                "spawn_reason": "银行事件刷新",
                "backtest_metrics": {"sharpe_ratio": 0.85, "total_return": 0.07, "max_drawdown": 0.06, "win_rate": 0.55, "trades_count": 14},
                "dedup_result": {"refresh_existing": True, "matched_strategy_id": "sid_existing_1", "matched_status": "incubating"},
            }
        ], {"date": "2026-03-08", "fg_level": "neutral", "fear_greed_index": 55}, db)

        assert result["created"] == 0
        assert result["refreshed"] == 1
        assert result["submitted"] == 1
        assert result["passed_quality_gate"] == 1
        saved_strategy = db.save_strategy.await_args.args[0]
        assert saved_strategy["id"] == "sid_existing_1"
        db.update_strategy_status.assert_not_awaited()
        db.save_strategy_lineage.assert_not_awaited()
        assert result["strategies"][0]["strategy_id"] == "sid_existing_1"
        assert result["strategies"][0]["refreshed_existing"] is True

    @pytest.mark.asyncio
    async def test_submitter_rejects_generic_ai_name_and_low_trade_count(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "D", "total_score": 18.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.8, "cvar_percent": 2.6, "stress_loss_percent": -18.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True, "passed_strict": False, "provisional_pass": True, "reasons": [], "warnings": []}),
        )

        result = await submitter.submit([
            {
                "name": "dsl_rule策略",
                "strategy_type": "dsl_rule",
                "params": {
                    "dsl": {
                        "version": "1.0",
                        "timeframe": "daily",
                        "entry": {"all": [{"op": "cross_above", "left": {"indicator": "ema", "field": "close", "window": 10}, "right": {"indicator": "ema", "field": "close", "window": 30}}]},
                        "exit": {"any": [{"op": "cross_below", "left": {"indicator": "ema", "field": "close", "window": 10}, "right": {"indicator": "ema", "field": "close", "window": 30}}]},
                    }
                },
                "backtest_metrics": {"sharpe_ratio": 0.42, "total_return": 0.09, "max_drawdown": 0.10, "win_rate": 0.5, "trades_count": 2},
                "spawn_reason": "generic_name_and_low_trade",
                "tags": ["factory", "external_llm", "ai_generated", "daily_dsl"],
            }
        ], {"fg_level": "neutral"}, db)

        assert result["passed_quality_gate"] == 0
        assert result["strategies"][0]["passed"] is False
        assert result["strategies"][0]["provisional_pass"] is False
        reasons = result["strategies"][0]["gate_3"]["reasons"]
        assert any("trade_count 2 < 4" in reason for reason in reasons)
        assert any("too generic" in reason for reason in reasons)

    @pytest.mark.asyncio
    async def test_submitter_rejects_event_candidate_on_preference_mismatch_and_target_drift(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "B", "total_score": 66.0}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.2, "cvar_percent": 1.8, "stress_loss_percent": -12.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True, "passed_strict": True, "reasons": [], "warnings": []}),
        )

        result = await submitter.submit([
            {
                "name": "高股息银行动量漂移",
                "strategy_type": "momentum",
                "params": {"lookback": 8, "threshold": 0.01},
                "target_symbols": ["601398", "601288", "600036", "601857", "600941", "601939", "601166", "600000"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036", "601857", "600941", "601939", "601166", "600000"]},
                "research_task": {
                    "task_id": "task_evt_bank",
                    "task_source": "event_driven",
                    "theme_code": "high_dividend_banks",
                    "opportunity_type": "sector_breakout",
                    "strategy_preferences": ["quality_factor", "value_factor", "ma_cross"],
                    "target_symbols": ["601398", "601288", "600036", "601166", "600000"],
                },
                "backtest_metrics": {"sharpe_ratio": 0.71, "total_return": 0.13, "max_drawdown": 0.08, "win_rate": 0.56, "trades_count": 9},
                "spawn_reason": "event_target_drift",
                "tags": ["factory", "ai_generated", "event_driven"],
            }
        ], {"fg_level": "neutral"}, db)

        assert result["passed_quality_gate"] == 0
        reasons = result["strategies"][0]["gate_3"]["reasons"]
        assert any("does not align with task preferences" in reason for reason in reasons)
        assert any("candidate universe drifted" in reason for reason in reasons)

    @pytest.mark.asyncio
    async def test_submitter_rejects_refresh_existing_without_strict_pass(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.get_strategy = AsyncMock(return_value={
            "id": "sid_existing_2",
            "name": "高股息银行均线",
            "author_id": "strategy_factory",
            "strategy_type": "ma_cross",
            "status": "incubating",
            "params": {"short_period": 10, "long_period": 30, "target_symbols": ["601398", "601288", "600036"]},
            "factor_weights": {},
            "tags": ["factory", "ma_cross"],
        })
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()
        db.save_strategy_generation_experiment = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True, "passed_strict": False, "provisional_pass": True, "reasons": [], "warnings": []}),
        )

        result = await submitter.submit([
            {
                "name": "高股息银行均线增强",
                "strategy_type": "ma_cross",
                "params": {"short_period": 10, "long_period": 30},
                "target_symbols": ["601398", "601288", "600036"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "600036"]},
                "backtest_metrics": {"sharpe_ratio": 0.86, "total_return": 0.11, "max_drawdown": 0.07, "win_rate": 0.58, "trades_count": 14},
                "dedup_result": {"refresh_existing": True, "matched_strategy_id": "sid_existing_2", "matched_status": "incubating"},
                "spawn_reason": "refresh_without_strict_pass",
            }
        ], {"date": "2026-03-08", "fg_level": "neutral", "fear_greed_index": 55}, db)

        assert result["refreshed"] == 1
        assert result["passed_quality_gate"] == 0
        assert result["strategies"][0]["passed"] is False
        assert any("requires strict quality gate pass" in reason for reason in result["strategies"][0]["gate_3"]["reasons"])

    @pytest.mark.asyncio
    async def test_submitter_runs_initial_incubation_pipeline(self, monkeypatch):
        submitter = StrategySubmitter()
        db = MagicMock()
        db.save_strategy = AsyncMock()
        db.save_strategy_metrics = AsyncMock()
        db.update_strategy_status = AsyncMock()
        db.save_strategy_lineage = AsyncMock()
        db.save_strategy_quality_report = AsyncMock()
        db.save_strategy_generation_experiment = AsyncMock()

        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_validation_report",
            AsyncMock(return_value={"rating": {"grade": "B", "total_score": 66.0, "recommendation": "Strong"}, "walk_forward": {"oos_rank_ic_mean": 0.05}}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory._run_risk_report",
            AsyncMock(return_value={"var_percent": 1.5, "cvar_percent": 2.1, "stress_loss_percent": -12.0}),
        )
        monkeypatch.setattr(
            "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
            AsyncMock(return_value={"passed": True}),
        )

        class _DummyIncubationService:
            async def ensure_account(self, *_args, **_kwargs):
                return {'account': {'id': 'paper_acc_1'}}

        class _DummyIncubationPipeline:
            async def run_strategy(self, *_args, **_kwargs):
                return {
                    'task_run_id': 88,
                    'snapshot': {
                        'pipeline_stage': 'warmup',
                        'pipeline_status': 'collecting',
                        'readiness_score': 0.42,
                    },
                }

        class _DummyVectorPlatform:
            async def build_strategy_profile(self, *_args, **_kwargs):
                return {'id': 7}

        monkeypatch.setattr('akshare_mcp.services.incubation.get_strategy_incubation_service', lambda: _DummyIncubationService())
        monkeypatch.setattr('akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service', lambda: _DummyIncubationPipeline())
        monkeypatch.setattr('akshare_mcp.services.vector_platform.get_strategy_vector_platform', lambda: _DummyVectorPlatform())

        result = await submitter.submit([
            {
                'strategy_type': 'momentum',
                'params': {'lookback': 20, 'threshold': 0.02},
                'backtest_metrics': {'sharpe_ratio': 1.1, 'total_return': 0.2, 'max_drawdown': 0.12, 'win_rate': 0.55, 'trades_count': 8},
                'spawn_reason': '测试提交',
                'experiment_id': 'exp_1',
                'generator_type': 'external_llm',
                'llm_response': {'provider': 'openai_compatible', 'model': 'test-model'},
            }
        ], {'date': '2026-03-08', 'fg_level': 'neutral'}, db)

        assert result['passed_quality_gate'] == 1
        assert result['strategies'][0]['incubation_pipeline_stage'] == 'warmup'
        assert result['strategies'][0]['incubation_pipeline_status'] == 'collecting'
        assert result['strategies'][0]['incubation_task_run_id'] == 88
