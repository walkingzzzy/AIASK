"""相对估值 & 历史估值

包含 4 阶段可比公司筛选、相对估值分析、历史估值数据获取等
需要数据库 / 数据源访问的工具实现逻辑。
由 valuation.py 中的 @mcp.tool() 调用。
"""

from typing import Optional, List
import statistics

from ..storage import get_db
from ..utils import ok, fail


# ---------------------------------------------------------------------------
# 相对估值（4-stage peer selection）
# ---------------------------------------------------------------------------

async def _relative_valuation_impl(
    code: str,
    metrics: Optional[List[str]] = None,
    peers: Optional[List[str]] = None,
):
    """
    相对估值分析实现。

    Args:
        code: 目标股票代码
        metrics: 估值指标列表，如['pe_ratio', 'pb_ratio', 'ps_ratio']
        peers: 可比公司列表（不填则自动查找同行业公司）
    """
    db = get_db()

    # 默认估值指标
    if not metrics:
        metrics = ['pe_ratio', 'pb_ratio']

    # 获取目标股票信息
    target_info = await db.get_stock_info(code)
    if not target_info:
        return fail(f'Stock {code} not found')

    target_industry = target_info.get('industry', '')
    target_market_cap = float(target_info.get('market_cap') or 0.0)
    target_financial = None
    try:
        target_financial = await db.get_financials(code, limit=1)
    except Exception:
        target_financial = None
    if not target_financial:
        try:
            from .finance import get_financials as _api_get_financials
            fin_res = await _api_get_financials(code)
            if fin_res and fin_res.get('success') and fin_res.get('data'):
                target_financial = [fin_res['data']]
        except Exception:
            pass

    def _latest_row(rows):
        if isinstance(rows, list) and rows:
            for item in rows:
                if isinstance(item, dict):
                    return item
        if isinstance(rows, dict):
            return rows
        return None

    def _safe_float(value):
        try:
            return float(value) if value is not None else None
        except Exception:
            return None

    def _first_number(row: dict, keys: List[str]):
        if not isinstance(row, dict):
            return None
        for k in keys:
            if k in row and row.get(k) is not None:
                val = _safe_float(row.get(k))
                if val is not None:
                    return val
        return None

    def _derive_growth(fin_row: dict):
        return _first_number(fin_row, [
            'revenue_yoy', 'revenue_growth', 'growth_rate',
            'net_profit_growth', 'profit_growth',
        ])

    def _derive_cashflow_quality(fin_row: dict):
        ocf = _first_number(fin_row, [
            'operating_cash_flow',
            'net_operate_cash_flow',
            'net_cash_flow_from_operating_activities',
            'cashflow_from_operations',
        ])
        net_profit = _first_number(fin_row, [
            'net_profit',
            'netProfit',
            'net_income',
            'profit',
        ])
        ratio = None
        if net_profit is not None and abs(net_profit) > 1e-9 and ocf is not None:
            ratio = ocf / net_profit
        return ocf, net_profit, ratio

    target_fin_row = _latest_row(target_financial) or {}
    target_roe = _safe_float(target_fin_row.get('roe'))
    target_debt_ratio = _safe_float(target_fin_row.get('debt_ratio'))
    target_growth = _derive_growth(target_fin_row)
    target_ocf, target_net_profit, target_ocf_profit_ratio = _derive_cashflow_quality(target_fin_row)

    # 获取目标股票估值指标
    target_metrics = {}
    for metric in metrics:
        value = target_info.get(metric)
        if value and value > 0:
            target_metrics[metric] = float(value)

    if not target_metrics:
        return fail(f'No valid valuation metrics for {code}')

    # 查找可比公司（优先同行业，扩大样本后再做层层过滤）
    peer_source = 'explicit'
    peer_fallback_reasons: list[str] = []
    if not peers:
        async with db.acquire() as conn:
            rows = []
            if target_industry:
                rows = await conn.fetch(
                    """SELECT code FROM stocks
                       WHERE industry = $1 AND code != $2
                       LIMIT 200""",
                    target_industry, code
                )
                peers = [row['code'] for row in rows]
                peer_source = 'industry'
                if not peers:
                    peer_fallback_reasons.append('industry_peer_empty')
            else:
                peer_fallback_reasons.append('industry_missing')

            if not peers:
                if target_market_cap > 0:
                    rows = await conn.fetch(
                        """SELECT code FROM stocks
                           WHERE code != $1
                           ORDER BY ABS(COALESCE(market_cap, 0) - $2) ASC
                           LIMIT 200""",
                        code, target_market_cap
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT code FROM stocks
                           WHERE code != $1
                           ORDER BY market_cap DESC NULLS LAST
                           LIMIT 200""",
                        code
                    )
                peers = [row['code'] for row in rows]
                peer_source = 'market_cap_fallback'

    if not peers:
        return fail(f'No peer companies found for {code}')

    # 获取候选可比公司估值与质量数据
    peer_candidates = []
    for peer_code in peers:
        peer_info = await db.get_stock_info(peer_code)
        if not peer_info:
            continue

        peer_metrics = {'code': peer_code, 'name': peer_info.get('name', '')}
        valid = False
        for metric in metrics:
            value = peer_info.get(metric)
            if value and value > 0:
                peer_metrics[metric] = float(value)
                valid = True

        if valid:
            peer_metrics['_market_cap'] = float(peer_info.get('market_cap') or 0.0)
            peer_financial = None
            try:
                peer_financial = await db.get_financials(peer_code, limit=1)
            except Exception:
                peer_financial = None
            if not peer_financial:
                try:
                    from .finance import get_financials as _api_get_financials
                    fin_res = await _api_get_financials(peer_code)
                    if fin_res and fin_res.get('success') and fin_res.get('data'):
                        peer_financial = [fin_res['data']]
                except Exception:
                    pass
            peer_fin_row = _latest_row(peer_financial) or {}
            peer_metrics['_roe'] = _safe_float(peer_fin_row.get('roe'))
            peer_metrics['_debt_ratio'] = _safe_float(peer_fin_row.get('debt_ratio'))
            peer_metrics['_growth'] = _derive_growth(peer_fin_row)
            peer_ocf, peer_profit, peer_ocf_profit_ratio = _derive_cashflow_quality(peer_fin_row)
            peer_metrics['_ocf'] = peer_ocf
            peer_metrics['_net_profit'] = peer_profit
            peer_metrics['_ocf_profit_ratio'] = peer_ocf_profit_ratio
            peer_candidates.append(peer_metrics)

    if not peer_candidates:
        return fail('No valid peer data found')

    peer_pool_build = {
        'candidate_count': len(peer_candidates),
        'peer_source': peer_source,
        'fallback_reasons': peer_fallback_reasons,
        'size_filter_relaxed': False,
        'quality_filter_relaxed': False,
        'growth_filter_relaxed': False,
        'cashflow_filter_relaxed': False,
        'size_ratio_min': 0.3,
        'size_ratio_max': 3.0,
        'quality_thresholds': {},
        'growth_thresholds': {},
        'cashflow_thresholds': {},
        'relaxation_reasons': [],
    }

    # 过滤1：规模可比（默认 0.3x~3x）
    peer_stage = peer_candidates
    size_filtered = peer_stage
    if target_market_cap > 0:
        size_filtered = [
            p for p in peer_stage
            if p.get('_market_cap', 0.0) > 0
            and 0.3 <= (p.get('_market_cap', 0.0) / target_market_cap) <= 3.0
        ]
        peer_pool_build['after_size_filter'] = len(size_filtered)
        if len(size_filtered) >= 5:
            peer_stage = size_filtered
        else:
            peer_pool_build['size_filter_relaxed'] = True
    else:
        peer_pool_build['after_size_filter'] = len(peer_stage)

    # 过滤2：质量可比（ROE/负债率）
    quality_filtered = peer_stage
    roe_threshold = None
    debt_threshold = None
    if target_roe is not None:
        roe_threshold = max(0.05, target_roe * 0.5)
        peer_pool_build['quality_thresholds']['roe_min'] = roe_threshold
    if target_debt_ratio is not None:
        debt_threshold = min(0.95, target_debt_ratio + 0.25)
        peer_pool_build['quality_thresholds']['debt_ratio_max'] = debt_threshold

    if roe_threshold is not None or debt_threshold is not None:
        quality_filtered = []
        for p in peer_stage:
            ok_roe = True
            if roe_threshold is not None:
                peer_roe = p.get('_roe')
                ok_roe = (peer_roe is not None) and (peer_roe >= roe_threshold)

            ok_debt = True
            if debt_threshold is not None:
                peer_debt = p.get('_debt_ratio')
                ok_debt = (peer_debt is None) or (peer_debt <= debt_threshold)

            if ok_roe and ok_debt:
                quality_filtered.append(p)

        peer_pool_build['after_quality_filter'] = len(quality_filtered)
        if len(quality_filtered) >= 5:
            peer_stage = quality_filtered
        else:
            peer_pool_build['quality_filter_relaxed'] = True
            peer_pool_build['relaxation_reasons'].append('quality_filter_relaxed_due_to_small_sample')
    else:
        peer_pool_build['after_quality_filter'] = len(peer_stage)

    # 过滤3：成长可比（优先使用 revenue/profit growth）
    growth_filtered = peer_stage
    growth_target = target_growth
    growth_floor = None
    growth_ceil = None
    if growth_target is not None:
        growth_tolerance = max(0.08, abs(growth_target) * 0.6)
        growth_floor = growth_target - growth_tolerance
        growth_ceil = growth_target + growth_tolerance
        peer_pool_build['growth_thresholds'] = {
            'target_growth': float(growth_target),
            'growth_floor': float(growth_floor),
            'growth_ceil': float(growth_ceil),
            'mode': 'around_target',
        }
    else:
        growth_floor = -0.30
        peer_pool_build['growth_thresholds'] = {
            'growth_floor': float(growth_floor),
            'mode': 'minimum_floor',
        }

    growth_filtered = []
    growth_data_available = False
    for p in peer_stage:
        g = p.get('_growth')
        if g is None:
            continue
        growth_data_available = True
        if growth_ceil is not None:
            if growth_floor <= g <= growth_ceil:
                growth_filtered.append(p)
        else:
            if g >= growth_floor:
                growth_filtered.append(p)

    peer_pool_build['after_growth_filter'] = len(growth_filtered)
    if growth_data_available and len(growth_filtered) >= 5:
        peer_stage = growth_filtered
    else:
        peer_pool_build['growth_filter_relaxed'] = True
        if not growth_data_available:
            peer_pool_build['relaxation_reasons'].append('growth_filter_relaxed_due_to_missing_data')
        else:
            peer_pool_build['relaxation_reasons'].append('growth_filter_relaxed_due_to_small_sample')

    # 过滤4：现金流口径一致性（经营现金流与净利润匹配）
    cashflow_filtered = []
    cashflow_data_available = False

    if target_ocf_profit_ratio is not None:
        ratio_floor = max(0.2, target_ocf_profit_ratio * 0.5)
        ratio_ceil = max(ratio_floor + 0.1, target_ocf_profit_ratio * 1.5)
        peer_pool_build['cashflow_thresholds'] = {
            'target_ocf_profit_ratio': float(target_ocf_profit_ratio),
            'ratio_floor': float(ratio_floor),
            'ratio_ceil': float(ratio_ceil),
            'require_positive_ocf': bool((target_ocf or 0.0) > 0),
            'mode': 'ratio_band',
        }
    else:
        ratio_floor = 0.2
        ratio_ceil = None
        peer_pool_build['cashflow_thresholds'] = {
            'ratio_floor': float(ratio_floor),
            'require_positive_ocf': True,
            'mode': 'minimum_ratio_or_positive_ocf',
        }

    for p in peer_stage:
        ocf = p.get('_ocf')
        ratio = p.get('_ocf_profit_ratio')
        has_any = (ocf is not None) or (ratio is not None)
        if not has_any:
            continue
        cashflow_data_available = True

        ok_cash = True
        if ratio is not None:
            ok_cash = ratio >= ratio_floor
            if ratio_ceil is not None:
                ok_cash = ok_cash and (ratio <= ratio_ceil)
        elif ocf is not None:
            ok_cash = ocf > 0

        if ok_cash:
            cashflow_filtered.append(p)

    peer_pool_build['after_cashflow_filter'] = len(cashflow_filtered)
    if cashflow_data_available and len(cashflow_filtered) >= 5:
        peer_stage = cashflow_filtered
    else:
        peer_pool_build['cashflow_filter_relaxed'] = True
        if not cashflow_data_available:
            peer_pool_build['relaxation_reasons'].append('cashflow_filter_relaxed_due_to_missing_data')
        else:
            peer_pool_build['relaxation_reasons'].append('cashflow_filter_relaxed_due_to_small_sample')

    # 排序：优先规模更接近目标
    if target_market_cap > 0:
        peer_stage = sorted(
            peer_stage,
            key=lambda p: abs((p.get('_market_cap', target_market_cap) / target_market_cap) - 1.0),
        )

    peer_data = []
    for p in peer_stage:
        public_row = {k: v for k, v in p.items() if not str(k).startswith('_')}
        peer_data.append(public_row)

    if not peer_data:
        return fail('No valid peer data found')

    # 计算行业统计
    industry_stats = {}
    for metric in metrics:
        values = [p[metric] for p in peer_data if metric in p]
        if values:
            industry_stats[metric] = {
                'mean': float(statistics.mean(values)),
                'median': float(statistics.median(values)),
                'min': float(min(values)),
                'max': float(max(values)),
                'count': len(values)
            }

    # 计算相对估值
    comparison = {}
    for metric in target_metrics:
        if metric in industry_stats:
            target_value = target_metrics[metric]
            industry_mean = industry_stats[metric]['mean']
            industry_median = industry_stats[metric]['median']

            ptm = float((target_value - industry_median) / industry_median * 100) if industry_median else None
            # 偏离风险标记：|premium_to_median| > 30% 为 high
            if ptm is not None:
                abs_ptm = abs(ptm)
                if abs_ptm > 50:
                    deviation_risk = 'extreme'
                elif abs_ptm > 30:
                    deviation_risk = 'high'
                else:
                    deviation_risk = 'normal'
                risk_flag = 'high_premium' if ptm > 30 else ('high_discount' if ptm < -30 else 'normal')
            else:
                deviation_risk = None
                risk_flag = None

            comparison[metric] = {
                'target': target_value,
                'industry_mean': industry_mean,
                'industry_median': industry_median,
                'premium_to_mean': float((target_value - industry_mean) / industry_mean * 100) if industry_mean else None,
                'premium_to_median': ptm,
                'deviation_risk': deviation_risk,
                'risk_flag': risk_flag,
                'percentile': float(sum(1 for p in peer_data if p.get(metric, float('inf')) < target_value) / len(peer_data) * 100)
            }

    return ok({
        'code': code,
        'name': target_info.get('name', ''),
        'industry': target_industry,
        'target_metrics': target_metrics,
        'industry_stats': industry_stats,
        'comparison': comparison,
        'peer_count': len(peer_data),
        'peer_pool_build': peer_pool_build,
        'peers': peer_data[:10]  # 只返回前10个可比公司
    })


# ---------------------------------------------------------------------------
# 历史估值
# ---------------------------------------------------------------------------

async def _get_historical_valuation_impl(
    code: str,
    days: int = 30,
):
    """
    获取历史估值数据实现。

    已知限制与降级策略：
    - 首选 stock_quotes 历史库；无数据时按 Tushare -> AkShare -> Baostock 依次降级。
    - 不同源字段可用性不同，可能出现仅价格可用、估值字段缺失。
    - 返回新增 data_quality/source_chain/fallback_reason，便于审计与质量评估。
    """
    from datetime import datetime, timedelta

    db = get_db()
    rows = []
    source_chain: list[str] = ['db.stock_quotes']
    fallback_reason: list[str] = []

    try:
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """SELECT time, pe, pb, mkt_cap, price
                   FROM stock_quotes
                   WHERE code = $1
                   AND time >= NOW() - INTERVAL '1 day' * $2
                   ORDER BY time DESC""",
                code, days
            )
    except Exception as e:
        rows = []
        fallback_reason.append(f'stock_quotes查询失败: {e}')

    def _to_float(value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    history_raw = []
    for row in rows or []:
        history_raw.append({
            'date': row['time'].strftime('%Y-%m-%d') if row.get('time') else None,
            'pe_ratio': _to_float(row.get('pe')),
            'pb_ratio': _to_float(row.get('pb')),
            'market_cap': _to_float(row.get('mkt_cap')),
            'price': _to_float(row.get('price')),
        })

    if not history_raw:
        source_chain.append('tushare.daily_basic')
        try:
            from ..data_source import data_source
            pro = data_source.get_tushare_pro()
            if pro:
                ts_code = f"{code}.SH" if str(code).startswith('6') else f"{code}.SZ"
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=max(days, 1))).strftime('%Y%m%d')
                df = pro.daily_basic(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='trade_date,pe_ttm,pb,total_mv,close',
                )
                if df is not None and not df.empty:
                    for _, r in df.iterrows():
                        trade_date = str(r.get('trade_date') or '').strip()
                        dt = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}" if len(trade_date) == 8 else None
                        history_raw.append({
                            'date': dt,
                            'pe_ratio': _to_float(r.get('pe_ttm')),
                            'pb_ratio': _to_float(r.get('pb')),
                            'market_cap': _to_float(r.get('total_mv')),
                            'price': _to_float(r.get('close')),
                        })
        except Exception as e:
            fallback_reason.append(f'Tushare降级失败: {e}')

    if not history_raw:
        source_chain.append('akshare.stock_a_indicator_lg')
        try:
            import akshare as ak
            df = ak.stock_a_indicator_lg(symbol=code)
            if df is not None and not df.empty:
                for _, r in df.tail(max(days, 1)).iterrows():
                    dt = str(r.get('trade_date') or r.get('日期') or '')[:10] or None
                    history_raw.append({
                        'date': dt,
                        'pe_ratio': _to_float(r.get('pe') if 'pe' in r else r.get('市盈率')),
                        'pb_ratio': _to_float(r.get('pb') if 'pb' in r else r.get('市净率')),
                        'market_cap': _to_float(r.get('total_mv') if 'total_mv' in r else r.get('总市值')),
                        'price': _to_float(r.get('close') if 'close' in r else r.get('收盘价')),
                    })
        except Exception as e:
            fallback_reason.append(f'AkShare降级失败: {e}')

    if not history_raw:
        source_chain.append('baostock.history_k_data_plus')
        try:
            from ..baostock_api import baostock_client
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=max(days * 2, 5))).strftime('%Y-%m-%d')
            df = baostock_client.query_history_k_data_plus(
                code,
                fields='date,close',
                start_date=start_date,
                end_date=end_date,
                frequency='d',
                adjustflag='2',
            )
            if df is not None and not df.empty:
                for _, r in df.tail(max(days, 1)).iterrows():
                    history_raw.append({
                        'date': str(r.get('date') or '')[:10] or None,
                        'pe_ratio': None,
                        'pb_ratio': None,
                        'market_cap': None,
                        'price': _to_float(r.get('close')),
                    })
        except Exception as e:
            fallback_reason.append(f'Baostock降级失败: {e}')

    if not history_raw:
        source_chain.append('db.get_stock_info')
        stock_info = await db.get_stock_info(code)
        if stock_info:
            fallback_reason.append('无历史估值序列，已降级为股票基础估值快照')
            history_raw.append({
                'date': None,
                'pe_ratio': _to_float(stock_info.get('pe_ratio')),
                'pb_ratio': _to_float(stock_info.get('pb_ratio')),
                'market_cap': _to_float(stock_info.get('market_cap')),
                'price': None,
            })

    def _record_score(item: dict) -> int:
        return sum(item.get(k) is not None for k in ('pe_ratio', 'pb_ratio', 'market_cap', 'price'))

    dedup_map: dict[str, dict] = {}
    for idx, item in enumerate(history_raw):
        key = item.get('date') or f'__nodate_{idx}'
        old = dedup_map.get(key)
        if old is None or _record_score(item) >= _record_score(old):
            dedup_map[key] = item

    history = list(dedup_map.values())
    history.sort(key=lambda x: (x.get('date') is not None, x.get('date') or ''), reverse=True)

    pe_values = [h['pe_ratio'] for h in history if h.get('pe_ratio') is not None]
    pb_values = [h['pb_ratio'] for h in history if h.get('pb_ratio') is not None]

    stats = {}
    if pe_values:
        stats['pe'] = {
            'current': pe_values[0],
            'mean': float(statistics.mean(pe_values)),
            'median': float(statistics.median(pe_values)),
            'min': float(min(pe_values)),
            'max': float(max(pe_values))
        }
    if pb_values:
        stats['pb'] = {
            'current': pb_values[0],
            'mean': float(statistics.mean(pb_values)),
            'median': float(statistics.median(pb_values)),
            'min': float(min(pb_values)),
            'max': float(max(pb_values))
        }

    total_cells = len(history) * 4
    missing_cells = sum(1 for h in history for k in ('pe_ratio', 'pb_ratio', 'market_cap', 'price') if h.get(k) is None)
    completeness_ratio = float((total_cells - missing_cells) / total_cells) if total_cells > 0 else 0.0
    data_quality = {
        'raw_count': len(history_raw),
        'deduplicated_count': len(history),
        'duplicate_removed': max(0, len(history_raw) - len(history)),
        'field_count': 4,
        'missing_cells': missing_cells,
        'completeness_ratio': round(completeness_ratio, 4),
        'missing_ratio': round(1.0 - completeness_ratio, 4),
    }

    payload = {
        'code': code,
        'days': days,
        'history': history,
        'stats': stats,
        'count': len(history),
        'source_chain': source_chain,
        'fallback_reason': fallback_reason,
        'data_quality': data_quality,
    }
    if not rows:
        payload['message'] = 'stock_quotes 无历史数据或查询失败，已返回降级结果'
        payload['source'] = 'fallback'

    return ok(payload)
