"""决策工具"""

from ._decision_buy import should_i_buy
from ._decision_common import get_investment_analysis
from ._decision_context import build_event_context, build_quant_context, build_stock_context
from ._decision_sell import should_i_sell
from ._decision_unified import (
    fuse_decision_payload,
    get_unified_decision,
    get_unified_decision_details,
    get_unified_decision_summary,
    run_decision_gate,
)


def register(mcp):
    """注册决策工具"""
    mcp.tool()(should_i_buy)
    mcp.tool()(should_i_sell)
    mcp.tool()(build_stock_context)
    mcp.tool()(build_quant_context)
    mcp.tool()(build_event_context)
    mcp.tool()(run_decision_gate)
    mcp.tool()(fuse_decision_payload)
    mcp.tool()(get_unified_decision_summary)
    mcp.tool()(get_unified_decision_details)
    mcp.tool()(get_unified_decision)
    mcp.tool()(get_investment_analysis)
