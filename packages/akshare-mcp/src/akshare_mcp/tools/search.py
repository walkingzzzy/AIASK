"""搜索工具"""

import time
from typing import Optional
from ..storage import get_db
from ..utils import normalize_code
from ..data_source import data_source
from .manager_protocol import fail_with_meta, ok_with_meta
from .tool_catalog import get_tool_contract as get_catalog_tool_contract


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
    """获取已注册的工具列表 - 兼容 FastMCP (多版本)"""
    import inspect

    # FastMCP internal _tool_manager._tools (stable across versions)
    tool_manager = getattr(mcp, '_tool_manager', None)
    if tool_manager:
        tools_dict = getattr(tool_manager, '_tools', None)
        if isinstance(tools_dict, dict):
            return list(tools_dict.items())

    # Fallback: public API mcp.list_tools() — may be sync or async
    list_tools = getattr(mcp, 'list_tools', None)
    if callable(list_tools):
        try:
            result_or_coro = list_tools()
            if inspect.isawaitable(result_or_coro):
                return []
            tools = result_or_coro
            if tools and hasattr(tools, '__iter__'):
                result = []
                for t in tools:
                    name = getattr(t, 'name', None) or str(t)
                    result.append((name, t))
                if result:
                    return result
        except Exception:
            pass

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

    def _read_only_meta(
        *,
        status: str,
        target: str,
        degraded: bool = False,
        extra_quality: dict | None = None,
    ) -> dict:
        quality = {"status": status}
        if isinstance(extra_quality, dict):
            quality.update(extra_quality)
        return {
            "quality": quality,
            "side_effect": {
                "level": "read_only",
                "target": target,
                "confirmation_required": False,
                "idempotent": True,
            },
            "degraded": degraded,
        }
    
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
        started_at = time.perf_counter()
        source_chain = ["search.search_stocks", "db.search_stocks"]
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
            
            fallback_used = False
            if not results:
                results = _search_stocks_tushare_fallback(keyword, limit)
                fallback_used = bool(results)
                if fallback_used:
                    source_chain.append("tushare_pro.stock_basic")
            
            return ok_with_meta(
                {
                    'keyword': keyword,
                    'results': results,
                    'count': len(results),
                },
                tool_name="search_stocks",
                action="query",
                started_at=started_at,
                source_chain=source_chain,
                extra_meta=_read_only_meta(
                    status="available" if results else "not_found",
                    target=keyword.strip() or "stock_search",
                    degraded=fallback_used,
                    extra_quality={
                        "result_count": len(results),
                        "fallback_used": fallback_used,
                    },
                ),
            )
        
        except Exception as e:
            return fail_with_meta(
                str(e),
                tool_name="search_stocks",
                action="query",
                started_at=started_at,
                source_chain=source_chain,
                extra_meta=_read_only_meta(
                    status="failed",
                    target=keyword.strip() or "stock_search",
                    degraded=True,
                ),
            )
    
    @mcp.tool()
    def available_tools(category: str | None = None, include_contracts: bool = True):
        """获取所有可用工具列表"""
        started_at = time.perf_counter()
        tools = []
        requested_category = str(category or "").strip().lower()
        contract_count = 0
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
            
            inferred_category = _infer_tool_category(str(name), tool)
            if requested_category and inferred_category != requested_category:
                continue
            row = {
                'name': str(name),
                'category': inferred_category,
                'description': desc.strip() if isinstance(desc, str) else None,
            }
            if include_contracts:
                contract = get_catalog_tool_contract(str(name))
                if contract is not None:
                    contract_count += 1
                    row.update(
                        {
                            "title": contract.get("title"),
                            "required_params": contract.get("required_params"),
                            "side_effect": contract.get("side_effect"),
                            "freshness": contract.get("freshness"),
                            "examples": contract.get("examples"),
                            "input_schema": contract.get("input_schema"),
                            "output_schema": contract.get("output_schema"),
                            "tags": contract.get("tags"),
                            "contract_version": contract.get("contract_version"),
                        }
                    )
            tools.append(row)
        tools.sort(key=lambda x: x.get('name', ''))

        coverage = 1.0 if not tools else round(contract_count / len(tools), 4)
        return ok_with_meta(
            {'tools': tools, 'count': len(tools), 'category': requested_category or None, 'include_contracts': bool(include_contracts)},
            tool_name="available_tools",
            action="list",
            started_at=started_at,
            source_chain=["search.available_tools", "tool_registry", "tool_catalog"],
            extra_meta=_read_only_meta(
                status="available",
                target=requested_category or "tool_registry",
                extra_quality={
                    "tool_count": len(tools),
                    "contract_count": contract_count,
                    "contract_coverage": coverage,
                    "include_contracts": bool(include_contracts),
                },
            ),
        )

    @mcp.tool()
    def get_tool_contract(tool_name: str):
        """获取单个工具的 AI 调用契约。"""
        started_at = time.perf_counter()
        contract = get_catalog_tool_contract(tool_name)
        if contract is None:
            return fail_with_meta(
                f"tool contract not found: {tool_name}",
                tool_name="get_tool_contract",
                action="get",
                started_at=started_at,
                source_chain=["search.get_tool_contract", "tool_catalog"],
                error_code="NOT_FOUND",
                extra_meta=_read_only_meta(
                    status="not_found",
                    target=tool_name.strip() or "tool_catalog",
                    degraded=True,
                ),
            )
        return ok_with_meta(
            {"tool": tool_name, "contract": contract},
            tool_name="get_tool_contract",
            action="get",
            started_at=started_at,
            source_chain=["search.get_tool_contract", "tool_catalog"],
            extra_meta=_read_only_meta(
                status="available",
                target=tool_name.strip() or "tool_catalog",
                extra_quality={"contract_version": contract.get("contract_version")},
            ),
        )

    @mcp.tool()
    def get_available_categories():
        """获取工具分类"""
        started_at = time.perf_counter()
        names = sorted({
            _infer_tool_category(str(name), tool)
            for name, tool in _iter_registered_tools(mcp)
            if name and not _is_hidden_tool(name, tool)
        })
        categories = [
            {'name': name, 'description': _category_description(name)}
            for name in names
        ]
        
        return ok_with_meta(
            {'categories': categories},
            tool_name="get_available_categories",
            action="list",
            started_at=started_at,
            source_chain=["search.get_available_categories", "tool_registry"],
            extra_meta=_read_only_meta(
                status="available",
                target="tool_categories",
                extra_quality={"category_count": len(categories)},
            ),
        )
