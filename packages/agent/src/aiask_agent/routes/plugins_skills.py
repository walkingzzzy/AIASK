from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request


FullToolCall = Callable[[Request, str, dict[str, Any]], Awaitable[dict[str, Any]]]


def create_plugins_skills_router(
    *,
    require_full: Callable[[Request], Any],
    full_tool_call: FullToolCall,
    build_full_runtime: Callable[[], Any],
    plugin_manager_factory: Callable[[], Any],
    plugin_self_test_payload: Callable[[dict[str, Any], str], dict[str, Any]],
    plugin_tools: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/skills")
    async def skills(request: Request) -> dict[str, Any]:
        require_full(request)
        result = await build_full_runtime().tool_registry.call_tool("agent_skill_manage", {"action": "snapshot"})
        return {"object": "list", "data": dict(result.get("data") or {})}

    @router.post("/v1/skills")
    async def skill_create(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_skill_manage", {"action": "install", **dict(payload or {})})

    @router.patch("/v1/skills/{name}")
    async def skill_update(request: Request, name: str) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_skill_manage", {"action": "update", "name": name, **dict(payload or {})})

    @router.delete("/v1/skills/{name}")
    async def skill_delete(request: Request, name: str) -> dict[str, Any]:
        return await full_tool_call(request, "agent_skill_manage", {"action": "uninstall", "name": name})

    @router.get("/v1/plugins")
    async def plugins(request: Request) -> dict[str, Any]:
        require_full(request)
        return {"object": "list", "data": plugin_manager_factory().list()}

    @router.post("/v1/plugins")
    async def plugin_upsert(request: Request) -> dict[str, Any]:
        payload = await request.json()
        return await full_tool_call(request, "agent_plugin_manage", {"action": "upsert", **dict(payload or {})})

    @router.patch("/v1/plugins/{name}")
    async def plugin_toggle(request: Request, name: str) -> dict[str, Any]:
        payload = dict(await request.json() or {})
        action = "enable" if bool(payload.get("enabled", True)) else "disable"
        return await full_tool_call(request, "agent_plugin_manage", {"action": action, "name": name, **payload})

    @router.post("/v1/plugins/{name}/tools/{tool}/test")
    async def plugin_tool_test(request: Request, name: str, tool: str) -> dict[str, Any]:
        require_full(request)
        manager = plugin_manager_factory()
        plugin = manager.get(name)
        if not plugin:
            raise HTTPException(404, detail=f"plugin not found: {name}")
        if str(tool or "").strip().lower() in {"", "__manifest__", "manifest", "self-test", "self_test"}:
            return plugin_self_test_payload(plugin, name)
        plugin_name = str(plugin.get("name") or name).replace("-", "_")
        wrapped = f"agent_plugin_{plugin_name}_{str(tool).replace('-', '_')}"
        payload = dict(await request.json() or {})
        try:
            return {"object": "plugin.tool_test", "success": True, "data": await manager.call_tool(wrapped, payload), "error": None}
        except ValueError as exc:
            return {
                "object": "plugin.tool_test",
                "success": False,
                "data": {
                    "plugin": str(plugin.get("name") or name),
                    "tool": tool,
                    "available_tools": [str(item.get("name") or "") for item in plugin_tools(plugin)],
                    "configured": False,
                },
                "error": str(exc),
                "error_code": "PLUGIN_TOOL_NOT_CONFIGURED",
            }

    @router.get("/v1/plugins/{name}/commands")
    async def plugin_commands(request: Request, name: str) -> dict[str, Any]:
        require_full(request)
        manager = plugin_manager_factory()
        if not manager.get(name):
            raise HTTPException(404, detail=f"plugin not found: {name}")
        return {"object": "list", "data": manager.list_commands(name)}

    @router.post("/v1/plugins/{name}/commands/{command}/test")
    async def plugin_command_test(request: Request, name: str, command: str) -> dict[str, Any]:
        require_full(request)
        payload = dict(await request.json() or {})
        try:
            return {"object": "plugin.command_test", "success": True, "data": await plugin_manager_factory().call_command(name, command, payload), "error": None}
        except ValueError as exc:
            return {
                "object": "plugin.command_test",
                "success": False,
                "data": {"plugin": name, "command": command, "configured": False},
                "error": str(exc),
                "error_code": "PLUGIN_COMMAND_NOT_CONFIGURED",
            }

    return router
