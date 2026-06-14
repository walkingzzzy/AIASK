from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request


FullToolCall = Callable[[Request, str, dict[str, Any]], Awaitable[dict[str, Any]]]


def create_webhooks_router(
    *,
    require_full: Callable[[Request], Any],
    full_tool_call: FullToolCall,
    webhook_store_factory: Callable[[], Any],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/webhooks")
    async def webhooks(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": webhook_store_factory().list()}

    @router.post("/v1/webhooks")
    async def webhook_subscribe(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_webhook", {"action": "subscribe", **dict(payload or {})})

    @router.delete("/v1/webhooks/{webhook_id}")
    async def webhook_delete(request: Request, webhook_id: str) -> dict[str, Any]:
        return await full_tool_call(request, "agent_webhook", {"action": "remove", "webhook_id": webhook_id})

    @router.post("/v1/webhooks/{webhook_id}/trigger")
    async def webhook_trigger(request: Request, webhook_id: str) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_webhook", {"action": "trigger", "webhook_id": webhook_id, **dict(payload or {})})

    return router
