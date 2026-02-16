"""选股器管理器 - 多因子选股"""

import json
import time
import asyncio
import logging
from ...storage import get_db
from ...utils import ok, fail, normalize_code

logger = logging.getLogger(__name__)

# 预置经典筛选策略（基于行业最佳实践）
PRESET_STRATEGIES = {
    'value_stocks': {
        'name': '价值股策略',
        'description': '低估值、高股息、稳健财务',
        'criteria': {
            'max_pe': 15,
            'max_pb': 1.5,
            'min_roe': 15,
            'max_debt_ratio': 0.3,
            'min_revenue_growth': 3
        },
        'source': '巴菲特价值投资理念'
    },
    'growth_stocks': {
        'name': '成长股策略',
        'description': '高增长、高ROE、合理估值',
        'criteria': {
            'min_revenue_growth': 20,
            'min_roe': 20,
            'max_pe': 30,
            'max_debt_ratio': 0.5
        },
        'source': '彼得·林奇成长投资'
    },
    'quality_stocks': {
        'name': '质量股策略',
        'description': '高ROE、低负债、稳定盈利',
        'criteria': {
            'min_roe': 20,
            'max_debt_ratio': 0.3,
            'min_revenue_growth': 10,
            'max_pe': 25
        },
        'source': '质量因子投资'
    },
    'dividend_stocks': {
        'name': '股息股策略',
        'description': '高股息、稳定分红、低估值',
        'criteria': {
            'min_dividend_yield': 4,
            'max_pe': 15,
            'min_roe': 10,
            'max_debt_ratio': 0.4
        },
        'source': '股息投资策略'
    },
    'momentum_stocks': {
        'name': '动量股策略',
        'description': '强势上涨、高成交量',
        'criteria': {
            'min_revenue_growth': 15,
            'min_roe': 15,
            'max_pe': 35
        },
        'source': '动量因子投资'
    }
}


def _normalize_kwargs(kwargs: dict) -> dict:
    extra = kwargs.get("kwargs")
    if extra is not None:
        if isinstance(extra, str):
            try:
                extra = json.loads(extra or "{}")
            except Exception:
                extra = None
        if isinstance(extra, dict):
            kwargs = {**kwargs, **extra}
    return kwargs


async def _get_stock_pool_with_klines(
    stock_codes: list,
    period: str = 'daily',
    limit: int = 100,
    max_concurrent: int = 3,
    per_stock_timeout: float = 15.0,
    total_timeout: float = 120.0,
    pool_cap: int = 100,
) -> dict:
    """
    批量异步获取股票池的K线数据（带超时保护与降载）

    返回 dict 包含:
      - stocks: 成功获取的股票数据列表
      - diagnostics: 诊断信息（pool_size, success_count, timeout_count, error_count, elapsed_ms）

    设计原则：
      1. 股票池截断到 pool_cap，避免无限制拉取
      2. 并发上限 max_concurrent（Semaphore），防止数据源过载
      3. 单股票超时 per_stock_timeout，超时跳过并记录
      4. 总任务超时 total_timeout，超时返回已完成的部分结果
      5. 任何异常只记录不抛出，保证返回部分结果
    """
    from ..tdx_formula import _get_kline_for_fallback

    # 截断股票池
    truncated = len(stock_codes) > pool_cap
    codes = stock_codes[:pool_cap]

    semaphore = asyncio.Semaphore(max_concurrent)
    success_count = 0
    timeout_count = 0
    error_count = 0

    async def fetch_one(code: str):
        nonlocal success_count, timeout_count, error_count
        async with semaphore:
            code = code.split('.')[0] if '.' in code else code
            code = normalize_code(code)
            try:
                klines = await asyncio.wait_for(
                    asyncio.to_thread(_get_kline_for_fallback, code, period, limit),
                    timeout=per_stock_timeout,
                )
                if klines:
                    klines = sorted(klines, key=lambda x: x.get('date', ''))
                    success_count += 1
                    return {'code': code, 'name': '', 'klines': klines}
                error_count += 1
                return None
            except asyncio.TimeoutError:
                timeout_count += 1
                logger.warning("Kline fetch timeout for %s (%.1fs)", code, per_stock_timeout)
                return None
            except Exception as e:
                error_count += 1
                logger.warning("Kline fetch error for %s: %s", code, e)
                return None

    t0 = time.monotonic()
    tasks = [asyncio.create_task(fetch_one(c)) for c in codes]

    try:
        done, pending = await asyncio.wait(tasks, timeout=total_timeout)
        # 取消超时未完成的任务
        for t in pending:
            t.cancel()
            timeout_count += 1
    except Exception as e:
        logger.error("_get_stock_pool_with_klines unexpected error: %s", e)
        done = set()

    elapsed_ms = round((time.monotonic() - t0) * 1000)
    results = []
    for t in done:
        try:
            r = t.result()
            if r and not isinstance(r, Exception):
                results.append(r)
        except Exception:
            error_count += 1

    diagnostics = {
        'pool_size': len(codes),
        'pool_truncated': truncated,
        'original_pool_size': len(stock_codes),
        'success_count': success_count,
        'timeout_count': timeout_count,
        'error_count': error_count,
        'elapsed_ms': elapsed_ms,
    }
    logger.info("Stock pool klines: %s", diagnostics)

    return {'stocks': results, 'diagnostics': diagnostics}


def register_screener_manager(mcp):
    """注册选股器管理器工具"""
    
    @mcp.tool()
    async def screener_manager(action: str, **kwargs):
        """选股器管理器 - 多因子选股"""
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'screen': '条件选股（需要 criteria）',
                        'list': '列出已保存的选股策略',
                        'save_strategy': '保存选股策略',
                        'run_strategy': '运行已保存策略',
                        'technical_screen': '技术面选股',
                        'list_conditions': '列出支持的选股条件',
                        'combined_screen': '组合选股',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'screen':
                criteria = kwargs.get('criteria', {})
                if isinstance(criteria, str):
                    try:
                        criteria = json.loads(criteria)
                    except Exception:
                        criteria = {}
                
                # 筛选条件
                min_market_cap = criteria.get('min_market_cap', 0)
                max_market_cap = criteria.get('max_market_cap', 1e12)
                min_pe = criteria.get('min_pe', 0)
                max_pe = criteria.get('max_pe', 100)
                min_pb = criteria.get('min_pb', 0)
                max_pb = criteria.get('max_pb', 10)
                min_roe = criteria.get('min_roe', 0)
                max_roe = criteria.get('max_roe', 100)
                min_revenue_growth = criteria.get('min_revenue_growth', -100)
                max_debt_ratio = criteria.get('max_debt_ratio', 100.0)
                sectors = criteria.get('sectors', [])

                # 单位归一化：DB 中 roe/debt_ratio 存储为百分比数值（如 15.0 表示 15%）
                # 用户可能传入小数形式（如 0.15 表示 15%），自动转换
                if 0 < min_roe < 1:
                    min_roe = min_roe * 100
                if 0 < max_debt_ratio < 1:
                    max_debt_ratio = max_debt_ratio * 100
                
                async with db.acquire() as conn:
                    # 兼容 financials 表为 stock_code 或 code 列
                    f_code_col = await db._financials_code_column(conn)
                    query = f"""
                        SELECT s.stock_code, s.stock_name, s.market_cap, s.pe_ratio, s.pb_ratio,
                               f.roe, f.revenue_growth, f.debt_ratio, s.industry
                        FROM stocks s
                        LEFT JOIN financials f ON s.stock_code = f.{f_code_col}
                        WHERE s.market_cap >= $1 AND s.market_cap <= $2
                          AND s.pe_ratio >= $3 AND s.pe_ratio <= $4
                          AND s.pb_ratio >= $5 AND s.pb_ratio <= $6
                    """
                    params = [min_market_cap, max_market_cap, min_pe, max_pe, min_pb, max_pb]
                    param_idx = 7
                    
                    if min_roe > 0:
                        query += f" AND f.roe >= ${param_idx}"
                        params.append(min_roe)
                        param_idx += 1
                    
                    if max_roe < 100:
                        query += f" AND f.roe <= ${param_idx}"
                        params.append(max_roe)
                        param_idx += 1
                    
                    if min_revenue_growth > -100:
                        query += f" AND f.revenue_growth >= ${param_idx}"
                        params.append(min_revenue_growth)
                        param_idx += 1
                    
                    if max_debt_ratio < 100.0:
                        query += f" AND f.debt_ratio <= ${param_idx}"
                        params.append(max_debt_ratio)
                        param_idx += 1
                    
                    if sectors:
                        placeholders = ','.join([f'${i}' for i in range(param_idx, param_idx + len(sectors))])
                        query += f" AND s.industry IN ({placeholders})"
                        params.extend(sectors)
                    
                    query += " ORDER BY s.market_cap DESC LIMIT 50"
                    
                    rows = await conn.fetch(query, *params)
                    stocks = [dict(row) for row in rows]
                
                # 计算综合评分
                for stock in stocks:
                    score = 0
                    
                    roe = stock.get('roe', 0) or 0
                    if roe > 20:
                        score += 30
                    elif roe > 15:
                        score += 20
                    elif roe > 10:
                        score += 10
                    
                    pe = stock.get('pe_ratio', 0) or 0
                    if 0 < pe < 15:
                        score += 30
                    elif pe < 25:
                        score += 20
                    elif pe < 35:
                        score += 10
                    
                    pb = stock.get('pb_ratio', 0) or 0
                    if 0 < pb < 2:
                        score += 20
                    elif pb < 3:
                        score += 10
                    
                    debt_ratio = stock.get('debt_ratio', 0) or 0
                    if debt_ratio < 0.3:
                        score += 20
                    elif debt_ratio < 0.5:
                        score += 10
                    
                    stock['score'] = score
                    stock['rating'] = 'A' if score >= 80 else ('B' if score >= 60 else ('C' if score >= 40 else 'D'))
                    # 向后兼容：统一输出 code/name 字段，避免仅有 stock_code/stock_name
                    stock['code'] = stock.get('stock_code') or stock.get('code')
                    stock['name'] = stock.get('stock_name') or stock.get('name') or ''
                
                stocks.sort(key=lambda x: x['score'], reverse=True)
                
                return ok({
                    'criteria': criteria,
                    'stocks': stocks,
                    'count': len(stocks),
                    'top_picks': stocks[:10],
                })
            
            elif action == 'save_strategy':
                name = kwargs.get('name')
                criteria = kwargs.get('criteria', {})
                user_id = kwargs.get('user_id', 'default')
                
                if not name:
                    return fail('需要提供策略名称')
                
                async with db.acquire() as conn:
                    strategy_id = await conn.fetchval(
                        """INSERT INTO screener_strategies (user_id, name, criteria, created_at)
                           VALUES ($1, $2, $3, NOW())
                           RETURNING id""",
                        user_id, name, json.dumps(criteria)
                    )
                return ok({
                    'strategy_id': strategy_id,
                    'name': name,
                    'user_id': user_id
                })
            
            elif action in ('list', 'list_strategies'):
                user_id = kwargs.get('user_id', 'default')
                
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT * FROM screener_strategies WHERE user_id = $1 ORDER BY created_at DESC",
                        user_id
                    )
                    user_strategies = [dict(row) for row in rows]
                
                # 合并预置策略和用户策略
                preset_list = [
                    {
                        'id': f'preset_{key}',
                        'name': value['name'],
                        'description': value['description'],
                        'criteria': value['criteria'],
                        'source': value['source'],
                        'type': 'preset'
                    }
                    for key, value in PRESET_STRATEGIES.items()
                ]
                
                return ok({
                    'preset_strategies': preset_list,
                    'user_strategies': user_strategies,
                    'total': len(preset_list) + len(user_strategies),
                    'message': '包含5个预置策略和用户自定义策略'
                })
            
            elif action == 'run_strategy':
                raw_strategy_id = kwargs.get('strategy_id')

                if raw_strategy_id is None or raw_strategy_id == '':
                    return fail('需要提供strategy_id')

                # 兼容 int/string：统一转字符串用于预置策略判断；用户策略ID再安全转int
                strategy_id_str = str(raw_strategy_id).strip()

                # 检查是否为预置策略
                if strategy_id_str.startswith('preset_'):
                    preset_key = strategy_id_str.replace('preset_', '')
                    if preset_key in PRESET_STRATEGIES:
                        preset = PRESET_STRATEGIES[preset_key]
                        result = await screener_manager(
                            action='screen',
                            criteria=preset['criteria']
                        )

                        if result.get('success') and isinstance(result.get('data'), dict):
                            result['data']['strategy_name'] = preset['name']
                            result['data']['strategy_id'] = strategy_id_str
                            result['data']['strategy_type'] = 'preset'

                        return result
                    else:
                        return fail(f'预置策略不存在: {preset_key}')

                # 用户自定义策略：ID 应为整数
                try:
                    strategy_id = int(strategy_id_str)
                except Exception:
                    return fail(f'无效的 strategy_id: {raw_strategy_id}（用户策略需为整数ID，或使用 preset_xxx）')

                async with db.acquire() as conn:
                    strategy = await conn.fetchrow(
                        "SELECT * FROM screener_strategies WHERE id = $1",
                        strategy_id
                    )

                    if not strategy:
                        return fail('策略不存在')

                criteria = json.loads(strategy['criteria']) if isinstance(strategy['criteria'], str) else strategy['criteria']

                result = await screener_manager(
                    action='screen',
                    criteria=criteria
                )

                if result.get('success') and isinstance(result.get('data'), dict):
                    result['data']['strategy_name'] = strategy['name']
                    result['data']['strategy_id'] = strategy_id
                    result['data']['strategy_type'] = 'user'

                return result
            
            elif action == 'technical_screen':
                # 技术面选股 — 使用增强选股引擎
                from ...services.screen_engine import engine as screen_engine
                from ...services import screen_conditions as _sc  # noqa: F401

                condition_ids = kwargs.get('conditions', [])
                if isinstance(condition_ids, str):
                    condition_ids = [c.strip() for c in condition_ids.split(',') if c.strip()]
                if not condition_ids:
                    return fail('需要提供 conditions 参数（条件ID列表）')

                logic = kwargs.get('logic', 'AND')
                params = kwargs.get('params', {})
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except Exception:
                        params = {}

                pool = kwargs.get('stock_pool', [])
                if isinstance(pool, str):
                    pool = [c.strip() for c in pool.split(',') if c.strip()]

                if not pool:
                    from ..tdx_formula import _get_default_stock_pool
                    pool = _get_default_stock_pool()

                # 异步并发获取K线数据（带超时保护）
                kline_result = await _get_stock_pool_with_klines(pool)
                stock_data = kline_result['stocks']
                diagnostics = kline_result['diagnostics']

                matched = screen_engine.scan(stock_data, condition_ids, logic, params)

                return ok({
                    'matched': matched,
                    'total': len(pool),
                    'matched_count': len(matched),
                    'conditions': condition_ids,
                    'logic': logic,
                    'diagnostics': diagnostics,
                    'message': f"技术选股完成，扫描 {diagnostics['success_count']}/{len(pool)} 只，命中 {len(matched)} 只"
                })

            elif action == 'list_conditions':
                from ...services.screen_engine import engine as screen_engine
                from ...services import screen_conditions as _sc  # noqa: F401

                category = kwargs.get('category')
                conditions = screen_engine.list_conditions(category)
                categories = screen_engine.list_categories()

                return ok({
                    'conditions': conditions,
                    'categories': categories,
                    'total': len(conditions),
                    'message': f"共 {len(conditions)} 个可用条件"
                })

            elif action == 'combined_screen':
                # 组合选股：基本面 + 技术面
                from ...services.screen_engine import engine as screen_engine
                from ...services import screen_conditions as _sc  # noqa: F401

                tech_conditions = kwargs.get('tech_conditions', [])
                if isinstance(tech_conditions, str):
                    tech_conditions = [c.strip() for c in tech_conditions.split(',') if c.strip()]

                fundamental_criteria = kwargs.get('fundamental_criteria', {})
                if isinstance(fundamental_criteria, str):
                    try:
                        fundamental_criteria = json.loads(fundamental_criteria)
                    except Exception:
                        fundamental_criteria = {}

                logic = kwargs.get('logic', 'AND')
                params = kwargs.get('params', {})
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except Exception:
                        params = {}

                # 第一步：基本面筛选（如果有条件）
                fundamental_codes = None
                if fundamental_criteria:
                    fund_result = await screener_manager(action='screen', criteria=fundamental_criteria)
                    if fund_result.get('success') and fund_result.get('data'):
                        stocks = fund_result['data'].get('stocks', [])
                        fundamental_codes = [s['stock_code'] for s in stocks]

                # 第二步：技术面筛选
                if tech_conditions:
                    from ..tdx_formula import _get_default_stock_pool

                    # 优先使用传入的 stock_pool，其次基本面结果，最后默认池
                    user_pool = kwargs.get('stock_pool', [])
                    if isinstance(user_pool, str):
                        user_pool = [c.strip() for c in user_pool.split(',') if c.strip()]

                    if user_pool:
                        pool = user_pool
                    elif fundamental_codes is not None:
                        pool = fundamental_codes
                    else:
                        pool = _get_default_stock_pool()

                    # 异步并发获取K线数据（带超时保护）
                    kline_result = await _get_stock_pool_with_klines(pool)
                    stock_data = kline_result['stocks']
                    diagnostics = kline_result['diagnostics']

                    matched = screen_engine.scan(stock_data, tech_conditions, logic, params)
                elif fundamental_codes is not None:
                    matched = [{'code': c, 'name': '', 'matched_conditions': []} for c in fundamental_codes]
                    diagnostics = None
                else:
                    return fail('需要提供 tech_conditions 或 fundamental_criteria')

                result_data = {
                    'matched': matched,
                    'matched_count': len(matched),
                    'fundamental_criteria': fundamental_criteria,
                    'tech_conditions': tech_conditions,
                    'logic': logic,
                    'message': f"组合选股完成，命中 {len(matched)} 只"
                }
                if diagnostics:
                    result_data['diagnostics'] = diagnostics
                return ok(result_data)

            else:
                return fail(
                    f'Unknown action: {action}. Supported: list, screen, '
                    f'save_strategy, run_strategy, technical_screen, '
                    f'list_conditions, combined_screen'
                )
        except Exception as e:
            return fail(str(e))
