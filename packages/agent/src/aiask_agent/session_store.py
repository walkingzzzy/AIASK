from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .paths import default_state_db_path


SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "broker_token",
    "cookie",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(0, int(days or 0)))).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_text(value: Any, *, limit: int = 2000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated {len(text) - limit} chars>"


def _is_secret_key(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def _clean_optional(value: Any, *, limit: int = 500) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


def _int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _side_effect_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()[:200] or None
    if isinstance(value, dict):
        for key in ("level", "side_effect", "type"):
            if value.get(key):
                return str(value.get(key)).strip()[:200]
        return _dumps(sanitize_for_audit(value))[:500]
    return str(value).strip()[:200] or None


def sanitize_for_audit(value: Any, *, max_depth: int = 4, max_items: int = 40, max_text: int = 2000) -> Any:
    """Return a bounded, secret-redacted copy that is safe for local audit rows."""
    if max_depth <= 0:
        if isinstance(value, (dict, list, tuple)):
            return {"truncated": True, "type": value.__class__.__name__}
        return _bounded_text(value, limit=max_text) if isinstance(value, str) else value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_text(value, limit=max_text)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                result["_truncated_items"] = max(0, len(value) - max_items)
                break
            text_key = str(key)
            if _is_secret_key(text_key):
                result[text_key] = "[redacted]"
            else:
                result[text_key] = sanitize_for_audit(item, max_depth=max_depth - 1, max_items=max_items, max_text=max_text)
        return result
    if isinstance(value, (list, tuple)):
        items = [
            sanitize_for_audit(item, max_depth=max_depth - 1, max_items=max_items, max_text=max_text)
            for item in list(value)[:max_items]
        ]
        if len(value) > max_items:
            items.append({"_truncated_items": len(value) - max_items})
        return items
    return _bounded_text(value, limit=max_text)


def _metadata_archived(metadata: dict[str, Any] | None) -> bool:
    value = dict(metadata or {}).get("archived")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "archived"}
    return bool(value)


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
                created_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_reason TEXT,
                deleted_by TEXT
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
            CREATE TABLE IF NOT EXISTS user_activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                session_id TEXT,
                run_id TEXT,
                trace_id TEXT,
                page_key TEXT,
                route TEXT,
                event_type TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                target_label TEXT,
                target_testid TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT 'desktop',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tool_invocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invocation_id TEXT NOT NULL UNIQUE,
                user_id TEXT,
                session_id TEXT,
                run_id TEXT,
                trace_id TEXT,
                tool_name TEXT NOT NULL,
                capability TEXT,
                category TEXT,
                side_effect TEXT,
                status TEXT NOT NULL,
                input_summary_json TEXT NOT NULL DEFAULT '{}',
                output_summary_json TEXT NOT NULL DEFAULT '{}',
                error_code TEXT,
                error_summary TEXT,
                duration_ms INTEGER,
                approval_id TEXT,
                action_intent_id TEXT,
                source_chain_json TEXT NOT NULL DEFAULT '[]',
                secrets_redacted INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL UNIQUE,
                user_id TEXT,
                session_id TEXT,
                run_id TEXT,
                trace_id TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                provider TEXT,
                source_type TEXT NOT NULL,
                title TEXT,
                url TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                data_timestamp TEXT,
                excerpt TEXT,
                source_tier TEXT,
                credibility_score REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id TEXT NOT NULL UNIQUE,
                user_id TEXT,
                session_id TEXT,
                run_id TEXT,
                trace_id TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                path TEXT,
                uri TEXT,
                mime_type TEXT,
                size_bytes INTEGER,
                sha256 TEXT,
                preview_text TEXT,
                preview_json TEXT NOT NULL DEFAULT '{}',
                source_id TEXT,
                status TEXT NOT NULL DEFAULT 'ready',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS context_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                user_id TEXT,
                session_id TEXT NOT NULL,
                run_id TEXT,
                trace_id TEXT,
                context_summary_id TEXT,
                policy TEXT NOT NULL DEFAULT 'runtime_prepare',
                compacted INTEGER NOT NULL DEFAULT 0,
                message_count INTEGER NOT NULL DEFAULT 0,
                source_message_ids_json TEXT NOT NULL DEFAULT '[]',
                source_ids_json TEXT NOT NULL DEFAULT '[]',
                artifact_ids_json TEXT NOT NULL DEFAULT '[]',
                token_estimate_before INTEGER,
                token_estimate_after INTEGER,
                summary TEXT,
                summary_model TEXT,
                risk_flags_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feedback_id TEXT NOT NULL UNIQUE,
                user_id TEXT,
                session_id TEXT,
                run_id TEXT,
                target_type TEXT NOT NULL,
                target_id TEXT,
                feedback_type TEXT NOT NULL,
                rating INTEGER,
                comment TEXT,
                allow_learning INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_data_policies (
                user_id TEXT PRIMARY KEY,
                event_ttl_days INTEGER NOT NULL DEFAULT 90,
                audit_ttl_days INTEGER NOT NULL DEFAULT 180,
                run_event_ttl_days INTEGER NOT NULL DEFAULT 180,
                tool_payload_ttl_days INTEGER NOT NULL DEFAULT 90,
                conversation_retention TEXT NOT NULL DEFAULT 'keep_until_user_deletes',
                allow_product_analytics INTEGER NOT NULL DEFAULT 1,
                allow_learning INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS broker_profiles (
                broker_profile_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                display_name TEXT,
                account_ref_hash TEXT,
                market TEXT,
                read_only_enabled INTEGER NOT NULL DEFAULT 1,
                write_enabled INTEGER NOT NULL DEFAULT 0,
                consent_status TEXT NOT NULL DEFAULT 'unknown',
                consent_version TEXT,
                status TEXT NOT NULL DEFAULT 'unconfigured',
                error_code TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                last_sync_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS broker_account_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                broker_profile_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                account_ref_hash TEXT,
                currency TEXT,
                total_asset REAL,
                cash_available REAL,
                market_value REAL,
                frozen_cash REAL,
                buying_power REAL,
                source_tool TEXT,
                source_run_id TEXT,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS broker_position_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                broker_profile_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                symbol TEXT,
                exchange TEXT,
                name TEXT,
                quantity REAL,
                available_quantity REAL,
                cost_basis REAL,
                last_price REAL,
                market_value REAL,
                unrealized_pnl REAL,
                unrealized_pnl_pct REAL,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS broker_order_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                broker_profile_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                order_ref_hash TEXT,
                symbol TEXT,
                side TEXT,
                order_type TEXT,
                price REAL,
                quantity REAL,
                filled_quantity REAL,
                status TEXT,
                submitted_at TEXT,
                updated_at TEXT,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS broker_deal_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                broker_profile_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                deal_ref_hash TEXT,
                order_ref_hash TEXT,
                symbol TEXT,
                side TEXT,
                price REAL,
                quantity REAL,
                amount REAL,
                fee REAL,
                occurred_at TEXT,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS broker_behavior_analytics (
                analytics_id TEXT PRIMARY KEY,
                broker_profile_id TEXT,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                signals_json TEXT NOT NULL DEFAULT '{}',
                risk_flags_json TEXT NOT NULL DEFAULT '[]',
                source_snapshot_ids_json TEXT NOT NULL DEFAULT '{}',
                model_version TEXT NOT NULL DEFAULT 'deterministic-p0',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
            CREATE INDEX IF NOT EXISTS idx_responses_session ON responses(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, event_id);
            CREATE INDEX IF NOT EXISTS idx_session_handoffs_session ON session_handoffs(session_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_subgoals_session ON subgoals(session_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_user_activity_events_user_created ON user_activity_events(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_user_activity_events_session_created ON user_activity_events(session_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_user_activity_events_page_created ON user_activity_events(page_key, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tool_invocations_user_created ON tool_invocations(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tool_invocations_run_created ON tool_invocations(run_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_tool_invocations_tool_created ON tool_invocations(tool_name, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_agent_sources_run_created ON agent_sources(run_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_agent_sources_session_created ON agent_sources(session_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_agent_sources_tool_call ON agent_sources(tool_call_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_agent_sources_url ON agent_sources(url);
            CREATE INDEX IF NOT EXISTS idx_agent_artifacts_run_created ON agent_artifacts(run_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_agent_artifacts_session_created ON agent_artifacts(session_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_agent_artifacts_tool_call ON agent_artifacts(tool_call_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_agent_artifacts_path ON agent_artifacts(path);
            CREATE INDEX IF NOT EXISTS idx_context_snapshots_run_created ON context_snapshots(run_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_context_snapshots_session_created ON context_snapshots(session_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_context_snapshots_user_created ON context_snapshots(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_feedback_events_user_created ON feedback_events(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_feedback_events_target ON feedback_events(target_type, target_id);
            CREATE INDEX IF NOT EXISTS idx_broker_profiles_user_provider ON broker_profiles(user_id, provider, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_broker_account_user_provider ON broker_account_snapshots(user_id, provider, observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_broker_position_user_provider ON broker_position_snapshots(user_id, provider, observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_broker_order_user_provider ON broker_order_snapshots(user_id, provider, observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_broker_deal_user_provider ON broker_deal_snapshots(user_id, provider, observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_broker_analytics_user_provider ON broker_behavior_analytics(user_id, provider, created_at DESC);
            """
        )
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        for column, ddl in {
            "deleted_at": "ALTER TABLE messages ADD COLUMN deleted_at TEXT",
            "deleted_reason": "ALTER TABLE messages ADD COLUMN deleted_reason TEXT",
            "deleted_by": "ALTER TABLE messages ADD COLUMN deleted_by TEXT",
        }.items():
            if column not in existing_columns:
                conn.execute(ddl)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_active ON messages(session_id, deleted_at, id)")
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

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT session_id, user_id, title, created_at, updated_at, metadata_json
                FROM sessions
                WHERE session_id = ?
                """,
                (str(session_id or "").strip(),),
            ).fetchone()
        return self._session_row(row)

    def update_session_metadata(
        self,
        session_id: str,
        updates: dict[str, Any],
        *,
        remove_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        ts = now_iso()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT session_id, user_id, title, created_at, updated_at, metadata_json FROM sessions WHERE session_id = ?",
                (sid,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"session not found: {sid}")
            metadata = _loads(row["metadata_json"], {})
            for key in list(remove_keys or []):
                metadata.pop(str(key), None)
            metadata.update(dict(updates or {}))
            conn.execute(
                "UPDATE sessions SET metadata_json = ?, updated_at = ? WHERE session_id = ?",
                (_dumps(metadata), ts, sid),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT session_id, user_id, title, created_at, updated_at, metadata_json FROM sessions WHERE session_id = ?",
                (sid,),
            ).fetchone()
        item = self._session_row(updated)
        assert item is not None
        return item

    def set_session_handoff_state(
        self,
        session_id: str,
        *,
        status: str,
        handoff_id: str | None = None,
        target: str | None = None,
        source_run_id: str | None = None,
        source_tool_call_id: str | None = None,
        context_snapshot_id: str | None = None,
        summary: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_status = str(status or "pending").strip().lower() or "pending"
        handoff_state = {
            "status": normalized_status,
            "handoff_id": _clean_optional(handoff_id),
            "target": _clean_optional(target),
            "source_run_id": _clean_optional(source_run_id),
            "source_tool_call_id": _clean_optional(source_tool_call_id),
            "context_snapshot_id": _clean_optional(context_snapshot_id),
            "summary": _bounded_text(summary, limit=4000) if summary else None,
            "reason": _bounded_text(reason, limit=1000) if reason else None,
            "updated_at": now_iso(),
            "metadata": sanitize_for_audit(dict(metadata or {})),
        }
        session = self.update_session_metadata(
            session_id,
            {
                "handoff_state": handoff_state,
                "handoff_status": normalized_status,
                "handoff_target": _clean_optional(target),
                "handoff_id": _clean_optional(handoff_id),
                "handoff_context_snapshot_id": _clean_optional(context_snapshot_id),
            },
        )
        return dict(session.get("metadata") or {}).get("handoff_state") or handoff_state

    def consume_session_handoff_state(
        self,
        session_id: str,
        *,
        run_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any] | None:
        session = self.get_session(session_id)
        metadata = dict((session or {}).get("metadata") or {})
        state = dict(metadata.get("handoff_state") or {})
        if str(state.get("status") or "").strip().lower() != "pending":
            return None
        consumed = {
            **state,
            "status": "active",
            "active_run_id": _clean_optional(run_id),
            "active_trace_id": _clean_optional(trace_id),
            "activated_at": now_iso(),
        }
        updated = self.update_session_metadata(
            session_id,
            {
                "handoff_state": consumed,
                "handoff_status": "active",
                "active_agent": _clean_optional(state.get("target")) or "handoff_target",
                "last_handoff_id": _clean_optional(state.get("handoff_id")),
                "active_context_snapshot_id": _clean_optional(state.get("context_snapshot_id")),
            },
        )
        return dict(updated.get("metadata") or {}).get("handoff_state") or consumed

    def set_session_archived(
        self,
        session_id: str,
        archived: bool = True,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        ts = now_iso()
        cleaned_reason = str(reason or ("archived" if archived else "unarchived")).strip()[:500]
        cleaned_actor = str(actor or "control_token").strip()[:200] or "control_token"
        updates: dict[str, Any] = {
            "archived": bool(archived),
            "archived_updated_at": ts,
            "archived_updated_by": cleaned_actor,
        }
        if archived:
            updates.update(
                {
                    "archived_at": ts,
                    "archived_reason": cleaned_reason or "archived",
                    "archived_by": cleaned_actor,
                }
            )
        else:
            updates.update(
                {
                    "archived_at": None,
                    "archived_reason": None,
                    "unarchived_at": ts,
                    "unarchived_reason": cleaned_reason or "unarchived",
                    "unarchived_by": cleaned_actor,
                }
            )
        session = self.update_session_metadata(session_id, updates)
        return {
            "session_id": session["session_id"],
            "archived": bool(archived),
            "archived_at": (session.get("metadata") or {}).get("archived_at"),
            "archived_reason": (session.get("metadata") or {}).get("archived_reason"),
            "session": session,
        }

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
                "SELECT payload_json FROM messages WHERE session_id = ? AND deleted_at IS NULL ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [_loads(row["payload_json"], {}) for row in rows]

    def undo_last_turns(
        self,
        session_id: str,
        turns: int = 1,
        *,
        reason: str | None = None,
        deleted_by: str | None = None,
    ) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        try:
            turns_requested = int(turns or 1)
        except (TypeError, ValueError):
            turns_requested = 1
        turns_requested = max(1, min(turns_requested, 100))
        ts = now_iso()
        cleaned_reason = str(reason or "hermes_undo").strip()[:500] or "hermes_undo"
        cleaned_deleted_by = str(deleted_by or "control_token").strip()[:200] or "control_token"

        with self._connection() as conn:
            turn_rows = conn.execute(
                """
                SELECT id
                FROM messages
                WHERE session_id = ? AND deleted_at IS NULL AND role = 'user'
                ORDER BY id DESC
                LIMIT ?
                """,
                (sid, turns_requested),
            ).fetchall()
            if not turn_rows:
                return {
                    "session_id": sid,
                    "turns_requested": turns_requested,
                    "turns_undone": 0,
                    "message_ids": [],
                    "message_count": 0,
                    "deleted_at": ts,
                    "deleted_reason": cleaned_reason,
                    "deleted_by": cleaned_deleted_by,
                    "soft_deleted": True,
                    "side_effects_rolled_back": False,
                    "external_side_effects": "not_rolled_back",
                }

            cutoff_id = min(int(row["id"]) for row in turn_rows)
            rows = conn.execute(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE session_id = ? AND deleted_at IS NULL AND id >= ?
                ORDER BY id ASC
                """,
                (sid, cutoff_id),
            ).fetchall()
            message_ids = [int(row["id"]) for row in rows]
            if message_ids:
                placeholders = ", ".join("?" for _ in message_ids)
                conn.execute(
                    f"""
                    UPDATE messages
                    SET deleted_at = ?, deleted_reason = ?, deleted_by = ?
                    WHERE id IN ({placeholders})
                    """,
                    (ts, cleaned_reason, cleaned_deleted_by, *message_ids),
                )
                try:
                    conn.executemany(
                        "DELETE FROM aiask_search_fts WHERE kind = ? AND object_id = ?",
                        [("message", str(message_id)) for message_id in message_ids],
                    )
                except sqlite3.OperationalError:
                    pass
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                    (ts, sid),
                )
            conn.commit()

        return {
            "session_id": sid,
            "turns_requested": turns_requested,
            "turns_undone": len(turn_rows),
            "message_ids": message_ids,
            "message_count": len(message_ids),
            "deleted_at": ts,
            "deleted_reason": cleaned_reason,
            "deleted_by": cleaned_deleted_by,
            "soft_deleted": True,
            "side_effects_rolled_back": False,
            "external_side_effects": "not_rolled_back",
        }

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

    def list_runs(
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
            values.append(str(session_id).strip())
        if status:
            clauses.append("status = ?")
            values.append(str(status).strip())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT run_id, session_id, status, payload_json, created_at, updated_at
                FROM runs
                {where}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = _loads(item.pop("payload_json", None), {})
            items.append(item)
        return items

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

    def count_run_events(self, run_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM run_events WHERE run_id = ?",
                (str(run_id or "").strip(),),
            ).fetchone()
        return int((row["total"] if row else 0) or 0)

    def latest_message_at(self, session_id: str) -> str | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT created_at
                FROM messages
                WHERE session_id = ? AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(session_id or "").strip(),),
            ).fetchone()
        return str(row["created_at"]) if row and row["created_at"] else None

    def count_session_messages(self, session_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM messages WHERE session_id = ? AND deleted_at IS NULL",
                (str(session_id or "").strip(),),
            ).fetchone()
        return int((row["total"] if row else 0) or 0)

    def list_session_messages(self, session_id: str, *, limit: int = 200, include_deleted: bool = False) -> list[dict[str, Any]]:
        deleted_filter = "" if include_deleted else "AND deleted_at IS NULL"
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, role, content, name, tool_call_id, payload_json, created_at, deleted_at, deleted_reason, deleted_by
                FROM messages
                WHERE session_id = ? {deleted_filter}
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

    def list_sessions(
        self,
        *,
        user_id: str | None = None,
        limit: int = 100,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        max_rows = max(1, min(int(limit or 100), 1000))
        if user_id:
            clauses.append("user_id = ?")
            values.append(user_id)
        values.append(5000 if not include_archived else max_rows)
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
            item = self._session_row(row)
            if item is None:
                continue
            if not include_archived and _metadata_archived(item.get("metadata")):
                continue
            items.append(item)
            if len(items) >= max_rows:
                break
        return items

    def record_activity_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event or {})
        event_type = str(payload.get("event_type") or payload.get("type") or "").strip()
        if not event_type:
            raise ValueError("event_type is required")
        ts = str(payload.get("created_at") or now_iso())
        safe_payload = sanitize_for_audit(payload.get("payload") if "payload" in payload else payload.get("payload_json", {}))
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO user_activity_events
                    (user_id, session_id, run_id, trace_id, page_key, route, event_type,
                     target_type, target_id, target_label, target_testid, payload_json, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _clean_optional(payload.get("user_id")),
                    _clean_optional(payload.get("session_id")),
                    _clean_optional(payload.get("run_id")),
                    _clean_optional(payload.get("trace_id")),
                    _clean_optional(payload.get("page_key")),
                    _clean_optional(payload.get("route")),
                    event_type[:120],
                    _clean_optional(payload.get("target_type")),
                    _clean_optional(payload.get("target_id")),
                    _clean_optional(payload.get("target_label")),
                    _clean_optional(payload.get("target_testid")),
                    _dumps(safe_payload),
                    str(payload.get("source") or "desktop").strip()[:80] or "desktop",
                    ts,
                ),
            )
            event_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()
        return {
            "id": event_id,
            "user_id": _clean_optional(payload.get("user_id")),
            "session_id": _clean_optional(payload.get("session_id")),
            "run_id": _clean_optional(payload.get("run_id")),
            "trace_id": _clean_optional(payload.get("trace_id")),
            "page_key": _clean_optional(payload.get("page_key")),
            "route": _clean_optional(payload.get("route")),
            "event_type": event_type[:120],
            "target_type": _clean_optional(payload.get("target_type")),
            "target_id": _clean_optional(payload.get("target_id")),
            "target_label": _clean_optional(payload.get("target_label")),
            "target_testid": _clean_optional(payload.get("target_testid")),
            "payload": safe_payload,
            "source": str(payload.get("source") or "desktop").strip()[:80] or "desktop",
            "created_at": ts,
        }

    def record_activity_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.record_activity_event(dict(event or {})) for event in list(events or [])[:200]]

    def list_activity_events(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        page_key: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": run_id,
            "page_key": page_key,
        }.items():
            if value:
                clauses.append(f"{column} = ?")
                values.append(str(value).strip())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM user_activity_events
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [self._activity_event_row(row) for row in rows]

    def start_tool_invocation(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        invocation_id: str | None = None,
        capability: str | None = None,
        category: str | None = None,
        side_effect: Any = None,
        approval_id: str | None = None,
        action_intent_id: str | None = None,
        source_chain: list[str] | None = None,
    ) -> dict[str, Any]:
        cleaned_tool = str(tool_name or "").strip()
        if not cleaned_tool:
            raise ValueError("tool_name is required")
        iid = str(invocation_id or f"tool_{uuid4().hex}").strip()
        ts = now_iso()
        side_effect_text = _side_effect_text(side_effect)
        source_chain_value = [str(item) for item in list(source_chain or []) if str(item).strip()]
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tool_invocations
                    (invocation_id, user_id, session_id, run_id, trace_id, tool_name,
                     capability, category, side_effect, status, input_summary_json,
                     output_summary_json, error_code, error_summary, duration_ms,
                     approval_id, action_intent_id, source_chain_json, secrets_redacted,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    iid,
                    _clean_optional(user_id),
                    _clean_optional(session_id),
                    _clean_optional(run_id),
                    _clean_optional(trace_id),
                    cleaned_tool,
                    _clean_optional(capability),
                    _clean_optional(category),
                    side_effect_text,
                    "running",
                    _dumps(sanitize_for_audit(arguments or {})),
                    _dumps({}),
                    None,
                    None,
                    None,
                    _clean_optional(approval_id),
                    _clean_optional(action_intent_id),
                    _dumps(source_chain_value),
                    1,
                    ts,
                    ts,
                ),
            )
            conn.commit()
        return self.get_tool_invocation(iid) or {"invocation_id": iid, "tool_name": cleaned_tool, "status": "running"}

    def finish_tool_invocation(
        self,
        invocation_id: str,
        *,
        status: str,
        result: Any = None,
        error_code: str | None = None,
        error_summary: str | None = None,
        duration_ms: int | None = None,
        approval_id: str | None = None,
        action_intent_id: str | None = None,
    ) -> dict[str, Any] | None:
        iid = str(invocation_id or "").strip()
        if not iid:
            return None
        normalized_status = str(status or "completed").strip().lower()
        if normalized_status not in {"queued", "running", "succeeded", "failed", "denied", "cancelled", "blocked"}:
            normalized_status = "succeeded" if normalized_status in {"success", "completed"} else "failed"
        existing = self.get_tool_invocation(iid)
        if existing is None:
            return None
        resolved_approval_id = _clean_optional(approval_id) or existing.get("approval_id")
        resolved_intent_id = _clean_optional(action_intent_id) or existing.get("action_intent_id")
        output_summary = sanitize_for_audit(result if result is not None else {})
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE tool_invocations
                SET status = ?,
                    output_summary_json = ?,
                    error_code = ?,
                    error_summary = ?,
                    duration_ms = ?,
                    approval_id = ?,
                    action_intent_id = ?,
                    updated_at = ?
                WHERE invocation_id = ?
                """,
                (
                    normalized_status,
                    _dumps(output_summary),
                    _clean_optional(error_code),
                    _bounded_text(error_summary, limit=1000) if error_summary else None,
                    duration_ms,
                    resolved_approval_id,
                    resolved_intent_id,
                    now_iso(),
                    iid,
                ),
            )
            conn.commit()
        return self.get_tool_invocation(iid)

    def get_tool_invocation(self, invocation_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM tool_invocations WHERE invocation_id = ?",
                (str(invocation_id or "").strip(),),
            ).fetchone()
        return self._tool_invocation_row(row)

    def list_tool_invocations(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": run_id,
            "tool_name": tool_name,
        }.items():
            if value:
                clauses.append(f"{column} = ?")
                values.append(str(value).strip())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM tool_invocations
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._tool_invocation_row(row)) is not None]

    def upsert_broker_profile(
        self,
        *,
        user_id: str,
        provider: str,
        display_name: str | None = None,
        account_ref_hash: str | None = None,
        market: str | None = None,
        read_only_enabled: bool = True,
        consent_status: str = "granted",
        consent_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        uid = str(user_id or "local").strip() or "local"
        broker = str(provider or "").strip().lower()
        if not broker:
            raise ValueError("provider is required")
        ts = now_iso()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT broker_profile_id, metadata_json, created_at FROM broker_profiles WHERE user_id = ? AND provider = ? ORDER BY updated_at DESC LIMIT 1",
                (uid, broker),
            ).fetchone()
            profile_id = row["broker_profile_id"] if row else f"broker_profile_{uuid4().hex}"
            existing_metadata = _loads(row["metadata_json"], {}) if row else {}
            merged_metadata = {**dict(existing_metadata or {}), **dict(metadata or {})}
            conn.execute(
                """
                INSERT OR REPLACE INTO broker_profiles
                    (broker_profile_id, user_id, provider, display_name, account_ref_hash,
                     market, read_only_enabled, write_enabled, consent_status, consent_version,
                     status, error_code, metadata_json, last_sync_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    uid,
                    broker,
                    _clean_optional(display_name),
                    _clean_optional(account_ref_hash),
                    _clean_optional(market),
                    1 if read_only_enabled else 0,
                    str(consent_status or "unknown").strip() or "unknown",
                    _clean_optional(consent_version),
                    "configured" if read_only_enabled else "disabled",
                    None,
                    _dumps(sanitize_for_audit(merged_metadata)),
                    None,
                    row["created_at"] if row else ts,
                    ts,
                ),
            )
            conn.commit()
        return self.get_broker_profile(profile_id) or {"broker_profile_id": profile_id, "user_id": uid, "provider": broker}

    def mark_broker_profile_synced(
        self,
        *,
        broker_profile_id: str,
        status: str = "ready",
        error_code: str | None = None,
    ) -> dict[str, Any]:
        profile_id = str(broker_profile_id or "").strip()
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                "UPDATE broker_profiles SET status = ?, error_code = ?, last_sync_at = ?, updated_at = ? WHERE broker_profile_id = ?",
                (str(status or "ready"), _clean_optional(error_code), ts, ts, profile_id),
            )
            conn.commit()
        return self.get_broker_profile(profile_id) or {"broker_profile_id": profile_id, "status": status}

    def get_broker_profile(self, broker_profile_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM broker_profiles WHERE broker_profile_id = ?", (str(broker_profile_id or "").strip(),)).fetchone()
        return self._broker_profile_row(row)

    def list_broker_profiles(
        self,
        *,
        user_id: str | None = None,
        provider: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            values.append(str(user_id).strip())
        if provider:
            clauses.append("provider = ?")
            values.append(str(provider).strip().lower())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(f"SELECT * FROM broker_profiles {where} ORDER BY updated_at DESC LIMIT ?", tuple(values)).fetchall()
        return [item for row in rows if (item := self._broker_profile_row(row)) is not None]

    def record_broker_account_snapshot(
        self,
        *,
        broker_profile_id: str,
        user_id: str,
        provider: str,
        account: dict[str, Any],
        source_tool: str | None = None,
        source_run_id: str | None = None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        snapshot_id = f"broker_account_{uuid4().hex}"
        ts = now_iso()
        observed = str(observed_at or ts)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO broker_account_snapshots
                    (snapshot_id, broker_profile_id, user_id, provider, account_ref_hash,
                     currency, total_asset, cash_available, market_value, frozen_cash,
                     buying_power, source_tool, source_run_id, observed_at, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    broker_profile_id,
                    user_id,
                    provider,
                    _clean_optional(account.get("account_ref_hash")),
                    _clean_optional(account.get("currency")),
                    _float_or_none(account.get("total_asset")),
                    _float_or_none(account.get("cash_available")),
                    _float_or_none(account.get("market_value")),
                    _float_or_none(account.get("frozen_cash")),
                    _float_or_none(account.get("buying_power")),
                    _clean_optional(source_tool),
                    _clean_optional(source_run_id),
                    observed,
                    _dumps(sanitize_for_audit(account)),
                    ts,
                ),
            )
            conn.commit()
        return self.list_broker_account_snapshots(broker_profile_id=broker_profile_id, limit=1)[0]

    def record_broker_position_snapshots(
        self,
        *,
        broker_profile_id: str,
        user_id: str,
        provider: str,
        positions: list[dict[str, Any]],
        observed_at: str | None = None,
    ) -> list[dict[str, Any]]:
        ts = now_iso()
        observed = str(observed_at or ts)
        rows: list[tuple[Any, ...]] = []
        for item in list(positions or [])[:1000]:
            rows.append(
                (
                    f"broker_position_{uuid4().hex}",
                    broker_profile_id,
                    user_id,
                    provider,
                    _clean_optional(item.get("symbol")),
                    _clean_optional(item.get("exchange")),
                    _clean_optional(item.get("name")),
                    _float_or_none(item.get("quantity")),
                    _float_or_none(item.get("available_quantity")),
                    _float_or_none(item.get("cost_basis")),
                    _float_or_none(item.get("last_price")),
                    _float_or_none(item.get("market_value")),
                    _float_or_none(item.get("unrealized_pnl")),
                    _float_or_none(item.get("unrealized_pnl_pct")),
                    observed,
                    _dumps(sanitize_for_audit(item)),
                    ts,
                )
            )
        with self._connection() as conn:
            conn.executemany(
                """
                INSERT INTO broker_position_snapshots
                    (snapshot_id, broker_profile_id, user_id, provider, symbol, exchange,
                     name, quantity, available_quantity, cost_basis, last_price, market_value,
                     unrealized_pnl, unrealized_pnl_pct, observed_at, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        return self.list_broker_position_snapshots(broker_profile_id=broker_profile_id, limit=len(rows) or 1)

    def record_broker_order_snapshots(
        self,
        *,
        broker_profile_id: str,
        user_id: str,
        provider: str,
        orders: list[dict[str, Any]],
        observed_at: str | None = None,
    ) -> list[dict[str, Any]]:
        ts = now_iso()
        observed = str(observed_at or ts)
        rows: list[tuple[Any, ...]] = []
        for item in list(orders or [])[:1000]:
            rows.append(
                (
                    f"broker_order_{uuid4().hex}",
                    broker_profile_id,
                    user_id,
                    provider,
                    _clean_optional(item.get("order_ref_hash")),
                    _clean_optional(item.get("symbol")),
                    _clean_optional(item.get("side")),
                    _clean_optional(item.get("order_type")),
                    _float_or_none(item.get("price")),
                    _float_or_none(item.get("quantity")),
                    _float_or_none(item.get("filled_quantity")),
                    _clean_optional(item.get("status")),
                    _clean_optional(item.get("submitted_at")),
                    _clean_optional(item.get("updated_at")),
                    observed,
                    _dumps(sanitize_for_audit(item)),
                    ts,
                )
            )
        with self._connection() as conn:
            conn.executemany(
                """
                INSERT INTO broker_order_snapshots
                    (snapshot_id, broker_profile_id, user_id, provider, order_ref_hash,
                     symbol, side, order_type, price, quantity, filled_quantity, status,
                     submitted_at, updated_at, observed_at, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        return self.list_broker_order_snapshots(broker_profile_id=broker_profile_id, limit=len(rows) or 1)

    def record_broker_deal_snapshots(
        self,
        *,
        broker_profile_id: str,
        user_id: str,
        provider: str,
        deals: list[dict[str, Any]],
        observed_at: str | None = None,
    ) -> list[dict[str, Any]]:
        ts = now_iso()
        observed = str(observed_at or ts)
        rows: list[tuple[Any, ...]] = []
        for item in list(deals or [])[:1000]:
            rows.append(
                (
                    f"broker_deal_{uuid4().hex}",
                    broker_profile_id,
                    user_id,
                    provider,
                    _clean_optional(item.get("deal_ref_hash")),
                    _clean_optional(item.get("order_ref_hash")),
                    _clean_optional(item.get("symbol")),
                    _clean_optional(item.get("side")),
                    _float_or_none(item.get("price")),
                    _float_or_none(item.get("quantity")),
                    _float_or_none(item.get("amount")),
                    _float_or_none(item.get("fee")),
                    _clean_optional(item.get("occurred_at")),
                    observed,
                    _dumps(sanitize_for_audit(item)),
                    ts,
                )
            )
        with self._connection() as conn:
            conn.executemany(
                """
                INSERT INTO broker_deal_snapshots
                    (snapshot_id, broker_profile_id, user_id, provider, deal_ref_hash,
                     order_ref_hash, symbol, side, price, quantity, amount, fee,
                     occurred_at, observed_at, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
        return self.list_broker_deal_snapshots(broker_profile_id=broker_profile_id, limit=len(rows) or 1)

    def record_broker_behavior_analytics(
        self,
        *,
        broker_profile_id: str | None,
        user_id: str,
        provider: str,
        period_start: str | None = None,
        period_end: str | None = None,
        metrics: dict[str, Any] | None = None,
        signals: dict[str, Any] | None = None,
        risk_flags: list[dict[str, Any]] | None = None,
        source_snapshot_ids: dict[str, Any] | None = None,
        model_version: str = "deterministic-p0",
    ) -> dict[str, Any]:
        analytics_id = f"broker_analytics_{uuid4().hex}"
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO broker_behavior_analytics
                    (analytics_id, broker_profile_id, user_id, provider, period_start,
                     period_end, metrics_json, signals_json, risk_flags_json,
                     source_snapshot_ids_json, model_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analytics_id,
                    _clean_optional(broker_profile_id),
                    str(user_id or "local").strip() or "local",
                    str(provider or "unknown").strip().lower() or "unknown",
                    _clean_optional(period_start),
                    _clean_optional(period_end),
                    _dumps(sanitize_for_audit(metrics or {})),
                    _dumps(sanitize_for_audit(signals or {})),
                    _dumps(sanitize_for_audit(risk_flags or [])),
                    _dumps(sanitize_for_audit(source_snapshot_ids or {})),
                    str(model_version or "deterministic-p0"),
                    ts,
                ),
            )
            conn.commit()
        return self.latest_broker_analytics(user_id=user_id, provider=provider) or {"analytics_id": analytics_id}

    def list_broker_account_snapshots(self, **filters: Any) -> list[dict[str, Any]]:
        return self._list_broker_rows("broker_account_snapshots", self._broker_account_row, **filters)

    def list_broker_position_snapshots(self, **filters: Any) -> list[dict[str, Any]]:
        return self._list_broker_rows("broker_position_snapshots", self._broker_position_row, **filters)

    def list_broker_order_snapshots(self, **filters: Any) -> list[dict[str, Any]]:
        return self._list_broker_rows("broker_order_snapshots", self._broker_order_row, **filters)

    def list_broker_deal_snapshots(self, **filters: Any) -> list[dict[str, Any]]:
        return self._list_broker_rows("broker_deal_snapshots", self._broker_deal_row, **filters)

    def latest_broker_analytics(
        self,
        *,
        user_id: str | None = None,
        provider: str | None = None,
        broker_profile_id: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.list_broker_analytics(user_id=user_id, provider=provider, broker_profile_id=broker_profile_id, limit=1)
        return rows[0] if rows else None

    def list_broker_analytics(
        self,
        *,
        user_id: str | None = None,
        provider: str | None = None,
        broker_profile_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clauses, values = self._broker_filter_clauses(user_id=user_id, provider=provider, broker_profile_id=broker_profile_id)
        values.append(max(1, min(int(limit or 20), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(f"SELECT * FROM broker_behavior_analytics {where} ORDER BY created_at DESC LIMIT ?", tuple(values)).fetchall()
        return [item for row in rows if (item := self._broker_analytics_row(row)) is not None]

    def _list_broker_rows(
        self,
        table: str,
        row_mapper: Any,
        *,
        user_id: str | None = None,
        provider: str | None = None,
        broker_profile_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses, values = self._broker_filter_clauses(user_id=user_id, provider=provider, broker_profile_id=broker_profile_id)
        values.append(max(1, min(int(limit or 100), 5000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(f"SELECT * FROM {table} {where} ORDER BY observed_at DESC, created_at DESC LIMIT ?", tuple(values)).fetchall()
        return [item for row in rows if (item := row_mapper(row)) is not None]

    @staticmethod
    def _broker_filter_clauses(
        *,
        user_id: str | None = None,
        provider: str | None = None,
        broker_profile_id: str | None = None,
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            values.append(str(user_id).strip())
        if provider:
            clauses.append("provider = ?")
            values.append(str(provider).strip().lower())
        if broker_profile_id:
            clauses.append("broker_profile_id = ?")
            values.append(str(broker_profile_id).strip())
        return clauses, values

    def record_source(self, source: dict[str, Any]) -> dict[str, Any]:
        payload = dict(source or {})
        source_id = str(payload.get("source_id") or f"src_{uuid4().hex}").strip()
        source_type = str(payload.get("source_type") or "data_provider").strip()[:80] or "data_provider"
        fetched_at = str(payload.get("fetched_at") or now_iso())
        created_at = str(payload.get("created_at") or fetched_at)
        metadata = sanitize_for_audit(payload.get("metadata") if "metadata" in payload else {})
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_sources
                    (source_id, user_id, session_id, run_id, trace_id, tool_call_id,
                     tool_name, provider, source_type, title, url, published_at,
                     fetched_at, data_timestamp, excerpt, source_tier,
                     credibility_score, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    _clean_optional(payload.get("user_id")),
                    _clean_optional(payload.get("session_id")),
                    _clean_optional(payload.get("run_id")),
                    _clean_optional(payload.get("trace_id")),
                    _clean_optional(payload.get("tool_call_id")),
                    _clean_optional(payload.get("tool_name")),
                    _clean_optional(payload.get("provider")),
                    source_type,
                    _bounded_text(payload.get("title"), limit=500) if payload.get("title") is not None else None,
                    _clean_optional(payload.get("url"), limit=2000),
                    _clean_optional(payload.get("published_at"), limit=200),
                    fetched_at,
                    _clean_optional(payload.get("data_timestamp"), limit=200),
                    _bounded_text(payload.get("excerpt"), limit=2000) if payload.get("excerpt") is not None else None,
                    _clean_optional(payload.get("source_tier"), limit=80),
                    _float_or_none(payload.get("credibility_score")),
                    _dumps(metadata),
                    created_at,
                ),
            )
            self._index_search_row(
                conn,
                kind="source",
                object_id=source_id,
                session_id=str(payload.get("session_id") or ""),
                user_id=_clean_optional(payload.get("user_id")),
                content=" ".join(
                    str(item or "")
                    for item in (
                        payload.get("title"),
                        payload.get("url"),
                        payload.get("provider"),
                        payload.get("excerpt"),
                        source_type,
                    )
                ).strip(),
                payload={**payload, "metadata": metadata, "source_id": source_id, "source_type": source_type},
            )
            conn.commit()
        item = self.get_source(source_id)
        assert item is not None
        return item

    def record_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        payload = dict(artifact or {})
        artifact_id = str(payload.get("artifact_id") or f"art_{uuid4().hex}").strip()
        kind = str(payload.get("kind") or "file").strip()[:80] or "file"
        title = str(payload.get("title") or payload.get("path") or artifact_id).strip()[:500] or artifact_id
        status = str(payload.get("status") or "ready").strip()[:80] or "ready"
        created_at = str(payload.get("created_at") or now_iso())
        updated_at = str(payload.get("updated_at") or created_at)
        metadata = sanitize_for_audit(payload.get("metadata") if "metadata" in payload else {})
        preview_json = sanitize_for_audit(payload.get("preview_json") if "preview_json" in payload else {})
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_artifacts
                    (artifact_id, user_id, session_id, run_id, trace_id, tool_call_id,
                     tool_name, kind, title, path, uri, mime_type, size_bytes,
                     sha256, preview_text, preview_json, source_id, status,
                     metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    _clean_optional(payload.get("user_id")),
                    _clean_optional(payload.get("session_id")),
                    _clean_optional(payload.get("run_id")),
                    _clean_optional(payload.get("trace_id")),
                    _clean_optional(payload.get("tool_call_id")),
                    _clean_optional(payload.get("tool_name")),
                    kind,
                    title,
                    _clean_optional(payload.get("path"), limit=2000),
                    _clean_optional(payload.get("uri"), limit=2000),
                    _clean_optional(payload.get("mime_type"), limit=200),
                    _int_or_none(payload.get("size_bytes")),
                    _clean_optional(payload.get("sha256"), limit=128),
                    _bounded_text(payload.get("preview_text"), limit=4000) if payload.get("preview_text") is not None else None,
                    _dumps(preview_json),
                    _clean_optional(payload.get("source_id")),
                    status,
                    _dumps(metadata),
                    created_at,
                    updated_at,
                ),
            )
            self._index_search_row(
                conn,
                kind="artifact",
                object_id=artifact_id,
                session_id=str(payload.get("session_id") or ""),
                user_id=_clean_optional(payload.get("user_id")),
                content=" ".join(
                    str(item or "")
                    for item in (
                        title,
                        payload.get("path"),
                        payload.get("uri"),
                        payload.get("preview_text"),
                        kind,
                    )
                ).strip(),
                payload={
                    **payload,
                    "artifact_id": artifact_id,
                    "kind": kind,
                    "title": title,
                    "status": status,
                    "metadata": metadata,
                    "preview_json": preview_json,
                },
            )
            conn.commit()
        item = self.get_artifact(artifact_id)
        assert item is not None
        return item

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_sources WHERE source_id = ?",
                (str(source_id or "").strip(),),
            ).fetchone()
        return self._source_row(row)

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_artifacts WHERE artifact_id = ?",
                (str(artifact_id or "").strip(),),
            ).fetchone()
        return self._artifact_row(row)

    def list_sources(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": run_id,
            "tool_call_id": tool_call_id,
            "source_type": source_type,
        }.items():
            if value:
                clauses.append(f"{column} = ?")
                values.append(str(value).strip())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM agent_sources
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._source_row(row)) is not None]

    def list_artifacts(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": run_id,
            "tool_call_id": tool_call_id,
            "kind": kind,
        }.items():
            if value:
                clauses.append(f"{column} = ?")
                values.append(str(value).strip())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM agent_artifacts
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._artifact_row(row)) is not None]

    def record_context_snapshot(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        context_summary_id: str | None = None,
        policy: str = "runtime_prepare",
        compacted: bool = False,
        message_count: int = 0,
        source_message_ids: list[Any] | None = None,
        source_ids: list[Any] | None = None,
        artifact_ids: list[Any] | None = None,
        token_estimate_before: int | None = None,
        token_estimate_after: int | None = None,
        summary: str | None = None,
        summary_model: str | None = None,
        risk_flags: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        snap_id = str(snapshot_id or f"ctxsnap_{uuid4().hex}").strip()
        ts = now_iso()
        cleaned_source_message_ids = [str(item) for item in list(source_message_ids or []) if str(item).strip()]
        cleaned_source_ids = [str(item) for item in list(source_ids or []) if str(item).strip()]
        cleaned_artifact_ids = [str(item) for item in list(artifact_ids or []) if str(item).strip()]
        cleaned_risk_flags = [str(item)[:120] for item in list(risk_flags or []) if str(item).strip()]
        safe_metadata = sanitize_for_audit(dict(metadata or {}), max_depth=4, max_items=80, max_text=2000)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO context_snapshots
                    (snapshot_id, user_id, session_id, run_id, trace_id, context_summary_id,
                     policy, compacted, message_count, source_message_ids_json,
                     source_ids_json, artifact_ids_json, token_estimate_before,
                     token_estimate_after, summary, summary_model, risk_flags_json,
                     metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap_id,
                    _clean_optional(user_id),
                    sid,
                    _clean_optional(run_id),
                    _clean_optional(trace_id),
                    _clean_optional(context_summary_id),
                    str(policy or "runtime_prepare").strip()[:120] or "runtime_prepare",
                    1 if compacted else 0,
                    max(0, int(message_count or 0)),
                    _dumps(cleaned_source_message_ids),
                    _dumps(cleaned_source_ids),
                    _dumps(cleaned_artifact_ids),
                    _int_or_none(token_estimate_before),
                    _int_or_none(token_estimate_after),
                    _bounded_text(summary, limit=12000) if summary else None,
                    _clean_optional(summary_model),
                    _dumps(cleaned_risk_flags),
                    _dumps(safe_metadata),
                    ts,
                ),
            )
            conn.commit()
        item = self.get_context_snapshot(snap_id)
        assert item is not None
        return item

    def get_context_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM context_snapshots WHERE snapshot_id = ?",
                (str(snapshot_id or "").strip(),),
            ).fetchone()
        return self._context_snapshot_row(row)

    def list_context_snapshots(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": run_id,
        }.items():
            if value:
                clauses.append(f"{column} = ?")
                values.append(str(value).strip())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM context_snapshots
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._context_snapshot_row(row)) is not None]

    def record_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        payload = dict(feedback or {})
        target_type = str(payload.get("target_type") or "").strip()
        feedback_type = str(payload.get("feedback_type") or payload.get("type") or "").strip()
        if not target_type:
            raise ValueError("target_type is required")
        if not feedback_type:
            raise ValueError("feedback_type is required")
        feedback_id = str(payload.get("feedback_id") or f"feedback_{uuid4().hex}").strip()
        rating = payload.get("rating")
        try:
            rating_value = int(rating) if rating is not None and str(rating).strip() != "" else None
        except (TypeError, ValueError):
            rating_value = None
        ts = str(payload.get("created_at") or now_iso())
        safe_payload = sanitize_for_audit(payload.get("payload") if "payload" in payload else {})
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO feedback_events
                    (feedback_id, user_id, session_id, run_id, target_type, target_id,
                     feedback_type, rating, comment, allow_learning, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    _clean_optional(payload.get("user_id")),
                    _clean_optional(payload.get("session_id")),
                    _clean_optional(payload.get("run_id")),
                    target_type[:80],
                    _clean_optional(payload.get("target_id")),
                    feedback_type[:80],
                    rating_value,
                    _bounded_text(payload.get("comment"), limit=2000) if payload.get("comment") is not None else None,
                    1 if _truthy(payload.get("allow_learning")) else 0,
                    _dumps(safe_payload),
                    ts,
                ),
            )
            conn.commit()
        return self.get_feedback(feedback_id) or {"feedback_id": feedback_id}

    def get_feedback(self, feedback_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM feedback_events WHERE feedback_id = ?",
                (str(feedback_id or "").strip(),),
            ).fetchone()
        return self._feedback_row(row)

    def list_feedback(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in {
            "user_id": user_id,
            "session_id": session_id,
            "run_id": run_id,
            "target_type": target_type,
            "target_id": target_id,
        }.items():
            if value:
                clauses.append(f"{column} = ?")
                values.append(str(value).strip())
        values.append(max(1, min(int(limit or 100), 1000)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM feedback_events
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._feedback_row(row)) is not None]

    def get_user_data_policy(self, user_id: str) -> dict[str, Any]:
        uid = str(user_id or "local").strip() or "local"
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_data_policies
                    (user_id, event_ttl_days, audit_ttl_days, run_event_ttl_days,
                     tool_payload_ttl_days, conversation_retention,
                     allow_product_analytics, allow_learning, updated_at)
                VALUES (?, 90, 180, 180, 90, 'keep_until_user_deletes', 1, 0, ?)
                """,
                (uid, ts),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM user_data_policies WHERE user_id = ?", (uid,)).fetchone()
        item = self._policy_row(row)
        assert item is not None
        return item

    def update_user_data_policy(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        current = self.get_user_data_policy(user_id)
        updates = dict(patch or {})
        allowed_ints = {
            "event_ttl_days": (1, 3650),
            "audit_ttl_days": (1, 3650),
            "run_event_ttl_days": (1, 3650),
            "tool_payload_ttl_days": (1, 3650),
        }
        next_policy = dict(current)
        for key, (minimum, maximum) in allowed_ints.items():
            if key in updates:
                try:
                    next_policy[key] = max(minimum, min(int(updates[key]), maximum))
                except (TypeError, ValueError):
                    pass
        if updates.get("conversation_retention"):
            value = str(updates.get("conversation_retention") or "").strip()
            if value in {"keep_until_user_deletes", "delete_after_ttl", "archive_after_ttl"}:
                next_policy["conversation_retention"] = value
        for key in ("allow_product_analytics", "allow_learning"):
            if key in updates:
                next_policy[key] = _truthy(updates[key])
        ts = now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE user_data_policies
                SET event_ttl_days = ?,
                    audit_ttl_days = ?,
                    run_event_ttl_days = ?,
                    tool_payload_ttl_days = ?,
                    conversation_retention = ?,
                    allow_product_analytics = ?,
                    allow_learning = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    next_policy["event_ttl_days"],
                    next_policy["audit_ttl_days"],
                    next_policy["run_event_ttl_days"],
                    next_policy["tool_payload_ttl_days"],
                    next_policy["conversation_retention"],
                    1 if next_policy["allow_product_analytics"] else 0,
                    1 if next_policy["allow_learning"] else 0,
                    ts,
                    str(user_id or "local").strip() or "local",
                ),
            )
            conn.commit()
        return self.get_user_data_policy(str(user_id or "local").strip() or "local")

    def user_activity_summary(self, *, user_id: str, limit: int = 20) -> dict[str, Any]:
        uid = str(user_id or "local").strip() or "local"
        return {
            "object": "aiask.user_activity",
            "user_id": uid,
            "sessions": self.list_sessions(user_id=uid, limit=limit),
            "runs": [
                item
                for item in self.list_runs(limit=limit * 5)
                if str((item.get("payload") or {}).get("user_id") or "") == uid
            ][:limit],
            "events": self.list_activity_events(user_id=uid, limit=limit),
            "tool_invocations": self.list_tool_invocations(user_id=uid, limit=limit),
            "context_snapshots": self.list_context_snapshots(user_id=uid, limit=limit),
            "feedback": self.list_feedback(user_id=uid, limit=limit),
            "policy": self.get_user_data_policy(uid),
            "secrets_redacted": True,
        }

    def analytics_summary(self, *, user_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        uid = str(user_id or "").strip()
        clauses: list[str] = []
        values: list[Any] = []
        if uid:
            clauses.append("user_id = ?")
            values.append(uid)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        max_rows = max(1, min(int(limit or 20), 100))
        with self._connection() as conn:
            event_total = int(conn.execute(f"SELECT COUNT(*) FROM user_activity_events {where}", tuple(values)).fetchone()[0])
            feedback_total = int(conn.execute(f"SELECT COUNT(*) FROM feedback_events {where}", tuple(values)).fetchone()[0])
            tool_total = int(conn.execute(f"SELECT COUNT(*) FROM tool_invocations {where}", tuple(values)).fetchone()[0])
            event_rows = conn.execute(
                f"""
                SELECT event_type, COUNT(*) AS count
                FROM user_activity_events
                {where}
                GROUP BY event_type
                ORDER BY count DESC, event_type ASC
                LIMIT ?
                """,
                tuple(values + [max_rows]),
            ).fetchall()
            page_rows = conn.execute(
                f"""
                SELECT COALESCE(page_key, route, 'unknown') AS page_key, COUNT(*) AS count
                FROM user_activity_events
                {where}
                GROUP BY COALESCE(page_key, route, 'unknown')
                ORDER BY count DESC, page_key ASC
                LIMIT ?
                """,
                tuple(values + [max_rows]),
            ).fetchall()
            tool_rows = conn.execute(
                f"""
                SELECT tool_name,
                       COUNT(*) AS count,
                       SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded,
                       SUM(CASE WHEN status IN ('failed', 'denied', 'blocked', 'cancelled') THEN 1 ELSE 0 END) AS failed,
                       AVG(duration_ms) AS avg_duration_ms
                FROM tool_invocations
                {where}
                GROUP BY tool_name
                ORDER BY count DESC, tool_name ASC
                LIMIT ?
                """,
                tuple(values + [max_rows]),
            ).fetchall()
            feedback_rows = conn.execute(
                f"""
                SELECT target_type, feedback_type, COUNT(*) AS count, AVG(rating) AS avg_rating
                FROM feedback_events
                {where}
                GROUP BY target_type, feedback_type
                ORDER BY count DESC, target_type ASC, feedback_type ASC
                LIMIT ?
                """,
                tuple(values + [max_rows]),
            ).fetchall()
        return {
            "object": "aiask.analytics_summary",
            "scope": "user" if uid else "aggregate",
            "user_id": uid or None,
            "totals": {
                "events": event_total,
                "tool_invocations": tool_total,
                "feedback": feedback_total,
            },
            "events_by_type": [dict(row) for row in event_rows],
            "pages": [dict(row) for row in page_rows],
            "tools": [
                {
                    **dict(row),
                    "failed": int(row["failed"] or 0),
                    "succeeded": int(row["succeeded"] or 0),
                    "failure_rate": (float(row["failed"] or 0) / float(row["count"] or 1)) if row["count"] else 0.0,
                    "avg_duration_ms": float(row["avg_duration_ms"] or 0.0),
                }
                for row in tool_rows
            ],
            "feedback": [
                {
                    **dict(row),
                    "avg_rating": float(row["avg_rating"]) if row["avg_rating"] is not None else None,
                }
                for row in feedback_rows
            ],
            "secrets_redacted": True,
        }

    def export_user_data(self, *, user_id: str, limit: int = 500) -> dict[str, Any]:
        uid = str(user_id or "local").strip() or "local"
        max_rows = max(1, min(int(limit or 500), 5000))
        session_ids = [str(item.get("session_id")) for item in self.list_sessions(user_id=uid, limit=max_rows, include_archived=True)]
        runs = [
            item
            for item in self.list_runs(limit=max_rows * 5)
            if str((item.get("payload") or {}).get("user_id") or "") == uid or str(item.get("session_id") or "") in session_ids
        ][:max_rows]
        run_ids = [str(item.get("run_id")) for item in runs if item.get("run_id")]
        messages: list[dict[str, Any]] = []
        for session_id in session_ids[:max_rows]:
            messages.extend(self.list_session_messages(session_id, limit=max_rows, include_deleted=True))
            if len(messages) >= max_rows:
                messages = messages[:max_rows]
                break
        run_events: list[dict[str, Any]] = []
        for run_id in run_ids[:max_rows]:
            run_events.extend(self.list_run_events(run_id, limit=max_rows))
            if len(run_events) >= max_rows:
                run_events = run_events[:max_rows]
                break
        return {
            "object": "aiask.user_data_export",
            "user_id": uid,
            "exported_at": now_iso(),
            "profile_policy": self.get_user_data_policy(uid),
            "sessions": self.list_sessions(user_id=uid, limit=max_rows, include_archived=True),
            "messages": messages,
            "runs": runs,
            "run_events": run_events,
            "activity_events": self.list_activity_events(user_id=uid, limit=max_rows),
            "tool_invocations": self.list_tool_invocations(user_id=uid, limit=max_rows),
            "context_snapshots": self.list_context_snapshots(user_id=uid, limit=max_rows),
            "feedback": self.list_feedback(user_id=uid, limit=max_rows),
            "sources": self.list_sources(user_id=uid, limit=max_rows),
            "artifacts": self.list_artifacts(user_id=uid, limit=max_rows),
            "analytics": self.analytics_summary(user_id=uid),
            "secrets_redacted": True,
        }

    def delete_user_data(
        self,
        *,
        user_id: str,
        include_conversations: bool = True,
        include_audit: bool = True,
        hard_delete: bool = False,
        reason: str = "user_data_delete",
        actor: str = "user",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        uid = str(user_id or "local").strip() or "local"
        ts = now_iso()
        anonymous_user = f"deleted:{uid}"
        counts = {
            "sessions": 0,
            "messages": 0,
            "responses": 0,
            "runs": 0,
            "run_events": 0,
            "activity_events": 0,
            "tool_invocations": 0,
            "context_snapshots": 0,
            "feedback": 0,
            "sources": 0,
            "artifacts": 0,
            "search_rows": 0,
        }
        with self._connection() as conn:
            session_rows = conn.execute("SELECT session_id FROM sessions WHERE user_id = ?", (uid,)).fetchall()
            session_ids = [str(row["session_id"]) for row in session_rows]
            run_rows = conn.execute("SELECT run_id, session_id, payload_json FROM runs").fetchall()
            session_id_set = set(session_ids)
            run_ids = [
                str(row["run_id"])
                for row in run_rows
                if str(row["session_id"] or "") in session_id_set or str((_loads(row["payload_json"], {}) or {}).get("user_id") or "") == uid
            ]

            def count_where(table: str, clause: str, params: tuple[Any, ...]) -> int:
                return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {clause}", params).fetchone()[0])

            if include_conversations:
                counts["sessions"] = count_where("sessions", "user_id = ?", (uid,))
                counts["messages"] = count_where("messages", f"session_id IN ({','.join('?' for _ in session_ids)})", tuple(session_ids)) if session_ids else 0
                counts["responses"] = count_where("responses", f"session_id IN ({','.join('?' for _ in session_ids)})", tuple(session_ids)) if session_ids else 0
                counts["runs"] = len(run_ids)
                counts["run_events"] = count_where("run_events", f"run_id IN ({','.join('?' for _ in run_ids)})", tuple(run_ids)) if run_ids else 0
                counts["search_rows"] = count_where("aiask_search_fts", "user_id = ?", (uid,)) if self._fts_available(conn) else 0
            if include_audit:
                counts["activity_events"] = count_where("user_activity_events", "user_id = ?", (uid,))
                counts["tool_invocations"] = count_where("tool_invocations", "user_id = ?", (uid,))
                counts["context_snapshots"] = count_where("context_snapshots", "user_id = ?", (uid,))
                counts["feedback"] = count_where("feedback_events", "user_id = ?", (uid,))
                counts["sources"] = count_where("agent_sources", "user_id = ?", (uid,))
                counts["artifacts"] = count_where("agent_artifacts", "user_id = ?", (uid,))
            if dry_run:
                return {
                    "object": "aiask.user_data_delete",
                    "user_id": uid,
                    "dry_run": True,
                    "hard_delete": bool(hard_delete),
                    "counts": counts,
                    "secrets_redacted": True,
                }
            if include_conversations and session_ids:
                if hard_delete:
                    conn.execute(f"DELETE FROM messages WHERE session_id IN ({','.join('?' for _ in session_ids)})", tuple(session_ids))
                    conn.execute(f"DELETE FROM responses WHERE session_id IN ({','.join('?' for _ in session_ids)})", tuple(session_ids))
                    if run_ids:
                        conn.execute(f"DELETE FROM run_events WHERE run_id IN ({','.join('?' for _ in run_ids)})", tuple(run_ids))
                        conn.execute(f"DELETE FROM runs WHERE run_id IN ({','.join('?' for _ in run_ids)})", tuple(run_ids))
                    conn.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
                else:
                    conn.execute(
                        f"UPDATE messages SET content = '', payload_json = '{{}}', deleted_at = ?, deleted_reason = ?, deleted_by = ? WHERE session_id IN ({','.join('?' for _ in session_ids)})",
                        tuple([ts, reason, actor] + session_ids),
                    )
                    for session_id in session_ids:
                        row = conn.execute("SELECT metadata_json FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
                        metadata = _loads(row["metadata_json"] if row else None, {})
                        metadata.update({"user_deleted": True, "deleted_at": ts, "deleted_reason": reason})
                        conn.execute(
                            "UPDATE sessions SET user_id = ?, title = ?, metadata_json = ?, updated_at = ? WHERE session_id = ?",
                            (anonymous_user, "Deleted user data", _dumps(metadata), ts, session_id),
                        )
                    run_id_set = set(run_ids)
                    for row in run_rows:
                        if str(row["run_id"]) not in run_id_set:
                            continue
                        payload = _loads(row["payload_json"], {})
                        if isinstance(payload, dict):
                            payload["user_id"] = anonymous_user
                        conn.execute(
                            "UPDATE runs SET payload_json = ?, updated_at = ? WHERE run_id = ?",
                            (_dumps(payload if isinstance(payload, dict) else {"user_id": anonymous_user}), ts, str(row["run_id"])),
                        )
                if self._fts_available(conn):
                    conn.execute("DELETE FROM aiask_search_fts WHERE user_id = ?", (uid,))
            if include_audit:
                if hard_delete:
                    for table in ("user_activity_events", "tool_invocations", "context_snapshots", "feedback_events", "agent_sources", "agent_artifacts"):
                        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
                else:
                    conn.execute("UPDATE user_activity_events SET user_id = ?, session_id = NULL, run_id = NULL, trace_id = NULL, payload_json = '{}' WHERE user_id = ?", (anonymous_user, uid))
                    conn.execute("UPDATE tool_invocations SET user_id = ?, session_id = NULL, run_id = NULL, trace_id = NULL, input_summary_json = '{}', output_summary_json = '{}' WHERE user_id = ?", (anonymous_user, uid))
                    conn.execute("UPDATE context_snapshots SET user_id = ?, session_id = '', run_id = NULL, trace_id = NULL, source_message_ids_json = '[]', source_ids_json = '[]', artifact_ids_json = '[]', summary = NULL, metadata_json = '{}' WHERE user_id = ?", (anonymous_user, uid))
                    conn.execute("UPDATE feedback_events SET user_id = ?, session_id = NULL, run_id = NULL, comment = NULL, payload_json = '{}' WHERE user_id = ?", (anonymous_user, uid))
                    conn.execute("UPDATE agent_sources SET user_id = ?, session_id = NULL, run_id = NULL, trace_id = NULL, metadata_json = '{}' WHERE user_id = ?", (anonymous_user, uid))
                    conn.execute("UPDATE agent_artifacts SET user_id = ?, session_id = NULL, run_id = NULL, trace_id = NULL, preview_text = NULL, preview_json = '{}', metadata_json = '{}' WHERE user_id = ?", (anonymous_user, uid))
            conn.commit()
        return {
            "object": "aiask.user_data_delete",
            "user_id": uid,
            "dry_run": False,
            "hard_delete": bool(hard_delete),
            "anonymized_user_id": None if hard_delete else anonymous_user,
            "counts": counts,
            "deleted_at": ts,
            "external_side_effects": "not_rolled_back",
            "secrets_redacted": True,
        }

    def apply_retention_policies(self, *, user_id: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        uid = str(user_id or "").strip()
        policies = [self.get_user_data_policy(uid)] if uid else self._list_user_data_policies()
        if not policies:
            policies = [self.get_user_data_policy("local")]
        deleted: dict[str, int] = {
            "user_activity_events": 0,
            "tool_invocations_payloads": 0,
            "context_snapshot_payloads": 0,
            "run_events": 0,
            "feedback_events": 0,
            "messages": 0,
        }
        with self._connection() as conn:
            for policy in policies:
                policy_uid = str(policy.get("user_id") or "local")
                event_cutoff = _iso_days_ago(int(policy.get("event_ttl_days") or 90))
                audit_cutoff = _iso_days_ago(int(policy.get("audit_ttl_days") or 180))
                run_cutoff = _iso_days_ago(int(policy.get("run_event_ttl_days") or 180))
                tool_payload_cutoff = _iso_days_ago(int(policy.get("tool_payload_ttl_days") or 90))

                deleted["user_activity_events"] += int(conn.execute("SELECT COUNT(*) FROM user_activity_events WHERE user_id = ? AND created_at < ?", (policy_uid, event_cutoff)).fetchone()[0])
                deleted["feedback_events"] += int(conn.execute("SELECT COUNT(*) FROM feedback_events WHERE user_id = ? AND created_at < ?", (policy_uid, audit_cutoff)).fetchone()[0])
                deleted["tool_invocations_payloads"] += int(conn.execute("SELECT COUNT(*) FROM tool_invocations WHERE user_id = ? AND created_at < ? AND (input_summary_json != '{}' OR output_summary_json != '{}')", (policy_uid, tool_payload_cutoff)).fetchone()[0])
                deleted["context_snapshot_payloads"] += int(conn.execute("SELECT COUNT(*) FROM context_snapshots WHERE user_id = ? AND created_at < ? AND (summary IS NOT NULL OR source_message_ids_json != '[]' OR source_ids_json != '[]' OR artifact_ids_json != '[]' OR metadata_json != '{}')", (policy_uid, audit_cutoff)).fetchone()[0])
                run_ids = [
                    str(row["run_id"])
                    for row in conn.execute("SELECT run_id, payload_json FROM runs").fetchall()
                    if str((_loads(row["payload_json"], {}) or {}).get("user_id") or "") == policy_uid
                ]
                if run_ids:
                    deleted["run_events"] += int(conn.execute(f"SELECT COUNT(*) FROM run_events WHERE run_id IN ({','.join('?' for _ in run_ids)}) AND created_at < ?", tuple(run_ids + [run_cutoff])).fetchone()[0])
                if policy.get("conversation_retention") == "delete_after_ttl":
                    session_ids = [
                        str(row["session_id"])
                        for row in conn.execute("SELECT session_id FROM sessions WHERE user_id = ? AND updated_at < ?", (policy_uid, audit_cutoff)).fetchall()
                    ]
                    if session_ids:
                        deleted["messages"] += int(conn.execute(f"SELECT COUNT(*) FROM messages WHERE session_id IN ({','.join('?' for _ in session_ids)}) AND deleted_at IS NULL", tuple(session_ids)).fetchone()[0])
                if dry_run:
                    continue
                conn.execute("DELETE FROM user_activity_events WHERE user_id = ? AND created_at < ?", (policy_uid, event_cutoff))
                conn.execute("DELETE FROM feedback_events WHERE user_id = ? AND created_at < ?", (policy_uid, audit_cutoff))
                conn.execute("UPDATE tool_invocations SET input_summary_json = '{}', output_summary_json = '{}' WHERE user_id = ? AND created_at < ?", (policy_uid, tool_payload_cutoff))
                conn.execute("UPDATE context_snapshots SET source_message_ids_json = '[]', source_ids_json = '[]', artifact_ids_json = '[]', summary = NULL, metadata_json = '{}' WHERE user_id = ? AND created_at < ?", (policy_uid, audit_cutoff))
                if run_ids:
                    conn.execute(f"DELETE FROM run_events WHERE run_id IN ({','.join('?' for _ in run_ids)}) AND created_at < ?", tuple(run_ids + [run_cutoff]))
                if policy.get("conversation_retention") == "delete_after_ttl":
                    session_ids = [
                        str(row["session_id"])
                        for row in conn.execute("SELECT session_id FROM sessions WHERE user_id = ? AND updated_at < ?", (policy_uid, audit_cutoff)).fetchall()
                    ]
                    if session_ids:
                        conn.execute(
                            f"UPDATE messages SET content = '', payload_json = '{{}}', deleted_at = ?, deleted_reason = ?, deleted_by = ? WHERE session_id IN ({','.join('?' for _ in session_ids)}) AND deleted_at IS NULL",
                            tuple([now_iso(), "retention_policy", "retention_sweep"] + session_ids),
                        )
            if not dry_run:
                conn.commit()
        return {
            "object": "aiask.retention_sweep",
            "dry_run": bool(dry_run),
            "user_id": uid or None,
            "counts": deleted,
            "tables": list(deleted.keys()),
            "market_data_affected": False,
            "secrets_redacted": True,
        }

    def learning_dataset(self, *, user_id: str, limit: int = 100) -> dict[str, Any]:
        uid = str(user_id or "local").strip() or "local"
        policy = self.get_user_data_policy(uid)
        if not policy.get("allow_learning"):
            return {
                "object": "aiask.learning_dataset",
                "user_id": uid,
                "allowed": False,
                "items": [],
                "reason": "learning_not_allowed",
                "secrets_redacted": True,
            }
        max_rows = max(1, min(int(limit or 100), 500))
        feedback = [item for item in self.list_feedback(user_id=uid, limit=max_rows) if item.get("allow_learning")]
        items: list[dict[str, Any]] = []
        for item in feedback:
            items.append(
                {
                    "kind": "feedback",
                    "target_type": item.get("target_type"),
                    "target_id": item.get("target_id"),
                    "feedback_type": item.get("feedback_type"),
                    "rating": item.get("rating"),
                    "comment": item.get("comment"),
                    "created_at": item.get("created_at"),
                }
            )
        return {
            "object": "aiask.learning_dataset",
            "user_id": uid,
            "allowed": True,
            "items": items[:max_rows],
            "count": min(len(items), max_rows),
            "secrets_redacted": True,
        }

    def workflow_recommendations(self, *, user_id: str, limit: int = 5) -> dict[str, Any]:
        uid = str(user_id or "local").strip() or "local"
        analytics = self.analytics_summary(user_id=uid)
        recommendations: list[dict[str, Any]] = []
        failed_tools = [tool for tool in analytics.get("tools", []) if float(tool.get("failure_rate") or 0) >= 0.25 and int(tool.get("count") or 0) >= 2]
        for tool in failed_tools[:3]:
            recommendations.append(
                {
                    "id": f"tool_reliability:{tool.get('tool_name')}",
                    "kind": "tool_reliability",
                    "priority": "high",
                    "title": f"Review failing tool {tool.get('tool_name')}",
                    "reason": f"Failure rate {float(tool.get('failure_rate') or 0):.0%} across {tool.get('count')} calls.",
                    "target": {"tool_name": tool.get("tool_name")},
                }
            )
        if not analytics.get("feedback"):
            recommendations.append(
                {
                    "id": "feedback:collect",
                    "kind": "feedback_collection",
                    "priority": "medium",
                    "title": "Collect explicit feedback",
                    "reason": "No feedback events are stored for this user yet.",
                    "target": {"page_key": "workbench"},
                }
            )
        if int((analytics.get("totals") or {}).get("events") or 0) > 0 and not self.get_user_data_policy(uid).get("allow_learning"):
            recommendations.append(
                {
                    "id": "learning:opt_in_review",
                    "kind": "learning_policy",
                    "priority": "low",
                    "title": "Review learning opt-in",
                    "reason": "Behavior data exists, but learning use is disabled.",
                    "target": {"user_id": uid},
                }
            )
        return {
            "object": "aiask.workflow_recommendations",
            "user_id": uid,
            "data_source": "local_user_activity",
            "data": recommendations[: max(1, min(int(limit or 5), 20))],
            "count": min(len(recommendations), max(1, min(int(limit or 5), 20))),
            "secrets_redacted": True,
        }

    def _list_user_data_policies(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM user_data_policies ORDER BY user_id ASC").fetchall()
        return [item for row in rows if (item := self._policy_row(row)) is not None]

    @staticmethod
    def _fts_available(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("SELECT 1 FROM aiask_search_fts LIMIT 1").fetchone()
            return True
        except sqlite3.OperationalError:
            return False

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
                INSERT OR IGNORE INTO sessions
                    (session_id, user_id, title, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sid, user_id, None, ts, ts, _dumps({})),
            )
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
        include_archived: bool = False,
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
                return [
                    item
                    for row in rows
                    if (item := self._search_row(row)) is not None
                    and (include_archived or not self._session_is_archived(conn, str(item.get("session_id") or "")))
                ]
            except sqlite3.OperationalError:
                return self._search_like(conn, token=token, session_id=session_id, limit=max_rows, include_archived=include_archived)

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
        include_archived: bool,
    ) -> list[dict[str, Any]]:
        values: list[Any] = [f"%{token}%"]
        clauses = ["content LIKE ?"]
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        clauses.append("deleted_at IS NULL")
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
        items = [
            item
            for row in rows
            if (item := AgentSessionStore._search_row(row)) is not None
            and (include_archived or not AgentSessionStore._session_is_archived(conn, str(item.get("session_id") or "")))
        ]
        if len(items) >= limit:
            return items[:limit]
        remaining = max(1, limit - len(items))
        source_values: list[Any] = [f"%{token}%", f"%{token}%", f"%{token}%", f"%{token}%"]
        source_clauses = ["(title LIKE ? OR url LIKE ? OR provider LIKE ? OR excerpt LIKE ?)"]
        if session_id:
            source_clauses.append("session_id = ?")
            source_values.append(session_id)
        source_values.append(remaining)
        source_rows = conn.execute(
            f"""
            SELECT 'source' AS kind, source_id AS object_id, session_id, user_id,
                   COALESCE(title, url, provider, source_type) AS content, metadata_json AS payload_json
            FROM agent_sources
            WHERE {" AND ".join(source_clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(source_values),
        ).fetchall()
        items.extend(
            item
            for row in source_rows
            if (item := AgentSessionStore._search_row(row)) is not None
            and (include_archived or not AgentSessionStore._session_is_archived(conn, str(item.get("session_id") or "")))
        )
        if len(items) >= limit:
            return items[:limit]
        remaining = max(1, limit - len(items))
        artifact_values: list[Any] = [f"%{token}%", f"%{token}%", f"%{token}%", f"%{token}%"]
        artifact_clauses = ["(title LIKE ? OR path LIKE ? OR uri LIKE ? OR preview_text LIKE ?)"]
        if session_id:
            artifact_clauses.append("session_id = ?")
            artifact_values.append(session_id)
        artifact_values.append(remaining)
        artifact_rows = conn.execute(
            f"""
            SELECT 'artifact' AS kind, artifact_id AS object_id, session_id, user_id,
                   COALESCE(title, path, uri, kind) AS content, metadata_json AS payload_json
            FROM agent_artifacts
            WHERE {" AND ".join(artifact_clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            tuple(artifact_values),
        ).fetchall()
        items.extend(
            item
            for row in artifact_rows
            if (item := AgentSessionStore._search_row(row)) is not None
            and (include_archived or not AgentSessionStore._session_is_archived(conn, str(item.get("session_id") or "")))
        )
        return items[:limit]

    @staticmethod
    def _session_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["metadata"] = _loads(item.pop("metadata_json", None), {})
        return item

    @staticmethod
    def _session_is_archived(conn: sqlite3.Connection, session_id: str) -> bool:
        if not session_id:
            return False
        row = conn.execute("SELECT metadata_json FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return False
        return _metadata_archived(_loads(row["metadata_json"], {}))

    @staticmethod
    def _activity_event_row(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        return item

    @staticmethod
    def _tool_invocation_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["input_summary"] = _loads(item.pop("input_summary_json", None), {})
        item["output_summary"] = _loads(item.pop("output_summary_json", None), {})
        item["source_chain"] = _loads(item.pop("source_chain_json", None), [])
        item["secrets_redacted"] = bool(item.get("secrets_redacted"))
        return item

    @staticmethod
    def _source_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["metadata"] = _loads(item.pop("metadata_json", None), {})
        return item

    @staticmethod
    def _artifact_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["preview_json"] = _loads(item.pop("preview_json", None), {})
        item["metadata"] = _loads(item.pop("metadata_json", None), {})
        return item

    @staticmethod
    def _context_snapshot_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["compacted"] = bool(item.get("compacted"))
        item["source_message_ids"] = _loads(item.pop("source_message_ids_json", None), [])
        item["source_ids"] = _loads(item.pop("source_ids_json", None), [])
        item["artifact_ids"] = _loads(item.pop("artifact_ids_json", None), [])
        item["risk_flags"] = _loads(item.pop("risk_flags_json", None), [])
        item["metadata"] = _loads(item.pop("metadata_json", None), {})
        item["secrets_redacted"] = True
        return item

    @staticmethod
    def _feedback_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        item["allow_learning"] = bool(item.get("allow_learning"))
        return item

    @staticmethod
    def _policy_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["allow_product_analytics"] = bool(item.get("allow_product_analytics"))
        item["allow_learning"] = bool(item.get("allow_learning"))
        return item

    @staticmethod
    def _broker_profile_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["read_only_enabled"] = bool(item.get("read_only_enabled"))
        item["write_enabled"] = bool(item.get("write_enabled"))
        item["metadata"] = _loads(item.pop("metadata_json", None), {})
        item["secrets_redacted"] = True
        return item

    @staticmethod
    def _broker_account_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        item["secrets_redacted"] = True
        return item

    @staticmethod
    def _broker_position_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        item["secrets_redacted"] = True
        return item

    @staticmethod
    def _broker_order_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        item["secrets_redacted"] = True
        return item

    @staticmethod
    def _broker_deal_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["payload"] = _loads(item.pop("payload_json", None), {})
        item["secrets_redacted"] = True
        return item

    @staticmethod
    def _broker_analytics_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["metrics"] = _loads(item.pop("metrics_json", None), {})
        item["signals"] = _loads(item.pop("signals_json", None), {})
        item["risk_flags"] = _loads(item.pop("risk_flags_json", None), [])
        item["source_snapshot_ids"] = _loads(item.pop("source_snapshot_ids_json", None), {})
        item["secrets_redacted"] = True
        return item

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
