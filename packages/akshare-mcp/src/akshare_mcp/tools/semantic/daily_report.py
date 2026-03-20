"""每日市场报告 — generate_daily_report"""

import statistics
from typing import Optional
from datetime import datetime
from ...storage import get_db
from ...utils import ok, fail
from ...data_source import data_source


def _parse_date_like(value: Optional[str]):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except Exception:
            continue
    return None


def _normalize_hot_sector_item(item: dict) -> dict:
    return {
        'name': str(
            item.get('name')
            or item.get('blockName')
            or item.get('block_name')
            or ''
        ),
        'change_pct': round(float(
            item.get('change_pct')
            or item.get('avgChange')
            or item.get('avgChangePct')
            or item.get('avg_change_pct')
            or 0
        ), 2),
        'stock_count': int(
            item.get('stock_count')
            or item.get('stockCount')
            or item.get('stocksCount')
            or 0
        ),
    }


async def generate_daily_report(date: Optional[str] = None):
    """
    生成每日市场报告 - 聚合指数、板块、资金流向、涨跌统计等数据

    数据源优先级: TimescaleDB → Tushare Pro → AkShare（降级）

    Args:
        date (str, optional): 日期，格式 YYYY-MM-DD，不填则使用当前日期

    Returns:
        dict: {"success": bool, "data": {
            "date": str,
            "market_summary": dict,       # 主要指数行情 {代码: {name, close, change_pct, volume, amount}}
            "stats": dict,                # 涨跌统计 {up_count, down_count, limit_up_count, limit_down_count, total_count}
            "hot_sectors": list[dict],    # 热门板块 [{name, change_pct, stock_count}]
            "capital_flow": dict,         # 资金流向 {north_fund: {net_inflow, sh_connect, sz_connect}, main_fund: {...}}
            "sentiment": str,             # 市场情绪 "bullish"|"bearish"|"neutral"
            "highlights": list[str],      # 市场要点
            "outlook": str,               # 后市展望
            "generated_at": str
        }}

    Errors:
        - 非交易日或数据源不可用时部分字段可能为空/零值

    Examples:
        generate_daily_report()
        generate_daily_report("2026-01-15")
    """
    try:
        db = get_db()
        report_date = date or datetime.now().strftime('%Y-%m-%d')

        # 1. 市场概况
        market_summary = _fetch_index_quotes()

        # 2. 涨跌统计
        stats = await _fetch_stats(db, report_date)

        # 3. 热门板块
        hot_sectors = await _fetch_hot_sectors(db)

        # 4. 资金流向
        capital_flow = _fetch_capital_flow(report_date)

        # 5. 市场情绪
        sentiment = 'neutral'
        if market_summary:
            avg_change = statistics.mean([v['change_pct'] for v in market_summary.values()])
            if avg_change > 1:
                sentiment = 'bullish'
            elif avg_change < -1:
                sentiment = 'bearish'

        # 6. 生成要点
        highlights = []
        if market_summary:
            avg_change = statistics.mean([v['change_pct'] for v in market_summary.values()])
            if avg_change > 0:
                highlights.append(f'市场整体上涨{abs(avg_change):.2f}%，情绪偏暖')
            else:
                highlights.append(f'市场整体下跌{abs(avg_change):.2f}%，情绪偏冷')

        if stats['limit_up_count'] > 30:
            highlights.append(f'涨停{stats["limit_up_count"]}只，市场活跃度高')

        if hot_sectors:
            top_sector = hot_sectors[0]
            highlights.append(f'{top_sector["name"]}板块领涨，涨幅{top_sector["change_pct"]}%')

        if stats['up_count'] > stats['down_count'] * 1.5:
            highlights.append('上涨家数明显多于下跌，市场赚钱效应好')
        elif stats['down_count'] > stats['up_count'] * 1.5:
            highlights.append('下跌家数明显多于上涨，市场亏钱效应明显')

        # 7. 后市展望
        if sentiment == 'bullish':
            outlook = '短期市场情绪偏暖，关注热门板块机会，注意追高风险'
        elif sentiment == 'bearish':
            outlook = '短期市场情绪偏冷，建议控制仓位，等待企稳信号'
        else:
            outlook = '市场震荡整理，建议观望为主，等待方向明朗'

        return ok({
            'date': report_date,
            'market_summary': market_summary,
            'stats': stats,
            'hot_sectors': hot_sectors,
            'capital_flow': capital_flow,
            'sentiment': sentiment,
            'highlights': highlights,
            'outlook': outlook,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        return fail(str(e))


# --------------- 内部辅助 ---------------

def _fetch_index_quotes() -> dict:
    """获取主要指数行情"""
    market_summary = {}
    index_codes = {
        '000001': '上证指数',
        '399001': '深证成指',
        '399006': '创业板指'
    }
    from ..market import get_index_quote as _get_idx_quote
    for code, name in index_codes.items():
        try:
            idx_res = _get_idx_quote(code)
            if idx_res and idx_res.get('success') and idx_res.get('data'):
                idx_data = idx_res['data']
                market_summary[code] = {
                    'name': name,
                    'close': idx_data.get('price') or idx_data.get('close', 0),
                    'change_pct': round(float(idx_data.get('changePercent') or idx_data.get('change_pct') or 0), 2),
                    'volume': idx_data.get('volume', 0),
                    'amount': idx_data.get('amount', 0)
                }
        except Exception:
            pass
    return market_summary


async def _fetch_stats(db, report_date: str) -> dict:
    """获取涨跌统计"""
    stats = {
        'up_count': 0, 'down_count': 0,
        'limit_up_count': 0, 'limit_down_count': 0, 'total_count': 0
    }
    try:
        async with db.acquire() as conn:
            up_count = await conn.fetchval(
                "SELECT COUNT(*) FROM stock_quotes WHERE time::date = $1 AND change_pct > 0",
                report_date
            ) or 0
            down_count = await conn.fetchval(
                "SELECT COUNT(*) FROM stock_quotes WHERE time::date = $1 AND change_pct < 0",
                report_date
            ) or 0
            limit_up_count = await conn.fetchval(
                "SELECT COUNT(*) FROM stock_quotes WHERE time::date = $1 AND change_pct >= 9.9",
                report_date
            ) or 0
            limit_down_count = await conn.fetchval(
                "SELECT COUNT(*) FROM stock_quotes WHERE time::date = $1 AND change_pct <= -9.9",
                report_date
            ) or 0
            stats = {
                'up_count': up_count, 'down_count': down_count,
                'limit_up_count': limit_up_count, 'limit_down_count': limit_down_count,
                'total_count': up_count + down_count
            }
    except Exception:
        pass

    # DB 无数据时，尝试 Tushare
    if stats['total_count'] == 0:
        try:
            ts_pro = data_source.get_tushare_pro()
            if ts_pro:
                zt_date = report_date.replace('-', '') if isinstance(report_date, str) else str(report_date).replace('-', '')
                import datetime as _dt
                base_date = _dt.datetime.strptime(zt_date, '%Y%m%d')
                for days_back in range(7):
                    check_date = (base_date - _dt.timedelta(days=days_back)).strftime('%Y%m%d')
                    try:
                        df_daily = ts_pro.daily(trade_date=check_date, fields='ts_code,pct_chg')
                        if df_daily is not None and not df_daily.empty and len(df_daily) > 100:
                            up = int((df_daily['pct_chg'] > 0).sum())
                            down = int((df_daily['pct_chg'] < 0).sum())
                            limit_up = int((df_daily['pct_chg'] >= 9.9).sum())
                            limit_down = int((df_daily['pct_chg'] <= -9.9).sum())
                            stats = {
                                'up_count': up, 'down_count': down,
                                'limit_up_count': limit_up, 'limit_down_count': limit_down,
                                'total_count': up + down
                            }
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    # 仍无数据时，尝试涨停板接口
    if stats['limit_up_count'] == 0:
        try:
            from ..market.limit_up import get_limit_up_stocks as _get_zt
            zt_date = report_date.replace('-', '') if isinstance(report_date, str) else report_date
            zt_res = _get_zt(date=str(zt_date))
            if zt_res.get('success') and zt_res.get('data'):
                zt_data = zt_res['data']
                if isinstance(zt_data, list):
                    stats['limit_up_count'] = len(zt_data)
        except Exception:
            pass

    return stats


async def _fetch_hot_sectors(db) -> list:
    """获取热门板块"""
    hot_sectors = []
    try:
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """SELECT block_name, avg_change_pct, stock_count
                   FROM market_blocks
                   WHERE block_name IS NOT NULL AND block_name != ''
                   ORDER BY avg_change_pct DESC NULLS LAST
                   LIMIT 5"""
            )
            for row in rows:
                hot_sectors.append({
                    'name': row['block_name'],
                    'change_pct': round(float(row['avg_change_pct'] or 0), 2),
                    'stock_count': row['stock_count'] or 0
                })
    except Exception:
        pass

    if not hot_sectors:
        try:
            from ..market_blocks import get_market_blocks
            blocks_res = await get_market_blocks(block_type='industry', limit=5)
            if blocks_res.get('success') and blocks_res.get('data', {}).get('blocks'):
                for b in blocks_res['data']['blocks'][:5]:
                    normalized = _normalize_hot_sector_item(b)
                    if normalized['name']:
                        hot_sectors.append(normalized)
        except Exception:
            pass

    return hot_sectors


def _fetch_capital_flow(report_date: str) -> dict:
    """获取资金流向"""
    capital_flow = {
        'north_fund': {'net_inflow': 0, 'sh_connect': 0, 'sz_connect': 0},
        'main_fund': {'net_inflow': 0, 'buy': 0, 'sell': 0}
    }
    try:
        from ..fund_flow import get_north_fund
        nf_res = get_north_fund(days=1)
        if nf_res and nf_res.get('success') and nf_res.get('data'):
            nf_data = nf_res['data']
            items = nf_data.get('items', []) if isinstance(nf_data, dict) else nf_data
            report_dt = _parse_date_like(report_date)
            latest_date = _parse_date_like(items[-1].get('date')) if isinstance(items, list) and items else None
            source_name = str(nf_data.get('source') or '') if isinstance(nf_data, dict) else ''
            is_stale = bool(nf_data.get('stale')) if isinstance(nf_data, dict) else False
            is_fresh_enough = (
                report_dt is not None
                and latest_date is not None
                and abs((report_dt - latest_date).days) <= 3
            )
            if (
                isinstance(items, list)
                and len(items) > 0
                and not is_stale
                and not source_name.endswith('_stale')
                and is_fresh_enough
            ):
                latest = items[-1]
                capital_flow['north_fund'] = {
                    'net_inflow': latest.get('total', 0),
                    'sh_connect': latest.get('shConnect', 0),
                    'sz_connect': latest.get('szConnect', 0),
                }
    except Exception:
        pass

    # 尝试 Tushare 获取主力资金
    try:
        ts_pro = data_source.get_tushare_pro()
        if ts_pro:
            import datetime as _dt2
            zt_date2 = report_date.replace('-', '') if isinstance(report_date, str) else str(report_date).replace('-', '')
            base_date2 = _dt2.datetime.strptime(zt_date2[:8], '%Y%m%d')
            for days_back2 in range(7):
                check_date2 = (base_date2 - _dt2.timedelta(days=days_back2)).strftime('%Y%m%d')
                try:
                    df_mf = ts_pro.moneyflow_hsgt(trade_date=check_date2)
                    if df_mf is not None and not df_mf.empty:
                        row_mf = df_mf.iloc[0]
                        north_buy = float(row_mf.get('north_money', 0) or 0)
                        capital_flow['main_fund'] = {
                            'net_inflow': north_buy,
                            'buy': north_buy if north_buy > 0 else 0,
                            'sell': abs(north_buy) if north_buy < 0 else 0,
                            'note': '北向资金净流入作为主力资金参考'
                        }
                        break
                except Exception:
                    continue
    except Exception:
        pass

    return capital_flow
