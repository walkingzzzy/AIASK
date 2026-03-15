import importlib.util
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock


def test_get_db_registers_shutdown_hook_once(monkeypatch):
    import akshare_mcp.storage.timescaledb as db_mod

    class _FakeAdapter:
        pass

    registered = []
    monkeypatch.setattr(db_mod, 'TimescaleDBAdapter', _FakeAdapter)
    monkeypatch.setattr(db_mod.atexit, 'register', lambda fn: registered.append(fn))
    monkeypatch.setattr(db_mod, '_db_instance', None)
    monkeypatch.setattr(db_mod, '_shutdown_registered', False)

    db1 = db_mod.get_db()
    db2 = db_mod.get_db()

    assert isinstance(db1, _FakeAdapter)
    assert db1 is db2
    assert registered == [db_mod._safe_shutdown_db_atexit]


@pytest.mark.asyncio
async def test_initialize_terminates_stale_pool_on_loop_change(monkeypatch):
    import akshare_mcp.storage.timescaledb.schema_base as schema_mod

    old_loop = object()
    current_loop = object()
    old_pool = MagicMock()
    new_pool = MagicMock()

    async def _fake_create_pool(**_kwargs):
        return new_pool

    monkeypatch.setattr(schema_mod, 'ASYNCPG_AVAILABLE', True)
    monkeypatch.setattr(schema_mod.asyncio, 'get_running_loop', lambda: current_loop)
    monkeypatch.setattr(schema_mod.asyncpg, 'create_pool', _fake_create_pool)
    monkeypatch.setattr(schema_mod.SchemaBase, '_init_tables', AsyncMock())

    schema = schema_mod.SchemaBase()
    schema.pool = old_pool
    schema._initialized = True
    schema._bound_loop = old_loop

    await schema.initialize()

    old_pool.terminate.assert_called_once_with()
    assert schema.pool is new_pool
    assert schema._bound_loop is current_loop
    assert schema._initialized is True


@pytest.mark.asyncio
async def test_close_falls_back_to_terminate_when_pool_close_fails():
    from akshare_mcp.storage.timescaledb.schema_base import SchemaBase

    pool = MagicMock()
    pool.close = AsyncMock(side_effect=RuntimeError('loop closed'))

    schema = SchemaBase()
    schema.pool = pool
    schema._initialized = True
    schema._bound_loop = object()

    await schema.close()

    pool.close.assert_awaited_once()
    pool.terminate.assert_called_once_with()
    assert schema.pool is None
    assert schema._initialized is False


def test_schema_base_uses_compact_pool_defaults_for_tool_only_profile(monkeypatch):
    from akshare_mcp.storage.timescaledb.schema_base import SchemaBase

    monkeypatch.setenv('AKSHARE_MCP_STARTUP_PROFILE', 'tool-only')
    monkeypatch.delenv('AKSHARE_MCP_DB_POOL_MIN', raising=False)
    monkeypatch.delenv('AKSHARE_MCP_DB_POOL_MAX', raising=False)

    config = SchemaBase()._build_db_config()

    assert config['min_size'] == 1
    assert config['max_size'] == 2
    assert config['server_settings']['application_name'] == 'akshare-mcp:tool-only'


def test_schema_base_pool_limits_honor_env_overrides(monkeypatch):
    from akshare_mcp.storage.timescaledb.schema_base import SchemaBase

    monkeypatch.setenv('AKSHARE_MCP_STARTUP_PROFILE', 'full')
    monkeypatch.setenv('AKSHARE_MCP_DB_POOL_MIN', '3')
    monkeypatch.setenv('AKSHARE_MCP_DB_POOL_MAX', '2')

    config = SchemaBase()._build_db_config()

    assert config['min_size'] == 3
    assert config['max_size'] == 3
    assert config['server_settings']['application_name'] == 'akshare-mcp:full'


@pytest.mark.asyncio
async def test_await_with_db_cleanup_closes_db(monkeypatch):
    import akshare_mcp.storage.timescaledb as db_mod

    close_mock = AsyncMock()
    monkeypatch.setattr(db_mod, 'close_db', close_mock)

    async def _probe():
        return 'ok'

    result = await db_mod.await_with_db_cleanup(_probe())

    assert result == 'ok'
    close_mock.assert_awaited_once()


@pytest.mark.parametrize(
    ('script_path', 'entry_call'),
    [
        ('sync_daily/engine.py', 'run_with_db_cleanup(main())'),
        ('sync_daily/sync_complete.py', 'run_with_db_cleanup(main())'),
        ('sync_daily/sync_historical.py', 'run_with_db_cleanup(main())'),
        ('sync_daily/sync_init.py', 'run_with_db_cleanup(main())'),
        ('scripts/archive/_fix_schema.py', 'run_with_db_cleanup(fix())'),
    ],
)
def test_sync_daily_entrypoints_use_run_with_db_cleanup(script_path, entry_call):
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / script_path).read_text(encoding='utf-8')

    assert 'from akshare_mcp.storage import run_with_db_cleanup' in source
    assert entry_call in source
    assert 'asyncio.run(main())' not in source


def _load_module_from_repo_path(module_name: str, relative_path: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_verify_db_connection_closes_connection_on_query_failure(monkeypatch):
    mod = _load_module_from_repo_path('verify_db_connection_test_mod', 'scripts/verify_db_connection.py')

    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=RuntimeError('boom'))
    conn.close = AsyncMock()
    monkeypatch.setattr(mod.asyncpg, 'connect', AsyncMock(return_value=conn))

    result = await mod.check_connection('postgres', 'password', 'stockdb', 'localhost', 5432)

    assert result is False
    conn.close.assert_awaited_once()
