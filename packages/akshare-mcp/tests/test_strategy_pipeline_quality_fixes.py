from __future__ import annotations

import asyncio


class _EmptyConfirmationProvider:
    def is_enabled(self):
        return True

    async def call_stage(self, **kwargs):
        return {"confirmations": []}


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
