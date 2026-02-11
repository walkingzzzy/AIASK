"""告警管理器 - 创建、查询、更新、删除告警（增强版）

统一使用 alerts.py 的进程内存存储 _alerts_store，
确保 alerts_manager 与 create_indicator_alert / check_all_alerts 数据一致。
"""

import json
from ...utils import ok, fail, normalize_code
from ...data_source import data_source
import logging

logger = logging.getLogger(__name__)


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


def register_alerts_manager(mcp):
    """注册告警管理器工具"""

    @mcp.tool()
    async def alerts_manager(action: str, **kwargs):
        """告警管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/list/create/check/update/delete
            kwargs: JSON 字符串或关键字参数，不同 action 所需参数:
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
            kwargs = _normalize_kwargs(dict(kwargs))

            # 统一使用 alerts.py 的内存存储
            from ..alerts import _alerts_store

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
                alerts = list(_alerts_store.values())

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
                alerts = [a for a in _alerts_store.values() if a.get('active', True)]
                triggered = []

                for alert in alerts:
                    if alert.get('type') != 'indicator':
                        continue
                    code = alert.get('code')
                    indicator = alert.get('indicator')
                    condition = alert.get('condition')
                    target_value = alert.get('value')
                    if not all([code, indicator, condition, target_value is not None]):
                        continue

                    current_value = None
                    try:
                        if indicator == 'price':
                            quote = data_source.get_realtime_quote(code)
                            if quote:
                                current_value = quote.get('price')
                        elif indicator == 'change_pct':
                            quote = data_source.get_realtime_quote(code)
                            if quote:
                                current_value = quote.get('changePercent')
                    except Exception as exc:
                        logger.debug(f"[AlertsManager] 获取 {code} 实时数据失败: {exc}")

                    if current_value is not None:
                        alert['current_value'] = current_value
                        _ops = {
                            '>': lambda a, b: a > b,
                            '<': lambda a, b: a < b,
                            '>=': lambda a, b: a >= b,
                            '<=': lambda a, b: a <= b,
                            '==': lambda a, b: abs(a - b) < 1e-6,
                        }
                        op = _ops.get(condition)
                        if op and op(current_value, target_value):
                            alert['triggered'] = True
                            triggered.append({
                                'alert_id': alert['alert_id'],
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
                if not alert:
                    return fail(f'告警不存在: {alert_id}')
                new_status = kwargs.get('status', 'inactive')
                alert['active'] = (new_status == 'active')
                return ok({'alert_id': alert_id, 'status': new_status})

            elif action == 'delete':
                alert_id = kwargs.get('alert_id')
                if not alert_id:
                    return fail('需要提供 alert_id')
                removed = _alerts_store.pop(alert_id, None)
                if removed is None:
                    return fail(f'告警不存在: {alert_id}')
                return ok({'alert_id': alert_id, 'deleted': True})

            else:
                return fail(f'Unknown action: {action}. Supported: help, list, create, check, update, delete')

        except Exception as e:
            logger.error(f"[AlertsManager] Error: {e}")
            return fail(str(e))
