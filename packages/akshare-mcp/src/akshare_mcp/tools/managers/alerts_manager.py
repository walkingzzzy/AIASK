"""告警管理器 - 创建、查询、更新、删除告警（增强版）

T09: DB-first 模式 — 所有 CRUD 操作以 DB 为 source of truth，
_alerts_store 仅作为进程内读缓存，每次操作前先从 DB 同步。
"""

from typing import Any
import json
from ...utils import ok, fail, normalize_code
from ..manager_protocol import normalize_manager_payload
import logging

logger = logging.getLogger(__name__)


def _normalize_kwargs(kwargs: dict) -> dict:
    """统一解析 kwargs 参数（兼容 JSON 字符串和 dict）"""
    params = kwargs.get("params")
    if isinstance(params, dict):
        kwargs = {**kwargs, **params}
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


def _safe_user_id(value: object) -> str:
    text = str(value or "").strip()
    return text or "default"


def _make_alert_id(user_id: str, code: str, indicator: str, condition: str) -> str:
    normalized_user = _safe_user_id(user_id)
    if normalized_user == "default":
        return f"alert_{code}_{indicator}_{condition}"
    safe_user = normalized_user.replace(":", "_").replace("/", "_").replace(" ", "_")
    return f"alert_{safe_user}_{code}_{indicator}_{condition}"


def _belongs_to_user(alert: dict, user_id: str) -> bool:
    return _safe_user_id(alert.get("user_id")) == _safe_user_id(user_id)


def _list_user_alerts(alerts_store: dict, user_id: str) -> list[dict]:
    return [alert for alert in alerts_store.values() if _belongs_to_user(alert, user_id)]


def register_alerts_manager(mcp):
    """注册告警管理器工具"""

    @mcp.tool()
    async def alerts_manager(action: str, params: dict | None = None, kwargs: Any = None):
        """告警管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/create/check/update/delete
            kwargs: 支持 structured ``params``、JSON 字符串 ``kwargs`` 或关键字参数，不同 action 所需参数:
                - help: 无需额外参数
                - list: status(str, optional, "active"/"inactive"/"all")
                - create: code(str), indicator(str, "price"/"rsi"/"macd"等), condition(str, ">"/"<"/">="/"<="/"=="), value(float)
                - check: 无需额外参数（检查所有活跃告警）
                - update: alert_id(str), 以及需要更新的字段
                - delete: alert_id(str)

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            alerts_manager(action="help", kwargs="{}")
            # 创建价格告警
            alerts_manager(action="create", kwargs='{"code":"600519","indicator":"price","condition":">","value":1800}')
            # 检查所有活跃告警
            alerts_manager(action="check", kwargs="{}")
            # 列出告警
            alerts_manager(action="list", kwargs='{"status":"active"}')
            # 删除告警
            alerts_manager(action="delete", kwargs='{"alert_id":"alert_600519_price_>"}')
        """
        try:
            # 解析 MCP 传入的 kwargs JSON 字符串
            kwargs = normalize_manager_payload(params=params, kwargs=kwargs)

            # 统一使用 alerts.py 的进程内存存储与评估逻辑
            from ..alerts import _alerts_store, _evaluate_combo, _evaluate_indicator
            user_id = _safe_user_id(kwargs.get("user_id"))

            if action == 'help':
                return ok({
                    'supported_actions': {
                        'list': '列出告警',
                        'create': '创建告警（需要 code, indicator, condition, value）',
                        'check': '检查告警状态',
                        'update': '更新告警（需要 alert_id）',
                        'delete': '删除告警（需要 alert_id）',
                        'help': '显示帮助信息',
                    }
                })

            elif action == 'list':
                status = kwargs.get('status', 'active')

                # T09: DB-first – sync alerts from DB before listing
                try:
                    import json as _json
                    from ...storage import get_db
                    db = get_db()
                    async with db.acquire() as conn:
                        rows = await conn.fetch("SELECT * FROM alerts WHERE status='active'")
                        for r in rows:
                            aid = _make_alert_id(
                                _safe_user_id(r.get('user_id', 'default')),
                                r.get('code', ''),
                                r.get('indicator', ''),
                                r.get('condition', ''),
                            )
                            _alerts_store[aid] = {
                                'alert_id': aid,
                                'user_id': _safe_user_id(r.get('user_id', 'default')),
                                'code': r.get('code', ''),
                                'indicator': r.get('indicator', 'price'),
                                'condition': r.get('condition', '>'),
                                'value': float(r.get('value', 0)),
                                'active': True,
                                'type': 'indicator',
                                'triggered': False,
                            }
                except Exception as e:
                    logger.warning("[AlertsManager] DB sync failed: %s", e)

                alerts = _list_user_alerts(_alerts_store, user_id)

                if status == 'active':
                    alerts = [a for a in alerts if a.get('active', True)]
                elif status == 'inactive':
                    alerts = [a for a in alerts if not a.get('active', True)]
                # status == 'all' → no filter

                return ok({'alerts': alerts, 'count': len(alerts)})

            elif action == 'create':
                code = kwargs.get('code')
                indicator = kwargs.get('indicator')
                condition = kwargs.get('condition')
                value = kwargs.get('value')

                if not all([code, indicator, condition, value is not None]):
                    return fail('需要提供 code, indicator, condition, value')

                code = normalize_code(code)

                valid_indicators = ['price', 'change_pct', 'volume', 'ma5', 'ma20', 'rsi', 'macd']
                valid_conditions = ['>', '<', '>=', '<=', '==']

                if indicator not in valid_indicators:
                    return fail(f'不支持的指标: {indicator}. 支持: {", ".join(valid_indicators)}')

                if condition not in valid_conditions:
                    return fail(f'不支持的条件: {condition}. 支持: {", ".join(valid_conditions)}')

                alert_id = _make_alert_id(user_id, code, indicator, condition)
                alert = {
                    'alert_id': alert_id,
                    'user_id': user_id,
                    'code': code,
                    'indicator': indicator,
                    'condition': condition,
                    'value': float(value),
                    'active': True,
                    'type': 'indicator',
                    'triggered': False,
                }

                # T09: DB-first — persist to DB, then update cache
                try:
                    from ...storage import get_db
                    db = get_db()
                    async with db.acquire() as conn:
                        await conn.execute(
                            """INSERT INTO alerts (user_id, code, indicator, condition, value, status)
                               VALUES ($1, $2, $3, $4, $5, 'active')
                               ON CONFLICT DO NOTHING""",
                            user_id, code, indicator, condition, float(value)
                        )
                except Exception as e:
                    logger.warning("[AlertsManager] DB persist failed: %s", e)

                _alerts_store[alert_id] = alert
                logger.info(f"[AlertsManager] 创建告警: {alert_id}")

                return ok({
                    'alert_id': alert_id,
                    'code': code,
                    'indicator': indicator,
                    'condition': condition,
                    'value': float(value),
                    'status': 'created'
                })

            elif action == 'check':
                alerts = [a for a in _list_user_alerts(_alerts_store, user_id) if a.get('active', True)]
                triggered = []
                quote_cache = {}

                for alert in alerts:
                    try:
                        if alert.get('type') == 'combo':
                            evaluated = await _evaluate_combo(alert, quote_cache)
                        else:
                            evaluated = await _evaluate_indicator(alert, quote_cache)
                    except Exception as exc:
                        logger.debug(f"[AlertsManager] 检查告警失败: {exc}")
                        continue

                    alert_id = str(alert.get('alert_id') or '')
                    if alert_id:
                        _alerts_store[alert_id] = {**alert, **evaluated, 'user_id': user_id}

                    if evaluated.get('triggered') is True:
                        code = str(evaluated.get('code') or '')
                        indicator = str(evaluated.get('indicator') or '')
                        condition = str(evaluated.get('condition') or '')
                        target_value = evaluated.get('value')
                        current_value = evaluated.get('current_value')
                        triggered.append({
                            'alert_id': evaluated.get('alert_id'),
                            'code': code,
                            'indicator': indicator,
                            'condition': condition,
                            'target_value': target_value,
                            'current_value': current_value,
                            'message': f'{code} {indicator} {condition} {target_value} (当前: {current_value})'
                        })

                return ok({
                    'triggered': triggered,
                    'count': len(triggered)
                })

            elif action == 'update':
                alert_id = kwargs.get('alert_id')
                if not alert_id:
                    return fail('需要提供 alert_id')
                alert = _alerts_store.get(alert_id)
                if not alert or not _belongs_to_user(alert, user_id):
                    return fail(f'告警不存在: {alert_id}')
                if 'code' in kwargs and kwargs.get('code'):
                    alert['code'] = normalize_code(kwargs.get('code'))
                if 'indicator' in kwargs and kwargs.get('indicator'):
                    alert['indicator'] = kwargs.get('indicator')
                if 'condition' in kwargs and kwargs.get('condition'):
                    alert['condition'] = kwargs.get('condition')
                if 'value' in kwargs and kwargs.get('value') is not None:
                    try:
                        alert['value'] = float(kwargs.get('value'))
                    except Exception:
                        return fail('value 必须是数字')

                if kwargs.get('status') is not None:
                    alert['active'] = str(kwargs.get('status')).lower() == 'active'
                elif kwargs.get('active') is not None:
                    alert['active'] = bool(kwargs.get('active'))

                # T09: DB-first — sync updated state back to DB
                try:
                    from ...storage import get_db
                    db = get_db()
                    db_status = 'active' if alert.get('active', True) else 'inactive'
                    async with db.acquire() as conn:
                        await conn.execute(
                            """UPDATE alerts SET
                                   code = $1, indicator = $2, condition = $3,
                                   value = $4, status = $5
                               WHERE user_id = $6 AND code = $7 AND indicator = $8 AND condition = $9""",
                            alert.get('code', ''), alert.get('indicator', ''),
                            alert.get('condition', ''), float(alert.get('value', 0)),
                            db_status, user_id,
                            # Use original fields to locate the row
                            alert.get('code', ''), alert.get('indicator', ''),
                            alert.get('condition', ''),
                        )
                except Exception as e:
                    logger.warning("[AlertsManager] DB update failed: %s", e)

                status = 'active' if alert.get('active', True) else 'inactive'
                return ok({'alert_id': alert_id, 'status': status, 'alert': alert})

            elif action == 'delete':
                alert_id = kwargs.get('alert_id')
                if not alert_id:
                    return fail('需要提供 alert_id')
                removed = _alerts_store.get(alert_id)
                if removed is None or not _belongs_to_user(removed, user_id):
                    return fail(f'告警不存在: {alert_id}')

                # T09: DB-first — delete from DB, then evict cache
                try:
                    from ...storage import get_db
                    db = get_db()
                    async with db.acquire() as conn:
                        await conn.execute(
                            """DELETE FROM alerts
                               WHERE user_id = $1 AND code = $2 AND indicator = $3 AND condition = $4""",
                            _safe_user_id(removed.get('user_id', 'default')),
                            removed.get('code', ''), removed.get('indicator', ''),
                            removed.get('condition', ''),
                        )
                except Exception as e:
                    logger.warning("[AlertsManager] DB delete failed: %s", e)

                _alerts_store.pop(alert_id, None)
                return ok({'alert_id': alert_id, 'deleted': True})

            else:
                return fail(f'Unknown action: {action}. Supported: help, list, create, check, update, delete')

        except Exception as e:
            logger.error(f"[AlertsManager] Error: {e}")
            return fail(str(e))
