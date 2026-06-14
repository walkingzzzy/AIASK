from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request


FullToolCall = Callable[[Request, str, dict[str, Any]], Awaitable[dict[str, Any]]]


def create_mcp_router(
    *,
    require_api: Callable[[Request], Any],
    require_full: Callable[[Request], Any],
    full_tool_call: FullToolCall,
    mcp_aggregator_factory: Callable[[], Any],
    refresh_mcp_runtime: Callable[[], None],
    classify_mcp_error: Callable[[BaseException], tuple[str, str]],
    mcp_action_error_payload: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/mcp/servers")
    async def mcp_servers(request: Request, all: bool = False) -> dict[str, Any]:
        require_api(request)
        return {"object": "list", "data": mcp_aggregator_factory().servers_summary(include_all=all)}

    @router.get("/v1/mcp/tools")
    async def mcp_tools(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": mcp_aggregator_factory().tools_summary(include_all=all)}

    @router.get("/v1/mcp/resources")
    async def mcp_resources(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": mcp_aggregator_factory().resources_summary(include_all=all)}

    @router.get("/v1/mcp/prompts")
    async def mcp_prompts(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": mcp_aggregator_factory().prompts_summary(include_all=all)}

    @router.get("/v1/mcp/oauth_status")
    async def mcp_oauth_status(request: Request, all: bool = False) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": mcp_aggregator_factory().oauth_status(include_all=all)}

    @router.post("/v1/mcp/register-local")
    async def mcp_register_local(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        data = mcp_aggregator_factory().register_local_server(
            name=payload.get("name"),
            url=payload.get("url"),
            transport=payload.get("transport"),
            domain=payload.get("domain"),
        )
        refresh_mcp_runtime()
        return {"object": "mcp.registration", "success": True, "data": data}

    @router.post("/v1/mcp/discover")
    async def mcp_discover(request: Request) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        server_name = str(payload.get("server") or "").strip()
        if not server_name:
            raise HTTPException(400, detail="server is required")
        try:
            data = await mcp_aggregator_factory().discover_and_update(server_name)
            refresh_mcp_runtime()
            return {"object": "mcp.discovery", "success": True, "data": data}
        except Exception as exc:
            error_code, detail = classify_mcp_error(exc)
            auth: dict[str, Any] = {}
            try:
                auth = mcp_aggregator_factory().auth_readiness(server_name)
            except Exception:
                auth = {}
            discovery_status = "auth_missing" if error_code == "MCP_DISCOVERY_AUTH_REQUIRED" else "discovery_failed"
            return {
                "object": "mcp.discovery",
                "success": False,
                "data": {"server": server_name, "configured": False, "discovery_status": discovery_status, "detail": detail, **auth},
                "error": detail,
                "error_code": error_code,
            }

    @router.post("/v1/mcp/oauth/start")
    async def mcp_oauth_start(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        require_full(request)
        return {"object": "mcp.oauth_start", "data": mcp_aggregator_factory().oauth_start(str(payload.get("server") or ""))}

    @router.post("/v1/mcp/oauth/callback")
    async def mcp_oauth_callback(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        result = await full_tool_call(request, "agent_mcp_manage", {"action": "oauth_callback", **payload})
        return {"object": "mcp.oauth_callback", "data": result.get("data")}

    @router.post("/v1/mcp/resources/read")
    async def mcp_resource_read(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        require_full(request)
        server_name = str(payload.get("server") or "")
        try:
            return {
                "object": "mcp.resource",
                "success": True,
                "data": await mcp_aggregator_factory().read_resource(server_name, str(payload.get("uri") or "")),
                "error": None,
            }
        except Exception as exc:
            return mcp_action_error_payload(action="resource", server_name=server_name, exc=exc)

    @router.post("/v1/mcp/prompts/get")
    async def mcp_prompt_get(request: Request) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        require_full(request)
        server_name = str(payload.get("server") or "")
        try:
            return {
                "object": "mcp.prompt",
                "success": True,
                "data": await mcp_aggregator_factory().get_prompt(
                    server_name,
                    str(payload.get("prompt") or payload.get("name") or ""),
                    dict(payload.get("arguments") or {}),
                ),
                "error": None,
            }
        except Exception as exc:
            return mcp_action_error_payload(action="prompt", server_name=server_name, exc=exc)

    return router
