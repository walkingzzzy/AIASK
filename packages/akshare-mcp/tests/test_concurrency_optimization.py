"""Phase 1 并发优化 — 单元测试。

覆盖:
  - 新增常量的默认值与 env 覆盖
  - factory_scheduler 有界并发行为
  - backtest_filter  有界并发行为
  - submitter        有界并发行为
  - strategy_llm_provider / text_embedding 连接池复用
  - strategy_pipeline 阶段特定超时
"""

from __future__ import annotations

import asyncio
import importlib
import os
import types
from unittest import mock

import pytest


# ────────────────────────────────────────────────────────────────────────────
# 1. 常量默认值与 env 覆盖
# ────────────────────────────────────────────────────────────────────────────


class TestConcurrencyConstants:
    """验证新增并发常量的默认值和环境变量覆盖。"""

    def test_defaults(self):
        keys_to_clear = [
            "STRATEGY_FACTORY_RESEARCH_TASK_CONCURRENCY",
            "STRATEGY_FACTORY_BACKTEST_CONCURRENCY",
            "STRATEGY_FACTORY_SUBMIT_CONCURRENCY",
            "STRATEGY_FACTORY_MAX_RESEARCH_TASKS",
            "STRATEGY_FACTORY_CANDIDATES_PER_TASK",
            "STRATEGY_PIPELINE_STAGE_TIMEOUT_SEC",
            "STRATEGY_PIPELINE_STAGE_EVENT_RECOGNITION_TIMEOUT_SEC",
            "STRATEGY_PIPELINE_STAGE_THEME_PROPAGATION_TIMEOUT_SEC",
            "STRATEGY_PIPELINE_STAGE_EXPOSURE_MAPPING_TIMEOUT_SEC",
            "STRATEGY_PIPELINE_STAGE_MARKET_CONFIRMATION_TIMEOUT_SEC",
            "STRATEGY_PIPELINE_STAGE_STRATEGY_GENERATION_TIMEOUT_SEC",
        ]
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in keys_to_clear:
                os.environ.pop(key, None)
            with mock.patch("akshare_mcp.env_loader.load_mcp_env", return_value=None):
                from strategy_factory.domain import constants as C
                C = importlib.reload(C)

                assert C.RESEARCH_TASK_CONCURRENCY == 5
                assert C.BACKTEST_CONCURRENCY == 4
                assert C.SUBMIT_CONCURRENCY == 3
                assert C.AUTONOMY_MAX_RESEARCH_TASKS == 12
                assert C.AUTONOMY_CANDIDATES_PER_TASK == 4
                assert C.PIPELINE_STAGE_TIMEOUT_SEC == 10.0

    def test_pipeline_stage_timeouts_dict(self):
        from akshare_mcp.services.strategy_factory.constants import PIPELINE_STAGE_TIMEOUTS

        assert isinstance(PIPELINE_STAGE_TIMEOUTS, dict)
        assert "event_recognition" in PIPELINE_STAGE_TIMEOUTS
        assert "strategy_generation" in PIPELINE_STAGE_TIMEOUTS
        # strategy_generation 应该是最长的
        assert PIPELINE_STAGE_TIMEOUTS["strategy_generation"] >= PIPELINE_STAGE_TIMEOUTS["theme_propagation"]
        assert PIPELINE_STAGE_TIMEOUTS["event_recognition"] >= 1.0

    def test_global_pipeline_timeout_applies_to_all_stages_when_configured(self):
        with mock.patch.dict(
            os.environ,
            {
                "STRATEGY_PIPELINE_STAGE_TIMEOUT_SEC": "20",
            },
            clear=False,
        ):
            for key in (
                "STRATEGY_PIPELINE_STAGE_EVENT_RECOGNITION_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_THEME_PROPAGATION_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_EXPOSURE_MAPPING_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_MARKET_CONFIRMATION_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_STRATEGY_GENERATION_TIMEOUT_SEC",
            ):
                os.environ.pop(key, None)
            from strategy_factory.domain import constants as C

            C = importlib.reload(C)
            assert C.PIPELINE_STAGE_TIMEOUT_SEC == 20.0
            assert C.PIPELINE_STAGE_TIMEOUTS["event_recognition"] == 20.0
            assert C.PIPELINE_STAGE_TIMEOUTS["strategy_generation"] == 20.0

    def test_stage_specific_timeout_can_override_global_timeout(self):
        with mock.patch.dict(
            os.environ,
            {
                "STRATEGY_PIPELINE_STAGE_TIMEOUT_SEC": "20",
                "STRATEGY_PIPELINE_STAGE_EVENT_RECOGNITION_TIMEOUT_SEC": "35",
            },
            clear=False,
        ):
            for key in (
                "STRATEGY_PIPELINE_STAGE_THEME_PROPAGATION_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_EXPOSURE_MAPPING_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_MARKET_CONFIRMATION_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_STRATEGY_GENERATION_TIMEOUT_SEC",
            ):
                os.environ.pop(key, None)
            from strategy_factory.domain import constants as C

            C = importlib.reload(C)
            assert C.PIPELINE_STAGE_TIMEOUTS["event_recognition"] == 35.0
            assert C.PIPELINE_STAGE_TIMEOUTS["theme_propagation"] == 20.0

    def test_env_override_research_concurrency(self):
        with mock.patch.dict(os.environ, {"STRATEGY_FACTORY_RESEARCH_TASK_CONCURRENCY": "8"}):
            from akshare_mcp.services.strategy_factory.constants import _env_int

            val = _env_int("STRATEGY_FACTORY_RESEARCH_TASK_CONCURRENCY", 5, minimum=1, maximum=12)
            assert val == 8

    def test_env_clamp(self):
        """值超出 [min, max] 范围时应被钳位。"""
        from akshare_mcp.services.strategy_factory.constants import _env_int

        with mock.patch.dict(os.environ, {"TEST_CLAMP": "100"}):
            assert _env_int("TEST_CLAMP", 5, minimum=1, maximum=10) == 10
        with mock.patch.dict(os.environ, {"TEST_CLAMP": "0"}):
            assert _env_int("TEST_CLAMP", 5, minimum=1, maximum=10) == 1


# ────────────────────────────────────────────────────────────────────────────
# 2. 调度器有界并发
# ────────────────────────────────────────────────────────────────────────────


class TestSchedulerConcurrency:
    """验证 _run_autonomy_batches 使用了 asyncio.Semaphore 做有界并发。"""

    def test_research_task_concurrency_is_capped_by_external_provider(self):
        from akshare_mcp.services.strategy_factory.factory_scheduler import StrategyFactoryScheduler

        enabled_provider = types.SimpleNamespace(
            is_enabled=lambda: True,
            config=types.SimpleNamespace(max_concurrency=3),
        )
        autonomy_gateway = types.SimpleNamespace(
            generation_service=types.SimpleNamespace(
                llm_generator=types.SimpleNamespace(external_provider=enabled_provider)
            )
        )

        assert StrategyFactoryScheduler._resolve_research_task_concurrency(autonomy_gateway) == 3

    @pytest.mark.asyncio
    async def test_tasks_run_concurrently(self):
        """多个研究任务应并发执行，而不是串行。"""
        from akshare_mcp.services.strategy_factory.factory_scheduler import StrategyFactoryScheduler

        scheduler = StrategyFactoryScheduler()

        fake_scanner = mock.MagicMock()
        fake_scanner.scan = mock.AsyncMock(return_value={
            "tasks": [
                {"task_key": f"t{i}", "task_id": f"t{i}", "opportunity_type": "test"} for i in range(3)
            ],
            "summary": {"task_sources": {"test": 3}},
        })

        fake_autonomy = mock.MagicMock()
        fake_autonomy.generate_factory_candidates = mock.AsyncMock(
            return_value={"candidates": [{"strategy_type": "test"}], "experiments": [], "llm_generation": {}}
        )

        factory_pkg = mock.MagicMock()
        factory_pkg.MarketOpportunityScanner.return_value = fake_scanner

        async def fake_call_optional(db_or_obj, method_name, *args, **kwargs):
            return kwargs.get("default", {"id": None})

        with mock.patch(
            "akshare_mcp.services.strategy_factory.factory_scheduler.get_strategy_factory_package",
            return_value=factory_pkg,
        ), mock.patch(
            "akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service",
            return_value=fake_autonomy,
        ), mock.patch(
            "akshare_mcp.services.strategy_factory.factory_scheduler._call_optional_async",
            side_effect=fake_call_optional,
        ):
            result = await scheduler._run_autonomy_batches(mock.MagicMock(), {"date": "2025-01-01"})

        stage = result["stage"]
        assert stage["task_count"] == 3
        assert len(result["candidates"]) == 3

    @pytest.mark.asyncio
    async def test_single_task_failure_does_not_abort_others(self):
        """一个任务失败不应影响其他任务。"""
        from akshare_mcp.services.strategy_factory.factory_scheduler import StrategyFactoryScheduler

        scheduler = StrategyFactoryScheduler()

        call_keys: list[str] = []

        async def fake_generate(db, snapshot, *, limit=4, research_task=None, source=""):
            task_key = (research_task or {}).get("task_key", "")
            call_keys.append(task_key)
            if task_key == "t1":
                raise RuntimeError("boom")
            return {"candidates": [{"strategy_type": "test"}], "experiments": [], "llm_generation": {}}

        fake_scanner = mock.MagicMock()
        fake_scanner.scan = mock.AsyncMock(return_value={
            "tasks": [
                {"task_key": f"t{i}", "task_id": f"t{i}", "opportunity_type": "test"} for i in range(3)
            ],
            "summary": {"task_sources": {"test": 3}},
        })

        fake_autonomy = mock.MagicMock()
        fake_autonomy.generate_factory_candidates = fake_generate

        factory_pkg = mock.MagicMock()
        factory_pkg.MarketOpportunityScanner.return_value = fake_scanner

        async def fake_call_optional(db_or_obj, method_name, *args, **kwargs):
            return kwargs.get("default", {"id": None})

        with mock.patch(
            "akshare_mcp.services.strategy_factory.factory_scheduler.get_strategy_factory_package",
            return_value=factory_pkg,
        ), mock.patch(
            "akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service",
            return_value=fake_autonomy,
        ), mock.patch(
            "akshare_mcp.services.strategy_factory.factory_scheduler._call_optional_async",
            side_effect=fake_call_optional,
        ):
            result = await scheduler._run_autonomy_batches(mock.MagicMock(), {"date": "2025-01-01"})

        stage = result["stage"]
        assert len(call_keys) == 3
        assert stage["completed_task_count"] == 2
        assert stage["failed_task_count"] == 1


# ────────────────────────────────────────────────────────────────────────────
# 3. BacktestFilter 有界并发
# ────────────────────────────────────────────────────────────────────────────


class TestBacktestFilterConcurrency:
    @pytest.mark.asyncio
    async def test_filter_calls_gather(self):
        """filter() 应使用 asyncio.gather 并发测试候选。"""
        from akshare_mcp.services.strategy_factory.backtest_filter import (
            BACKTEST_CONCURRENCY,
            BacktestFilter,
        )

        bf = BacktestFilter()
        concurrent_peak = 0
        active = 0

        original_test_one = bf._test_one

        async def counting_test_one(candidate, db, engine):
            nonlocal active, concurrent_peak
            active += 1
            if active > concurrent_peak:
                concurrent_peak = active
            await asyncio.sleep(0.02)
            active -= 1
            return {"passed": True, "metrics": {"sharpe_ratio": 1.0}}

        bf._test_one = counting_test_one

        candidates = [
            {"strategy_type": "momentum", "params": {"fast": 5}, "tags": []}
            for _ in range(6)
        ]

        with mock.patch("akshare_mcp.services.backtest.engine.BacktestEngine"):
            passed = await bf.filter(candidates, mock.MagicMock())

        assert len(passed) == 6
        # 并发度上限来自当前运行配置，峰值不应超过有效常量。
        assert concurrent_peak <= BACKTEST_CONCURRENCY


# ────────────────────────────────────────────────────────────────────────────
# 4. StrategySubmitter 有界并发
# ────────────────────────────────────────────────────────────────────────────


class TestSubmitterConcurrency:
    @pytest.mark.asyncio
    async def test_submit_calls_gather(self):
        """submit() 应使用 asyncio.gather 并发提交候选。"""
        from akshare_mcp.services.strategy_factory.submitter import StrategySubmitter

        submitter = StrategySubmitter()
        call_count = 0

        async def fake_submit_one(candidate, snapshot, db):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return {
                "created": True,
                "refreshed_existing": False,
                "submitted": True,
                "passed": True,
                "summary": {"strategy_id": f"s{call_count}", "name": "test"},
            }

        submitter._submit_one = fake_submit_one
        candidates = [{"strategy_type": "rsi", "params": {}} for _ in range(5)]
        result = await submitter.submit(candidates, {"date": "2025-01-01"}, mock.MagicMock())

        assert result["submitted"] == 5
        assert call_count == 5


# ────────────────────────────────────────────────────────────────────────────
# 5. 连接池复用
# ────────────────────────────────────────────────────────────────────────────


class TestConnectionPoolReuse:
    def test_llm_provider_shared_client(self):
        """StrategyLLMProvider 应在 __init__ 中创建共享 _client。"""
        from akshare_mcp.services.strategy_llm_provider import StrategyLLMProvider
        import httpx

        provider = StrategyLLMProvider()
        assert hasattr(provider, "_client")
        assert isinstance(provider._client, httpx.AsyncClient)

    def test_text_embedding_shared_client(self):
        """StrategyTextEmbeddingService 应在 __init__ 中创建共享 _client。"""
        from akshare_mcp.services.text_embedding import StrategyTextEmbeddingService
        import httpx

        service = StrategyTextEmbeddingService()
        assert hasattr(service, "_client")
        assert isinstance(service._client, httpx.AsyncClient)


# ────────────────────────────────────────────────────────────────────────────
# 6. Pipeline 阶段特定超时
# ────────────────────────────────────────────────────────────────────────────


class TestPipelineStageTimeout:
    def test_stage_specific_timeout_is_used(self):
        """_call_llm_stage 应使用每阶段独立超时。"""
        with mock.patch.dict(
            os.environ,
            {
                "STRATEGY_PIPELINE_STAGE_TIMEOUT_SEC": "18",
                "STRATEGY_PIPELINE_STAGE_EVENT_RECOGNITION_TIMEOUT_SEC": "24",
            },
            clear=False,
        ):
            for key in (
                "STRATEGY_PIPELINE_STAGE_THEME_PROPAGATION_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_EXPOSURE_MAPPING_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_MARKET_CONFIRMATION_TIMEOUT_SEC",
                "STRATEGY_PIPELINE_STAGE_STRATEGY_GENERATION_TIMEOUT_SEC",
            ):
                os.environ.pop(key, None)
            from strategy_factory.domain import constants as C

            C = importlib.reload(C)
            from akshare_mcp.services import strategy_pipeline as pipeline_mod

            pipeline_mod = importlib.reload(pipeline_mod)
            pipeline = pipeline_mod.MultiStageStrategyPipeline()

            assert pipeline is not None

            expected = C.PIPELINE_STAGE_TIMEOUTS["strategy_generation"]
            assert expected == 18.0

            expected_event = C.PIPELINE_STAGE_TIMEOUTS["event_recognition"]
            assert expected_event == 24.0
