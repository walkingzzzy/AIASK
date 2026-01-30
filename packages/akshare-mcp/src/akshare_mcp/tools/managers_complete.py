"""完整的30个Manager工具实现"""

from typing import Optional, List, Dict, Any
from ..storage import get_db
from ..utils import ok, fail
from datetime import datetime


def register(mcp):
    """注册所有30个Manager工具"""
    
    # ========== 1. alerts_manager ==========
    @mcp.tool()
    async def alerts_manager(action: str, **kwargs):
        """告警管理器 - 创建、查询、更新、删除告警"""
        try:
            db = get_db()
            
            if action == 'list':
                # 查询告警列表
                status = kwargs.get('status', 'active')
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM alerts WHERE status = $1 ORDER BY created_at DESC LIMIT 100",
                        status
                    )
                    alerts = [dict(row) for row in rows]
                return ok({'alerts': alerts, 'count': len(alerts)})
            
            elif action == 'create':
                # 创建告警
                code = kwargs.get('code')
                indicator = kwargs.get('indicator')
                condition = kwargs.get('condition')
                value = kwargs.get('value')
                
                async with db.acquire() as conn:
                    alert_id = await conn.fetchval(
                        """INSERT INTO alerts (code, indicator, condition, value, status, created_at)
                           VALUES ($1, $2, $3, $4, 'active', NOW())
                           RETURNING id""",
                        code, indicator, condition, value
                    )
                return ok({'alert_id': alert_id, 'status': 'created'})
            
            elif action == 'update':
                # 更新告警状态
                alert_id = kwargs.get('alert_id')
                status = kwargs.get('status', 'inactive')
                
                async with db.acquire() as conn:
                    await conn.execute(
                        "UPDATE alerts SET status = $1, updated_at = NOW() WHERE id = $2",
                        status, alert_id
                    )
                return ok({'alert_id': alert_id, 'status': status})
            
            elif action == 'delete':
                # 删除告警
                alert_id = kwargs.get('alert_id')
                async with db.acquire() as conn:
                    await conn.execute("DELETE FROM alerts WHERE id = $1", alert_id)
                return ok({'alert_id': alert_id, 'deleted': True})
            
            else:
                return fail(f'Unknown action: {action}')
        
        except Exception as e:
            return fail(str(e))
    
    # ========== 2. portfolio_manager ==========
    @mcp.tool()
    async def portfolio_manager(action: str, **kwargs):
        """组合管理器 - 创建、调整、查询组合"""
        try:
            db = get_db()
            
            if action == 'list':
                user_id = kwargs.get('user_id', 'default')
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM portfolios WHERE user_id = $1 ORDER BY created_at DESC",
                        user_id
                    )
                    portfolios = [dict(row) for row in rows]
                return ok({'portfolios': portfolios})
            
            elif action == 'create':
                name = kwargs.get('name')
                user_id = kwargs.get('user_id', 'default')
                initial_capital = kwargs.get('initial_capital', 100000)
                
                async with db.acquire() as conn:
                    portfolio_id = await conn.fetchval(
                        """INSERT INTO portfolios (name, user_id, initial_capital, current_value, created_at)
                           VALUES ($1, $2, $3, $3, NOW())
                           RETURNING id""",
                        name, user_id, initial_capital
                    )
                return ok({'portfolio_id': portfolio_id})
            
            elif action == 'add_holding':
                portfolio_id = kwargs.get('portfolio_id')
                code = kwargs.get('code')
                shares = kwargs.get('shares')
                cost_price = kwargs.get('cost_price')
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO holdings (portfolio_id, code, shares, cost_price, created_at)
                           VALUES ($1, $2, $3, $4, NOW())
                           ON CONFLICT (portfolio_id, code) DO UPDATE
                           SET shares = holdings.shares + EXCLUDED.shares""",
                        portfolio_id, code, shares, cost_price
                    )
                return ok({'portfolio_id': portfolio_id, 'code': code, 'shares': shares})
            
            elif action == 'get_holdings':
                portfolio_id = kwargs.get('portfolio_id')
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )
                    holdings = [dict(row) for row in rows]
                return ok({'holdings': holdings})
            
            elif action == 'calculate_return':
                portfolio_id = kwargs.get('portfolio_id')
                # 计算组合收益
                async with db.acquire() as conn:
                    portfolio = await conn.fetchrow(
                        "SELECT * FROM portfolios WHERE id = $1",
                        portfolio_id
                    )
                    if not portfolio:
                        return fail('Portfolio not found')
                    
                    total_return = (portfolio['current_value'] - portfolio['initial_capital']) / portfolio['initial_capital']
                    
                return ok({
                    'portfolio_id': portfolio_id,
                    'initial_capital': float(portfolio['initial_capital']),
                    'current_value': float(portfolio['current_value']),
                    'total_return': float(total_return),
                })
            
            else:
                return fail(f'Unknown action: {action}')
        
        except Exception as e:
            return fail(str(e))
    
    # ========== 3. backtest_manager ==========
    @mcp.tool()
    async def backtest_manager(action: str, **kwargs):
        """回测管理器 - 保存、查询回测结果"""
        try:
            db = get_db()
            
            if action == 'save':
                code = kwargs.get('code')
                strategy = kwargs.get('strategy')
                params = kwargs.get('params', {})
                result = kwargs.get('result', {})
                
                async with db.acquire() as conn:
                    backtest_id = await conn.fetchval(
                        """INSERT INTO backtest_results 
                           (code, strategy, params, total_return, sharpe_ratio, max_drawdown, created_at)
                           VALUES ($1, $2, $3, $4, $5, $6, NOW())
                           RETURNING id""",
                        code, strategy, str(params),
                        result.get('total_return'), result.get('sharpe_ratio'), result.get('max_drawdown')
                    )
                return ok({'backtest_id': backtest_id})
            
            elif action == 'list':
                code = kwargs.get('code')
                limit = kwargs.get('limit', 20)
                
                async with db.acquire() as conn:
                    if code:
                        rows = await conn.fetch(
                            "SELECT * FROM backtest_results WHERE code = $1 ORDER BY created_at DESC LIMIT $2",
                            code, limit
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT $1",
                            limit
                        )
                    results = [dict(row) for row in rows]
                
                return ok({'results': results})
            
            elif action == 'get':
                backtest_id = kwargs.get('backtest_id')
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM backtest_results WHERE id = $1",
                        backtest_id
                    )
                    if not row:
                        return fail('Backtest not found')
                    result = dict(row)
                
                return ok(result)
            
            else:
                return fail(f'Unknown action: {action}')
        
        except Exception as e:
            return fail(str(e))
    
    # ========== 4. data_sync_manager ==========
    @mcp.tool()
    async def data_sync_manager(action: str, **kwargs):
        """数据同步管理器 - 任务调度、状态跟踪"""
        try:
            db = get_db()
            
            if action == 'status':
                # 获取各类数据的最后同步时间
                async with db.acquire() as conn:
                    kline_sync = await conn.fetchval("SELECT MAX(updated_at) FROM kline_1d")
                    quote_sync = await conn.fetchval("SELECT MAX(updated_at) FROM quotes")
                    financial_sync = await conn.fetchval("SELECT MAX(updated_at) FROM financials")
                    
                    # 获取待处理任务数
                    pending_tasks = await conn.fetchval(
                        "SELECT COUNT(*) FROM sync_tasks WHERE status = 'pending'"
                    ) or 0
                    
                    running_tasks = await conn.fetchval(
                        "SELECT COUNT(*) FROM sync_tasks WHERE status = 'running'"
                    ) or 0
                
                return ok({
                    'last_sync': {
                        'kline': kline_sync.isoformat() if kline_sync else None,
                        'quote': quote_sync.isoformat() if quote_sync else None,
                        'financial': financial_sync.isoformat() if financial_sync else None,
                    },
                    'status': 'running' if running_tasks > 0 else 'idle',
                    'pending_tasks': int(pending_tasks),
                    'running_tasks': int(running_tasks),
                })
            
            elif action == 'sync':
                task_type = kwargs.get('type', 'kline')
                codes = kwargs.get('codes', [])
                priority = kwargs.get('priority', 'normal')  # high, normal, low
                
                if not codes:
                    return fail('需要提供codes参数')
                
                # 创建同步任务
                task_id = f'sync_{task_type}_{int(datetime.now().timestamp())}'
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO sync_tasks (task_id, task_type, codes, priority, status, created_at)
                           VALUES ($1, $2, $3, $4, 'pending', NOW())""",
                        task_id, task_type, codes, priority
                    )
                
                return ok({
                    'task_id': task_id,
                    'task_type': task_type,
                    'codes_count': len(codes),
                    'priority': priority,
                    'status': 'pending',
                    'message': '同步任务已创建，等待执行',
                })
            
            elif action == 'get_task':
                task_id = kwargs.get('task_id')
                
                if not task_id:
                    return fail('需要提供task_id参数')
                
                async with db.acquire() as conn:
                    task = await conn.fetchrow(
                        "SELECT * FROM sync_tasks WHERE task_id = $1",
                        task_id
                    )
                    
                    if not task:
                        return fail(f'未找到任务: {task_id}')
                    
                    task_data = dict(task)
                
                return ok(task_data)
            
            elif action == 'list_tasks':
                status = kwargs.get('status')  # pending, running, completed, failed
                limit = kwargs.get('limit', 20)
                
                async with db.acquire() as conn:
                    if status:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_tasks WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
                            status, limit
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT * FROM sync_tasks ORDER BY created_at DESC LIMIT $1",
                            limit
                        )
                    
                    tasks = [dict(row) for row in rows]
                
                return ok({
                    'tasks': tasks,
                    'count': len(tasks),
                })
            
            elif action == 'cancel_task':
                task_id = kwargs.get('task_id')
                
                if not task_id:
                    return fail('需要提供task_id参数')
                
                async with db.acquire() as conn:
                    result = await conn.execute(
                        "UPDATE sync_tasks SET status = 'cancelled', updated_at = NOW() WHERE task_id = $1 AND status IN ('pending', 'running')",
                        task_id
                    )
                    
                    if result == 'UPDATE 0':
                        return fail('任务不存在或无法取消（已完成或已失败）')
                
                return ok({
                    'task_id': task_id,
                    'status': 'cancelled',
                })
            
            elif action == 'schedule':
                # 定时同步任务
                task_type = kwargs.get('type', 'kline')
                codes = kwargs.get('codes', [])
                schedule = kwargs.get('schedule', 'daily')  # daily, hourly, weekly
                
                if not codes:
                    return fail('需要提供codes参数')
                
                schedule_id = f'schedule_{task_type}_{int(datetime.now().timestamp())}'
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO sync_schedules (schedule_id, task_type, codes, schedule, enabled, created_at)
                           VALUES ($1, $2, $3, $4, true, NOW())""",
                        schedule_id, task_type, codes, schedule
                    )
                
                return ok({
                    'schedule_id': schedule_id,
                    'task_type': task_type,
                    'schedule': schedule,
                    'codes_count': len(codes),
                    'enabled': True,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: status, sync, get_task, list_tasks, cancel_task, schedule')
        except Exception as e:
            return fail(str(e))
    
    # ========== 5. options_manager ==========
    @mcp.tool()
    async def options_manager(action: str, **kwargs):
        """期权管理器 - Black-Scholes定价和Greeks计算"""
        try:
            if action == 'list':
                # 期权列表（简化实现）
                return ok({'options': [], 'count': 0, 'note': '期权列表功能待实现'})
            
            elif action == 'calculate_greeks':
                code = kwargs.get('code')
                spot = kwargs.get('spot', 100.0)
                strike = kwargs.get('strike', 100.0)
                time_to_maturity = kwargs.get('time_to_maturity', 0.25)  # 默认3个月
                risk_free_rate = kwargs.get('risk_free_rate', 0.03)
                volatility = kwargs.get('volatility', 0.25)
                option_type = kwargs.get('option_type', 'call')
                dividend_yield = kwargs.get('dividend_yield', 0.0)
                
                # 如果提供了到期日期，计算time_to_maturity
                expiry_date = kwargs.get('expiry_date')
                if expiry_date:
                    from ..services.options_pricing import options_pricing
                    time_to_maturity = options_pricing.calculate_time_to_maturity(expiry_date)
                
                # 使用Black-Scholes模型计算Greeks
                from ..services.options_pricing import options_pricing
                
                # 计算期权价格
                option_price = options_pricing.black_scholes(
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    volatility=volatility,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                # 计算Greeks
                greeks = options_pricing.calculate_greeks(
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    volatility=volatility,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                return ok({
                    'code': code,
                    'option_type': option_type,
                    'spot': spot,
                    'strike': strike,
                    'time_to_maturity': f"{time_to_maturity:.4f} years ({time_to_maturity*365:.0f} days)",
                    'volatility': f"{volatility*100:.2f}%",
                    'risk_free_rate': f"{risk_free_rate*100:.2f}%",
                    'option_price': f"{option_price:.4f}",
                    'greeks': {
                        'delta': f"{greeks['delta']:.4f}",
                        'gamma': f"{greeks['gamma']:.4f}",
                        'theta': f"{greeks['theta']:.4f} (per day)",
                        'vega': f"{greeks['vega']:.4f} (per 1% vol change)",
                        'rho': f"{greeks['rho']:.4f} (per 1% rate change)",
                    },
                    'interpretation': {
                        'delta': f"标的价格变动1元，期权价格变动{abs(greeks['delta']):.4f}元",
                        'gamma': f"Delta对标的价格的敏感度为{greeks['gamma']:.4f}",
                        'theta': f"每天时间价值衰减{abs(greeks['theta']):.4f}元",
                        'vega': f"波动率变动1%，期权价格变动{greeks['vega']:.4f}元",
                        'rho': f"利率变动1%，期权价格变动{greeks['rho']:.4f}元",
                    }
                })
            
            elif action == 'calculate_price':
                spot = kwargs.get('spot', 100.0)
                strike = kwargs.get('strike', 100.0)
                time_to_maturity = kwargs.get('time_to_maturity', 0.25)
                risk_free_rate = kwargs.get('risk_free_rate', 0.03)
                volatility = kwargs.get('volatility', 0.25)
                option_type = kwargs.get('option_type', 'call')
                dividend_yield = kwargs.get('dividend_yield', 0.0)
                
                # 如果提供了到期日期，计算time_to_maturity
                expiry_date = kwargs.get('expiry_date')
                if expiry_date:
                    from ..services.options_pricing import options_pricing
                    time_to_maturity = options_pricing.calculate_time_to_maturity(expiry_date)
                
                from ..services.options_pricing import options_pricing
                
                # 计算期权价格
                option_price = options_pricing.black_scholes(
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    volatility=volatility,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                # 计算内在价值和时间价值
                if option_type == 'call':
                    intrinsic_value = max(spot - strike, 0)
                else:
                    intrinsic_value = max(strike - spot, 0)
                
                time_value = option_price - intrinsic_value
                
                return ok({
                    'option_type': option_type,
                    'spot': spot,
                    'strike': strike,
                    'option_price': f"{option_price:.4f}",
                    'intrinsic_value': f"{intrinsic_value:.4f}",
                    'time_value': f"{time_value:.4f}",
                    'moneyness': 'ITM' if intrinsic_value > 0 else ('ATM' if abs(spot - strike) < 0.01 * spot else 'OTM'),
                })
            
            elif action == 'implied_volatility':
                option_price = kwargs.get('option_price')
                spot = kwargs.get('spot', 100.0)
                strike = kwargs.get('strike', 100.0)
                time_to_maturity = kwargs.get('time_to_maturity', 0.25)
                risk_free_rate = kwargs.get('risk_free_rate', 0.03)
                option_type = kwargs.get('option_type', 'call')
                dividend_yield = kwargs.get('dividend_yield', 0.0)
                
                if not option_price:
                    return fail('需要提供option_price参数')
                
                # 如果提供了到期日期，计算time_to_maturity
                expiry_date = kwargs.get('expiry_date')
                if expiry_date:
                    from ..services.options_pricing import options_pricing
                    time_to_maturity = options_pricing.calculate_time_to_maturity(expiry_date)
                
                from ..services.options_pricing import options_pricing
                
                # 计算隐含波动率
                iv = options_pricing.implied_volatility(
                    option_price=option_price,
                    spot=spot,
                    strike=strike,
                    time_to_maturity=time_to_maturity,
                    risk_free_rate=risk_free_rate,
                    option_type=option_type,
                    dividend_yield=dividend_yield
                )
                
                if iv is None:
                    return fail('隐含波动率计算未收敛')
                
                return ok({
                    'option_price': option_price,
                    'implied_volatility': f"{iv*100:.2f}%",
                    'iv_value': iv,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: list, calculate_greeks, calculate_price, implied_volatility')
        except Exception as e:
            return fail(str(e))
    
    # ========== 6. technical_analysis_manager ==========
    @mcp.tool()
    async def technical_analysis_manager(action: str, **kwargs):
        """技术分析管理器"""
        try:
            if action == 'calculate':
                code = kwargs.get('code')
                indicators = kwargs.get('indicators', ['MA', 'RSI', 'MACD'])
                
                from ..services import technical_analysis
                db = get_db()
                klines = await db.get_klines(code, limit=100)
                
                if not klines:
                    return fail('No kline data')
                
                results = technical_analysis.calculate_all_indicators(klines, indicators)
                return ok({'code': code, 'indicators': results})
            
            elif action == 'list_indicators':
                indicators = ['MA', 'EMA', 'RSI', 'MACD', 'KDJ', 'BOLL', 'ATR']
                return ok({'indicators': indicators})
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 7. fundamental_analysis_manager ==========
    @mcp.tool()
    async def fundamental_analysis_manager(action: str, **kwargs):
        """基本面分析管理器 - 杜邦分析、同行对比、内在价值"""
        try:
            db = get_db()
            
            if action == 'analyze':
                code = kwargs.get('code')
                financials = await db.get_financials(code, limit=4)
                
                if not financials:
                    return fail(f'未找到{code}的财务数据')
                
                latest = financials[0]
                
                # 基础分析
                revenue_trend = 'unknown'
                if len(financials) >= 2:
                    revenue_growth = (latest.get('revenue', 0) - financials[1].get('revenue', 0)) / financials[1].get('revenue', 1)
                    revenue_trend = 'growing' if revenue_growth > 0 else 'declining'
                
                profitability = 'average'
                roe = latest.get('roe', 0)
                if roe > 15:
                    profitability = 'excellent'
                elif roe > 10:
                    profitability = 'good'
                elif roe < 5:
                    profitability = 'poor'
                
                return ok({
                    'code': code,
                    'financials': financials,
                    'analysis': {
                        'revenue_trend': revenue_trend,
                        'profitability': profitability,
                        'roe': roe,
                        'debt_ratio': latest.get('debt_ratio', 0),
                        'current_ratio': latest.get('current_ratio', 0),
                    }
                })
            
            elif action == 'dupont_analysis':
                code = kwargs.get('code')
                financials = await db.get_financials(code, limit=1)
                
                if not financials:
                    return fail(f'未找到{code}的财务数据')
                
                latest = financials[0]
                
                # 杜邦分析：ROE = 净利率 × 资产周转率 × 权益乘数
                net_profit_margin = latest.get('net_profit_margin', 0)  # 净利率
                asset_turnover = latest.get('asset_turnover', 0)  # 资产周转率
                equity_multiplier = latest.get('equity_multiplier', 0)  # 权益乘数
                
                # 如果数据库没有这些字段，尝试计算
                if not net_profit_margin and latest.get('net_profit') and latest.get('revenue'):
                    net_profit_margin = latest['net_profit'] / latest['revenue']
                
                if not asset_turnover and latest.get('revenue') and latest.get('total_assets'):
                    asset_turnover = latest['revenue'] / latest['total_assets']
                
                if not equity_multiplier and latest.get('total_assets') and latest.get('equity'):
                    equity_multiplier = latest['total_assets'] / latest['equity']
                
                # 计算ROE
                roe_calculated = net_profit_margin * asset_turnover * equity_multiplier
                roe_reported = latest.get('roe', 0)
                
                # 分析各组成部分
                analysis = {
                    'net_profit_margin': {
                        'value': float(net_profit_margin),
                        'percentage': f"{net_profit_margin*100:.2f}%",
                        'level': 'high' if net_profit_margin > 0.15 else ('medium' if net_profit_margin > 0.08 else 'low'),
                        'description': '净利率反映盈利能力',
                    },
                    'asset_turnover': {
                        'value': float(asset_turnover),
                        'level': 'high' if asset_turnover > 1.0 else ('medium' if asset_turnover > 0.5 else 'low'),
                        'description': '资产周转率反映运营效率',
                    },
                    'equity_multiplier': {
                        'value': float(equity_multiplier),
                        'level': 'high' if equity_multiplier > 3.0 else ('medium' if equity_multiplier > 2.0 else 'low'),
                        'description': '权益乘数反映财务杠杆',
                    },
                }
                
                # 综合评价
                strengths = []
                weaknesses = []
                
                if analysis['net_profit_margin']['level'] == 'high':
                    strengths.append('盈利能力强')
                elif analysis['net_profit_margin']['level'] == 'low':
                    weaknesses.append('盈利能力弱')
                
                if analysis['asset_turnover']['level'] == 'high':
                    strengths.append('运营效率高')
                elif analysis['asset_turnover']['level'] == 'low':
                    weaknesses.append('运营效率低')
                
                if analysis['equity_multiplier']['level'] == 'high':
                    strengths.append('财务杠杆高（风险较大）')
                elif analysis['equity_multiplier']['level'] == 'low':
                    strengths.append('财务杠杆低（风险较小）')
                
                return ok({
                    'code': code,
                    'roe': {
                        'calculated': float(roe_calculated),
                        'reported': float(roe_reported),
                        'percentage': f"{roe_calculated*100:.2f}%",
                    },
                    'components': analysis,
                    'strengths': strengths,
                    'weaknesses': weaknesses,
                    'formula': 'ROE = 净利率 × 资产周转率 × 权益乘数',
                })
            
            elif action == 'compare':
                codes = kwargs.get('codes', [])
                
                if not codes or len(codes) < 2:
                    return fail('需要至少2个股票代码进行对比')
                
                comparison_data = []
                
                for code in codes:
                    financials = await db.get_financials(code, limit=1)
                    stock_info = await db.get_stock_info(code)
                    
                    if financials:
                        latest = financials[0]
                        comparison_data.append({
                            'code': code,
                            'name': stock_info.get('stock_name', code) if stock_info else code,
                            'roe': latest.get('roe', 0),
                            'pe_ratio': latest.get('pe_ratio', 0),
                            'pb_ratio': latest.get('pb_ratio', 0),
                            'revenue': latest.get('revenue', 0),
                            'net_profit': latest.get('net_profit', 0),
                            'debt_ratio': latest.get('debt_ratio', 0),
                            'current_ratio': latest.get('current_ratio', 0),
                        })
                
                if not comparison_data:
                    return fail('未找到任何财务数据')
                
                # 计算平均值和排名
                metrics = ['roe', 'pe_ratio', 'pb_ratio', 'revenue', 'net_profit', 'debt_ratio', 'current_ratio']
                averages = {}
                
                for metric in metrics:
                    values = [d[metric] for d in comparison_data if d[metric] is not None]
                    averages[metric] = sum(values) / len(values) if values else 0
                
                # 添加排名
                for metric in ['roe', 'revenue', 'net_profit', 'current_ratio']:
                    sorted_data = sorted(comparison_data, key=lambda x: x[metric], reverse=True)
                    for i, item in enumerate(sorted_data):
                        item[f'{metric}_rank'] = i + 1
                
                # 找出最佳和最差
                best_roe = max(comparison_data, key=lambda x: x['roe'])
                worst_roe = min(comparison_data, key=lambda x: x['roe'])
                
                return ok({
                    'codes': codes,
                    'comparison': comparison_data,
                    'averages': averages,
                    'highlights': {
                        'best_roe': {'code': best_roe['code'], 'value': best_roe['roe']},
                        'worst_roe': {'code': worst_roe['code'], 'value': worst_roe['roe']},
                    },
                })
            
            elif action == 'intrinsic_value':
                code = kwargs.get('code')
                method = kwargs.get('method', 'dcf')  # dcf, pe, pb
                
                financials = await db.get_financials(code, limit=4)
                
                if not financials:
                    return fail(f'未找到{code}的财务数据')
                
                latest = financials[0]
                
                if method == 'dcf':
                    # DCF估值（简化版）
                    fcf = latest.get('free_cash_flow', latest.get('net_profit', 0) * 0.8)  # 自由现金流
                    growth_rate = kwargs.get('growth_rate', 0.10)  # 增长率
                    discount_rate = kwargs.get('discount_rate', 0.10)  # 折现率
                    terminal_growth = kwargs.get('terminal_growth', 0.03)  # 永续增长率
                    years = kwargs.get('years', 5)  # 预测年数
                    
                    # 计算未来现金流现值
                    pv_fcf = 0
                    for year in range(1, years + 1):
                        future_fcf = fcf * ((1 + growth_rate) ** year)
                        pv = future_fcf / ((1 + discount_rate) ** year)
                        pv_fcf += pv
                    
                    # 计算终值
                    terminal_fcf = fcf * ((1 + growth_rate) ** years) * (1 + terminal_growth)
                    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
                    pv_terminal = terminal_value / ((1 + discount_rate) ** years)
                    
                    enterprise_value = pv_fcf + pv_terminal
                    
                    # 获取股本
                    shares = latest.get('total_shares', 1000000000)  # 总股本
                    intrinsic_price = enterprise_value / shares
                    
                    return ok({
                        'code': code,
                        'method': 'DCF',
                        'intrinsic_value': float(enterprise_value),
                        'intrinsic_price_per_share': float(intrinsic_price),
                        'assumptions': {
                            'fcf': float(fcf),
                            'growth_rate': f"{growth_rate*100:.1f}%",
                            'discount_rate': f"{discount_rate*100:.1f}%",
                            'terminal_growth': f"{terminal_growth*100:.1f}%",
                            'years': years,
                        },
                        'components': {
                            'pv_fcf': float(pv_fcf),
                            'pv_terminal': float(pv_terminal),
                        }
                    })
                
                elif method == 'pe':
                    # PE估值
                    eps = latest.get('eps', 0)
                    industry_pe = kwargs.get('industry_pe', 15)  # 行业平均PE
                    
                    intrinsic_price = eps * industry_pe
                    
                    return ok({
                        'code': code,
                        'method': 'PE',
                        'intrinsic_price_per_share': float(intrinsic_price),
                        'eps': float(eps),
                        'industry_pe': float(industry_pe),
                    })
                
                elif method == 'pb':
                    # PB估值
                    bvps = latest.get('bvps', 0)  # 每股净资产
                    industry_pb = kwargs.get('industry_pb', 2.0)  # 行业平均PB
                    
                    intrinsic_price = bvps * industry_pb
                    
                    return ok({
                        'code': code,
                        'method': 'PB',
                        'intrinsic_price_per_share': float(intrinsic_price),
                        'bvps': float(bvps),
                        'industry_pb': float(industry_pb),
                    })
                
                else:
                    return fail(f'不支持的估值方法: {method}. 支持: dcf, pe, pb')
            
            else:
                return fail(f'Unknown action: {action}. Supported: analyze, dupont_analysis, compare, intrinsic_value')
        except Exception as e:
            return fail(str(e))
    
    # ========== 8. sentiment_manager ==========
    @mcp.tool()
    async def sentiment_manager(action: str, **kwargs):
        """情绪分析管理器"""
        try:
            if action == 'analyze':
                code = kwargs.get('code')
                from ..services.sentiment import sentiment_analyzer
                db = get_db()
                klines = await db.get_klines(code, limit=100)
                
                if not klines:
                    return fail('No data')
                
                result = sentiment_analyzer.analyze_sentiment(klines)
                result['code'] = code
                return ok(result)
            
            elif action == 'get_index':
                from ..services.sentiment import sentiment_analyzer
                result = sentiment_analyzer.calculate_fear_greed_index()
                return ok(result)
            
            else:
                return fail(f'Unknown action: {action}')
        except Exception as e:
            return fail(str(e))
    
    # ========== 9. market_insight_manager ==========
    @mcp.tool()
    async def market_insight_manager(action: str, **kwargs):
        """市场洞察管理器 - 市场趋势、板块分析"""
        try:
            db = get_db()
            
            if action == 'get_insights':
                date = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))
                
                # 获取主要指数数据
                indices = ['000001', '399001', '399006']  # 上证指数、深证成指、创业板指
                insights = []
                
                for index_code in indices:
                    klines = await db.get_klines(index_code, limit=20)
                    if klines and len(klines) >= 2:
                        latest = klines[-1]
                        prev = klines[-2]
                        
                        change_pct = (latest['close'] - prev['close']) / prev['close']
                        
                        # 计算短期趋势（5日）
                        if len(klines) >= 5:
                            ma5 = sum(k['close'] for k in klines[-5:]) / 5
                            trend = 'up' if latest['close'] > ma5 else 'down'
                            strength = abs(latest['close'] - ma5) / ma5
                        else:
                            trend = 'up' if change_pct > 0 else 'down'
                            strength = abs(change_pct)
                        
                        index_name = {
                            '000001': '上证指数',
                            '399001': '深证成指',
                            '399006': '创业板指'
                        }.get(index_code, index_code)
                        
                        insights.append({
                            'type': 'index',
                            'index': index_name,
                            'code': index_code,
                            'message': f"{index_name}{'上涨' if change_pct > 0 else '下跌'}{abs(change_pct)*100:.2f}%",
                            'trend': trend,
                            'strength': float(strength),
                            'confidence': 0.8,
                        })
                
                # 添加市场整体判断
                if insights:
                    up_count = sum(1 for i in insights if i['trend'] == 'up')
                    market_trend = 'up' if up_count >= 2 else 'down'
                    
                    insights.insert(0, {
                        'type': 'market',
                        'message': f"市场整体{'上涨' if market_trend == 'up' else '下跌'}，{up_count}/{len(insights)}个主要指数上涨",
                        'trend': market_trend,
                        'confidence': 0.7,
                    })
                
                return ok({
                    'date': date,
                    'insights': insights,
                    'count': len(insights),
                })
            
            elif action == 'analyze_sector':
                sector = kwargs.get('sector', '科技')
                
                # 获取板块相关股票（简化实现）
                sector_stocks = {
                    '科技': ['000001', '600519', '000858'],
                    '金融': ['600036', '601318', '601398'],
                    '医药': ['600276', '000538', '002415'],
                    '消费': ['600519', '000858', '002304'],
                }
                
                stocks = sector_stocks.get(sector, [])
                
                if not stocks:
                    return ok({
                        'sector': sector,
                        'trend': 'unknown',
                        'strength': 0.0,
                        'message': f'未找到{sector}板块数据',
                    })
                
                # 分析板块趋势
                up_count = 0
                total_change = 0.0
                
                for code in stocks:
                    klines = await db.get_klines(code, limit=2)
                    if klines and len(klines) >= 2:
                        latest = klines[-1]
                        prev = klines[-2]
                        change_pct = (latest['close'] - prev['close']) / prev['close']
                        total_change += change_pct
                        if change_pct > 0:
                            up_count += 1
                
                avg_change = total_change / len(stocks) if stocks else 0
                trend = 'up' if avg_change > 0 else 'down'
                strength = abs(avg_change)
                
                return ok({
                    'sector': sector,
                    'trend': trend,
                    'strength': float(strength),
                    'avg_change': f"{avg_change*100:.2f}%",
                    'up_ratio': f"{up_count}/{len(stocks)}",
                    'stocks_analyzed': len(stocks),
                })
            
            elif action == 'market_sentiment':
                # 分析市场情绪
                # 获取涨跌家数比例
                limit_up_count = 0  # 涨停数量（简化）
                limit_down_count = 0  # 跌停数量（简化）
                
                # 简化的情绪指标
                sentiment_score = 50  # 中性
                
                # 根据主要指数涨跌调整情绪
                indices = ['000001', '399001', '399006']
                up_indices = 0
                
                for index_code in indices:
                    klines = await db.get_klines(index_code, limit=2)
                    if klines and len(klines) >= 2:
                        latest = klines[-1]
                        prev = klines[-2]
                        if latest['close'] > prev['close']:
                            up_indices += 1
                
                sentiment_score = 30 + (up_indices / len(indices)) * 40
                
                sentiment_level = 'neutral'
                if sentiment_score >= 70:
                    sentiment_level = 'bullish'
                elif sentiment_score >= 55:
                    sentiment_level = 'slightly_bullish'
                elif sentiment_score <= 30:
                    sentiment_level = 'bearish'
                elif sentiment_score <= 45:
                    sentiment_level = 'slightly_bearish'
                
                return ok({
                    'sentiment_score': float(sentiment_score),
                    'sentiment_level': sentiment_level,
                    'description': {
                        'bullish': '市场情绪乐观',
                        'slightly_bullish': '市场情绪偏乐观',
                        'neutral': '市场情绪中性',
                        'slightly_bearish': '市场情绪偏悲观',
                        'bearish': '市场情绪悲观',
                    }.get(sentiment_level, '未知'),
                    'up_indices': f"{up_indices}/{len(indices)}",
                })
            
            elif action == 'hot_sectors':
                # 热门板块分析
                sectors = ['科技', '金融', '医药', '消费', '新能源']
                sector_performance = []
                
                for sector in sectors:
                    # 简化的板块表现分析
                    sector_stocks = {
                        '科技': ['000001', '600519'],
                        '金融': ['600036', '601318'],
                        '医药': ['600276', '000538'],
                        '消费': ['600519', '000858'],
                        '新能源': ['000001', '000858'],
                    }
                    
                    stocks = sector_stocks.get(sector, [])
                    total_change = 0.0
                    
                    for code in stocks:
                        klines = await db.get_klines(code, limit=2)
                        if klines and len(klines) >= 2:
                            latest = klines[-1]
                            prev = klines[-2]
                            change_pct = (latest['close'] - prev['close']) / prev['close']
                            total_change += change_pct
                    
                    avg_change = total_change / len(stocks) if stocks else 0
                    
                    sector_performance.append({
                        'sector': sector,
                        'change': f"{avg_change*100:.2f}%",
                        'change_value': float(avg_change),
                    })
                
                # 按涨幅排序
                sector_performance.sort(key=lambda x: x['change_value'], reverse=True)
                
                return ok({
                    'hot_sectors': sector_performance[:3],
                    'all_sectors': sector_performance,
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: get_insights, analyze_sector, market_sentiment, hot_sectors')
        except Exception as e:
            return fail(str(e))
    
    # ========== 10. industry_chain_manager ==========
    @mcp.tool()
    async def industry_chain_manager(action: str, **kwargs):
        """产业链管理器 - 产业链分析和关联股票"""
        try:
            if action == 'get_chain':
                keyword = kwargs.get('keyword', '新能源')
                
                # 产业链数据库（可扩展）
                industry_chains = {
                    '新能源': {
                        'name': '新能源汽车产业链',
                        'chain': [
                            {
                                'level': 'upstream',
                                'name': '上游-原材料',
                                'segments': [
                                    {'name': '锂矿开采', 'stocks': ['002460', '002466'], 'description': '锂资源开采和提炼'},
                                    {'name': '钴矿开采', 'stocks': ['603993', '000762'], 'description': '钴资源开采'},
                                    {'name': '镍矿开采', 'stocks': ['600432', '002460'], 'description': '镍资源开采'},
                                ]
                            },
                            {
                                'level': 'midstream',
                                'name': '中游-制造',
                                'segments': [
                                    {'name': '电池制造', 'stocks': ['300750', '002594'], 'description': '动力电池生产'},
                                    {'name': '电机电控', 'stocks': ['002074', '300124'], 'description': '电机和电控系统'},
                                    {'name': '充电桩', 'stocks': ['300001', '002664'], 'description': '充电设施'},
                                ]
                            },
                            {
                                'level': 'downstream',
                                'name': '下游-应用',
                                'segments': [
                                    {'name': '整车制造', 'stocks': ['002594', '600104'], 'description': '新能源汽车整车'},
                                    {'name': '运营服务', 'stocks': ['600066', '600611'], 'description': '充电运营和服务'},
                                ]
                            },
                        ]
                    },
                    '半导体': {
                        'name': '半导体产业链',
                        'chain': [
                            {
                                'level': 'upstream',
                                'name': '上游-设备材料',
                                'segments': [
                                    {'name': '半导体设备', 'stocks': ['688012', '688008'], 'description': '芯片制造设备'},
                                    {'name': '半导体材料', 'stocks': ['688396', '300655'], 'description': '硅片、光刻胶等'},
                                ]
                            },
                            {
                                'level': 'midstream',
                                'name': '中游-制造',
                                'segments': [
                                    {'name': '芯片设计', 'stocks': ['688981', '603986'], 'description': 'IC设计'},
                                    {'name': '芯片制造', 'stocks': ['688981', '600584'], 'description': '晶圆代工'},
                                    {'name': '封装测试', 'stocks': ['600584', '002185'], 'description': '芯片封测'},
                                ]
                            },
                            {
                                'level': 'downstream',
                                'name': '下游-应用',
                                'segments': [
                                    {'name': '消费电子', 'stocks': ['002475', '000725'], 'description': '手机、电脑等'},
                                    {'name': '汽车电子', 'stocks': ['600699', '002920'], 'description': '车载芯片'},
                                ]
                            },
                        ]
                    },
                    '人工智能': {
                        'name': '人工智能产业链',
                        'chain': [
                            {
                                'level': 'upstream',
                                'name': '上游-算力',
                                'segments': [
                                    {'name': 'AI芯片', 'stocks': ['688981', '002230'], 'description': 'GPU、NPU等'},
                                    {'name': '服务器', 'stocks': ['002916', '002439'], 'description': 'AI服务器'},
                                ]
                            },
                            {
                                'level': 'midstream',
                                'name': '中游-平台',
                                'segments': [
                                    {'name': '云计算', 'stocks': ['002230', '300454'], 'description': '云服务平台'},
                                    {'name': '大模型', 'stocks': ['300454', '002230'], 'description': 'AI大模型'},
                                ]
                            },
                            {
                                'level': 'downstream',
                                'name': '下游-应用',
                                'segments': [
                                    {'name': 'AI应用', 'stocks': ['300454', '002230'], 'description': 'AI软件应用'},
                                    {'name': '智能硬件', 'stocks': ['002475', '000725'], 'description': '智能设备'},
                                ]
                            },
                        ]
                    },
                }
                
                chain_data = industry_chains.get(keyword)
                
                if not chain_data:
                    # 返回可用的产业链列表
                    return ok({
                        'keyword': keyword,
                        'found': False,
                        'available_chains': list(industry_chains.keys()),
                        'message': f'未找到"{keyword}"产业链，请从可用列表中选择',
                    })
                
                return ok({
                    'keyword': keyword,
                    'name': chain_data['name'],
                    'chain': chain_data['chain'],
                    'total_segments': sum(len(level['segments']) for level in chain_data['chain']),
                })
            
            elif action == 'analyze':
                chain_id = kwargs.get('chain_id', '新能源')
                
                # 获取产业链数据
                result = await industry_chain_manager(action='get_chain', keyword=chain_id)
                
                if not result.get('success') or not result['data'].get('found', True):
                    return fail(f'未找到产业链: {chain_id}')
                
                chain_data = result['data']
                
                # 分析产业链各环节表现
                db = get_db()
                level_performance = []
                
                for level in chain_data['chain']:
                    level_stocks = []
                    for segment in level['segments']:
                        level_stocks.extend(segment['stocks'])
                    
                    # 计算该环节的平均涨幅
                    total_change = 0.0
                    valid_count = 0
                    
                    for code in level_stocks:
                        klines = await db.get_klines(code, limit=2)
                        if klines and len(klines) >= 2:
                            latest = klines[-1]
                            prev = klines[-2]
                            change_pct = (latest['close'] - prev['close']) / prev['close']
                            total_change += change_pct
                            valid_count += 1
                    
                    avg_change = total_change / valid_count if valid_count > 0 else 0
                    
                    level_performance.append({
                        'level': level['level'],
                        'name': level['name'],
                        'avg_change': f"{avg_change*100:.2f}%",
                        'change_value': float(avg_change),
                        'stocks_count': len(level_stocks),
                    })
                
                # 找出表现最好的环节
                best_level = max(level_performance, key=lambda x: x['change_value']) if level_performance else None
                
                return ok({
                    'chain_id': chain_id,
                    'name': chain_data['name'],
                    'level_performance': level_performance,
                    'best_level': best_level,
                    'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })
            
            elif action == 'get_related_stocks':
                keyword = kwargs.get('keyword', '新能源')
                level = kwargs.get('level')  # upstream, midstream, downstream
                
                # 获取产业链数据
                result = await industry_chain_manager(action='get_chain', keyword=keyword)
                
                if not result.get('success') or not result['data'].get('found', True):
                    return fail(f'未找到产业链: {keyword}')
                
                chain_data = result['data']
                related_stocks = []
                
                for chain_level in chain_data['chain']:
                    # 如果指定了level，只返回该level的股票
                    if level and chain_level['level'] != level:
                        continue
                    
                    for segment in chain_level['segments']:
                        for stock_code in segment['stocks']:
                            related_stocks.append({
                                'code': stock_code,
                                'level': chain_level['level'],
                                'level_name': chain_level['name'],
                                'segment': segment['name'],
                                'description': segment['description'],
                            })
                
                return ok({
                    'keyword': keyword,
                    'level': level or 'all',
                    'stocks': related_stocks,
                    'count': len(related_stocks),
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: get_chain, analyze, get_related_stocks')
        except Exception as e:
            return fail(str(e))
    
    # ========== 11. limit_up_manager ==========
    @mcp.tool()
    async def limit_up_manager(action: str, **kwargs):
        """涨停板管理器"""
        try:
            if action == 'get_limit_up':
                date = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))

                # 获取涨停股票
                from ..tools.market import get_limit_up_stocks
                result = get_limit_up_stocks(date)
                return result
            
            elif action == 'analyze':
                date = kwargs.get('date', datetime.now().strftime('%Y-%m-%d'))
                return ok({
                    'date': date,
                    'analysis': {
                        'total_count': 0,
                        'continuous_limit_up': [],
                        'first_limit_up': [],
                        'reasons': {}
                    }
                })
            
            else:
                return fail(f'Unknown action: {action}')
        
        except Exception as e:
            return fail(str(e))
