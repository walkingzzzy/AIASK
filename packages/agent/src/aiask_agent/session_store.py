from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .paths import default_state_db_path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


class AgentSessionStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_db_path()
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.RLock()
        self._schema_ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if not self._schema_ready:
            conn.execute("PRAGMA journal_mode=WAL")
            self._ensure_schema(conn)
            self._schema_ready = True
        return conn

    @contextmanager
    def _connection(self) -> Any:
        with self._conn_lock:
            if self._conn is None:
                self._conn = self._connect()
            try:
                yield self._conn
            except Exception:
                self._conn.rollback()
                raise

    def ensure_ready(self) -> None:
        with self._connection():
            pass

    def close(self) -> None:
        with self._conn_lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                name TEXT,
                tool_call_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS responses (
                response_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                accessed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_handoffs (
                handoff_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT,
                target TEXT,
                status TEXT NOT NULL,
                reason TEXT,
                summary TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subgoals (
                subgoal_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT,
                title TEXT NOT NULL,
                criteria_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
            CREATE INDEX IF NOT EXISTS idx_responses_session ON responses(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, event_id);
            CREATE INDEX IF NOT EXISTS idx_session_handoffs_session ON session_handoffs(session_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_subgoals_session ON subgoals(session_id, updated_at);
            """
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS aiask_search_fts
                USING fts5(kind, object_id, session_id, user_id, content, payload_json)
                """
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()

    def create_session(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        sid = str(session_id or uuid4()).strip()
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sessions
                    (session_id, user_id, title, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sid, user_id, title, ts, ts, _dumps(dict(metadata or {}))),
            )
            conn.commit()
        return sid

    def touch_session(self, session_id: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now_iso(), session_id),
            )
            conn.commit()

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        payload = dict(message or {})
        role = str(payload.get("role") or "").strip() or "user"
        content = payload.get("content")
        if not isinstance(content, str):
            content = _dumps(content)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO messages
                    (session_id, role, content, name, tool_call_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    payload.get("name"),
                    payload.get("tool_call_id"),
                    _dumps(payload),
                    now_iso(),
                ),
            )
            message_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._index_search_row(
                conn,
                kind="message",
                object_id=str(message_id),
                session_id=session_id,
                user_id=self._session_user_id(conn, session_id),
                content=str(content or ""),
                payload=payload,
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now_iso(), session_id),
            )
            conn.commit()

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [_loads(row["payload_json"], {}) for row in rows]

    def save_response(self, response_id: str, session_id: str, payload: dict[str, Any]) -> None:
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO responses
                    (response_id, session_id, payload_json, created_at, accessed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (response_id, session_id, _dumps(payload), ts, ts),
            )
            self._index_search_row(
                conn,
                kind="response",
                object_id=response_id,
                session_id=session_id,
                user_id=self._session_user_id(conn, session_id),
                content=str(payload.get("content") or payload.get("output_text") or ""),
                payload=payload,
            )
            conn.commit()

    def get_response(self, response_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM responses WHERE response_id = ?",
                (response_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE responses SET accessed_at = ? WHERE response_id = ?",
                    (now_iso(), response_id),
                )
                conn.commit()
        return _loads(row["payload_json"], {}) if row else None

    def delete_response(self, response_id: str) -> bool:
        with self._connection() as conn:
            cur = conn.execute("DELETE FROM responses WHERE response_id = ?", (response_id,))
            conn.commit()
            return cur.rowcount > 0

    def create_run(self, session_id: str, payload: dict[str, Any] | None = None) -> str:
        run_id = f"run_{uuid4().hex}"
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, session_id, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, session_id, "queued", _dumps(dict(payload or {})), ts, ts),
            )
            conn.commit()
        return run_id

    def update_run(self, run_id: str, *, status: str, payload: dict[str, Any] | None = None) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, payload_json = ?, updated_at = ? WHERE run_id = ?",
                (status, _dumps(dict(payload or {})), now_iso(), run_id),
            )
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT run_id, session_id, status, payload_json, created_at, updated_at FROM runs WHERE run_id = ?",
                (str(run_id or "").strip(),),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        return item

    def append_run_event(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO run_events (run_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, event_type, _dumps(dict(payload or {})), ts),
            )
            event_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
        return {
            "id": str(event_id),
            "event": event_type,
            "run_id": run_id,
            "created_at": ts,
            "data": dict(payload or {}),
        }

    def list_run_events(self, run_id: str, *, after_event_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT event_id, run_id, event_type, payload_json, created_at
                FROM run_events
                WHERE run_id = ? AND event_id > ?
                ORDER BY event_id ASC
                LIMIT ?
                """,
                (str(run_id or "").strip(), int(after_event_id or 0), max(1, min(int(limit or 500), 5000))),
            ).fetchall()
        return [
            {
                "id": str(row["event_id"]),
                "event": row["event_type"],
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "data": _loads(row["payload_json"], {}),
            }
            for row in rows
        ]

    def list_session_messages(self, session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, name, tool_call_id, payload_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (str(session_id or "").strip(), max(1, min(int(limit or 200), 2000))),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = _loads(item.pop("payload_json", None), {})
            items.append(item)
        return items

    def list_sessions(self, *, user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            values.append(user_id)
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT session_id, user_id, title, created_at, updated_at, metadata_json
                FROM sessions
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = _loads(item.pop("metadata_json", None), {})
            items.append(item)
        return items

    def request_handoff(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        target: str | None = None,
        reason: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        handoff_id = f"handoff_{uuid4().hex}"
        ts = now_iso()
        sid = str(session_id or "default").strip() or "default"
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO session_handoffs
                    (handoff_id, session_id, user_id, target, status, reason, summary, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    handoff_id,
                    sid,
                    user_id,
                    target,
                    "requested",
                    reason,
                    summary,
                    _dumps(dict(metadata or {})),
                    ts,
                    ts,
                ),
            )
            conn.commit()
        item = self.get_handoff(handoff_id)
        assert item is not None
        return item

    def get_handoff(self, handoff_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM session_handoffs WHERE handoff_id = ?",
                (str(handoff_id or "").strip(),),
            ).fetchone()
        return self._handoff_row(row)

    def update_handoff(self, handoff_id: str, *, status: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        token = str(handoff_id or "").strip()
        if not token:
            raise ValueError("handoff_id is required")
        current = self.get_handoff(token)
        if current is None:
            raise FileNotFoundError(f"handoff not found: {token}")
        merged = dict(current.get("metadata") or {})
        merged.update(dict(metadata or {}))
        with self._connection() as conn:
            conn.execute(
                "UPDATE session_handoffs SET status = ?, metadata_json = ?, updated_at = ? WHERE handoff_id = ?",
                (str(status or "requested"), _dumps(merged), now_iso(), token),
            )
            conn.commit()
        item = self.get_handoff(token)
        assert item is not None
        return item

    def list_handoffs(
        self,
        *,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            values.append(str(session_id))
        if status:
            clauses.append("status = ?")
            values.append(str(status))
        values.append(max(1, min(int(limit or 100), 200)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM session_handoffs {where} ORDER BY updated_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._handoff_row(row)) is not None]

    def upsert_subgoal(
        self,
        *,
        session_id: str,
        subgoal_id: str | None = None,
        user_id: str | None = None,
        title: str,
        criteria: list[str] | None = None,
        status: str = "pending",
    ) -> dict[str, Any]:
        sid = str(session_id or "default").strip() or "default"
        goal_id = str(subgoal_id or f"subgoal_{uuid4().hex[:12]}").strip()
        if not str(title or "").strip():
            raise ValueError("title is required")
        normalized_status = str(status or "pending").strip().lower()
        if normalized_status not in {"pending", "in_progress", "completed", "cancelled"}:
            normalized_status = "pending"
        ts = now_iso()
        with self._connection() as conn:
            existing = conn.execute("SELECT created_at FROM subgoals WHERE subgoal_id = ?", (goal_id,)).fetchone()
            created_at = existing["created_at"] if existing else ts
            conn.execute(
                """
                INSERT OR REPLACE INTO subgoals
                    (subgoal_id, session_id, user_id, title, criteria_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal_id,
                    sid,
                    user_id,
                    str(title).strip(),
                    _dumps([str(item) for item in list(criteria or []) if str(item).strip()]),
                    normalized_status,
                    created_at,
                    ts,
                ),
            )
            conn.commit()
        item = self.get_subgoal(goal_id)
        assert item is not None
        return item

    def get_subgoal(self, subgoal_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM subgoals WHERE subgoal_id = ?",
                (str(subgoal_id or "").strip(),),
            ).fetchone()
        return self._subgoal_row(row)

    def list_subgoals(self, *, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM subgoals
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (str(session_id or "default").strip() or "default", max(1, min(int(limit or 100), 200))),
            ).fetchall()
        return [item for row in rows if (item := self._subgoal_row(row)) is not None]

    def clear_subgoals(self, *, session_id: str) -> list[dict[str, Any]]:
        sid = str(session_id or "default").strip() or "default"
        with self._connection() as conn:
            conn.execute("DELETE FROM subgoals WHERE session_id = ?", (sid,))
            conn.commit()
        return []

    def search(
        self,
        *,
        query: str,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        token = str(query or "").strip()
        max_rows = max(1, min(int(limit or 20), 200))
        if not token:
            return []
        with self._connection() as conn:
            try:
                clauses = ["aiask_search_fts MATCH ?"]
                values: list[Any] = [token]
                if session_id:
                    clauses.append("session_id = ?")
                    values.append(session_id)
                if user_id:
                    clauses.append("user_id = ?")
                    values.append(user_id)
                values.append(max_rows)
                rows = conn.execute(
                    f"""
                    SELECT kind, object_id, session_id, user_id, content, payload_json
                    FROM aiask_search_fts
                    WHERE {" AND ".join(clauses)}
                    LIMIT ?
                    """,
                    tuple(values),
                ).fetchall()
                return [self._search_row(row) for row in rows]
            except sqlite3.OperationalError:
                return self._search_like(conn, token=token, session_id=session_id, limit=max_rows)

    @staticmethod
    def _index_search_row(
        conn: sqlite3.Connection,
        *,
        kind: str,
        object_id: str,
        session_id: str,
        user_id: str | None,
        content: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            conn.execute(
                "DELETE FROM aiask_search_fts WHERE kind = ? AND object_id = ?",
                (kind, object_id),
            )
            conn.execute(
                """
                INSERT INTO aiask_search_fts (kind, object_id, session_id, user_id, content, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (kind, object_id, session_id, user_id, content, _dumps(payload)),
            )
        except sqlite3.OperationalError:
            return

    @staticmethod
    def _search_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        return item

    @staticmethod
    def _search_like(
        conn: sqlite3.Connection,
        *,
        token: str,
        session_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        values: list[Any] = [f"%{token}%"]
        clauses = ["content LIKE ?"]
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        values.append(limit)
        rows = conn.execute(
            f"""
            SELECT 'message' AS kind, CAST(id AS TEXT) AS object_id, session_id, NULL AS user_id, content, payload_json
            FROM messages
            WHERE {" AND ".join(clauses)}
            ORDER BY id DESC
            LIMIT ?
            """,
            tuple(values),
        ).fetchall()
        return [AgentSessionStore._search_row(row) for row in rows]

    @staticmethod
    def _handoff_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["metadata"] = _loads(item.pop("metadata_json", None), {})
        return item

    @staticmethod
    def _subgoal_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["criteria"] = _loads(item.pop("criteria_json", None), [])
        return item

    @staticmethod
    def _session_user_id(conn: sqlite3.Connection, session_id: str) -> str | None:
        row = conn.execute("SELECT user_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return row["user_id"] if row else None
