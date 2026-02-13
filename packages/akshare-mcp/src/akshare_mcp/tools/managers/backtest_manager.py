"""回测管理器 - 运行、保存、查询回测结果（增强版）"""

import uuid
import json
from datetime import date, datetime
from ...storage import get_db
from ...utils import ok, fail, normalize_code
from ...data_source import data_source
import logging

logger = logging.getLogger(__name__)

def _normalize_kwargs(kwargs: dict) -> dict:
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
    if "code" not in kwargs or not kwargs.get("code"):
        kwargs["code"] = kwargs.get("Code") or kwargs.get("stock_code") or kwargs.get("symbol")
    return kwargs


def register_backtest_manager(mcp):
    """注册回测管理器工具"""
    
    @mcp.tool()
    async def backtest_manager(action: str, **kwargs):
        """回测管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/run/save/list/get/compare
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - run: code(str), strategy(str, "ma_cross"等), start_date(str, optional), end_date(str, optional)
                - save: backtest_id(str), name(str, optional)
                - list: limit(int, optional)
                - get: backtest_id(str)
                - compare: backtest_ids(list[str])

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            backtest_manager(action="help", kwargs="{}")
            # 运行均线交叉回测
            backtest_manager(action="run", kwargs='{"code":"600519","strategy":"ma_cross","short_period":5,"long_period":20}')
            # 列出回测记录
            backtest_manager(action="list", kwargs='{"limit":10}')
            # 对比多个回测
            backtest_manager(action="compare", kwargs='{"backtest_ids":["abc123","def456"]}')
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(kwargs)
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'run': '运行回测（需要 code, 可选 strategy/start_date/end_date）',
                        'save': '保存回测结果',
                        'list': '列出回测记录',
                        'get': '获取回测详情（需要 backtest_id）',
                        'compare': '对比回测（需要 backtest_ids）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'run':
                code = kwargs.get('code')
                strategy = kwargs.get('strategy', 'ma_cross')
                
                if not code:
                    return fail('需要提供股票代码')
                
                code = normalize_code(code)
                
                # 1. 获取K线数据
                limit = kwargs.get('limit', 250)
                klines = await db.get_klines(code, limit=limit)
                
                if not klines:
                    logger.info(f"[BacktestManager] Fetching klines for {code}")
                    klines = data_source.get_kline(code, 'daily', limit)
                    
                    if klines:
                        try:
                            await db.save_klines(code, klines)
                        except Exception as e:
                            logger.warning(f"[BacktestManager] Failed to save klines: {e}")
                
                if not klines or len(klines) < 50:
                    return fail(f'K线数据不足，无法回测（需要至少50天数据，当前{len(klines) if klines else 0}天）')
                
                # 2. 运行回测
                from ...services.backtest import backtest_engine
                
                initial_capital = kwargs.get('initial_capital', 100000)
                commission_rate = kwargs.get('commission_rate', kwargs.get('commission', 0.0003))
                slippage = kwargs.get('slippage', 0.0)
                benchmark_code = (kwargs.get('benchmark') or '000300').strip()

                benchmark_klines = []
                if benchmark_code:
                    benchmark_normalized = normalize_code(benchmark_code)
                    benchmark_klines = await db.get_klines(benchmark_normalized, limit=limit)
                    if not benchmark_klines:
                        try:
                            benchmark_klines = data_source.get_kline(benchmark_normalized, 'daily', limit)
                        except Exception as e:
                            logger.warning(f"[BacktestManager] Failed to fetch benchmark klines: {e}")
                            benchmark_klines = []

                supported_strategies = ['ma_cross', 'buy_and_hold', 'momentum', 'rsi']
                if strategy not in supported_strategies:
                    return fail(f'不支持的策略: {strategy}，支持: {", ".join(supported_strategies)}')

                params = {
                    'initial_capital': initial_capital,
                    'commission': commission_rate,
                    'slippage': slippage,
                    'benchmark': benchmark_code,
                    'benchmark_klines': benchmark_klines,
                    'short_period': kwargs.get('short_period', 5),
                    'long_period': kwargs.get('long_period', 20),
                    'lookback': kwargs.get('lookback', 20),
                    'threshold': kwargs.get('threshold', 0.02),
                    'rsi_period': kwargs.get('rsi_period', 14),
                    'oversold': kwargs.get('oversold', 30),
                    'overbought': kwargs.get('overbought', 70),
                }

                result = backtest_engine.run_backtest(
                    code=code,
                    klines=klines,
                    strategy=strategy,
                    params=params,
                )
                
                if not result.get('success'):
                    return fail(result.get('error', '回测执行失败'))
                
                result = result.get('data', result)
                
                # 3. 保存回测结果
                backtest_id = str(uuid.uuid4())[:8]
                
                # 解析日期，兼容 date 对象和字符串
                def _safe_date(val):
                    if isinstance(val, date):
                        return val
                    if isinstance(val, str):
                        for fmt in ('%Y-%m-%d', '%Y%m%d', '%Y/%m/%d'):
                            try:
                                return datetime.strptime(val, fmt).date()
                            except Exception:
                                continue
                    return date.today()
                
                start_dt = _safe_date(klines[0].get('date')) if klines else date.today()
                end_dt = _safe_date(klines[-1].get('date')) if klines else date.today()
                
                # 确保 start_date <= end_date（防止K线未排序导致日期反转）
                if start_dt > end_dt:
                    start_dt, end_dt = end_dt, start_dt
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO backtest_results 
                           (id, code, strategy, params, start_date, end_date, initial_capital, final_capital, 
                            total_return, sharpe_ratio, max_drawdown, created_at)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())""",
                        backtest_id, code, strategy, str(kwargs),
                        start_dt, end_dt,
                        initial_capital,
                        result.get('final_capital', initial_capital),
                        result.get('total_return', 0),
                        result.get('sharpe_ratio', 0),
                        result.get('max_drawdown', 0)
                    )
                
                return ok({
                    'backtest_id': backtest_id,
                    'code': code,
                    'strategy': strategy,
                    'result': result,
                    'data_points': len(klines)
                })
            
            elif action == 'save':
                code = kwargs.get('code')
                strategy = kwargs.get('strategy')
                params = kwargs.get('params', {})
                result = kwargs.get('result', {})
                
                backtest_id = str(uuid.uuid4())[:8]
                
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO backtest_results 
                           (id, code, strategy, params, start_date, end_date, initial_capital, final_capital, 
                            total_return, sharpe_ratio, max_drawdown, created_at)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())""",
                        backtest_id, code, strategy, str(params),
                        result.get('start_date', date.today()), 
                        result.get('end_date', date.today()),
                        result.get('initial_capital', 100000),
                        result.get('final_capital', 100000),
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
                    results = []
                    for row in rows:
                        r = dict(row)
                        # 序列化 date/datetime 对象为字符串
                        for k, v in r.items():
                            if isinstance(v, datetime):
                                r[k] = v.isoformat()
                            elif isinstance(v, date):
                                r[k] = v.isoformat()
                        # 确保 start_date <= end_date
                        sd = r.get('start_date', '')
                        ed = r.get('end_date', '')
                        if sd and ed and str(sd) > str(ed):
                            r['start_date'], r['end_date'] = ed, sd
                        results.append(r)
                
                return ok({'results': results, 'count': len(results)})
            
            elif action == 'get':
                backtest_id = kwargs.get('backtest_id')
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM backtest_results WHERE id = $1",
                        backtest_id
                    )
                    if not row:
                        return fail('回测结果不存在')
                    result = dict(row)
                
                return ok(result)
            
            elif action == 'compare':
                backtest_ids = kwargs.get('backtest_ids', [])
                if not backtest_ids:
                    return fail('需要提供回测ID列表')
                
                comparison = []
                async with db.acquire() as conn:
                    for bid in backtest_ids[:5]:  # 限制最多5个
                        row = await conn.fetchrow(
                            "SELECT * FROM backtest_results WHERE id = $1",
                            bid
                        )
                        if row:
                            comparison.append(dict(row))
                
                return ok({
                    'comparison': comparison,
                    'count': len(comparison)
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, run, save, list, get, compare')
        
        except Exception as e:
            logger.error(f"[BacktestManager] Error: {e}")
            return fail(str(e))
