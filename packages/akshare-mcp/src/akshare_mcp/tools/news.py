import os
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

import akshare as ak

from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter
from ..utils import (
    fail,
    format_period,
    normalize_code,
    ok,
    parse_date_input,
    safe_float,
    safe_int,
)

_RETRY_SLEEP_SECONDS = float(os.getenv("AKSHARE_RETRY_SLEEP_SECONDS", "0.5"))


@cached(ttl=1800.0)  # 30分钟缓存，公告数据相对稳定
def get_stock_notices(
    start_date: str,
    end_date: str,
    types: Optional[list[str]] = None,
    stock_code: str = "",
) -> dict:
    """
    获取公告事件日历（东方财富公告）

    Args:
        start_date: 开始日期 YYYY-MM-DD 或 YYYYMMDD
        end_date: 结束日期 YYYY-MM-DD 或 YYYYMMDD
        types: 公告类型列表
        stock_code: 股票代码（可选）
    """
    limiter = get_limiter("news", rate=3.0)  # 3次/秒
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
            "all": "全部",
            "全部": "全部",
            "重大事项": "重大事项",
            "财务报告": "财务报告",
            "融资公告": "融资公告",
            "风险提示": "风险提示",
            "资产重组": "资产重组",
            "信息变更": "信息变更",
            "持股变动": "持股变动",
            "major": "重大事项",
            "financial": "财务报告",
            "financing": "融资公告",
            "risk": "风险提示",
            "restructuring": "资产重组",
            "change": "信息变更",
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
        start_ts = time.monotonic()
        partial = False

        current = start
        while current <= end:
            if max_seconds > 0 and (time.monotonic() - start_ts) > max_seconds:
                partial = True
                break
            date_str = current.strftime("%Y%m%d")
            for notice_type in normalized_types:
                try:
                    df = None
                    last_error: Optional[Exception] = None
                    for _ in range(max_retry):
                        try:
                            df = ak.stock_notice_report(symbol=notice_type, date=date_str)
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
        max_items = int(os.getenv("AKSHARE_NOTICE_MAX_ITEMS", "500"))
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


@cached(ttl=3600.0)  # 1小时缓存，研报数据更新不频繁
def get_stock_research(stock_code: str, limit: int = 10) -> dict:
    """
    获取个股研究报告列表
    
    Args:
        stock_code: 股票代码（6位数字）
        limit: 返回数量限制，默认10
    
    Returns:
        研报列表，包含标题、机构、评级、目标价等
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()
    
    try:
        code = normalize_code(stock_code)
        
        # 尝试获取东方财富研报数据
        try:
            df = ak.stock_research_report_em(symbol=code)
        except Exception:
            # 可能是接口限制，尝试获取行业研报
            return fail(f"暂无股票 {code} 的研报数据或接口限制")
        
        if df is None or df.empty:
            return fail(f"未找到股票 {code} 的研报")
        
        # 限制返回数量
        df = df.head(limit)
        
        reports = []
        for _, row in df.iterrows():
            report = {
                "title": str(row.get("报告名称", row.get("标题", ""))).strip(),
                "institution": str(row.get("机构名称", row.get("机构", ""))).strip(),
                "author": str(row.get("研究员", row.get("作者", ""))).strip(),
                "rating": str(row.get("最新评级", row.get("评级", ""))).strip(),
                "targetPrice": safe_float(row.get("目标价", row.get("最高目标价"))),
                "date": format_period(row.get("发布日期", row.get("日期"))),
            }
            # 只保留有效数据
            if report["title"] or report["institution"]:
                reports.append(report)
        
        if not reports:
            return fail(f"股票 {code} 研报数据解析失败")
        
        return ok({
            "stockCode": code,
            "reports": reports,
            "total": len(reports),
        })
    except Exception as e:
        return fail(e)


@cached(ttl=3600.0)  # 1小时缓存
def search_research(keyword: str = "", stock_code: str = "", days: int = 30) -> dict:
    """
    搜索研究报告
    
    Args:
        keyword: 关键词搜索
        stock_code: 按股票代码筛选（可选）
        days: 最近天数，默认30
    
    Returns:
        匹配的研报列表
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()
    
    try:
        # 如果指定了股票代码，直接获取该股票研报
        if stock_code:
            code = normalize_code(stock_code)
            try:
                df = ak.stock_research_report_em(symbol=code)
                if df is not None and not df.empty:
                    # 按关键词过滤
                    if keyword:
                        keyword_lower = keyword.lower()
                        df = df[
                            df.apply(
                                lambda row: keyword_lower in str(row.get("报告名称", "")).lower()
                                or keyword_lower in str(row.get("机构名称", "")).lower(),
                                axis=1
                            )
                        ]
                    
                    reports = []
                    for _, row in df.head(20).iterrows():
                        reports.append({
                            "stockCode": code,
                            "title": str(row.get("报告名称", "")).strip(),
                            "institution": str(row.get("机构名称", "")).strip(),
                            "rating": str(row.get("最新评级", "")).strip(),
                            "date": format_period(row.get("发布日期")),
                        })
                    
                    if reports:
                        return ok({
                            "keyword": keyword,
                            "stockCode": code,
                            "reports": reports,
                            "total": len(reports),
                        })
            except Exception:
                pass
        
        # 如果没有指定股票或获取失败，返回提示
        return ok({
            "keyword": keyword,
            "stockCode": stock_code,
            "reports": [],
            "total": 0,
            "message": "请指定股票代码以获取研报，或使用 get_stock_research 工具",
        })
    except Exception as e:
        return fail(e)


@cached(ttl=86400.0)  # 24小时缓存，排名数据每年更新
def get_analyst_ranking(year: str = "") -> dict:
    """
    获取分析师排名（新财富等榜单）
    
    Args:
        year: 年份，默认当年
    
    Returns:
        分析师排名列表
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()
    
    try:
        if not year:
            year = str(date.today().year)
        
        try:
            df = ak.stock_analyst_rank_em(year=year)
        except Exception:
            # 接口可能需要特定参数或有限制
            return fail(f"暂时无法获取 {year} 年分析师排名数据")
        
        if df is None or df.empty:
            return fail(f"未找到 {year} 年分析师排名数据")
        
        analysts = []
        for _, row in df.head(50).iterrows():
            analysts.append({
                "rank": safe_int(row.get("排名", row.get("序号"))),
                "name": str(row.get("分析师", row.get("姓名", ""))).strip(),
                "institution": str(row.get("所属机构", row.get("机构", ""))).strip(),
                "industry": str(row.get("所属行业", row.get("行业", ""))).strip(),
                "score": safe_float(row.get("综合得分", row.get("得分"))),
                "winRate": safe_float(row.get("胜率")),
            })
        
        return ok({
            "year": year,
            "analysts": analysts,
            "total": len(analysts),
        })
    except Exception as e:
        return fail(e)


@cached(ttl=3600.0)  # 1小时缓存
def get_research_reports(symbol: str = "", limit: int = 10) -> dict:
    """
    获取个股研报
    
    Args:
        symbol: 股票代码，为空则返回最新所有研报
        limit: 返回条数
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()
    
    try:
        # standardizing code not applicable if empty
        code = normalize_code(symbol) if symbol else ""
        df = ak.stock_research_report_em(symbol=code)
        if df is None or df.empty:
            return fail("未找到研报数据")

        limit = int(limit)
        df = df.head(limit)
        
        # Convert to records
        records = df.to_dict(orient="records")
        return ok(records)
    except Exception as e:
        return fail(e)


@cached(ttl=3600.0)  # 1小时缓存
def get_profit_forecast(symbol: str = "") -> dict:
    """
    获取个股盈利预测（包含机构评级和目标价）
    
    Args:
        symbol: 股票代码
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()
    
    try:
        code = normalize_code(symbol)
        df = None
        last_error: Optional[Exception] = None
        
        # 1. Try EastMoney first
        try:
            df = ak.stock_profit_forecast_em(symbol=code)
        except Exception as exc:
            last_error = exc
            df = None

        # 2. Try THS as fallback if EM fails or returns empty
        if df is None or df.empty:
            try:
                df = ak.stock_profit_forecast_ths(symbol=code)
            except Exception as exc:
                last_error = last_error or exc
                df = None

        if df is None or df.empty:
            msg = str(last_error) if last_error else "未找到盈利预测数据 (返回为空)"
            return fail(f"获取盈利预测失败: {msg}")

        # Ensure we can convert to records without error
        try:
            records = df.fillna("").to_dict(orient="records")
            return ok({
                "stockCode": code,
                "items": records,
                "total": len(records)
            })
        except Exception as e:
            return fail(f"数据解析失败: {e}")
            
    except Exception as e:
        return fail(f"系统错误: {e}")


def register(mcp):
    mcp.tool()(get_stock_notices)
    mcp.tool()(get_stock_research)
    mcp.tool()(search_research)
    mcp.tool()(get_analyst_ranking)
    mcp.tool()(get_research_reports)
    mcp.tool()(get_profit_forecast)
