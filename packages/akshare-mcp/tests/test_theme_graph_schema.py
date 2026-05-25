"""PR-A smoke tests: theme graph schema + seed idempotency.

This test file is part of the event-driven theme-linkage upgrade plan
(see ``事件驱动主题联动-结合当前代码升级方案-2026-05-24.md`` Phase 0).

Design principle (Phase 0 verification line 1):
    "新建临时 SQLite 后,真实 adapter 初始化能创建全部事件驱动表"

That is, the test must drive the real ``SQLiteAdapter`` so that any future
DDL change is exercised. Earlier revisions of this file embedded raw
``CREATE TABLE`` strings copied from ``schema_strategy_parts/queries.py``.
That bypassed the very migration code we want to validate, so the
embedded DDL was removed. If you find yourself adding ``CREATE TABLE`` to
this file again, stop — extend the real schema module instead.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Make local ``akshare_mcp`` (compat shell that aliases the canonical
# ``aiask_quant_core.storage.sqlite`` package) and ``aiask_quant_core``
# both importable when this test is run via ``pytest`` from any cwd.
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
QUANT_CORE_SRC = WORKSPACE_ROOT / "packages" / "aiask-quant-core" / "src"
for candidate in (SRC, QUANT_CORE_SRC):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a fresh tmp path used by both the real adapter and seed runs."""

    return tmp_path / "test_theme_graph.sqlite3"


@pytest.fixture
def initialized_db(tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Drive the real ``SQLiteAdapter`` so it creates every strategy table.

    Returns the path of the initialized database. Subsequent tests can
    open it via raw ``sqlite3.connect`` for assertions.
    """

    monkeypatch.setenv("AKSHARE_MCP_SQLITE_PATH", str(tmp_db_path))
    monkeypatch.setenv("AIASK_SQLITE_PATH", str(tmp_db_path))

    from aiask_quant_core.storage.sqlite import SQLiteAdapter

    adapter = SQLiteAdapter(path=tmp_db_path)

    async def _setup() -> None:
        try:
            await adapter.initialize()
        finally:
            try:
                await adapter.close()
            except Exception:
                pass

    asyncio.run(_setup())
    return tmp_db_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# These five tables are the minimum surface area that the event-driven
# theme-linkage plan requires (§2 of the upgrade plan).
EXPECTED_TABLES = (
    "strategy_factory_theme_nodes",
    "strategy_factory_theme_edges",
    "strategy_factory_event_injections",
    "strategy_factory_event_task_lineage",
    "strategy_factory_theme_exposure",
)

# Legacy ``LocalEventDrivenResearchEngine`` writes here. The plan keeps
# them around during the migration window, so the real adapter must keep
# creating them too.
LEGACY_TABLES = (
    "strategy_factory_event_clusters",
    "strategy_factory_event_signals",
)

# The plan §4.3/§6 Phase 0.5 forbids any Tushare-shaped local cache. If
# a future PR accidentally re-introduces this table, this test must fail.
FORBIDDEN_TABLES = (
    "strategy_factory_company_mainbz",
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_real_adapter_creates_event_driven_tables(initialized_db: Path) -> None:
    """``SQLiteAdapter.initialize()`` must create the five event-driven tables.

    This replaces the previous test which embedded copy-pasted DDL — that
    version could never detect schema drift inside
    ``schema_strategy_parts/queries.py``.
    """

    conn = sqlite3.connect(str(initialized_db))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    missing = [t for t in EXPECTED_TABLES if t not in names]
    assert not missing, f"adapter init left these tables uncreated: {missing}"


def test_real_adapter_keeps_legacy_event_tables(initialized_db: Path) -> None:
    """Legacy cluster/signal tables must coexist with the new event_injections."""

    conn = sqlite3.connect(str(initialized_db))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    missing = [t for t in LEGACY_TABLES if t not in names]
    assert not missing, (
        "legacy cluster/signal tables disappeared; cutover must be planned, "
        f"not implicit: {missing}"
    )


def test_no_forbidden_tushare_shaped_cache(initialized_db: Path) -> None:
    """Phase 0.5 禁令: 不允许出现 strategy_factory_company_mainbz."""

    conn = sqlite3.connect(str(initialized_db))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    leaked = [t for t in FORBIDDEN_TABLES if t in names]
    assert not leaked, (
        "Phase 0.5 forbids Tushare-shaped local caches in the event-driven plan; "
        f"these tables are not allowed: {leaked}"
    )


def test_event_injections_has_approver_columns(initialized_db: Path) -> None:
    """方案 §6 Phase 0 验收: approver_id / approved_at 列必须存在.

    DAO 写入它们是 PR-B1 的工作,但列必须先就位。
    """

    conn = sqlite3.connect(str(initialized_db))
    try:
        cols = _table_columns(conn, "strategy_factory_event_injections")
    finally:
        conn.close()

    for required in ("approver_id", "approved_at"):
        assert required in cols, (
            f"{required} column missing on strategy_factory_event_injections; "
            "PR-B1 cannot persist approval state without it."
        )


def test_event_task_lineage_has_gate_columns(initialized_db: Path) -> None:
    """方案 §6 Phase 0 验收: lineage 表必须支持 Gate 状态写回."""

    conn = sqlite3.connect(str(initialized_db))
    try:
        cols = _table_columns(conn, "strategy_factory_event_task_lineage")
    finally:
        conn.close()

    for required in (
        "gate_1_passed",
        "gate_2_passed",
        "gate_3_passed",
        "strategies_submitted",
    ):
        assert required in cols, (
            f"{required} column missing on strategy_factory_event_task_lineage; "
            "Phase 0 lineage update method cannot land without it."
        )


def test_seed_idempotent_against_real_schema(initialized_db: Path) -> None:
    """Seed must run twice without dup, on top of a real adapter-built schema."""

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from seed_strategy_factory_theme_graph import (  # type: ignore[import-not-found]
        seed,
        THEME_NODES,
        THEME_EDGES,
    )

    asyncio.run(seed(str(initialized_db)))
    asyncio.run(seed(str(initialized_db)))  # second run should be a no-op

    conn = sqlite3.connect(str(initialized_db))
    try:
        node_count = conn.execute(
            "SELECT COUNT(*) FROM strategy_factory_theme_nodes"
        ).fetchone()[0]
        edge_count = conn.execute(
            "SELECT COUNT(*) FROM strategy_factory_theme_edges"
        ).fetchone()[0]
    finally:
        conn.close()

    assert node_count == len(THEME_NODES) == 15, (
        f"expected 15 seed nodes, got {node_count}"
    )
    assert edge_count == len(THEME_EDGES) == 10, (
        f"expected 10 seed edges, got {edge_count}"
    )


def test_seed_node_fields_round_trip(initialized_db: Path) -> None:
    """Seed must preserve breadth / horizon / industry_tags exactly as declared."""

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from seed_strategy_factory_theme_graph import seed  # type: ignore[import-not-found]

    asyncio.run(seed(str(initialized_db)))

    conn = sqlite3.connect(str(initialized_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT theme_code, theme_name, breadth, default_horizon, industry_tags "
            "FROM strategy_factory_theme_nodes WHERE theme_code = 'upstream_oil_gas'"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "seed did not produce upstream_oil_gas node"
    assert row["breadth"] == "narrow"
    assert row["default_horizon"] == "swing_1_5d"
    assert "石油开采" in row["industry_tags"]


def test_edge_unique_constraint_against_real_schema(initialized_db: Path) -> None:
    """Verify edge UNIQUE(source, target, relation_type) enforced by real DDL."""

    conn = sqlite3.connect(str(initialized_db))
    try:
        conn.execute(
            "INSERT INTO strategy_factory_theme_edges "
            "(source_theme_code, target_theme_code, relation_type, direction_sign) "
            "VALUES ('a', 'b', 'amplifies', 1)"
        )
        conn.commit()

        # Duplicate triple should be ignored, even if direction_sign differs.
        conn.execute(
            "INSERT OR IGNORE INTO strategy_factory_theme_edges "
            "(source_theme_code, target_theme_code, relation_type, direction_sign) "
            "VALUES ('a', 'b', 'amplifies', -1)"
        )
        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM strategy_factory_theme_edges "
            "WHERE source_theme_code='a' AND target_theme_code='b' "
            "AND relation_type='amplifies'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 1, "UNIQUE constraint did not collapse duplicate triple"


def test_test_file_does_not_embed_ddl() -> None:
    """Self-check: this very file must never reintroduce ``CREATE TABLE`` DDL.

    Embedded DDL was the bug PR-A is fixing; future maintainers should
    feel friction immediately if they paste a CREATE TABLE in here.

    The check looks for ``conn.execute(`` immediately followed (within a
    short window) by a SQL string containing ``CREATE TABLE``. That avoids
    false positives from prose / docstrings / assert messages, which are
    fine and historically necessary to explain *why* the DDL was removed.
    """

    import re

    text = Path(__file__).read_text(encoding="utf-8")
    pattern = re.compile(
        r"conn\s*\.\s*execute\s*\(\s*[fr]?[\"']{1,3}[^\"']*?CREATE\s+TABLE",
        re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(text)
    assert not matches, (
        "test_theme_graph_schema.py must not embed CREATE TABLE statements; "
        "drive SQLiteAdapter().initialize() instead. "
        f"Found {len(matches)} embedded DDL call(s)."
    )


# ---------------------------------------------------------------------------
# PR-B1 (2026-05-24): DAO contract tests
#
# Phase 0 验收余项 — 全部依赖 ``initialized_db`` fixture (= real adapter):
#   - factory_event_create / list / record_outcome 在真实 DAO 上 CRUD
#   - factory_event_approve 持久化 approver_id / approved_at + 自审被拒绝
#   - outbox / 消费状态可以按 dedupe_key 幂等处理同一事件
#   - upsert_theme_exposure / bulk_upsert_theme_exposure 行为一致
#   - update_event_task_lineage_gates 部分更新不重置已通过 Gate
# ---------------------------------------------------------------------------


def _build_adapter(db_path: Path):
    """Build a fresh ``SQLiteAdapter`` for tests that need DAO calls."""

    from aiask_quant_core.storage.sqlite import SQLiteAdapter

    return SQLiteAdapter(path=db_path)


def _run(coro):
    return asyncio.run(coro)


async def _seed_tdx_only_exposure_fixture(adapter) -> None:
    """Seed local TDX/cache tables used by the Phase 6 v1 exposure path."""

    async with adapter.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stocks
                (stock_code, stock_name, market, sector, industry, list_date,
                 market_cap, tdx_industry, list_status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT(stock_code) DO UPDATE SET
                stock_name = EXCLUDED.stock_name,
                market = EXCLUDED.market,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                market_cap = EXCLUDED.market_cap,
                tdx_industry = EXCLUDED.tdx_industry,
                list_status = EXCLUDED.list_status
            """,
            "600100",
            "AI Chip Co",
            "SH",
            "Technology",
            "Semiconductor",
            "2020-01-01",
            120.0,
            "Semiconductor",
            "L",
        )
        await conn.execute(
            """
            INSERT INTO stocks
                (stock_code, stock_name, market, sector, industry, list_date,
                 market_cap, tdx_industry, list_status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT(stock_code) DO UPDATE SET
                stock_name = EXCLUDED.stock_name,
                market = EXCLUDED.market,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                market_cap = EXCLUDED.market_cap,
                tdx_industry = EXCLUDED.tdx_industry,
                list_status = EXCLUDED.list_status
            """,
            "600200",
            "Low Liquidity Co",
            "SH",
            "Technology",
            "Semiconductor",
            "2021-01-01",
            1.0,
            "Semiconductor",
            "L",
        )
        await conn.execute(
            """
            INSERT INTO tdx_relation (code, block_code, block_name, block_type, gp_num)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT(code, block_code) DO UPDATE SET
                block_name = EXCLUDED.block_name,
                block_type = EXCLUDED.block_type,
                gp_num = EXCLUDED.gp_num
            """,
            "600100",
            "C001",
            "AI concept",
            "concept",
            50,
        )
        await conn.execute(
            """
            INSERT INTO tdx_relation (code, block_code, block_name, block_type, gp_num)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT(code, block_code) DO UPDATE SET
                block_name = EXCLUDED.block_name,
                block_type = EXCLUDED.block_type,
                gp_num = EXCLUDED.gp_num
            """,
            "600100",
            "I001",
            "Semiconductor",
            "industry",
            70,
        )
        await conn.execute(
            """
            INSERT INTO market_blocks (block_code, block_name, block_type, stock_count)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT(block_code, block_type) DO UPDATE SET
                block_name = EXCLUDED.block_name,
                stock_count = EXCLUDED.stock_count
            """,
            "C002",
            "AI block",
            "concept",
            20,
        )
        await conn.execute(
            """
            INSERT INTO block_stocks (block_code, stock_code, stock_name)
            VALUES ($1, $2, $3)
            ON CONFLICT(block_code, stock_code) DO UPDATE SET
                stock_name = EXCLUDED.stock_name
            """,
            "C002",
            "600100",
            "AI Chip Co",
        )
        await conn.execute(
            """
            INSERT INTO tdx_stock_extra
                (code, trade_date, turnover_rate, zsz, ltsz, tp_flag)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT(code, trade_date) DO UPDATE SET
                turnover_rate = EXCLUDED.turnover_rate,
                zsz = EXCLUDED.zsz,
                ltsz = EXCLUDED.ltsz,
                tp_flag = EXCLUDED.tp_flag
            """,
            "600100",
            "2026-05-24",
            2.5,
            120.0,
            80.0,
            "",
        )
        await conn.execute(
            """
            INSERT INTO tdx_stock_extra
                (code, trade_date, turnover_rate, zsz, ltsz, tp_flag)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT(code, trade_date) DO UPDATE SET
                turnover_rate = EXCLUDED.turnover_rate,
                zsz = EXCLUDED.zsz,
                ltsz = EXCLUDED.ltsz,
                tp_flag = EXCLUDED.tp_flag
            """,
            "600200",
            "2026-05-24",
            0.01,
            1.0,
            1.0,
            "",
        )


def test_event_injection_crud_persists_approver_state(initialized_db: Path) -> None:
    """``upsert_event_injection`` must persist ``approver_id`` / ``approved_at``."""

    adapter = _build_adapter(initialized_db)

    async def scenario() -> tuple[list, list]:
        await adapter.initialize()
        try:
            await adapter.upsert_event_injection({
                "event_id": "test_evt_approver",
                "source": "manual",
                "event_name": "稀土出口管制",
                "event_type": "critical_minerals",
                "direction": "positive",
                "confidence": 0.9,
                "intensity": 0.85,
                "horizon": "swing_5_20d",
                "scope": "theme",
                "primary_themes": [{"theme_code": "rare_earth", "direction": "positive"}],
                "valid_from": "2026-05-24T00:00:00+00:00",
                "valid_until": "2026-06-13T00:00:00+00:00",
                "status": "pending_review",
                "operator_id": "operator_alice",
            })
            # Patch in approval state via a follow-up upsert (simulates handler).
            await adapter.upsert_event_injection({
                "event_id": "test_evt_approver",
                "source": "manual",
                "event_name": "稀土出口管制",
                "event_type": "critical_minerals",
                "primary_themes": [{"theme_code": "rare_earth", "direction": "positive"}],
                "confidence": 0.9,
                "intensity": 0.85,
                "horizon": "swing_5_20d",
                "scope": "theme",
                "valid_from": "2026-05-24T00:00:00+00:00",
                "valid_until": "2026-06-13T00:00:00+00:00",
                "status": "active",
                "operator_id": "operator_alice",
                "approver_id": "approver_bob",
                "approved_at": "2026-05-24T01:23:45+00:00",
            })
            pending = await adapter.list_event_injections(status="pending_review", limit=200)
            active = await adapter.list_event_injections(status="active", limit=200)
            return pending, active
        finally:
            await adapter.close()

    pending, active = _run(scenario())
    pending_ids = [e["event_id"] for e in pending]
    active_ids = [e["event_id"] for e in active]
    assert "test_evt_approver" not in pending_ids, "event must leave pending_review"
    assert "test_evt_approver" in active_ids, "event must end up active"
    target = next(e for e in active if e["event_id"] == "test_evt_approver")
    assert target.get("approver_id") == "approver_bob"
    assert target.get("approved_at") == "2026-05-24T01:23:45+00:00"
    assert target.get("operator_id") == "operator_alice"


def test_event_injection_does_not_lose_approver_on_partial_update(
    initialized_db: Path,
) -> None:
    """A later upsert without approver_id must NOT reset persisted approval."""

    adapter = _build_adapter(initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            await adapter.upsert_event_injection({
                "event_id": "test_evt_approver_keep",
                "source": "manual",
                "event_name": "AI 算力补贴",
                "event_type": "ai_semiconductor",
                "primary_themes": [{"theme_code": "ai_compute", "direction": "positive"}],
                "confidence": 0.7,
                "intensity": 0.6,
                "horizon": "swing_5_20d",
                "valid_from": "2026-05-24T00:00:00+00:00",
                "valid_until": "2026-06-13T00:00:00+00:00",
                "status": "active",
                "operator_id": "operator_alice",
                "approver_id": "approver_bob",
                "approved_at": "2026-05-24T01:23:45+00:00",
            })
            # Operator later edits the rationale only — approver state must
            # survive. The DAO uses COALESCE on approver_id/approved_at, so
            # passing them as None should preserve the existing values.
            await adapter.upsert_event_injection({
                "event_id": "test_evt_approver_keep",
                "source": "manual",
                "event_name": "AI 算力补贴 (rev)",
                "event_type": "ai_semiconductor",
                "primary_themes": [{"theme_code": "ai_compute", "direction": "positive"}],
                "confidence": 0.72,
                "intensity": 0.6,
                "horizon": "swing_5_20d",
                "valid_from": "2026-05-24T00:00:00+00:00",
                "valid_until": "2026-06-13T00:00:00+00:00",
                "status": "active",
                "rationale": "added later",
            })
            rows = await adapter.list_event_injections(status="active", limit=200)
            return next(r for r in rows if r["event_id"] == "test_evt_approver_keep")
        finally:
            await adapter.close()

    row = _run(scenario())
    assert row["approver_id"] == "approver_bob"
    assert row["approved_at"] == "2026-05-24T01:23:45+00:00"
    assert "added later" in (row.get("rationale") or "")


def test_handle_factory_event_approve_writes_db_state(initialized_db: Path) -> None:
    """The manager handler must drive DAO so approval is durable, not just envelope."""

    from aiask_quant_core.storage.sqlite import SQLiteAdapter
    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_event_approve,
        handle_factory_event_create,
        handle_factory_event_list,
    )

    adapter = SQLiteAdapter(path=initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            create = await handle_factory_event_create(
                adapter,
                {
                    "event_id": "test_evt_handler",
                    "event_name": "霍尔木兹油运封锁",
                    "event_type": "energy_shipping",
                    "direction": "positive",
                    "confidence": 0.85,
                    "intensity": 0.9,  # >= 0.8 → pending_review
                    "scope": "theme",
                    "primary_themes": [{"theme_code": "shipping_trade", "direction": "positive"}],
                    "operator_id": "operator_alice",
                },
            )
            assert create["success"] is True
            assert create["data"]["status"] == "pending_review"

            # Self-approval must be rejected.
            self_approve = await handle_factory_event_approve(
                adapter,
                {"event_id": "test_evt_handler", "approver_id": "operator_alice"},
            )
            assert self_approve.get("success") is False
            assert "self-approve" in str(self_approve.get("error", ""))

            # Missing approver_id must be rejected.
            missing = await handle_factory_event_approve(
                adapter,
                {"event_id": "test_evt_handler"},
            )
            assert missing.get("success") is False

            ok = await handle_factory_event_approve(
                adapter,
                {"event_id": "test_evt_handler", "approver_id": "approver_bob"},
            )
            assert ok["success"] is True
            assert ok["data"]["status"] == "active"
            assert ok["data"]["approved_by"] == "approver_bob"
            assert ok["data"].get("approved_at")

            listed = await handle_factory_event_list(adapter, {"status": "active"})
            return listed
        finally:
            await adapter.close()

    listed = _run(scenario())
    rows = listed["data"]["events"]
    target = next(r for r in rows if r["event_id"] == "test_evt_handler")
    assert target["approver_id"] == "approver_bob"
    assert target["approved_at"], "approved_at should be persisted, not just returned"


def test_record_outcome_updates_outcome_columns(initialized_db: Path) -> None:
    """record_outcome must set ``actual_outcome`` and ``outcome_notes`` durably."""

    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_event_create,
        handle_factory_event_record_outcome,
    )

    adapter = _build_adapter(initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            await handle_factory_event_create(
                adapter,
                {
                    "event_id": "test_evt_outcome",
                    "event_name": "黄金避险",
                    "event_type": "commodity_gold",
                    "direction": "positive",
                    "confidence": 0.7,
                    "intensity": 0.5,
                    "primary_themes": [{"theme_code": "gold", "direction": "positive"}],
                    "operator_id": "operator_carol",
                },
            )
            await handle_factory_event_record_outcome(
                adapter,
                {
                    "event_id": "test_evt_outcome",
                    "actual_outcome": "positive",
                    "outcome_notes": "黄金 ETF 上涨 4.2%",
                },
            )
            rows = await adapter.list_event_injections(limit=200)
            return next(r for r in rows if r["event_id"] == "test_evt_outcome")
        finally:
            await adapter.close()

    row = _run(scenario())
    assert row.get("actual_outcome") == "positive"
    assert "黄金 ETF" in (row.get("outcome_notes") or "")
    assert row.get("outcome_recorded_at"), "outcome_recorded_at must be set by DAO"


def test_upsert_theme_exposure_round_trip(initialized_db: Path) -> None:
    """Single-row upsert must round-trip and respect UNIQUE(symbol, theme_code)."""

    adapter = _build_adapter(initialized_db)

    async def scenario() -> list:
        await adapter.initialize()
        try:
            await adapter.upsert_theme_exposure({
                "symbol": "601857",
                "theme_code": "upstream_oil_gas",
                "exposure_score": 0.82,
                "industry_match_level": 2,
                "name_match_score": 0.6,
                "mainbz_match_score": 0.7,
                "historical_beta": 0.4,
                "evidence": {"src": "tdx_relation"},
            })
            # Second write with a higher score must update, not duplicate.
            await adapter.upsert_theme_exposure({
                "symbol": "601857",
                "theme_code": "upstream_oil_gas",
                "exposure_score": 0.91,
                "industry_match_level": 2,
                "evidence": {"src": "tdx_relation+kline"},
            })
            return await adapter.list_theme_exposure(
                theme_code="upstream_oil_gas", min_exposure=0.0, limit=10
            )
        finally:
            await adapter.close()

    rows = _run(scenario())
    matching = [r for r in rows if r["symbol"] == "601857"]
    assert len(matching) == 1, "UNIQUE(symbol, theme_code) must be enforced"
    assert abs(float(matching[0]["exposure_score"]) - 0.91) < 1e-6, "second write should overwrite"


def test_bulk_upsert_theme_exposure_idempotent(initialized_db: Path) -> None:
    """Bulk path must batch, accept the same payload twice, and return metrics."""

    adapter = _build_adapter(initialized_db)

    async def scenario() -> tuple[dict, dict, list]:
        await adapter.initialize()
        try:
            payload = [
                {"symbol": f"60{i:04d}", "theme_code": "upstream_oil_gas",
                 "exposure_score": 0.5 + (i % 5) * 0.1,
                 "industry_match_level": 1}
                for i in range(20)
            ]
            payload.append({"symbol": "", "theme_code": "skip_me"})  # invalid row
            r1 = await adapter.bulk_upsert_theme_exposure(payload, batch_size=7)
            r2 = await adapter.bulk_upsert_theme_exposure(payload, batch_size=7)
            rows = await adapter.list_theme_exposure(
                theme_code="upstream_oil_gas", min_exposure=0.0, limit=200
            )
            return r1, r2, rows
        finally:
            await adapter.close()

    r1, r2, rows = _run(scenario())
    assert r1["written"] == 20
    assert r1["skipped"] == 1
    assert r1["batch_count"] >= 3, "must split into multiple batches"
    # Second run is idempotent (overwrites in place, not duplicating).
    assert r2["written"] == 20
    distinct = {(r["symbol"], r["theme_code"]) for r in rows}
    assert len(distinct) == 20


def test_lineage_gate_update_partial(initialized_db: Path) -> None:
    """``update_event_task_lineage_gates`` must support partial patches.

    在 PR-D / PR-E 中 Gate-1 / Gate-2 / Gate-3 由不同处理阶段写回。
    DAO 不能在 Gate-2 上线时把 Gate-1 重置成 NULL。
    """

    adapter = _build_adapter(initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            await adapter.upsert_event_task_lineage({
                "event_id": "test_evt_lineage",
                "task_id": "task_abc",
                "theme_code": "shipping_trade",
                "impact_direction": "positive",
                "impact_magnitude": 0.7,
                "target_symbols": ["601919", "600026"],
                "target_count": 2,
                "breadth_resolved": "narrow",
            })
            # Stage 1: Gate-1 passes.
            await adapter.update_event_task_lineage_gates(
                event_id="test_evt_lineage",
                task_id="task_abc",
                gate_1_passed=True,
            )
            # Stage 2: only Gate-2 fails — must NOT erase the Gate-1 win.
            await adapter.update_event_task_lineage_gates(
                event_id="test_evt_lineage",
                task_id="task_abc",
                gate_2_passed=False,
            )
            await adapter.update_event_task_lineage_gates(
                event_id="test_evt_lineage",
                task_id="task_abc",
                strategies_submitted=3,
            )
            async with adapter.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT gate_1_passed, gate_2_passed, gate_3_passed, "
                    "strategies_submitted FROM strategy_factory_event_task_lineage "
                    "WHERE event_id = $1 AND task_id = $2",
                    "test_evt_lineage",
                    "task_abc",
                )
            return dict(row) if row else {}
        finally:
            await adapter.close()

    row = _run(scenario())
    assert row.get("gate_1_passed") == 1, "Gate-1 must remain truthy after later patches"
    assert row.get("gate_2_passed") == 0
    assert row.get("gate_3_passed") is None, "untouched gate stays NULL"
    assert row.get("strategies_submitted") == 3


def test_outbox_dedupe_idempotent(initialized_db: Path) -> None:
    """First claim must succeed; second claim of an in-flight key bumps attempts.

    Terminal states (processed / abandoned) must reject re-claim with
    ``claimed=False`` so the publisher skips processing.
    """

    adapter = _build_adapter(initialized_db)

    async def scenario() -> tuple[dict, dict, dict, dict, dict]:
        await adapter.initialize()
        try:
            payload = {
                "dedupe_key": "manual:critical_minerals:dummyhash:2026-05-24",
                "source_event_id": "manual_test123",
                "theme_code": "rare_earth",
                "event_type": "critical_minerals",
            }
            first = await adapter.claim_event_outbox(payload)
            second = await adapter.claim_event_outbox(payload)  # same key, in-flight
            await adapter.mark_event_outbox_processed(payload["dedupe_key"])
            third = await adapter.claim_event_outbox(payload)  # processed → no claim
            # And a separate failed branch.
            fail_payload = {
                **payload,
                "dedupe_key": "manual:critical_minerals:other:2026-05-24",
            }
            fourth = await adapter.claim_event_outbox(fail_payload)
            await adapter.mark_event_outbox_failed(
                fail_payload["dedupe_key"], error="downstream timeout"
            )
            fifth = await adapter.claim_event_outbox(fail_payload)
            return first, second, third, fourth, fifth
        finally:
            await adapter.close()

    first, second, third, fourth, fifth = _run(scenario())
    assert first["claimed"] is True and first["attempts"] == 1
    assert second["claimed"] is True and second["attempts"] == 2
    assert third["claimed"] is False
    assert third["status"] == "processed"
    assert fourth["claimed"] is True and fourth["attempts"] == 1
    # Failed (non-terminal) is re-claimable; attempts count must climb.
    assert fifth["claimed"] is True and fifth["attempts"] == 2


def test_outbox_supports_abandon_terminal_state(initialized_db: Path) -> None:
    """``mark_event_outbox_failed(abandon=True)`` must lock the slot."""

    adapter = _build_adapter(initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            payload = {
                "dedupe_key": "manual:abandoned_case:2026-05-24",
                "source_event_id": "manual_abandon",
            }
            await adapter.claim_event_outbox(payload)
            await adapter.mark_event_outbox_failed(
                payload["dedupe_key"], error="permanent", abandon=True
            )
            return await adapter.claim_event_outbox(payload)
        finally:
            await adapter.close()

    result = _run(scenario())
    assert result["claimed"] is False
    assert result["status"] == "abandoned"


# ---------------------------------------------------------------------------
# Phase 6 v1: TDX-only exposure DAO + manager maintenance actions
# ---------------------------------------------------------------------------


def test_tdx_only_company_concept_and_industry_daos(initialized_db: Path) -> None:
    """TDX-only DAOs must read local tables and support filters."""

    adapter = _build_adapter(initialized_db)

    async def scenario() -> tuple[list, list, list]:
        await adapter.initialize()
        try:
            await _seed_tdx_only_exposure_fixture(adapter)
            concepts = await adapter.list_company_concept_blocks(
                symbols=["600100"], theme_code="AI", limit=10
            )
            filtered_out = await adapter.list_company_concept_blocks(
                symbols=["600100"], theme_code="not-present", limit=10
            )
            industries = await adapter.list_industry_blocks(symbols=["600100"], limit=10)
            return concepts, filtered_out, industries
        finally:
            await adapter.close()

    concepts, filtered_out, industries = _run(scenario())
    assert {row["block_code"] for row in concepts} == {"C001", "C002"}
    assert all(row["symbol"] == "600100" for row in concepts)
    assert filtered_out == []
    assert {row["industry_source"] for row in industries} >= {"stocks", "tdx_relation"}
    assert any(row["industry_name"] == "Semiconductor" for row in industries)


def test_lineage_and_status_handlers_read_real_tables(initialized_db: Path) -> None:
    """Lineage/exposure/outbox read actions must use persisted DAO state."""

    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_event_lineage,
        handle_factory_event_outbox_status,
        handle_factory_theme_exposure_status,
    )

    adapter = _build_adapter(initialized_db)

    async def scenario() -> tuple[dict, dict, dict]:
        await adapter.initialize()
        try:
            await adapter.upsert_event_injection({
                "event_id": "evt_status_read",
                "source": "manual",
                "event_name": "status read event",
                "event_type": "policy_shock",
                "direction": "positive",
                "confidence": 0.8,
                "intensity": 0.7,
                "horizon": "swing_5_20d",
                "scope": "theme",
                "primary_themes": [{"theme_code": "status_theme", "direction": "positive"}],
                "valid_from": "2026-05-24T00:00:00+00:00",
                "valid_until": "2099-01-01T00:00:00+00:00",
                "status": "active",
                "operator_id": "operator_status",
            })
            await adapter.upsert_event_task_lineage({
                "dedupe_key": "evt_status_read:status_theme:600100",
                "event_id": "evt_status_read",
                "task_id": "task_status_read",
                "theme_code": "status_theme",
                "impact_direction": "positive",
                "impact_magnitude": 0.7,
                "target_symbols": ["600100"],
                "target_count": 1,
                "breadth_resolved": "narrow",
            })
            await adapter.update_event_task_lineage_gates(
                event_id="evt_status_read",
                task_id="task_status_read",
                gate_1_passed=True,
                strategies_submitted=2,
            )
            await adapter.bulk_upsert_theme_exposure([
                {
                    "symbol": "600100",
                    "theme_code": "status_theme",
                    "exposure_score": 0.88,
                    "industry_match_level": 2,
                    "evidence": {"source": "test"},
                }
            ])
            await adapter.claim_event_outbox({
                "dedupe_key": "evt_status_read:status_theme:600100",
                "source_event_id": "evt_status_read",
                "theme_code": "status_theme",
                "event_type": "policy_shock",
            })
            await adapter.mark_event_outbox_processed("evt_status_read:status_theme:600100")

            lineage = await handle_factory_event_lineage(
                adapter,
                {"event_id": "evt_status_read", "limit": 10},
            )
            exposure_status = await handle_factory_theme_exposure_status(adapter, {})
            outbox_status = await handle_factory_event_outbox_status(adapter, {"limit": 10})
            return lineage, exposure_status, outbox_status
        finally:
            await adapter.close()

    lineage, exposure_status, outbox_status = _run(scenario())
    assert lineage["success"] is True
    row = lineage["data"]["lineage"][0]
    assert row["event_name"] == "status read event"
    assert row["task_id"] == "task_status_read"
    assert row["target_symbols"] == ["600100"]
    assert row["gate_1_passed"] == 1
    assert row["strategies_submitted"] == 2
    assert exposure_status["data"]["row_count"] >= 1
    assert exposure_status["data"]["theme_count"] >= 1
    assert outbox_status["data"]["counts"]["processed"] >= 1


def test_theme_exposure_refresh_handler_uses_tdx_only_builder(
    initialized_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual refresh action must bulk-write Phase 6 v1 TDX-only evidence."""

    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_theme_exposure_refresh,
    )

    monkeypatch.setenv("STRATEGY_FACTORY_THEME_EXPOSURE_MIN_TURNOVER", "0.1")
    monkeypatch.setenv("STRATEGY_FACTORY_THEME_EXPOSURE_MIN_MARKET_CAP", "10")
    adapter = _build_adapter(initialized_db)

    async def scenario() -> tuple[dict, list]:
        await adapter.initialize()
        try:
            await _seed_tdx_only_exposure_fixture(adapter)
            await adapter.upsert_theme_node({
                "theme_code": "ai_semiconductor",
                "theme_name": "AI Semiconductor",
                "aliases": ["AI"],
                "industry_tags": ["Semiconductor"],
                "breadth": "narrow",
                "is_active": 1,
            })
            response = await handle_factory_theme_exposure_refresh(
                adapter,
                {"stock_limit": 10, "theme_limit": 10, "batch_size": 3},
            )
            rows = await adapter.list_theme_exposure(
                theme_code="ai_semiconductor", min_exposure=0.0, limit=20
            )
            return response, rows
        finally:
            await adapter.close()

    response, rows = _run(scenario())
    assert response["success"] is True
    report = response["data"]
    assert report["status"] == "completed"
    assert report["source"] == "tdx_only_v1"
    assert report["rows_scanned"] >= 2
    assert report["rows_written"] >= 1
    assert report["batch_count"] >= 1
    assert report["industry_coverage"] > 0
    assert report["concept_block_coverage"] > 0
    assert report["skipped_low_liquidity"] >= 1
    target = next(row for row in rows if row["symbol"] == "600100")
    assert target["mainbz_match_score"] == 0
    assert "tdx_only_v1" in str(target["evidence"])


def test_event_outbox_drain_writes_lineage_once(initialized_db: Path) -> None:
    """Outbox drain must claim, write lineage, mark processed, and dedupe."""

    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_event_lineage,
        handle_factory_event_outbox_drain,
        handle_factory_event_outbox_status,
    )

    adapter = _build_adapter(initialized_db)

    async def scenario() -> tuple[dict, dict, dict, dict]:
        await adapter.initialize()
        try:
            await adapter.upsert_theme_node({
                "theme_code": "drain_root",
                "theme_name": "Drain root",
                "breadth": "narrow",
                "default_horizon": "swing_5_20d",
                "is_active": 1,
            })
            await adapter.bulk_upsert_theme_exposure([
                {
                    "symbol": "600100",
                    "theme_code": "drain_root",
                    "exposure_score": 0.85,
                    "industry_match_level": 2,
                    "evidence": {"source": "test"},
                }
            ])
            await adapter.upsert_event_injection({
                "event_id": "evt_drain_once",
                "source": "manual",
                "event_name": "drain event",
                "event_type": "policy_shock",
                "direction": "positive",
                "confidence": 0.9,
                "intensity": 0.9,
                "horizon": "swing_5_20d",
                "scope": "theme",
                "primary_themes": [{"theme_code": "drain_root", "direction": "positive"}],
                "valid_from": "2026-05-24T00:00:00+00:00",
                "valid_until": "2099-01-01T00:00:00+00:00",
                "status": "active",
                "operator_id": "operator_drain",
            })

            first = await handle_factory_event_outbox_drain(adapter, {"limit": 10})
            lineage = await handle_factory_event_lineage(
                adapter,
                {"event_id": "evt_drain_once", "limit": 10},
            )
            second = await handle_factory_event_outbox_drain(adapter, {"limit": 10})
            status = await handle_factory_event_outbox_status(adapter, {"limit": 10})
            return first, lineage, second, status
        finally:
            await adapter.close()

    first, lineage, second, status = _run(scenario())
    assert first["success"] is True
    assert first["data"]["single_worker"] is True
    assert first["data"]["processed"] == 1
    assert first["data"]["failed"] == 0
    assert lineage["data"]["count"] == 1
    row = lineage["data"]["lineage"][0]
    assert row["event_id"] == "evt_drain_once"
    assert row["theme_code"] == "drain_root"
    assert row["target_symbols"] == ["600100"]
    assert second["success"] is True
    assert second["data"]["processed"] == 0
    assert second["data"]["skipped"] >= 1
    assert status["data"]["counts"]["processed"] == 1


def test_theme_regression_run_handler_skips_without_edges(initialized_db: Path) -> None:
    """Manual regression action should be callable and skip cleanly when empty."""

    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_theme_regression_run,
    )

    adapter = _build_adapter(initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            return await handle_factory_theme_regression_run(adapter, {})
        finally:
            await adapter.close()

    response = _run(scenario())
    assert response["success"] is True
    assert response["data"] == {"status": "skipped", "reason": "no_active_edges"}


# ---------------------------------------------------------------------------
# PR-D (Phase 2, 2026-05-24): preview_tasks must drive real BFS + basket
# ---------------------------------------------------------------------------


def test_preview_tasks_returns_real_propagation_with_candidates(initialized_db: Path) -> None:
    """``factory_event_preview_tasks`` must return impacts + candidate symbols
    via the real ``propagate_event_to_themes`` + ``resolve_target_basket``
    pipeline, not the legacy depth-1 listing."""

    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_event_preview_tasks,
    )

    adapter = _build_adapter(initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            # Seed two theme nodes + one edge so BFS has something to walk.
            await adapter.upsert_theme_node({
                "theme_code": "preview_root",
                "theme_name": "Preview root",
                "breadth": "narrow",
                "default_horizon": "swing_5_20d",
            })
            await adapter.upsert_theme_node({
                "theme_code": "preview_child",
                "theme_name": "Preview child",
                "breadth": "narrow",
                "default_horizon": "swing_5_20d",
            })
            await adapter.upsert_theme_edge({
                "source_theme_code": "preview_root",
                "target_theme_code": "preview_child",
                "relation_type": "amplifies",
                "direction_sign": 1,
                "magnitude_factor": 0.8,
                "confidence": 0.7,
                "lag_days": 1,
            })
            # Seed exposure rows so resolve_target_basket has something to pick.
            await adapter.bulk_upsert_theme_exposure([
                {"symbol": "600100", "theme_code": "preview_root", "exposure_score": 0.85,
                 "industry_match_level": 2, "evidence": {"src": "test"}},
                {"symbol": "600200", "theme_code": "preview_root", "exposure_score": 0.7,
                 "industry_match_level": 1, "evidence": {"src": "test"}},
                {"symbol": "600300", "theme_code": "preview_child", "exposure_score": 0.6,
                 "industry_match_level": 1, "evidence": {"src": "test"}},
            ])

            return await handle_factory_event_preview_tasks(
                adapter,
                {
                    "event_id": "preview_event_001",
                    "event_name": "preview test",
                    "event_type": "policy_stimulus",
                    "direction": "positive",
                    "confidence": 0.9,
                    "intensity": 0.9,
                    "horizon": "swing_5_20d",
                    "primary_themes": [
                        {"theme_code": "preview_root", "direction": "positive"},
                    ],
                },
            )
        finally:
            await adapter.close()

    response = _run(scenario())
    assert response["success"] is True
    data = response["data"]
    assert data["preview_mode"] == "real_propagation_v1"
    # BFS reached both root and child.
    theme_codes = {item["theme_code"] for item in data["impacts"]}
    assert "preview_root" in theme_codes
    assert "preview_child" in theme_codes
    # Each impact carries candidate_symbols (because exposure was seeded).
    root_impact = next(it for it in data["impacts"] if it["theme_code"] == "preview_root")
    assert root_impact["candidate_count"] >= 1
    assert root_impact["candidate_symbols"], "root preview should expose seed symbols"
    # Aggregated candidate_symbols deduplicated across themes.
    assert isinstance(data["candidate_symbols"], list)
    assert data["candidate_count"] == len(set(data["candidate_symbols"]))
    # warnings is a list (possibly empty when seed is clean).
    assert isinstance(data["warnings"], list)


def test_preview_tasks_neutral_primary_emits_warning(initialized_db: Path) -> None:
    """Neutral primary 必须只出 lineage 标记,不展开下游."""

    from akshare_mcp.tools.managers.strategy_mgr_factory_events import (
        handle_factory_event_preview_tasks,
    )

    adapter = _build_adapter(initialized_db)

    async def scenario() -> dict:
        await adapter.initialize()
        try:
            # neutral_root has an edge that, if expanded, would surface
            # `neutral_child` — but neutral primaries must not expand.
            await adapter.upsert_theme_node({
                "theme_code": "neutral_root",
                "theme_name": "Neutral root",
                "breadth": "narrow",
            })
            await adapter.upsert_theme_node({
                "theme_code": "neutral_child",
                "theme_name": "Neutral child",
                "breadth": "narrow",
            })
            await adapter.upsert_theme_edge({
                "source_theme_code": "neutral_root",
                "target_theme_code": "neutral_child",
                "relation_type": "amplifies",
                "direction_sign": 1,
                "magnitude_factor": 0.9,
                "confidence": 0.9,
                "lag_days": 0,
            })

            return await handle_factory_event_preview_tasks(
                adapter,
                {
                    "event_id": "preview_neutral",
                    "event_name": "neutral preview",
                    "event_type": "policy_stimulus",
                    "direction": "neutral",
                    "confidence": 0.8,
                    "intensity": 0.8,
                    "primary_themes": [
                        {"theme_code": "neutral_root", "direction": "neutral"},
                    ],
                },
            )
        finally:
            await adapter.close()

    response = _run(scenario())
    assert response["success"] is True
    data = response["data"]
    theme_codes = {it["theme_code"] for it in data["impacts"]}
    assert "neutral_root" in theme_codes
    assert "neutral_child" not in theme_codes
    types = {w["type"] for w in data["warnings"]}
    assert "neutral_primary_skipped" in types
