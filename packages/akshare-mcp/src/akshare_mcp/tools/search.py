"""搜索工具"""

from typing import Optional
from ..storage import get_db
from ..utils import ok, fail


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
            keyword: 关键词（代码或名称）
            limit: 返回数量
        """
        try:
            db = get_db()
            
            # 直接查询数据库，使用正确的字段名
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
            
            return ok({
                'keyword': keyword,
                'results': results,
                'count': len(results),
            })
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    def available_tools():
        """获取可用工具列表"""
        tools = [
            {'name': 'get_realtime_quote', 'category': 'market', 'description': '获取实时行情'},
            {'name': 'get_batch_quotes', 'category': 'market', 'description': '批量获取行情'},
            {'name': 'get_kline_data', 'category': 'market', 'description': '获取K线数据'},
            {'name': 'search_stocks', 'category': 'market', 'description': '搜索股票'},
            {'name': 'get_stock_info', 'category': 'market', 'description': '获取股票信息'},
            {'name': 'get_financials', 'category': 'finance', 'description': '获取财务数据'},
            {'name': 'get_valuation_metrics', 'category': 'valuation', 'description': '获取估值指标'},
            {'name': 'dcf_valuation', 'category': 'valuation', 'description': 'DCF估值'},
            {'name': 'calculate_technical_indicators', 'category': 'technical', 'description': '计算技术指标'},
            {'name': 'check_candlestick_patterns', 'category': 'technical', 'description': '检测K线形态'},
            {'name': 'run_simple_backtest', 'category': 'backtest', 'description': '运行回测'},
            {'name': 'optimize_portfolio', 'category': 'portfolio', 'description': '组合优化'},
            {'name': 'analyze_portfolio_risk', 'category': 'portfolio', 'description': '风险分析'},
            {'name': 'should_i_buy', 'category': 'decision', 'description': '买入建议'},
            {'name': 'should_i_sell', 'category': 'decision', 'description': '卖出建议'},
        ]
        
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
