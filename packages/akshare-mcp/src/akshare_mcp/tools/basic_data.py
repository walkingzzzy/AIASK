"""
基础数据工具模块

Phase 3 实现 - MCP 服务开发方案

提供量化策略必需的基础数据：
- 交易日历
- 新股/新债申购信息
- 可转债信息
- 股本数据
"""

from typing import Optional, List
from ..data_source import data_source
from ..utils import ok, fail, resolve_security_code


def register(mcp):
    """注册基础数据工具"""

    @mcp.tool()
    async def get_trading_dates(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        count: int = -1
    ):
        """
        获取交易日历
        
        Args:
            start_date (str, optional): 起始日期，格式 YYYYMMDD（如 "20260101"）
            end_date (str, optional): 结束日期，格式 YYYYMMDD（如 "20261231"）
            count (int, optional): 返回最近的 count 个交易日，-1 表示全部（默认 -1）
        
        Returns:
            dict: {"success": bool, "data": {"dates": list[str], "count": int, "source": str}}
            dates 格式: ["YYYYMMDD", ...]，按时间升序排列
        
        Errors:
            - start_date/end_date 格式错误时返回失败
            - 数据源不可用时返回失败

        Example:
            get_trading_dates(count=10)
            get_trading_dates(start_date="20260101", end_date="20260131")
        """
        try:
            import datetime as _dt

            def _valid_yyyymmdd(v: Optional[str]) -> bool:
                if not v:
                    return True
                if len(v) != 8 or not v.isdigit():
                    return False
                try:
                    _dt.datetime.strptime(v, "%Y%m%d")
                    return True
                except ValueError:
                    return False

            if not _valid_yyyymmdd(start_date):
                return fail("start_date 格式错误，应为 YYYYMMDD")
            if not _valid_yyyymmdd(end_date):
                return fail("end_date 格式错误，应为 YYYYMMDD")
            if start_date and end_date and start_date > end_date:
                return fail("start_date 不能晚于 end_date")
            if count == 0 or count < -1:
                return fail("count 仅支持 -1 或正整数")

            result = data_source.get_trading_dates(
                market="SH",
                start_time=start_date or "",
                end_time=end_date or "",
                count=count
            )

            if result.get("success"):
                return ok({
                    "dates": result["data"],
                    "count": len(result["data"]),
                    "source": result.get("source", "unknown")
                })
            else:
                return fail(result.get("message", "获取交易日历失败"))
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_ipo_info(
        ipo_type: int = 2,
        include_future: bool = True
    ):
        """
        获取新股/新债申购信息
        
        Args:
            ipo_type (int, optional): 申购类型，默认 2
                - 0: 仅新股申购
                - 1: 仅新发债
                - 2: 新股和新发债
            include_future (bool, optional): 是否包含未来申购信息，默认 True
        
        Returns:
            dict: {"success": bool, "data": {"ipo_list": list[dict], "count": int, "source": str}}
            每条记录包含: 代码、名称、申购日期、发行价格等（字段因数据源而异）

        Errors:
            - 当前无申购信息时返回空列表（success=true, count=0）

        Example:
            get_ipo_info()
            get_ipo_info(ipo_type=0, include_future=False)
        """
        try:
            ipo_date = 1 if include_future else 0
            result = data_source.get_ipo_info(ipo_type=ipo_type, ipo_date=ipo_date)
            
            if result.get("success") and result.get("data"):
                return ok({
                    "ipo_list": result["data"],
                    "count": len(result["data"]),
                    "source": result.get("source", "unknown")
                })
            
            # 返回空但成功的结果（而非 fail），避免链路中断
            return ok({
                "ipo_list": [],
                "count": 0,
                "source": "none",
                "message": "当前暂无新股/新债申购信息"
            })
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_cb_info(
        code: Optional[str] = None,
        stock_code: Optional[str] = None,
        symbol: Optional[str] = None,
    ):
        """
        获取可转债基础信息
        
        Args:
            code (str, required): 可转债代码，如 "123039" 或 "123039.SZ"
        
        Returns:
            dict: {"success": bool, "data": {"cb_info": dict, "source": str}}
            cb_info 包含:
            - KZZCode(str): 可转债代码
            - HSCode(str): 正股代码
            - ZGPrice(float): 转股价格
            - ZGDate(str): 转股日期
            - EndDate(str): 到期日期
            - RestScope(float): 剩余规模

        Errors:
            - 代码为空时返回错误
            - 代码不存在时返回失败

        Example:
            get_cb_info("123039")
        """
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol)
            if not code:
                return fail("可转债代码不能为空（支持 code / stock_code / symbol）")
            
            result = data_source.get_cb_info(stock_code=code)
            
            if result.get("success"):
                return ok({
                    "cb_info": result["data"],
                    "source": result.get("source", "unknown")
                })
            else:
                return fail(result.get("message", "获取可转债信息失败"))
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_stock_capital(
        code: Optional[str] = None,
        dates: Optional[List[str]] = None,
        stock_code: Optional[str] = None,
        symbol: Optional[str] = None,
        ticker: Optional[str] = None,
    ):
        """
        获取股票股本数据
        
        Args:
            code (str, required): 股票代码，如 "600519" 或 "600519.SH"
            dates (list[str], optional): 日期列表，格式 ["YYYYMMDD", ...]，须从小到大排序；
                                         不提供则返回最新数据
        
        Returns:
            dict: {"success": bool, "data": {"capital_data": list[dict], "count": int, "source": str}}
            每条记录包含:
            - Date(str): 日期
            - ltgb(int): 流通股本（股）
            - zgb(int): 总股本（股）

        Errors:
            - 代码为空时返回错误
            - 数据源不可用时返回失败

        Example:
            get_stock_capital("600519")
            get_stock_capital("600519", dates=["20260101", "20260601"])
        """
        try:
            code = resolve_security_code(code, stock_code=stock_code, symbol=symbol, ticker=ticker)
            if not code:
                return fail("股票代码不能为空（支持 code / stock_code / symbol / ticker）")
            
            date_list = dates or []
            count = len(date_list) if date_list else 1
            
            result = data_source.get_gb_info(
                stock_code=code,
                date_list=date_list,
                count=count
            )
            
            if result.get("success"):
                capital_data = result.get("data") or []
                return ok({
                    "capital_data": capital_data,
                    "count": len(capital_data),
                    "source": result.get("source", "unknown"),
                    "message": result.get("message"),
                    "backend_requested": result.get("backend_requested"),
                    "backend_used": result.get("backend_used"),
                    "fallback_used": result.get("fallback_used", False),
                    "fallback_reason": result.get("fallback_reason"),
                    "quality_flags": result.get("quality_flags", []),
                    "asof_time": result.get("asof_time"),
                    "freshness_sec": result.get("freshness_sec"),
                    "latency_ms": result.get("latency_ms"),
                })
            else:
                return fail(result.get("message") or result.get("error") or "获取股本数据失败")
        except Exception as e:
            return fail(str(e))
