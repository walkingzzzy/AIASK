"""
市场板块工具 - 获取板块数据
"""

from typing import Dict, Any, Optional, List
import akshare as ak
from ..storage.timescaledb import get_db


async def get_market_blocks(
    block_type: str = 'industry',
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    获取市场板块数据
    
    Args:
        block_type: 板块类型 (industry=行业, concept=概念, region=地域)
        limit: 限制返回数量
    
    Returns:
        板块数据列表
    """
    try:
        # 从东方财富获取板块数据
        if block_type == 'industry':
            df = ak.stock_board_industry_name_em()
        elif block_type == 'concept':
            df = ak.stock_board_concept_name_em()
        elif block_type == 'region':
            df = ak.stock_board_region_name_em()
        else:
            return {
                'success': False,
                'error': f'Invalid block_type: {block_type}. Use: industry, concept, region'
            }
        
        if df is None or df.empty:
            return {'success': False, 'error': 'No data returned'}
        
        # 转换为标准格式
        blocks = []
        for _, row in df.iterrows():
            block = {
                'block_code': str(row.get('板块代码', '')),
                'block_name': str(row.get('板块名称', '')),
                'block_type': block_type,
                'stock_count': int(row.get('公司数量', 0)),
                'avg_change_pct': float(row.get('涨跌幅', 0)),
                'total_amount': float(row.get('总成交额', 0)) if '总成交额' in row else None,
                'leader_code': str(row.get('领涨股票代码', '')) if '领涨股票代码' in row else None,
                'leader_name': str(row.get('领涨股票', '')) if '领涨股票' in row else None,
            }
            blocks.append(block)
        
        # 限制返回数量
        if limit:
            blocks = blocks[:limit]
        
        # 保存到数据库
        db = get_db()
        await _save_blocks_to_db(db, blocks)
        
        return {
            'success': True,
            'data': {
                'blocks': blocks,
                'count': len(blocks),
                'block_type': block_type,
            }
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to get market blocks: {str(e)}'
        }


async def get_block_stocks(block_code: str) -> Dict[str, Any]:
    """
    获取板块成分股
    
    Args:
        block_code: 板块代码
    
    Returns:
        成分股列表
    """
    try:
        # 从东方财富获取板块成分股
        df = ak.stock_board_industry_cons_em(symbol=block_code)
        
        if df is None or df.empty:
            return {'success': False, 'error': 'No stocks found in block'}
        
        stocks = []
        for _, row in df.iterrows():
            stock = {
                'stock_code': str(row.get('代码', '')),
                'stock_name': str(row.get('名称', '')),
                'change_pct': float(row.get('涨跌幅', 0)),
                'price': float(row.get('最新价', 0)),
                'volume': int(row.get('成交量', 0)),
                'amount': float(row.get('成交额', 0)),
            }
            stocks.append(stock)
        
        return {
            'success': True,
            'data': {
                'block_code': block_code,
                'stocks': stocks,
                'count': len(stocks),
            }
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Failed to get block stocks: {str(e)}'
        }


async def _save_blocks_to_db(db, blocks: List[Dict[str, Any]]) -> None:
    """保存板块数据到数据库"""
    try:
        async with db.acquire() as conn:
            for block in blocks:
                await conn.execute("""
                    INSERT INTO market_blocks (
                        block_code, block_name, block_type, stock_count,
                        avg_change_pct, total_amount, leader_code, leader_name, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    ON CONFLICT (block_code, block_type) DO UPDATE SET
                        block_name = EXCLUDED.block_name,
                        stock_count = EXCLUDED.stock_count,
                        avg_change_pct = EXCLUDED.avg_change_pct,
                        total_amount = EXCLUDED.total_amount,
                        leader_code = EXCLUDED.leader_code,
                        leader_name = EXCLUDED.leader_name,
                        updated_at = NOW()
                """, 
                    block['block_code'],
                    block['block_name'],
                    block['block_type'],
                    block['stock_count'],
                    block['avg_change_pct'],
                    block['total_amount'],
                    block['leader_code'],
                    block['leader_name']
                )
    except Exception as e:
        print(f"[MarketBlocks] Failed to save to DB: {e}")
