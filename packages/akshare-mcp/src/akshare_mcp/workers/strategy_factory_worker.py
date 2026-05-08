"""DB-backed worker for heavy strategy_factory strategy_manager actions."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
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


def _worker_id() -> str:
    configured = str(os.getenv("STRATEGY_FACTORY_WORKER_ID") or "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}:{os.getpid()}"


def _timeout_seconds(action: str) -> float:
    normalized = str(action or "").strip().lower()
    specific_env = f"STRATEGY_FACTORY_WORKER_TIMEOUT_{normalized.upper()}_SECONDS"
    raw = os.getenv(specific_env)
    if raw is None:
        if normalized == "runtime_cycle_run":
            raw = os.getenv("STRATEGY_RUNTIME_WORKER_TASK_TIMEOUT_SECONDS")
        else:
            raw = os.getenv("STRATEGY_FACTORY_WORKER_TASK_TIMEOUT_SECONDS")
    defaults = {
        "factory_dispatch_run": 180.0,
        "factory_run_once": 180.0,
        "incubation_pipeline_run": 120.0,
        "incubation_sync_run": 120.0,
        "runtime_cycle_run": 900.0,
        "risk_scan_run": 300.0,
        "runtime_alert_dispatch_run": 180.0,
        "promotion_review_run": 180.0,
        "domain_projection_rebuild": 300.0,
        "vector_reconcile": 300.0,
        "vector_rebuild": 300.0,
        "vector_cleanup": 300.0,
        "ai_generate": 300.0,
    }
    try:
        return max(10.0, float(raw)) if raw is not None else defaults.get(normalized, 300.0)
    except (TypeError, ValueError):
        return defaults.get(normalized, 300.0)


def _lease_seconds(action: str) -> int:
    timeout = _timeout_seconds(action)
    raw = os.getenv("STRATEGY_FACTORY_WORKER_LEASE_SECONDS")
    try:
        configured = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        configured = 0
    return max(60, min(max(configured, int(timeout) + 60), 24 * 3600))


def _heartbeat_interval_seconds(action: str) -> float:
    raw = os.getenv("STRATEGY_FACTORY_WORKER_HEARTBEAT_INTERVAL_SECONDS")
    try:
        configured = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        configured = 0.0
    lease = _lease_seconds(action)
    return max(5.0, min(configured or lease / 3.0, max(5.0, lease / 2.0)))


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
            clear_lease=True,
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
                clear_lease=True,
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
            clear_lease=True,
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
            clear_lease=True,
        )


async def _safe_update_task_run(db, task_id: int, **payload: Any) -> None:
    try:
        await db.update_strategy_task_run(task_id, **payload)
    except Exception:
        logger.exception("Failed to update strategy task_run_id=%s", task_id)


async def _heartbeat_loop(db, task_id: int, *, action: str, worker_id: str, stop_event: asyncio.Event) -> None:
    interval = _heartbeat_interval_seconds(action)
    lease = _lease_seconds(action)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            break
        try:
            heartbeat = getattr(db, "heartbeat_strategy_task_run", None)
            if callable(heartbeat):
                await heartbeat(task_id, lease_owner=worker_id, lease_seconds=lease)
            else:
                await db.update_strategy_task_run(
                    task_id,
                    heartbeat_at=_utc_now(),
                    lease_owner=worker_id,
                )
        except Exception as exc:
            logger.warning(
                "Heartbeat failed for strategy task_run_id=%s action=%s: %s",
                task_id,
                action,
                exc,
            )


async def _execute_with_timeout(db, task_run: dict, *, worker_id: str) -> None:
    task_id = int(task_run.get("id"))
    payload = dict(task_run.get("payload") or {})
    action = str(payload.get("action") or task_run.get("task_name") or "").strip()
    timeout = _timeout_seconds(action)
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(db, task_id, action=action, worker_id=worker_id, stop_event=heartbeat_stop),
        name=f"strategy-task-heartbeat-{task_id}",
    )
    try:
        await asyncio.wait_for(_execute_task_run(db, task_run), timeout=timeout)
    except asyncio.TimeoutError:
        status = "retryable_timeout"
        try:
            attempts = int(task_run.get("attempt_count") or 0)
            max_attempts = int(task_run.get("max_attempts") or 3)
            if attempts >= max_attempts:
                status = "failed_timeout"
        except Exception:
            pass
        logger.error(
            "Strategy factory task_run_id=%s action=%s timed out after %.0fs; status=%s",
            task_id,
            action,
            timeout,
            status,
        )
        await _safe_update_task_run(
            db,
            task_id,
            status=status,
            error=f"{action or 'task'} timed out after {timeout:.0f}s",
            result={
                "action": action,
                "error_type": "TimeoutError",
                "timeout_seconds": timeout,
                "retryable": status == "retryable_timeout",
                "worker_id": worker_id,
            },
            completed_at=_utc_now(),
            clear_lease=True,
        )
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task


async def run_worker() -> None:
    logging.basicConfig(
        level=str(os.getenv("LOG_LEVEL") or "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    db = get_db()
    await db.initialize()

    poll_interval = _poll_interval_seconds()
    action_names = _action_names()
    worker_id = _worker_id()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logger.info(
        "strategy-factory-worker started worker_id=%s scope=%s actions=%s poll_interval=%ss",
        worker_id,
        STRATEGY_FACTORY_WORKER_TASK_SCOPE,
        ",".join(action_names),
        poll_interval,
    )
    try:
        while not stop_event.is_set():
            try:
                task_run = await db.claim_strategy_task_run(
                    task_scope=STRATEGY_FACTORY_WORKER_TASK_SCOPE,
                    task_names=action_names,
                    lease_owner=worker_id,
                    lease_seconds=max(_lease_seconds(action) for action in action_names) if action_names else 300,
                )
            except Exception as exc:
                logger.exception("strategy-factory-worker claim failed; resetting DB pool: %s", exc)
                with contextlib.suppress(Exception):
                    await close_db()
                await asyncio.sleep(max(2.0, poll_interval * 2.0))
                db = get_db()
                with contextlib.suppress(Exception):
                    await db.initialize()
                continue
            if not task_run:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                await _execute_with_timeout(db, task_run, worker_id=worker_id)
            except Exception as exc:
                task_id = int(task_run.get("id") or 0)
                logger.exception("strategy-factory-worker task execution crashed; resetting DB pool: %s", exc)
                if task_id:
                    await _safe_update_task_run(
                        db,
                        task_id,
                        status="retryable_failure",
                        error=str(exc),
                        result={
                            "error_type": exc.__class__.__name__,
                            "worker_id": worker_id,
                            "retryable": True,
                        },
                        completed_at=_utc_now(),
                        clear_lease=True,
                    )
                with contextlib.suppress(Exception):
                    await close_db()
                await asyncio.sleep(max(2.0, poll_interval * 2.0))
                db = get_db()
                with contextlib.suppress(Exception):
                    await db.initialize()
    finally:
        logger.info("strategy-factory-worker stopping")
        await close_db()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
