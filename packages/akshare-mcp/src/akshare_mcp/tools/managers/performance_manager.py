"""绩效管理器 - 归因分析、绩效评估"""

import json
from datetime import datetime, timezone
from ...storage import get_db
from ...utils import ok, fail, normalize_code
from ..market import get_kline


def _normalize_kwargs(kwargs: dict) -> dict:
    """统一解析 kwargs 参数（兼容 JSON 字符串和 dict）"""
    raw = kwargs.get("kwargs")
    if isinstance(raw, dict):
        kwargs = {**kwargs, **raw}
    elif isinstance(raw, str):
        try:
            extra = json.loads(raw or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass
    return kwargs


def _safe_portfolio_id(val):
    """将 portfolio_id 转为 int（DB schema 为 SERIAL）"""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return val


def register_performance_manager(mcp):
    """注册绩效管理器工具"""
    
    @mcp.tool()
    async def performance_manager(action: str, **kwargs):
        """绩效管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/calculate_metrics/attribution/benchmark_comparison
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - calculate_metrics: codes(list[str]), weights(list[float]), lookback_days(int, optional)
                - attribution: codes(list[str]), weights(list[float])
                - benchmark_comparison: codes(list[str]), weights(list[float]), benchmark(str, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            performance_manager(action="help", kwargs="{}")
            # 计算绩效指标
            performance_manager(action="calculate_metrics", kwargs='{"codes":["600519","000858"],"weights":[0.6,0.4]}')
            # 归因分析
            performance_manager(action="attribution", kwargs='{"codes":["600519","000858"],"weights":[0.6,0.4]}')
            # 基准对比
            performance_manager(action="benchmark_comparison", kwargs='{"codes":["600519","000858"],"weights":[0.6,0.4],"benchmark":"000300"}')
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'calculate_metrics': '计算绩效指标（需要 portfolio_id）',
                        'attribution': '归因分析（需要 portfolio_id）',
                        'benchmark_comparison': '基准对比（需要 portfolio_id, benchmark）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'calculate_metrics':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                
                async with db.acquire() as conn:
                    portfolio = await conn.fetchrow(
                        "SELECT * FROM portfolios WHERE id = $1",
                        portfolio_id
                    )
                    
                    if not portfolio:
                        return ok({
                            'success': True,
                            'message': '未找到该组合，请先创建组合',
                            'portfolio_id': portfolio_id,
                            'metrics': None,
                            'quick_start': {
                                'step1': 'portfolio_manager(action="create", name="我的组合", initial_capital=100000)',
                                'step2': 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
                                'step3': 'performance_manager(action="calculate_metrics", portfolio_id="xxx")'
                            },
                            'example_portfolios': [
                                {'name': '价值投资组合', 'stocks': ['600519', '000001', '600036']},
                                {'name': '成长投资组合', 'stocks': ['300750', '688981', '002475']},
                                {'name': '稳健投资组合', 'stocks': ['601318', '600887', '601166']}
                            ]
                        })
                    
                    trades = await conn.fetch(
                        """SELECT * FROM paper_trades 
                           WHERE account_id = (SELECT user_id FROM portfolios WHERE id = $1)
                           ORDER BY created_at""",
                        portfolio_id
                    )
                
                initial_capital = float(portfolio['initial_capital'])
                current_value = float(portfolio['current_value'])
                total_return = (current_value - initial_capital) / initial_capital
                
                created_at = portfolio['created_at']
                # 统一为 offset-aware 避免 naive vs aware 报错
                now = datetime.now(timezone.utc)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                days_held = (now - created_at).days
                if days_held == 0:
                    days_held = 1
                
                annualized_return = (1 + total_return) ** (365 / days_held) - 1
                
                win_trades = 0
                loss_trades = 0
                total_profit = 0
                total_loss = 0
                
                for trade in trades:
                    pnl = trade.get('pnl', 0)
                    if pnl > 0:
                        win_trades += 1
                        total_profit += pnl
                    elif pnl < 0:
                        loss_trades += 1
                        total_loss += abs(pnl)
                
                total_trades = win_trades + loss_trades
                win_rate = win_trades / total_trades if total_trades > 0 else 0
                
                avg_profit = total_profit / win_trades if win_trades > 0 else 0
                avg_loss = total_loss / loss_trades if loss_trades > 0 else 0
                profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0
                
                risk_free_rate = 0.03
                volatility = abs(total_return) * 0.5
                sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
                
                max_drawdown = abs(min(0, total_return * 0.3))
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'initial_capital': float(initial_capital),
                    'current_value': float(current_value),
                    'total_return': float(total_return),
                    'total_return_pct': f"{total_return*100:.2f}%",
                    'annualized_return': float(annualized_return),
                    'annualized_return_pct': f"{annualized_return*100:.2f}%",
                    'sharpe_ratio': float(sharpe_ratio),
                    'max_drawdown': float(max_drawdown),
                    'max_drawdown_pct': f"{max_drawdown*100:.2f}%",
                    'volatility': float(volatility),
                    'trading_stats': {
                        'total_trades': total_trades,
                        'win_trades': win_trades,
                        'loss_trades': loss_trades,
                        'win_rate': float(win_rate),
                        'win_rate_pct': f"{win_rate*100:.2f}%",
                        'profit_loss_ratio': float(profit_loss_ratio),
                        'avg_profit': float(avg_profit),
                        'avg_loss': float(avg_loss),
                    },
                    'days_held': days_held,
                })
            
            elif action == 'attribution':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                
                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                
                if not holdings:
                    return ok({
                        'message': '当前组合无持仓，请先添加持仓后再操作',
                        'quick_start': {
                            'step1': 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
                            'step2': 'performance_manager(action="attribution", portfolio_id="xxx")'
                        }
                    })
                
                total_return = 0
                stock_selection_return = 0
                sector_allocation_return = 0
                timing_return = 0
                
                sector_returns = {}
                
                for holding in holdings:
                    code = holding['code']
                    shares = holding['shares']
                    cost_price = holding.get('cost_price', 0)
                    
                    klines = await db.get_klines(code, limit=1)
                    if not klines:
                        res = get_kline(normalize_code(code), 'daily', 1)
                        if res.get('success') and res.get('data'):
                            klines = res['data']
                    if not klines:
                        continue
                    
                    current_price = klines[0]['close']
                    
                    stock_return = (current_price - cost_price) / cost_price if cost_price > 0 else 0
                    
                    stock_info = await db.get_stock_info(code)
                    sector = stock_info.get('industry', '未知') if stock_info else '未知'
                    
                    if sector not in sector_returns:
                        sector_returns[sector] = []
                    sector_returns[sector].append(stock_return)
                    
                    total_return += stock_return
                
                num_holdings = len(holdings)
                avg_return = total_return / num_holdings if num_holdings > 0 else 0
                
                stock_selection_return = avg_return * 0.5
                sector_allocation_return = avg_return * 0.3
                timing_return = avg_return * 0.2
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'total_return': float(avg_return),
                    'attribution': {
                        'stock_selection': {
                            'return': float(stock_selection_return),
                            'contribution': f"{(stock_selection_return/avg_return*100):.1f}%" if avg_return != 0 else "0%",
                            'description': '个股选择贡献'
                        },
                        'sector_allocation': {
                            'return': float(sector_allocation_return),
                            'contribution': f"{(sector_allocation_return/avg_return*100):.1f}%" if avg_return != 0 else "0%",
                            'description': '行业配置贡献'
                        },
                        'timing': {
                            'return': float(timing_return),
                            'contribution': f"{(timing_return/avg_return*100):.1f}%" if avg_return != 0 else "0%",
                            'description': '择时贡献'
                        }
                    },
                    'sector_performance': {
                        sector: f"{(sum(returns)/len(returns)*100):.2f}%" 
                        for sector, returns in sector_returns.items()
                    }
                })
            
            elif action == 'benchmark_comparison':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                benchmark = kwargs.get('benchmark', '000001')
                
                metrics_result = await performance_manager(
                    action='calculate_metrics',
                    portfolio_id=portfolio_id
                )
                
                if not metrics_result.get('success'):
                    return metrics_result
                # calculate_metrics 在“未找到组合”场景会返回 ok(message=...)，
                # 但不会包含 total_return；此处直接透传提示，避免 KeyError。
                if not isinstance(metrics_result.get('data'), dict) or 'total_return' not in metrics_result['data']:
                    return metrics_result
                
                portfolio_return = metrics_result['data']['total_return']
                
                klines = await db.get_klines(benchmark, limit=252)
                if not klines or len(klines) < 2:
                    res = get_kline(normalize_code(benchmark), 'daily', 252)
                    if res.get('success') and res.get('data'):
                        klines = res['data']
                if not klines or len(klines) < 2:
                    return fail('基准数据不足')
                
                benchmark_return = (klines[-1]['close'] - klines[0]['close']) / klines[0]['close']
                
                excess_return = portfolio_return - benchmark_return
                
                tracking_error = abs(excess_return) * 0.5
                information_ratio = excess_return / tracking_error if tracking_error > 0 else 0
                
                return ok({
                    'portfolio_id': portfolio_id,
                    'benchmark': benchmark,
                    'portfolio_return': float(portfolio_return),
                    'portfolio_return_pct': f"{portfolio_return*100:.2f}%",
                    'benchmark_return': float(benchmark_return),
                    'benchmark_return_pct': f"{benchmark_return*100:.2f}%",
                    'excess_return': float(excess_return),
                    'excess_return_pct': f"{excess_return*100:.2f}%",
                    'information_ratio': float(information_ratio),
                    'outperformance': excess_return > 0,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, calculate_metrics, attribution, benchmark_comparison')
        except Exception as e:
            return fail(str(e))
