"""
AKShare MCP Server
提供A股实时行情、K线、财务数据、北向资金等数据服务

Real-only 原则：
- 不返回任何模拟/占位数据；缺数据/异常直接返回 success=false
- 所有工具统一返回结构：{success, data, error, source, cached, timestamp}
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import (
    market,
    finance,
    fund_flow,
    macro,
    news,
    options,
)
mcp = FastMCP("AKShare Stock Data Server")



# 注册工具
market.register(mcp)
finance.register(mcp)
fund_flow.register(mcp)
macro.register(mcp)
news.register(mcp)
options.register(mcp)


def main() -> None:
    """启动 MCP Server"""
    mcp.run()


if __name__ == "__main__":
    main()
