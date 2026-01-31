import os
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

import akshare as ak

from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter
from ..data_source import data_source
from ..utils import (
    fail,
    format_period,
    normalize_code,
    ok,
    parse_date_input,
    safe_float,
    safe_int,
    pick_value,
)

_RETRY_SLEEP_SECONDS = float(os.getenv("AKSHARE_RETRY_SLEEP_SECONDS", "0.5"))

def _to_ymd(value: Any) -> str:
    text = format_period(value)
    return text.replace("-", "") if text else ""


def _map_tushare_ann_rows(rows: list[dict]) -> list[dict]:
    results: list[dict] = []
    for row in rows:
        title = row.get("ann_title") or row.get("title") or row.get("公告标题")
        time_val = row.get("ann_date") or row.get("f_ann_date") or row.get("date")
        url = row.get("ann_url") or row.get("url")
        if not title and not url:
            continue
        results.append(
            {
                "title": str(title or ""),
                "time": format_period(time_val),
                "source": "tushare",
                "url": str(url or ""),
                "date": format_period(time_val),
            }
        )
    return results


def _try_tushare_anns(start_date: str, end_date: str, stock_code: str, limit: int) -> list[dict]:
    pro = data_source.get_tushare_pro()
    if not pro:
        return []
    try:
        ts_code = ""
        if stock_code:
            code = normalize_code(stock_code)
            ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
        df = pro.anns(
            ts_code=ts_code,
            start_date=_to_ymd(start_date),
            end_date=_to_ymd(end_date),
        )
        if df is None or df.empty:
            return []
        rows = df.head(limit).fillna("").to_dict(orient="records")
        return _map_tushare_ann_rows(rows)
    except Exception:
        return []


def _try_tushare_news(start_date: str, end_date: str, limit: int) -> list[dict]:
    pro = data_source.get_tushare_pro()
    if not pro:
        return []
    try:
        df = pro.news(
            start_date=_to_ymd(start_date),
            end_date=_to_ymd(end_date),
            src="sina",
        )
        if df is None or df.empty:
            return []
        rows = df.head(limit).fillna("").to_dict(orient="records")
        results: list[dict] = []
        for row in rows:
            title = row.get("title") or row.get("新闻标题")
            time_val = row.get("datetime") or row.get("date") or row.get("time")
            url = row.get("url")
            if not title and not url:
                continue
            results.append(
                {
                    "title": str(title or ""),
                    "time": format_period(time_val),
                    "source": str(row.get("src") or "tushare"),
                    "url": str(url or ""),
                    "date": format_period(time_val),
                }
            )
        return results
    except Exception:
        return []


def _map_news_rows(rows: list[dict]) -> list[dict]:
    results: list[dict] = []
    for row in rows:
        title = pick_value(row, ["title", "标题", "新闻标题", "公告标题"])
        time_val = pick_value(row, ["time", "发布时间", "公告日期", "日期", "date", "发布时间"])
        source = pick_value(row, ["source", "来源", "来源网站", "媒体名称"])
        url = pick_value(row, ["url", "链接", "网址", "新闻链接"])
        if not title and not url:
            continue
        results.append(
            {
                "title": str(title or ""),
                "time": format_period(time_val),
                "source": str(source or ""),
                "url": str(url or ""),
                "date": format_period(time_val),
            }
        )
    return results


def _map_research_rows(rows: list[dict]) -> list[dict]:
    results: list[dict] = []
    for row in rows:
        title = pick_value(row, ["title", "报告名称", "标题", "研报标题"])
        institution = pick_value(row, ["institution", "机构名称", "机构", "研究机构", "发布机构"])
        author = pick_value(row, ["author", "作者", "研究员", "分析师"])
        time_val = pick_value(row, ["date", "发布日期", "日期", "发布时间"])
        url = pick_value(row, ["url", "链接", "网址", "报告链接"])
        if not title and not institution:
            continue
        results.append(
            {
                "title": str(title or ""),
                "time": format_period(time_val),
                "source": str(institution or author or ""),
                "url": str(url or ""),
                "date": format_period(time_val),
            }
        )
    return results


def _try_akshare_news_functions(code: str, limit: int) -> list[dict]:
    candidates = [
        ("stock_news_em", {"symbol": code}),
        ("stock_news_em", {"code": code}),
        ("stock_news", {"symbol": code}),
    ]
    for func_name, kwargs in candidates:
        func = getattr(ak, func_name, None)
        if not func:
            continue
        try:
            df = func(**kwargs)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = df.head(limit).fillna("").to_dict(orient="records")
        mapped = _map_news_rows(rows)
        if mapped:
            return mapped
    return []


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
            name = str(
                pick_value(row, ["分析师", "姓名", "研究员", "作者", "分析师姓名"]) or ""
            ).strip()
            institution = str(
                pick_value(row, ["所属机构", "机构", "机构名称", "所在机构"]) or ""
            ).strip()
            industry = str(
                pick_value(row, ["所属行业", "行业", "研究领域", "行业名称"]) or ""
            ).strip()
            rank = safe_int(pick_value(row, ["排名", "序号", "名次", "排行"]))
            score = safe_float(pick_value(row, ["综合得分", "得分", "评分", "总评分"]))
            win_rate = safe_float(pick_value(row, ["胜率", "准确率", "命中率"]))

            if not name and not institution:
                continue

            analysts.append(
                {
                    "rank": rank,
                    "name": name,
                    "institution": institution,
                    "industry": industry,
                    "score": score,
                    "winRate": win_rate,
                }
            )

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


@cached(ttl=1800.0)  # 30分钟缓存
def get_stock_news(stock_code: str, limit: int = 20) -> dict:
    """
    获取个股新闻列表（优先使用 AkShare 内置接口，失败则回退公告/研报）
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    try:
        code = normalize_code(stock_code)
        limit = int(limit) if int(limit or 0) > 0 else 20

        # 0. Try Tushare announcements as news
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        items = _try_tushare_anns(start_date.isoformat(), end_date.isoformat(), code, limit)
        if items:
            return ok(items[:limit])

        items = _try_akshare_news_functions(code, limit)
        if items:
            return ok(items[:limit])

        # 回退1：使用公告数据充当新闻
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        fallback = get_stock_notices(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            types=["全部"],
            stock_code=code,
        )
        if fallback.get("success") and fallback.get("data"):
            events = fallback["data"].get("events", [])
            mapped = _map_news_rows(events)
            if mapped:
                return ok(mapped[:limit])

        # 回退2：使用研报数据充当新闻
        research = get_stock_research(code, limit=max(limit, 10))
        if research.get("success") and research.get("data"):
            reports = research["data"].get("reports", [])
            mapped = _map_research_rows(reports)
            if mapped:
                return ok(mapped[:limit])

        # 回退3：使用研报通用接口（可能返回更广泛研报）
        reports = get_research_reports(code, limit=max(limit, 10))
        if reports.get("success") and reports.get("data"):
            mapped = _map_research_rows(reports["data"] if isinstance(reports["data"], list) else [])
            if mapped:
                return ok(mapped[:limit])

        return fail(f"未获取到 {code} 的新闻数据")
    except Exception as e:
        return fail(e)


@cached(ttl=1800.0)
def get_market_news(limit: int = 20) -> dict:
    """
    获取市场新闻（如不可用则返回失败）
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    try:
        limit = int(limit) if int(limit or 0) > 0 else 20
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        items = _try_tushare_news(start_date.isoformat(), end_date.isoformat(), limit)
        if items:
            return ok(items[:limit])

        items = _try_akshare_news_functions("", limit)
        if items:
            return ok(items[:limit])

        fallback = get_stock_notices(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            types=["全部"],
            stock_code="",
        )
        if fallback.get("success") and fallback.get("data"):
            events = fallback["data"].get("events", [])
            mapped = _map_news_rows(events)
            if mapped:
                return ok(mapped[:limit])

        return fail("市场新闻暂不可用")
    except Exception as e:
        return fail(e)


def register(mcp):
    mcp.tool()(get_stock_notices)
    mcp.tool()(get_stock_research)
    mcp.tool()(search_research)
    mcp.tool()(get_analyst_ranking)
    mcp.tool()(get_research_reports)
    mcp.tool()(get_profit_forecast)
    mcp.tool()(get_stock_news)
    mcp.tool()(get_market_news)
