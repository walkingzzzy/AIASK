"""Durable task board for strategy factory orchestration.

This is an AIASK-native board inspired by durable agent boards: it stores
factory tasks in SQLite, supports claim heartbeats and stale reclaim, and keeps
artifact references close to the task lifecycle. It intentionally does not
replace the existing scheduler or pipeline; it gives them a recoverable control
plane.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

try:
    from aiask_quant_core.storage.sqlite.strategy_factory_json_budget import (
        bounded_json_text,
        strategy_json_field_max_bytes,
    )
except Exception:  # pragma: no cover - strategy-factory can be imported standalone in narrow tests
    bounded_json_text = None

    def strategy_json_field_max_bytes() -> int:
        return 64 * 1024


TASK_TYPES = frozenset(
    {
        "research",
        "candidate_generation",
        "quality_gate",
        "backtest",
        "dedup",
        "submit",
        "incubation",
        "promotion_review",
    }
)

TASK_STATUSES = frozenset({"ready", "running", "completed", "blocked"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _bounded_dumps(field_name: str, value: Any) -> str:
    if bounded_json_text is None:
        return _dumps(value)
    return bounded_json_text(
        field_name,
        value,
        max_bytes=strategy_json_field_max_bytes(),
    )


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def default_task_board_path() -> Path:
    raw = str(os.getenv("STRATEGY_FACTORY_TASK_BOARD_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".aiask" / "strategy_factory_task_board.sqlite3"


class FactoryTaskBoard:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path else default_task_board_path()

    @classmethod
    def from_env(cls) -> "FactoryTaskBoard":
        return cls(default_task_board_path())

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema(conn)
        return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factory_tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                artifact_refs_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                claimed_by TEXT,
                claim_token TEXT,
                claim_expires_at TEXT,
                last_heartbeat_at TEXT,
                blocked_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factory_task_attempts (
                attempt_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                claimer TEXT,
                claim_token TEXT,
                status TEXT NOT NULL,
                result_json TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                FOREIGN KEY(task_id) REFERENCES factory_tasks(task_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_factory_tasks_status ON factory_tasks(status, claim_expires_at)")
        conn.commit()

    @staticmethod
    def _row_to_task(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        item["artifact_refs"] = _loads(item.pop("artifact_refs_json", None), [])
        return item

    def create_task(
        self,
        *,
        task_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        artifact_refs: list[dict[str, Any]] | None = None,
        task_id: str | None = None,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        normalized_type = str(task_type or "").strip()
        if normalized_type not in TASK_TYPES:
            raise ValueError(f"unsupported factory task type: {normalized_type}")
        tid = str(task_id or "").strip() or f"factory_task_{uuid4().hex[:16]}"
        ts = _iso()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO factory_tasks
                    (task_id, task_type, title, status, payload_json, artifact_refs_json,
                     attempts, max_attempts, created_at, updated_at)
                VALUES (?, ?, ?, 'ready', ?, ?, 0, ?, ?, ?)
                """,
                (
                    tid,
                    normalized_type,
                    str(title or normalized_type).strip() or normalized_type,
                    _bounded_dumps("factory_tasks.payload_json", dict(payload or {})),
                    _bounded_dumps("factory_tasks.artifact_refs_json", list(artifact_refs or [])),
                    max(1, int(max_attempts or 3)),
                    ts,
                    ts,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (tid,)).fetchone()
        task = self._row_to_task(row)
        assert task is not None
        return task

    def claim_task(
        self,
        task_id: str | None = None,
        *,
        worker_id: str | None = None,
        task_type: str | None = None,
        ttl_seconds: int = 300,
    ) -> dict[str, Any] | None:
        claimer = str(worker_id or "strategy_factory_worker").strip()
        expires_at = _iso(_now() + timedelta(seconds=max(1, int(ttl_seconds or 300))))
        token = f"claim_{uuid4().hex[:16]}"
        ts = _iso()
        with closing(self._connect()) as conn:
            params: list[Any] = []
            where = "status = 'ready'"
            if task_id:
                where += " AND task_id = ?"
                params.append(str(task_id).strip())
            if task_type:
                where += " AND task_type = ?"
                params.append(str(task_type).strip())
            row = conn.execute(
                f"SELECT * FROM factory_tasks WHERE {where} ORDER BY created_at LIMIT 1",
                tuple(params),
            ).fetchone()
            if row is None:
                return None
            attempts = int(row["attempts"] or 0) + 1
            if attempts > int(row["max_attempts"] or 1):
                conn.execute(
                    """
                    UPDATE factory_tasks
                    SET status = 'blocked', blocked_reason = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    ("retry budget exhausted", ts, row["task_id"]),
                )
                conn.commit()
                return self._row_to_task(conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (row["task_id"],)).fetchone())
            conn.execute(
                """
                UPDATE factory_tasks
                SET status = 'running', attempts = ?, claimed_by = ?, claim_token = ?,
                    claim_expires_at = ?, last_heartbeat_at = ?, updated_at = ?
                WHERE task_id = ? AND status = 'ready'
                """,
                (attempts, claimer, token, expires_at, ts, ts, row["task_id"]),
            )
            conn.execute(
                """
                INSERT INTO factory_task_attempts
                    (attempt_id, task_id, claimer, claim_token, status, started_at)
                VALUES (?, ?, ?, ?, 'running', ?)
                """,
                (f"attempt_{uuid4().hex[:16]}", row["task_id"], claimer, token, ts),
            )
            conn.commit()
            claimed = conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
        return self._row_to_task(claimed)

    def heartbeat(self, task_id: str, claim_token: str | None = None, *, ttl_seconds: int = 300) -> dict[str, Any] | None:
        ts = _iso()
        expires_at = _iso(_now() + timedelta(seconds=max(1, int(ttl_seconds or 300))))
        with closing(self._connect()) as conn:
            values: list[Any] = [ts, expires_at, ts, str(task_id or "").strip()]
            where = "task_id = ? AND status = 'running'"
            if claim_token:
                where += " AND claim_token = ?"
                values.append(str(claim_token))
            conn.execute(
                f"""
                UPDATE factory_tasks
                SET last_heartbeat_at = ?, claim_expires_at = ?, updated_at = ?
                WHERE {where}
                """,
                tuple(values),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (str(task_id or "").strip(),)).fetchone()
        return self._row_to_task(row)

    def complete_task(
        self,
        task_id: str,
        *,
        claim_token: str | None = None,
        artifact_refs: list[dict[str, Any]] | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        ts = _iso()
        with closing(self._connect()) as conn:
            current = conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (str(task_id or "").strip(),)).fetchone()
            if current is None:
                return None
            refs = list(artifact_refs if artifact_refs is not None else _loads(current["artifact_refs_json"], []))
            values: list[Any] = [
                _bounded_dumps("factory_tasks.artifact_refs_json", refs),
                ts,
                ts,
                str(task_id or "").strip(),
            ]
            where = "task_id = ?"
            if claim_token:
                where += " AND claim_token = ?"
                values.append(str(claim_token))
            conn.execute(
                f"""
                UPDATE factory_tasks
                SET status = 'completed', artifact_refs_json = ?, completed_at = ?,
                    updated_at = ?, claim_expires_at = NULL
                WHERE {where}
                """,
                tuple(values),
            )
            conn.execute(
                """
                UPDATE factory_task_attempts
                SET status = 'completed', result_json = ?, ended_at = ?
                WHERE task_id = ? AND ended_at IS NULL
                """,
                (_bounded_dumps("factory_task_attempts.result_json", dict(result or {})), ts, str(task_id or "").strip()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (str(task_id or "").strip(),)).fetchone()
        return self._row_to_task(row)

    def block_task(self, task_id: str, reason: str, *, claim_token: str | None = None) -> dict[str, Any] | None:
        ts = _iso()
        with closing(self._connect()) as conn:
            values: list[Any] = [str(reason or "blocked"), ts, str(task_id or "").strip()]
            where = "task_id = ?"
            if claim_token:
                where += " AND claim_token = ?"
                values.append(str(claim_token))
            conn.execute(
                f"""
                UPDATE factory_tasks
                SET status = 'blocked', blocked_reason = ?, updated_at = ?,
                    claim_expires_at = NULL
                WHERE {where}
                """,
                tuple(values),
            )
            conn.execute(
                """
                UPDATE factory_task_attempts
                SET status = 'blocked', result_json = ?, ended_at = ?
                WHERE task_id = ? AND ended_at IS NULL
                """,
                (_bounded_dumps("factory_task_attempts.result_json", {"blocked_reason": reason}), ts, str(task_id or "").strip()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (str(task_id or "").strip(),)).fetchone()
        return self._row_to_task(row)

    def reclaim_stale(
        self,
        *,
        now: datetime | None = None,
        block_task_types: Iterable[str] | None = None,
        block_reason: str | None = None,
    ) -> list[dict[str, Any]]:
        cutoff = _iso(now or _now())
        ts = _iso()
        blocking_types = {
            str(item or "").strip()
            for item in list(block_task_types or [])
            if str(item or "").strip()
        }
        reclaimed_ids: list[str] = []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM factory_tasks
                WHERE status = 'running'
                  AND claim_expires_at IS NOT NULL
                  AND claim_expires_at < ?
                """,
                (cutoff,),
            ).fetchall()
            for row in rows:
                if str(row["task_type"] or "").strip() in blocking_types:
                    next_status = "blocked"
                    reason = block_reason or "stale running task reclaimed as blocked"
                else:
                    next_status = "ready" if int(row["attempts"] or 0) < int(row["max_attempts"] or 1) else "blocked"
                    reason = None if next_status == "ready" else "retry budget exhausted after stale reclaim"
                attempt_status = "blocked" if next_status == "blocked" else "reclaimed"
                conn.execute(
                    """
                    UPDATE factory_tasks
                    SET status = ?, blocked_reason = ?, claim_token = NULL, claimed_by = NULL,
                        claim_expires_at = NULL, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (next_status, reason, ts, row["task_id"]),
                )
                conn.execute(
                    """
                    UPDATE factory_task_attempts
                    SET status = ?, result_json = ?, ended_at = ?
                    WHERE task_id = ? AND ended_at IS NULL
                    """,
                    (
                        attempt_status,
                        _bounded_dumps("factory_task_attempts.result_json", {"reclaim_reason": reason or "stale claim expired"}),
                        ts,
                        row["task_id"],
                    ),
                )
                reclaimed_ids.append(str(row["task_id"]))
            conn.commit()
            updated_rows = [
                conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (task_id,)).fetchone()
                for task_id in reclaimed_ids
            ]
        return [item for item in (self._row_to_task(row) for row in updated_rows) if item is not None]

    def list_tasks(
        self,
        *,
        statuses: Iterable[str] | None = None,
        task_type: str | None = None,
        title: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        normalized_statuses = [
            str(item or "").strip()
            for item in list(statuses or [])
            if str(item or "").strip()
        ]
        if normalized_statuses:
            placeholders = ", ".join("?" for _ in normalized_statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(normalized_statuses)
        if task_type:
            clauses.append("task_type = ?")
            params.append(str(task_type).strip())
        if title:
            clauses.append("title = ?")
            params.append(str(title).strip())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        max_rows = max(1, min(int(limit or 100), 1000))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT * FROM factory_tasks{where} ORDER BY created_at LIMIT ?",
                tuple(params + [max_rows]),
            ).fetchall()
        return [task for task in (self._row_to_task(row) for row in rows) if task is not None]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM factory_tasks WHERE task_id = ?", (str(task_id or "").strip(),)).fetchone()
        return self._row_to_task(row)

__all__ = ["FactoryTaskBoard", "TASK_STATUSES", "TASK_TYPES", "default_task_board_path"]
