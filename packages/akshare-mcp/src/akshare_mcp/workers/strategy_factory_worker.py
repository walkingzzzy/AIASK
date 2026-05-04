"""DB-backed worker for heavy strategy_factory strategy_manager actions."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Any

from akshare_mcp.storage import close_db, get_db
from akshare_mcp.tools.managers.strategy_manager import (
    ACTION_HANDLERS,
    STRATEGY_FACTORY_WORKER_ACTIONS,
    STRATEGY_FACTORY_WORKER_TASK_SCOPE,
    _WORKER_BYPASS_PARAM,
    _normalize_strategy_manager_failure,
)

logger = logging.getLogger(__name__)


def _poll_interval_seconds() -> float:
    raw = os.getenv("STRATEGY_FACTORY_WORKER_POLL_INTERVAL_SECONDS", "2")
    try:
        return max(0.25, float(raw))
    except (TypeError, ValueError):
        return 2.0


def _action_names() -> list[str]:
    configured = str(os.getenv("STRATEGY_FACTORY_WORKER_ACTIONS") or "").strip()
    if configured:
        actions = [item.strip() for item in configured.split(",") if item.strip()]
    else:
        actions = sorted(STRATEGY_FACTORY_WORKER_ACTIONS)
    return [action for action in actions if action in ACTION_HANDLERS]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result_failed(result: Any) -> bool:
    return isinstance(result, dict) and result.get("success") is False


def _result_error(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    return str(result.get("error") or result.get("message") or "").strip() or None


def _handler_action(action: str) -> str:
    if action == "factory_dispatch_run" and str(
        os.getenv("STRATEGY_FACTORY_WORKER_SYNC_FACTORY_DISPATCH", "true")
    ).strip().lower() in {"1", "true", "yes", "on"}:
        return "factory_run_once"
    return action


async def _execute_task_run(db, task_run: dict) -> None:
    task_id = int(task_run.get("id"))
    payload = dict(task_run.get("payload") or {})
    action = str(payload.get("action") or task_run.get("task_name") or "").strip()
    params = dict(payload.get("params") or {})
    params[_WORKER_BYPASS_PARAM] = True
    params.setdefault("source", "strategy_factory_worker")
    params.setdefault("worker_task_run_id", task_id)

    handler_name = _handler_action(action)
    handler = ACTION_HANDLERS.get(handler_name)
    if not action or handler is None:
        message = f"unsupported strategy factory worker action: {action or '<empty>'}"
        await db.update_strategy_task_run(
            task_id,
            status="failed",
            error=message,
            result={"action": action, "handler_action": handler_name},
            completed_at=_utc_now(),
        )
        logger.warning("Rejected strategy factory task_run_id=%s: %s", task_id, message)
        return

    logger.info(
        "Running strategy factory task_run_id=%s action=%s handler=%s",
        task_id,
        action,
        handler_name,
    )
    try:
        result = await handler(db, params)
        result = _normalize_strategy_manager_failure(action, result)
        if _result_failed(result):
            await db.update_strategy_task_run(
                task_id,
                status="failed",
                error=_result_error(result) or f"{action} failed",
                result={
                    "action": action,
                    "handler_action": handler_name,
                    "result": result,
                },
                completed_at=_utc_now(),
            )
            return
        await db.update_strategy_task_run(
            task_id,
            status="completed",
            result={
                "action": action,
                "handler_action": handler_name,
                "result": result,
            },
            error=None,
            completed_at=_utc_now(),
        )
    except Exception as exc:
        logger.exception("Strategy factory task_run_id=%s action=%s failed", task_id, action)
        await db.update_strategy_task_run(
            task_id,
            status="failed",
            error=str(exc),
            result={
                "action": action,
                "handler_action": handler_name,
                "error_type": exc.__class__.__name__,
            },
            completed_at=_utc_now(),
        )


async def run_worker() -> None:
    logging.basicConfig(
        level=str(os.getenv("LOG_LEVEL") or "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    db = get_db()
    await db.initialize()

    poll_interval = _poll_interval_seconds()
    action_names = _action_names()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logger.info(
        "strategy-factory-worker started scope=%s actions=%s poll_interval=%ss",
        STRATEGY_FACTORY_WORKER_TASK_SCOPE,
        ",".join(action_names),
        poll_interval,
    )
    try:
        while not stop_event.is_set():
            task_run = await db.claim_strategy_task_run(
                task_scope=STRATEGY_FACTORY_WORKER_TASK_SCOPE,
                task_names=action_names,
            )
            if not task_run:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                except asyncio.TimeoutError:
                    pass
                continue
            await _execute_task_run(db, task_run)
    finally:
        logger.info("strategy-factory-worker stopping")
        await close_db()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
