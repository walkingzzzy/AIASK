import pytest

from strategy_factory.application.research.runner import ResearchPlaneRunner


class _FakeSpawner:
    def __init__(self):
        self._report = {"summary": {"candidate_count": 1, "source_counts": {"fear_greed": 1}}}

    def spawn(self, _snapshot):
        return [
            {
                "strategy_type": "momentum",
                "spawn_reason": "fear_greed local rule",
                "generation_reason": {"source": "fear_greed"},
            }
        ]

    def get_last_report(self):
        return self._report


class _SyntheticTargetSpawner:
    def __init__(self):
        self._report = {"summary": {"candidate_count": 1}}

    def spawn(self, _snapshot):
        return [
            {
                "strategy_type": "ma_cross",
                "target_symbols": ["920185", "689009", "688981"],
                "requested_target_symbols": ["920185", "689009", "688981"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["920185", "689009", "688981"]},
                "research_task": {
                    "task_source": "snapshot",
                    "synthetic_local_spawn": True,
                    "target_symbols": ["920185", "689009", "688981"],
                    "target_symbols_signature": "920185,689009,688981",
                    "stock_pool": {"selection_mode": "explicit", "symbols": ["920185", "689009", "688981"]},
                    "gate_1_representative_count": 3,
                },
            }
        ]

    def get_last_report(self):
        return self._report


class _FakeFactoryPkg:
    StrategySpawner = _FakeSpawner


class _SyntheticTargetFactoryPkg:
    StrategySpawner = _SyntheticTargetSpawner


class _FakeScheduler:
    def _adapt_gateway_repository(self, db):
        return {"wrapped_db": db}

    def _summarize_refresh_result(self, payload):
        return {"computed": payload.get("computed")}

    def _inject_factor_refresh_meta(self, artifact, refresh_meta):
        result = dict(artifact or {})
        result["freshness_repair"] = dict(refresh_meta or {})
        summary = dict(result.get("summary") or {})
        summary["refresh_attempted"] = bool(refresh_meta.get("refresh_attempted"))
        summary["refresh_status"] = refresh_meta.get("refresh_status")
        result["summary"] = summary
        return result

    async def _run_autonomy_batches(self, _db, _snapshot):
        return {
            "stage": {
                "generated_count": 2,
                "external_llm_status": "succeeded",
                "external_llm_attempt_count": 3,
                "external_llm_network_request_count": 5,
                "external_llm_compatibility_skip_count": 1,
                "external_llm_cooldown_skip_count": 0,
                "external_llm_selected_count": 2,
            },
            "candidates": [
                {
                    "strategy_type": "value_factor",
                    "research_task": {"task_source": "snapshot"},
                    "experiment_id": "exp_alpha",
                    "params": {"generator_type": "external_llm"},
                },
                {
                    "strategy_type": "ma_cross",
                    "research_task": {
                        "task_source": "bulk_stock_matrix",
                        "source_candidate_artifact_id": "candidate_alpha",
                    },
                    "params": {"generator_type": "external_llm"},
                },
            ],
            "experiments": [{"experiment_id": "exp_alpha", "status": "recorded"}],
        }


class _FakeKlineDb:
    def __init__(self, counts):
        self._counts = dict(counts)

    async def get_klines(self, code, limit=60):
        return [{"close": 1.0}] * min(limit, int(self._counts.get(code, 0)))


class _FakeFactorGateway:
    def __init__(self):
        self.build_calls = 0
        self.refresh_calls = 0

    async def build_artifact(self, gateway_db, snapshot):
        self.build_calls += 1
        return {
            "gateway_db": gateway_db,
            "snapshot_marker": snapshot.get("marker"),
            "summary": {
                "factor_source_mode": "seed_fallback",
                "stale": self.build_calls == 1,
            },
        }

    async def refresh(self):
        self.refresh_calls += 1
        return {"computed": 7}


@pytest.mark.asyncio
async def test_research_plane_runner_builds_factor_research_artifact_with_refresh(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_AUTO_REFRESH", "1")
    runner = ResearchPlaneRunner(_FakeScheduler(), _FakeFactoryPkg())
    gateway = _FakeFactorGateway()

    artifact = await runner.build_factor_research_artifact(
        gateway,
        db={"db": "adapter"},
        snapshot={"marker": "snapshot"},
    )

    assert gateway.build_calls == 2
    assert gateway.refresh_calls == 1
    assert artifact["gateway_db"] == {"wrapped_db": {"db": "adapter"}}
    assert artifact["snapshot_marker"] == "snapshot"
    assert artifact["freshness_repair"]["refresh_attempted"] is True
    assert artifact["summary"]["refresh_status"] == "success"


@pytest.mark.asyncio
async def test_research_plane_runner_skips_refresh_when_auto_refresh_disabled(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_AUTO_REFRESH", "0")
    runner = ResearchPlaneRunner(_FakeScheduler(), _FakeFactoryPkg())
    gateway = _FakeFactorGateway()

    artifact = await runner.build_factor_research_artifact(
        gateway,
        db={"db": "adapter"},
        snapshot={"marker": "snapshot"},
    )

    assert gateway.build_calls == 1
    assert gateway.refresh_calls == 0
    assert artifact["freshness_repair"]["refresh_attempted"] is False
    assert artifact["freshness_repair"]["refresh_status"] == "disabled"
    assert artifact["summary"]["refresh_status"] == "disabled"


@pytest.mark.asyncio
async def test_research_plane_runner_run_generation_separates_research_boundaries():
    runner = ResearchPlaneRunner(_FakeScheduler(), _FakeFactoryPkg())

    result = await runner.run_generation(db=object(), snapshot={})

    assert len(result.local_candidates) == 1
    assert len(result.autonomy_candidates) == 2
    assert len(result.generated_candidates) == 3
    assert result.local_spawn_report["summary"]["candidate_count"] == 1
    assert result.candidate_origin_counts == {
        "local_rule": 1,
        "external_autonomy": 1,
        "governed_candidate_activation": 1,
    }
    assert result.local_rule_candidate_count == 1
    assert result.external_autonomy_candidate_count == 1
    assert result.governed_candidate_activation_count == 1
    assert result.autonomy_candidates[0]["params"]["factory_attempt_count"] == 3
    assert result.autonomy_candidates[0]["params"]["factory_global_attempt_count"] == 3
    assert result.autonomy_candidates[1]["params"]["factory_network_request_count"] == 5


@pytest.mark.asyncio
async def test_research_plane_runner_prunes_insufficient_kline_codes_from_synthetic_local_spawn():
    runner = ResearchPlaneRunner(_FakeScheduler(), _SyntheticTargetFactoryPkg())
    db = _FakeKlineDb({"920185": 11, "689009": 60, "688981": 60})

    result = await runner.run_generation(db=db, snapshot={})

    candidate = result.local_candidates[0]
    assert sorted(candidate["target_symbols"]) == ["688981", "689009"]
    assert sorted(candidate["requested_target_symbols"]) == ["688981", "689009"]
    assert sorted(candidate["stock_pool"]["symbols"]) == ["688981", "689009"]
    assert sorted(candidate["params"]["target_symbols"]) == ["688981", "689009"]
    assert sorted(candidate["research_task"]["target_symbols"]) == ["688981", "689009"]
    assert sorted(candidate["research_task"]["target_symbols_signature"].split(",")) == ["688981", "689009"]
    assert candidate["research_task"]["gate_1_representative_count"] == 2

    summary = result.local_spawn_report["summary"]
    assert summary["target_symbol_sanitization_enabled"] is True
    assert summary["target_symbol_sanitization_pruned_candidate_count"] == 1
    assert summary["target_symbol_sanitization_pruned_symbol_count"] == 1
    assert summary["target_symbol_sanitization_insufficient_kline_codes"] == ["920185"]
