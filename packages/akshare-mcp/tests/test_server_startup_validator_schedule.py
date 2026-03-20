from unittest.mock import MagicMock

import akshare_mcp.server as server_mod


def test_start_startup_validator_background_uses_daemon_thread(monkeypatch):
    validator = MagicMock()

    async def _run_async():
        return {"status": "ok"}

    validator.run_async = _run_async
    captured = {}

    def _fake_runner(coro_factory, name):
        captured["factory"] = coro_factory
        captured["name"] = name
        return object()

    monkeypatch.setattr(
        "akshare_mcp.services.startup_validator.get_startup_validator",
        lambda: validator,
    )
    monkeypatch.setattr(server_mod, "_run_async_task_in_daemon_thread", _fake_runner)

    server_mod._start_startup_validator_background()

    assert captured["factory"] is validator.run_async
    assert captured["name"] == "startup-validator"


def test_main_schedules_startup_validator_via_helper(monkeypatch):
    scheduled = {}

    monkeypatch.setenv("AKSHARE_MCP_STARTUP_PROFILE", "full")
    monkeypatch.setenv("FACTOR_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("MATCHING_ENGINE_ENABLED", "false")
    monkeypatch.setenv("NAV_ENGINE_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_TRACKER_ENABLED", "false")
    monkeypatch.setenv("STRATEGY_FACTORY_ENABLED", "false")
    monkeypatch.setenv("DATA_SYNC_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("STARTUP_VALIDATION_ENABLED", "true")

    monkeypatch.setattr(server_mod, "_enforce_http_security_baseline", lambda: None)

    def _fake_schedule():
        scheduled["startup_validator"] = True
        return object()

    monkeypatch.setattr(server_mod, "_start_startup_validator_background", _fake_schedule)
    monkeypatch.setattr(server_mod.mcp, "run", lambda: scheduled.setdefault("mcp_run", True))

    server_mod.main()

    assert scheduled["startup_validator"] is True
    assert scheduled["mcp_run"] is True
