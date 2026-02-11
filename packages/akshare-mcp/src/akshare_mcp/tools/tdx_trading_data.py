"""
TdxQuant 交易数据模块 (Phase 1)

封装通达信本地数据包中的 GP/BK/SC 系列交易数据：
- GP 系列：股票交易数据（股东户数/龙虎榜/融资融券/大宗交易/增减持/陆股通等）
- BK 系列：板块交易数据（板块PE/PB/涨跌家数/涨停家数/融资融券/陆股通等）
- SC 系列：市场交易数据（全市场融资融券/陆股通/涨跌停/股指期货/ETF申赎等）

这些数据为 TDX 本地数据包独有，AkShare/Tushare 无法替代。
需要先在通达信客户端中下载「盘后数据包」。
"""

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


def _parse_date_to_year_mmdd(date_str: str) -> tuple[int, int]:
    """将 YYYYMMDD 字符串转换为 (year, mmdd) 整数元组

    示例：'20250615' → (2025, 615)
          '20250103' → (2025, 103)
          ''         → (0, 0)  # 取最新数据
    """
    if not date_str:
        return 0, 0
    return int(date_str[:4]), int(date_str[4:])



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

    Args:
        stock_codes (list[str], required): 股票代码列表，如 ["600519", "000001"]
        fields (list[str], required): GP 字段列表，如 ["GP1", "GP3", "GP6"]
            常用字段：
            - GP1: 股东户数(户)
            - GP2: 龙虎榜 买入/卖出总计(万元)
            - GP3: 融资融券 融资余额(万元)/融券余量(股)
            - GP4: 大宗交易 成交均价(元)/成交额(万元)
            - GP5: 增减持 成交均价(元)/变动股数(股)
            - GP6: 陆股通持股量(股)
            - GP7: 陆股通市场净买入(万元)
            - GP15: 涨跌停状态/封单金额(万元)
            - GP16: 总市值(万元)
            - GP21: 股息率(%)
        start_date (str, optional): 起始日期 YYYYMMDD，为空则取最新
        end_date (str, optional): 结束日期 YYYYMMDD

    Returns:
        dict: {"success": bool, "data": dict, "source": "tdxquant"}
        日期范围查询时 data 结构: {stock_code: {field: [{"Date": str, "Value": [str, ...]}]}}
        单日期/最新查询时 data 结构: {stock_code: {field: [str, ...]}}

    Errors:
        - TdxQuant 不可用时返回 success=false
        - fields 为空时返回 success=false

    Examples:
        tdx_get_stock_trading_data(["600519"], ["GP1", "GP3", "GP6"])
        tdx_get_stock_trading_data(["600519", "000001"], ["GP3"], start_date="20250101", end_date="20250131")
    """
    if not fields:
        return {"success": False, "error": "fields 不能为空，请指定 GP 字段列表，如 ['GP1', 'GP3']"}

    if not stock_codes:
        return {"success": False, "error": "stock_codes 不能为空"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动并下载了盘后数据包"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        # 转换代码格式：600519 → 600519.SH
        tdx_codes = [data_source._convert_to_tdx_code(c) for c in stock_codes]

        # 判断查询模式
        if start_date and end_date:
            # 日期范围查询
            result = tq.get_gpjy_value(
                stock_list=tdx_codes,
                field_list=fields,
                start_time=start_date,
                end_time=end_date,
            )
        else:
            # 单日期/最新查询
            year, mmdd = _parse_date_to_year_mmdd(start_date)
            result = tq.get_gpjy_value_by_date(
                stock_list=tdx_codes,
                field_list=fields,
                year=year,
                mmdd=mmdd,
            )

        if isinstance(result, dict) and result.get("ErrorId"):
            if result["ErrorId"] != "0":
                return {"success": False, "error": result.get("Error", "查询失败")}

        return {"success": True, "data": result, "source": "tdxquant"}
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

    Args:
        sector_codes (list[str], required): 板块代码列表，如 ["880660.SH"]
        fields (list[str], required): BK 字段列表，如 ["BK5", "BK9", "BK12"]
            常用字段：
            - BK5: 市盈率TTM 整体法/算术平均
            - BK6: 市净率MRQ 整体法/算术平均
            - BK9: 涨跌数 上涨家数/下跌家数
            - BK10: 板块总市值(亿元)
            - BK11: 板块流通市值(亿元)
            - BK12: 涨停数 涨停家数/曾涨停家数
            - BK13: 跌停数 跌停家数/曾跌停家数
            - BK15: 融资融券 融资余额(万元)/融券余额(万元)
            - BK16: 陆股通 沪股通流入(亿元)/深股通流入(亿元)
            - BK18: 板块股息率(%)
        start_date (str, optional): 起始日期 YYYYMMDD，为空则取最新
        end_date (str, optional): 结束日期 YYYYMMDD
            日期参数说明：start_date 和 end_date 均非空时按日期范围查询；
            仅 start_date 非空时按指定日期查询；均为空时取最新数据。

    Returns:
        dict: {"success": bool, "data": dict, "source": "tdxquant"}
        日期范围查询时 data 结构: {sector_code: {field: [{"Date": str, "Value": [str, ...]}]}}
        单日期/最新查询时 data 结构: {sector_code: {field: [str, ...]}}

    Errors:
        - TdxQuant 不可用时返回 success=false
        - fields 为空时返回 success=false

    Examples:
        tdx_get_sector_trading_data(["880660.SH"], ["BK5", "BK9", "BK12"])
        tdx_get_sector_trading_data(["880660.SH"], ["BK15", "BK16"], start_date="20250101", end_date="20250131")
    """
    if not fields:
        return {"success": False, "error": "fields 不能为空，请指定 BK 字段列表，如 ['BK5', 'BK9']"}

    if not sector_codes:
        return {"success": False, "error": "sector_codes 不能为空"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动并下载了盘后数据包"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        if start_date and end_date:
            result = tq.get_bkjy_value(
                stock_list=sector_codes,
                field_list=fields,
                start_time=start_date,
                end_time=end_date,
            )
        else:
            year, mmdd = _parse_date_to_year_mmdd(start_date)
            result = tq.get_bkjy_value_by_date(
                stock_list=sector_codes,
                field_list=fields,
                year=year,
                mmdd=mmdd,
            )

        if isinstance(result, dict) and result.get("ErrorId"):
            if result["ErrorId"] != "0":
                return {"success": False, "error": result.get("Error", "查询失败")}

        return {"success": True, "data": result, "source": "tdxquant"}
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

    Args:
        fields (list[str], required): SC 字段列表，如 ["SC1", "SC2", "SC3"]
            常用字段：
            - SC1: 融资融券 融资余额(万元)/融券余额(万元)
            - SC2: 陆股通资金流入 沪股通(亿元)/深股通(亿元)
            - SC3: 涨停股个数/曾涨停股个数
            - SC4: 跌停股个数/曾跌停股个数
            - SC5: 上证50股指期货净持仓(手)
            - SC6: 沪深300股指期货净持仓(手)
            - SC7: 中证500股指期货净持仓(手)
            - SC8: ETF基金规模(亿份)/ETF净申赎(亿份)
            - SC10: 增减持统计 增持额(万元)/减持额(万元)
            - SC11: 大宗交易 溢价额(万元)/折价额(万元)
            - SC16: 龙虎榜 买入(亿元)/卖出(亿元)
            - SC20: 陆股通净买入 沪股通(亿元)/深股通(亿元)
            - SC31: 涨跌家数（剔除停牌）
        start_date (str, optional): 起始日期 YYYYMMDD，为空则取最新
        end_date (str, optional): 结束日期 YYYYMMDD
            日期参数说明：start_date 和 end_date 均非空时按日期范围查询；
            仅 start_date 非空时按指定日期查询；均为空时取最新数据。

    Returns:
        dict: {"success": bool, "data": dict, "source": "tdxquant"}
        日期范围查询时 data 结构: {field: [{"Date": str, "Value": [str, ...]}]}
        单日期/最新查询时 data 结构: {field: [str, ...]}

    Errors:
        - TdxQuant 不可用时返回 success=false
        - fields 为空时返回 success=false

    Examples:
        tdx_get_market_trading_data(["SC1", "SC2", "SC3"])
        tdx_get_market_trading_data(["SC3", "SC4", "SC31"], start_date="20250101", end_date="20250131")
    """
    if not fields:
        return {"success": False, "error": "fields 不能为空，请指定 SC 字段列表，如 ['SC1', 'SC3']"}

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动并下载了盘后数据包"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        if start_date and end_date:
            result = tq.get_scjy_value(
                field_list=fields,
                start_time=start_date,
                end_time=end_date,
            )
        else:
            year, mmdd = _parse_date_to_year_mmdd(start_date)
            result = tq.get_scjy_value_by_date(
                field_list=fields,
                year=year,
                mmdd=mmdd,
            )

        if isinstance(result, dict) and result.get("ErrorId"):
            if result["ErrorId"] != "0":
                return {"success": False, "error": result.get("Error", "查询失败")}

        return {"success": True, "data": result, "source": "tdxquant"}
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
