"""告警工具 — P3 增强：RSI/MACD/volume 指标评估 + combo 告警 + DB 持久化"""

import logging
from typing import List, Dict, Any
import numpy as np
from ..utils import ok, fail, normalize_code
from .market import get_realtime_quote

logger = logging.getLogger(__name__)

# 进程内告警存储（供 alerts.py 与 alerts_manager.py 共享）
_alerts_store: Dict[str, Dict[str, Any]] = {}

# 比较运算符
_COMPARE_OPS = {
    '>': lambda p, v: p > v,
    '<': lambda p, v: p < v,
    '>=': lambda p, v: p >= v,
    '<=': lambda p, v: p <= v,
    '==': lambda p, v: abs(p - v) < 1e-6,
}


def _calc_rsi(closes: list, period: int = 14) -> float | None:
    """计算 RSI"""
    if len(closes) < period + 1:
        return None
    arr = np.array(closes, dtype=float)
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _calc_macd_histogram(closes: list) -> float | None:
    """计算 MACD 柱值（DIF - DEA）"""
    if len(closes) < 35:
        return None
    arr = np.array(closes, dtype=float)
    ema12 = _ema(arr, 12)
    ema26 = _ema(arr, 26)
    dif = ema12 - ema26
    dea = _ema(dif, 9)
    return float((dif[-1] - dea[-1]) * 2)

def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均"""
    alpha = 2.0 / (period + 1)
    result = np.empty_like(data)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


async def _get_closes(code: str, limit: int = 60) -> list:
    """获取最近 K 线收盘价"""
    try:
        from ..storage import get_db
        db = get_db()
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT close FROM kline_1d WHERE code=$1 ORDER BY time DESC LIMIT $2",
                code, limit
            )
            return [float(r['close']) for r in reversed(rows)]
    except Exception:
        return []


async def _evaluate_indicator(alert: dict, quote_cache: dict) -> dict:
    """评估单个指标告警，返回带 triggered/current_value 的 alert dict"""
    item = dict(alert)
    item['triggered'] = False
    code = item.get('code', '')
    indicator = str(item.get('indicator', '')).lower()
    condition = item.get('condition')
    threshold = float(item.get('value', 0.0))

    current_value = None

    if indicator == 'price':
        if code and code not in quote_cache:
            quote_cache[code] = get_realtime_quote(code) if code else {}
        quote = quote_cache.get(code, {})
        quote_data = quote.get('data') or {} if isinstance(quote, dict) else {}
        current_value = quote_data.get('price')

    elif indicator == 'rsi':
        closes = await _get_closes(code)
        current_value = _calc_rsi(closes)

    elif indicator == 'macd':
        closes = await _get_closes(code)
        current_value = _calc_macd_histogram(closes)

    elif indicator == 'volume':
        if code and code not in quote_cache:
            quote_cache[code] = get_realtime_quote(code) if code else {}
        quote = quote_cache.get(code, {})
        quote_data = quote.get('data') or {} if isinstance(quote, dict) else {}
        current_value = quote_data.get('volume')

    item['current_value'] = current_value
    if current_value is not None and condition in _COMPARE_OPS:
        item['triggered'] = bool(_COMPARE_OPS[condition](float(current_value), threshold))

    return item


async def _evaluate_combo(alert: dict, quote_cache: dict) -> dict:
    """评估组合告警"""
    item = dict(alert)
    item['triggered'] = False
    conditions = item.get('conditions', [])
    logic = str(item.get('logic', 'AND')).upper()

    results = []
    for cond in conditions:
        sub = {
            'code': cond.get('code', ''),
            'indicator': cond.get('indicator', 'price'),
            'condition': cond.get('condition', '>'),
            'value': cond.get('value', 0),
            'type': 'indicator',
        }
        evaluated = await _evaluate_indicator(sub, quote_cache)
        results.append(evaluated.get('triggered', False))

    if logic == 'AND':
        item['triggered'] = all(results) if results else False
    else:
        item['triggered'] = any(results) if results else False

    item['sub_results'] = results
    return item


def register(mcp):
    """注册告警工具"""

    @mcp.tool()
    async def create_indicator_alert(
        code: str,
        indicator: str,
        condition: str,
        value: float
    ):
        """创建指标告警

        Args:
            code: 股票代码
            indicator: 指标名称 ('price', 'rsi', 'macd', 'volume')
            condition: 条件 ('>', '<', '>=', '<=', '==')
            value: 阈值
        """
        try:
            code = normalize_code(code)
            alert_id = f'alert_{code}_{indicator}_{condition}'
            alert = {
                'alert_id': alert_id,
                'code': code,
                'indicator': indicator,
                'condition': condition,
                'value': float(value),
                'active': True,
                'type': 'indicator',
                'triggered': False,
            }
            _alerts_store[alert_id] = alert

            # 持久化到 DB
            try:
                from ..storage import get_db
                db = get_db()
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO alerts (user_id, code, indicator, condition, value, status)
                           VALUES ('default', $1, $2, $3, $4, 'active')
                           ON CONFLICT DO NOTHING""",
                        code, indicator, condition, float(value)
                    )
            except Exception as e:
                logger.warning("[Alerts] DB persist failed: %s", e)

            return ok(alert)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def create_combo_alert(
        name: str,
        conditions: List[Dict[str, Any]],
        logic: str = 'AND'
    ):
        """创建组合告警

        Args:
            name: 告警名称
            conditions: 条件列表 [{"code":"600519","indicator":"rsi","condition":">","value":70}, ...]
            logic: 逻辑关系 ('AND', 'OR')
        """
        try:
            alert_id = f'combo_{name}'
            alert = {
                'alert_id': alert_id,
                'name': name,
                'conditions': conditions,
                'logic': logic,
                'active': True,
                'type': 'combo',
                'triggered': False,
            }
            _alerts_store[alert_id] = alert

            # 持久化到 DB combo_alerts 表
            try:
                import json as _json
                from ..storage import get_db
                db = get_db()
                async with db.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO combo_alerts (name, conditions, logic, status)
                           VALUES ($1, $2, $3, 'active')
                           ON CONFLICT DO NOTHING""",
                        name, _json.dumps(conditions), logic
                    )
            except Exception as e:
                logger.warning("[Alerts] combo DB persist failed: %s", e)

            return ok(alert)
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def check_all_alerts(
        status: str = 'active',
        alert_type: str = 'all'
    ):
        """检查所有告警（支持 price/rsi/macd/volume 指标 + combo 组合告警）

        Args:
            status: 状态 ('active', 'inactive', 'all')
            alert_type: 类型 ('indicator', 'combo', 'all')
        """
        try:
            # 每次从 DB 同步告警（DB 为 source of truth）
            try:
                import json as _json
                from ..storage import get_db
                db = get_db()
                async with db.acquire() as conn:
                    # 加载指标告警
                    rows = await conn.fetch("SELECT * FROM alerts WHERE status='active'")
                    for r in rows:
                        aid = f"alert_{r.get('code','')}_{r.get('indicator','')}_{r.get('condition','')}"
                        _alerts_store[aid] = {
                            'alert_id': aid,
                            'code': r.get('code', ''),
                            'indicator': r.get('indicator', 'price'),
                            'condition': r.get('condition', '>'),
                            'value': float(r.get('value', 0)),
                            'active': True,
                            'type': 'indicator',
                            'triggered': False,
                        }
                    # 加载组合告警
                    combo_rows = await conn.fetch("SELECT * FROM combo_alerts WHERE status='active'")
                    for r in combo_rows:
                        name = r.get('name', '')
                        aid = f"combo_{name}"
                        conds = r.get('conditions', '[]')
                        if isinstance(conds, str):
                            conds = _json.loads(conds)
                        _alerts_store[aid] = {
                            'alert_id': aid,
                            'name': name,
                            'conditions': conds,
                            'logic': r.get('logic', 'AND'),
                            'active': True,
                            'type': 'combo',
                            'triggered': False,
                        }
            except Exception as e:
                logger.warning("[Alerts] DB sync failed: %s", e)

            alerts = list(_alerts_store.values())
            if status == 'active':
                alerts = [a for a in alerts if a.get('active', True)]
            elif status == 'inactive':
                alerts = [a for a in alerts if not a.get('active', True)]

            if alert_type in ('indicator', 'combo'):
                alerts = [a for a in alerts if a.get('type') == alert_type]

            quote_cache: Dict[str, Any] = {}
            triggered_count = 0
            evaluated: List[Dict[str, Any]] = []

            for alert in alerts:
                if alert.get('type') == 'combo':
                    item = await _evaluate_combo(alert, quote_cache)
                else:
                    item = await _evaluate_indicator(alert, quote_cache)

                if item.get('triggered'):
                    triggered_count += 1
                evaluated.append(item)

            return ok({
                'alerts': evaluated,
                'count': len(evaluated),
                'triggered_count': triggered_count,
                'status': status,
                'type': alert_type,
            })
        except Exception as e:
            return fail(str(e))

