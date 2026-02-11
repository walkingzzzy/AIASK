"""
TdxQuant 文件交互与板块管理补全模块 (Phase 2)

封装通达信客户端的文件推送/下载和板块管理补全功能：
- send_file：发送文件到客户端 TQ 策略数据浏览器（支持 txt/pdf/html）
- download_file：下载十大股东/ETF申赎等数据文件
- rename_sector：重命名自定义板块
- clear_sector：清空板块成份股（保留板块）
"""

from ..data_source import data_source


def tdx_send_file(file_path: str) -> dict:
    """
    [TDX] 发送文件到通达信客户端

    将文件发送到通达信客户端，可在 TQ 策略数据浏览器中打开查看。
    支持 txt、pdf、html 三种文件格式。

    典型用法：AI 生成分析报告（HTML）→ 写入文件 → 调用此工具 → 通达信客户端打开展示。

    Args:
        file_path (str, required): 文件路径
            - 文件放于通达信 PYPlugins/file/ 目录下时，可仅传文件名（如 "report.html"）
            - 其他位置需传绝对路径（如 "C:/reports/analysis.html"）
            - 支持格式：txt, pdf, html

    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用时返回 success=false
        - 文件类型不支持时返回 success=false

    Examples:
        tdx_send_file("report.html")
        tdx_send_file("C:/reports/daily_analysis.pdf")
    """
    if not file_path:
        return {"success": False, "message": "file_path 不能为空"}

    # 检查文件扩展名
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext not in ("txt", "pdf", "html"):
        return {"success": False, "message": f"不支持的文件类型: .{ext}，仅支持 txt/pdf/html"}

    if not data_source.is_tdx_available():
        return {"success": False, "message": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "message": "TdxQuant 初始化失败"}

        result = tq.send_file(file=file_path)

        if isinstance(result, dict):
            if result.get("ErrorId") == "0":
                return {"success": True, "message": f"文件已发送到通达信客户端: {file_path}"}
            else:
                return {"success": False, "message": f"发送失败: {result.get('Error', result.get('Msg', '未知错误'))}"}

        return {"success": True, "message": f"文件已发送到通达信客户端: {file_path}"}
    except Exception as e:
        return {"success": False, "message": f"操作异常: {e}"}


def tdx_download_data(
    stock_code: str,
    date: str,
    data_type: str = "shareholder",
) -> dict:
    """
    [TDX] 下载特定数据文件

    从通达信服务器下载十大股东数据或 ETF 申赎清单，文件保存在通达信
    PYPlugins/data/ 目录下。

    Args:
        stock_code (str, required): 证券代码，如 "688318"（股票）或 "159109"（ETF）
        date (str, required): 日期 YYYYMMDD
            - 十大股东数据：仅年份生效（如 "20250101" 实际下载 2025 年数据）
            - ETF 申赎清单：精确到日期
        data_type (str, optional): 数据类型，默认 "shareholder"
            - "shareholder": 十大股东数据（down_type=1）
            - "etf_redemption": ETF 申赎清单（down_type=2）

    Returns:
        dict: {"success": bool, "message": str, "data": dict|None}

    Errors:
        - TdxQuant 不可用时返回 success=false
        - data_type 无效时返回 success=false

    Examples:
        tdx_download_data("688318", "20250101", "shareholder")
        tdx_download_data("159109", "20250101", "etf_redemption")
    """
    if not stock_code:
        return {"success": False, "message": "stock_code 不能为空"}
    if not date:
        return {"success": False, "message": "date 不能为空"}

    type_map = {"shareholder": 1, "etf_redemption": 2}
    down_type = type_map.get(data_type)
    if down_type is None:
        return {"success": False, "message": f"未知的 data_type: {data_type}，可选 shareholder/etf_redemption"}

    if not data_source.is_tdx_available():
        return {"success": False, "message": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "message": "TdxQuant 初始化失败"}

        # 转换代码格式
        tdx_code = data_source._convert_to_tdx_code(stock_code)

        result = tq.download_file(
            stock_code=tdx_code,
            down_time=date,
            down_type=down_type,
        )

        if isinstance(result, dict):
            if result.get("ErrorId") == "0":
                msg = result.get("Msg", "下载成功")
                return {"success": True, "message": msg, "data": result}
            else:
                return {"success": False, "message": f"下载失败: {result.get('Msg', result.get('Error', '未知错误'))}"}

        return {"success": True, "message": "下载请求已发送", "data": result}
    except Exception as e:
        return {"success": False, "message": f"操作异常: {e}"}


def tdx_rename_sector(block_code: str, new_name: str) -> dict:
    """
    [TDX] 重命名自定义板块

    重命名通达信客户端中的自定义板块。板块代码不变，仅修改显示名称。

    Args:
        block_code (str, required): 自定义板块代码（简称），如 "MYBLOCK1"
        new_name (str, required): 新的板块名称，如 "AI精选股"

    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用或板块不存在时返回 success=false

    Examples:
        tdx_rename_sector("MYBLOCK1", "AI精选股")
    """
    if not block_code:
        return {"success": False, "message": "block_code 不能为空"}
    if not new_name:
        return {"success": False, "message": "new_name 不能为空"}

    if not data_source.is_tdx_available():
        return {"success": False, "message": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "message": "TdxQuant 初始化失败"}

        result = tq.rename_sector(block_code=block_code, block_name=new_name)

        if isinstance(result, dict):
            if result.get("ErrorId") == "0":
                return {"success": True, "message": f"板块 {block_code} 已重命名为「{new_name}」"}
            else:
                return {"success": False, "message": f"重命名失败: {result.get('Error', '未知错误')}"}
        elif isinstance(result, str):
            if "失败" in result or "错误" in result:
                return {"success": False, "message": f"重命名失败: {result}"}
            return {"success": True, "message": f"板块 {block_code} 已重命名为「{new_name}」"}

        return {"success": True, "message": f"板块 {block_code} 已重命名为「{new_name}」"}
    except Exception as e:
        return {"success": False, "message": f"操作异常: {e}"}


def tdx_clear_sector(block_code: str) -> dict:
    """
    [TDX] 清空板块成份股

    清空通达信客户端中指定自定义板块的所有成份股，但保留板块本身。
    适用于需要重新填充板块内容的场景（如每日更新选股结果）。

    Args:
        block_code (str, required): 自定义板块代码（简称），如 "MYBLOCK1"

    Returns:
        dict: {"success": bool, "message": str}

    Errors:
        - TdxQuant 不可用或板块不存在时返回 success=false

    Examples:
        tdx_clear_sector("MYBLOCK1")
    """
    if not block_code:
        return {"success": False, "message": "block_code 不能为空"}

    if not data_source.is_tdx_available():
        return {"success": False, "message": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "message": "TdxQuant 初始化失败"}

        result = tq.clear_sector(block_code=block_code)

        if isinstance(result, dict):
            if result.get("ErrorId") == "0":
                return {"success": True, "message": f"板块 {block_code} 的成份股已清空"}
            else:
                return {"success": False, "message": f"清空失败: {result.get('Error', '未知错误')}"}
        elif isinstance(result, str):
            if "失败" in result or "错误" in result:
                return {"success": False, "message": f"清空失败: {result}"}
            return {"success": True, "message": f"板块 {block_code} 的成份股已清空"}

        return {"success": True, "message": f"板块 {block_code} 的成份股已清空"}
    except Exception as e:
        return {"success": False, "message": f"操作异常: {e}"}


def register(mcp):
    """注册 TDX 文件交互与板块管理补全工具"""
    mcp.tool()(tdx_send_file)
    mcp.tool()(tdx_download_data)
    mcp.tool()(tdx_rename_sector)
    mcp.tool()(tdx_clear_sector)
