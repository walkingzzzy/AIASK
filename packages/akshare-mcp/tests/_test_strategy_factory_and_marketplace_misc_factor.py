from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class TestDataCollector:
    @pytest.mark.asyncio
    async def test_collect_returns_structured_snapshot_when_partially_degraded(self):
        """部分数据源失败时应返回结构化完整性摘要"""
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(60))
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 12})

        async def _factor_ic_side_effect(fname, *_args):
            if fname == "quality":
                raise Exception("quality unavailable")
            return [{"ic_value": 0.12}] * 10

        async def _count_by_type(status):
            if status == "listed":
                return {"momentum": 2, "value_factor": 1}
            return {"momentum": 1}

        db.get_factor_ic_history = AsyncMock(side_effect=_factor_ic_side_effect)
        db.count_strategies_by_type = AsyncMock(side_effect=_count_by_type)
        db.save_daily_snapshot = AsyncMock()

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 61, "level": "greed", "components": {"breadth": 70}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 20}, {"total": 30}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "AI", "mainNetInflow": 2},
                    {"name": "券商", "mainNetInflow": 1},
                    {"name": "煤炭", "mainNetInflow": -1},
                    {"name": "地产", "mainNetInflow": -2},
                ]},
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["summary"]["listed_count"] == 3
        assert snapshot["summary"]["degraded"] is True
        assert snapshot["completeness"]["completion_ratio"] < 1.0
        assert snapshot["source"] == "strategy_factory.collector"
        assert snapshot["asof_time"]
        assert snapshot["freshness_sec"] >= 0
        assert "degraded" in snapshot["quality_flags"]
        assert "incomplete" in snapshot["quality_flags"]
        assert snapshot["sources"]["factor_ic"]["status"] == "partial"
        assert snapshot["sources"]["factor_ic"]["source"] == "factor_ic"
        assert snapshot["sources"]["factor_ic"]["asof_time"] == snapshot["asof_time"]
        assert snapshot["sources"]["factor_ic"]["freshness_sec"] >= 0
        assert "partial" in snapshot["sources"]["factor_ic"]["quality_flags"]
        assert snapshot["degraded"] is True
        assert any(item["source"] == "factor_ic" for item in snapshot["failure_reasons"])
        db.save_daily_snapshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collect_marks_empty_factor_history_as_fallback(self):
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(60))
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 12})
        db.get_factor_ic_history = AsyncMock(return_value=[])
        db.count_strategies_by_type = AsyncMock(side_effect=lambda status: {"momentum": 2} if status == "listed" else {"momentum": 1})
        db.save_daily_snapshot = AsyncMock()

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 61, "level": "greed", "components": {"breadth": 70}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 20}, {"total": 30}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "AI", "mainNetInflow": 2},
                    {"name": "券商", "mainNetInflow": 1},
                    {"name": "煤炭", "mainNetInflow": -1},
                    {"name": "地产", "mainNetInflow": -2},
                ]},
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["factor_ic"] == {}
        assert snapshot["factor_ic_trend"] == {}
        assert snapshot["sources"]["factor_ic"]["status"] == "fallback"
        assert snapshot["degraded"] is True
        assert snapshot["completeness"]["is_complete"] is False
        assert "factor_ic" in snapshot["completeness"]["missing_sources"]
        assert any(item["source"] == "factor_ic" and item["fallback_used"] for item in snapshot["failure_reasons"])
        db.save_daily_snapshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collect_with_all_failures_still_returns_snapshot(self):
        """所有外部数据源失败时仍应返回有效快照"""
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=[])
        db.get_limit_up_stats = AsyncMock(side_effect=Exception("no data"))
        db.get_factor_ic_history = AsyncMock(side_effect=Exception("no data"))
        db.count_strategies_by_type = AsyncMock(return_value={})
        db.save_daily_snapshot = AsyncMock()
        # north_fund DB 路径也需要失败
        db.acquire = MagicMock(side_effect=Exception("db unavailable"))

        with patch("akshare_mcp.services.strategy_factory.asyncio.to_thread",
                   side_effect=Exception("network error")), \
             patch("akshare_mcp.tools.market.kline.get_index_kline",
                   new_callable=AsyncMock,
                   return_value={"success": False, "data": []}):
            snapshot = await collector.collect(db)

        assert "date" in snapshot
        assert "fear_greed_index" in snapshot
        assert snapshot["fear_greed_index"] == 50  # fallback
        assert snapshot["north_fund_3d_net"] == 0.0
        assert isinstance(snapshot["category_counts"], dict)
        assert snapshot["degraded"] is True
        assert snapshot["completeness"]["is_complete"] is False
        assert "north_fund_3d_net" in snapshot["missing_fields"]
        assert snapshot["sources"]["fear_greed"]["status"] == "fallback"
        assert len(snapshot["failure_reasons"]) >= 4
        db.save_daily_snapshot.assert_awaited_once()


class TestFactorSchedulerAndBatchFactors:
    def test_factor_scheduler_defaults_align_with_strategy_factory_consumption(self):
        from akshare_mcp.services.factor_scheduler import DEFAULT_FACTORS

        assert "reversal" in DEFAULT_FACTORS
        assert "liquidity" not in DEFAULT_FACTORS

    @pytest.mark.asyncio
    async def test_batch_compute_factors_supports_reversal(self, monkeypatch):
        from akshare_mcp.tools.managers.quant_manager import quant_manager

        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(80, base=20.0, trend=-0.01, noise=0.001))
        db.get_financials = AsyncMock(return_value=[])
        db.save_factor_values = AsyncMock()
        monkeypatch.setattr("akshare_mcp.tools.managers.quant_manager.get_db", lambda: db)

        result = await quant_manager(
            action="batch_compute_factors",
            kwargs=json.dumps({
                "codes": ["000001"],
                "factors": ["reversal"],
                "persist": True,
                "compute_ic": False,
            }),
        )

        assert result["success"] is True
        assert result["data"]["computed_count"] == 1
        assert result["data"]["factors"] == ["reversal"]
        saved_values = db.save_factor_values.await_args.args[2]
        assert "reversal" in saved_values
        assert "liquidity" not in saved_values

    @pytest.mark.asyncio
    async def test_factor_scheduler_run_once_can_import_quant_manager(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        calls = []
        monkeypatch.setenv("FACTOR_LLM_ENABLED", "0")
        monkeypatch.setenv("FACTOR_SCHEDULER_LLM_MINING", "0")

        async def _fake_quant_manager(*, action, code=None, **kwargs):
            calls.append({"action": action, "code": code, "kwargs": kwargs})
            payload = json.loads(kwargs["kwargs"])
            assert payload["factors"] == ["reversal"]
            assert payload["persist"] is True
            assert payload["compute_ic"] is True
            return {"success": True, "data": {"computed_count": 1, "error_count": 0}}

        monkeypatch.setattr(
            quant_manager_module,
            "quant_manager",
            _fake_quant_manager,
        )

        scheduler = FactorScheduler(universe=["000001", "000002"], factors=["reversal"], batch_size=1)
        result = await scheduler.run_once()

        assert result["computed"] == 2
        assert result["errors"] == 0
        assert result["universe_size"] == 2
        assert result["source"] == "factor_scheduler"
        assert result["asof_time"]
        assert result["freshness_sec"] >= 0
        assert result["quality_flags"] == []
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_factor_scheduler_run_once_records_workflow_stages_and_history(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        monkeypatch.setenv("FACTOR_LLM_ENABLED", "1")
        monkeypatch.setenv("FACTOR_SCHEDULER_LLM_MINING", "1")
        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: MagicMock())

        async def _fake_quant_manager(*, action, code=None, **kwargs):
            del code
            payload = json.loads(kwargs["kwargs"])
            if action == "batch_compute_factors":
                return {"success": True, "data": {"computed_count": len(payload.get("codes") or []), "error_count": 0}}
            if action == "llm_factor_mining":
                return {
                    "success": True,
                    "data": {
                        "artifact_id": "factor_llm_scheduler_workflow_case",
                        "codes": ["000001", "000002", "000333", "600519"],
                        "candidate_count": 1,
                        "candidates": [
                            {"name": "workflow_candidate", "family": "momentum", "formula": "rank(close / delay(close, 20))"},
                        ],
                    },
                }
            if action == "validate_factor_candidate":
                return {"success": True, "data": {"artifact_id": payload["output_artifact_id"]}}
            if action == "factor_candidate_registry" and payload.get("op") == "summary":
                return {"success": True, "data": {"summary": {"governed_active_count": 1, "blocked_active_count": 0}}}
            if action == "factor_candidate_registry" and payload.get("op") == "active_pool":
                return {"success": True, "data": {"active_pool": {"count": 1}}}
            raise AssertionError(f"unexpected action: {action}")

        monkeypatch.setattr(quant_manager_module, "quant_manager", _fake_quant_manager)

        scheduler = FactorScheduler(universe=["000001", "000002"], factors=["reversal"], batch_size=1)
        result = await scheduler.run_once()
        status = scheduler.status()

        assert result["run_id"].startswith("factor_scheduler_run_")
        assert result["status"] == "success"
        assert result["workflow_version"] == "p2.v1"
        assert result["quality_status"] == "fresh"
        assert result["stale"] is False
        assert result["summary"]["run_id"] == result["run_id"]
        assert result["summary"]["llm_generation_artifact_id"] == "factor_llm_scheduler_workflow_case"
        assert result["lineage"]["llm_generation_artifact_id"] == "factor_llm_scheduler_workflow_case"
        assert result["stage_summary"]["stage_status_counts"]["completed"] >= 4
        assert result["stages"]["batch_compute"]["status"] == "completed"
        assert result["stages"]["batch_compute"]["retry_boundary"] == "batch"
        assert result["stages"]["llm_factor_mining"]["artifact_id"] == "factor_llm_scheduler_workflow_case"
        assert result["stages"]["llm_validation"]["status"] == "completed"
        assert result["stages"]["registry_refresh"]["status"] == "completed"
        assert result["recovery_checkpoint"]["last_completed_stage"] == "registry_refresh"
        assert result["recovery_checkpoint"]["retryable_stage_names"] == []
        assert status["quality_status"] == "fresh"
        assert status["stale"] is False
        assert status["last_summary"]["run_id"] == result["run_id"]
        assert status["run_history"][0]["run_id"] == result["run_id"]
        assert status["run_history"][0]["stage_summary"]["failed_stage_count"] == 0

    @pytest.mark.asyncio
    async def test_factor_scheduler_run_once_counts_failed_manager_batches(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        monkeypatch.setattr(
            quant_manager_module,
            "quant_manager",
            AsyncMock(return_value={"success": False, "data": None, "error": "bad json"}),
        )

        scheduler = FactorScheduler(universe=["000001", "000002"], factors=["reversal"], batch_size=1)
        result = await scheduler.run_once()

        assert result["computed"] == 0
        assert result["errors"] == 2
        assert result["universe_size"] == 2
        assert result["source"] == "factor_scheduler"
        assert "degraded" in result["quality_flags"]
        assert "failed" in result["quality_flags"]

    @pytest.mark.asyncio
    async def test_factor_scheduler_passes_codes_to_llm_factor_mining(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        monkeypatch.setenv("FACTOR_LLM_ENABLED", "1")
        monkeypatch.setenv("FACTOR_SCHEDULER_LLM_MINING", "1")

        calls = []

        async def _fake_quant_manager(*, action, code=None, **kwargs):
            payload = json.loads(kwargs["kwargs"])
            calls.append({"action": action, "code": code, "payload": payload})
            if action == "batch_compute_factors":
                return {"success": True, "data": {"computed_count": len(payload.get("codes") or []), "error_count": 0}}
            if action == "llm_factor_mining":
                return {"success": True, "data": {"codes": payload.get("codes") or []}}
            raise AssertionError(f"unexpected action: {action}")

        monkeypatch.setattr(
            quant_manager_module,
            "quant_manager",
            _fake_quant_manager,
        )

        scheduler = FactorScheduler(universe=["000001", "000002"], factors=["reversal"], batch_size=1)
        result = await scheduler.run_once()

        llm_calls = [item for item in calls if item["action"] == "llm_factor_mining"]
        assert len(llm_calls) == 1
        assert llm_calls[0]["payload"]["codes"] == ["000001", "000002"]
        assert result["llm_mining"]["success"] is True
        assert result["llm_mining"]["data"]["codes"] == ["000001", "000002"]

    @pytest.mark.asyncio
    async def test_factor_scheduler_runs_llm_validation_and_refreshes_registry_pool(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        monkeypatch.setenv("FACTOR_LLM_ENABLED", "1")
        monkeypatch.setenv("FACTOR_SCHEDULER_LLM_MINING", "1")
        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: MagicMock())

        calls = []
        validation_codes = ["000001", "000002", "000333", "600519", "601318"]
        candidates = [
            {"name": "candidate_alpha", "formula": "rank(close / delay(close, 20))", "family": "momentum"},
            {"name": "candidate_beta", "formula": "ts_mean(volume, 10)", "family": "liquidity"},
        ]

        async def _fake_quant_manager(*, action, code=None, **kwargs):
            payload = json.loads(kwargs["kwargs"])
            calls.append({"action": action, "code": code, "payload": payload})
            if action == "batch_compute_factors":
                return {
                    "success": True,
                    "data": {
                        "computed_count": len(payload.get("codes") or []),
                        "error_count": 0,
                    },
                }
            if action == "llm_factor_mining":
                return {
                    "success": True,
                    "data": {
                        "codes": validation_codes,
                        "candidate_count": len(candidates),
                        "candidates": candidates,
                    },
                }
            if action == "validate_factor_candidate":
                return {
                    "success": True,
                    "data": {"artifact_id": payload["output_artifact_id"]},
                }
            if action == "factor_candidate_registry" and payload.get("op") == "summary":
                return {
                    "success": True,
                    "data": {
                        "summary": {
                            "count": 2,
                            "governed_active_count": 2,
                            "blocked_active_count": 1,
                        }
                    },
                }
            if action == "factor_candidate_registry" and payload.get("op") == "active_pool":
                return {
                    "success": True,
                    "data": {
                        "active_pool": {
                            "count": 2,
                            "top_candidates": [
                                {"artifact_id": "artifact_alpha"},
                                {"artifact_id": "artifact_beta"},
                            ],
                        }
                    },
                }
            raise AssertionError(f"unexpected action: {action}")

        monkeypatch.setattr(quant_manager_module, "quant_manager", _fake_quant_manager)

        scheduler = FactorScheduler(
            universe=["000001", "000002", "000333", "600519"],
            factors=["reversal"],
            batch_size=2,
        )
        result = await scheduler.run_once()

        assert result["computed"] == 4
        assert result["errors"] == 0
        assert result["quality_flags"] == []
        assert result["llm_validation"]["status"] == "success"
        assert result["llm_validation"]["validation_attempted"] is True
        assert result["llm_validation"]["generated_candidate_count"] == 2
        assert result["llm_validation"]["validated_candidate_count"] == 2
        assert result["llm_validation"]["validation_failed_count"] == 0
        assert result["llm_validation"]["validation_codes"] == validation_codes
        assert result["llm_validation"]["registry_refresh_status"] == "success"
        assert result["llm_validation"]["active_pool_count_after_run"] == 2
        assert result["llm_validation"]["governed_active_count_after_run"] == 2
        assert result["llm_validation"]["blocked_active_count_after_run"] == 1
        assert len(result["llm_validation"]["validation_artifact_ids"]) == 2

        actions = [item["action"] for item in calls]
        assert actions == [
            "batch_compute_factors",
            "batch_compute_factors",
            "llm_factor_mining",
            "validate_factor_candidate",
            "validate_factor_candidate",
            "factor_candidate_registry",
            "factor_candidate_registry",
        ]

        validation_calls = [item for item in calls if item["action"] == "validate_factor_candidate"]
        assert [item["payload"]["candidate"]["name"] for item in validation_calls] == ["candidate_alpha", "candidate_beta"]
        assert all(item["payload"]["codes"] == validation_codes for item in validation_calls)
        assert all(item["payload"]["persist_artifact"] is True for item in validation_calls)
        assert all(item["payload"]["write_memory"] is True for item in validation_calls)

        registry_calls = [item for item in calls if item["action"] == "factor_candidate_registry"]
        assert [item["payload"]["op"] for item in registry_calls] == ["summary", "active_pool"]
        assert all(item["payload"]["codes"] == validation_codes for item in registry_calls)
        assert all(item["payload"]["market_codes_only"] is True for item in registry_calls)

    @pytest.mark.asyncio
    async def test_factor_scheduler_marks_partial_when_some_llm_validations_fail(self, monkeypatch):
        from akshare_mcp.services.factor_scheduler import FactorScheduler
        from akshare_mcp.tools.managers import quant_manager as quant_manager_module

        monkeypatch.setenv("FACTOR_LLM_ENABLED", "1")
        monkeypatch.setenv("FACTOR_SCHEDULER_LLM_MINING", "1")
        monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: MagicMock())

        calls = []
        validation_codes = ["000001", "000002", "000333", "600519"]
        candidates = [
            {"name": "candidate_ok", "formula": "rank(close / delay(close, 10))", "family": "momentum"},
            {"name": "candidate_bad", "formula": "delay(close, -1)", "family": "leakage"},
        ]

        async def _fake_quant_manager(*, action, code=None, **kwargs):
            payload = json.loads(kwargs["kwargs"])
            calls.append({"action": action, "code": code, "payload": payload})
            if action == "batch_compute_factors":
                return {
                    "success": True,
                    "data": {
                        "computed_count": len(payload.get("codes") or []),
                        "error_count": 0,
                    },
                }
            if action == "llm_factor_mining":
                return {
                    "success": True,
                    "data": {
                        "codes": validation_codes,
                        "candidate_count": len(candidates),
                        "candidates": candidates,
                    },
                }
            if action == "validate_factor_candidate":
                if payload["candidate"]["name"] == "candidate_bad":
                    return {"success": False, "error": "multiple testing unavailable"}
                return {
                    "success": True,
                    "data": {"artifact_id": payload["output_artifact_id"]},
                }
            if action == "factor_candidate_registry" and payload.get("op") == "summary":
                return {
                    "success": True,
                    "data": {
                        "summary": {
                            "count": 1,
                            "governed_active_count": 1,
                            "blocked_active_count": 0,
                        }
                    },
                }
            if action == "factor_candidate_registry" and payload.get("op") == "active_pool":
                return {
                    "success": True,
                    "data": {"active_pool": {"count": 1}},
                }
            raise AssertionError(f"unexpected action: {action}")

        monkeypatch.setattr(quant_manager_module, "quant_manager", _fake_quant_manager)

        scheduler = FactorScheduler(
            universe=["000001", "000002", "000333", "600519"],
            factors=["reversal"],
            batch_size=2,
        )
        result = await scheduler.run_once()

        assert result["computed"] == 4
        assert result["errors"] == 0
        assert "partial" in result["quality_flags"]
        assert result["llm_validation"]["status"] == "partial"
        assert result["llm_validation"]["generated_candidate_count"] == 2
        assert result["llm_validation"]["validated_candidate_count"] == 1
        assert result["llm_validation"]["validation_failed_count"] == 1
        assert result["llm_validation"]["registry_refresh_status"] == "success"
        assert result["llm_validation"]["active_pool_count_after_run"] == 1
        assert result["llm_validation"]["governed_active_count_after_run"] == 1
        assert result["llm_validation"]["failed_candidates"] == [
            {
                "candidate_index": 1,
                "name": "candidate_bad",
                "error": "multiple testing unavailable",
            }
        ]

        registry_calls = [item for item in calls if item["action"] == "factor_candidate_registry"]
        assert [item["payload"]["op"] for item in registry_calls] == ["summary", "active_pool"]

    def test_factor_scheduler_status_marks_stale_result(self):
        from akshare_mcp.services.factor_scheduler import FactorScheduler

        scheduler = FactorScheduler(universe=["000001"], factors=["reversal"], batch_size=1)
        scheduler.last_run = datetime.now(timezone.utc) - timedelta(days=2)
        scheduler.last_result = {
            "computed": 1,
            "errors": 0,
            "elapsed_seconds": 1.2,
            "universe_size": 1,
            "source": "factor_scheduler",
            "asof_time": scheduler.last_run.isoformat(),
            "freshness_sec": 0.0,
            "quality_flags": [],
        }

        status = scheduler.status()

        assert status["source"] == "factor_scheduler"
        assert status["asof_time"] == scheduler.last_run.isoformat()
        assert status["freshness_sec"] >= 2 * 24 * 60 * 60
        assert "stale" in status["quality_flags"]

    @pytest.mark.asyncio
    async def test_collect_prefers_db_index_klines_before_external_fetch(self):
        collector = DataCollector()
        db = MagicMock()
        db.get_klines = AsyncMock(return_value=_make_klines(60, base=3000, trend=0.002, noise=0.001))
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 9})
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.08}] * 10)
        db.count_strategies_by_type = AsyncMock(side_effect=lambda status: {"momentum": 2} if status == "listed" else {"momentum": 1})
        db.save_daily_snapshot = AsyncMock()
        db.acquire = MagicMock(side_effect=Exception("db unavailable"))
        db.list_stock_universe = AsyncMock(return_value=[])
        db.save_factory_event_cluster = None
        db.save_factory_event_signal = None

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 63, "level": "greed", "components": {"breadth": 72}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 12}, {"total": 8}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "AI", "mainNetInflow": 2},
                    {"name": "券商", "mainNetInflow": 1},
                    {"name": "煤炭", "mainNetInflow": -1},
                    {"name": "地产", "mainNetInflow": -2},
                ]},
            ],
        ), patch(
            "akshare_mcp.tools.market.kline.get_index_kline",
            new_callable=AsyncMock,
            return_value={"success": True, "data": _make_klines(60, base=3000, trend=0.003, noise=0.001)},
        ) as index_mock:
            snapshot = await collector.collect(db)

        assert snapshot["fear_greed_index"] == 63
        assert snapshot["sources"]["fear_greed"]["status"] == "success"
        assert index_mock.await_count == 0

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_collect_uses_db_native_paths_without_external_threads(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.55e12, "pe_ratio": 9.5, "pb_ratio": 1.1},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.20e12, "pe_ratio": 8.8, "pb_ratio": 1.2},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": "金融", "market": "SH", "market_cap": 8.00e11, "pe_ratio": 6.2, "pb_ratio": 0.9},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601857", "600938"}:
                return _make_klines(size, base=10.0, trend=0.012, noise=0.002)
            return _make_klines(size, base=30.0, trend=-0.002, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 67, "level": "greed", "components": {"breadth": 74}},
        ), patch(
            "strategy_factory.application.collect.resolve_event_runtime_mode",
            return_value="refresh",
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=AssertionError("external thread should not be called"),
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["fear_greed"]["status"] == "success"
        assert snapshot["sources"]["north_fund"]["status"] == "fallback"
        assert snapshot["sources"]["margin_data"]["status"] == "success"
        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert snapshot["sources"]["sector_fund_flow"]["details"]["mode"] == "local_rotation"
        internal_snapshot = await db.get_factory_market_internal_snapshot()
        assert internal_snapshot is not None
        assert internal_snapshot["engine"] == "local_db_rule_v1"
        assert "石油石化" in list(internal_snapshot.get("hot_sectors") or [])

    @pytest.mark.asyncio
    async def test_collect_uses_industry_as_rotation_fallback_when_sector_missing(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601398", "name": "工商银行", "industry": "银行", "sector": None, "market": "SH", "market_cap": 2.52e11, "pe_ratio": 6.9, "pb_ratio": 0.66},
            {"code": "601288", "name": "农业银行", "industry": "银行", "sector": None, "market": "SH", "market_cap": 2.33e11, "pe_ratio": 8.2, "pb_ratio": 0.86},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": None, "market": "SH", "market_cap": 9.73e10, "pe_ratio": 6.5, "pb_ratio": 0.91},
            {"code": "600048", "name": "保利发展", "industry": "房地产开发", "sector": None, "market": "SH", "market_cap": 1.10e11, "pe_ratio": 10.8, "pb_ratio": 0.88},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601398", "601288", "600036"}:
                return _make_klines(size, base=8.0, trend=0.011, noise=0.0015)
            return _make_klines(size, base=12.0, trend=-0.006, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 64, "level": "greed", "components": {"breadth": 72}},
        ), patch(
            "strategy_factory.application.collect.resolve_event_runtime_mode",
            return_value="refresh",
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=AssertionError("external thread should not be called"),
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert "银行" in list(snapshot.get("hot_sectors") or [])
        internal_snapshot = await db.get_factory_market_internal_snapshot()
        assert internal_snapshot is not None
        assert "银行" in list(internal_snapshot.get("hot_sectors") or [])

    @pytest.mark.asyncio
    async def test_collect_uses_theme_alias_as_rotation_fallback_when_industry_missing(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601398", "name": "工商银行", "industry": None, "sector": None, "market": "SH", "market_cap": 2.52e11, "pe_ratio": 6.9, "pb_ratio": 0.66},
            {"code": "601288", "name": "农业银行", "industry": None, "sector": None, "market": "SH", "market_cap": 2.33e11, "pe_ratio": 8.2, "pb_ratio": 0.86},
            {"code": "600036", "name": "招商银行", "industry": None, "sector": None, "market": "SH", "market_cap": 9.73e10, "pe_ratio": 6.5, "pb_ratio": 0.91},
            {"code": "600048", "name": "保利发展", "industry": None, "sector": None, "market": "SH", "market_cap": 1.10e11, "pe_ratio": 10.8, "pb_ratio": 0.88},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601398", "601288", "600036"}:
                return _make_klines(size, base=8.0, trend=0.011, noise=0.0015)
            return _make_klines(size, base=12.0, trend=-0.006, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 64, "level": "greed", "components": {"breadth": 72}},
        ), patch(
            "strategy_factory.application.collect.resolve_event_runtime_mode",
            return_value="refresh",
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=AssertionError("external thread should not be called"),
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert "高股息金融" in list(snapshot.get("hot_sectors") or [])
        internal_snapshot = await db.get_factory_market_internal_snapshot()
        assert internal_snapshot is not None
        assert "高股息金融" in list(internal_snapshot.get("hot_sectors") or [])

    @pytest.mark.asyncio
    async def test_collect_local_event_engine_generates_oil_event_without_external_sector_flow(self):
        collector = DataCollector()
        db = _StrategyDB()
        db.list_stock_universe = AsyncMock(return_value=[
            {"code": "601857", "name": "中国石油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.55e12, "pe_ratio": 9.5, "pb_ratio": 1.1},
            {"code": "600938", "name": "中国海油", "industry": "油气开采", "sector": "石油石化", "market": "SH", "market_cap": 1.20e12, "pe_ratio": 8.8, "pb_ratio": 1.2},
            {"code": "600028", "name": "中国石化", "industry": "炼化", "sector": "石油石化", "market": "SH", "market_cap": 7.20e11, "pe_ratio": 10.1, "pb_ratio": 0.9},
            {"code": "600036", "name": "招商银行", "industry": "银行", "sector": "金融", "market": "SH", "market_cap": 8.00e11, "pe_ratio": 6.2, "pb_ratio": 0.9},
        ])

        async def _get_klines(code, limit=200):
            size = max(limit, 60)
            if code == "000001":
                return _make_klines(size, base=3200, trend=0.0015, noise=0.001)
            if code in {"601857", "600938", "600028"}:
                return _make_klines(size, base=10.0, trend=0.012, noise=0.002)
            return _make_klines(size, base=30.0, trend=-0.004, noise=0.0015)

        db.get_klines = AsyncMock(side_effect=_get_klines)
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.09}] * 10)

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 67, "level": "greed", "components": {"breadth": 74}},
        ), patch(
            "strategy_factory.application.collect.resolve_event_runtime_mode",
            return_value="refresh",
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 12}, {"total": 8}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                Exception("sector flow unavailable"),
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["sources"]["sector_fund_flow"]["status"] == "success"
        assert "石油石化" in list(snapshot.get("hot_sectors") or [])
        assert snapshot["event_driven"]["enabled"] is True
        assert snapshot["event_driven"]["event_count"] >= 1
        assert any(str(item.get("event_id") or "") == "local_theme_upstream_oil_gas_positive" for item in snapshot["event_driven"]["events"])
        oil_event = next(item for item in snapshot["event_driven"]["events"] if item.get("event_id") == "local_theme_upstream_oil_gas_positive")
        assert oil_event["themes"][0]["theme_code"] == "upstream_oil_gas"
        assert oil_event["themes"][0]["target_symbols"][:2] == ["601857", "600938"]

    @pytest.mark.asyncio
    async def test_collect_builds_event_driven_snapshot_from_factory_tables(self):
        collector = DataCollector()
        db = MagicMock()
        db.get_limit_up_stats = AsyncMock(return_value={"up_count": 8})
        db.get_factor_ic_history = AsyncMock(return_value=[{"ic_value": 0.08}] * 10)
        db.count_strategies_by_type = AsyncMock(side_effect=lambda status: {"momentum": 2} if status == "listed" else {"momentum": 1})
        db.save_daily_snapshot = AsyncMock()
        db.list_factory_event_clusters = AsyncMock(return_value=[{
            "event_id": "evt_oil_1",
            "event_type": "geopolitics",
            "event_name": "中东战事升级",
            "summary": "中东战事升级推动原油供给担忧升温。",
            "direction": "positive",
            "intensity": 0.85,
            "confidence": 0.91,
            "horizon": "swing_5_20d",
            "themes": ["upstream_oil_gas"],
            "status": "active",
            "last_seen_at": "2026-03-09T09:00:00+08:00",
        }])
        db.list_factory_theme_definitions = AsyncMock(return_value=[{
            "theme_code": "upstream_oil_gas",
            "theme_name": "上游油气",
            "active": True,
        }])
        db.list_factory_event_signals = AsyncMock(return_value=[
            {
                "event_id": "evt_oil_1",
                "symbol": "601857",
                "theme_code": "upstream_oil_gas",
                "final_score": 0.92,
                "theme_score": 0.88,
                "exposure_score": 0.91,
                "price_confirm_score": 0.84,
                "flow_confirm_score": 0.73,
                "rationale": "上游油气对油价上行弹性更高。",
            },
            {
                "event_id": "evt_oil_1",
                "symbol": "600938",
                "theme_code": "upstream_oil_gas",
                "final_score": 0.87,
                "theme_score": 0.82,
                "exposure_score": 0.85,
                "price_confirm_score": 0.79,
                "flow_confirm_score": 0.68,
                "rationale": "供给扰动叠加板块相对强势。",
            },
        ])

        with patch(
            "akshare_mcp.services.sentiment.sentiment_analyzer.calculate_fear_greed_index",
            return_value={"index": 58, "level": "neutral", "components": {"breadth": 60}},
        ), patch(
            "akshare_mcp.services.strategy_factory.asyncio.to_thread",
            side_effect=[
                {"success": True, "data": {"items": [{"total": 10}, {"total": 12}, {"total": 8}]}},
                {"success": True, "data": [
                    {"marginBalance": 120}, {"marginBalance": 118}, {"marginBalance": 117},
                    {"marginBalance": 116}, {"marginBalance": 115}, {"marginBalance": 100},
                ]},
                {"success": True, "data": [
                    {"name": "石油石化", "mainNetInflow": 2},
                    {"name": "航运", "mainNetInflow": 1},
                    {"name": "航空", "mainNetInflow": -1},
                    {"name": "化工", "mainNetInflow": -2},
                ]},
            ],
        ):
            snapshot = await collector.collect(db)

        assert snapshot["event_driven"]["enabled"] is True
        assert snapshot["event_driven"]["event_count"] == 1
        assert snapshot["event_driven"]["tasks_ready_count"] == 1
        assert snapshot["event_driven"]["events"][0]["event_id"] == "evt_oil_1"
        assert snapshot["event_driven"]["events"][0]["themes"][0]["target_symbols"] == ["601857", "600938"]
        assert snapshot["summary"]["event_count"] == 1
        assert snapshot["sources"]["event_driven"]["status"] == "success"
        db.save_daily_snapshot.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════
# 12. 生命周期状态转换测试
# ═══════════════════════════════════════════════════════════════


__all__ = [name for name in globals() if name.startswith("Test")]
