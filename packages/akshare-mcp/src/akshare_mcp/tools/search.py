"""搜索工具"""

from typing import Optional
from ..storage import get_db
from ..utils import ok, fail, normalize_code
from ..data_source import data_source


def _search_stocks_tushare_fallback(keyword: str, limit: int) -> list:
    """DB 无数据时用 Tushare Pro 股票列表按名称/代码筛选"""
    pro = data_source.get_tushare_pro()
    if not pro:
        return []
    keyword_stripped = keyword.strip()
    if not keyword_stripped:
        return []
    keyword_lower = keyword_stripped.lower()
    try:
        df = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,industry",
        )
    except Exception:
        return []
    if df is None or df.empty:
        return []
    results = []
    for _, row in df.iterrows():
        ts_code = str(row.get("ts_code", "") or "")
        symbol = str(row.get("symbol", "") or "")
        name = str(row.get("name", "") or "")
        industry = str(row.get("industry", "") or "")
        if (
            keyword_lower in ts_code.lower()
            or keyword_lower in symbol.lower()
            or keyword_lower in name
        ):
            results.append({
                "code": normalize_code(symbol) if symbol else ts_code,
                "name": name,
                "industry": industry or None,
                "market_cap": None,
            })
            if len(results) >= limit:
                break
    return results


def _iter_registered_tools(mcp):
    """获取已注册的工具列表 - 兼容 FastMCP"""
    # FastMCP 使用 _tool_manager._tools 存储工具
    tool_manager = getattr(mcp, '_tool_manager', None)
    if tool_manager:
        tools_dict = getattr(tool_manager, '_tools', None)
        if isinstance(tools_dict, dict):
            return list(tools_dict.items())
    
    # 兜底：返回空列表
    return []


def register(mcp):
    """注册搜索工具"""
    
    @mcp.tool()
    async def search_stocks(
        keyword: str,
        limit: int = 20
    ):
        """
        搜索股票
        
        Args:
            keyword: 关键词（代码或名称，支持中文）
            limit: 返回数量
        """
        try:
            db = get_db()
            results = []
            
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT stock_code, stock_name, industry, market_cap
                       FROM stocks
                       WHERE stock_code LIKE $1 OR stock_name LIKE $2
                       ORDER BY market_cap DESC NULLS LAST
                       LIMIT $3""",
                    f'%{keyword}%', f'%{keyword}%', limit
                )
                results = [
                    {
                        'code': row['stock_code'],
                        'name': row['stock_name'],
                        'industry': row['industry'],
                        'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                    }
                    for row in rows
                ]
            
            if not results:
                results = _search_stocks_tushare_fallback(keyword, limit)
            
            return ok({
                'keyword': keyword,
                'results': results,
                'count': len(results),
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    def available_tools():
        """获取所有可用工具列表"""
        tools = []
        for name, tool in _iter_registered_tools(mcp):
            if not name:
                continue
            # FastMCP Tool 对象有 description 属性
            desc = getattr(tool, "description", None)
            if not desc:
                # 兜底：尝试从原始函数获取
                fn = getattr(tool, "fn", None)
                if fn:
                    desc = getattr(fn, "__doc__", None)
            
            tools.append({
                'name': str(name),
                'category': getattr(tool, "category", None),
                'description': desc.strip() if isinstance(desc, str) else None,
            })
        tools.sort(key=lambda x: x.get('name', ''))

        return ok({'tools': tools, 'count': len(tools)})

    @mcp.tool()
    def get_available_categories():
        """获取工具分类"""
        categories = [
            {'name': 'market', 'description': '市场数据'},
            {'name': 'finance', 'description': '财务数据'},
            {'name': 'technical', 'description': '技术分析'},
            {'name': 'valuation', 'description': '估值分析'},
            {'name': 'backtest', 'description': '回测'},
            {'name': 'portfolio', 'description': '组合管理'},
            {'name': 'decision', 'description': '决策支持'},
        ]
        
        return ok({'categories': categories})
