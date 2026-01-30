"""
AKShare MCP Server v2
提供完整的A股量化分析服务
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import (
    market, finance, fund_flow, macro, news, options,
    technical, backtest, portfolio, valuation, decision,
    search, semantic, data_warmup, alerts,
    vector, skills, quant, sentiment, market_blocks,
)
from .tools import managers_complete as managers
from .tools import managers_extended

mcp = FastMCP("AKShare Stock Data Server v2")

market.register(mcp)
finance.register(mcp)
fund_flow.register(mcp)
macro.register(mcp)
news.register(mcp)
options.register(mcp)
technical.register(mcp)
backtest.register(mcp)
portfolio.register(mcp)
valuation.register(mcp)
decision.register(mcp)
search.register(mcp)
semantic.register(mcp)
data_warmup.register(mcp)
alerts.register(mcp)
managers.register(mcp)
managers_extended.register(mcp)  # 注册扩展的19个managers
vector.register(mcp)
skills.register(mcp)
quant.register(mcp)
sentiment.register(mcp)

# 注册市场板块工具
mcp.tool()(market_blocks.get_market_blocks)
mcp.tool()(market_blocks.get_block_stocks)


def main() -> None:
    """启动 MCP Server"""
    mcp.run()


if __name__ == "__main__":
    main()
