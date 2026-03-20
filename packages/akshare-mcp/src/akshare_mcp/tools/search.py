"""搜索工具"""

from typing import Optional
from ..storage import get_db
from ..utils import ok, fail, normalize_code
from ..data_source import data_source


_CATEGORY_DESCRIPTIONS = {
    "alerts": "预警与告警",
    "backtest": "回测与策略验证",
    "basic_data": "基础资料与静态数据",
    "compliance": "合规校验",
    "data_sync": "数据同步与预热",
    "decision": "投资决策与建议",
    "execution": "执行规划与拆单",
    "factor": "因子与量化研究",
    "finance": "财务与估值数据",
    "fund_flow": "资金流与席位资金",
    "industry_chain": "产业链与主题关联",
    "macro": "宏观与市场环境",
    "market": "行情、K线与盘口",
    "news": "新闻、公告与研报",
    "options": "期权与衍生品",
    "paper_trading": "模拟交易",
    "performance": "绩效与归因",
    "portfolio": "组合与持仓管理",
    "quant": "技术分析与量化工具",
    "research": "研究与洞察",
    "risk": "风险分析与压力测试",
    "screening": "选股与筛选",
    "search": "搜索与工具发现",
    "sector": "板块与行业分析",
    "semantic": "语义分析与日报",
    "sentiment": "情绪与舆情",
    "skills": "内置技能编排",
    "strategy": "策略工厂与策略超市",
    "technical": "技术指标与形态",
    "user": "用户画像与偏好",
    "vector": "向量检索与相似度分析",
    "watchlist": "自选股与分组",
}

_MODULE_CATEGORY_PREFIXES = (
    ("akshare_mcp.tools.market.", "market"),
    ("akshare_mcp.tools.news.", "news"),
    ("akshare_mcp.tools.semantic.", "semantic"),
)

_MODULE_CATEGORY_MAP = {
    "akshare_mcp.tools.alerts": "alerts",
    "akshare_mcp.tools.backtest": "backtest",
    "akshare_mcp.tools.basic_data": "basic_data",
    "akshare_mcp.tools.data_sync": "data_sync",
    "akshare_mcp.tools.data_warmup": "data_sync",
    "akshare_mcp.tools.decision": "decision",
    "akshare_mcp.tools.factor_profile": "factor",
    "akshare_mcp.tools.finance": "finance",
    "akshare_mcp.tools.fund_flow": "fund_flow",
    "akshare_mcp.tools.macro": "macro",
    "akshare_mcp.tools.market_blocks": "sector",
    "akshare_mcp.tools.options": "options",
    "akshare_mcp.tools.portfolio": "portfolio",
    "akshare_mcp.tools.quant": "quant",
    "akshare_mcp.tools.search": "search",
    "akshare_mcp.tools.sentiment": "sentiment",
    "akshare_mcp.tools.skills": "skills",
    "akshare_mcp.tools.technical": "technical",
    "akshare_mcp.tools.valuation": "finance",
    "akshare_mcp.tools.vector": "vector",
}

_MANAGER_CATEGORY_MAP = {
    "alerts_manager": "alerts",
    "backtest_manager": "backtest",
    "benchmark_manager": "backtest",
    "compliance_manager": "compliance",
    "comprehensive_manager": "research",
    "data_sync_manager": "data_sync",
    "decision_manager": "decision",
    "event_manager": "news",
    "execution_manager": "execution",
    "fundamental_analysis_manager": "finance",
    "industry_chain_manager": "industry_chain",
    "insight_manager": "research",
    "limit_up_manager": "market",
    "macro_manager": "macro",
    "market_insight_manager": "market",
    "options_manager": "options",
    "paper_trading_manager": "paper_trading",
    "performance_manager": "performance",
    "portfolio_manager": "portfolio",
    "quant_manager": "quant",
    "research_manager": "research",
    "risk_manager": "risk",
    "screener_manager": "screening",
    "sector_manager": "sector",
    "sentiment_manager": "sentiment",
    "strategy_manager": "strategy",
    "technical_analysis_manager": "technical",
    "trading_data_manager": "fund_flow",
    "user_manager": "user",
    "vector_search_manager": "vector",
    "watchlist_manager": "watchlist",
}

_TOOL_CATEGORY_MAP = {
    "available_tools": "search",
    "get_available_categories": "search",
    "get_market_blocks": "sector",
    "get_block_stocks": "sector",
    "get_block_trades": "fund_flow",
    "get_concept_fund_flow": "fund_flow",
    "get_dragon_tiger": "fund_flow",
    "get_margin_data": "risk",
    "get_margin_ranking": "risk",
    "get_north_fund": "fund_flow",
    "get_north_fund_holding": "fund_flow",
    "get_north_fund_top": "fund_flow",
    "get_sector_fund_flow": "fund_flow",
}


def _search_stocks_tushare_fallback(keyword: str, limit: int) -> list:
    """DB 无数据时用 Tushare Pro 股票列表按名称/代码/行业筛选"""
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
            or keyword_lower in industry.lower()
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


def _infer_tool_category(name: str, tool) -> str:
    explicit = getattr(tool, "category", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()

    if name in _TOOL_CATEGORY_MAP:
        return _TOOL_CATEGORY_MAP[name]

    fn = getattr(tool, "fn", None)
    module_name = str(getattr(fn, "__module__", "") or "")
    if module_name.startswith("akshare_mcp.tools.managers."):
        manager_name = module_name.rsplit(".", 1)[-1]
        if manager_name in _MANAGER_CATEGORY_MAP:
            return _MANAGER_CATEGORY_MAP[manager_name]

    for prefix, category in _MODULE_CATEGORY_PREFIXES:
        if module_name.startswith(prefix):
            return category

    mapped = _MODULE_CATEGORY_MAP.get(module_name)
    if mapped:
        return mapped

    if name.startswith("get_factor_") or name.startswith("validate_factor_") or name.startswith("backtest_factor"):
        return "factor"

    return "general"


def _category_description(category: str) -> str:
    return _CATEGORY_DESCRIPTIONS.get(category, f"{category} 工具")


def _is_hidden_tool(name: str, tool) -> bool:
    return False


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
                    """SELECT code, stock_name, industry, market_cap
                       FROM stocks
                       WHERE code LIKE $1
                          OR stock_name LIKE $2
                          OR (industry IS NOT NULL AND industry LIKE $2)
                       ORDER BY market_cap DESC NULLS LAST
                       LIMIT $3""",
                    f'%{keyword}%', f'%{keyword}%', limit
                )
                results = [
                    {
                        'code': row['code'],
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
            if _is_hidden_tool(name, tool):
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
                'category': _infer_tool_category(str(name), tool),
                'description': desc.strip() if isinstance(desc, str) else None,
            })
        tools.sort(key=lambda x: x.get('name', ''))

        return ok({'tools': tools, 'count': len(tools)})

    @mcp.tool()
    def get_available_categories():
        """获取工具分类"""
        names = sorted({
            _infer_tool_category(str(name), tool)
            for name, tool in _iter_registered_tools(mcp)
            if name and not _is_hidden_tool(name, tool)
        })
        categories = [
            {'name': name, 'description': _category_description(name)}
            for name in names
        ]
        
        return ok({'categories': categories})
