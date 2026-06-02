from __future__ import annotations

import asyncio
from types import SimpleNamespace


class _EmptyConfirmationProvider:
    def is_enabled(self):
        return True

    async def call_stage(self, **kwargs):
        return {"confirmations": []}


class _BadJsonProvider:
    def is_enabled(self):
        return True

    async def call_stage(self, **kwargs):
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMRequestError

        raise StrategyLLMRequestError(
            "call_stage(market_confirmation) failed after repair",
            metrics={
                "stage_id": "market_confirmation",
                "status": "failed",
                "last_error_type": "StrategyLLMResponseParseError",
                "last_error": "response content is not valid JSON",
                "attempts": [
                    {
                        "status": "failed",
                        "error_type": "StrategyLLMResponseParseError",
                        "error": "response content is not valid JSON",
                    }
                ],
            },
        )


class _FakeDb:
    async def get_klines(self, symbol, limit=30):
        return [
            {"close": 10.0},
            {"close": 10.2},
            {"close": 10.4},
            {"close": 10.8},
            {"close": 11.1},
            {"close": 11.4},
        ]


class _EnabledProvider:
    config = SimpleNamespace(provider="test", model="test-model", strict=False)

    def is_enabled(self):
        return True


class _NoFallbackMiner:
    def generate_factor_candidates(self, *args, **kwargs):
        raise AssertionError("local factor miner must not run after staged pipeline suppression")


class _NoFallbackRuleGenerator:
    def generate(self, *args, **kwargs):
        from akshare_mcp.services.strategy_spec import StrategySpec

        return [
            StrategySpec(
                strategy_type="ma_cross",
                params={"short_period": 5, "long_period": 20},
                name="rule should be suppressed",
                metadata={"generator_type": "rule"},
            )
        ]


class _SuppressedLLMGenerator:
    replay_called = False

    async def generate(self, *args, **kwargs):
        return []

    def get_last_report(self):
        return {
            "post_pipeline_fallback_suppressed": True,
            "post_pipeline_suppression_reason": "provider_output_format_failure",
            "external_provider": {
                "status": "failed_output_format",
                "monolithic_fallback_suppressed": True,
                "local_fallback_suppressed": True,
            },
            "local_generator": {
                "status": "skipped_after_pipeline_failure",
                "local_fallback_suppressed": True,
            },
        }

    async def replay_persisted_specs(self, *args, **kwargs):
        self.replay_called = True
        raise AssertionError("hypothesis replay must not run after staged pipeline suppression")


class _NoFallbackOptimizer:
    evolve_called = False

    async def evolve(self, *args, **kwargs):
        self.evolve_called = True
        raise AssertionError("optimizer must not run after staged pipeline suppression")


def test_market_confirmation_empty_output_records_explainable_fallback():
    from akshare_mcp.services.strategy_pipeline import MultiStageStrategyPipeline
    from akshare_mcp.services.strategy_stages import get_stage_registry

    pipeline = MultiStageStrategyPipeline(provider=_EmptyConfirmationProvider())
    stage_result = asyncio.run(
        pipeline.run_stage(
            db=_FakeDb(),
            stage_id="market_confirmation",
            input_data={
                "research_task": {
                    "target_symbols": ["600000"],
                    "candidate_family": "value_factor",
                }
            },
            snapshot={},
            stage_def=get_stage_registry()["market_confirmation"],
        )
    )

    assert stage_result.used_fallback is True
    assert stage_result.output["confirmations"]
    assert stage_result.llm_error_metrics["validation_failure_reason"] == "empty_confirmations"
    assert stage_result.llm_error_metrics["output_keys"] == ["confirmations"]


def test_stage_provider_format_failure_suppresses_local_fallback():
    from akshare_mcp.services.strategy_pipeline import MultiStageStrategyPipeline
    from akshare_mcp.services.strategy_stages import get_stage_registry

    pipeline = MultiStageStrategyPipeline(provider=_BadJsonProvider())
    stage_result = asyncio.run(
        pipeline.run_stage(
            db=_FakeDb(),
            stage_id="market_confirmation",
            input_data={
                "research_task": {
                    "target_symbols": ["600000"],
                    "candidate_family": "value_factor",
                }
            },
            snapshot={},
            stage_def=get_stage_registry()["market_confirmation"],
        )
    )

    assert stage_result.used_fallback is False
    assert stage_result.output == {}
    assert stage_result.error == "llm output format failed for market_confirmation"
    assert stage_result.llm_error_metrics["local_fallback_suppressed"] is True
    assert stage_result.llm_error_metrics["suppression_reason"] == "provider_output_format_failure"


def test_generator_suppresses_monolithic_and_local_fallback_after_bad_staged_output(monkeypatch):
    import pandas as pd

    import akshare_mcp.services._strategy_generators_generate as generate_module
    import akshare_mcp.services.strategy_generators as public_generators
    from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator
    from akshare_mcp.services.strategy_pipeline import PipelineResult
    from akshare_mcp.services.strategy_stages import StageResult

    class _BadOutputPipeline:
        async def run_pipeline(self, **kwargs):
            return PipelineResult(
                stages={
                    "market_confirmation": StageResult(
                        stage_id="market_confirmation",
                        output={},
                        used_fallback=False,
                        llm_attempted=True,
                        prompt_chars=12,
                        response_chars=21,
                        elapsed_sec=0.01,
                        error="llm output format failed for market_confirmation",
                        llm_error="response content is not valid JSON",
                        llm_error_type="StrategyLLMResponseParseError",
                        llm_error_metrics={
                            "status": "failed",
                            "local_fallback_suppressed": True,
                            "suppression_reason": "provider_output_format_failure",
                        },
                    )
                },
                candidates=[],
                elapsed_sec=0.01,
            )

    monkeypatch.delenv("STRATEGY_FACTORY_ALLOW_PIPELINE_EMPTY_MONOLITHIC_FALLBACK", raising=False)
    monkeypatch.setattr(public_generators, "PIPELINE_MODE", "staged", raising=False)
    monkeypatch.setattr(generate_module, "PIPELINE_MODE", "staged", raising=False)
    monkeypatch.setattr(public_generators, "get_strategy_pipeline", lambda: _BadOutputPipeline(), raising=False)

    generator = LLMProxyStrategyGenerator()
    generator.external_provider = _EnabledProvider()
    generator.miner = _NoFallbackMiner()

    async def _recent_experiments(*args, **kwargs):
        return []

    async def _build_research_context(*args, **kwargs):
        return {"task_target_context": {}, "blocked_by_target_universe": False}

    async def _build_market_frame(*args, **kwargs):
        return pd.DataFrame({"close": [10.0, 10.2, 10.4], "volume": [1000, 1100, 1200]})

    async def _build_symbol_frame_cache(*args, **kwargs):
        return {}

    async def _run_external_provider_request(*args, **kwargs):
        raise AssertionError("monolithic external provider must not run after staged suppression")

    monkeypatch.setattr(generator, "_recent_experiments", _recent_experiments)
    monkeypatch.setattr(generator, "_build_research_context", _build_research_context)
    monkeypatch.setattr(generator, "_build_market_frame", _build_market_frame)
    monkeypatch.setattr(generator, "_build_symbol_frame_cache", _build_symbol_frame_cache)
    monkeypatch.setattr(generator, "_run_external_provider_request", _run_external_provider_request)

    specs = asyncio.run(
        generator.generate(
            _FakeDb(),
            limit=2,
            snapshot={},
            parent_strategies=[],
            research_task={"target_symbols": ["600000"], "allowed_strategy_types": ["dsl_rule"]},
        )
    )

    report = generator.get_last_report()
    requests = report["pipeline_staged_provenance"]["stages"]["market_confirmation"]["llm_error_metrics"]
    assert specs == []
    assert report["post_pipeline_fallback_suppressed"] is True
    assert report["post_pipeline_suppression_reason"] == "provider_output_format_failure"
    assert report["external_provider"]["monolithic_fallback_suppressed"] is True
    assert report["external_provider"]["local_fallback_suppressed"] is True
    assert report["local_generator"]["local_fallback_suppressed"] is True
    assert requests["local_fallback_suppressed"] is True


def test_generator_skips_monolithic_but_keeps_local_fallback_after_empty_pipeline(monkeypatch):
    import pandas as pd

    import akshare_mcp.services._strategy_generators_generate as generate_module
    import akshare_mcp.services.strategy_generators as public_generators
    from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator
    from akshare_mcp.services.strategy_pipeline import PipelineResult
    from akshare_mcp.services.strategy_spec import StrategySpec
    from akshare_mcp.services.strategy_stages import StageResult

    class _EmptyPipeline:
        async def run_pipeline(self, **kwargs):
            return PipelineResult(
                stages={
                    "strategy_generation": StageResult(
                        stage_id="strategy_generation",
                        output={"candidates": []},
                        used_fallback=True,
                        llm_attempted=True,
                        prompt_chars=12,
                        response_chars=21,
                        elapsed_sec=0.01,
                        error="no executable candidates",
                        llm_error_metrics={
                            "status": "non_executable",
                            "validation_failure_reason": "empty_candidates",
                        },
                    )
                },
                candidates=[],
                elapsed_sec=0.01,
            )

    class _LocalFallbackMiner:
        called = False

        def generate_factor_candidates(self, *args, **kwargs):
            self.called = True
            return [
                {
                    "name": "local momentum fallback",
                    "description": "local candidate",
                    "formula": "close / close.shift(20) - 1",
                    "category": "momentum",
                    "rationale": "pipeline empty fallback",
                    "_engine": "local_rule_v1",
                }
            ]

    monkeypatch.setenv("STRATEGY_FACTORY_ALLOW_PIPELINE_EMPTY_MONOLITHIC_FALLBACK", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_PIPELINE_EMPTY_SKIP_MONOLITHIC_FALLBACK", "1")
    monkeypatch.setattr(public_generators, "PIPELINE_MODE", "staged", raising=False)
    monkeypatch.setattr(generate_module, "PIPELINE_MODE", "staged", raising=False)
    monkeypatch.setattr(public_generators, "get_strategy_pipeline", lambda: _EmptyPipeline(), raising=False)

    generator = LLMProxyStrategyGenerator()
    generator.external_provider = _EnabledProvider()
    generator.miner = _LocalFallbackMiner()

    async def _recent_experiments(*args, **kwargs):
        return []

    async def _build_research_context(*args, **kwargs):
        return {"task_target_context": {}, "blocked_by_target_universe": False}

    async def _build_market_frame(*args, **kwargs):
        return pd.DataFrame({"close": [10.0, 10.2, 10.4], "volume": [1000, 1100, 1200]})

    async def _build_symbol_frame_cache(*args, **kwargs):
        return {}

    async def _run_external_provider_request(*args, **kwargs):
        raise AssertionError("monolithic external provider must not run after empty staged pipeline")

    def _local_candidate_to_spec(candidate, research_task=None):
        return StrategySpec(
            strategy_type="momentum",
            params={"lookback": 20, "threshold": 0.02},
            name=str(candidate.get("name") or "local fallback"),
            metadata={"generator_type": "local_rule_v1"},
        )

    monkeypatch.setattr(generator, "_recent_experiments", _recent_experiments)
    monkeypatch.setattr(generator, "_build_research_context", _build_research_context)
    monkeypatch.setattr(generator, "_build_market_frame", _build_market_frame)
    monkeypatch.setattr(generator, "_build_symbol_frame_cache", _build_symbol_frame_cache)
    monkeypatch.setattr(generator, "_run_external_provider_request", _run_external_provider_request)
    monkeypatch.setattr(generator, "_local_candidate_to_spec", _local_candidate_to_spec)

    specs = asyncio.run(
        generator.generate(
            _FakeDb(),
            limit=2,
            snapshot={},
            parent_strategies=[],
            research_task={"target_symbols": ["600000"], "allowed_strategy_types": ["momentum"]},
        )
    )

    report = generator.get_last_report()
    assert len(specs) == 1
    assert generator.miner.called is True
    assert report["post_pipeline_fallback_suppressed"] is False
    assert report["post_pipeline_suppression_reason"] is None
    assert report["external_provider"]["status"] == "skipped_after_pipeline_empty"
    assert report["external_provider"]["monolithic_external_provider_skipped"] is True
    assert report["external_provider"]["monolithic_external_provider_skip_reason"] == "staged_pipeline_empty"
    assert "monolithic_fallback_suppressed" not in report["external_provider"]
    assert "local_fallback_suppressed" not in report["external_provider"]
    assert report["local_generator"]["status"] == "succeeded"
    assert report["selected_generators"]["local_rule_v1"] == 1


def test_candidate_generation_suppresses_rule_replay_and_optimizer_fallbacks():
    from akshare_mcp.services.strategy_autonomy_components import CandidateGenerationService

    llm_generator = _SuppressedLLMGenerator()
    optimizer = _NoFallbackOptimizer()
    service = CandidateGenerationService(
        rule_generator=_NoFallbackRuleGenerator(),
        llm_generator=llm_generator,
        optimizer=optimizer,
    )

    result = asyncio.run(
        service.generate(
            _FakeDb(),
            snapshot={
                "fear_greed_index": 50,
                "_shared_generation_context": {
                    "parent_strategies": [{"id": "parent_1"}],
                    "history_summary": [{"experiment_id": "old"}],
                },
            },
            limit=3,
            research_task={"target_symbols": ["600000"], "candidate_family": "ma_cross"},
        )
    )

    assert result["rule_specs"] == []
    assert result["replay_specs"] == []
    assert result["evolved_specs"] == []
    assert result["merged_specs"] == []
    assert result["llm_report"]["candidate_fallback_suppressed"] is True
    assert result["llm_report"]["replay_provider"]["status"] == "skipped_after_llm_failure"
    assert result["llm_report"]["optimizer"]["status"] == "skipped_after_llm_failure"
    assert llm_generator.replay_called is False
    assert optimizer.evolve_called is False
