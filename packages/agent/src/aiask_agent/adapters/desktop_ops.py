from __future__ import annotations

import asyncio
import inspect
import time
import sys
from pathlib import Path
from typing import Any, Callable


def _ensure_monorepo_paths() -> None:
    for parent in Path(__file__).resolve().parents:
        candidates = [
            parent / "akshare-mcp" / "src",
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
            gateway.get_active_factors(limit=max(1, min(int(limit or 50), 200))),
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
            timeout=float(params.get("_timeout_seconds") or 120),
        )
        return result if isinstance(result, dict) else {"success": True, "data": result, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="data_sync")


async def _execute_factor_factory(action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        _ensure_monorepo_paths()
        from akshare_mcp.services.factor_mining_factory import get_factor_mining_factory
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="factor_factory")

    try:
        factory = get_factor_mining_factory()
        timeout = float(params.get("_timeout_seconds") or 300)
        if action == "run_once":
            result = await asyncio.wait_for(
                factory.run_mining_cycle(
                    trigger=str(params.get("trigger") or "desktop_intent"),
                    engines=[str(item) for item in list(params.get("engines") or [])] or None,
                    candidate_count=int(params.get("candidate_count") or params.get("candidates") or 10),
                    evolution_generations=int(params.get("evolution_generations") or params.get("generations") or 2),
                    codes=[str(item) for item in list(params.get("codes") or [])] or None,
                ),
                timeout=timeout,
            )
        elif action == "maintenance":
            result = await asyncio.wait_for(factory.run_maintenance(), timeout=timeout)
        else:
            raise ValueError(f"unsupported factor factory action: {action}")
        return {"success": bool(not isinstance(result, dict) or result.get("success") is not False), "data": result, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="factor_factory")


async def _execute_incubation_factory(action: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        _ensure_monorepo_paths()
        from akshare_mcp.services.incubation_factory import (
            IncubationFactoryRunner,
            get_incubation_factory_runner,
        )
    except ModuleNotFoundError as exc:
        return _dependency_missing(exc, dependency="incubation_factory")

    try:
        timeout = float(params.get("_timeout_seconds") or 600)
        if action == "dry_run":
            runner = IncubationFactoryRunner(dry_run=True)
            result = await asyncio.wait_for(runner.run_once(), timeout=timeout)
        elif action == "run_once":
            result = await asyncio.wait_for(get_incubation_factory_runner().run_once(), timeout=timeout)
        elif action == "maintenance":
            runner = get_incubation_factory_runner()
            result = {
                "status": "ready",
                "detail": "Incubation factory has no separate maintenance pass; status was refreshed.",
                "runner": runner.status(),
            }
        else:
            raise ValueError(f"unsupported incubation factory action: {action}")
        return {"success": bool(not isinstance(result, dict) or result.get("success") is not False), "data": result, "error": None}
    except Exception as exc:
        return _execution_failed(exc, action=action, dependency="incubation_factory")


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
            "quantity": int(payload.get("quantity") or payload.get("shares") or 0),
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
    if normalized_tool == "gateway":
        return await _execute_gateway(normalized_action, payload)
    if normalized_tool == "webhook":
        return await _execute_webhook(normalized_action, payload)
    if normalized_tool == "financial_manager":
        return await _execute_financial_manager(normalized_action, payload)
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
