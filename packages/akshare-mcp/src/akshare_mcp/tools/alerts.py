"""告警工具"""

from typing import List, Dict, Any
from ..utils import ok, fail, normalize_code


# 进程内告警存储（供 alerts.py 与 alerts_manager.py 共享）
_alerts_store: Dict[str, Dict[str, Any]] = {}


def register(mcp):
    """注册告警工具"""

    @mcp.tool()
    async def create_indicator_alert(
        code: str,
        indicator: str,
        condition: str,
        value: float
    ):
        """
        创建指标告警

        Args:
            code: 股票代码
            indicator: 指标名称 ('price', 'rsi', 'macd', etc.)
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
            return ok(alert)

        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def create_combo_alert(
        name: str,
        conditions: List[Dict[str, Any]],
        logic: str = 'AND'
    ):
        """
        创建组合告警

        Args:
            name: 告警名称
            conditions: 条件列表
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
            return ok(alert)

        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def check_all_alerts(
        status: str = 'active',
        alert_type: str = 'all'
    ):
        """
        检查所有告警

        Args:
            status: 状态 ('active', 'inactive', 'all')
            alert_type: 类型 ('indicator', 'combo', 'all')
        """
        try:
            alerts = list(_alerts_store.values())
            if status == 'active':
                alerts = [a for a in alerts if a.get('active', True)]
            elif status == 'inactive':
                alerts = [a for a in alerts if not a.get('active', True)]

            if alert_type in ('indicator', 'combo'):
                alerts = [a for a in alerts if a.get('type') == alert_type]

            return ok({
                'alerts': alerts,
                'count': len(alerts),
                'status': status,
                'type': alert_type
            })

        except Exception as e:
            return fail(str(e))
