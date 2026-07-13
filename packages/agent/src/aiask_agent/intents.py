from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .paths import default_intent_db_path
from .tool_risk import (
    AGENT_EXECUTABLE_STRATEGY_ACTIONS,
    CONFIRM_REQUIRED_STRATEGY_ACTIONS,
    STATEFUL_INTENT_ACTIONS_REQUIRING_EXPLICIT_DRY_RUN,
    classify_strategy_manager_action,
)


INTENT_STATUSES = (
    "awaiting_confirmation",
    "confirmed",
    "denied",
    "executing",
    "succeeded",
    "failed",
    "expired",
)

ALLOWED_STRATEGY_ACTIONS = set(CONFIRM_REQUIRED_STRATEGY_ACTIONS)

ALLOWED_ACTIONS = {
    f"strategy_manager.{action}": {"tool": "strategy_manager", "action": action}
    for action in sorted(ALLOWED_STRATEGY_ACTIONS)
}
ALLOWED_ACTIONS.update(
    {
        "data_sync.sync": {"tool": "data_sync", "action": "sync"},
        "data_sync.maintenance": {"tool": "data_sync", "action": "maintenance"},
        "data_sync.run_due_schedules": {"tool": "data_sync", "action": "run_due_schedules"},
        "portfolio_manager.create": {"tool": "financial_manager", "action": "portfolio_manager.create"},
        "portfolio_manager.update": {"tool": "financial_manager", "action": "portfolio_manager.update"},
        "portfolio_manager.delete": {"tool": "financial_manager", "action": "portfolio_manager.delete"},
        "portfolio_manager.add_holding": {"tool": "financial_manager", "action": "portfolio_manager.add_holding"},
        "portfolio_manager.remove_holding": {"tool": "financial_manager", "action": "portfolio_manager.remove_holding"},
        "watchlist_manager.create_group": {"tool": "financial_manager", "action": "watchlist_manager.create_group"},
        "watchlist_manager.delete_group": {"tool": "financial_manager", "action": "watchlist_manager.delete_group"},
        "watchlist_manager.add": {"tool": "financial_manager", "action": "watchlist_manager.add"},
        "watchlist_manager.remove": {"tool": "financial_manager", "action": "watchlist_manager.remove"},
        "watchlist_manager.reorder": {"tool": "financial_manager", "action": "watchlist_manager.reorder"},
        "paper_trading_manager.submit_order": {"tool": "financial_manager", "action": "paper_trading_manager.submit_order"},
        "paper_trading_manager.cancel_order": {"tool": "financial_manager", "action": "paper_trading_manager.cancel_order"},
        "execution_manager.create_plan": {"tool": "financial_manager", "action": "execution_manager.create_plan"},
        "execution_manager.submit_task": {"tool": "financial_manager", "action": "execution_manager.submit_task"},
        "execution_manager.cancel_task": {"tool": "financial_manager", "action": "execution_manager.cancel_task"},
        "factor_factory.run_once": {"tool": "factor_factory", "action": "run_once"},
        "factor_factory.maintenance": {"tool": "factor_factory", "action": "maintenance"},
        "incubation_factory.run_once": {"tool": "incubation_factory", "action": "run_once"},
        "incubation_factory.dry_run": {"tool": "incubation_factory", "action": "dry_run"},
        "incubation_factory.maintenance": {"tool": "incubation_factory", "action": "maintenance"},
        "stock_radar.run_once": {"tool": "stock_radar", "action": "run_once"},
        "stock_radar.push_digest": {"tool": "stock_radar", "action": "push_digest"},
        "stock_radar.schedule_update": {"tool": "stock_radar", "action": "schedule_update"},
        "gateway.send_message": {"tool": "gateway", "action": "send_message"},
        "gateway.direct_deliver": {"tool": "gateway", "action": "direct_deliver"},
        "webhook.trigger": {"tool": "webhook", "action": "trigger"},
        # P2 soak / ops (read-only; dry-run defaults inside executor)
        "ops.db_soak": {"tool": "ops", "action": "db_soak"},
        "factory.soak_check": {"tool": "ops", "action": "db_soak"},
    }
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def normalize_action(action: str) -> tuple[str, dict[str, str]]:
    token = str(action or "").strip()
    if token in ALLOWED_ACTIONS:
        return token, dict(ALLOWED_ACTIONS[token])
    prefixed = f"strategy_manager.{token}"
    if prefixed in ALLOWED_ACTIONS:
        return prefixed, dict(ALLOWED_ACTIONS[prefixed])
    raise ValueError(f"action is not allowed for confirmation execution: {token}")


def _strategy_action_name(action_key: str, target_action: str) -> str:
    if action_key.startswith("strategy_manager."):
        return action_key.split(".", 1)[1]
    return str(target_action or "").strip()


def assert_intent_executable(action_key: str, target: dict[str, str]) -> None:
    """Fail closed before creating intents that cannot be confirmed usefully."""
    tool = str(target.get("tool") or "").strip()
    target_action = str(target.get("action") or "").strip()
    if tool == "strategy_manager":
        strategy_action = _strategy_action_name(action_key, target_action)
        classification = classify_strategy_manager_action(strategy_action)
        if classification.get("confirmation_required") and not classification.get("agent_executable", True):
            raise ValueError(
                "STRATEGY_FACTORY_EXTERNAL_RUNNER_REQUIRED: "
                f"{action_key} is confirm-policy-listed but owned by external runner; "
                f"executable_actions={sorted(AGENT_EXECUTABLE_STRATEGY_ACTIONS)}"
            )


def apply_intent_safety_defaults(action_key: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Default high-side-effect intents to dry_run unless explicitly overridden."""
    payload = dict(params or {})
    if action_key in STATEFUL_INTENT_ACTIONS_REQUIRING_EXPLICIT_DRY_RUN:
        if "dry_run" not in payload:
            payload["dry_run"] = True
    if action_key == "incubation_factory.run_once" and "dry_run" not in payload:
        payload["dry_run"] = True
    if action_key in {"paper_trading_manager.submit_order", "execution_manager.create_plan"}:
        payload["dry_run"] = True
    if action_key == "stock_radar.push_digest" and "dry_run" not in payload:
        payload["dry_run"] = True
    return payload


@dataclass(frozen=True)
class IntentTransition:
    changed: bool
    intent: dict[str, Any] | None


class ActionIntentStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_intent_db_path()

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
            CREATE TABLE IF NOT EXISTS action_intents (
                intent_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                target_tool TEXT NOT NULL,
                target_action TEXT NOT NULL,
                params_json TEXT NOT NULL,
                status TEXT NOT NULL,
                user_id TEXT,
                rationale TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                confirmed_at TEXT,
                denied_at TEXT,
                executed_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_action_intents_status ON action_intents(status, expires_at)"
        )
        conn.commit()

    @staticmethod
    def _row_to_intent(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["params"] = _loads(item.pop("params_json", None), {})
        item["result"] = _loads(item.pop("result_json", None), None)
        return item

    def create(
        self,
        *,
        action: str,
        params: dict[str, Any] | None = None,
        user_id: str | None = None,
        rationale: str | None = None,
        ttl_seconds: int = 24 * 60 * 60,
    ) -> dict[str, Any]:
        action_key, target = normalize_action(action)
        assert_intent_executable(action_key, target)
        safe_params = apply_intent_safety_defaults(action_key, params)
        ts = now_utc()
        intent_id = f"intent_{ts.strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:10]}"
        expires_at = ts + timedelta(seconds=max(60, int(ttl_seconds or 86400)))
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO action_intents
                    (intent_id, action, target_tool, target_action, params_json, status,
                     user_id, rationale, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_id,
                    action_key,
                    target["tool"],
                    target["action"],
                    _dumps(safe_params),
                    "awaiting_confirmation",
                    user_id,
                    rationale,
                    ts.isoformat(),
                    ts.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
        return self.get(intent_id) or {"intent_id": intent_id, "status": "awaiting_confirmation"}

    def get(self, intent_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM action_intents WHERE intent_id = ?",
                (str(intent_id or "").strip(),),
            ).fetchone()
        item = self._row_to_intent(row)
        if item and item.get("status") == "awaiting_confirmation":
            expires_at = datetime.fromisoformat(str(item["expires_at"]))
            if expires_at < now_utc():
                # Use transition() (guarded UPDATE) instead of update_status(),
                # which would re-enter get() and recurse infinitely on an
                # already-expired intent (the row stays awaiting_confirmation
                # until the UPDATE lands). transition() flips the row directly
                # and returns the refreshed (now "expired") intent.
                transition = self.transition(
                    item["intent_id"],
                    expected_status="awaiting_confirmation",
                    next_status="expired",
                    error="intent expired",
                )
                return transition.intent if transition.intent is not None else item
        return item

    def list(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        normalized_status = str(status or "").strip()
        if normalized_status:
            clauses.append("status = ?")
            values.append(normalized_status)
        values.append(max(1, min(int(limit or 100), 500)))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT * FROM action_intents {where} ORDER BY updated_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
        return [item for row in rows if (item := self._row_to_intent(row)) is not None]

    def transition(
        self,
        intent_id: str,
        *,
        expected_status: str,
        next_status: str,
        result: Any = None,
        error: str | None = None,
    ) -> IntentTransition:
        if expected_status not in INTENT_STATUSES or next_status not in INTENT_STATUSES:
            raise ValueError("invalid intent status")
        ts = now_iso()
        fields = ["status = ?", "updated_at = ?"]
        values: list[Any] = [next_status, ts]
        if result is not None:
            fields.append("result_json = ?")
            values.append(_dumps(result))
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if next_status == "confirmed":
            fields.append("confirmed_at = ?")
            values.append(ts)
        if next_status == "denied":
            fields.append("denied_at = ?")
            values.append(ts)
        if next_status in {"succeeded", "failed"}:
            fields.append("executed_at = ?")
            values.append(ts)
        values.extend([str(intent_id or "").strip(), expected_status])
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"""
                UPDATE action_intents
                SET {", ".join(fields)}
                WHERE intent_id = ? AND status = ?
                """,
                tuple(values),
            )
            conn.commit()
            changed = cur.rowcount == 1
        return IntentTransition(changed=changed, intent=self.get(intent_id))

    def update_status(
        self,
        intent_id: str,
        status: str,
        *,
        result: Any = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        current = self.get(intent_id)
        if current is None:
            return None
        return self.transition(
            intent_id,
            expected_status=str(current["status"]),
            next_status=status,
            result=result,
            error=error,
        ).intent


class IntentExecutor:
    def __init__(self, store: ActionIntentStore | None = None) -> None:
        self.store = store or ActionIntentStore()

    async def confirm(self, intent_id: str) -> dict[str, Any]:
        current = self.store.get(intent_id)
        if current is None:
            return {"success": False, "error": f"intent not found: {intent_id}", "error_code": "NOT_FOUND"}
        transition = self.store.transition(
            intent_id,
            expected_status="awaiting_confirmation",
            next_status="confirmed",
        )
        if not transition.changed or transition.intent is None:
            return {
                "success": False,
                "error": f"intent cannot be confirmed from status={current.get('status')}",
                "error_code": "INVALID_STATUS",
                "data": {"intent": current},
            }
        executing = self.store.transition(intent_id, expected_status="confirmed", next_status="executing")
        intent = executing.intent or transition.intent
        try:
            from .adapters.desktop_ops import execute_confirmed_action

            result = await execute_confirmed_action(
                str(intent["target_tool"]),
                str(intent["target_action"]),
                dict(intent.get("params") or {}),
            )
        except Exception as exc:
            final_intent = self.store.update_status(intent_id, "failed", error=str(exc))
            return {
                "success": False,
                "error": str(exc),
                "error_code": "EXECUTION_FAILED",
                "data": {"intent": final_intent},
            }

        success = not isinstance(result, dict) or result.get("success") is not False
        final_intent = self.store.update_status(
            intent_id,
            "succeeded" if success else "failed",
            result=result,
            error=None if success else str(result.get("error") if isinstance(result, dict) else "execution failed"),
        )
        return {
            "success": success,
            "data": {"intent": final_intent, "execution_result": result},
            "error": None if success else "intent execution failed",
        }

    async def deny(self, intent_id: str, reason: str | None = None) -> dict[str, Any]:
        current = self.store.get(intent_id)
        if current is None:
            return {"success": False, "error": f"intent not found: {intent_id}", "error_code": "NOT_FOUND"}
        transition = self.store.transition(
            intent_id,
            expected_status="awaiting_confirmation",
            next_status="denied",
            error=reason or "denied",
        )
        if not transition.changed:
            return {
                "success": False,
                "error": f"intent cannot be denied from status={current.get('status')}",
                "error_code": "INVALID_STATUS",
                "data": {"intent": current},
            }
        return {"success": True, "data": {"intent": transition.intent}, "error": None}
