"""股票列表工具"""

from ...utils import ok, fail
from ...core.cache_manager import cached
from .helpers import get_stock_list_cached


@cached(ttl=86400.0)  # 24h cache
def get_stock_list() -> dict:
    """获取A股股票列表，返回股票代码和名称。

    Examples:
        get_stock_list()
    """
    try:
        data, _ = get_stock_list_cached()
        return ok({'stocks': data, 'count': len(data)})
    except Exception as e:
        return fail(str(e))
