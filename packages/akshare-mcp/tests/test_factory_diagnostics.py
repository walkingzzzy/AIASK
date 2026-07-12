"""Unit tests for FactoryDiagnosticsService (P0-C)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from akshare_mcp.services.factory_diagnostics import (
    FactoryDiagnosticsService,
    handle_factory_formal_diagnostics,
    investigate_exit_signal_gap,
)


class _Db:
    def __init__(self, conn):
        self.connection = conn


def _make_db(tmp_path: Path) -> _Db:
    path = tmp_path / "diag.sqlite3"
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE strategies (
            id TEXT PRIMARY KEY,
            status TEXT,
            incubating TEXT,
            params TEXT,
            formal_readiness_blockers TEXT
        );
        CREATE TABLE paper_orders (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            direction TEXT,
            status TEXT,
            signal_id TEXT
        );
        CREATE TABLE paper_trades (
            id TEXT PRIMARY KEY,
            strategy_id TEXT
        );
        CREATE TABLE strategy_signals (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            signal INTEGER,
            event_action TEXT,
            code TEXT
        );
        CREATE TABLE strategy_trade_positions (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            code TEXT,
            status TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO strategies VALUES (?,?,?,?,?)",
        (
            "s1",
            "incubating",
            "observe_incubation",
            '{"execution_audit_gate":{"status":"bootstrap_pending"},"formal_readiness_blockers":["execution_audit_gate:bootstrap_pending"]}',
            '["execution_audit_gate:bootstrap_pending"]',
        ),
    )
    conn.execute(
        "INSERT INTO strategies VALUES (?,?,?,?,?)",
        (
            "s2",
            "incubating",
            "observe_incubation",
            '{"execution_audit_gate":{"status":"missing"}}',
            None,
        ),
    )
    conn.execute(
        "INSERT INTO strategies VALUES (?,?,?,?,?)",
        ("s3", "formal", "formal_incubation", '{"execution_audit_gate":{"status":"passed"}}', None),
    )
    conn.execute(
        "INSERT INTO paper_orders VALUES (?,?,?,?,?)",
        ("o1", "s1", "buy", "filled", "sig-1"),
    )
    conn.execute(
        "INSERT INTO paper_orders VALUES (?,?,?,?,?)",
        ("o2", "s1", "sell", "pending", ""),
    )
    conn.execute(
        "INSERT INTO paper_orders VALUES (?,?,?,?,?)",
        ("o3", "s2", "buy", "filled", None),
    )
    conn.execute(
        "INSERT INTO strategy_signals VALUES (?,?,?,?,?)",
        ("sig1", "s1", -1, "exit", "000001"),
    )
    conn.execute(
        "INSERT INTO strategy_trade_positions VALUES (?,?,?,?)",
        ("p1", "s1", "000001", "open"),
    )
    conn.execute(
        "INSERT INTO strategy_trade_positions VALUES (?,?,?,?)",
        ("p2", "s1", "000002", "closed"),
    )
    conn.execute(
        "INSERT INTO paper_trades VALUES (?,?)",
        ("t1", "s1"),
    )
    conn.commit()
    return _Db(conn)


def test_collect_basic_counts(tmp_path):
    db = _make_db(tmp_path)
    svc = FactoryDiagnosticsService()
    payload = svc.collect(db, top_n=10)
    assert payload["ok"] is True
    assert payload["object"] == "aiask.factory_formal_diagnostics"
    assert payload["formal_count"] == 1
    assert payload["observe_count"] == 2
    assert payload["orders_total"] == 3
    assert payload["orders_with_signal_id"] == 1
    assert payload["signal_id_coverage"] == round(1 / 3, 4)
    assert payload["exit_funnel"]["open_positions"] == 1
    assert payload["exit_funnel"]["closed"] == 1
    assert payload["exit_funnel"]["with_exit_signal"] == 1
    assert payload["exit_funnel"]["with_exit_order"] == 1
    assert payload["hard_gate_histogram"]["bootstrap_pending"] >= 1
    assert payload["hard_gate_histogram"]["missing"] >= 1
    assert payload["hard_gate_histogram"]["passed"] >= 1
    assert any(b["code"].startswith("execution_audit_gate") for b in payload["top_blockers"])
    assert payload["next_actions"]
    assert "exit_gap" in payload
    assert payload["exit_gap"]["exit_signals"] >= 1
    assert isinstance(payload["exit_gap"].get("likely_causes"), list)
    db.connection.close()


def test_handle_envelope(tmp_path):
    import asyncio

    db = _make_db(tmp_path)

    async def _body():
        return await handle_factory_formal_diagnostics(db, {"top_n": 5})

    result = asyncio.run(_body())
    assert result["success"] is True
    assert result["data"]["formal_count"] == 1
    assert result["meta"]["side_effect"]["level"] == "read_only"
    db.connection.close()


def test_empty_db_missing_tables(tmp_path):
    path = tmp_path / "empty.sqlite3"
    conn = sqlite3.connect(str(path))
    db = _Db(conn)
    payload = FactoryDiagnosticsService().collect(db)
    assert payload["ok"] is False
    assert "strategies_table_missing" in str(payload.get("error") or "")
    conn.close()


def test_exit_signal_gap_investigation(tmp_path):
    db = _make_db(tmp_path)
    # Add orphan exit signal without matching sell order for s2
    db.connection.execute(
        "INSERT INTO strategy_signals VALUES (?,?,?,?,?)",
        ("sig2", "s2", -1, "exit", "000002"),
    )
    db.connection.commit()
    payload = investigate_exit_signal_gap(db, sample_limit=5)
    assert payload["ok"] is True
    assert payload["object"] == "aiask.factory_exit_gap"
    gap = payload["exit_gap"]
    assert gap["exit_signals"] >= 2
    assert gap["strategies_with_exit_signal_no_order"] >= 1
    assert isinstance(gap["sample_strategies"], list)
    assert gap["likely_causes"]
    assert gap["recommendations"]
    # collect should surface investigate next_action
    full = FactoryDiagnosticsService().collect(db, top_n=10)
    codes = [a.get("code") for a in full.get("next_actions") or []]
    assert "investigate_exit_signal_gap" in codes or "restore_exit_continuity" in codes or "repair_signal_lineage" in codes
    db.connection.close()


def test_exit_gap_empty_without_signals_table(tmp_path):
    path = tmp_path / "no_sig.sqlite3"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE strategies (id TEXT PRIMARY KEY, status TEXT, incubating TEXT, params TEXT, formal_readiness_blockers TEXT)")
    conn.commit()
    db = _Db(conn)
    payload = investigate_exit_signal_gap(db)
    assert payload["ok"] is True
    assert payload["exit_gap"]["exit_signals"] == 0
    assert "strategy_signals_table_missing" in payload["exit_gap"]["likely_causes"]
    conn.close()

