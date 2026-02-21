"""板块管理器 - 板块轮动、板块分析"""

import json
import numpy as np
from ...storage import get_db
from ...utils import ok, fail


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


def register_sector_manager(mcp):
    """注册板块管理器工具"""
    
    @mcp.tool()
    async def sector_manager(action: str, **kwargs):
        """板块管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list_sectors/sector_performance/sector_rotation/sector_correlation
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list_sectors: block_type(str, optional, "industry"/"concept"/"region")
                - sector_performance: sector(str, optional), days(int, optional)
                - sector_rotation: days(int, optional)
                - sector_correlation: sectors(list[str], optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            sector_manager(action="help", kwargs="{}")
            # 列出行业板块
            sector_manager(action="list_sectors", kwargs='{"block_type":"industry"}')
            # 板块轮动分析
            sector_manager(action="sector_rotation", kwargs='{"days":30}')
            # 板块相关性分析
            sector_manager(action="sector_correlation", kwargs="{}")
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'list_sectors': '列出板块列表',
                        'sector_performance': '板块表现分析（需要 sector/block_code）',
                        'sector_rotation': '板块轮动分析',
                        'sector_correlation': '板块相关性分析',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'list_sectors':
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT DISTINCT block_code, block_name, block_type FROM market_blocks ORDER BY block_name"
                    )
                    sectors = [dict(row) for row in rows]
                
                return ok({
                    'sectors': sectors,
                    'count': len(sectors)
                })
            
            elif action == 'sector_performance':
                period = kwargs.get('period', 20)
                sector_type = kwargs.get('type', 'industry')
                
                async with db.acquire() as conn:
                    sectors = await conn.fetch(
                        "SELECT block_code, block_name FROM market_blocks WHERE block_type = $1 LIMIT 20",
                        sector_type
                    )
                
                # DB 无板块数据时自动拉取
                if not sectors:
                    try:
                        from ..market_blocks import get_market_blocks
                        blocks_res = await get_market_blocks(block_type=sector_type, limit=20)
                        if blocks_res.get('success') and blocks_res.get('data', {}).get('blocks'):
                            # 重新从 DB 读取（get_market_blocks 已写入 DB）
                            async with db.acquire() as conn:
                                sectors = await conn.fetch(
                                    "SELECT block_code, block_name FROM market_blocks WHERE block_type = $1 LIMIT 20",
                                    sector_type
                                )
                            # 如果 DB 仍为空，直接用返回数据构造（camelCase output）
                            if not sectors:
                                fetched = blocks_res['data']['blocks'][:20]
                                sectors = [
                                    {'block_code': b.get('blockCode') or b.get('block_code'), 'block_name': b.get('blockName') or b.get('block_name')}
                                    for b in fetched if b.get('blockCode') or b.get('block_code')
                                ]
                    except Exception:
                        pass
                
                sector_performance = []
                
                for sector in sectors:
                    block_code = sector['block_code']
                    block_name = sector['block_name']
                    
                    async with db.acquire() as conn:
                        stocks = await conn.fetch(
                            "SELECT stock_code FROM block_stocks WHERE block_code = $1",
                            block_code
                        )
                    
                    if not stocks:
                        continue
                    
                    total_return = 0
                    valid_count = 0
                    
                    for stock in stocks[:10]:
                        code = stock['stock_code']
                        klines = await db.get_klines(code, limit=period + 1)
                        
                        if len(klines) >= 2:
                            start_price = klines[0]['close']
                            end_price = klines[-1]['close']
                            stock_return = (end_price - start_price) / start_price
                            total_return += stock_return
                            valid_count += 1
                    
                    if valid_count > 0:
                        avg_return = total_return / valid_count

                        sector_performance.append({
                            'blockCode': block_code,
                            'blockName': block_name,
                            'return': float(avg_return),
                            'returnPct': f"{avg_return*100:.2f}%",
                            'stocksCount': valid_count,
                            'strength': 'strong' if avg_return > 0.1 else ('weak' if avg_return < -0.05 else 'medium')
                        })
                
                sector_performance.sort(key=lambda x: x['return'], reverse=True)
                
                return ok({
                    'period': period,
                    'sectors': sector_performance,
                    'top_sectors': sector_performance[:5],
                    'bottom_sectors': sector_performance[-5:] if len(sector_performance) > 5 else [],
                })
            
            elif action == 'sector_rotation':
                period = kwargs.get('period', 20)
                
                performance_result = await sector_manager(
                    action='sector_performance',
                    period=period
                )
                
                sectors = []
                if performance_result.get('success') and performance_result.get('data'):
                    sectors = performance_result['data'].get('sectors', [])
                
                # 如果 sector_performance 返回空，直接用 get_market_blocks 的涨跌幅数据
                if not sectors:
                    try:
                        from ..market_blocks import get_market_blocks
                        blocks_res = await get_market_blocks(block_type='industry', limit=20)
                        if blocks_res.get('success') and blocks_res.get('data', {}).get('blocks'):
                            for b in blocks_res['data']['blocks']:
                                avg_chg = float(b.get('avgChangePct') or b.get('avg_change_pct') or 0)
                                sectors.append({
                                    'blockCode': b.get('blockCode') or b.get('block_code', ''),
                                    'blockName': b.get('blockName') or b.get('block_name', ''),
                                    'return': avg_chg / 100.0,
                                    'returnPct': f"{avg_chg:.2f}%",
                                    'stocksCount': b.get('stockCount') or b.get('stock_count', 0),
                                    'strength': 'strong' if avg_chg > 2 else ('weak' if avg_chg < -1 else 'medium')
                                })
                            sectors.sort(key=lambda x: x['return'], reverse=True)
                    except Exception:
                        pass
                
                if not sectors:
                    return ok({
                        'period': period,
                        'message': '无板块数据，请先获取板块信息',
                        'strong_sectors': [],
                        'weak_sectors': [],
                        'rotation_advice': [],
                        'market_style': 'unknown'
                    })
                
                total_count = len(sectors)
                strong_count = max(1, int(total_count * 0.3))
                weak_count = max(1, int(total_count * 0.3))
                
                strong_sectors = sectors[:strong_count]
                weak_sectors = sectors[-weak_count:]
                
                rotation_advice = []
                
                for sector in strong_sectors:
                    rotation_advice.append({
                        'sector': sector.get('blockName') or sector.get('block_name', ''),
                        'action': 'overweight',
                        'reason': f"板块表现强势，{period}日涨幅{sector.get('returnPct') or sector.get('return_pct', '')}"
                    })

                for sector in weak_sectors:
                    rotation_advice.append({
                        'sector': sector.get('blockName') or sector.get('block_name', ''),
                        'action': 'underweight',
                        'reason': f"板块表现弱势，{period}日涨幅{sector.get('returnPct') or sector.get('return_pct', '')}"
                    })
                
                top_return = strong_sectors[0]['return']
                return ok({
                    'period': period,
                    'strong_sectors': strong_sectors,
                    'weak_sectors': weak_sectors,
                    'rotation_advice': rotation_advice,
                    'market_style': 'growth' if top_return > 0.15 else (
                        'value' if top_return < 0.05 else 'balanced'
                    )
                })
            
            elif action == 'sector_correlation':
                sectors = kwargs.get('sectors', [])
                period = kwargs.get('period', 60)
                
                if len(sectors) < 2:
                    return fail('需要至少2个板块代码')
                
                sector_returns = {}
                
                for sector_code in sectors:
                    async with db.acquire() as conn:
                        stocks = await conn.fetch(
                            "SELECT stock_code FROM block_stocks WHERE block_code = $1 LIMIT 5",
                            sector_code
                        )
                    
                    if not stocks:
                        continue
                    
                    daily_returns = []
                    
                    for i in range(period):
                        day_return = 0
                        valid_count = 0
                        
                        for stock in stocks:
                            code = stock['stock_code']
                            klines = await db.get_klines(code, limit=period + 1)
                            
                            if len(klines) > i + 1:
                                ret = (klines[-(i+1)]['close'] - klines[-(i+2)]['close']) / klines[-(i+2)]['close']
                                day_return += ret
                                valid_count += 1
                        
                        if valid_count > 0:
                            daily_returns.append(day_return / valid_count)
                    
                    sector_returns[sector_code] = daily_returns
                
                correlation_matrix = {}
                
                for sector1 in sectors:
                    if sector1 not in sector_returns:
                        continue
                    
                    correlation_matrix[sector1] = {}
                    
                    for sector2 in sectors:
                        if sector2 not in sector_returns:
                            continue
                        
                        if len(sector_returns[sector1]) > 0 and len(sector_returns[sector2]) > 0:
                            min_len = min(len(sector_returns[sector1]), len(sector_returns[sector2]))
                            corr = np.corrcoef(
                                sector_returns[sector1][:min_len],
                                sector_returns[sector2][:min_len]
                            )[0, 1]
                            correlation_matrix[sector1][sector2] = float(corr)
                        else:
                            correlation_matrix[sector1][sector2] = 0.0
                
                return ok({
                    'sectors': sectors,
                    'period': period,
                    'correlation_matrix': correlation_matrix,
                    'interpretation': {
                        'high_correlation': '>0.7表示高度相关',
                        'low_correlation': '<0.3表示低相关',
                        'negative_correlation': '<0表示负相关'
                    }
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, list_sectors, sector_performance, sector_rotation, sector_correlation')
        except Exception as e:
            return fail(str(e))
