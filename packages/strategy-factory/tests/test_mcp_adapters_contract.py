import pytest

from strategy_factory.api import (
    AutonomyGateway,
    FactorResearchGateway,
    IncubationGateway,
    RiskGateway,
    StrategyFactoryRepository,
    ValidationGateway,
    VectorSearchGateway,
)
from strategy_factory.infrastructure import (
    MCPAutonomyGatewayImpl,
    MCPRuntimeAdapters,
    MCPStrategyFactoryRepositoryAdapter,
    MCPVectorSearchGatewayImpl,
    adapt_repository,
    build_mcp_runtime_adapters,
)


class _FakeDB:
    extra_value = "ok"

    def __init__(self):
        self.calls = []
        self.acquire_calls = 0

    def acquire(self):
        self.acquire_calls += 1
        return f"acquire_ctx_{self.acquire_calls}"

    async def get_klines(self, code: str, limit: int = 500):
        self.calls.append(("get_klines", code, limit))
        return [{"code": code, "limit": limit}]

    async def save_strategy(self, data):
        self.calls.append(("save_strategy", data))
        return {"saved": data}

    async def get_limit_up_stats(self):
        return {"date": "2026-03-20"}

    async def get_factor_ic_history(self, factor_name: str, horizon: str, limit: int):
        return [{"factor_name": factor_name, "horizon": horizon, "limit": limit}]

    async def count_strategies_by_type(self, status: str):
        return {status: 1}

    async def save_daily_snapshot(self, snapshot_date, snapshot):
        return {"snapshot_date": snapshot_date, "snapshot": snapshot}

    async def list_strategies(self, status: str, limit: int = 500):
        return [{"id": "s1", "status": status, "limit": limit}]

    async def get_strategy(self, strategy_id: str):
        return {"id": strategy_id}

    async def get_strategy_metrics(self, strategy_id: str):
        return [{"strategy_id": strategy_id, "period": "backtest"}]

    async def get_signal_stats(self, strategy_id: str):
        return {"strategy_id": strategy_id, "hit_rate": {}}

    async def save_strategy_quality_report(self, strategy_id: str, report_type: str, report):
        return {"strategy_id": strategy_id, "report_type": report_type, "report": report}

    async def update_strategy_status(self, strategy_id: str, status: str, **kwargs):
        return {"strategy_id": strategy_id, "status": status, "kwargs": kwargs}

    async def save_strategy_lineage(self, strategy_id: str, parent_strategy_id, reason: str, snapshot):
        return {"strategy_id": strategy_id, "parent_strategy_id": parent_strategy_id, "reason": reason}

    async def save_strategy_metrics(self, strategy_id: str, period: str, payload):
        return {"strategy_id": strategy_id, "period": period, "payload": payload}

    async def save_elimination_log(self, strategy_id: str, log_date, red_flags, reason: str):
        return {"strategy_id": strategy_id, "log_date": log_date, "red_flags": red_flags, "reason": reason}

    async def get_strategy_generation_experiment(self, experiment_id: str):
        return {"experiment_id": experiment_id}

    async def save_strategy_generation_experiment(self, payload):
        return {"payload": payload}

    async def save_factory_task_evidence(self, payload):
        return {"payload": payload}

    async def save_strategy_task_run(self, payload):
        return {"id": "task_1", "payload": payload}

    async def update_strategy_task_run(self, task_run_id, **kwargs):
        return {"id": task_run_id, "kwargs": kwargs}

    async def list_stock_universe(self, limit: int = 200, offset: int = 0):
        return [{"code": "600519", "limit": limit, "offset": offset}]

    async def list_factory_event_clusters(self, status=None, limit: int = 200):
        return [{"status": status, "limit": limit}]

    async def save_factory_theme_definition(self, payload):
        return {"payload": payload}

    async def save_strategy_factory_run(self, results):
        return {"results": results}

    async def list_strategy_factory_runs(self, limit: int = 20):
        return [{"run_id": "factory_run_1", "limit": limit}]

    async def get_strategy_factory_run(self, run_id: str):
        return {"run_id": run_id, "status": "success"}

    async def get_latest_strategy_factory_run(self):
        return {"run_id": "factory_run_latest", "status": "success"}

    async def get_strategy_incubation_account(self, strategy_id: str):
        return {"strategy_id": strategy_id, "account_id": f"acct_{strategy_id}"}

    async def save_strategy_incubation_account(self, strategy_id: str, account_id: str, **kwargs):
        return {"strategy_id": strategy_id, "account_id": account_id, "kwargs": kwargs}


class _FakeVectorEngine:
    def __init__(self):
        self.last_backend_used = "index"
        self.last_meta = {"backend_requested": "index", "backend_used": "index"}
        self.calls = []

    def find_similar_patterns(self, **kwargs):
        self.calls.append(kwargs)
        return [{"code": "s1", "similarity": 0.99}]


class _FakeAutonomyService:
    async def generate_factory_candidates(self, db, snapshot, *, limit=4, research_task=None, source=""):
        return {
            "db_type": type(db).__name__,
            "snapshot": dict(snapshot),
            "limit": limit,
            "research_task": dict(research_task or {}),
            "source": source,
        }


class _FakeFactorScheduler:
    def status(self):
        return {"running": False, "last_run": None}

    async def run_once(self):
        return {"computed": 3, "errors": 0, "quality_flags": []}


class _FakeFactorResearchBuilder:
    @staticmethod
    async def build(db, snapshot):
        return {
            "active_factors": ["value"],
            "summary": {
                "active_factor_count": 1,
                "top_factor_names": ["value"],
            },
            "snapshot_date": snapshot.get("date"),
            "db_type": type(db).__name__,
        }


class _FakeIncubationService:
    async def ensure_account(self, db, strategy, *, source_run_id=None, stage="warmup"):
        return {"binding": {"strategy_id": strategy.get("id"), "source_run_id": source_run_id, "stage": stage}}


class _FakeIncubationPipelineService:
    async def run_strategy(self, db, strategy, *, source="strategy_factory_submit", auto_apply_review=False):
        return {"snapshot": {"strategy_id": strategy.get("id"), "source": source, "auto_apply_review": auto_apply_review}}


async def _fake_validation_runner(strategy_type: str, params: dict, db):
    return {"strategy_type": strategy_type, "params": dict(params), "db_type": type(db).__name__}


async def _fake_risk_runner(strategy_type: str, params: dict, db):
    return {"strategy_type": strategy_type, "params": dict(params), "db_type": type(db).__name__}


@pytest.mark.asyncio
async def test_repository_adapter_wraps_db_surface():
    db = _FakeDB()
    repo = adapt_repository(db)

    assert isinstance(repo, MCPStrategyFactoryRepositoryAdapter)
    assert isinstance(repo, StrategyFactoryRepository)
    assert repo.raw is db
    with pytest.raises(AttributeError):
        _ = repo.extra_value

    klines = await repo.get_klines("600519", limit=3)
    saved = await repo.save_strategy({"id": "s1"})
    latest_run = await repo.get_latest_strategy_factory_run()
    run_detail = await repo.get_strategy_factory_run("factory_run_1")
    run_list = await repo.list_strategy_factory_runs(limit=5)

    assert klines == [{"code": "600519", "limit": 3}]
    assert saved == {"saved": {"id": "s1"}}
    assert latest_run["run_id"] == "factory_run_latest"
    assert run_detail["run_id"] == "factory_run_1"
    assert run_list == [{"run_id": "factory_run_1", "limit": 5}]
    assert db.calls[:2] == [("get_klines", "600519", 3), ("save_strategy", {"id": "s1"})]


def test_repository_adapter_proxies_acquire():
    db = _FakeDB()
    repo = adapt_repository(db)

    handle = repo.acquire()

    assert handle == "acquire_ctx_1"
    assert db.acquire_calls == 1


@pytest.mark.asyncio
async def test_repository_adapter_proxies_incubation_account_methods():
    db = _FakeDB()
    repo = adapt_repository(db)

    existing = await repo.get_strategy_incubation_account("sid_1")
    saved = await repo.save_strategy_incubation_account("sid_1", "acct_sid_1", stage="warmup")

    assert existing["account_id"] == "acct_sid_1"
    assert saved["strategy_id"] == "sid_1"
    assert saved["account_id"] == "acct_sid_1"
    assert saved["kwargs"]["stage"] == "warmup"


def test_vector_gateway_delegates_to_engine():
    engine = _FakeVectorEngine()
    gateway = MCPVectorSearchGatewayImpl(engine)

    assert isinstance(gateway, VectorSearchGateway)
    result = gateway.find_similar_patterns(
        query_klines=[{"close": 1.0}],
        candidate_klines_dict={"s1": [{"close": 1.0}]},
        top_k=1,
        method="returns",
    )

    assert result == [{"code": "s1", "similarity": 0.99}]
    assert gateway.last_backend_used == "index"
    assert gateway.last_meta["backend_used"] == "index"
    assert engine.calls[0]["top_k"] == 1
    assert engine.calls[0]["method"] == "returns"


@pytest.mark.asyncio
async def test_runtime_adapter_bundle_exposes_mcp_gateways():
    db = _FakeDB()
    bundle = build_mcp_runtime_adapters(
        db,
        vector_engine=_FakeVectorEngine(),
        autonomy_service=_FakeAutonomyService(),
        factor_scheduler=_FakeFactorScheduler(),
        factor_research_builder=_FakeFactorResearchBuilder,
        incubation_service=_FakeIncubationService(),
        incubation_pipeline_service=_FakeIncubationPipelineService(),
        validation_runner=_fake_validation_runner,
        risk_runner=_fake_risk_runner,
    )

    assert isinstance(bundle, MCPRuntimeAdapters)
    assert isinstance(bundle.repository, StrategyFactoryRepository)
    assert isinstance(bundle.vector_search, VectorSearchGateway)
    assert isinstance(bundle.autonomy, AutonomyGateway)
    assert isinstance(bundle.factor_research, FactorResearchGateway)
    assert isinstance(bundle.incubation, IncubationGateway)
    assert isinstance(bundle.validation, ValidationGateway)
    assert isinstance(bundle.risk, RiskGateway)

    autonomy_result = await bundle.autonomy.generate_factory_candidates(
        bundle.repository,
        {"date": "2026-03-20"},
        limit=6,
        research_task={"task_id": "t1"},
        source="strategy_factory:test",
    )
    incubation_result = await bundle.incubation.submit(
        bundle.repository,
        {"id": "sid_1"},
        source_run_id="2026-03-20",
        source="strategy_factory_submit",
        auto_apply_review=False,
    )
    factor_research_result = await bundle.factor_research.build_artifact(bundle.repository, {"date": "2026-03-20"})
    factor_refresh_result = await bundle.factor_research.refresh()
    validation_result = await bundle.validation.run_validation_report("momentum", {"lookback": 20}, bundle.repository)
    risk_result = await bundle.risk.run_risk_report("momentum", {"lookback": 20}, bundle.repository)

    assert autonomy_result["limit"] == 6
    assert autonomy_result["research_task"]["task_id"] == "t1"
    assert bundle.factor_research.status()["running"] is False
    assert factor_research_result["summary"]["active_factor_count"] == 1
    assert factor_research_result["snapshot_date"] == "2026-03-20"
    assert factor_refresh_result["computed"] == 3
    assert incubation_result["binding"]["binding"]["strategy_id"] == "sid_1"
    assert incubation_result["pipeline"]["snapshot"]["source"] == "strategy_factory_submit"
    assert validation_result["strategy_type"] == "momentum"
    assert risk_result["params"]["lookback"] == 20


class _NarrowAutonomyService:
    async def generate_factory_candidates(self, db, snapshot, *, limit=4):
        return {
            "db_type": type(db).__name__,
            "snapshot": dict(snapshot),
            "limit": limit,
        }


class _BuggyAutonomyService:
    async def generate_factory_candidates(self, db, snapshot, *, limit=4):
        raise TypeError("internal autonomy failure")


@pytest.mark.asyncio
async def test_autonomy_gateway_filters_unsupported_kwargs_without_typeerror_retries():
    db = _FakeDB()
    gateway = MCPAutonomyGatewayImpl(_NarrowAutonomyService())

    result = await gateway.generate_factory_candidates(
        db,
        {"date": "2026-03-20"},
        limit=7,
        research_task={"task_id": "t1"},
        source="strategy_factory:test",
    )

    assert result["db_type"] == "MCPStrategyFactoryRepositoryAdapter"
    assert result["limit"] == 7
    assert result["snapshot"]["date"] == "2026-03-20"


@pytest.mark.asyncio
async def test_autonomy_gateway_preserves_internal_typeerrors():
    db = _FakeDB()
    gateway = MCPAutonomyGatewayImpl(_BuggyAutonomyService())

    with pytest.raises(TypeError, match="internal autonomy failure"):
        await gateway.generate_factory_candidates(db, {"date": "2026-03-20"})
