"""
数据同步 MCP 工具模块

Phase 4 实现 - 数据源整合优化

提供以下 MCP 工具：
1. sync_kline_data - 同步K线数据（带缓存）
2. sync_trading_calendar - 同步交易日历
3. batch_sync_klines - 批量同步股票K线
4. get_cache_stats - 获取缓存统计
5. clear_cache - 清空缓存
"""

import asyncio
from typing import Optional, List

from ..services.data_sync import data_sync_service, CACHE_TTL
from ..cache import cache


def register(mcp):
    """注册数据同步相关的 MCP 工具"""

    @mcp.tool()
    async def sync_kline_data(
        stock_code: str,
        period: str = "daily",
        start_date: str = "",
        end_date: str = "",
        limit: int = 100,
        use_cache: bool = True
    ) -> dict:
        """
        同步K线数据（带多层缓存）

        数据流向: SimpleCache → TimescaleDB → API（TDX/Tushare/AkShare）

        Args:
            stock_code (str, required): 股票代码，如 "600519"、"000001"
            period (str, optional): K线周期，可选 "daily"/"weekly"/"monthly"，默认 "daily"
            start_date (str, optional): 开始日期，格式 YYYYMMDD
            end_date (str, optional): 结束日期，格式 YYYYMMDD
            limit (int, optional): 数据条数限制，默认 100
            use_cache (bool, optional): 是否使用缓存，默认 True

        Returns:
            dict: {"success": bool, "data": list[dict], "source": str, "count": int, "cached": bool}
            每条K线包含: date, open, high, low, close, volume, amount

        Errors:
            - 股票代码无效或所有数据源均不可用时返回 success=false

        Examples:
            sync_kline_data("600519")
            sync_kline_data("000001", period="weekly", limit=50)
        """
        return await data_sync_service.get_kline_with_cache(
            stock_code=stock_code,
            period=period,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            use_cache=use_cache
        )

    @mcp.tool()
    async def sync_trading_calendar(year: int = None) -> dict:
        """
        同步交易日历

        Args:
            year (int, optional): 年份，默认当前年份

        Returns:
            dict: {"success": bool, "data": {"dates": list[str], "count": int, "year": int}}
            dates 格式: ["YYYYMMDD", ...]

        Examples:
            sync_trading_calendar()
            sync_trading_calendar(year=2025)
        """
        return await data_sync_service.sync_trading_dates(year)

    @mcp.tool()
    async def batch_sync_klines(
        codes: List[str],
        start_date: str = "",
        end_date: str = "",
        period: str = "daily"
    ) -> dict:
        """
        批量同步股票K线数据

        Args:
            codes (list[str], required): 股票代码列表，如 ["600519", "000001"]
            start_date (str, optional): 开始日期，格式 YYYYMMDD
            end_date (str, optional): 结束日期，格式 YYYYMMDD
            period (str, optional): K线周期，默认 "daily"

        Returns:
            dict: {"success": bool, "data": {"synced": int, "failed": int, "total": int, "errors": list[str]}}

        Examples:
            batch_sync_klines(["600519", "000001"])
            batch_sync_klines(["600519", "000858"], start_date="20250101")
        """
        return await data_sync_service.sync_stock_klines(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            period=period
        )

    @mcp.tool()
    def get_sync_status() -> dict:
        """
        获取数据同步队列与失败状态（含 dead-letter 概览）

        Returns:
            dict: {
                "success": bool,
                "metrics": dict,
                "dead_letters": {"count": int, "path": str}
            }

        Examples:
            get_sync_status()
        """
        metrics = data_sync_service.get_sync_metrics()
        dlq = data_sync_service.get_dead_letters(limit=1)
        return {
            "success": True,
            "metrics": metrics,
            "dead_letters": {
                "count": dlq.get("count", 0),
                "path": dlq.get("path", ""),
            },
        }

    @mcp.tool()
    def get_dead_letters(limit: int = 20) -> dict:
        """
        获取最近的 dead-letter 失败落盘记录

        Args:
            limit (int, optional): 返回条数上限，默认 20

        Returns:
            dict: {"success": bool, "path": str, "count": int, "records": list}

        Examples:
            get_dead_letters()
            get_dead_letters(limit=50)
        """
        return data_sync_service.get_dead_letters(limit=limit)

    @mcp.tool()
    def clear_dead_letters() -> dict:
        """
        清空 dead-letter 失败记录

        Returns:
            dict: {"success": bool, "removed": int, "path": str}

        Examples:
            clear_dead_letters()
        """
        return data_sync_service.clear_dead_letters()


    @mcp.tool()
    def get_cache_stats() -> dict:
        """
        获取缓存统计信息

        Returns:
            dict: {"file_count": int, "total_size_mb": float, "hit_rate": float, "cache_dir": str, "ttl_config": dict}

        Examples:
            get_cache_stats()
        """
        stats = cache.get_stats()
        stats["ttl_config"] = CACHE_TTL
        return stats

    @mcp.tool()
    def clear_cache() -> dict:
        """
        清空所有缓存

        Returns:
            dict: {"success": bool, "cleared_count": int, "message": str}

        Examples:
            clear_cache()
        """
        count = cache.clear()
        return {
            "success": True,
            "cleared_count": count,
            "message": f"已清除 {count} 个缓存文件"
        }

