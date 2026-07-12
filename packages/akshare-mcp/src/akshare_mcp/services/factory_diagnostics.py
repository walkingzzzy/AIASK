"""Factory formal / evidence / hard-gate / exit funnel diagnostics.

Single source of truth for scripts, Agent tools, and Desktop Factory Ops.
Read-only; never mutates factory state. Fail soft on missing tables.
Includes exit-signal gap investigation (P1-A3).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

HARD_GATE_BUCKETS = (
    "missing",
    "bootstrap_pending",
    "insufficient_samples",
    "failed_metrics",
    "bootstrap_ready",
    "passed",
    "unknown",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _decode_jsonish(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return value


def _flatten_blockers(raw: Any) -> list[str]:
    parsed = _decode_jsonish(raw)
    codes: list[str] = []
    if parsed is None:
        return codes
    if isinstance(parsed, str):
        token = parsed.strip()
        if token:
            codes.append(token)
        return codes
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, str) and item.strip():
                codes.append(item.strip())
            elif isinstance(item, dict):
                code = str(item.get("code") or item.get("blocker") or item.get("reason") or "").strip()
                if code:
                    codes.append(code)
        return codes
    if isinstance(parsed, dict):
        for key in ("blockers", "codes", "reasons", "items"):
            nested = parsed.get(key)
            if nested is not None:
                return _flatten_blockers(nested)
        for key, val in parsed.items():
            if val in (True, 1, "1", "true", "True"):
                codes.append(str(key))
            elif isinstance(val, str) and val.strip():
                codes.append(f"{key}:{val.strip()}")
        return codes
    return codes


class FactoryDiagnosticsService:
    """Aggregate factory production diagnostics from a shared DB connection."""

    object_name = "aiask.factory_formal_diagnostics"

    def collect(self, db: Any, *, top_n: int = 15) -> dict[str, Any]:
        """Synchronous collect when ``db.connection`` is a sqlite3 connection."""
        conn = getattr(db, "connection", None)
        if conn is None:
            return self._empty(error="database_connection_unavailable")
        try:
            return self._collect_from_connection(conn, top_n=top_n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FactoryDiagnosticsService.collect failed: %s", exc)
            return self._empty(error=f"{type(exc).__name__}:{exc}")

    async def collect_async(self, db: Any, *, top_n: int = 15) -> dict[str, Any]:
        """Async wrapper; uses sqlite connection if present, else empty."""
        # Prefer sync path for sqlite facade used by diagnose scripts / agent.
        if getattr(db, "connection", None) is not None:
            return self.collect(db, top_n=top_n)
        acquire = getattr(db, "acquire", None)
        if not callable(acquire):
            return self._empty(error="database_connection_unavailable")
        try:
            async with acquire() as conn:
                # asyncpg-style: adapt via thin bridge if fetch available
                if hasattr(conn, "fetch"):
                    return await self._collect_from_async_conn(conn, top_n=top_n)
                return self._collect_from_connection(conn, top_n=top_n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("FactoryDiagnosticsService.collect_async failed: %s", exc)
            return self._empty(error=f"{type(exc).__name__}:{exc}")

    def _empty(self, *, error: Optional[str] = None) -> dict[str, Any]:
        payload = {
            "object": self.object_name,
            "as_of": _now_iso(),
            "formal_count": 0,
            "observe_count": 0,
            "incubating_count": 0,
            "status_histogram": {},
            "top_blockers": [],
            "evidence_gaps": [],
            "signal_id_coverage": None,
            "order_signal_id_coverage": None,
            "exit_funnel": {
                "open_positions": 0,
                "with_exit_signal": 0,
                "with_exit_order": 0,
                "closed": 0,
                "exit_order_conversion": None,
            },
            "exit_gap": {
                "exit_signals": 0,
                "strategies_with_exit_signal_no_order": 0,
                "exit_signals_in_execution_universe": 0,
                "execution_universe_size": 0,
                "sample_strategies": [],
                "likely_causes": [],
                "recommendations": [],
            },
            "hard_gate_histogram": {k: 0 for k in HARD_GATE_BUCKETS},
            "next_actions": [],
            "ok": error is None,
        }
        if error:
            payload["error"] = error
        return payload

    def _table_exists(self, conn: Any, name: str) -> bool:
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
                (name,),
            ).fetchone()
            return bool(row)
        except Exception:
            return False

    def _scalar(self, conn: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
        try:
            row = conn.execute(sql, params).fetchone()
            if not row:
                return 0
            return _safe_int(row[0], 0)
        except Exception:
            return 0

    def _collect_from_connection(self, conn: Any, *, top_n: int) -> dict[str, Any]:
        if not self._table_exists(conn, "strategies"):
            return self._empty(error="strategies_table_missing")

        formal_count = self._scalar(
            conn,
            """
            SELECT COUNT(*) FROM strategies
            WHERE LOWER(COALESCE(incubating, status, '')) IN
                  ('formal_incubation', 'formal', 'listed', 'candidate')
               OR LOWER(COALESCE(status, '')) = 'formal'
            """,
        )
        # Prefer incubating column semantics used by diagnose scripts
        formal_by_incubating = self._scalar(
            conn,
            "SELECT COUNT(*) FROM strategies WHERE incubating = 'formal_incubation'",
        )
        observe_count = self._scalar(
            conn,
            "SELECT COUNT(*) FROM strategies WHERE incubating = 'observe_incubation'",
        )
        incubating_count = self._scalar(
            conn,
            """
            SELECT COUNT(*) FROM strategies
            WHERE LOWER(COALESCE(status, '')) = 'incubating'
               OR incubating IN ('observe_incubation', 'formal_incubation')
            """,
        )
        if formal_by_incubating > 0 or observe_count > 0:
            formal_count = formal_by_incubating

        status_histogram: dict[str, int] = {}
        try:
            for row in conn.execute(
                """
                SELECT COALESCE(NULLIF(incubating, ''), NULLIF(status, ''), '(null)') AS bucket, COUNT(*)
                FROM strategies
                GROUP BY bucket
                ORDER BY COUNT(*) DESC
                LIMIT 50
                """
            ):
                status_histogram[str(row[0])] = _safe_int(row[1])
        except Exception:
            status_histogram = {}

        top_blockers = self._top_blockers(conn, top_n=top_n)
        evidence = self._evidence_coverage(conn)
        exit_funnel = self._exit_funnel(conn)
        exit_gap = self._exit_signal_gap(conn, sample_limit=min(10, max(3, top_n // 2)))
        hard_gate_histogram = self._hard_gate_histogram(conn)
        next_actions = self._next_actions(
            formal_count=formal_count,
            observe_count=observe_count,
            evidence=evidence,
            exit_funnel=exit_funnel,
            hard_gate_histogram=hard_gate_histogram,
            top_blockers=top_blockers,
            exit_gap=exit_gap,
        )

        return {
            "object": self.object_name,
            "as_of": _now_iso(),
            "formal_count": formal_count,
            "observe_count": observe_count,
            "incubating_count": incubating_count,
            "status_histogram": status_histogram,
            "top_blockers": top_blockers,
            "evidence_gaps": evidence.get("gaps") or [],
            "signal_id_coverage": evidence.get("signal_id_coverage"),
            "order_signal_id_coverage": evidence.get("order_signal_id_coverage"),
            "orders_total": evidence.get("orders_total", 0),
            "orders_with_signal_id": evidence.get("orders_with_signal_id", 0),
            "signals_total": evidence.get("signals_total", 0),
            "trades_total": evidence.get("trades_total", 0),
            "exit_funnel": exit_funnel,
            "exit_gap": exit_gap,
            "hard_gate_histogram": hard_gate_histogram,
            "next_actions": next_actions,
            "ok": True,
        }

    async def _collect_from_async_conn(self, conn: Any, *, top_n: int) -> dict[str, Any]:
        # Minimal async path: reuse empty if we cannot run sqlite SQL.
        # Production Agent path uses sqlite connection facade.
        return self._empty(error="async_pg_diagnostics_not_implemented")

    def _top_blockers(self, conn: Any, *, top_n: int) -> list[dict[str, Any]]:
        counter: Counter[str] = Counter()
        # params JSON blockers
        try:
            rows = conn.execute(
                """
                SELECT params, formal_readiness_blockers
                FROM strategies
                WHERE incubating IN ('observe_incubation', 'formal_incubation')
                   OR LOWER(COALESCE(status, '')) IN ('incubating', 'observe', 'formal')
                LIMIT 5000
                """
            ).fetchall()
        except Exception:
            try:
                rows = conn.execute(
                    """
                    SELECT params, NULL
                    FROM strategies
                    LIMIT 5000
                    """
                ).fetchall()
            except Exception:
                rows = []

        for row in rows:
            params_raw = row[0] if row else None
            blockers_col = row[1] if row and len(row) > 1 else None
            for code in _flatten_blockers(blockers_col):
                counter[code] += 1
            params = _decode_jsonish(params_raw)
            if isinstance(params, dict):
                for code in _flatten_blockers(params.get("formal_readiness_blockers")):
                    counter[code] += 1
                for code in _flatten_blockers(params.get("readiness_blockers")):
                    counter[code] += 1
                gate = params.get("execution_audit_gate") or params.get("execution_audit")
                if isinstance(gate, dict):
                    status = str(gate.get("status") or "").strip()
                    if status:
                        counter[f"execution_audit_gate:{status}"] += 1
                elif isinstance(gate, str) and gate.strip():
                    counter[f"execution_audit_gate:{gate.strip()}"] += 1

        return [{"code": code, "count": count} for code, count in counter.most_common(top_n)]

    def _evidence_coverage(self, conn: Any) -> dict[str, Any]:
        signals_total = 0
        trades_total = 0
        orders_total = 0
        orders_with_signal_id = 0
        gaps: list[dict[str, Any]] = []

        if self._table_exists(conn, "strategy_signals"):
            signals_total = self._scalar(conn, "SELECT COUNT(*) FROM strategy_signals")
        if self._table_exists(conn, "paper_trades"):
            trades_total = self._scalar(conn, "SELECT COUNT(*) FROM paper_trades")
        if self._table_exists(conn, "paper_orders"):
            orders_total = self._scalar(conn, "SELECT COUNT(*) FROM paper_orders")
            # signal_id column may not exist on older schemas
            try:
                orders_with_signal_id = self._scalar(
                    conn,
                    """
                    SELECT COUNT(*) FROM paper_orders
                    WHERE signal_id IS NOT NULL AND TRIM(CAST(signal_id AS TEXT)) != ''
                    """,
                )
            except Exception:
                orders_with_signal_id = 0

        coverage = None
        if orders_total > 0:
            coverage = round(float(orders_with_signal_id) / float(orders_total), 4)
            if coverage < 0.95:
                gaps.append(
                    {
                        "code": "missing_signal_id_on_orders",
                        "count": orders_total - orders_with_signal_id,
                        "coverage": coverage,
                    }
                )

        # trades without signals gap (observe pool)
        if self._table_exists(conn, "paper_trades") and self._table_exists(conn, "strategy_signals"):
            try:
                with_trades = self._scalar(
                    conn,
                    """
                    SELECT COUNT(DISTINCT strategy_id) FROM paper_trades
                    WHERE strategy_id IN (
                        SELECT id FROM strategies WHERE incubating = 'observe_incubation'
                    )
                    """,
                )
                with_signals = self._scalar(
                    conn,
                    """
                    SELECT COUNT(DISTINCT strategy_id) FROM strategy_signals
                    WHERE strategy_id IN (
                        SELECT id FROM strategies WHERE incubating = 'observe_incubation'
                    )
                    """,
                )
                gap = max(0, with_trades - with_signals)
                if gap > 0:
                    gaps.append(
                        {
                            "code": "trades_without_signals",
                            "count": gap,
                            "strategies_with_trades": with_trades,
                            "strategies_with_signals": with_signals,
                        }
                    )
            except Exception:
                pass

        if trades_total <= 0 and signals_total <= 0 and orders_total <= 0:
            gaps.append({"code": "missing_realized_trade_evidence", "count": 0})

        return {
            "signals_total": signals_total,
            "trades_total": trades_total,
            "orders_total": orders_total,
            "orders_with_signal_id": orders_with_signal_id,
            "signal_id_coverage": coverage,
            "order_signal_id_coverage": coverage,
            "gaps": gaps,
        }

    def _exit_funnel(self, conn: Any) -> dict[str, Any]:
        open_positions = 0
        closed = 0
        with_exit_signal = 0
        with_exit_order = 0
        if self._table_exists(conn, "strategy_trade_positions"):
            open_positions = self._scalar(
                conn,
                """
                SELECT COUNT(*) FROM strategy_trade_positions
                WHERE LOWER(COALESCE(status, 'open')) IN
                      ('open', 'pending_exit', 'pending_entry', 'created', 'submitted', '')
                """,
            )
            closed = self._scalar(
                conn,
                """
                SELECT COUNT(*) FROM strategy_trade_positions
                WHERE LOWER(COALESCE(status, '')) IN ('closed', 'filled', 'done', 'completed', 'exited')
                """,
            )
        if self._table_exists(conn, "strategy_signals"):
            with_exit_signal = self._scalar(
                conn,
                """
                SELECT COUNT(*) FROM strategy_signals
                WHERE CAST(signal AS INTEGER) < 0
                   OR LOWER(COALESCE(event_action, '')) IN ('sell', 'exit', 'close', 'reduce')
                """,
            )
        if self._table_exists(conn, "paper_orders"):
            with_exit_order = self._scalar(
                conn,
                """
                SELECT COUNT(*) FROM paper_orders
                WHERE LOWER(COALESCE(direction, '')) IN ('sell', 'exit', 'short', 'close', 'reduce')
                """,
            )
        conversion = None
        if open_positions > 0 and with_exit_signal > 0:
            # rough: exit orders / min(open, exit signals) not exact; leave ratio of orders to open
            conversion = round(float(with_exit_order) / float(max(open_positions, 1)), 4)
        elif with_exit_signal > 0:
            conversion = round(float(with_exit_order) / float(with_exit_signal), 4)
        return {
            "open_positions": open_positions,
            "with_exit_signal": with_exit_signal,
            "with_exit_order": with_exit_order,
            "closed": closed,
            "exit_order_conversion": conversion,
        }


    def _exit_signal_gap(self, conn: Any, *, sample_limit: int = 10) -> dict[str, Any]:
        """Investigate exit-signal → exit-order conversion gaps (read-only).

        Mirrors scripts/factories/investigate_exit_signal_gap.py logic so
        Desktop/Agent and CLI share one source of truth (P1-A3).
        """
        empty = {
            "exit_signals": 0,
            "strategies_with_exit_signal_no_order": 0,
            "exit_signals_in_execution_universe": 0,
            "execution_universe_size": 0,
            "sample_strategies": [],
            "likely_causes": [],
            "recommendations": [],
        }
        if not self._table_exists(conn, "strategy_signals"):
            empty["likely_causes"] = ["strategy_signals_table_missing"]
            return empty

        exit_signals = self._scalar(
            conn,
            """
            SELECT COUNT(*) FROM strategy_signals
            WHERE CAST(signal AS INTEGER) < 0
               OR LOWER(COALESCE(event_action, '')) IN ('sell', 'exit', 'close', 'reduce')
            """,
        )
        empty["exit_signals"] = exit_signals

        strategies_no_order = 0
        if self._table_exists(conn, "paper_orders"):
            strategies_no_order = self._scalar(
                conn,
                """
                SELECT COUNT(DISTINCT strategy_id)
                FROM strategy_signals
                WHERE (CAST(signal AS INTEGER) < 0
                       OR LOWER(COALESCE(event_action, '')) IN ('sell', 'exit', 'close', 'reduce'))
                  AND strategy_id IS NOT NULL
                  AND TRIM(CAST(strategy_id AS TEXT)) != ''
                  AND strategy_id NOT IN (
                      SELECT DISTINCT strategy_id FROM paper_orders
                      WHERE LOWER(COALESCE(direction, '')) IN ('sell', 'exit', 'short', 'close', 'reduce')
                        AND strategy_id IS NOT NULL
                  )
                """,
            )
        else:
            strategies_no_order = self._scalar(
                conn,
                """
                SELECT COUNT(DISTINCT strategy_id) FROM strategy_signals
                WHERE CAST(signal AS INTEGER) < 0
                   OR LOWER(COALESCE(event_action, '')) IN ('sell', 'exit', 'close', 'reduce')
                """,
            )
        empty["strategies_with_exit_signal_no_order"] = strategies_no_order

        execution_universe_size = 0
        exit_in_universe = 0
        if self._table_exists(conn, "strategies"):
            has_accounts = self._table_exists(conn, "strategy_incubation_accounts")
            if has_accounts:
                execution_universe_size = self._scalar(
                    conn,
                    """
                    SELECT COUNT(DISTINCT s.id)
                    FROM strategies s
                    LEFT JOIN strategy_incubation_accounts sia ON sia.strategy_id = s.id
                    WHERE LOWER(COALESCE(s.status, '')) IN ('incubating', 'listed')
                      AND (sia.status IS NULL OR LOWER(COALESCE(sia.status, '')) = 'active')
                    """,
                )
                exit_in_universe = self._scalar(
                    conn,
                    """
                    SELECT COUNT(DISTINCT ss.strategy_id)
                    FROM strategy_signals ss
                    JOIN strategies s ON s.id = ss.strategy_id
                    LEFT JOIN strategy_incubation_accounts sia ON sia.strategy_id = ss.strategy_id
                    WHERE (CAST(ss.signal AS INTEGER) < 0
                           OR LOWER(COALESCE(ss.event_action, '')) IN ('sell', 'exit', 'close', 'reduce'))
                      AND LOWER(COALESCE(s.status, '')) IN ('incubating', 'listed')
                      AND (sia.status IS NULL OR LOWER(COALESCE(sia.status, '')) = 'active')
                    """,
                )
            else:
                execution_universe_size = self._scalar(
                    conn,
                    """
                    SELECT COUNT(*) FROM strategies
                    WHERE LOWER(COALESCE(status, '')) IN ('incubating', 'listed')
                       OR incubating IN ('observe_incubation', 'formal_incubation')
                    """,
                )
                exit_in_universe = self._scalar(
                    conn,
                    """
                    SELECT COUNT(DISTINCT ss.strategy_id)
                    FROM strategy_signals ss
                    JOIN strategies s ON s.id = ss.strategy_id
                    WHERE (CAST(ss.signal AS INTEGER) < 0
                           OR LOWER(COALESCE(ss.event_action, '')) IN ('sell', 'exit', 'close', 'reduce'))
                      AND (
                        LOWER(COALESCE(s.status, '')) IN ('incubating', 'listed')
                        OR s.incubating IN ('observe_incubation', 'formal_incubation')
                      )
                    """,
                )
        empty["execution_universe_size"] = execution_universe_size
        empty["exit_signals_in_execution_universe"] = exit_in_universe

        samples: list[dict[str, Any]] = []
        try:
            if self._table_exists(conn, "paper_orders") and self._table_exists(conn, "strategies"):
                rows = conn.execute(
                    """
                    SELECT
                        ss.strategy_id,
                        COALESCE(s.status, '') AS status,
                        COALESCE(s.incubating, '') AS incubating,
                        COUNT(DISTINCT ss.id) AS signal_count
                    FROM strategy_signals ss
                    LEFT JOIN strategies s ON s.id = ss.strategy_id
                    WHERE (CAST(ss.signal AS INTEGER) < 0
                           OR LOWER(COALESCE(ss.event_action, '')) IN ('sell', 'exit', 'close', 'reduce'))
                      AND ss.strategy_id IS NOT NULL
                      AND ss.strategy_id NOT IN (
                          SELECT DISTINCT strategy_id FROM paper_orders
                          WHERE LOWER(COALESCE(direction, '')) IN ('sell', 'exit', 'short', 'close', 'reduce')
                            AND strategy_id IS NOT NULL
                      )
                    GROUP BY ss.strategy_id, s.status, s.incubating
                    ORDER BY signal_count DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(sample_limit or 10), 50)),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT strategy_id, '', '', COUNT(*) AS signal_count
                    FROM strategy_signals
                    WHERE CAST(signal AS INTEGER) < 0
                       OR LOWER(COALESCE(event_action, '')) IN ('sell', 'exit', 'close', 'reduce')
                    GROUP BY strategy_id
                    ORDER BY signal_count DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(sample_limit or 10), 50)),),
                ).fetchall()
            for row in rows or []:
                sid = str(row[0] or "")
                open_count = 0
                if sid and self._table_exists(conn, "strategy_trade_positions"):
                    open_count = self._scalar(
                        conn,
                        """
                        SELECT COUNT(*) FROM strategy_trade_positions
                        WHERE strategy_id = ?
                          AND LOWER(COALESCE(status, 'open')) IN
                              ('open', 'pending_exit', 'pending_entry', 'created', 'submitted', '')
                        """,
                        (sid,),
                    )
                samples.append(
                    {
                        "strategy_id": sid,
                        "status": str(row[1] or ""),
                        "incubating": str(row[2] or ""),
                        "exit_signal_count": _safe_int(row[3], 0),
                        "open_positions": open_count,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("exit gap sample query failed: %s", exc)
        empty["sample_strategies"] = samples

        causes: list[str] = []
        recs: list[str] = []
        if exit_signals <= 0:
            causes.append("no_exit_signals")
            recs.append("ensure Phase 3c2 generates exit signals for open positions")
        else:
            if strategies_no_order > 0:
                causes.append("exit_signal_without_exit_order")
                recs.append("verify incubation runner exit candidate selection and order lineage fail-closed")
            if strategies_no_order > exit_in_universe and exit_signals > 0:
                causes.append("strategies_outside_execution_universe")
                recs.append("confirm strategy status is incubating/listed and incubation account active")
            samples_with_open = sum(1 for s in samples if _safe_int(s.get("open_positions"), 0) > 0)
            if samples and samples_with_open == 0:
                causes.append("exit_signal_without_open_position")
                recs.append("enable stale paper position closure or regenerate signals for open books only")
            if not causes:
                causes.append("conversion_path_needs_runtime_trace")
                recs.append("run incubation_factory.dry_run then inspect exit_funnel deltas")
        if not recs:
            recs.append("monitor exit_funnel and exit_gap after next incubation cycle")
        empty["likely_causes"] = causes
        empty["recommendations"] = recs
        return empty

    def _hard_gate_histogram(self, conn: Any) -> dict[str, int]:
        hist = {k: 0 for k in HARD_GATE_BUCKETS}
        try:
            rows = conn.execute(
                """
                SELECT params FROM strategies
                WHERE incubating IN ('observe_incubation', 'formal_incubation')
                   OR LOWER(COALESCE(status, '')) = 'incubating'
                LIMIT 5000
                """
            ).fetchall()
        except Exception:
            return hist

        for row in rows:
            params = _decode_jsonish(row[0] if row else None)
            status = "unknown"
            if isinstance(params, dict):
                for key in (
                    "execution_audit_gate_status",
                    "execution_hard_gate_status",
                    "hard_gate_status",
                ):
                    token = str(params.get(key) or "").strip().lower()
                    if token:
                        status = token
                        break
                if status == "unknown":
                    gate = params.get("execution_audit_gate") or params.get("hard_gate_result")
                    if isinstance(gate, dict):
                        status = str(gate.get("status") or gate.get("gate_status") or "unknown").strip().lower()
                    elif isinstance(gate, str) and gate.strip():
                        status = gate.strip().lower()
                # reasons-based fallback
                if status == "unknown":
                    blockers = _flatten_blockers(params.get("formal_readiness_blockers"))
                    joined = " ".join(blockers).lower()
                    if "bootstrap_pending" in joined:
                        status = "bootstrap_pending"
                    elif "insufficient" in joined:
                        status = "insufficient_samples"
                    elif "execution_audit_missing" in joined or "missing" in joined:
                        status = "missing"
                    elif "failed" in joined:
                        status = "failed_metrics"
            if status not in hist:
                status = "unknown"
            hist[status] = hist.get(status, 0) + 1
        return hist

    def _next_actions(
        self,
        *,
        formal_count: int,
        observe_count: int,
        evidence: dict[str, Any],
        exit_funnel: dict[str, Any],
        hard_gate_histogram: dict[str, int],
        top_blockers: list[dict[str, Any]],
        exit_gap: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        actions: list[dict[str, str]] = []
        coverage = evidence.get("signal_id_coverage")
        if coverage is not None and coverage < 0.95:
            actions.append(
                {
                    "code": "repair_signal_lineage",
                    "detail": f"order signal_id coverage={coverage}; enable fail-closed + backfill",
                }
            )
        open_pos = _safe_int(exit_funnel.get("open_positions"))
        closed = _safe_int(exit_funnel.get("closed"))
        if open_pos > 0 and closed == 0:
            actions.append(
                {
                    "code": "restore_exit_continuity",
                    "detail": f"open_positions={open_pos} but closed=0; check Phase 3c2 exit execution",
                }
            )
        gap = exit_gap or {}
        no_order = _safe_int(gap.get("strategies_with_exit_signal_no_order"))
        exit_sigs = _safe_int(gap.get("exit_signals"))
        if exit_sigs > 0 and no_order > 0:
            top_cause = ""
            causes = gap.get("likely_causes") or []
            if isinstance(causes, list) and causes:
                top_cause = str(causes[0])
            actions.append(
                {
                    "code": "investigate_exit_signal_gap",
                    "detail": (
                        f"exit_signals={exit_sigs}, strategies_no_exit_order={no_order}"
                        + (f", cause={top_cause}" if top_cause else "")
                    ),
                }
            )
        missing = _safe_int(hard_gate_histogram.get("missing"))
        bootstrap = _safe_int(hard_gate_histogram.get("bootstrap_pending"))
        if observe_count > 0 and (missing + bootstrap) >= observe_count and formal_count == 0:
            actions.append(
                {
                    "code": "accumulate_realized_samples",
                    "detail": "hard gate mostly missing/bootstrap_pending; need exit closes + realized trades",
                }
            )
        if formal_count == 0 and top_blockers:
            top = top_blockers[0]
            actions.append(
                {
                    "code": "explain_formal_blockers",
                    "detail": f"formal=0; top blocker={top.get('code')} count={top.get('count')}",
                }
            )
        if not actions:
            actions.append(
                {
                    "code": "monitor",
                    "detail": "no critical factory production blockers detected from available counters",
                }
            )
        return actions


def get_factory_diagnostics_service() -> FactoryDiagnosticsService:
    return FactoryDiagnosticsService()


def investigate_exit_signal_gap(db: Any, *, sample_limit: int = 10) -> dict[str, Any]:
    """Public read-only API used by CLI thin wrappers and tests."""
    service = get_factory_diagnostics_service()
    conn = getattr(db, "connection", None)
    if conn is None:
        return {
            "object": "aiask.factory_exit_gap",
            "as_of": _now_iso(),
            "ok": False,
            "error": "database_connection_unavailable",
            "exit_gap": {
                "exit_signals": 0,
                "strategies_with_exit_signal_no_order": 0,
                "exit_signals_in_execution_universe": 0,
                "execution_universe_size": 0,
                "sample_strategies": [],
                "likely_causes": ["database_connection_unavailable"],
                "recommendations": [],
            },
        }
    gap = service._exit_signal_gap(conn, sample_limit=sample_limit)
    return {
        "object": "aiask.factory_exit_gap",
        "as_of": _now_iso(),
        "ok": True,
        "exit_gap": gap,
        "exit_funnel": service._exit_funnel(conn),
    }


async def handle_factory_formal_diagnostics(db: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Manager/Agent handler envelope for formal diagnostics."""
    top_n = 15
    if params:
        try:
            top_n = max(1, min(int(params.get("top_n") or 15), 50))
        except Exception:
            top_n = 15
    service = get_factory_diagnostics_service()
    payload = await service.collect_async(db, top_n=top_n)
    return {
        "success": True,
        "data": payload,
        "error": None,
        "meta": {
            "tool": "agent_factory_formal_diagnostics",
            "side_effect": {
                "level": "read_only",
                "confirmation_required": False,
                "idempotent": True,
            },
        },
    }
