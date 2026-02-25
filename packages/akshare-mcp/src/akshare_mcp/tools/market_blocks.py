"""
市场板块工具 - 获取板块数据
数据源优先级: DB缓存 → TDX → 东方财富datacenter HTTP → AKShare
"""

import json
import urllib.request
from typing import Dict, Any, Optional, List
from ..storage.timescaledb import get_db
from ..data_source import data_source
from ..utils import safe_stderr_print, safe_float
from ..core.normalize import normalize_block_list, normalize_block_stock_list

try:
    import akshare as ak
except ImportError:
    ak = None

# 东方财富 datacenter API (datacenter-web 域名可通，push2 被 Clash DNS 劫持不通)
_EM_DC_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_EM_DC_REPORT = {
    'industry': 'RPT_BOARD_INDUSTRY_ALLCONS',
    'concept':  'RPT_BOARD_CONCEPT_ALLCONS',
}


def _fetch_em_blocks_direct(block_type: str) -> list:
    """通过东方财富 datacenter-web API 获取板块数据（该域名不受 Clash DNS 劫持影响）"""
    report = _EM_DC_REPORT.get(block_type)
    if not report:
        return []
    try:
        import requests
        params = {
            'reportName': report,
            'columns': 'BOARD_CODE,BOARD_NAME,CHANGE_RATE,DEAL_AMOUNT,LEAD_STOCK_CODE,LEAD_STOCK_NAME,BOARD_STOCK_NUM',
            'sortColumns': 'CHANGE_RATE',
            'sortTypes': -1,
            'pageSize': 500,
            'pageNumber': 1,
        }
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
        r = requests.get(_EM_DC_URL, params=params, headers=headers, timeout=10)
        data = r.json()
        result = data.get('result')
        items = result.get('data', []) if result else []
        if not items:
            return []
        blocks = []
        for it in items:
            blocks.append({
                'block_code': str(it.get('BOARD_CODE', '')),
                'block_name': str(it.get('BOARD_NAME', '')),
                'block_type': block_type,
                'stock_count': int(it.get('BOARD_STOCK_NUM', 0) or 0),
                'avg_change_pct': float(it.get('CHANGE_RATE', 0) or 0),
                'total_amount': float(it.get('DEAL_AMOUNT', 0) or 0),
                'leader_code': str(it.get('LEAD_STOCK_CODE', '') or ''),
                'leader_name': str(it.get('LEAD_STOCK_NAME', '') or ''),
            })
        return blocks
    except Exception as e:
        safe_stderr_print(f"[MarketBlocks] 东方财富datacenter失败: {e}")
        return []


async def _fetch_from_db(block_type: str, limit: Optional[int]) -> list:
    """从DB读取近期板块数据(30分钟内视为有效)"""
    try:
        db = get_db()
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT block_code, block_name, block_type, stock_count, "
                "avg_change_pct, total_amount, leader_code, leader_name "
                "FROM market_blocks WHERE block_type = $1 "
                "AND updated_at > NOW() - INTERVAL '30 minutes' "
                "ORDER BY avg_change_pct DESC LIMIT $2",
                block_type, limit or 500
            )
            return [dict(r) for r in rows] if rows else []
    except Exception as e:
        safe_stderr_print(f"[MarketBlocks] DB读取失败: {e}")
        return []


def _fetch_from_tdx(block_type: str) -> list:
    """从TDX获取板块列表 — 先快照算涨跌幅排序，再对top N补名称"""
    if block_type != 'industry' or not data_source.is_tdx_available():
        return []
    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return []
        codes = data_source.get_sector_list_tdxquant()
        if not codes:
            return []
        industry_codes = [c for c in codes if isinstance(c, str) and c.startswith('880')]
        # Phase 1: 快速获取所有板块快照(只需Now/LastClose算涨跌幅)
        raw = []
        for code in industry_codes:
            try:
                snap = tq.get_market_snapshot(stock_code=code)
                if not snap or snap.get('ErrorId') != '0':
                    continue
                now = safe_float(snap.get('Now', 0))
                last = safe_float(snap.get('LastClose', 0))
                if not now or not last:
                    continue
                chg_pct = round((now - last) / last * 100, 2)
                raw.append((code, chg_pct, safe_float(snap.get('Amount', 0))))
            except Exception:
                continue
        # 按涨跌幅绝对值降序，取top 50补名称
        raw.sort(key=lambda x: abs(x[1]), reverse=True)
        blocks = []
        for code, chg_pct, amount in raw[:50]:
            try:
                info = tq.get_stock_info(stock_code=code, field_list=['Name'])
                name = (info or {}).get('Name', '') if isinstance(info, dict) else ''
            except Exception:
                name = code.replace('.SH', '')
            blocks.append({
                'block_code': code.replace('.SH', ''),
                'block_name': name,
                'block_type': block_type,
                'stock_count': 0,
                'avg_change_pct': chg_pct,
                'total_amount': amount,
                'leader_code': None,
                'leader_name': None,
            })
        blocks.sort(key=lambda b: b['avg_change_pct'], reverse=True)
        return blocks
    except Exception as e:
        safe_stderr_print(f"[MarketBlocks] TDX失败: {e}")
        return []


def _fetch_from_akshare(block_type: str) -> list:
    """从AKShare获取(最后降级)"""
    if ak is None:
        return []
    try:
        fn = {'industry': ak.stock_board_industry_name_em,
              'concept': ak.stock_board_concept_name_em,
              'region': ak.stock_board_region_name_em}.get(block_type)
        if not fn:
            return []
        df = fn()
        if df is None or df.empty:
            return []
        blocks = []
        for _, row in df.iterrows():
            blocks.append({
                'block_code': str(row.get('板块代码', '')),
                'block_name': str(row.get('板块名称', '')),
                'block_type': block_type,
                'stock_count': int(row.get('公司数量', 0)),
                'avg_change_pct': float(row.get('涨跌幅', 0)),
                'total_amount': float(row.get('总成交额', 0)) if '总成交额' in row else None,
                'leader_code': str(row.get('领涨股票代码', '')) if '领涨股票代码' in row else None,
                'leader_name': str(row.get('领涨股票', '')) if '领涨股票' in row else None,
            })
        return blocks
    except Exception as e:
        safe_stderr_print(f"[MarketBlocks] AKShare失败: {e}")
        return []


async def get_market_blocks(
    block_type: str = 'industry',
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    获取市场板块数据
    数据源优先级: DB缓存(30min) → TDX → 东方财富直接HTTP → AKShare
    """
    if block_type not in ('industry', 'concept', 'region'):
        return {'success': False, 'error': f'Invalid block_type: {block_type}. Use: industry, concept, region'}

    source = 'none'
    blocks = []

    # 1. DB缓存
    blocks = await _fetch_from_db(block_type, limit)
    if blocks:
        source = 'db'

    # 2. TDX
    if not blocks:
        blocks = _fetch_from_tdx(block_type)
        if blocks:
            source = 'tdx'

    # 3. 东方财富直接HTTP(绕过代理)
    if not blocks:
        blocks = _fetch_em_blocks_direct(block_type)
        if blocks:
            source = 'eastmoney_direct'

    # 4. AKShare(最后降级)
    if not blocks:
        blocks = _fetch_from_akshare(block_type)
        if blocks:
            source = 'akshare'

    if not blocks:
        return {'success': False, 'error': '所有数据源均失败'}

    if limit:
        blocks = blocks[:limit]

    # 非DB来源时写入DB缓存
    if source != 'db':
        try:
            db = get_db()
            await _save_blocks_to_db(db, blocks)
        except Exception as e:
            safe_stderr_print(f"[MarketBlocks] 写DB失败: {e}")

    safe_stderr_print(f"[MarketBlocks] 成功获取 {len(blocks)} 个{block_type}板块 (source={source})")

    return {
        'success': True,
        'data': {
            'blocks': normalize_block_list(blocks),
            'count': len(blocks),
            'block_type': block_type,
            'source': source,
        }
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
        if ak is None:
            return {'success': False, 'error': 'akshare not available'}
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
                'stocks': normalize_block_stock_list(stocks),
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
        safe_stderr_print(f"[MarketBlocks] Failed to save to DB: {e}")
