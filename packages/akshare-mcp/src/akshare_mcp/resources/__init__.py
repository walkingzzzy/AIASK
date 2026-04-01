"""MCP resource registrations for high-value read-only objects."""

from __future__ import annotations

from .stock_and_watchlist import register as register_stock_and_watchlist_resources
from .strategy import register as register_strategy_resources


def register(mcp) -> None:
    """Register concrete MCP resources."""

    @mcp.resource(
        "resource://server/capabilities",
        name="server_capabilities",
        title="Server Capabilities",
        description="Runtime MCP capabilities and implemented native objects",
        mime_type="application/json",
    )
    async def server_capabilities() -> dict:
        tool_names = sorted(getattr(mcp._tool_manager, "_tools", {}).keys())
        prompt_names = sorted(prompt.name for prompt in mcp._prompt_manager.list_prompts())
        resource_templates = sorted(
            template.uri_template for template in mcp._resource_manager.list_templates()
        )
        resource_uris = sorted(resource.uri for resource in mcp._resource_manager.list_resources())

        return {
            "server": "AKShare Stock Data Server v2",
            "tools": {
                "count": len(tool_names),
                "sample": tool_names[:24],
            },
            "resources": {
                "count": len(resource_uris),
                "uris": resource_uris,
            },
            "resource_templates": {
                "count": len(resource_templates),
                "uris": resource_templates,
            },
            "prompts": {
                "count": len(prompt_names),
                "names": prompt_names,
            },
        }

    register_stock_and_watchlist_resources(mcp)
    register_strategy_resources(mcp)
