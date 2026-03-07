"""新闻/研报工具 — 公告事件"""

import os
import time
from datetime import timedelta
from typing import Any, Optional

try:
    import akshare as ak
except ImportError:
    ak = None

from ...core.cache_manager import cached
from ...core.rate_limiter import get_limiter
from ...utils import fail, format_period, normalize_code, ok, parse_date_input
from .helpers import _RETRY_SLEEP_SECONDS, _try_tushare_anns


@cached(ttl=1800.0)
def get_stock_notices(
    start_date: str,
    end_date: str,
    types: Optional[list[str]] = None,
    stock_code: str = "",
) -> dict:
    """
    获取公告事件日历（东方财富公告）

    数据源优先级: Tushare Pro(announcements) → AkShare(stock_notice_report)
    时效性: 日频

    Args:
        start_date (str, required): 开始日期，格式 YYYY-MM-DD 或 YYYYMMDD（必填）
        end_date (str, required): 结束日期，格式 YYYY-MM-DD 或 YYYYMMDD（必填，跨度上限由环境变量 AKSHARE_NOTICE_MAX_DAYS 控制，默认31天）
        types (list[str]|None, optional): 公告类型列表
        stock_code (str, optional): 股票代码过滤

    Returns:
        dict: {"success": bool, "data": {...}}
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    try:
        start = parse_date_input(start_date)
        end = parse_date_input(end_date)
        if not start or not end:
            return fail("日期格式错误，需 YYYY-MM-DD 或 YYYYMMDD")
        if end < start:
            start, end = end, start

        max_days = int(os.getenv("AKSHARE_NOTICE_MAX_DAYS", "31"))
        if (end - start).days + 1 > max_days:
            end = start + timedelta(days=max_days - 1)

        raw_types = types or []
        type_map = {
            "all": "全部", "全部": "全部",
            "重大事项": "重大事项", "财务报告": "财务报告",
            "融资公告": "融资公告", "风险提示": "风险提示",
            "资产重组": "资产重组", "信息变更": "信息变更",
            "持股变动": "持股变动",
            "major": "重大事项", "financial": "财务报告",
            "financing": "融资公告", "risk": "风险提示",
            "restructuring": "资产重组", "change": "信息变更",
            "holding": "持股变动",
        }
        normalized_types = []
        for t in raw_types:
            key = str(t or "").strip()
            if not key:
                continue
            mapped = type_map.get(key.lower()) or type_map.get(key) or None
            if mapped:
                normalized_types.append(mapped)
        if not normalized_types:
            normalized_types = ["全部"]

        code_filter = normalize_code(stock_code) if stock_code else ""
        events: list[dict[str, Any]] = []
        max_seconds = int(os.getenv("AKSHARE_NOTICE_MAX_SECONDS", "20"))
        max_retry = int(os.getenv("AKSHARE_NOTICE_RETRY", "2"))
        max_items = int(os.getenv("AKSHARE_NOTICE_MAX_ITEMS", "500"))
        start_ts = time.monotonic()
        partial = False

        # 0. Try Tushare Pro announcements first
        try:
            tushare_items = _try_tushare_anns(start.isoformat(), end.isoformat(), code_filter, max_items)
            if tushare_items:
                return ok(
                    {
                        "startDate": start.isoformat(),
                        "endDate": end.isoformat(),
                        "types": normalized_types,
                        "events": tushare_items,
                        "truncated": len(tushare_items) > max_items,
                        "partial": False,
                    }
                )
        except Exception:
            pass

        current = start
        while current <= end:
            if max_seconds > 0 and (time.monotonic() - start_ts) > max_seconds:
                partial = True
                break
            if ak is None:
                break
            date_str = current.strftime("%Y%m%d")
            for notice_type in normalized_types:
                try:
                    df = None
                    last_error: Optional[Exception] = None
                    for _ in range(max_retry):
                        try:
                            df = ak.stock_notice_report(symbol=notice_type, date=date_str) if ak is not None else None
                            if df is not None and not df.empty:
                                break
                        except Exception as exc:
                            last_error = exc
                            if _RETRY_SLEEP_SECONDS > 0:
                                time.sleep(_RETRY_SLEEP_SECONDS)
                except Exception:
                    continue
                if df is None or df.empty or "代码" not in df.columns:
                    continue
                for _, row in df.iterrows():
                    code = normalize_code(row.get("代码", ""))
                    if code_filter and code != code_filter:
                        continue
                    notice_date = row.get("公告日期")
                    events.append(
                        {
                            "code": code,
                            "name": str(row.get("名称", "")),
                            "title": str(row.get("公告标题", "")),
                            "type": str(row.get("公告类型", notice_type)),
                            "date": format_period(notice_date),
                            "url": str(row.get("网址", "")),
                        }
                    )
            current += timedelta(days=1)

        events = sorted(events, key=lambda x: str(x.get("date") or ""), reverse=True)
        truncated = len(events) > max_items
        if truncated:
            events = events[:max_items]

        return ok(
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "types": normalized_types,
                "events": events,
                "truncated": truncated,
                "partial": partial,
            }
        )
    except Exception as e:
        return fail(e)
