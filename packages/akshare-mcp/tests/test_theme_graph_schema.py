"""PR-1 smoke tests: theme graph schema DDL + seed idempotency."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture
def tmp_db(tmp_path):
    """Return path to a temporary SQLite database."""
    return str(tmp_path / "test_theme_graph.sqlite3")


def _run_async(coro):
    return asyncio.run(coro)


async def _create_tables(db_path: str):
    """Execute the schema DDL against a fresh SQLite database."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        # Create the 5 new tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_factory_theme_nodes (
                theme_code TEXT PRIMARY KEY,
                theme_name TEXT NOT NULL,
                parent_theme_code TEXT,
                breadth TEXT NOT NULL DEFAULT 'medium',
                default_horizon TEXT NOT NULL DEFAULT 'swing_5_20d',
                aliases TEXT DEFAULT '[]',
                industry_tags TEXT DEFAULT '[]',
                description TEXT,
                shock_detection_profile TEXT NOT NULL DEFAULT 'fast',
                benchmark_index_code TEXT DEFAULT '000300',
                manual_locked INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_factory_theme_edges (
                edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_theme_code TEXT NOT NULL,
                target_theme_code TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                direction_sign INTEGER NOT NULL,
                magnitude_factor REAL NOT NULL DEFAULT 0.5,
                lag_days INTEGER NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0.5,
                confidence_source TEXT NOT NULL DEFAULT 'manual',
                manual_confidence_backup REAL,
                manual_magnitude_backup REAL,
                manual_locked INTEGER NOT NULL DEFAULT 0,
                last_regression_at TEXT,
                evidence TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT,
                UNIQUE(source_theme_code, target_theme_code, relation_type)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_factory_event_injections (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                event_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                direction TEXT,
                confidence REAL NOT NULL,
                intensity REAL NOT NULL,
                horizon TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'theme',
                primary_themes TEXT NOT NULL DEFAULT '[]',
                rationale TEXT,
                evidence TEXT,
                valid_from TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_review',
                operator_id TEXT,
                approver_id TEXT,
                approved_at TEXT,
                actual_outcome TEXT,
                outcome_notes TEXT,
                outcome_recorded_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_factory_event_task_lineage (
                lineage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                theme_code TEXT NOT NULL,
                impact_direction TEXT NOT NULL,
                impact_magnitude REAL NOT NULL,
                target_symbols TEXT NOT NULL DEFAULT '[]',
                target_count INTEGER NOT NULL,
                breadth_resolved TEXT NOT NULL,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                gate_1_passed INTEGER,
                gate_2_passed INTEGER,
                gate_3_passed INTEGER,
                strategies_submitted INTEGER DEFAULT 0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategy_factory_theme_exposure (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                theme_code TEXT NOT NULL,
                exposure_score REAL NOT NULL DEFAULT 0,
                industry_match_level INTEGER DEFAULT 0,
                name_match_score REAL DEFAULT 0,
                mainbz_match_score REAL DEFAULT 0,
                historical_beta REAL DEFAULT 0,
                evidence TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, theme_code)
            );
        """)
        conn.commit()
    finally:
        conn.close()


def test_schema_ddl_idempotent(tmp_db):
    """Schema DDL can be run twice without error."""
    _run_async(_create_tables(tmp_db))
    _run_async(_create_tables(tmp_db))  # second run should not fail


def test_seed_idempotent(tmp_db):
    """Seed script can be run twice without duplicating data."""
    _run_async(_create_tables(tmp_db))

    sys.path.insert(0, str(SCRIPTS_DIR))
    from seed_strategy_factory_theme_graph import seed, THEME_NODES, THEME_EDGES

    _run_async(seed(tmp_db))
    _run_async(seed(tmp_db))  # second run should not fail

    # Verify counts
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    node_count = conn.execute("SELECT COUNT(*) FROM strategy_factory_theme_nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM strategy_factory_theme_edges").fetchone()[0]
    conn.close()

    assert node_count == len(THEME_NODES)
    assert edge_count == len(THEME_EDGES)


def test_seed_node_fields(tmp_db):
    """Verify seed nodes have correct field values."""
    _run_async(_create_tables(tmp_db))

    sys.path.insert(0, str(SCRIPTS_DIR))
    from seed_strategy_factory_theme_graph import seed

    _run_async(seed(tmp_db))

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT * FROM strategy_factory_theme_nodes WHERE theme_code = 'upstream_oil_gas'"
    ).fetchone()
    conn.close()

    assert row is not None
    # theme_code is first column
    assert row[0] == "upstream_oil_gas"


def test_seed_edge_unique_constraint(tmp_db):
    """Verify edge UNIQUE constraint works."""
    _run_async(_create_tables(tmp_db))

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "INSERT INTO strategy_factory_theme_edges (source_theme_code, target_theme_code, relation_type, direction_sign) VALUES ('a', 'b', 'amplifies', 1)"
    )
    conn.commit()

    # Duplicate should be ignored with INSERT OR IGNORE
    conn.execute(
        "INSERT OR IGNORE INTO strategy_factory_theme_edges (source_theme_code, target_theme_code, relation_type, direction_sign) VALUES ('a', 'b', 'amplifies', -1)"
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM strategy_factory_theme_edges").fetchone()[0]
    conn.close()
    assert count == 1
