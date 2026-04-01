import asyncio
from unittest.mock import MagicMock

import akshare_mcp.server as server_mod


def test_start_startup_validator_background_returns_shutdown_tracked_task(monkeypatch):
    validator = MagicMock()
    started = asyncio.Event()
    finished = asyncio.Event()

    async def _run_async():
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        finally:
            finished.set()
        return {"status": "ok"}

    validator.run_async = _run_async

    monkeypatch.setattr(
        "akshare_mcp.services.startup_validator.get_startup_validator",
        lambda: validator,
    )

    async def _exercise():
        handle = server_mod._start_startup_validator_background()
        await asyncio.wait_for(started.wait(), timeout=1)
        await handle.shutdown()
        await asyncio.wait_for(finished.wait(), timeout=1)

    asyncio.run(_exercise())


def test_main_schedules_startup_validator_via_helper(monkeypatch):
    scheduled = {}
    remembered = []

    monkeypatch.setenv("AKSHARE_MCP_STARTUP_PROFILE", "full")
    monkeypatch.setenv("FACTOR_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("MATCHING_ENGINE_ENABLED", "false")
    monkeypatch.setenv("NAV_ENGINE_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_TRACKER_ENABLED", "false")
    monkeypatch.setenv("STRATEGY_FACTORY_ENABLED", "false")
    monkeypatch.setenv("DATA_SYNC_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("STARTUP_VALIDATION_ENABLED", "true")

    monkeypatch.setattr(server_mod, "_enforce_http_security_baseline", lambda: None)
    monkeypatch.setattr(server_mod, "_acquire_background_services_leader", lambda: True)
    monkeypatch.setattr(server_mod, "_release_background_services_leader", lambda: None)
    monkeypatch.setattr(server_mod, "_shutdown_completed", False)
    server_mod._started_background_services.clear()
    monkeypatch.setattr(
        server_mod,
        "_remember_started_service",
        lambda name, service: remembered.append((name, service)) or service,
    )

    def _fake_schedule():
        scheduled["startup_validator"] = True
        return MagicMock()

    monkeypatch.setattr(server_mod, "_start_startup_validator_background", _fake_schedule)

    async def _noop_transport(*_args, **_kwargs):
        scheduled["mcp_run"] = True

    monkeypatch.setattr(server_mod, "_run_mcp_transport_async", _noop_transport)

    server_mod.main()

    assert scheduled["startup_validator"] is True
    assert scheduled["mcp_run"] is True
    assert any(name == "StartupValidator" for name, _service in remembered)


def test_main_skips_background_services_when_not_leader(monkeypatch):
    scheduled = {}

    monkeypatch.setenv("AKSHARE_MCP_STARTUP_PROFILE", "full")
    monkeypatch.setenv("FACTOR_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("MATCHING_ENGINE_ENABLED", "false")
    monkeypatch.setenv("NAV_ENGINE_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_TRACKER_ENABLED", "false")
    monkeypatch.setenv("STRATEGY_FACTORY_ENABLED", "false")
    monkeypatch.setenv("DATA_SYNC_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("STARTUP_VALIDATION_ENABLED", "true")

    monkeypatch.setattr(server_mod, "_enforce_http_security_baseline", lambda: None)
    monkeypatch.setattr(server_mod, "_acquire_background_services_leader", lambda: False)
    monkeypatch.setattr(server_mod, "_release_background_services_leader", lambda: None)
    monkeypatch.setattr(server_mod, "_shutdown_completed", False)
    server_mod._started_background_services.clear()

    class _DummyScheduler:
        def start(self):
            scheduled["scheduler_started"] = True

    monkeypatch.setattr(server_mod, "get_factor_scheduler", lambda: _DummyScheduler())
    monkeypatch.setattr(server_mod, "_start_startup_validator_background", lambda: scheduled.setdefault("startup_validator", True))

    async def _noop_transport(*_args, **_kwargs):
        scheduled["mcp_run"] = True

    monkeypatch.setattr(server_mod, "_run_mcp_transport_async", _noop_transport)

    server_mod.main()

    assert "scheduler_started" not in scheduled
    assert "startup_validator" not in scheduled
    assert scheduled["mcp_run"] is True


def test_main_keeps_worker_profile_lightweight_even_with_heavy_tools(monkeypatch):
    scheduled = {}

    monkeypatch.setenv("AKSHARE_MCP_STARTUP_PROFILE", "worker")
    monkeypatch.setenv("FACTOR_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("MATCHING_ENGINE_ENABLED", "true")
    monkeypatch.setenv("NAV_ENGINE_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_TRACKER_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_FACTORY_ENABLED", "true")
    monkeypatch.setenv("DATA_SYNC_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("STARTUP_VALIDATION_ENABLED", "true")

    monkeypatch.setattr(server_mod, "_enforce_http_security_baseline", lambda: None)
    monkeypatch.setattr(server_mod, "_acquire_background_services_leader", lambda: scheduled.setdefault("leader_lock", True))
    monkeypatch.setattr(server_mod, "_release_background_services_leader", lambda: None)
    monkeypatch.setattr(server_mod, "_shutdown_completed", False)
    server_mod._started_background_services.clear()

    monkeypatch.setattr(server_mod, "_start_startup_validator_background", lambda: scheduled.setdefault("startup_validator", True))
    monkeypatch.setattr(server_mod, "get_factor_scheduler", lambda: scheduled.setdefault("scheduler", True))
    monkeypatch.setattr(server_mod, "get_matching_engine", lambda: scheduled.setdefault("matching", True))
    monkeypatch.setattr(server_mod, "get_nav_engine", lambda: scheduled.setdefault("nav", True))
    monkeypatch.setattr(server_mod, "get_signal_tracker", lambda: scheduled.setdefault("signal", True))

    async def _noop_transport(*_args, **_kwargs):
        scheduled["mcp_run"] = True

    monkeypatch.setattr(server_mod, "_run_mcp_transport_async", _noop_transport)

    server_mod.main()

    assert "leader_lock" not in scheduled
    assert "startup_validator" not in scheduled
    assert "scheduler" not in scheduled
    assert "matching" not in scheduled
    assert "nav" not in scheduled
    assert "signal" not in scheduled
    assert scheduled["mcp_run"] is True
