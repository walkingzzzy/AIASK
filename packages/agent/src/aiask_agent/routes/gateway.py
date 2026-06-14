from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request


def create_gateway_router(
    *,
    require_api: Callable[[Request], Any],
    require_full: Callable[[Request], Any],
    gateway_runtime_factory: Callable[[], Any],
    message_store_factory: Callable[[], Any],
    directory_store_factory: Callable[[], Any],
    config_store_factory: Callable[[], Any],
    delivery_router_factory: Callable[..., Any],
    adapter_for: Callable[[Any], Any],
    normalize_platform: Callable[[str | None], str],
    gateway_daemon_status_payload: Callable[[], dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/gateway/status")
    async def gateway_status_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return gateway_runtime_factory().status()

    @router.get("/v1/gateway/platforms")
    async def gateway_platforms_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": gateway_runtime_factory().list_platforms()}

    @router.get("/v1/gateway/messages")
    async def gateway_messages_api(request: Request, platform: str | None = None, limit: int = 100) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": message_store_factory().list(platform=platform, limit=limit)}

    @router.get("/v1/gateway/directory")
    async def gateway_directory_api(request: Request, platform: str | None = None, kind: str | None = None, limit: int = 200) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": directory_store_factory().list(platform=platform, kind=kind, limit=limit)}

    @router.post("/v1/gateway/directory/refresh")
    async def gateway_directory_refresh_api(request: Request) -> dict[str, Any]:
        require_full(request)
        data = directory_store_factory().refresh(config=config_store_factory())
        return {"object": "gateway.directory_refresh", "data": data}

    @router.post("/v1/gateway/send")
    async def gateway_send_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        data = await delivery_router_factory(messages=message_store_factory(), directory=directory_store_factory()).send(
            platform=str(payload.get("platform") or "local"),
            target=str(payload.get("target") or ""),
            message=str(payload.get("message") or ""),
            thread_id=payload.get("thread_id"),
            session_id=payload.get("session_id"),
            user_id=payload.get("user_id"),
            media_paths=[str(item) for item in list(payload.get("media_paths") or [])],
        )
        return {"object": "gateway.message", "data": data}

    @router.post("/v1/gateway/direct-deliver")
    async def gateway_direct_deliver_api(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        data = await delivery_router_factory(messages=message_store_factory(), directory=directory_store_factory()).send(
            platform=str(payload.get("platform") or "local"),
            target=str(payload.get("target") or ""),
            message=str(payload.get("message") or ""),
            thread_id=payload.get("thread_id"),
            session_id=payload.get("session_id"),
            user_id=payload.get("user_id"),
            media_paths=[str(item) for item in list(payload.get("media_paths") or [])],
        )
        data["deliver_mode"] = "direct_platform"
        return {"object": "gateway.direct_delivery", "data": data}

    @router.post("/v1/gateway/messages/{message_id}/retry")
    async def gateway_retry_api(request: Request, message_id: str) -> dict[str, Any]:
        require_full(request)
        data = await delivery_router_factory(messages=message_store_factory(), directory=directory_store_factory()).retry(message_id)
        return {"object": "gateway.retry", "data": data}

    @router.post("/v1/gateway/platforms/{platform}/start")
    async def gateway_platform_start_api(request: Request, platform: str) -> dict[str, Any]:
        require_full(request)
        status = config_store_factory().platform_status(normalize_platform(platform))
        return {"object": "gateway.platform", "data": await adapter_for(status).start()}

    @router.post("/v1/gateway/platforms/{platform}/stop")
    async def gateway_platform_stop_api(request: Request, platform: str) -> dict[str, Any]:
        require_full(request)
        status = config_store_factory().platform_status(normalize_platform(platform))
        return {"object": "gateway.platform", "data": await adapter_for(status).stop()}

    @router.get("/v1/gateway/platforms/{platform}/health")
    async def gateway_platform_health_api(request: Request, platform: str) -> dict[str, Any]:
        require_full(request)
        status = config_store_factory().platform_status(normalize_platform(platform))
        data = await adapter_for(status).health()
        data["runtime"] = gateway_runtime_factory().runtime_status()
        recent = message_store_factory().list(platform=platform, limit=20)
        data["last_inbound"] = next((item for item in recent if item.get("direction") == "inbound"), None)
        data["last_outbound"] = next((item for item in recent if item.get("direction") == "outbound"), None)
        return {"object": "gateway.platform_health", "data": data}

    @router.post("/v1/gateway/webhooks/{platform}")
    async def gateway_webhook_api(request: Request, platform: str) -> dict[str, Any]:
        require_api(request)
        raw_body = await request.body()
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        if not isinstance(payload, dict):
            raise HTTPException(400, detail="webhook payload must be a JSON object")
        signature = request.headers.get("X-AIASK-Gateway-Signature") or request.headers.get("X-Hub-Signature-256")
        status = config_store_factory().platform_status(normalize_platform(platform))
        adapter_result = await adapter_for(status).handle_inbound(payload=payload, headers=dict(request.headers), body=raw_body)
        item = delivery_router_factory(messages=message_store_factory()).record_inbound(
            platform=platform,
            payload=dict(adapter_result.get("payload") or payload),
            signature=signature,
            verified=bool(adapter_result.get("verified")),
            adapter_result=adapter_result,
        )
        return {"object": "gateway.inbound", "data": item}

    @router.get("/v1/gateway/daemon/status")
    async def gateway_daemon_status_api(request: Request) -> dict[str, Any]:
        require_full(request)
        return gateway_daemon_status_payload()

    return router
