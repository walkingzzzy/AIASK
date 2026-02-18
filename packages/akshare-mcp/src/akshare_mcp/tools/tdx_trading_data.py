"""
TdxQuant 交易数据模块 (Phase 1)

封装通达信本地数据包中的 GP/BK/SC 系列交易数据：
- GP 系列：股票交易数据（股东户数/龙虎榜/融资融券/大宗交易/增减持/陆股通等）
- BK 系列：板块交易数据（板块PE/PB/涨跌家数/涨停家数/融资融券/陆股通等）
- SC 系列：市场交易数据（全市场融资融券/陆股通/涨跌停/股指期货/ETF申赎等）

这些数据为 TDX 本地数据包独有，AkShare/Tushare 无法替代。
需要先在通达信客户端中下载「盘后数据包」。
"""

from datetime import datetime

from ..data_source import data_source


# ============== GP 字段定义 ==============

GP_FIELDS = {
    "GP1": "股东人数 股东户数(户)",
    "GP2": "龙虎榜 买入总计(万元) 卖出总计(万元)",
    "GP3": "融资融券 融资余额(万元) 融券余量(股)",
    "GP4": "大宗交易 成交均价(元) 成交额(万元)",
    "GP5": "增减持 成交均价(元) 变动股数(股)",
    "GP6": "陆股通持股量 持股数量(股)",
    "GP7": "陆股通市场成交净额 陆股通市场净买入(万元)",
    "GP15": "涨跌停 涨跌停状态 封单金额(万元)",
    "GP16": "总市值 总市值(万元)",
    "GP21": "股息率 股息率(%)",
}

# ============== BK 字段定义 ==============

BK_FIELDS = {
    "BK5": "市盈率TTM 整体法 算术平均",
    "BK6": "市净率MRQ 整体法 算术平均",
    "BK7": "市销率TTM 整体法 算术平均",
    "BK8": "市现率TTM 整体法 算术平均",
    "BK9": "涨跌数 上涨家数 下跌家数",
    "BK10": "板块总市值(亿元) 整体法 算术平均",
    "BK11": "板块流通市值(亿元) 整体法 算术平均",
    "BK12": "涨停数 涨停家数 曾涨停家数",
    "BK13": "跌停数 跌停家数 曾跌停家数",
    "BK14": "涨停数据 市场高度 2板及以上涨停个数",
    "BK15": "融资融券 沪深京融资余额(万元) 沪深京融券余额(万元)",
    "BK16": "陆股通资金流入 沪股通流入金额(亿元) 深股通流入金额(亿元)",
    "BK17": "开盘成交数 开盘成交额(万元) 开盘成交量(万股)",
    "BK18": "板块股息率(%) 算数平均 整体法",
    "BK19": "板块自由流通市值(亿元) 整体法 算术平均",
}

# ============== SC 字段定义 ==============

SC_FIELDS = {
    "SC1": "融资融券 沪深京融资余额(万元) 沪深京融券余额(万元)",
    "SC2": "陆股通资金流入 沪股通流入金额(亿元) 深股通流入金额(亿元)",
    "SC3": "沪深京涨停股个数 涨停股个数 曾涨停股个数",
    "SC4": "沪深京跌停股个数 跌停股个数 曾跌停股个数",
    "SC5": "上证50股指期货 净持仓(手)",
    "SC6": "沪深300股指期货 净持仓(手)",
    "SC7": "中证500股指期货 净持仓(手)",
    "SC8": "ETF基金规模份额数据 ETF基金规模(亿份) ETF净申赎(亿份)",
    "SC10": "增减持统计 增持额(万元) 减持额(万元)",
    "SC11": "大宗交易 溢价的大宗交易额(万元) 折价的大宗交易额(万元)",
    "SC16": "龙虎榜 买入总金额(亿元) 卖出总金额(亿元)",
    "SC20": "陆股通净买入 沪股通净买入额(亿元) 深股通净买入额(亿元)",
    "SC31": "涨跌家数 涨家数（剔除停牌） 跌家数（剔除停牌）",
}


def _validate_yyyymmdd(date_str: str, field_name: str) -> str | None:
    """校验 YYYYMMDD 日期格式与有效性。"""
    if not date_str:
        return None
    if len(date_str) != 8 or not date_str.isdigit():
        return f"{field_name} 格式错误，应为 YYYYMMDD"
    try:
        datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return f"{field_name} 非法日期: {date_str}"
    return None


def _parse_date_to_year_mmdd(date_str: str) -> tuple[int, int]:
    """将 YYYYMMDD 字符串转换为 (year, mmdd) 整数元组。"""
    if not date_str:
        return 0, 0
    return int(date_str[:4]), int(date_str[4:])


def _contains_placeholder(value) -> tuple[int, int]:
    """递归统计占位符（--）数量。返回 (总值数量, 占位符数量)。"""
    if isinstance(value, dict):
        total = 0
        placeholder = 0
        for v in value.values():
            t, p = _contains_placeholder(v)
            total += t
            placeholder += p
        return total, placeholder

    if isinstance(value, (list, tuple, set)):
        total = 0
        placeholder = 0
        for v in value:
            t, p = _contains_placeholder(v)
            total += t
            placeholder += p
        return total, placeholder

    text = str(value).strip() if value is not None else ""
    if value is None:
        return 1, 0
    if text == "--":
        return 1, 1
    return 1, 0


def _build_quality_hints(total_values: int, placeholder_values: int) -> list[str]:
    reasons: list[str] = []
    if placeholder_values <= 0:
        return reasons
    if total_values > 0 and placeholder_values == total_values:
        reasons.append("盘后数据未就绪（返回占位符 --）")
    else:
        reasons.append("数据源返回占位符（部分字段为 --）")
    return reasons


def _normalize_fields(fields: list[str], field_map: dict[str, str], field_prefix: str) -> tuple[list[str], list[str]]:
    """规范化字段并返回（可用字段, 不支持字段）。"""
    normalized: list[str] = []
    for f in fields:
        token = str(f or "").strip().upper()
        if not token:
            continue
        if field_prefix and not token.startswith(field_prefix):
            token = f"{field_prefix}{token}"
        normalized.append(token)

    # 去重并保持顺序
    deduped: list[str] = []
    seen = set()
    for token in normalized:
        if token not in seen:
            seen.add(token)
            deduped.append(token)

    supported = [f for f in deduped if f in field_map]
    unsupported = [f for f in deduped if f not in field_map]
    return supported, unsupported



def tdx_get_stock_trading_data(
    stock_codes: list[str],
    fields: list[str],
    start_date: str = "",
    end_date: str = "",
) -> dict:
    """
    [TDX] 获取股票交易数据（GP系列）

    从通达信本地数据包获取股票级别的交易数据，包括股东户数、龙虎榜、融资融券、
    大宗交易、增减持、陆股通等 AkShare/Tushare 无法替代的独有数据。
    需要先在通达信客户端中下载「盘后数据包」。
    """
    source_chain: list[str] = []
    fallback_reason: list[str] = []
    degraded = False

    if not fields:
        return {"success": False, "error": "fields 不能为空，请指定 GP 字段列表，如 ['GP1', 'GP3']"}

    if not stock_codes:
        return {"success": False, "error": "stock_codes 不能为空"}

    start_err = _validate_yyyymmdd(start_date, "start_date")
    if start_err:
        return {"success": False, "error": start_err}
    end_err = _validate_yyyymmdd(end_date, "end_date")
    if end_err:
        return {"success": False, "error": end_err}
    if end_date and not start_date:
        return {"success": False, "error": "仅传 end_date 无效，请同时传 start_date"}
    if start_date and end_date and start_date > end_date:
        return {"success": False, "error": "start_date 不能晚于 end_date"}

    normalized_fields, unsupported_fields = _normalize_fields(fields, GP_FIELDS, "GP")
    if unsupported_fields:
        degraded = True
        fallback_reason.append(f"字段不支持: {', '.join(unsupported_fields)}")
    if not normalized_fields:
        return {"success": False, "error": "无可用 GP 字段，请检查 fields 参数"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动并下载了盘后数据包"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        tdx_codes = [data_source._convert_to_tdx_code(c) for c in stock_codes]

        if start_date and end_date:
            source_chain.append("tdxquant.get_gpjy_value")
            result = tq.get_gpjy_value(
                stock_list=tdx_codes,
                field_list=normalized_fields,
                start_time=start_date,
                end_time=end_date,
            )
        else:
            source_chain.append("tdxquant.get_gpjy_value_by_date")
            year, mmdd = _parse_date_to_year_mmdd(start_date)
            result = tq.get_gpjy_value_by_date(
                stock_list=tdx_codes,
                field_list=normalized_fields,
                year=year,
                mmdd=mmdd,
            )

        if isinstance(result, dict) and result.get("ErrorId") and result["ErrorId"] != "0":
            return {"success": False, "error": result.get("Error", "查询失败")}

        total_values, placeholder_values = _contains_placeholder(result)
        quality_hints = _build_quality_hints(total_values, placeholder_values)
        if quality_hints:
            degraded = True
            fallback_reason.extend(quality_hints)

        return {
            "success": True,
            "data": result,
            "source": "tdxquant",
            "source_chain": source_chain,
            "fallback_reason": fallback_reason,
            "degraded": degraded,
            "data_quality": {
                "total_values": total_values,
                "placeholder_values": placeholder_values,
                "placeholder_ratio": (placeholder_values / total_values) if total_values else 0.0,
            },
        }
    except Exception as e:
        return {"success": False, "error": f"查询异常: {e}"}


def tdx_get_sector_trading_data(
    sector_codes: list[str],
    fields: list[str],
    start_date: str = "",
    end_date: str = "",
) -> dict:
    """
    [TDX] 获取板块交易数据（BK系列）

    从通达信本地数据包获取板块级别的交易数据，包括板块PE/PB、涨跌家数、
    涨停家数、融资融券、陆股通等数据。
    需要先在通达信客户端中下载「盘后数据包」。
    """
    source_chain: list[str] = []
    fallback_reason: list[str] = []
    degraded = False

    if not fields:
        return {"success": False, "error": "fields 不能为空，请指定 BK 字段列表，如 ['BK5', 'BK9']"}

    if not sector_codes:
        return {"success": False, "error": "sector_codes 不能为空"}

    start_err = _validate_yyyymmdd(start_date, "start_date")
    if start_err:
        return {"success": False, "error": start_err}
    end_err = _validate_yyyymmdd(end_date, "end_date")
    if end_err:
        return {"success": False, "error": end_err}
    if end_date and not start_date:
        return {"success": False, "error": "仅传 end_date 无效，请同时传 start_date"}
    if start_date and end_date and start_date > end_date:
        return {"success": False, "error": "start_date 不能晚于 end_date"}

    normalized_fields, unsupported_fields = _normalize_fields(fields, BK_FIELDS, "BK")
    if unsupported_fields:
        degraded = True
        fallback_reason.append(f"字段不支持: {', '.join(unsupported_fields)}")
    if not normalized_fields:
        return {"success": False, "error": "无可用 BK 字段，请检查 fields 参数"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动并下载了盘后数据包"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        if start_date and end_date:
            source_chain.append("tdxquant.get_bkjy_value")
            result = tq.get_bkjy_value(
                stock_list=sector_codes,
                field_list=normalized_fields,
                start_time=start_date,
                end_time=end_date,
            )
        else:
            source_chain.append("tdxquant.get_bkjy_value_by_date")
            year, mmdd = _parse_date_to_year_mmdd(start_date)
            result = tq.get_bkjy_value_by_date(
                stock_list=sector_codes,
                field_list=normalized_fields,
                year=year,
                mmdd=mmdd,
            )

        if isinstance(result, dict) and result.get("ErrorId") and result["ErrorId"] != "0":
            return {"success": False, "error": result.get("Error", "查询失败")}

        total_values, placeholder_values = _contains_placeholder(result)
        quality_hints = _build_quality_hints(total_values, placeholder_values)
        if quality_hints:
            degraded = True
            fallback_reason.extend(quality_hints)

        return {
            "success": True,
            "data": result,
            "source": "tdxquant",
            "source_chain": source_chain,
            "fallback_reason": fallback_reason,
            "degraded": degraded,
            "data_quality": {
                "total_values": total_values,
                "placeholder_values": placeholder_values,
                "placeholder_ratio": (placeholder_values / total_values) if total_values else 0.0,
            },
        }
    except Exception as e:
        return {"success": False, "error": f"查询异常: {e}"}


def tdx_get_market_trading_data(
    fields: list[str],
    start_date: str = "",
    end_date: str = "",
) -> dict:
    """
    [TDX] 获取市场交易数据（SC系列）

    从通达信本地数据包获取全市场级别的交易数据，包括融资融券、陆股通、
    涨跌停、股指期货净持仓、ETF申赎等数据。
    需要先在通达信客户端中下载「盘后数据包」。
    """
    source_chain: list[str] = []
    fallback_reason: list[str] = []
    degraded = False

    if not fields:
        return {"success": False, "error": "fields 不能为空，请指定 SC 字段列表，如 ['SC1', 'SC3']"}

    start_err = _validate_yyyymmdd(start_date, "start_date")
    if start_err:
        return {"success": False, "error": start_err}
    end_err = _validate_yyyymmdd(end_date, "end_date")
    if end_err:
        return {"success": False, "error": end_err}
    if end_date and not start_date:
        return {"success": False, "error": "仅传 end_date 无效，请同时传 start_date"}
    if start_date and end_date and start_date > end_date:
        return {"success": False, "error": "start_date 不能晚于 end_date"}

    normalized_fields, unsupported_fields = _normalize_fields(fields, SC_FIELDS, "SC")
    if unsupported_fields:
        degraded = True
        fallback_reason.append(f"字段不支持: {', '.join(unsupported_fields)}")
    if not normalized_fields:
        return {"success": False, "error": "无可用 SC 字段，请检查 fields 参数"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动并下载了盘后数据包"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        if start_date and end_date:
            source_chain.append("tdxquant.get_scjy_value")
            result = tq.get_scjy_value(
                field_list=normalized_fields,
                start_time=start_date,
                end_time=end_date,
            )
        else:
            source_chain.append("tdxquant.get_scjy_value_by_date")
            year, mmdd = _parse_date_to_year_mmdd(start_date)
            result = tq.get_scjy_value_by_date(
                field_list=normalized_fields,
                year=year,
                mmdd=mmdd,
            )

        if isinstance(result, dict) and result.get("ErrorId") and result["ErrorId"] != "0":
            return {"success": False, "error": result.get("Error", "查询失败")}

        total_values, placeholder_values = _contains_placeholder(result)
        quality_hints = _build_quality_hints(total_values, placeholder_values)
        if quality_hints:
            degraded = True
            fallback_reason.extend(quality_hints)

        return {
            "success": True,
            "data": result,
            "source": "tdxquant",
            "source_chain": source_chain,
            "fallback_reason": fallback_reason,
            "degraded": degraded,
            "data_quality": {
                "total_values": total_values,
                "placeholder_values": placeholder_values,
                "placeholder_ratio": (placeholder_values / total_values) if total_values else 0.0,
            },
        }
    except Exception as e:
        return {"success": False, "error": f"查询异常: {e}"}


def tdx_list_available_fields(data_type: str = "all") -> dict:
    """
    [TDX] 查询可用的交易数据字段及含义

    GP/BK/SC 系列合计 100+ 个字段，此工具帮助用户查询可用字段。

    Args:
        data_type (str, optional): 数据类型，可选 "gp"(股票)/"bk"(板块)/"sc"(市场)/"all"(全部)，默认 "all"

    Returns:
        dict: {"success": bool, "data": dict}
        data 结构: {"gp": {"GP1": "描述", ...}, "bk": {...}, "sc": {...}}

    Examples:
        tdx_list_available_fields("gp")
        tdx_list_available_fields("all")
    """
    result = {}
    dt = data_type.lower()
    if dt in ("gp", "all"):
        result["gp"] = GP_FIELDS
    if dt in ("bk", "all"):
        result["bk"] = BK_FIELDS
    if dt in ("sc", "all"):
        result["sc"] = SC_FIELDS

    if not result:
        return {
            "success": False,
            "error": f"未知的 data_type: {data_type}，可选 gp/bk/sc/all",
        }

    return {"success": True, "data": result}


def register(mcp):
    """注册 TDX 交易数据工具"""
    mcp.tool()(tdx_get_stock_trading_data)
    mcp.tool()(tdx_get_sector_trading_data)
    mcp.tool()(tdx_get_market_trading_data)
    mcp.tool()(tdx_list_available_fields)
