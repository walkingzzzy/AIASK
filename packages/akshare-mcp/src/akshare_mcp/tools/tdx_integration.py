"""
TdxQuant 通达信量化集成模块

提供与通达信客户端交互的功能：
- 消息推送
- 预警信号
- 自选股/板块管理
"""

import sys
import datetime
from typing import Optional
from ..data_source import data_source
from ..utils import normalize_code
from .risk_guard import risk_audited


def is_tdx_available() -> bool:
    """检查 TdxQuant 是否可用"""
    return data_source.is_tdx_available()


def _tdx_unavailable_payload() -> dict:
    """构造统一的 TDX 不可用错误，携带初始化诊断。"""
    diag = data_source.get_tdx_init_diagnostics()
    stage = diag.get("last_stage") or "unknown"
    err = diag.get("last_error") or "unknown"
    return {
        "success": False,
        "message": f"TdxQuant 不可用: stage={stage}, error={err}",
        "diagnostics": diag,
    }


def _get_tq_or_error() -> tuple[Optional[object], Optional[dict]]:
    """获取可用 tq 实例，不可用时返回标准错误载荷。"""
    tq = data_source.get_tdxquant()
    if tq is None:
        return None, _tdx_unavailable_payload()
    return tq, None


@risk_audited("tdx.push_message")
def push_message(message: str, confirm_token: str | None = None) -> dict:
    """
    推送消息到通达信客户端
    
    Args:
        message (str, required): 消息内容，使用 "|" 分隔可让客户端分行显示
        
    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用时返回 success=false 并提示启动通达信客户端

    Examples:
        push_message("MACD金叉提醒|600519 贵州茅台")
    """
    try:
        tq, err = _get_tq_or_error()
        if err is not None:
            return err
        
        result = tq.send_message(message)
        if result.get("ErrorId") == "0":
            return {"success": True, "message": "消息发送成功"}
        else:
            return {"success": False, "message": result.get("Error", "发送失败")}
    except Exception as e:
        return {"success": False, "message": f"发送异常: {e}"}


@risk_audited("tdx.push_warn")
def push_warn(
    stock_code: str,
    price: float,
    reason: str,
    bs_flag: int = 2,  # 0买 1卖 2未知
    confirm_token: str | None = None,
) -> dict:
    """
    发送预警信号到通达信客户端
    
    Args:
        stock_code (str, required): 股票代码，如 "600519"
        price (float, required): 当前价格
        reason (str, required): 预警原因，最多25个汉字
        bs_flag (int, optional): 买卖标志，0=买入/1=卖出/2=未知，默认 2
        
    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用时返回 success=false

    Examples:
        push_warn("600519", 1800.0, "MACD金叉买入信号", bs_flag=0)
    """
    try:
        tq, err = _get_tq_or_error()
        if err is not None:
            return err
        
        # 转换代码格式
        tdx_code = data_source._convert_to_tdx_code(stock_code)
        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        
        result = tq.send_warn(
            stock_list=[tdx_code],
            time_list=[now],
            price_list=[str(price)],
            close_list=[str(price)],
            volum_list=['0'],
            bs_flag_list=[str(bs_flag)],
            warn_type_list=['0'],
            reason_list=[reason[:25]],  # 最多25个汉字
            count=1
        )
        
        if result.get("ErrorId") == "0":
            return {"success": True, "message": "预警信号发送成功"}
        else:
            return {"success": False, "message": result.get("Error", "发送失败")}
    except Exception as e:
        return {"success": False, "message": f"发送异常: {e}"}


@risk_audited("tdx.create_watchlist")
def create_watchlist(
    block_code: str,
    block_name: str,
    stock_codes: list[str],
    confirm_token: str | None = None,
) -> dict:
    """
    在通达信创建自选股板块并添加股票

    Args:
        block_code (str, required): 板块代码，如 "MYBLOCK1"
        block_name (str, required): 板块名称，如 "我的自选"
        stock_codes (list[str], required): 股票代码列表，如 ["600519", "000001"]

    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用时返回 success=false
        - 创建板块或添加股票失败时返回具体错误信息

    Examples:
        create_watchlist("MYBLOCK1", "我的自选", ["600519", "000001"])
    """
    try:
        tq, err = _get_tq_or_error()
        if err is not None:
            return err

        # 步骤1: 创建空板块
        result = tq.create_sector(block_code=block_code, block_name=block_name)
        # 处理返回值：可能是字典或字符串
        if isinstance(result, dict):
            if result.get("ErrorId") != "0":
                return {"success": False, "message": f"创建板块失败: {result.get('Error', '未知错误')}"}
        elif isinstance(result, str):
            # 字符串返回通常表示成功消息
            if "失败" in result or "错误" in result:
                return {"success": False, "message": f"创建板块失败: {result}"}

        # 步骤2: 转换代码格式
        tdx_codes = [data_source._convert_to_tdx_code(code) for code in stock_codes]

        # 步骤3: 添加股票到板块
        result = tq.send_user_block(
            block_code=block_code,
            stocks=tdx_codes,
            show=True  # 切换到该板块
        )

        # 处理返回值
        if isinstance(result, dict):
            if result.get("ErrorId") == "0":
                return {"success": True, "message": f"板块 {block_name} 创建成功，已添加 {len(tdx_codes)} 只股票"}
            else:
                return {"success": False, "message": f"添加股票失败: {result.get('Error', '未知错误')}"}
        elif isinstance(result, str):
            if "失败" in result or "错误" in result:
                return {"success": False, "message": f"添加股票失败: {result}"}
            return {"success": True, "message": f"板块 {block_name} 创建成功，已添加 {len(tdx_codes)} 只股票"}

        return {"success": True, "message": f"板块 {block_name} 创建成功，已添加 {len(tdx_codes)} 只股票"}
    except Exception as e:
        return {"success": False, "message": f"操作异常: {e}"}


@risk_audited("tdx.add_stocks_to_watchlist")
def add_stocks_to_watchlist(
    block_code: str,
    stock_codes: list[str],
    show: bool = False,
    confirm_token: str | None = None,
) -> dict:
    """
    向已有板块添加股票

    Args:
        block_code (str, required): 板块代码
        stock_codes (list[str], required): 股票代码列表
        show (bool, optional): 是否切换到该板块显示，默认 False

    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用或板块不存在时返回 success=false

    Examples:
        add_stocks_to_watchlist("MYBLOCK1", ["000858", "600036"])
    """
    try:
        tq, err = _get_tq_or_error()
        if err is not None:
            return err

        tdx_codes = [data_source._convert_to_tdx_code(code) for code in stock_codes]

        result = tq.send_user_block(
            block_code=block_code,
            stocks=tdx_codes,
            show=show
        )

        if result.get("ErrorId") == "0":
            return {"success": True, "message": f"已添加 {len(tdx_codes)} 只股票到板块 {block_code}"}
        else:
            return {"success": False, "message": f"添加失败: {result.get('Error', '未知错误')}"}
    except Exception as e:
        return {"success": False, "message": f"操作异常: {e}"}


@risk_audited("tdx.delete_watchlist")
def delete_watchlist(block_code: str, confirm_token: str | None = None) -> dict:
    """
    删除自定义板块

    Args:
        block_code (str, required): 板块代码

    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用或板块不存在时返回 success=false

    Examples:
        delete_watchlist("MYBLOCK1")
    """
    try:
        tq, err = _get_tq_or_error()
        if err is not None:
            return err

        result = tq.delete_sector(block_code=block_code)

        # 处理返回值：可能是字典或字符串
        if isinstance(result, dict):
            if result.get("ErrorId") == "0":
                return {"success": True, "message": f"板块 {block_code} 已删除"}
            else:
                return {"success": False, "message": f"删除失败: {result.get('Error', '未知错误')}"}
        elif isinstance(result, str):
            if "失败" in result or "错误" in result:
                return {"success": False, "message": f"删除失败: {result}"}
            return {"success": True, "message": f"板块 {block_code} 已删除"}

        return {"success": True, "message": f"板块 {block_code} 已删除"}
    except Exception as e:
        return {"success": False, "message": f"操作异常: {e}"}


def get_user_sectors() -> dict:
    """
    获取用户自定义板块列表

    Returns:
        dict: {"success": bool, "data": list[dict], "message": str}
        每个板块包含: Code(str 板块代码), Name(str 板块名称)

    Errors:
        - TdxQuant 不可用时返回 success=false, data=[]

    Examples:
        get_user_sectors()
    """
    try:
        tq, err = _get_tq_or_error()
        if err is not None:
            return {"success": False, "data": [], "message": err["message"], "diagnostics": err.get("diagnostics")}

        result = tq.get_user_sector()

        # 处理返回值：根据文档，返回的是列表 [{'Code': 'xxx', 'Name': 'xxx'}, ...]
        if isinstance(result, list):
            return {"success": True, "data": result, "message": f"获取到 {len(result)} 个自定义板块"}
        elif isinstance(result, dict):
            if result.get("ErrorId") == "0":
                sectors = result.get("data", [])
                return {"success": True, "data": sectors, "message": f"获取到 {len(sectors)} 个自定义板块"}
            else:
                return {"success": False, "data": [], "message": result.get("Error", "获取失败")}

        return {"success": False, "data": [], "message": "返回格式异常"}
    except Exception as e:
        return {"success": False, "data": [], "message": f"操作异常: {e}"}


# ============== Phase 2: 回测数据联动 ==============

@risk_audited("tdx.send_backtest_result")
def send_backtest_result(
    stock_code: str,
    time_list: list[str],
    data_list: list[list[str]],
    count: int = 1,
    confirm_token: str | None = None,
) -> dict:
    """
    发送回测数据到通达信客户端进行可视化显示

    Args:
        stock_code (str, required): 股票代码，如 "600519"
        time_list (list[str], required): 时间列表，格式 YYYYMMDDHHMMSS 或 YYYY-MM-DD
        data_list (list[list[str]], required): 数据列表，每行对应一个时间点的多列数据
            信号值自动映射: B/BUY/买入→1, S/SELL/卖出→-1, HOLD/持有→0
        count (int, optional): 数据列数，1-16，默认 1

    Returns:
        dict: {"success": bool, "message": str, "run_id": str|null}

    Errors:
        - time_list 和 data_list 长度不匹配时返回错误
        - count 不在 1-16 范围时返回错误
        - TdxQuant 不可用时返回 success=false

    Examples:
        send_backtest_result("600519", ["20250101000000","20250102000000"], [["1"],["0"]])
    """
    try:
        tq, err = _get_tq_or_error()
        if err is not None:
            return err

        # 转换代码格式
        tdx_code = data_source._convert_to_tdx_code(stock_code)

        # 验证数据
        if len(time_list) != len(data_list):
            return {"success": False, "message": "time_list 和 data_list 长度不匹配"}

        if count < 1 or count > 16:
            return {"success": False, "message": "count 必须在 1-16 之间"}

        # 日期格式标准化：YYYY-MM-DD → YYYYMMDD，YYYY-MM-DD HH:MM:SS → YYYYMMDDHHMMSS
        normalized_time_list = []
        for t in time_list:
            t_str = str(t).replace('-', '').replace(':', '').replace(' ', '').replace('/', '')
            normalized_time_list.append(t_str)

        # data_list 自动清洗：将非数字字符串转换为数字
        # 常见映射: B/BUY/买入→1, S/SELL/卖出→-1, 其他非数字→0
        _SIGNAL_MAP = {
            "B": "1", "BUY": "1", "买入": "1", "买": "1",
            "S": "-1", "SELL": "-1", "卖出": "-1", "卖": "-1",
            "HOLD": "0", "持有": "0", "观望": "0",
        }
        normalized_data_list = []
        for row in data_list:
            normalized_row = []
            for val in row:
                val_str = str(val).strip()
                upper = val_str.upper()
                if upper in _SIGNAL_MAP:
                    normalized_row.append(_SIGNAL_MAP[upper])
                else:
                    # 尝试转为数字，失败则置0
                    try:
                        float(val_str)
                        normalized_row.append(val_str)
                    except (ValueError, TypeError):
                        normalized_row.append("0")
            normalized_data_list.append(normalized_row)

        # 发送回测数据
        result = tq.send_bt_data(
            stock_code=tdx_code,
            time_list=normalized_time_list,
            data_list=normalized_data_list,
            count=count
        )

        if result.get("ErrorId") == "0":
            return {
                "success": True,
                "message": f"回测数据发送成功，共 {len(time_list)} 条记录",
                "run_id": result.get("run_id")
            }
        else:
            return {"success": False, "message": result.get("Error", "发送失败")}
    except Exception as e:
        return {"success": False, "message": f"发送异常: {e}"}


@risk_audited("tdx.send_backtest_trades")
def send_backtest_trades(
    stock_code: str,
    trades: list[dict],
    confirm_token: str | None = None,
) -> dict:
    """
    发送回测交易记录到通达信客户端
    
    注意：TDX 客户端要求至少 4 条时间记录。如果交易记录不足 4 条，
    系统会自动用空记录填充以满足最低要求。

    Args:
        stock_code (str, required): 股票代码，如 "600519"
        trades (list[dict], required): 交易记录列表，每条含:
            - time/date (str): 交易时间，格式 YYYY-MM-DD 或 YYYYMMDDHHMMSS
            - price (float): 成交价格
            - signal (int|str): 信号，1=买入/-1=卖出/0=无
            - shares (int): 股数
            - profit (float): 盈亏

    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - trades 为空时返回错误

    Examples:
        send_backtest_trades("600519", [{"date":"2025-01-01","price":1800,"signal":1,"shares":100,"profit":0}])
    """
    if not trades:
        return {"success": False, "message": "交易记录为空"}

    try:
        # 转换交易记录为 TDX 格式
        time_list = []
        data_list = []

        for trade in trades:
            # 转换时间格式
            time_str = trade.get("time", trade.get("date", ""))
            if "-" in time_str or ":" in time_str:
                # 转换 YYYY-MM-DD HH:MM:SS 为 YYYYMMDDHHMMSS
                time_str = time_str.replace("-", "").replace(":", "").replace(" ", "").replace("/", "")

            # 确保时间格式正确 (14位)
            if len(time_str) < 14:
                time_str = time_str.ljust(14, "0")

            time_list.append(time_str[:14])

            # 构建数据列表: [价格, 信号, 股数, 盈亏]
            price = str(trade.get("price", 0))
            signal = str(trade.get("signal", 0))
            shares = str(trade.get("shares", 0))
            profit = str(trade.get("profit", 0))

            data_list.append([price, signal, shares, profit])

        # TDX 客户端要求 time_list 至少 4 条，不足时用空记录填充
        MIN_TRADES = 4
        while len(time_list) < MIN_TRADES:
            # 用最后一条记录的时间+1秒作为填充时间
            if time_list:
                last_t = time_list[-1]
                try:
                    last_sec = int(last_t[-2:]) + 1
                    pad_t = last_t[:-2] + str(last_sec).zfill(2)
                except (ValueError, IndexError):
                    pad_t = last_t
            else:
                pad_t = "20260101000000"
            time_list.append(pad_t)
            data_list.append(["0", "0", "0", "0"])

        # 发送到 TDX
        return send_backtest_result(
            stock_code=stock_code,
            time_list=time_list,
            data_list=data_list,
            count=4,  # 价格、信号、股数、盈亏
            confirm_token=confirm_token,
        )

    except Exception as e:
        return {"success": False, "message": f"转换异常: {e}"}


def register(mcp):
    """注册 TdxQuant 前端集成工具"""
    mcp.tool()(push_message)
    mcp.tool()(push_warn)
    mcp.tool()(create_watchlist)
    mcp.tool()(add_stocks_to_watchlist)
    mcp.tool()(delete_watchlist)
    mcp.tool()(get_user_sectors)
    mcp.tool()(send_backtest_result)
    mcp.tool()(send_backtest_trades)
