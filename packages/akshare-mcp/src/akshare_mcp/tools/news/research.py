"""新闻/研报工具 — 研报、分析师排名、盈利预测"""

from datetime import date, timedelta

try:
    import akshare as ak
except ImportError:
    ak = None

from ...core.cache_manager import cached
from ...core.rate_limiter import get_limiter
from ...data_source import data_source
from ...utils import fail, format_period, normalize_code, ok, pick_value, safe_float
from .helpers import _dedup_reports, _fetch_eastmoney_research


@cached(ttl=3600.0)
def get_stock_research(stock_code: str, limit: int = 10) -> dict:
    """
    获取个股研究报告列表

    数据源优先级: Tushare report_rc → 东财 datacenter → AkShare (降级)
    时效性: 研报数据缓存1小时
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    try:
        code = normalize_code(stock_code)

        # 1. 主路径: Tushare report_rc
        try:
            ts_pro = data_source.get_tushare_pro()
            if ts_pro:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                df_ts = ts_pro.report_rc(ts_code=ts_code, fields='report_title,org_name,author_name,report_date,rating')
                if df_ts is not None and not df_ts.empty:
                    reports = []
                    for _, row in df_ts.iterrows():
                        reports.append({
                            "title": str(row.get('report_title', '') or '').strip(),
                            "institution": str(row.get('org_name', '') or '').strip(),
                            "author": str(row.get('author_name', '') or '').strip(),
                            "rating": str(row.get('rating', '') or '').strip(),
                            "targetPrice": None,
                            "date": format_period(row.get('report_date')),
                        })
                    reports = _dedup_reports(reports)[:limit]
                    if reports:
                        return ok({"stockCode": code, "reports": reports, "total": len(reports)})
        except Exception:
            pass

        # 2. 降级: 东财 datacenter 研报
        try:
            items = _fetch_eastmoney_research(code, limit * 2)
            if items:
                items = _dedup_reports(items)[:limit]
                return ok({"stockCode": code, "reports": items, "total": len(items)})
        except Exception:
            pass

        # 3. 降级: AkShare
        if ak is not None:
            try:
                df = ak.stock_research_report_em(symbol=code)
                if df is not None and not df.empty:
                    reports = []
                    for _, row in df.iterrows():
                        report = {
                            "title": str(pick_value(row, ["报告名称", "标题", "研报标题", "title"]) or "").strip(),
                            "institution": str(pick_value(row, ["机构名称", "机构", "研究机构", "发布机构", "institution"]) or "").strip(),
                            "author": str(pick_value(row, ["研究员", "作者", "分析师", "author"]) or "").strip(),
                            "rating": str(pick_value(row, ["最新评级", "评级", "投资评级", "rating"]) or "").strip(),
                            "targetPrice": safe_float(pick_value(row, ["目标价", "最高目标价", "目标价格", "targetPrice"])),
                            "date": format_period(pick_value(row, ["发布日期", "日期", "发布时间", "date"])),
                        }
                        if report["title"] or report["institution"]:
                            reports.append(report)
                    reports = _dedup_reports(reports)[:limit]
                    if reports:
                        return ok({"stockCode": code, "reports": reports, "total": len(reports)})
            except Exception:
                pass

        return fail(f"暂无股票 {code} 的研报数据")
    except Exception as e:
        return fail(e)


@cached(ttl=3600.0)
def search_research(keyword: str = "", stock_code: str = "", days: int = 30) -> dict:
    """
    搜索研究报告

    数据源优先级: Tushare report_rc → 东财 datacenter → AkShare (降级)
    时效性: 研报数据缓存1小时
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    def _keyword_match(text: str, kw: str) -> bool:
        text_lower = str(text or "").lower()
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            return True
        if len(kw_lower) >= 4:
            tokens = set()
            for i in range(len(kw_lower) - 1):
                tokens.add(kw_lower[i:i+2])
            hit = sum(1 for t in tokens if t in text_lower)
            if hit >= max(1, len(tokens) // 2):
                return True
        return False

    try:
        code = normalize_code(stock_code) if stock_code else ""

        # 1. 主路径: Tushare report_rc
        try:
            ts_pro = data_source.get_tushare_pro()
            if ts_pro:
                end_dt = date.today().strftime("%Y%m%d")
                start_dt = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
                kwargs = {"start_date": start_dt, "end_date": end_dt, "fields": "ts_code,report_title,org_name,author_name,report_date,rating"}
                if code:
                    ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                    kwargs["ts_code"] = ts_code
                df_ts = ts_pro.report_rc(**kwargs)
                if df_ts is not None and not df_ts.empty:
                    if keyword:
                        df_ts = df_ts[
                            df_ts.apply(
                                lambda row: _keyword_match(row.get("report_title"), keyword)
                                or _keyword_match(row.get("org_name"), keyword),
                                axis=1
                            )
                        ]
                    reports = []
                    for _, row in df_ts.head(20).iterrows():
                        ts_c = str(row.get("ts_code", "") or "").split(".")[0]
                        reports.append({
                            "stockCode": ts_c or code,
                            "title": str(row.get("report_title", "") or "").strip(),
                            "institution": str(row.get("org_name", "") or "").strip(),
                            "rating": str(row.get("rating", "") or "").strip(),
                            "date": format_period(row.get("report_date")),
                        })
                    reports = _dedup_reports(reports)
                    if reports:
                        return ok({"keyword": keyword, "stockCode": code, "reports": reports, "total": len(reports)})
        except Exception:
            pass

        # 2. 降级: 东财 datacenter
        if code:
            try:
                items = _fetch_eastmoney_research(code, 20)
                if items and keyword:
                    items = [i for i in items if _keyword_match(i.get("title", ""), keyword) or _keyword_match(i.get("institution", ""), keyword)]
                if items:
                    reports = _dedup_reports([{"stockCode": code, **i} for i in items])
                    return ok({"keyword": keyword, "stockCode": code, "reports": reports, "total": len(reports)})
            except Exception:
                pass

        # 3. 降级: AkShare
        if code and ak is not None:
            try:
                df = ak.stock_research_report_em(symbol=code)
                if df is not None and not df.empty:
                    if keyword:
                        df = df[
                            df.apply(
                                lambda row: _keyword_match(pick_value(row, ["报告名称", "标题", "研报标题", "title"]), keyword)
                                or _keyword_match(pick_value(row, ["机构名称", "机构", "研究机构", "institution"]), keyword),
                                axis=1
                            )
                        ]
                    reports = []
                    for _, row in df.head(20).iterrows():
                        reports.append({
                            "stockCode": code,
                            "title": str(pick_value(row, ["报告名称", "标题", "研报标题", "title"]) or "").strip(),
                            "institution": str(pick_value(row, ["机构名称", "机构", "研究机构", "发布机构", "institution"]) or "").strip(),
                            "rating": str(pick_value(row, ["最新评级", "评级", "投资评级", "rating"]) or "").strip(),
                            "date": format_period(pick_value(row, ["发布日期", "日期", "发布时间", "date"])),
                        })
                    reports = _dedup_reports(reports)
                    if reports:
                        return ok({"keyword": keyword, "stockCode": code, "reports": reports, "total": len(reports)})
            except Exception:
                pass

        return ok({"keyword": keyword, "stockCode": code, "reports": [], "total": 0, "message": "未找到匹配的研报"})
    except Exception as e:
        return fail(e)


@cached(ttl=86400.0)
def get_analyst_ranking(year: str = "") -> dict:
    """
    获取分析师排名（基于研报数量统计）

    数据源: Tushare report_rc
    时效性: 缓存24小时
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    try:
        if not year:
            year = str(date.today().year)

        try:
            ts_pro = data_source.get_tushare_pro()
            if ts_pro:
                target_year = int(year)
                df = None
                actual_year = None
                for try_year in range(target_year, target_year - 5, -1):
                    try:
                        start_date = f"{try_year}0101"
                        end_date = f"{try_year}1231"
                        df = ts_pro.report_rc(
                            start_date=start_date,
                            end_date=end_date,
                            fields='author_name,org_name,report_date'
                        )
                        if df is not None and not df.empty:
                            actual_year = str(try_year)
                            break
                    except Exception:
                        continue

                if df is not None and not df.empty:
                    analyst_counts = df.groupby(['author_name', 'org_name']).size().reset_index(name='report_count')
                    analyst_counts = analyst_counts.sort_values('report_count', ascending=False).head(50)

                    analysts = []
                    for rank, (_, row) in enumerate(analyst_counts.iterrows(), 1):
                        name = str(row.get('author_name', '') or '').strip()
                        institution = str(row.get('org_name', '') or '').strip()
                        if not name:
                            continue
                        analysts.append({
                            'rank': rank,
                            'name': name,
                            'institution': institution,
                            'industry': '',
                            'score': None,
                            'winRate': None,
                            'report_count': int(row.get('report_count', 0)),
                        })

                    if analysts:
                        note = '基于研报数量统计的活跃分析师排名'
                        if actual_year and actual_year != year:
                            note += f'（{year}年数据不足，使用{actual_year}年数据）'
                        return ok({
                            'year': actual_year or year,
                            'requested_year': year,
                            'analysts': analysts,
                            'total': len(analysts),
                            'source': 'tushare_report_rc',
                            'note': note,
                        })
        except Exception:
            pass

        return ok({'year': year, 'analysts': [], 'total': 0, 'message': f"暂无 {year} 年分析师排名数据（数据源限制）"})
    except Exception as e:
        return fail(e)


@cached(ttl=3600.0)
def get_research_reports(symbol: str = "", limit: int = 10) -> dict:
    """
    获取个股研报

    数据源优先级: Tushare report_rc → 东财 datacenter → AkShare (降级)
    时效性: 缓存1小时
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    try:
        code = normalize_code(symbol) if symbol else ""
        limit = int(limit)

        # 1. Tushare report_rc
        try:
            ts_pro = data_source.get_tushare_pro()
            if ts_pro:
                kwargs = {"fields": "ts_code,report_title,org_name,author_name,report_date,rating"}
                if code:
                    ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                    kwargs["ts_code"] = ts_code
                df_ts = ts_pro.report_rc(**kwargs)
                if df_ts is not None and not df_ts.empty:
                    records = []
                    for _, row in df_ts.head(limit).iterrows():
                        records.append({
                            "title": str(row.get("report_title", "") or "").strip(),
                            "institution": str(row.get("org_name", "") or "").strip(),
                            "author": str(row.get("author_name", "") or "").strip(),
                            "rating": str(row.get("rating", "") or "").strip(),
                            "date": format_period(row.get("report_date")),
                        })
                    records = _dedup_reports(records)[:limit]
                    if records:
                        return ok(records)
        except Exception:
            pass

        # 2. 东财 datacenter
        if code:
            items = _fetch_eastmoney_research(code, limit * 2)
            if items:
                return ok(_dedup_reports(items)[:limit])

        # 3. AkShare
        if ak is not None:
            try:
                df = ak.stock_research_report_em(symbol=code)
                if df is not None and not df.empty:
                    df = df.head(limit * 2)
                    records = df.to_dict(orient="records")
                    return ok(_dedup_reports(records)[:limit])
            except Exception:
                pass

        return fail("未找到研报数据")
    except Exception as e:
        return fail(e)


@cached(ttl=3600.0)
def get_profit_forecast(symbol: str = "") -> dict:
    """
    获取个股盈利预测（包含机构评级和目标价）

    数据源优先级: 东财 datacenter → Tushare forecast → AkShare (降级)
    时效性: 缓存1小时
    """
    limiter = get_limiter("news", rate=3.0)
    limiter.acquire()

    try:
        code = normalize_code(symbol)

        # 1. 东财 datacenter 盈利预测
        try:
            import requests as _req
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "REPORT_DATE",
                "sortTypes": -1,
                "pageSize": 30,
                "pageNumber": 1,
                "reportName": "RPT_PUBLIC_OP_NEWPREDICT",
                "columns": "REPORT_DATE,ORG_NAME,RESEARCHER,RATING_NAME,PREDICT_NEXT_TWO_EPS,PREDICT_NEXT_TWO_INCOME,PREDICT_NEXT_TWO_NETPROFIT",
                "filter": f'(SECURITY_CODE="{code}")',
            }
            headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
            resp = _req.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                payload = resp.json()
                items = payload.get("result", {}).get("data", []) or []
                if items:
                    records = []
                    for item in items:
                        records.append({
                            "date": str(item.get("REPORT_DATE", "")).split(" ")[0],
                            "institution": str(item.get("ORG_NAME") or ""),
                            "researcher": str(item.get("RESEARCHER") or ""),
                            "rating": str(item.get("RATING_NAME") or ""),
                            "eps_forecast": safe_float(item.get("PREDICT_NEXT_TWO_EPS")),
                            "income_forecast": safe_float(item.get("PREDICT_NEXT_TWO_INCOME")),
                            "netprofit_forecast": safe_float(item.get("PREDICT_NEXT_TWO_NETPROFIT")),
                        })
                    return ok({"stockCode": code, "items": records, "total": len(records)})
        except Exception:
            pass

        # 2. Tushare forecast
        try:
            ts_pro = data_source.get_tushare_pro()
            if ts_pro:
                ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
                df_ts = ts_pro.forecast(ts_code=ts_code)
                if df_ts is not None and not df_ts.empty:
                    records = df_ts.head(20).fillna("").to_dict(orient="records")
                    return ok({"stockCode": code, "items": records, "total": len(records)})
        except Exception:
            pass

        # 3. AkShare
        if ak is not None:
            df = None
            try:
                df = ak.stock_profit_forecast_em(symbol=code)
            except Exception:
                pass
            if df is None or df.empty:
                try:
                    df = ak.stock_profit_forecast_ths(symbol=code)
                except Exception:
                    pass
            if df is not None and not df.empty:
                try:
                    records = df.fillna("").to_dict(orient="records")
                    return ok({"stockCode": code, "items": records, "total": len(records)})
                except Exception:
                    pass

        return fail(f"未获取到 {code} 的盈利预测数据")
    except Exception as e:
        return fail(f"系统错误: {e}")
