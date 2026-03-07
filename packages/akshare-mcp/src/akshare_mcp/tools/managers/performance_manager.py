"""绩效管理器 - 归因分析、绩效评估"""

import json
from datetime import datetime, timezone
import numpy as np
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


def _extract_closes_with_dates(klines):
    """从 K 线记录中提取按时间升序排列的 (日期, 收盘价) 序列。"""
    if not klines:
        return [], np.array([])

    rows = []
    for k in klines:
        if not isinstance(k, dict):
            continue
        close = k.get('close')
        if close is None:
            continue
        try:
            close_v = float(close)
        except Exception:
            continue

        dt = (
            k.get('date')
            or k.get('datetime')
            or k.get('trade_date')
            or k.get('time')
            or ''
        )
        rows.append((str(dt)[:10], close_v))

    if len(rows) < 2:
        return [], np.array([])

    rows.sort(key=lambda x: x[0])
    dates = [r[0] for r in rows]
    closes = np.array([r[1] for r in rows], dtype=float)
    return dates, closes


def _extract_closes(klines):
    """从 K 线记录中提取按时间升序排列的收盘价序列（兼容旧调用）。"""
    _, closes = _extract_closes_with_dates(klines)
    return closes


async def _fetch_klines_raw(db, code: str, lookback_days: int):
    """获取原始 K 线数据（优先 DB，失败回退工具层）。"""
    klines = await db.get_klines(code, limit=lookback_days + 1)
    if not klines or len(klines) < 2:
        res = await get_kline(normalize_code(code), 'daily', lookback_days + 1)
        if res.get('success') and res.get('data'):
            klines = res['data']
    return klines


async def _fetch_dated_returns_for_code(db, code: str, lookback_days: int):
    """获取 (dates, returns, latest_close)，dates 与 returns 等长（日历对齐用）。"""
    klines = await _fetch_klines_raw(db, code, lookback_days)
    dates, closes = _extract_closes_with_dates(klines)
    if len(closes) < 2:
        return [], np.array([]), None
    returns = np.diff(closes) / closes[:-1]
    return dates[1:], returns, float(closes[-1])


async def _fetch_returns_for_code(db, code: str, lookback_days: int):
    """获取单只股票日收益率序列（兼容旧调用）。"""
    _, returns, latest_close = await _fetch_dated_returns_for_code(db, code, lookback_days)
    return returns, latest_close


async def _fetch_close_series_for_code(db, code: str, lookback_days: int) -> np.ndarray:
    """获取单只股票收盘价序列（兼容旧调用）。"""
    klines = await _fetch_klines_raw(db, code, lookback_days)
    return _extract_closes(klines)


def _apply_daily_fee(returns: np.ndarray, fee_disclosure: dict) -> np.ndarray:
    """从日收益率中扣减日化费用（佣金+滑点+冲击）。"""
    if returns is None or len(returns) == 0:
        return returns
    annual_fee = (
        float(fee_disclosure.get('commission_rate', 0))
        + float(fee_disclosure.get('slippage_rate', 0))
        + float(fee_disclosure.get('impact_rate', 0))
    )
    daily_fee = annual_fee / 252.0
    return returns - daily_fee


def _calendar_align_returns(dated_returns_list):
    """基于日历日期交集对齐多只股票的收益率序列。

    Args:
        dated_returns_list: [(dates_list, returns_array), ...]
    Returns:
        (common_dates, aligned_2d_array) — aligned_2d_array shape = (n_stocks, n_dates)
    """
    if not dated_returns_list:
        return [], np.array([])

    # 求所有股票日期的交集
    date_sets = [set(d) for d, _ in dated_returns_list]
    common = date_sets[0]
    for s in date_sets[1:]:
        common &= s
    if len(common) < 2:
        return [], np.array([])

    common_dates = sorted(common)
    aligned = []
    for dates, returns in dated_returns_list:
        date_to_idx = {d: i for i, d in enumerate(dates)}
        row = np.array([float(returns[date_to_idx[d]]) for d in common_dates], dtype=float)
        aligned.append(row)

    return common_dates, np.array(aligned, dtype=float)


async def _build_portfolio_daily_returns(db, holdings, lookback_days: int, fee_disclosure: dict = None):
    """基于持仓构建组合日收益率序列（日历对齐 + 可选费用扣减）。"""
    if not holdings:
        return np.array([])

    dated_list = []
    value_list = []

    for h in holdings:
        code = h.get('code')
        if not code:
            continue

        dates, returns, latest_close = await _fetch_dated_returns_for_code(db, code, lookback_days)
        if len(returns) == 0 or latest_close is None:
            continue

        shares = float(h.get('shares') or 0)
        position_value = shares * latest_close
        if position_value <= 0:
            position_value = 1.0

        dated_list.append((dates, returns))
        value_list.append(position_value)

    if not dated_list:
        return np.array([])

    common_dates, aligned = _calendar_align_returns(dated_list)
    if len(common_dates) < 2:
        return np.array([])

    values = np.array(value_list, dtype=float)
    weights = values / values.sum() if values.sum() > 0 else np.array([1.0 / len(values)] * len(values))

    portfolio_returns = np.dot(weights, aligned)

    # 费用扣减
    if fee_disclosure:
        portfolio_returns = _apply_daily_fee(portfolio_returns, fee_disclosure)

    return portfolio_returns


def _calc_max_drawdown(returns: np.ndarray) -> float:
    """根据收益率序列计算最大回撤。"""
    if returns is None or len(returns) == 0:
        return 0.0

    equity = np.cumprod(1.0 + returns)
    running_max = np.maximum.accumulate(equity)
    drawdown = equity / running_max - 1.0
    return float(abs(np.min(drawdown)))


def _calc_annualized_from_daily(returns: np.ndarray) -> tuple:
    """从日收益率序列计算年化收益和年化波动。"""
    if returns is None or len(returns) == 0:
        return 0.0, 0.0

    mean_daily = float(np.mean(returns))
    ann_return = (1.0 + mean_daily) ** 252 - 1.0

    if len(returns) > 1:
        ann_vol = float(np.std(returns, ddof=1) * np.sqrt(252))
    else:
        ann_vol = 0.0

    return float(ann_return), float(ann_vol)


def _calc_period_return(returns: np.ndarray) -> float:
    """根据收益率序列计算区间累计收益率。"""
    if returns is None or len(returns) == 0:
        return 0.0
    return float(np.prod(1.0 + returns) - 1.0)


def _safe_non_negative_float(v, default: float) -> float:
    try:
        x = float(v)
    except Exception:
        return float(default)
    if not np.isfinite(x) or x < 0:
        return float(default)
    return float(x)


def _build_fee_disclosure(kwargs: dict) -> dict:
    """构建费用口径披露字段（P1-3）。"""
    default_commission = 0.0003
    default_slippage = 0.0005
    default_impact = 0.0002

    commission_rate = _safe_non_negative_float(kwargs.get('commission_rate', default_commission), default_commission)
    slippage_rate = _safe_non_negative_float(kwargs.get('slippage_rate', default_slippage), default_slippage)
    impact_rate = _safe_non_negative_float(kwargs.get('impact_rate', default_impact), default_impact)

    assumptions_source = (
        'input'
        if any(k in kwargs for k in ('commission_rate', 'slippage_rate', 'impact_rate'))
        else 'default'
    )

    return {
        'commission_rate': float(commission_rate),
        'slippage_rate': float(slippage_rate),
        'impact_rate': float(impact_rate),
        'total_annual_fee': float(commission_rate + slippage_rate + impact_rate),
        'assumptions_source': assumptions_source,
        'deducted': True,
        'deduction_method': 'daily_pro_rata',
    }


def _calc_rolling_sharpe(returns: np.ndarray, window: int, risk_free_rate: float) -> list:
    if returns is None or len(returns) < max(2, window):
        return []

    out = []
    rf_daily = float(risk_free_rate) / 252.0
    for end_idx in range(window, len(returns) + 1):
        seg = returns[end_idx - window:end_idx]
        vol = float(np.std(seg, ddof=1)) if len(seg) > 1 else 0.0
        if vol <= 0:
            out.append(0.0)
        else:
            sr = ((float(np.mean(seg)) - rf_daily) / vol) * float(np.sqrt(252))
            out.append(float(sr))
    return out


def _calc_rolling_drawdown(returns: np.ndarray, window: int) -> list:
    if returns is None or len(returns) < max(2, window):
        return []

    out = []
    for end_idx in range(window, len(returns) + 1):
        seg = returns[end_idx - window:end_idx]
        out.append(float(_calc_max_drawdown(seg)))
    return out


def _build_window_audit(lookback_days: int, aligned_days: int, rolling_window: int) -> dict:
    return {
        'lookback_days': int(lookback_days),
        'aligned_days': int(max(0, aligned_days)),
        'rolling_window': int(max(2, rolling_window)),
        'alignment_method': 'calendar_date_intersection',
    }


def _to_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _to_float_list(arr: np.ndarray):
    if arr is None or len(arr) == 0:
        return []
    return [float(x) for x in arr.tolist()]


def _compute_timing_component(price_matrix: np.ndarray, start_values: np.ndarray) -> dict:
    """基于价格路径计算择时贡献（真实路径收益 - 静态权重线性收益）。"""
    if (
        price_matrix is None
        or start_values is None
        or price_matrix.ndim != 2
        or len(start_values) != price_matrix.shape[0]
        or price_matrix.shape[1] < 2
    ):
        return {
            "timing_return": 0.0,
            "realized_total_return": 0.0,
            "static_total_return": 0.0,
            "daily_returns": np.array([]),
            "aligned_days": int(price_matrix.shape[1]) if isinstance(price_matrix, np.ndarray) and price_matrix.ndim == 2 else 0,
            "assets_used": 0,
        }

    valid_mask = (
        np.isfinite(start_values)
        & (start_values > 0)
        & np.isfinite(price_matrix[:, 0])
        & (price_matrix[:, 0] > 0)
    )
    if int(np.sum(valid_mask)) < 1:
        return {
            "timing_return": 0.0,
            "realized_total_return": 0.0,
            "static_total_return": 0.0,
            "daily_returns": np.array([]),
            "aligned_days": int(price_matrix.shape[1]),
            "assets_used": 0,
        }

    prices = np.array(price_matrix[valid_mask], dtype=float)
    start_vals = np.array(start_values[valid_mask], dtype=float)

    if prices.shape[1] < 2:
        return {
            "timing_return": 0.0,
            "realized_total_return": 0.0,
            "static_total_return": 0.0,
            "daily_returns": np.array([]),
            "aligned_days": int(prices.shape[1]),
            "assets_used": int(len(start_vals)),
        }

    static_weights = start_vals / float(np.sum(start_vals))
    daily_asset_returns = np.diff(prices, axis=1) / prices[:, :-1]
    daily_asset_returns = np.nan_to_num(daily_asset_returns, nan=0.0, posinf=0.0, neginf=0.0)
    daily_returns = np.dot(static_weights, daily_asset_returns)
    realized_total_return = float(np.prod(1.0 + daily_returns) - 1.0)

    asset_period_returns = prices[:, -1] / prices[:, 0] - 1.0
    static_total_return = float(np.dot(static_weights, asset_period_returns))

    return {
        "timing_return": float(realized_total_return - static_total_return),
        "realized_total_return": realized_total_return,
        "static_total_return": static_total_return,
        "daily_returns": daily_returns,
        "aligned_days": int(prices.shape[1]),
        "assets_used": int(len(start_vals)),
    }


def register_performance_manager(mcp):
    """注册绩效管理器工具"""

    @mcp.tool()
    async def performance_manager(action: str, **kwargs):
        """绩效管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/calculate_metrics/backtest_metrics/attribution/benchmark_comparison
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - calculate_metrics: portfolio_id(str|int), lookback_days(int, optional)
                - backtest_metrics: backtest_id(str, optional) 或 artifact_id(str, optional)
                - attribution: portfolio_id(str|int), lookback_days(int, optional)
                - benchmark_comparison: portfolio_id(str|int), benchmark(str, optional), lookback_days(int, optional)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            performance_manager(action="help", kwargs="{}")
            # 计算绩效指标
            performance_manager(action="calculate_metrics", kwargs='{"portfolio_id":1,"lookback_days":252}')
            # 按回测ID查询回测绩效
            performance_manager(action="backtest_metrics", kwargs='{"backtest_id":"bt_001"}')
            # 按工件ID查询回测绩效
            performance_manager(action="backtest_metrics", kwargs='{"artifact_id":"art_demo_001"}')
            # 归因分析
            performance_manager(action="attribution", kwargs='{"portfolio_id":1}')
            # 基准对比
            performance_manager(action="benchmark_comparison", kwargs='{"portfolio_id":1,"benchmark":"000300","lookback_days":252}')
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))

            if action == 'help':
                return ok({
                    'supported_actions': {
                        'calculate_metrics': '计算绩效指标（需要 portfolio_id）',
                        'backtest_metrics': '按 backtest_id/artifact_id 查询回测绩效',
                        'attribution': '归因分析（需要 portfolio_id）',
                        'benchmark_comparison': '基准对比（需要 portfolio_id, benchmark）',
                        'help': '显示帮助信息',
                    }
                })

            elif action == 'backtest_metrics':
                backtest_id = str(kwargs.get('backtest_id') or '').strip()
                artifact_id = str(kwargs.get('artifact_id') or '').strip()

                if not backtest_id and not artifact_id:
                    return fail('需要提供 backtest_id 或 artifact_id')

                async with db.acquire() as conn:
                    row = None
                    if backtest_id:
                        row = await conn.fetchrow(
                            "SELECT * FROM backtest_results WHERE id = $1",
                            backtest_id,
                        )

                    if not row and artifact_id:
                        pattern_json = f'%"artifact_id": "{artifact_id}"%'
                        pattern_py = f"%'artifact_id': '{artifact_id}'%"
                        row = await conn.fetchrow(
                            """SELECT * FROM backtest_results
                               WHERE params LIKE $1 OR params LIKE $2
                               ORDER BY created_at DESC
                               LIMIT 1""",
                            pattern_json,
                            pattern_py,
                        )

                if not row:
                    return fail('未找到匹配的回测结果')

                r = dict(row)

                def _to_iso(v):
                    if isinstance(v, datetime):
                        return v.isoformat()
                    return str(v) if v is not None else None

                start_date = _to_iso(r.get('start_date'))
                end_date = _to_iso(r.get('end_date'))
                created_at = _to_iso(r.get('created_at'))

                total_return = float(r.get('total_return') or 0.0)
                annual_return = float(r.get('annual_return') or 0.0)
                max_drawdown = float(r.get('max_drawdown') or 0.0)
                sharpe_ratio = float(r.get('sharpe_ratio') or 0.0)

                # 从 params 文本中提取 artifact_id（若存在）
                resolved_artifact_id = artifact_id
                params_text = str(r.get('params') or '')
                if not resolved_artifact_id and params_text:
                    marker_json = '"artifact_id": "'
                    marker_py = "'artifact_id': '"
                    if marker_json in params_text:
                        seg = params_text.split(marker_json, 1)[1]
                        resolved_artifact_id = seg.split('"', 1)[0]
                    elif marker_py in params_text:
                        seg = params_text.split(marker_py, 1)[1]
                        resolved_artifact_id = seg.split("'", 1)[0]

                return ok({
                    'backtest_id': r.get('id'),
                    'artifact_id': resolved_artifact_id or None,
                    'code': r.get('code'),
                    'strategy': r.get('strategy'),
                    'start_date': start_date,
                    'end_date': end_date,
                    'created_at': created_at,
                    'initial_capital': float(r.get('initial_capital') or 0.0),
                    'final_capital': float(r.get('final_capital') or 0.0),
                    'total_return': total_return,
                    'total_return_pct': _to_pct(total_return),
                    'annual_return': annual_return,
                    'annual_return_pct': _to_pct(annual_return),
                    'max_drawdown': max_drawdown,
                    'max_drawdown_pct': _to_pct(max_drawdown),
                    'sharpe_ratio': sharpe_ratio,
                    'sortino_ratio': float(r.get('sortino_ratio') or 0.0),
                    'win_rate': float(r.get('win_rate') or 0.0),
                    'win_rate_pct': _to_pct(float(r.get('win_rate') or 0.0)),
                    'trades_count': int(r.get('trades_count') or 0),
                })

            elif action == 'calculate_metrics':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                lookback_days = int(kwargs.get('lookback_days', 252) or 252)
                lookback_days = max(20, min(2000, lookback_days))
                rolling_window = int(kwargs.get('rolling_window', 20) or 20)
                rolling_window = max(2, min(252, rolling_window))
                fee_disclosure = _build_fee_disclosure(kwargs)

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

                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )

                    trades = await conn.fetch(
                        """SELECT * FROM paper_trades
                           WHERE account_id = (SELECT user_id FROM portfolios WHERE id = $1)
                           ORDER BY created_at""",
                        portfolio_id
                    )

                initial_capital = float(portfolio['initial_capital'])
                current_value = float(portfolio['current_value'])
                total_return = (current_value - initial_capital) / initial_capital if initial_capital > 0 else 0.0

                created_at = portfolio['created_at']
                # 统一为 offset-aware 避免 naive vs aware 报错
                now = datetime.now(timezone.utc)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                days_held = (now - created_at).days
                if days_held <= 0:
                    days_held = 1

                # 交易统计
                win_trades = 0
                loss_trades = 0
                total_profit = 0.0
                total_loss = 0.0

                for trade in trades:
                    pnl = float(trade.get('pnl', 0) or 0)
                    if pnl > 0:
                        win_trades += 1
                        total_profit += pnl
                    elif pnl < 0:
                        loss_trades += 1
                        total_loss += abs(pnl)

                total_trades = win_trades + loss_trades
                win_rate = win_trades / total_trades if total_trades > 0 else 0.0
                avg_profit = total_profit / win_trades if win_trades > 0 else 0.0
                avg_loss = total_loss / loss_trades if loss_trades > 0 else 0.0
                profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0.0

                # 时序绩效指标（优先使用持仓收益序列，缺失时回退到账户口径）
                risk_free_rate = 0.03
                portfolio_daily_returns = await _build_portfolio_daily_returns(db, holdings, lookback_days, fee_disclosure=fee_disclosure)

                if len(portfolio_daily_returns) > 1:
                    series_total_return = _calc_period_return(portfolio_daily_returns)
                    annualized_return, volatility = _calc_annualized_from_daily(portfolio_daily_returns)
                    max_drawdown = _calc_max_drawdown(portfolio_daily_returns)
                else:
                    series_total_return = total_return
                    annualized_return = (1 + total_return) ** (365 / days_held) - 1 if days_held > 0 else 0.0
                    volatility = 0.0
                    max_drawdown = 0.0

                sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0.0
                rolling_sharpe_series = _calc_rolling_sharpe(
                    portfolio_daily_returns,
                    rolling_window,
                    risk_free_rate,
                )
                rolling_drawdown_series = _calc_rolling_drawdown(
                    portfolio_daily_returns,
                    rolling_window,
                )
                window_audit = _build_window_audit(
                    lookback_days=lookback_days,
                    aligned_days=int(len(portfolio_daily_returns)),
                    rolling_window=rolling_window,
                )

                return ok({
                    'portfolio_id': portfolio_id,
                    'initial_capital': float(initial_capital),
                    'current_value': float(current_value),
                    'total_return': float(total_return),
                    'total_return_pct': _to_pct(total_return),
                    'series_total_return': float(series_total_return),
                    'series_total_return_pct': _to_pct(series_total_return),
                    'annualized_return': float(annualized_return),
                    'annualized_return_pct': _to_pct(annualized_return),
                    'sharpe_ratio': float(sharpe_ratio),
                    'max_drawdown': float(max_drawdown),
                    'max_drawdown_pct': _to_pct(max_drawdown),
                    'volatility': float(volatility),
                    'volatility_pct': _to_pct(volatility),
                    'risk_free_rate': float(risk_free_rate),
                    'lookback_days': lookback_days,
                    'daily_returns_count': int(len(portfolio_daily_returns)),
                    'rolling_window': int(rolling_window),
                    'rolling_metrics': {
                        'rolling_sharpe': [float(x) for x in rolling_sharpe_series],
                        'rolling_drawdown': [float(x) for x in rolling_drawdown_series],
                        'count': int(min(len(rolling_sharpe_series), len(rolling_drawdown_series))),
                    },
                    'fees': fee_disclosure,
                    'window_audit': window_audit,
                    'trading_stats': {
                        'total_trades': total_trades,
                        'win_trades': win_trades,
                        'loss_trades': loss_trades,
                        'win_rate': float(win_rate),
                        'win_rate_pct': _to_pct(win_rate),
                        'profit_loss_ratio': float(profit_loss_ratio),
                        'avg_profit': float(avg_profit),
                        'avg_loss': float(avg_loss),
                    },
                    'days_held': days_held,
                })

            elif action == 'attribution':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                lookback_days = int(kwargs.get('lookback_days', 252) or 252)
                lookback_days = max(20, min(2000, lookback_days))
                rolling_window = int(kwargs.get('rolling_window', 20) or 20)
                rolling_window = max(2, min(252, rolling_window))
                benchmark = kwargs.get('benchmark', '000300')
                fee_disclosure = _build_fee_disclosure(kwargs)

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

                rows = []
                total_weight_base = 0.0
                all_date_sets = []
                for holding in holdings:
                    code = holding['code']
                    shares = float(holding.get('shares') or 0)
                    cost_price = float(holding.get('cost_price') or 0)

                    klines = await _fetch_klines_raw(db, code, lookback_days)
                    dates, closes = _extract_closes_with_dates(klines)
                    if len(closes) < 2:
                        continue

                    current_price = float(closes[-1])
                    stock_return = float(current_price / closes[0] - 1.0)
                    lifetime_return = (current_price - cost_price) / cost_price if cost_price > 0 else stock_return

                    start_value = shares * float(closes[0]) if shares > 0 and closes[0] > 0 else 0.0
                    cost_value = shares * cost_price if shares > 0 and cost_price > 0 else 0.0
                    current_value = shares * current_price if shares > 0 and current_price > 0 else 0.0
                    weight_base = (
                        start_value
                        if start_value > 0
                        else (cost_value if cost_value > 0 else (current_value if current_value > 0 else 1.0))
                    )

                    stock_info = await db.get_stock_info(code)
                    sector = stock_info.get('industry', '未知') if stock_info else '未知'

                    rows.append({
                        'code': code,
                        'sector': sector,
                        'stock_return': float(stock_return),
                        'lifetime_return': float(lifetime_return),
                        'dates': dates,
                        'close_series': closes,
                        'timing_start_value': float(weight_base),
                        'weight_base': float(weight_base),
                    })
                    all_date_sets.append(set(dates))
                    total_weight_base += weight_base

                if not rows or total_weight_base <= 0:
                    return fail('持仓数据不足，无法进行归因分析')

                # 日历对齐：取日期交集（含 benchmark）
                bm_dates, bm_returns, _ = await _fetch_dated_returns_for_code(db, benchmark, lookback_days)
                bm_date_set = set(bm_dates) if len(bm_returns) > 0 else None

                common_dates = all_date_sets[0]
                for s in all_date_sets[1:]:
                    common_dates &= s
                if bm_date_set:
                    common_dates &= bm_date_set
                common_dates = sorted(common_dates)
                if len(common_dates) < 2:
                    return fail('价格序列日期交集不足，无法计算择时贡献')

                # benchmark 对齐收益率
                bm_aligned_return = None
                if bm_date_set and len(common_dates) >= 2:
                    bm_date_idx = {d: i for i, d in enumerate(bm_dates)}
                    bm_aligned_rets = np.array([bm_returns[bm_date_idx[d]] for d in common_dates if d in bm_date_idx], dtype=float)
                    bm_aligned_return = float(np.prod(1 + bm_aligned_rets) - 1) if len(bm_aligned_rets) > 0 else None

                price_rows = []
                for r in rows:
                    date_to_idx = {d: i for i, d in enumerate(r['dates'])}
                    aligned_closes = np.array([float(r['close_series'][date_to_idx[d]]) for d in common_dates], dtype=float)
                    price_rows.append(aligned_closes)

                price_matrix = np.array(price_rows, dtype=float)
                start_values = np.array(
                    [float(r.get('timing_start_value', 0.0) or 0.0) for r in rows],
                    dtype=float,
                )
                timing_info = _compute_timing_component(price_matrix, start_values)

                # 归一化权重
                for r in rows:
                    r['weight'] = float(r['weight_base'] / total_weight_base)

                # 静态线性收益（用于行业配置/选股拆分）
                static_total_return = float(sum(r['weight'] * r['stock_return'] for r in rows))
                realized_total_return = float(timing_info.get('realized_total_return', static_total_return))
                timing_return = float(timing_info.get('timing_return', 0.0))
                total_return = realized_total_return

                # 计算行业收益（行业内按权重加权）
                sector_weight_sum = {}
                sector_weighted_return_sum = {}
                for r in rows:
                    s = r['sector']
                    sector_weight_sum[s] = sector_weight_sum.get(s, 0.0) + r['weight']
                    sector_weighted_return_sum[s] = sector_weighted_return_sum.get(s, 0.0) + r['weight'] * r['stock_return']

                sector_return_map = {
                    s: (sector_weighted_return_sum[s] / sector_weight_sum[s]) if sector_weight_sum[s] > 0 else 0.0
                    for s in sector_weight_sum
                }

                # 可审计拆解：
                # sector_allocation = sum(weight * sector_return)
                # stock_selection = sum(weight * (stock_return - sector_return))
                # timing = realized_total_return - static_total_return
                sector_allocation_return = float(sum(r['weight'] * sector_return_map.get(r['sector'], 0.0) for r in rows))
                stock_selection_return = float(sum(
                    r['weight'] * (r['stock_return'] - sector_return_map.get(r['sector'], 0.0))
                    for r in rows
                ))

                # 数值稳定处理，确保分解和与总收益一致
                decomposition_total = stock_selection_return + sector_allocation_return + timing_return
                residual = total_return - decomposition_total
                timing_return += residual

                attribution_by_stock = []
                for r in rows:
                    contribution = r['weight'] * r['stock_return']
                    attribution_by_stock.append({
                        'code': r['code'],
                        'sector': r['sector'],
                        'weight': float(r['weight']),
                        'weight_pct': _to_pct(r['weight']),
                        'stock_return': float(r['stock_return']),
                        'stock_return_pct': _to_pct(r['stock_return']),
                        'lifetime_return': float(r.get('lifetime_return', r['stock_return'])),
                        'lifetime_return_pct': _to_pct(float(r.get('lifetime_return', r['stock_return']))),
                        'contribution': float(contribution),
                        'contribution_pct': _to_pct(contribution),
                    })

                attribution_by_stock.sort(key=lambda x: x['contribution'], reverse=True)

                return ok({
                    'portfolio_id': portfolio_id,
                    'total_return': float(total_return),
                    'total_return_pct': _to_pct(total_return),
                    'attribution': {
                        'stock_selection': {
                            'return': float(stock_selection_return),
                            'contribution': _to_pct(stock_selection_return),
                            'description': '个股选择贡献（相对行业收益的超额）'
                        },
                        'sector_allocation': {
                            'return': float(sector_allocation_return),
                            'contribution': _to_pct(sector_allocation_return),
                            'description': '行业配置贡献（按行业加权收益）'
                        },
                        'timing': {
                            'return': float(timing_return),
                            'contribution': _to_pct(timing_return),
                            'description': '择时贡献（真实路径收益 - 静态权重线性收益）',
                            'status': 'implemented',
                            'basis': 'buy_and_hold_path_minus_static_linear',
                            'aligned_days': int(timing_info.get('aligned_days', min_len)),
                            'assets_used': int(timing_info.get('assets_used', len(rows))),
                            'static_total_return': float(static_total_return),
                            'realized_total_return': float(realized_total_return),
                        }
                    },
                    'attribution_by_stock': attribution_by_stock,
                    'sector_performance': {
                        sector: {
                            'weight': float(sector_weight_sum[sector]),
                            'weight_pct': _to_pct(sector_weight_sum[sector]),
                            'return': float(sector_return_map[sector]),
                            'return_pct': _to_pct(sector_return_map[sector]),
                        }
                        for sector in sector_return_map
                    },
                    'method': 'weighted_return_decomposition_v2_with_timing',
                    'benchmark_alignment': {
                        'benchmark': benchmark,
                        'benchmark_return': float(bm_aligned_return) if bm_aligned_return is not None else None,
                        'benchmark_return_pct': _to_pct(bm_aligned_return) if bm_aligned_return is not None else None,
                        'excess_return': float(total_return - bm_aligned_return) if bm_aligned_return is not None else None,
                        'excess_return_pct': _to_pct(total_return - bm_aligned_return) if bm_aligned_return is not None else None,
                        'aligned': bm_aligned_return is not None,
                        'alignment_method': 'calendar_date_intersection',
                    },
                    'data_window': {
                        'lookback_days': int(lookback_days),
                        'aligned_days': int(timing_info.get('aligned_days', min_len)),
                    },
                    'fees': fee_disclosure,
                    'window_audit': _build_window_audit(
                        lookback_days=lookback_days,
                        aligned_days=int(timing_info.get('aligned_days', min_len)),
                        rolling_window=rolling_window,
                    ),
                })

            elif action == 'benchmark_comparison':
                portfolio_id = _safe_portfolio_id(kwargs.get('portfolio_id'))
                benchmark = kwargs.get('benchmark', '000001')
                lookback_days = int(kwargs.get('lookback_days', 252) or 252)
                lookback_days = max(20, min(2000, lookback_days))
                rolling_window = int(kwargs.get('rolling_window', 20) or 20)
                rolling_window = max(2, min(252, rolling_window))
                fee_disclosure = _build_fee_disclosure(kwargs)

                metrics_result = await performance_manager(
                    action='calculate_metrics',
                    portfolio_id=portfolio_id,
                    lookback_days=lookback_days
                )

                if not metrics_result.get('success'):
                    return metrics_result
                # calculate_metrics 在“未找到组合”场景会返回 ok(message=...)，
                # 但不会包含 total_return；此处直接透传提示，避免 KeyError。
                if not isinstance(metrics_result.get('data'), dict) or 'total_return' not in metrics_result['data']:
                    return metrics_result

                metrics_data = metrics_result['data']

                async with db.acquire() as conn:
                    holdings = await conn.fetch(
                        "SELECT * FROM holdings WHERE portfolio_id = $1",
                        portfolio_id
                    )

                portfolio_daily_returns = await _build_portfolio_daily_returns(db, holdings, lookback_days, fee_disclosure=fee_disclosure)

                # 基准：带日期的收益率，用于日历对齐
                bm_dates, bm_returns, _ = await _fetch_dated_returns_for_code(db, benchmark, lookback_days)

                # 组合收益率来自 _build_portfolio_daily_returns（已日历对齐内部持仓），
                # 但组合与基准之间仍需日历对齐。
                # 组合侧无日期输出，这里用基准尾部截断近似；
                # 若需精确对齐，需组合也输出日期——当前先用长度交集。
                if len(bm_returns) == 0:
                    benchmark_daily_returns = np.array([])
                else:
                    benchmark_daily_returns = bm_returns

                min_len = min(len(portfolio_daily_returns), len(benchmark_daily_returns))
                if min_len < 2:
                    return fail('组合或基准收益序列不足，无法计算 tracking_error')

                p_ret = portfolio_daily_returns[-min_len:]
                b_ret = benchmark_daily_returns[-min_len:]
                excess_daily = p_ret - b_ret

                portfolio_return = _calc_period_return(p_ret)
                benchmark_return = _calc_period_return(b_ret)
                excess_return = portfolio_return - benchmark_return

                tracking_error = float(np.std(excess_daily, ddof=1) * np.sqrt(252)) if len(excess_daily) > 1 else 0.0
                annualized_excess_return = (1.0 + excess_return) ** (252 / min_len) - 1.0
                information_ratio = annualized_excess_return / tracking_error if tracking_error > 0 else 0.0

                return ok({
                    'portfolio_id': portfolio_id,
                    'benchmark': benchmark,
                    'portfolio_return': float(portfolio_return),
                    'portfolio_return_pct': _to_pct(portfolio_return),
                    'benchmark_return': float(benchmark_return),
                    'benchmark_return_pct': _to_pct(benchmark_return),
                    'excess_return': float(excess_return),
                    'excess_return_pct': _to_pct(excess_return),
                    'tracking_error': float(tracking_error),
                    'tracking_error_pct': _to_pct(tracking_error),
                    'annualized_excess_return': float(annualized_excess_return),
                    'annualized_excess_return_pct': _to_pct(annualized_excess_return),
                    'information_ratio': float(information_ratio),
                    'outperformance': excess_return > 0,
                    'lookback_days': lookback_days,
                    'aligned_days': int(min_len),
                    'portfolio_total_return_account': float(metrics_data.get('total_return', 0.0)),
                    'portfolio_total_return_series': float(metrics_data.get('series_total_return', portfolio_return)),
                    'fees': fee_disclosure,
                    'window_audit': _build_window_audit(
                        lookback_days=lookback_days,
                        aligned_days=int(min_len),
                        rolling_window=rolling_window,
                    ),
                })

            else:
                return fail(f'Unknown action: {action}. Supported: help, calculate_metrics, backtest_metrics, attribution, benchmark_comparison')
        except Exception as e:
            return fail(str(e))
