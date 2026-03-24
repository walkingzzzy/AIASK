from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from akshare_mcp.tools.managers import data_sync_manager as manager_mod


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.schedule_rows = []

    @staticmethod
    def _normalize_query(query) -> str:
        return " ".join(str(query).split())

    async def execute(self, query, *args):
        normalized = self._normalize_query(query)
        self.executed.append((normalized, args))

        if "INSERT INTO sync_schedules" in normalized:
            self.schedule_rows.append(
                {
                    "schedule_id": args[0],
                    "task_type": args[1],
                    "codes": list(args[2] or []),
                    "schedule": args[3],
                    "params": json.loads(args[4]),
                    "enabled": bool(args[5]),
                    "next_run": args[6],
                    "last_run": None,
                    "created_at": datetime.now().astimezone(),
                }
            )
        elif "UPDATE sync_schedules SET last_run = $2, next_run = $3" in normalized:
            schedule_id = args[0]
            for row in self.schedule_rows:
                if row["schedule_id"] == schedule_id:
                    row["last_run"] = args[1]
                    row["next_run"] = args[2]
                    break

        return "OK"

    async def fetchval(self, query, *args):
        normalized = self._normalize_query(query)
        if "SELECT COUNT(*) FROM sync_tasks WHERE status = 'pending'" in normalized:
            return 0
        if "SELECT COUNT(*) FROM sync_tasks WHERE status = 'running'" in normalized:
            return 0
        if "SELECT COUNT(*) FROM sync_schedules WHERE enabled = true AND task_type = $1" in normalized:
            task_type = str(args[0])
            return sum(
                1
                for row in self.schedule_rows
                if row.get("enabled") and str(row.get("task_type") or "") == task_type
            )
        if "SELECT COUNT(*) FROM sync_schedules" in normalized:
            now = datetime.now().astimezone()
            return sum(
                1
                for row in self.schedule_rows
                if row.get("enabled") and (row.get("next_run") is None or row.get("next_run") <= now)
            )
        if "SELECT MIN(next_run) FROM sync_schedules" in normalized:
            enabled_runs = [row.get("next_run") for row in self.schedule_rows if row.get("enabled") and row.get("next_run")]
            return min(enabled_runs) if enabled_runs else None
        return 0

    async def fetch(self, query, *args):
        normalized = self._normalize_query(query)
        if "SELECT * FROM sync_schedules" not in normalized:
            return []

        rows = [dict(row) for row in self.schedule_rows]
        if "WHERE enabled = true AND (next_run IS NULL OR next_run <= $1)" in normalized:
            now = args[0]
            limit = args[1]
            rows = [row for row in rows if row.get("enabled") and (row.get("next_run") is None or row.get("next_run") <= now)]
            return rows[:limit]
        if "WHERE enabled = true ORDER BY COALESCE(next_run, created_at) ASC LIMIT $1" in normalized:
            limit = args[0]
            rows = [row for row in rows if row.get("enabled")]
            return rows[:limit]
        if "WHERE enabled = $1 ORDER BY created_at DESC LIMIT $2" in normalized:
            enabled = bool(args[0])
            limit = args[1]
            rows = [row for row in rows if bool(row.get("enabled")) is enabled]
            return rows[:limit]
        if "ORDER BY created_at DESC LIMIT $1" in normalized:
            limit = args[0]
            return rows[:limit]
        return rows

    async def fetchrow(self, query, *args):
        return None


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDb:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _AcquireCtx(self.conn)


@pytest.mark.asyncio
async def test_data_sync_manager_supports_core_market_sync_without_codes(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    async def _fake_sync_core_market_now(kwargs):
        return {
            "success": 1,
            "failed": 0,
            "errors": [],
            "exit_code": 0,
            "args": kwargs,
            "market_aux": {
                "north_fund_flow": {"count": 10, "max_date": "2026-03-20"},
            },
        }

    monkeypatch.setattr(manager_mod, "_sync_core_market_now", _fake_sync_core_market_now)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="sync",
        kwargs=json.dumps({"type": "core_market", "years": 1, "north_days": 30, "margin_days": 15}),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "core_market"
    assert data["status"] == "completed"
    assert data["results"]["exit_code"] == 0
    assert any("INSERT INTO sync_tasks" in item[0] for item in db.conn.executed)
    assert any("UPDATE sync_tasks" in item[0] for item in db.conn.executed)


@pytest.mark.asyncio
async def test_data_sync_manager_supports_vector_backfill_market_docs_sync(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    async def _fake_vector_backfill(kwargs):
        return {
            "success": 1,
            "failed": 0,
            "errors": [],
            "args": kwargs,
            "backfill": {
                "saved_docs": 12,
                "saved_chunks": 28,
                "embedded_chunks": 28,
            },
            "market_aux": {
                "market_documents": 12,
                "market_doc_chunks": 28,
                "vector_profiles": 28,
            },
        }

    monkeypatch.setattr(manager_mod, "_sync_vector_backfill_market_docs_now", _fake_vector_backfill)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="sync",
        kwargs=json.dumps(
            {
                "type": "vector_backfill_market_docs",
                "doc_types": ["news", "research"],
                "limit": 200,
                "batch_size": 50,
                "embed": True,
            }
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "vector_backfill_market_docs"
    assert data["status"] == "completed"
    assert data["results"]["backfill"]["saved_docs"] == 12
    assert data["results"]["args"]["doc_types"] == ["news", "research"]
    assert any("INSERT INTO sync_tasks" in item[0] for item in db.conn.executed)
    assert any("UPDATE sync_tasks" in item[0] for item in db.conn.executed)


@pytest.mark.asyncio
async def test_data_sync_manager_supports_vector_backfill_kline_patterns_sync(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    async def _fake_kline_pattern_backfill(kwargs):
        return {
            "success": 1,
            "failed": 0,
            "errors": [],
            "args": kwargs,
            "backfill": {
                "saved_windows": 30,
                "saved_profiles": 30,
                "processed_codes": 10,
            },
            "market_aux": {
                "kline_pattern_windows": 30,
                "vector_profiles_kline_patterns": 30,
            },
        }

    monkeypatch.setattr(manager_mod, "_sync_vector_backfill_kline_patterns_now", _fake_kline_pattern_backfill)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="sync",
        kwargs=json.dumps(
            {
                "type": "vector_backfill_kline_patterns",
                "window_size": 20,
                "lookback_days": 180,
                "max_windows_per_code": 2,
                "code_limit": 50,
            }
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "vector_backfill_kline_patterns"
    assert data["status"] == "completed"
    assert data["results"]["backfill"]["saved_windows"] == 30
    assert data["results"]["args"]["window_size"] == 20


@pytest.mark.asyncio
async def test_data_sync_manager_supports_core_market_schedule_without_codes(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="schedule",
        kwargs=json.dumps(
            {
                "type": "core_market",
                "schedule": "weekly",
                "years": 2,
                "north_days": 45,
                "margin_days": 20,
                "calendar_year": 2025,
            }
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "core_market"
    assert data["schedule"] == "weekly"
    assert data["params"]["years"] == 2
    assert data["params"]["north_days"] == 45
    assert data["params"]["margin_days"] == 20
    assert data["params"]["calendar_year"] == 2025
    assert data["next_run"]
    assert any("INSERT INTO sync_schedules" in item[0] for item in db.conn.executed)
    assert db.conn.schedule_rows[0]["params"]["years"] == 2
    assert db.conn.schedule_rows[0]["next_run"] is not None


@pytest.mark.asyncio
async def test_data_sync_manager_run_due_schedules_executes_core_market_schedule(monkeypatch):
    db = _FakeDb()
    db.conn.schedule_rows.append(
        {
            "schedule_id": "schedule_core_market_due_1",
            "task_type": "core_market",
            "codes": [],
            "schedule": "daily",
            "params": {
                "years": 1,
                "north_days": 7,
                "margin_days": 5,
                "calendar_year": 2026,
                "stock_codes": ["600519"],
            },
            "enabled": True,
            "last_run": None,
            "next_run": datetime.now().astimezone() - timedelta(hours=2),
            "created_at": datetime.now().astimezone() - timedelta(days=1),
        }
    )
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    captured_payloads = []

    async def _fake_sync_core_market_now(kwargs):
        captured_payloads.append(dict(kwargs))
        return {
            "success": 1,
            "failed": 0,
            "errors": [],
            "exit_code": 0,
            "args": kwargs,
        }

    monkeypatch.setattr(manager_mod, "_sync_core_market_now", _fake_sync_core_market_now)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(action="run_due_schedules", kwargs=json.dumps({"limit": 5}))

    assert result["success"] is True
    data = result["data"]
    assert data["matched"] == 1
    assert data["executed"] == 1
    assert data["schedules"][0]["task"]["status"] == "completed"
    assert data["schedules"][0]["task"]["results"]["exit_code"] == 0
    assert captured_payloads[0]["stock_codes"] == ["600519"]
    assert captured_payloads[0]["years"] == 1
    assert db.conn.schedule_rows[0]["last_run"] is not None
    assert db.conn.schedule_rows[0]["next_run"] > datetime.now().astimezone()
    assert any("INSERT INTO sync_tasks" in item[0] for item in db.conn.executed)
    assert any("UPDATE sync_schedules SET last_run = $2, next_run = $3" in item[0] for item in db.conn.executed)


@pytest.mark.asyncio
async def test_data_sync_manager_supports_factor_context_sync(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    async def _fake_sync_factor_context_now(kwargs):
        return {
            "success": 1,
            "failed": 0,
            "errors": [],
            "exit_code": 0,
            "args": kwargs,
            "market_aux": {
                "vector_documents": 12,
                "research_reports": {"count": 3, "max_date": "2026-03-20"},
                "stock_fund_flow": {"count": 4, "max_date": "2026-03-21"},
            },
        }

    monkeypatch.setattr(manager_mod, "_sync_factor_context_now", _fake_sync_factor_context_now)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="sync",
        kwargs=json.dumps(
            {
                "type": "factor_context",
                "codes": ["600519", "000858"],
                "news_days": 15,
                "notice_days": 10,
                "item_limit": 6,
            }
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "factor_context"
    assert data["status"] == "completed"
    assert data["results"]["exit_code"] == 0
    assert data["results"]["args"]["codes"] == ["600519", "000858"]
    assert data["results"]["args"]["news_days"] == 15
    assert any("INSERT INTO sync_tasks" in item[0] for item in db.conn.executed)
    assert any("UPDATE sync_tasks" in item[0] for item in db.conn.executed)


@pytest.mark.asyncio
async def test_data_sync_manager_supports_factor_context_sync_without_codes(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    async def _fake_sync_factor_context_now(kwargs):
        return {
            "success": 1,
            "failed": 0,
            "errors": [],
            "exit_code": 0,
            "args": kwargs,
        }

    monkeypatch.setattr(manager_mod, "_sync_factor_context_now", _fake_sync_factor_context_now)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="sync",
        kwargs=json.dumps(
            {
                "type": "factor_context",
                "scope_sources": "representative,active_pool,factory_targets",
                "active_pool_limit": 8,
                "task_run_limit": 20,
                "news_days": 15,
                "notice_days": 10,
                "item_limit": 6,
            }
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "factor_context"
    assert data["codes_count"] == 0
    assert data["results"]["args"]["scope_sources"] == "representative,active_pool,factory_targets"
    assert data["results"]["args"]["active_pool_limit"] == 8
    assert data["results"]["args"]["task_run_limit"] == 20


@pytest.mark.asyncio
async def test_data_sync_manager_supports_factor_context_schedule(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="schedule",
        kwargs=json.dumps(
            {
                "type": "factor_context",
                "codes": ["600519", "000858"],
                "schedule": "daily",
                "news_days": 14,
                "notice_days": 7,
                "item_limit": 5,
            }
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "factor_context"
    assert data["schedule"] == "daily"
    assert data["codes_count"] == 2
    assert data["params"]["news_days"] == 14
    assert data["params"]["notice_days"] == 7
    assert data["params"]["item_limit"] == 5
    assert data["next_run"]
    assert any("INSERT INTO sync_schedules" in item[0] for item in db.conn.executed)
    assert db.conn.schedule_rows[0]["params"]["news_days"] == 14
    assert db.conn.schedule_rows[0]["codes"] == ["600519", "000858"]


@pytest.mark.asyncio
async def test_data_sync_manager_supports_factor_context_schedule_without_codes(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="schedule",
        kwargs=json.dumps(
            {
                "type": "factor_context",
                "schedule": "daily",
                "scope_sources": "representative,active_pool,factory_targets",
                "active_pool_limit": 9,
                "task_run_limit": 18,
                "news_days": 14,
                "notice_days": 7,
                "item_limit": 5,
            }
        ),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["task_type"] == "factor_context"
    assert data["codes_count"] == 0
    assert data["params"]["scope_sources"] == "representative,active_pool,factory_targets"
    assert data["params"]["active_pool_limit"] == 9
    assert data["params"]["task_run_limit"] == 18
    assert db.conn.schedule_rows[0]["params"]["scope_sources"] == "representative,active_pool,factory_targets"


@pytest.mark.asyncio
async def test_data_sync_manager_run_due_schedules_executes_factor_context_schedule(monkeypatch):
    db = _FakeDb()
    db.conn.schedule_rows.append(
        {
            "schedule_id": "schedule_factor_context_due_1",
            "task_type": "factor_context",
            "codes": ["600519", "000858"],
            "schedule": "daily",
            "params": {
                "news_days": 21,
                "notice_days": 10,
                "item_limit": 4,
            },
            "enabled": True,
            "last_run": None,
            "next_run": datetime.now().astimezone() - timedelta(hours=2),
            "created_at": datetime.now().astimezone() - timedelta(days=1),
        }
    )
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    captured_payloads = []

    async def _fake_sync_factor_context_now(kwargs):
        captured_payloads.append(dict(kwargs))
        return {
            "success": 1,
            "failed": 0,
            "errors": [],
            "exit_code": 0,
            "args": kwargs,
        }

    monkeypatch.setattr(manager_mod, "_sync_factor_context_now", _fake_sync_factor_context_now)

    mcp = _DummyMCP()
    manager_mod.register_data_sync_manager(mcp)
    result = await mcp.data_sync_manager(
        action="run_due_schedules",
        kwargs=json.dumps({"limit": 5, "task_type": "factor_context"}),
    )

    assert result["success"] is True
    data = result["data"]
    assert data["matched"] == 1
    assert data["executed"] == 1
    assert data["schedules"][0]["task"]["status"] == "completed"
    assert data["schedules"][0]["task"]["results"]["exit_code"] == 0
    assert captured_payloads[0]["codes"] == ["600519", "000858"]
    assert captured_payloads[0]["news_days"] == 21
    assert captured_payloads[0]["notice_days"] == 10
    assert db.conn.schedule_rows[0]["last_run"] is not None
    assert db.conn.schedule_rows[0]["next_run"] > datetime.now().astimezone()
    assert any("INSERT INTO sync_tasks" in item[0] for item in db.conn.executed)
    assert any("UPDATE sync_schedules SET last_run = $2, next_run = $3" in item[0] for item in db.conn.executed)


@pytest.mark.asyncio
async def test_run_runtime_data_warmup_bootstraps_missing_schedules(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(manager_mod, "get_db", lambda: db)

    async def _fake_sync_core_market_now(kwargs):
        return {"success": 1, "failed": 0, "errors": [], "exit_code": 0, "args": kwargs}

    async def _fake_sync_factor_context_now(kwargs):
        return {"success": 1, "failed": 0, "errors": [], "exit_code": 0, "args": kwargs}

    monkeypatch.setattr(manager_mod, "_sync_core_market_now", _fake_sync_core_market_now)
    monkeypatch.setattr(manager_mod, "_sync_factor_context_now", _fake_sync_factor_context_now)

    result = await manager_mod.run_runtime_data_warmup(
        task_type="core_market,factor_context",
        source="test_runtime",
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["matched"] == 2
    assert result["executed"] == 2
    assert result["bootstrapped_task_types"] == ["core_market", "factor_context"]
    assert len(result["bootstrapped_schedules"]) == 2
    assert {row["task_type"] for row in db.conn.schedule_rows} == {"core_market", "factor_context"}
    factor_context_schedule = next(row for row in db.conn.schedule_rows if row["task_type"] == "factor_context")
    assert factor_context_schedule["params"]["scope_sources"] == "explicit,representative,active_pool,factory_targets"
    assert any("INSERT INTO sync_schedules" in item[0] for item in db.conn.executed)
    assert any("INSERT INTO sync_tasks" in item[0] for item in db.conn.executed)
