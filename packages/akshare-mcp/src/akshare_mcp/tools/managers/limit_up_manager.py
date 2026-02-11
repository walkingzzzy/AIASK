"""涨停板管理器"""

from datetime import datetime
import json
import logging
from ...utils import ok, fail
from ...data_source import data_source

logger = logging.getLogger(__name__)


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


def _normalize_date(raw) -> str:
    """统一日期格式为 YYYYMMDD"""
    return str(raw).replace('-', '').replace('/', '').replace(' ', '')[:8]


def register_limit_up_manager(mcp):
    """注册涨停板管理器工具"""
    
    @mcp.tool()
    async def limit_up_manager(action: str, **kwargs):
        """涨停板管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/statistics
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list: date(str, optional, "YYYY-MM-DD"，默认最近交易日)
                - statistics: date(str, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            limit_up_manager(action="help", kwargs="{}")
            # 获取今日涨停板列表
            limit_up_manager(action="list", kwargs="{}")
            # 获取指定日期涨停统计
            limit_up_manager(action="statistics", kwargs='{"date":"2025-01-15"}')
        """
        try:
            kwargs = _normalize_kwargs(kwargs)
            
            if action == 'help':
                return ok({
                    'supported_actions': {
                        'list': '涨停板列表（可选 date，格式 YYYYMMDD 或 YYYY-MM-DD）',
                        'statistics': '涨停统计（可选 date）',
                        'help': '显示帮助信息',
                    }
                })
            
            elif action == 'list':
                raw_date = kwargs.get('date') or kwargs.get('trade_date') or kwargs.get('Date') or ''
                date = _normalize_date(raw_date) if raw_date else datetime.now().strftime('%Y%m%d')
                request_date = date

                # 委托给 get_limit_up_stocks 工具（内部走 Tushare stk_limit）
                limit_up_stocks = []
                try:
                    from ..market.limit_up import get_limit_up_stocks as _get_zt
                    zt_res = _get_zt(date=date)
                    if zt_res.get('success') and zt_res.get('data'):
                        zt_data = zt_res['data']
                        if isinstance(zt_data, list):
                            for item in zt_data:
                                limit_up_stocks.append({
                                    'code': item.get('code', ''),
                                    'name': item.get('name', ''),
                                    'price': float(item.get('price', 0) or 0),
                                    'change_pct': float(item.get('changePercent', 0) or 0),
                                    'turnover_rate': float(item.get('turnoverRate', 0) or 0),
                                    'reason': item.get('industry', '') or item.get('concept', ''),
                                    'first_limit_up_time': item.get('firstLimitTime', ''),
                                    'last_limit_up_time': item.get('lastLimitTime', ''),
                                    'limit_up_count': int(item.get('continuousDays', 0) or 0),
                                })
                except Exception as e:
                    logger.warning(f"[LimitUp] get_limit_up_stocks 失败: {e}")

                # 降级：Tushare stk_limit（也尝试最近10个交易日）
                if not limit_up_stocks:
                    try:
                        ts_pro = data_source.get_tushare_pro()
                        if ts_pro:
                            from datetime import timedelta
                            base = datetime.strptime(date, '%Y%m%d')
                            for days_back in range(10):
                                check_date = (base - timedelta(days=days_back)).strftime('%Y%m%d')
                                try:
                                    df = ts_pro.stk_limit(trade_date=check_date)
                                    if df is not None and not df.empty:
                                        # stk_limit 返回所有涨跌停，筛选涨停
                                        if 'limit' in df.columns:
                                            up_df = df[df['limit'] == 'U']
                                        elif 'pct_chg' in df.columns:
                                            up_df = df[df['pct_chg'].astype(float, errors='ignore') >= 9.5]
                                        else:
                                            up_df = df.head(0)
                                        for _, row in up_df.iterrows():
                                            ts_code = str(row.get('ts_code', ''))
                                            code_val = ts_code.split('.')[0] if ts_code else ''
                                            limit_up_stocks.append({
                                                'code': code_val,
                                                'name': str(row.get('name', '')),
                                                'price': float(row.get('close', 0) or 0),
                                                'change_pct': float(row.get('pct_chg', 0) or 0),
                                                'turnover_rate': 0,
                                                'reason': '',
                                                'first_limit_up_time': '',
                                                'last_limit_up_time': '',
                                                'limit_up_count': 0,
                                            })
                                        if limit_up_stocks:
                                            date = check_date  # 更新为实际有数据的日期
                                            break
                                except Exception:
                                    continue
                    except Exception as e:
                        logger.warning(f"[LimitUp] Tushare stk_limit 失败: {e}")

                if limit_up_stocks:
                    return ok({
                        'request_date': request_date,
                        'date': date,
                        'limit_up_stocks': limit_up_stocks,
                        'count': len(limit_up_stocks)
                    })

                return ok({
                    'request_date': request_date,
                    'date': date,
                    'limit_up_stocks': [],
                    'count': 0,
                    'message': f'{date} 暂无涨停板数据（可能为非交易日）'
                })
            
            elif action == 'statistics':
                raw_date = kwargs.get('date') or kwargs.get('trade_date') or kwargs.get('Date') or ''
                date = _normalize_date(raw_date) if raw_date else datetime.now().strftime('%Y%m%d')
                request_date = date

                # 委托给 get_limit_up_statistics 工具
                try:
                    from ..market.limit_up import get_limit_up_statistics as _get_stat
                    stat_res = _get_stat(date=date)
                    if stat_res.get('success') and stat_res.get('data'):
                        stat_data = stat_res['data']
                        return ok({
                            'request_date': request_date,
                            'date': date,
                            'total_limit_up': stat_data.get('totalLimitUp', 0),
                            'sealed_limit_up': stat_data.get('totalLimitUp', 0) - stat_data.get('failedBoard', 0),
                            'broken_limit_up': stat_data.get('failedBoard', 0),
                            'seal_rate': f"{stat_data.get('successRate', 0):.2f}%",
                        })
                except Exception as e:
                    logger.warning(f"[LimitUp] get_limit_up_statistics 失败: {e}")

                return ok({
                    'request_date': request_date,
                    'date': date,
                    'total_limit_up': 0,
                    'sealed_limit_up': 0,
                    'broken_limit_up': 0,
                    'message': f'{date} 暂无涨停统计数据（可能为非交易日）'
                })
            
            else:
                return fail(f'Unknown action: {action}. Supported: help, list, statistics')
        except Exception as e:
            logger.error(f"[LimitUp] Error: {e}")
            return fail(str(e))
