"""向量搜索工具 - 基于特征相似度的实现"""

from ._vector_search_kline import search_by_kline
from ._vector_search_semantic import semantic_stock_search
from ._vector_search_similar import search_similar_stocks


def register(mcp):
    """注册向量搜索工具"""
    mcp.tool()(search_similar_stocks)
    mcp.tool()(search_by_kline)
    mcp.tool()(semantic_stock_search)
