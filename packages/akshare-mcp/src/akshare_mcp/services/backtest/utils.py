"""回测工具函数"""

from typing import List, Dict, Any, Optional, Union
import numpy as np
from akshare_mcp.services.slippage import SlippageCalculator, SlippageModelType


def _ensure_dict_list(klines: List[Union[Dict, Any]]) -> List[Dict[str, Any]]:
    """确保 K线数据是字典列表"""
    result = []
    for k in klines:
        if isinstance(k, dict):
            result.append(k)
        elif hasattr(k, 'model_dump'):
            result.append(k.model_dump())
        elif hasattr(k, '__dict__'):
            result.append({
                attr: getattr(k, attr) 
                for attr in ('date', 'open', 'high', 'low', 'close', 'volume', 'amount') 
                if hasattr(k, attr)
            })
        else:
            result.append(dict(k))
    return result


def _resolve_slippage_model(model_value: Any) -> SlippageModelType:
    """解析滑点模型类型"""
    if isinstance(model_value, SlippageModelType):
        return model_value
    if isinstance(model_value, str):
        normalized = model_value.strip().lower()
        for model in SlippageModelType:
            if model.value == normalized:
                return model
    return SlippageModelType.FIXED


def _compute_slippage_rate(
    prices: np.ndarray,
    volumes: Optional[np.ndarray],
    params: Dict[str, Any],
    default_rate: float = 0.0
) -> float:
    """根据参数计算滑点率"""
    if params is None:
        return default_rate

    if 'slippage_rate' in params and params['slippage_rate'] is not None:
        return float(params['slippage_rate'])

    model_value = params.get('slippage_model')
    if not model_value:
        return default_rate

    model_type = _resolve_slippage_model(model_value)
    calculator = SlippageCalculator(model_type=model_type)

    price = float(np.nanmean(prices)) if prices is not None and len(prices) > 0 else 0.0
    volume = 0.0
    if volumes is not None and len(volumes) > 0:
        volume = float(np.nanmean(volumes))

    if price <= 0:
        return default_rate

    order_size = params.get('order_size')
    if order_size is None:
        order_size = params.get('initial_capital', 100000) / price

    result = calculator.calculate(price, volume, float(order_size), True)
    return abs(float(result.get('slippage_rate', default_rate)))
