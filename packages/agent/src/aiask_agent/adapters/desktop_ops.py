from __future__ import annotations

import asyncio
import inspect
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..numeric import bounded_float, bounded_int


def _ensure_monorepo_paths() -> None:
    for parent in Path(__file__).resolve().parents:
        candidates = [
            parent / "akshare-mcp" / "src",
            parent / "aiask-quant-core" / "src",
            parent / "strategy-factory" / "src",
        ]
        added = False
        for candidate in candidates:
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
                added = True
        if added:
            return


def _dependency_missing(exc: BaseException, *, dependency: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "configured": False,
            "dependency": dependency,
            "detail": str(exc),
        },
        "error": str(exc),
        "error_code": f"MISSING_{dependency.upper()}",
    }


def _execution_failed(exc: BaseException, *, action: str, dependency: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "configured": False,
            "dependency": dependency,
            "action": action,
            "detail": str(exc),
        },
        "error": str(exc),
        "error_code": f"{dependency.upper()}_EXECUTION_FAILED",
    }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def factor_factory_status(limit: int = 50) -> dict[str, Any]:
    try:
        _ensure_monorepo_paths()
        from akshare_mcp.services.factor_mining_factory.api import get_factor_pool_gateway
    except ModuleNotFoundError as exc:
        return {
            "object": "aiask.desktop.factor_factory_status",
            "status": "unconfigured",
            "configured": False,
            "active_factors": [],
            "engine_health": {},
            "pool_health": {},
            "error": str(exc),
            "error_code": "MISSING_FACTOR_FACTORY",
            "secrets_redacted": True,
        }

    try:
        gateway = get_factor_pool_gateway()
        pool_status = await asyncio.wait_for(gateway.get_pool_status(), timeout=15)
        active_factors = await asyncio.wait_for(
            gateway.get_active_factors(limit=bounded_int(limit, default=50, minimum=1, maximum=200)),
            timeout=15,
        )
        return {
            "object": "aiask.desktop.factor_factory_status",
            "status": "ready",
            "configured": True,
            "factory": pool_status,
            "active_factors": list(active_factors or []),
            "engine_health": dict((pool_status or {}).get("engines") or {}),
            "pool_health": dict((pool_status or {}).get("pool_health") or {}),
            "secrets_redacted": True,
        }
    except Exception as exc:
        return {
            "object": "aiask.desktop.factor_factory_status",
            "status": "degraded",
            "configured": False,
            "active_factors": [],
            "engine_health": {},
            "pool_health": {},
            "error": str(exc),
            "error_code": "FACTOR_FACTORY_STATUS_FAILED",
            "secrets_redacted": True,
        }


async def _execute_data_sync(action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        _ensure_monorepo_paths()
        from akshare_mcp.tools.managers.data_sync_manager import register_data_sync_manager
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="data_sync")

    class _CaptureMcp:
        def __init__(self) -> None:
            self.tools: dict[str, Callable[..., Any]] = {}

        def tool(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                fn = args[0]
                self.tools[fn.__name__] = fn
                return fn

            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self.tools[fn.__name__] = fn
                return fn

            return _decorator

    try:
        capture = _CaptureMcp()
        register_data_sync_manager(capture)
        fn = capture.tools.get("data_sync_manager")
        if not callable(fn):
            raise RuntimeError("data_sync_manager was not registered")
        normalized = "run_due_schedules" if action == "maintenance" else action
        if normalized not in {"sync", "run_due_schedules", "schedule", "cancel_task", "cancel_schedule"}:
            raise ValueError(f"unsupported data sync action: {action}")
        result = await asyncio.wait_for(
            _maybe_await(
                fn(
                    action=normalized,
                    params=dict(params or {}),
                    codes=params.get("codes"),
                    task_type=params.get("task_type") or params.get("type"),
                    period=params.get("period"),
                    force=params.get("force"),
                    limit=params.get("limit"),
                    priority=params.get("priority"),
                )
            ),
            timeout=bounded_float(params.get("_timeout_seconds"), default=120.0, minimum=1.0, maximum=3600.0),
        )
        return result if isinstance(result, dict) else {"success": True, "data": result, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="data_sync")


async def _execute_factor_factory(action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        _ensure_monorepo_paths()
        from strategy_factory.runtime.default_bootstrap import ensure_default_runtime_services
        from strategy_factory.runtime.factor_mining import get_factor_mining_runtime
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="factor_factory")

    try:
        ensure_default_runtime_services()
        runtime = get_factor_mining_runtime()
        timeout = bounded_float(params.get("_timeout_seconds"), default=300.0, minimum=1.0, maximum=3600.0)
        if action == "run_once":
            result = await asyncio.wait_for(
                runtime.run_once(
                    trigger=str(params.get("trigger") or "desktop_intent"),
                    engines=[str(item) for item in list(params.get("engines") or [])] or None,
                    candidate_count=bounded_int(params.get("candidate_count") or params.get("candidates"), default=10, minimum=1, maximum=1000),
                    evolution_generations=bounded_int(params.get("evolution_generations") or params.get("generations"), default=2, minimum=0, maximum=100),
                    codes=[str(item) for item in list(params.get("codes") or [])] or None,
                ),
                timeout=timeout,
            )
        elif action == "maintenance":
            result = await asyncio.wait_for(runtime.run_maintenance(), timeout=timeout)
        else:
            raise ValueError(f"unsupported factor factory action: {action}")
        return {"success": bool(not isinstance(result, dict) or result.get("success") is not False), "data": result, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="factor_factory")


async def _execute_incubation_factory(action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        _ensure_monorepo_paths()
        from strategy_factory.runtime.default_bootstrap import ensure_default_runtime_services
        from strategy_factory.runtime.incubation import build_incubation_runtime
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="incubation_factory")

    try:
        ensure_default_runtime_services()
        timeout = bounded_float(params.get("_timeout_seconds"), default=600.0, minimum=1.0, maximum=3600.0)
        if action == "dry_run":
            runtime = build_incubation_runtime(dry_run=True)
            result = await asyncio.wait_for(runtime.run_once(), timeout=timeout)
        elif action == "run_once":
            runtime = build_incubation_runtime()
            result = await asyncio.wait_for(runtime.run_once(), timeout=timeout)
        elif action == "maintenance":
            runtime = build_incubation_runtime()
            result = {
                "status": "ready",
                "detail": "Incubation factory has no separate maintenance pass; status was refreshed.",
                "runner": runtime.status(),
            }
        else:
            raise ValueError(f"unsupported incubation factory action: {action}")
        return {"success": bool(not isinstance(result, dict) or result.get("success") is not False), "data": result, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="incubation_factory")


STOCK_RADAR_SCHEDULE_JOB_NAME = "AIASK Stock Radar Safe Daily Scan"


def _bool_param(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled"}:
            return False
    return bool(value)


def _stock_radar_run_params(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": str(payload.get("mode") or "run_once"),
        "days": bounded_int(payload.get("days"), default=3, minimum=1, maximum=30),
        "limit": bounded_int(payload.get("limit"), default=80, minimum=1, maximum=500),
        "stock_codes": payload.get("stock_codes") or payload.get("codes"),
        "allow_network": _bool_param(payload.get("allow_network"), default=False),
        "allow_llm": _bool_param(payload.get("allow_llm"), default=False),
        "embed": _bool_param(payload.get("embed"), default=False),
        "parse_pdf": _bool_param(payload.get("parse_pdf"), default=True),
        "include_rss": _bool_param(payload.get("include_rss"), default=True),
        "ingest_market_text": _bool_param(payload.get("ingest_market_text"), default=True),
    }


def _stock_radar_schedule_prompt(run_params: dict[str, Any]) -> str:
    return (
        "Run the AIASK stock radar once using the approved safe schedule payload. "
        f"Parameters: days={run_params.get('days')}, limit={run_params.get('limit')}, "
        f"allow_network={run_params.get('allow_network')}, allow_llm={run_params.get('allow_llm')}, "
        f"parse_pdf={run_params.get('parse_pdf')}, ingest_market_text={run_params.get('ingest_market_text')}. "
        "Persist the radar run and digest through Agent-owned facades. "
        "Do not include buy, sell, position sizing, or live trading instructions."
    )


def _find_stock_radar_job(store: Any) -> dict[str, Any] | None:
    for job in store.list():
        payload = dict(job.get("payload") or {})
        if payload.get("stock_radar") is True and payload.get("action") == "run_once":
            return job
        if str(job.get("name") or "") == STOCK_RADAR_SCHEDULE_JOB_NAME:
            return job
    return None


def _schedule_stock_radar_update(payload: dict[str, Any]) -> dict[str, Any]:
    from ..scheduler import AgentJobStore

    store = AgentJobStore()
    schedule_raw = str(payload.get("schedule") or "").strip()
    schedule_value = None if schedule_raw.lower() in {"", "manual", "none", "off"} else schedule_raw
    interval_seconds = payload.get("interval_seconds")
    if interval_seconds is not None:
        interval_seconds = bounded_int(interval_seconds, default=86400, minimum=60, maximum=604800)
    enabled = _bool_param(payload.get("enabled"), default=bool(schedule_value or interval_seconds))
    if enabled and not schedule_value and not interval_seconds:
        interval_seconds = 86400
    delete_requested = _bool_param(payload.get("delete") or payload.get("remove"), default=False) or schedule_raw.lower() in {"delete", "remove"}
    existing = _find_stock_radar_job(store)
    if delete_requested:
        deleted = bool(existing and store.delete(str(existing.get("job_id") or "")))
        return {
            "success": True,
            "data": {
                "object": "stock_radar.schedule_update",
                "status": "deleted" if deleted else "not_found",
                "deleted": deleted,
                "job_id": existing.get("job_id") if existing else None,
                "preview": False,
                "auto_push": False,
                "source_chain": ["ActionIntent", "aiask_agent.scheduler"],
            },
            "error": None,
            "meta": {"side_effect": {"level": "stateful", "target": "agent_jobs"}},
        }

    run_params = _stock_radar_run_params(payload)
    job_payload = {
        "stock_radar": True,
        "action": "run_once",
        "run_params": run_params,
        "source": "stock_radar.schedule_update",
        "no_trade_instructions": True,
        "auto_push": False,
    }
    prompt = _stock_radar_schedule_prompt(run_params)
    if existing:
        job = store.update(
            str(existing.get("job_id") or ""),
            name=STOCK_RADAR_SCHEDULE_JOB_NAME,
            prompt=prompt,
            schedule=schedule_value,
            interval_seconds=interval_seconds,
            toolset="finance_safe",
            enabled=enabled,
            payload=job_payload,
        )
        status = "updated" if enabled else "disabled"
    else:
        job = store.create(
            name=STOCK_RADAR_SCHEDULE_JOB_NAME,
            prompt=prompt,
            schedule=schedule_value,
            interval_seconds=interval_seconds,
            toolset="finance_safe",
            enabled=enabled,
            payload=job_payload,
        )
        status = "scheduled" if enabled else "disabled"
    return {
        "success": True,
        "data": {
            "object": "stock_radar.schedule_update",
            "status": status,
            "job": job,
            "job_id": job.get("job_id") if isinstance(job, dict) else None,
            "schedule": schedule_value,
            "interval_seconds": interval_seconds,
            "enabled": enabled,
            "preview": False,
            "auto_push": False,
            "source_chain": ["ActionIntent", "aiask_agent.scheduler"],
        },
        "error": None,
        "meta": {"side_effect": {"level": "stateful", "target": "agent_jobs"}},
    }


async def _execute_stock_radar(action: str, params: dict[str, Any]) -> dict[str, Any]:
    if action == "schedule_update":
        try:
            return _schedule_stock_radar_update(dict(params or {}))
        except Exception as exc:
            return _execution_failed(exc, action=action, dependency="stock_radar")

    try:
        _ensure_monorepo_paths()
        from akshare_mcp.storage import get_db
        from akshare_mcp.services.stock_radar import (
            push_stock_radar_digest,
            run_stock_radar,
        )
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="stock_radar")

    async def _record_gateway_delivery_log(db: Any, payload: dict[str, Any], data: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any] | None:
        recorder = getattr(db, "save_stock_radar_push_log", None)
        if not callable(recorder):
            return None
        push_logs = list(data.get("push_logs") or [])
        first_log = next((item for item in push_logs if isinstance(item, dict)), {})
        channels = data.get("channels") or payload.get("channels") or []
        if isinstance(channels, str):
            channels = [item.strip() for item in channels.split(",") if item.strip()]
        targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
        channel = str(delivery.get("channel") or "")
        target = payload.get("target")
        if target is None:
            target = targets.get(channel)
        try:
            return await recorder(
                {
                    "run_id": payload.get("run_id") or first_log.get("run_id"),
                    "channel": channel,
                    "platform": delivery.get("platform") or channel,
                    "target": target,
                    "status": "delivered" if delivery.get("ok") else "failed",
                    "message_preview": payload.get("message") or data.get("message_preview"),
                    "candidate_count": bounded_int(first_log.get("candidate_count") or data.get("candidate_count"), default=0, minimum=0),
                    "error": None if delivery.get("ok") else delivery.get("error") or delivery.get("status"),
                    "sent_at": datetime.now(timezone.utc).isoformat() if delivery.get("ok") else None,
                    "metadata": {
                        "dry_run": False,
                        "gateway_delivery": delivery,
                        "gateway_message_id": delivery.get("message_id"),
                        "no_trade_instructions": True,
                        "upstream_push_log_ids": [item.get("push_id") for item in push_logs if isinstance(item, dict) and item.get("push_id")],
                    },
                }
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "channel": channel,
            }

    async def _deliver_stock_radar_digest(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if payload.get("dry_run", True) or result.get("success") is False:
            return result
        channels = data.get("channels") or payload.get("channels") or ["wecom", "telegram"]
        if isinstance(channels, str):
            channels = [item.strip() for item in channels.split(",") if item.strip()]
        message = str(payload.get("message") or data.get("message_preview") or "").strip()
        if not message:
            return {
                **result,
                "data": {**data, "gateway_status": "blocked_empty_message", "gateway_deliveries": []},
                "success": False,
                "error": "stock radar digest message is empty",
                "error_code": "STOCK_RADAR_GATEWAY_MESSAGE_EMPTY",
            }
        try:
            from ..gateway import DeliveryRouter, GatewayChannelDirectoryStore, GatewayMessageStore
            from ..paths import default_state_db_path

            state_path = default_state_db_path()
            router = DeliveryRouter(
                messages=GatewayMessageStore(state_path),
                directory=GatewayChannelDirectoryStore(state_path),
            )
            deliveries: list[dict[str, Any]] = []
            for channel in list(channels or []):
                target = payload.get("target")
                targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
                if target is None:
                    target = targets.get(str(channel))
                try:
                    routed = await router.send(
                        platform=str(channel),
                        target=str(target or ""),
                        message=message,
                        thread_id=payload.get("thread_id"),
                        session_id=payload.get("session_id"),
                        user_id=payload.get("user_id"),
                    )
                    adapter = routed.get("adapter") if isinstance(routed, dict) else {}
                    deliveries.append(
                        {
                            "channel": channel,
                            "status": adapter.get("status") if isinstance(adapter, dict) else "unknown",
                            "ok": bool(adapter.get("ok")) if isinstance(adapter, dict) else False,
                            "message_id": (routed.get("message") or {}).get("message_id") if isinstance(routed, dict) and isinstance(routed.get("message"), dict) else None,
                            "configured": adapter.get("configured") if isinstance(adapter, dict) else None,
                            "platform": (routed.get("platform") or {}).get("name") if isinstance(routed, dict) and isinstance(routed.get("platform"), dict) else str(channel),
                        }
                    )
                except Exception as exc:
                    deliveries.append(
                        {
                            "channel": channel,
                            "status": "failed",
                            "ok": False,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        }
                    )
            ok_count = sum(1 for item in deliveries if item.get("ok"))
            audit_logs = [item for delivery in deliveries if (item := await _record_gateway_delivery_log(db, payload, data, delivery)) is not None]
            gateway_status = "delivered" if ok_count == len(deliveries) and deliveries else "partial_or_failed"
            return {
                **result,
                "success": bool(result.get("success") and ok_count == len(deliveries) and deliveries),
                "data": {
                    **data,
                    "gateway_status": gateway_status,
                    "gateway_deliveries": deliveries,
                    "gateway_delivered_count": ok_count,
                    "gateway_push_logs": audit_logs,
                },
                "error": None if ok_count == len(deliveries) and deliveries else "one or more gateway deliveries failed or are unconfigured",
                "error_code": None if ok_count == len(deliveries) and deliveries else "STOCK_RADAR_GATEWAY_DELIVERY_FAILED",
            }
        except Exception as exc:
            return {
                **result,
                "success": False,
                "data": {**data, "gateway_status": "failed", "gateway_deliveries": []},
                "error": str(exc),
                "error_code": "STOCK_RADAR_GATEWAY_DELIVERY_FAILED",
            }

    try:
        payload = dict(params or {})
        timeout = bounded_float(
            payload.pop("_timeout_seconds", 300 if action == "run_once" else 60),
            default=300.0 if action == "run_once" else 60.0,
            minimum=1.0,
            maximum=3600.0,
        )
        db = get_db()
        await db.initialize()
        if action == "run_once":
            result = await asyncio.wait_for(
                run_stock_radar(
                    db,
                    mode=str(payload.get("mode") or "run_once"),
                    days=payload.get("days", 3),
                    limit=payload.get("limit", 80),
                    stock_codes=payload.get("stock_codes") or payload.get("codes"),
                    allow_network=payload.get("allow_network", False),
                    allow_llm=payload.get("allow_llm", False),
                    embed=payload.get("embed", False),
                    parse_pdf=payload.get("parse_pdf", True),
                    include_rss=payload.get("include_rss", True),
                    ingest_market_text=payload.get("ingest_market_text", True),
                ),
                timeout=timeout,
            )
        elif action == "push_digest":
            payload.setdefault("dry_run", True)
            result = await asyncio.wait_for(push_stock_radar_digest(db, payload), timeout=timeout)
            result = await _deliver_stock_radar_digest(payload, result if isinstance(result, dict) else {"success": True, "data": result, "error": None})
        else:
            raise ValueError(f"unsupported stock radar action: {action}")
        return result if isinstance(result, dict) else {"success": True, "data": result, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="stock_radar")


async def _execute_gateway(action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        from ..gateway import DeliveryRouter, GatewayChannelDirectoryStore, GatewayMessageStore
        from ..paths import default_state_db_path

        state_path = default_state_db_path()
        router = DeliveryRouter(
            messages=GatewayMessageStore(state_path),
            directory=GatewayChannelDirectoryStore(state_path),
        )
        payload = dict(params or {})
        data = await router.send(
            platform=str(payload.get("platform") or "local"),
            target=str(payload.get("target") or ""),
            message=str(payload.get("message") or ""),
            thread_id=payload.get("thread_id"),
            session_id=payload.get("session_id"),
            user_id=payload.get("user_id"),
            media_paths=[str(item) for item in list(payload.get("media_paths") or [])],
        )
        if action == "direct_deliver":
            data["deliver_mode"] = "direct_platform"
        return {"success": True, "data": data, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="gateway")


async def _execute_webhook(action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        from ..gateway import DeliveryRouter, GatewayChannelDirectoryStore, GatewayMessageStore
        from ..paths import default_state_db_path
        from ..webhooks import WebhookStore

        if action != "trigger":
            raise ValueError(f"unsupported webhook action: {action}")
        payload = dict(params or {})
        state_path = default_state_db_path()
        data = WebhookStore(state_path).render_trigger(
            str(payload.get("webhook_id") or ""),
            event=str(payload.get("event") or "event"),
            payload=dict(payload.get("payload") or {}),
            signature=payload.get("signature"),
        )
        deliver_config = data.get("deliver") if isinstance(data.get("deliver"), dict) else {}
        if isinstance(deliver_config, dict) and deliver_config.get("mode") == "direct_platform":
            routed = await DeliveryRouter(
                messages=GatewayMessageStore(state_path),
                directory=GatewayChannelDirectoryStore(state_path),
            ).send(
                platform=str(deliver_config.get("platform") or "local"),
                target=str(deliver_config.get("target") or ""),
                thread_id=deliver_config.get("thread_id"),
                message=str(data.get("prompt") or ""),
            )
            data["direct_delivery"] = routed
        return {"success": True, "data": data, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="webhook")


def _invalid_financial_params(action: str, detail: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "configured": False,
            "action": action,
            "detail": detail,
        },
        "error": detail,
        "error_code": "FINANCIAL_MANAGER_INVALID_PARAMS",
    }


def _financial_scope_blocked(action: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "target_tool": "financial_manager",
            "target_action": action,
            "params": dict(params or {}),
            "detail": "Financial Manager confirmed execution is restricted to the allowlisted Desktop scope.",
        },
        "error": "financial manager confirmed execution is outside the allowlisted scope",
        "error_code": "FINANCIAL_MANAGER_EXECUTOR_SCOPE_BLOCKED",
    }


def _financial_dry_run_required(action: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": False,
        "data": {
            "target_tool": "financial_manager",
            "target_action": action,
            "params": dict(params or {}),
            "detail": "This Financial Manager confirmed action is limited to dry-run execution.",
        },
        "error": "financial manager confirmed action requires dry_run=true",
        "error_code": "FINANCIAL_MANAGER_DRY_RUN_REQUIRED",
    }


def _financial_manager_capture() -> type:
    class _CaptureMcp:
        def __init__(self) -> None:
            self.tools: dict[str, Callable[..., Any]] = {}

        def tool(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                fn = args[0]
                self.tools[fn.__name__] = fn
                return fn

            def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                self.tools[fn.__name__] = fn
                return fn

            return _decorator

    return _CaptureMcp


def _load_manager_callable(
    *,
    module_name: str,
    register_name: str,
    tool_name: str,
) -> Callable[..., Any]:
    _ensure_monorepo_paths()
    module = __import__(module_name, fromlist=[register_name])
    register = getattr(module, register_name)
    capture = _financial_manager_capture()()
    register(capture)
    fn = capture.tools.get(tool_name)
    if not callable(fn):
        raise RuntimeError(f"{tool_name} was not registered from {module_name}")
    return fn


def _normalize_financial_payload(action: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = dict(params or {})
    dry_run = bool(payload.get("dry_run", False))
    if action in {"execution_manager.create_plan", "paper_trading_manager.submit_order"} and not dry_run:
        raise ValueError("FINANCIAL_MANAGER_DRY_RUN_REQUIRED")
    if action == "watchlist_manager.add":
        group = payload.get("group") or payload.get("group_id")
        if group:
            payload["group_id"] = str(group)
        if not str(payload.get("code") or "").strip():
            raise KeyError("code")
    elif action == "watchlist_manager.remove":
        group = payload.get("group") or payload.get("group_id")
        if group:
            payload["group_id"] = str(group)
        if not str(payload.get("code") or "").strip():
            raise KeyError("code")
    elif action == "portfolio_manager.create":
        if not str(payload.get("name") or "").strip():
            raise KeyError("name")
    elif action == "portfolio_manager.add_holding":
        if payload.get("shares") is None:
            candidate = payload.get("quantity")
            if candidate is not None:
                payload["shares"] = candidate
        if payload.get("cost_price") is None and payload.get("price") is not None:
            payload["cost_price"] = payload.get("price")
        for required in ("portfolio_id", "code", "shares"):
            if payload.get(required) in {None, ""}:
                raise KeyError(required)
    elif action == "execution_manager.create_plan":
        algorithm = str(payload.get("algorithm") or "twap").strip().lower()
        if algorithm not in {"twap", "vwap"}:
            raise ValueError("algorithm")
        quantity = payload.get("total_quantity", payload.get("quantity", payload.get("total_shares")))
        duration = payload.get("duration_minutes", payload.get("duration", 60))
        if quantity in {None, ""}:
            raise KeyError("quantity")
        if not str(payload.get("code") or "").strip():
            raise KeyError("code")
        payload["algorithm"] = algorithm
        payload["total_quantity"] = quantity
        payload["total_shares"] = quantity
        payload["duration_minutes"] = duration
        payload["duration"] = duration
        payload["dry_run"] = True
    elif action == "paper_trading_manager.submit_order":
        quantity = payload.get("quantity", payload.get("shares"))
        if quantity in {None, ""}:
            raise KeyError("quantity")
        if not str(payload.get("code") or "").strip():
            raise KeyError("code")
        payload["quantity"] = quantity
        payload["shares"] = quantity
        payload["dry_run"] = True
    return payload


async def _execute_financial_manager(action: str, params: dict[str, Any]) -> dict[str, Any]:
    allowlisted = {
        "watchlist_manager.add",
        "watchlist_manager.remove",
        "portfolio_manager.create",
        "portfolio_manager.add_holding",
        "execution_manager.create_plan",
        "paper_trading_manager.submit_order",
    }
    if action not in allowlisted:
        return _financial_scope_blocked(action, params)

    try:
        payload = _normalize_financial_payload(action, params)
    except KeyError as exc:
        return _invalid_financial_params(action, f"missing required parameter: {exc.args[0]}")
    except ValueError as exc:
        if str(exc) == "FINANCIAL_MANAGER_DRY_RUN_REQUIRED":
            return _financial_dry_run_required(action, params)
        if str(exc) == "algorithm":
            return _invalid_financial_params(action, "algorithm must be twap or vwap")
        return _invalid_financial_params(action, str(exc))

    if action == "paper_trading_manager.submit_order":
        preview = {
            "preview_id": f"paper_preview_{int(time.time() * 1000)}",
            "status": "dry_run_preview",
            "dry_run": True,
            "manager": "paper_trading_manager",
            "action": "place_order",
            "code": str(payload.get("code") or ""),
            "side": str(payload.get("side") or payload.get("direction") or "buy"),
            "quantity": bounded_int(payload.get("quantity") or payload.get("shares"), default=0, minimum=0),
            "order_type": str(payload.get("order_type") or "market"),
            "account_id": payload.get("account_id"),
            "user_id": payload.get("user_id"),
            "note": "Financial Manager Desktop keeps paper order confirmed execution in dry-run preview mode only.",
        }
        return {"success": True, "data": preview, "error": None}

    try:
        if action.startswith("watchlist_manager."):
            fn = _load_manager_callable(
                module_name="akshare_mcp.tools.managers.watchlist_manager",
                register_name="register_watchlist_manager",
                tool_name="watchlist_manager",
            )
            manager_action = "add" if action.endswith(".add") else "remove"
            return await _maybe_await(fn(action=manager_action, params=payload))
        if action.startswith("portfolio_manager."):
            fn = _load_manager_callable(
                module_name="akshare_mcp.tools.managers.portfolio_manager",
                register_name="register_portfolio_manager",
                tool_name="portfolio_manager",
            )
            manager_action = action.split(".", 1)[1]
            return await _maybe_await(fn(action=manager_action, params=payload))
        if action == "execution_manager.create_plan":
            fn = _load_manager_callable(
                module_name="akshare_mcp.tools.managers.execution_manager",
                register_name="register_execution_manager",
                tool_name="execution_manager",
            )
            return await _maybe_await(
                fn(
                    action=str(payload.get("algorithm") or "twap"),
                    params=payload,
                    dry_run=True,
                )
            )
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="financial_manager")
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="financial_manager")

    return _financial_scope_blocked(action, params)




def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "ops" / "db_soak.py").exists():
            return parent
    return Path(__file__).resolve().parents[4]


def _load_db_soak_module():
    """Load scripts/ops/db_soak.py without installing scripts as a package."""
    import importlib.util
    import sys

    path = _repo_root() / "scripts" / "ops" / "db_soak.py"
    if not path.exists():
        raise ModuleNotFoundError(f"db_soak harness missing: {path}")
    mod_name = "aiask_ops_db_soak"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(f"cannot load db_soak from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


async def _execute_ops(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """P2 ops intents: read-only soak check (product path for scripts/ops/db_soak.py)."""
    normalized = str(action or "").strip()
    if normalized not in {"db_soak", "soak_check"}:
        return {
            "success": False,
            "data": {"action": normalized},
            "error": f"unsupported ops action: {normalized}",
            "error_code": "UNSUPPORTED_OPS_ACTION",
        }
    try:
        soak = _load_db_soak_module()
        # Always product-safe defaults: single sample unless params override (capped).
        payload = dict(params or {})
        if payload.get("duration_min") is None:
            payload["duration_min"] = 0.0
        result = await asyncio.to_thread(soak.run_soak_from_params, payload)
        if isinstance(result, dict):
            return result
        return {"success": True, "data": result, "error": None}
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="ops_db_soak")
    except Exception as exc:
        return _execution_failed(exc, action=normalized, dependency="ops_db_soak")


async def execute_confirmed_action(
    target_tool: str,
    action: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_tool = str(target_tool or "").strip()
    normalized_action = str(action or "").strip()
    payload = dict(params or {})
    if normalized_tool == "strategy_manager":
        from .strategy_factory import execute_confirmed_action as execute_strategy_action

        return await execute_strategy_action(normalized_action, payload)
    if normalized_tool == "data_sync":
        return await _execute_data_sync(normalized_action, payload)
    if normalized_tool == "factor_factory":
        return await _execute_factor_factory(normalized_action, payload)
    if normalized_tool == "incubation_factory":
        return await _execute_incubation_factory(normalized_action, payload)
    if normalized_tool == "stock_radar":
        return await _execute_stock_radar(normalized_action, payload)
    if normalized_tool == "gateway":
        return await _execute_gateway(normalized_action, payload)
    if normalized_tool == "webhook":
        return await _execute_webhook(normalized_action, payload)
    if normalized_tool == "financial_manager":
        return await _execute_financial_manager(normalized_action, payload)
    if normalized_tool == "ops":
        return await _execute_ops(normalized_action, payload)
    return {
        "success": False,
        "data": {
            "target_tool": normalized_tool,
            "target_action": normalized_action,
            "detail": "No confirmed-action executor is registered for this target.",
        },
        "error": f"unsupported confirmed action target: {normalized_tool}",
        "error_code": "UNSUPPORTED_INTENT_TARGET",
    }
