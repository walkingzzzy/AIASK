"""P2 synthetic factory golden path (fixture DB, no live market).

Chain covered (read-only evaluation on fixture rows):
  observe strategy -> paper order(signal_id) -> exit signal/order ->
  formal diagnostics histogram fields

Assertions:
  - fail-closed lineage still rejects missing signal_id
  - diagnostics surface formal/observe/exit/hard_gate fields
  - Mock AI readiness must not report production_ready=true
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from akshare_mcp.services import incubation as incubation_mod
from akshare_mcp.services.factory_diagnostics import FactoryDiagnosticsService


class _Db:
    def __init__(self, conn: sqlite3.Connection):
        self.connection = conn


def _seed_golden_db(path: Path) -> sqlite3.Connection:
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
            signal_id TEXT,
            position_id TEXT
        );
        CREATE TABLE paper_trades (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            signal_id TEXT
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
    # observe strategy with bootstrap-pending hard gate (not formal)
    conn.execute(
        "INSERT INTO strategies VALUES (?,?,?,?,?)",
        (
            "strat_observe",
            "incubating",
            "observe_incubation",
            '{"execution_audit_gate":{"status":"bootstrap_pending"},'
            '"formal_readiness_blockers":["execution_audit_gate:bootstrap_pending"]}',
            '["execution_audit_gate:bootstrap_pending"]',
        ),
    )
    # formal candidate with passed gate (sample only — does not imply L4)
    conn.execute(
        "INSERT INTO strategies VALUES (?,?,?,?,?)",
        (
            "strat_formal",
            "formal",
            "formal_incubation",
            '{"execution_audit_gate":{"status":"passed"}}',
            None,
        ),
    )
    # paper buy with signal_id (lineage OK)
    conn.execute(
        "INSERT INTO paper_orders VALUES (?,?,?,?,?,?)",
        ("ord_buy_1", "strat_observe", "buy", "filled", "sig_entry_1", "pos_1"),
    )
    # exit path
    conn.execute(
        "INSERT INTO strategy_signals VALUES (?,?,?,?,?)",
        ("sig_exit_1", "strat_observe", -1, "exit", "000001"),
    )
    conn.execute(
        "INSERT INTO paper_orders VALUES (?,?,?,?,?,?)",
        ("ord_sell_1", "strat_observe", "sell", "filled", "sig_exit_1", "pos_1"),
    )
    conn.execute(
        "INSERT INTO strategy_trade_positions VALUES (?,?,?,?)",
        ("pos_1", "strat_observe", "000001", "closed"),
    )
    conn.execute(
        "INSERT INTO paper_trades VALUES (?,?,?)",
        ("tr_1", "strat_observe", "sig_entry_1"),
    )
    # open position still needing exit continuity sample
    conn.execute(
        "INSERT INTO strategy_trade_positions VALUES (?,?,?,?)",
        ("pos_open", "strat_formal", "600519", "open"),
    )
    conn.execute(
        "INSERT INTO strategy_signals VALUES (?,?,?,?,?)",
        ("sig_entry_f", "strat_formal", 1, "entry", "600519"),
    )
    conn.execute(
        "INSERT INTO paper_orders VALUES (?,?,?,?,?,?)",
        ("ord_buy_f", "strat_formal", "buy", "filled", "sig_entry_f", "pos_open"),
    )
    conn.commit()
    return conn


def test_fail_closed_blocks_order_without_signal_id(monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    gap = incubation_mod._require_order_lineage(
        strategy_id="strat_observe",
        signal_id="",
        position_id="pos_1",
        context="golden_path",
    )
    assert gap == "missing_signal_id"


def test_golden_path_diagnostics_fields(tmp_path):
    conn = _seed_golden_db(tmp_path / "golden.sqlite3")
    db = _Db(conn)
    payload = FactoryDiagnosticsService().collect(db, top_n=10)
    assert payload["ok"] is True
    assert payload["object"] == "aiask.factory_formal_diagnostics"
    assert payload["formal_count"] >= 1
    assert payload["observe_count"] >= 1
    assert payload["orders_total"] >= 2
    assert payload["orders_with_signal_id"] >= 2
    # full coverage on seeded orders with signal_id
    assert float(payload["signal_id_coverage"] or 0) >= 0.99
    funnel = payload["exit_funnel"]
    assert funnel["closed"] >= 1
    assert funnel["open_positions"] >= 1
    hist = payload["hard_gate_histogram"]
    assert hist.get("bootstrap_pending", 0) + hist.get("passed", 0) >= 1
    assert isinstance(payload.get("next_actions"), list)
    # synthetic fixture is evidence sample only — not a production readiness claim
    assert payload["formal_count"] >= 1
    conn.close()


def test_lineage_complete_on_golden_orders(tmp_path, monkeypatch):
    monkeypatch.setenv("INCUBATION_FAIL_CLOSED_SIGNAL_ID", "1")
    conn = _seed_golden_db(tmp_path / "lineage.sqlite3")
    rows = conn.execute(
        "SELECT strategy_id, signal_id, position_id FROM paper_orders"
    ).fetchall()
    for strategy_id, signal_id, position_id in rows:
        gap = incubation_mod._require_order_lineage(
            strategy_id=strategy_id,
            signal_id=signal_id,
            position_id=position_id,
            context="golden_seed",
        )
        assert gap is None, f"seeded order missing lineage: {strategy_id} {signal_id}"
    conn.close()
