
import asyncio
from akshare_mcp.server import mcp

async def verify():
    # FastMCP uses a decorator to register tools, they are stored in mcp._tool_manager._tools usually
    # or mcp._tools depending on version. Let's try to inspect.
    
    # In newer FastMCP, tools might be in mcp.tools or similar.
    # Let's inspect the object.
    
    print(f"MCP Name: {mcp.name}")
    
    # Check for _tools or tools
    if hasattr(mcp, '_tools'):
        tools = mcp._tools
    elif hasattr(mcp, 'tools'):
        tools = mcp.tools
    elif hasattr(mcp, '_tool_manager'):
        tools = mcp._tool_manager._tools
    else:
        # Fallback for some versions
        tools = {}
        print("Could not find tools dict directly.")

    print(f"Total tools registered: {len(tools)}")
    
    print("Sample tools:")
    count = 0
    for name in tools:
        print(f" - {name}")
        count += 1
        if count >= 10:
            break
            
    # Check specific tools
    target_tools = ['get_stock_list', 'get_realtime_quote', 'portfolio_manager', 'alerts_manager']
    for t in target_tools:
        if t in tools:
            print(f"Found tool: {t}")
        else:
            print(f"MISSING tool: {t}")

if __name__ == "__main__":
    asyncio.run(verify())
