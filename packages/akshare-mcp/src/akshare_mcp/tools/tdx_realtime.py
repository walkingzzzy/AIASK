"""
TdxQuant 行情订阅与缓存管理模块 (Phase 4)

封装通达信行情订阅管理、数据缓存刷新、自定义K线公式计算：
- 行情订阅管理：订阅/取消订阅/查询已订阅列表
- 数据缓存刷新：刷新行情缓存/K线缓存
- 自定义K线公式计算：用户传入自定义K线数据进行公式计算
"""

from ..data_source import data_source


def tdx_manage_subscription(
    action: str,
    stock_codes: list[str] = None,
) -> dict:
    """
    [TDX] 行情订阅管理

    管理通达信实时行情订阅，支持订阅、取消订阅和查询已订阅列表。
    MCP 协议为请求-响应模式，不支持持续推送；订阅后可通过 check_all_alerts() 轮询检查。

    Args:
        action (str, required): 操作类型，可选 "subscribe"/"unsubscribe"/"list"
            - subscribe: 订阅指定股票的实时行情
            - unsubscribe: 取消订阅指定股票
            - list: 查询当前已订阅的股票列表
        stock_codes (list[str], optional): 股票代码列表，如 ["600519", "000001"]
            subscribe 和 unsubscribe 时必填，list 时忽略

    Returns:
        dict: {"success": bool, "data"|"message"|"error": ..., "source": "tdxquant"}
        - subscribe: {"success": true, "message": "订阅成功", "data": {...}, "source": "tdxquant"}
        - unsubscribe: {"success": true, "message": "取消订阅成功", "data": {...}, "source": "tdxquant"}
        - list: {"success": true, "data": ["600519.SH", ...], "source": "tdxquant"}

    Errors:
        - action 不在可选范围时返回 success=false
        - subscribe/unsubscribe 时 stock_codes 为空返回 success=false
        - TdxQuant 不可用时返回 success=false

    Examples:
        tdx_manage_subscription("subscribe", ["600519", "000001"])
        tdx_manage_subscription("unsubscribe", ["600519"])
        tdx_manage_subscription("list")
    """
    action = action.lower().strip()
    if action not in ("subscribe", "unsubscribe", "list"):
        return {"success": False, "error": f"未知的 action: {action}，可选 subscribe/unsubscribe/list"}

    if action in ("subscribe", "unsubscribe") and not stock_codes:
        return {"success": False, "error": "stock_codes 不能为空"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        if action == "subscribe":
            # subscribe_hq 已在 data_source.py 中实现（B类），复用
            tdx_codes = [data_source._convert_to_tdx_code(c) for c in stock_codes]
            result = tq.subscribe_hq(stock_list=tdx_codes)
            if isinstance(result, dict) and result.get("ErrorId") and result["ErrorId"] != "0":
                return {"success": False, "error": result.get("Error", "订阅失败")}
            return {"success": True, "message": "订阅成功", "data": result, "source": "tdxquant"}

        elif action == "unsubscribe":
            tdx_codes = [data_source._convert_to_tdx_code(c) for c in stock_codes]
            result = tq.unsubscribe_hq(stock_list=tdx_codes)
            if isinstance(result, dict) and result.get("ErrorId") and result["ErrorId"] != "0":
                return {"success": False, "error": result.get("Error", "取消订阅失败")}
            return {"success": True, "message": "取消订阅成功", "data": result, "source": "tdxquant"}

        else:  # list
            result = tq.get_subscribe_hq_stock_list()
            return {"success": True, "data": result, "source": "tdxquant"}

    except Exception as e:
        return {"success": False, "error": f"操作异常: {e}"}


def tdx_refresh_data(
    refresh_type: str = "all",
    market: str = "AG",
    force: bool = False,
    stock_codes: list[str] = None,
    period: str = "1d",
) -> dict:
    """
    [TDX] 刷新数据缓存

    刷新通达信行情缓存或K线缓存。行情缓存包括最新 snapshot 和K线数据；
    K线缓存可针对指定股票和周期定向下载历史K线。

    Args:
        refresh_type (str, optional): 刷新类型，可选 "cache"/"kline"/"all"，默认 "all"
            - cache: 刷新行情缓存（snapshot + K线）
            - kline: 刷新指定股票的K线缓存
            - all: 同时刷新行情缓存和K线缓存
        market (str, optional): 市场类型（仅 cache 模式），默认 "AG"
            可选: "AG"(A股)/"HK"(港股)/"US"(美股)/"QH"(期货)/"QQ"(期权)/"NQ"(新三板)/"ZZ"(中证国证指数)
        force (bool, optional): 是否强制刷新（仅 cache 模式），默认 False
            False 时距上次刷新不足10分钟则不刷新
        stock_codes (list[str], optional): 股票代码列表（仅 kline 模式），如 ["600519", "000001"]
        period (str, optional): K线周期（仅 kline 模式），默认 "1d"
            可选: "1d"(日线)/"1m"(1分钟)/"5m"(5分钟)

    Returns:
        dict: {"success": bool, "data": dict, "source": "tdxquant"}
        data 包含各刷新操作的返回结果

    Errors:
        - refresh_type 不在可选范围时返回 success=false
        - kline 模式下 stock_codes 为空返回 success=false
        - TdxQuant 不可用时返回 success=false

    Examples:
        tdx_refresh_data("cache")
        tdx_refresh_data("kline", stock_codes=["600519"], period="1d")
        tdx_refresh_data("all", stock_codes=["600519"])
    """
    refresh_type = refresh_type.lower().strip()
    if refresh_type not in ("cache", "kline", "all"):
        return {"success": False, "error": f"未知的 refresh_type: {refresh_type}，可选 cache/kline/all"}

    if refresh_type in ("kline", "all") and not stock_codes:
        if refresh_type == "kline":
            return {"success": False, "error": "kline 模式下 stock_codes 不能为空"}
        # all 模式下 stock_codes 为空时只刷新 cache
        refresh_type = "cache"

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        results = {}

        if refresh_type in ("cache", "all"):
            cache_result = tq.refresh_cache(market, force)
            results["cache"] = cache_result
            if isinstance(cache_result, dict) and cache_result.get("ErrorId") and cache_result["ErrorId"] != "0":
                return {"success": False, "error": cache_result.get("Error", "刷新行情缓存失败"), "data": results}

        if refresh_type in ("kline", "all") and stock_codes:
            tdx_codes = [data_source._convert_to_tdx_code(c) for c in stock_codes]
            kline_result = tq.refresh_kline(stock_list=tdx_codes, period=period)
            results["kline"] = kline_result
            if isinstance(kline_result, dict) and kline_result.get("ErrorId") and kline_result["ErrorId"] != "0":
                return {"success": False, "error": kline_result.get("Error", "刷新K线缓存失败"), "data": results}

        return {"success": True, "data": results, "source": "tdxquant"}
    except Exception as e:
        return {"success": False, "error": f"刷新异常: {e}"}


def tdx_custom_formula_calc(
    stock_code: str,
    kline_data: list[dict],
    formula_name: str = "MACD",
    formula_args: str = "",
    period: str = "1d",
    dividend_type: int = 0,
) -> dict:
    """
    [TDX] 自定义K线公式计算

    允许用户传入自定义K线数据进行通达信公式计算。与现有 tdx_calculate_indicator 的区别：
    现有工具只能使用 TDX 内置K线数据（通过 formula_set_data_info），
    此工具允许传入外部K线数据（通过 formula_format_data + formula_set_data）。

    处理流程：
    1. formula_format_data(kline_data) — 格式化K线数据
    2. formula_set_data(stock_code, period, formatted_data, count) — 设置公式数据
    3. formula_zb(formula_name, formula_args) — 执行公式计算

    Args:
        stock_code (str, required): 股票代码，如 "600519"
        kline_data (list[dict], required): 自定义K线数据列表，每条须包含以下字段：
            - Date (str): 日期时间，如 "2025-01-20 00:00:00"
            - Open (float): 开盘价
            - High (float): 最高价
            - Low (float): 最低价
            - Close (float): 收盘价
            - Volume (float): 成交量
            - Amount (float): 成交额
        formula_name (str, optional): 公式名称，默认 "MACD"
        formula_args (str, optional): 公式参数，逗号分隔，如 "12,26,9"
        period (str, optional): K线周期，默认 "1d"
        dividend_type (int, optional): 复权类型，0不复权/1前复权/2后复权，默认 0

    Returns:
        dict: {"success": bool, "data": dict, "source": "tdxquant"}
        data 为公式计算结果，如 MACD: {"DIF": [...], "DEA": [...], "MACD": [...]}

    Errors:
        - kline_data 为空时返回 success=false
        - TdxQuant 不可用时返回 success=false
        - 格式化或设置数据失败时返回具体错误

    Examples:
        tdx_custom_formula_calc("600519", kline_data=[...], formula_name="MACD", formula_args="12,26,9")
        tdx_custom_formula_calc("000001", kline_data=[...], formula_name="KDJ", formula_args="9,3,3")
    """
    if not stock_code:
        return {"success": False, "error": "stock_code 不能为空"}

    if not kline_data:
        return {"success": False, "error": "kline_data 不能为空，请提供K线数据列表"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        tdx_code = data_source._convert_to_tdx_code(stock_code)

        # Step 1: 格式化K线数据
        # formula_format_data 接受 get_market_data 格式的 dict
        # 输入格式: {stock_code: [kline_list]}，输出格式: {stock_code: [formatted_list]}
        raw_data = {tdx_code: kline_data}
        formatted = tq.formula_format_data(data_dict=raw_data)

        if isinstance(formatted, dict) and formatted.get("ErrorId") and formatted["ErrorId"] != "0":
            return {"success": False, "error": formatted.get("Error", "格式化K线数据失败")}

        # 获取格式化后的数据
        formatted_list = formatted.get(tdx_code, [])
        if not formatted_list:
            # 如果 format 返回的数据直接就是 list（某些版本可能如此）
            if isinstance(formatted, list):
                formatted_list = formatted
            else:
                return {"success": False, "error": "格式化K线数据返回为空"}

        # Step 2: 设置公式数据
        set_result = tq.formula_set_data(
            stock_code=tdx_code,
            stock_period=period,
            stock_data=formatted_list,
            count=len(formatted_list),
            dividend_type=dividend_type,
        )

        if isinstance(set_result, dict) and set_result.get("ErrorId") and set_result["ErrorId"] != "0":
            return {"success": False, "error": set_result.get("Error", "设置公式数据失败")}

        # Step 3: 执行公式计算
        calc_result = tq.formula_zb(formula_name=formula_name, formula_arg=formula_args)

        if isinstance(calc_result, dict) and calc_result.get("ErrorId") and calc_result["ErrorId"] != "0":
            return {"success": False, "error": calc_result.get("Error", "公式计算失败")}

        # 提取计算结果数据
        data = calc_result.get("Data", calc_result) if isinstance(calc_result, dict) else calc_result

        return {"success": True, "data": data, "source": "tdxquant"}
    except Exception as e:
        return {"success": False, "error": f"计算异常: {e}"}


def register(mcp):
    """注册 TDX 行情订阅与缓存管理工具"""
    mcp.tool()(tdx_manage_subscription)
    mcp.tool()(tdx_refresh_data)
    mcp.tool()(tdx_custom_formula_calc)
