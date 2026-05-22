from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from uuid import uuid4

from .paths import default_state_db_path
from .session_store import now_iso


DANGEROUS_COMMAND_RE = re.compile(
    r"(^|\s)(sudo|su|rm\s+-[^\n]*[rf]|mkfs|dd\s+if=|shutdown|reboot|killall|chmod\s+-R|chown\s+-R)\b",
    re.IGNORECASE,
)


class ApprovalStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_db_path()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                action TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    def create(self, *, tool_name: str, action: str, arguments: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        approval_id = f"approval_{uuid4().hex}"
        ts = now_iso()
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO approvals
                    (approval_id, tool_name, action, arguments_json, status, reason, result_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (approval_id, tool_name, action, json.dumps(arguments, ensure_ascii=False, sort_keys=True), "pending", reason, "{}", ts, ts),
            )
            conn.commit()
        item = self.get(approval_id)
        assert item is not None
        return item

    def get(self, approval_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?",
                (str(approval_id or "").strip(),),
            ).fetchone()
        return self._row(row)

    def list(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        values: list[Any] = []
        where = ""
        if status:
            where = "WHERE status = ?"
            values.append(status)
        values.append(max(1, min(int(limit or 100), 1000)))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT * FROM approvals {where} ORDER BY created_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._row(row)) is not None]

    def decide(self, approval_id: str, *, approved: bool, reason: str | None = None, result: dict[str, Any] | None = None) -> dict[str, Any] | None:
        status = "approved" if approved else "denied"
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE approvals SET status = ?, reason = ?, result_json = ?, updated_at = ? WHERE approval_id = ?",
                (status, reason, json.dumps(dict(result or {}), ensure_ascii=False, sort_keys=True), now_iso(), str(approval_id or "").strip()),
            )
            conn.commit()
        return self.get(approval_id)

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        for key, default in (("arguments_json", {}), ("result_json", {})):
            raw = item.pop(key, None)
            try:
                item[key.removesuffix("_json")] = json.loads(raw or "{}")
            except Exception:
                item[key.removesuffix("_json")] = default
        return item


def command_requires_approval(command: str) -> bool:
    if str(command or "").strip().lower().startswith("aiask-allow "):
        return False
    return bool(DANGEROUS_COMMAND_RE.search(str(command or "")))
