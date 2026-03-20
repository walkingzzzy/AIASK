import os
import time

import akshare as ak

from ..utils import (
    fail,
    format_period,
    normalize_code,
    ok,
    parse_numeric,
)

# Import optimization modules
from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter


from typing import Any, Optional, Callable, TypeVar
import sys
from datetime import datetime, timedelta
from ..baostock_api import baostock_client
from ..cache import cache
from ..services.financial_schema import (
    FINANCIAL_PRIMARY_FIELDS as _FINANCIAL_PRIMARY_FIELDS,
    merge_financial_payload,
    normalize_financial_payload,
    financial_gap_summary,
    financial_payload_is_complete,
    financial_payload_is_usable,
    financial_payload_needs_enrichment,
)
from .data_quality import build_quality_meta, infer_missing_fields, normalize_reason_list
from ..date_utils import get_latest_trading_date
from ..data_source import data_source

_RETRY_SLEEP_SECONDS = float(os.getenv("AKSHARE_RETRY_SLEEP_SECONDS", "0.5"))
_FINANCE_RETRY = int(os.getenv("AKSHARE_FINANCE_RETRY", "2"))

T = TypeVar("T")
_financial_payload_is_complete = financial_payload_is_complete
_financial_payload_needs_enrichment = financial_payload_needs_enrichment
_financial_payload_is_usable = financial_payload_is_usable
_financial_gap_summary = financial_gap_summary
_merge_financial_payload = merge_financial_payload


def _build_financial_cache_entry(
    payload: dict,
    *,
    source_chain: list[str],
    fallback_reason: Optional[list[str]] = None,
) -> dict:
    normalized_payload = normalize_financial_payload(payload, source_label=payload.get("source") if isinstance(payload, dict) else None)
    return {
        "payload": dict(normalized_payload or payload or {}),
        "source_chain": [str(item).strip() for item in list(source_chain or []) if str(item).strip()],
        "fallback_reason": normalize_reason_list(fallback_reason),
    }


def _read_financial_cache_entry(entry: Any) -> tuple[Optional[dict], list[str], list[str]]:
    if not isinstance(entry, dict):
        return None, [], []

    payload = entry.get("payload")
    if isinstance(payload, dict):
        return (
            dict(payload),
            [str(item).strip() for item in list(entry.get("source_chain") or []) if str(item).strip()],
            normalize_reason_list(entry.get("fallback_reason")),
        )

    payload = dict(entry)
    source_chain = payload.pop("source_chain", None)
    fallback_reason = payload.pop("fallback_reason", None)
    return (
        payload,
        [str(item).strip() for item in list(source_chain or []) if str(item).strip()],
        normalize_reason_list(fallback_reason),
    )


def _financial_missing_fields(payload: Optional[dict]) -> list[str]:
    normalized = normalize_financial_payload(payload, include_aliases=False)
    return infer_missing_fields(
        normalized,
        _FINANCIAL_PRIMARY_FIELDS,
    )


def _ok_financial(
    payload: dict,
    *,
    source_chain: list[str],
    fallback_reason: Optional[list[str]] = None,
    started_at: Optional[datetime] = None,
    cached_result: bool = False,
) -> dict:
    data = normalize_financial_payload(payload, source_label=payload.get("source") if isinstance(payload, dict) else None) or dict(payload or {})
    missing_fields = _financial_missing_fields(data)
    degraded = bool(missing_fields)
    response = ok(data, cached=cached_result)
    response.update(
        build_quality_meta(
            source=str(data.get("source") or "unknown"),
            source_chain=source_chain,
            fallback_reason=fallback_reason,
            asof_value=data.get("reportDate"),
            missing_fields=missing_fields,
            degraded=degraded,
            success=True,
            started_at=started_at,
        )
    )
    return response


def _fail_financial(
    message: str,
    *,
    source_chain: list[str],
    fallback_reason: Optional[list[str]] = None,
    started_at: Optional[datetime] = None,
) -> dict:
    response = fail(message)
    response.update(
        build_quality_meta(
            source="none",
            source_chain=source_chain,
            fallback_reason=fallback_reason or [message],
            asof_value=None,
            missing_fields=[],
            degraded=True,
            success=False,
            started_at=started_at,
        )
    )
    response["source"] = "none"
    return response

def _call_with_retry(fn: Callable[[], T]) -> T:
    last_error: Optional[Exception] = None
    for _ in range(_FINANCE_RETRY):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if _RETRY_SLEEP_SECONDS > 0:
                time.sleep(_RETRY_SLEEP_SECONDS)
    if last_error:
        raise last_error
    raise RuntimeError("请求失败")


def _row_non_null_count(row: Any, fields: tuple[str, ...]) -> int:
    count = 0
    for field in fields:
        try:
            value = row.get(field)
        except Exception:
            value = None
        if value is not None and value == value and value != "":
            count += 1
    return count


def _pick_best_statement_row(df: Any, fields: tuple[str, ...], date_field: str = "end_date", scan_limit: int = 6):
    if df is None or getattr(df, "empty", True):
        return None
    try:
        if date_field in getattr(df, "columns", []):
            df = df.sort_values(date_field, ascending=False)
        candidates = df.head(scan_limit)
        best_row = None
        best_key = (-1, "")
        for _, row in candidates.iterrows():
            raw_period = row.get(date_field)
            period = str(raw_period or "")
            score = _row_non_null_count(row, fields)
            key = (score, period)
            if best_row is None or key > best_key:
                best_key = key
                best_row = row
        return best_row if best_row is not None else df.iloc[0]
    except Exception:
        try:
            return df.iloc[0]
        except Exception:
            return None


def _calc_ratio(numerator: Any, denominator: Any, multiplier: float = 100.0) -> Optional[float]:
    num = parse_numeric(numerator)
    den = parse_numeric(denominator)
    if num is None or den in (None, 0):
        return None
    return (num / den) * multiplier


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _get_financials_tushare(code: str) -> Optional[dict]:
    pro = data_source.get_tushare_pro()
    if not pro:
        return None

    ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=550)).strftime("%Y%m%d")

    try:
        indicator_df = pro.fina_indicator(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as e:
        print(f"[Finance] Tushare fina_indicator failed: {e}", file=sys.stderr)
        indicator_df = None

    try:
        income_df = pro.income(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as e:
        print(f"[Finance] Tushare income failed: {e}", file=sys.stderr)
        income_df = None

    if (indicator_df is None or indicator_df.empty) and (income_df is None or income_df.empty):
        return None

    indicator_row = _pick_best_statement_row(
        indicator_df,
        ("end_date", "roe", "debt_to_assets", "current_ratio", "eps", "grossprofit_margin", "netprofit_margin"),
    )
    income_row = _pick_best_statement_row(
        income_df,
        ("end_date", "total_revenue", "operate_profit", "n_income"),
    )

    report_date = None
    if indicator_row is not None and indicator_row.get("end_date"):
        report_date = str(indicator_row.get("end_date"))
    elif income_row is not None and income_row.get("end_date"):
        report_date = str(income_row.get("end_date"))

    balance_row = None
    need_balance_sheet = (
        indicator_row is None
        or parse_numeric(indicator_row.get("debt_to_assets")) is None
        or parse_numeric(indicator_row.get("current_ratio")) is None
        or parse_numeric(indicator_row.get("roa")) is None
    )
    if need_balance_sheet:
        try:
            balance_df = pro.balancesheet(ts_code=ts_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"[Finance] Tushare balancesheet failed: {e}", file=sys.stderr)
            balance_df = None
        balance_row = _pick_best_statement_row(
            balance_df,
            ("end_date", "total_assets", "total_liab", "total_cur_assets", "total_cur_liab", "total_hldr_eqy_exc_min_int"),
        )

    if report_date is None and balance_row is not None and balance_row.get("end_date"):
        report_date = str(balance_row.get("end_date"))

    debt_ratio = parse_numeric(indicator_row.get("debt_to_assets")) if indicator_row is not None else None
    if debt_ratio is None and balance_row is not None:
        debt_ratio = _calc_ratio(balance_row.get("total_liab"), balance_row.get("total_assets"))

    current_ratio = parse_numeric(indicator_row.get("current_ratio")) if indicator_row is not None else None
    if current_ratio is None and balance_row is not None:
        current_ratio = _calc_ratio(balance_row.get("total_cur_assets"), balance_row.get("total_cur_liab"), multiplier=1.0)

    # 获取ROA，如果为空则尝试计算
    roa_value = parse_numeric(indicator_row.get("roa")) if indicator_row is not None else None
    if roa_value is None and income_row is not None and balance_row is not None:
        roa_value = _calc_ratio(income_row.get("n_income"), balance_row.get("total_assets"))
        if roa_value is not None:
            print(f"[Finance] Calculated ROA for {code}: {roa_value:.2f}%", file=sys.stderr)

    revenue_growth = None
    profit_growth = None
    if indicator_row is not None:
        revenue_growth = _first_not_none(
            parse_numeric(indicator_row.get("tr_yoy")),
            parse_numeric(indicator_row.get("or_yoy")),
            parse_numeric(indicator_row.get("q_gr_yoy")),
        )
        profit_growth = _first_not_none(
            parse_numeric(indicator_row.get("netprofit_yoy")),
            parse_numeric(indicator_row.get("q_netprofit_yoy")),
            parse_numeric(indicator_row.get("profit_dedt")),
        )

    return {
        "code": code,
        "reportDate": report_date,
        "revenue": parse_numeric(income_row.get("total_revenue")) if income_row is not None else None,
        "netProfit": parse_numeric(income_row.get("n_income")) if income_row is not None else None,
        "grossProfitMargin": parse_numeric(indicator_row.get("grossprofit_margin")) if indicator_row is not None else None,
        "netProfitMargin": parse_numeric(indicator_row.get("netprofit_margin")) if indicator_row is not None else None,
        "roe": parse_numeric(indicator_row.get("roe")) if indicator_row is not None else None,
        "roa": roa_value,
        "debtRatio": debt_ratio,
        "currentRatio": current_ratio,
        "eps": parse_numeric(indicator_row.get("eps")) if indicator_row is not None else None,
        "bvps": None,
        "revenueGrowth": revenue_growth,
        "profitGrowth": profit_growth,
        "source": "tushare_pro",
    }

@cached(ttl=86400.0)  # 24h cache for financial data
async def get_financials(stock_code: str) -> dict:
    """
    获取股票财务指标数据

    数据源优先级: TimescaleDB → Tushare Pro → AkShare → Baostock
    """
    # Rate limiting
    limiter = get_limiter("finance", max_calls=5, period=1.0)
    limiter.acquire()

    code = normalize_code(stock_code)
    started_at = datetime.now().astimezone()

    # 0. Check Cache (TTL 24h)
    cached_entry = cache.get(f"financials_{code}", ttl_seconds=86400)
    cached_payload, cached_source_chain, cached_fallback_reason = _read_financial_cache_entry(cached_entry)
    if cached_payload and _financial_payload_is_complete(cached_payload) and not _financial_payload_needs_enrichment(cached_payload):
        return _ok_financial(
            cached_payload,
            source_chain=cached_source_chain or [cached_payload.get("source") or "cache.financials"],
            fallback_reason=cached_fallback_reason,
            started_at=started_at,
            cached_result=True,
        )

    # 0.5. DB 优先：查 TimescaleDB financials 表
    db_result = None
    best_payload = None
    fallback_reason: list[str] = []
    source_chain = ["db.get_financials"]
    try:
        from ..storage import get_db
        db = get_db()
        db_data = await db.get_financials(code)
        if db_data:
            row = db_data[0]
            db_result = {
                "code": code,
                **row,
                "source": "timescaledb",
            }
            best_payload = normalize_financial_payload(db_result, source_label="timescaledb")
            if _financial_payload_is_complete(best_payload) and not _financial_payload_needs_enrichment(best_payload):
                cache.set(
                    f"financials_{code}",
                    _build_financial_cache_entry(best_payload, source_chain=source_chain),
                )
                return _ok_financial(
                    best_payload,
                    source_chain=source_chain,
                    started_at=started_at,
                )
    except Exception as e_db:
        import sys
        print(f"[Finance] TimescaleDB query failed for {code}: {e_db}", file=sys.stderr)
        fallback_reason.append(f"db.get_financials failed: {e_db}")

    # Strategy:
    # 1. Try Tushare Pro (custom/official) - 优先使用
    # 2. Try AkShare THS (Most recent) - 降级
    # 3. Try AkShare EM (Standard) - 降级
    # 4. Fallback to Baostock (Stable/Offline-like) - 最后降级

    # 1. Try Tushare Pro (优先补齐核心财务)
    try:
        source_chain.append("tushare_pro")
        tushare_res = _get_financials_tushare(code)
        if tushare_res:
            merged = _merge_financial_payload(best_payload or db_result, tushare_res)
            if merged:
                best_payload = merged
            if _financial_payload_needs_enrichment(best_payload):
                fallback_reason.append(f"tushare_pro incomplete: {_financial_gap_summary(best_payload)}")
            else:
                cache.set(
                    f"financials_{code}",
                    _build_financial_cache_entry(
                        best_payload,
                        source_chain=source_chain,
                        fallback_reason=fallback_reason,
                    ),
                )
                return _ok_financial(
                    best_payload,
                    source_chain=source_chain,
                    fallback_reason=fallback_reason,
                    started_at=started_at,
                )
        else:
            fallback_reason.append("tushare_pro returned empty")
    except Exception as e:
        print(f"Tushare financial fetch failed for {code}: {e}", file=sys.stderr)
        fallback_reason.append(f"tushare_pro failed: {e}")

    # 2 & 3. Try AkShare (补充 EPS/BVPS/比率等)
    if best_payload is None or _financial_payload_needs_enrichment(best_payload):
        try:
            source_chain.append("akshare_financials")
            akshare_res = _get_financials_akshare(code)
        except Exception as e:
            print(f"AkShare financial fetch failed for {code}: {e}", file=sys.stderr)
            akshare_res = None
            fallback_reason.append(f"akshare_financials failed: {e}")
        if akshare_res:
            merged = _merge_financial_payload(best_payload or db_result, akshare_res)
            if merged:
                best_payload = merged
            if _financial_payload_needs_enrichment(best_payload):
                fallback_reason.append(f"akshare_financials incomplete: {_financial_gap_summary(best_payload)}")
            else:
                cache.set(
                    f"financials_{code}",
                    _build_financial_cache_entry(
                        best_payload,
                        source_chain=source_chain,
                        fallback_reason=fallback_reason,
                    ),
                )
                return _ok_financial(
                    best_payload,
                    source_chain=source_chain,
                    fallback_reason=fallback_reason,
                    started_at=started_at,
                )
        elif "akshare_financials failed:" not in " | ".join(fallback_reason):
            fallback_reason.append("akshare_financials returned empty")

    # 4. Fallback to Baostock
    if best_payload is None or _financial_payload_needs_enrichment(best_payload):
        try:
            source_chain.append("baostock_financials")
            # Baostock generally works with Quarter/Year, so we get the latest available
            # But for "latest", we might need to guess the quarter.
            # Let's try previous quarter relative to now.
            now = datetime.now()
            baostock_res = None
            # Simple logic: Check last 4 quarters
            for i in range(4):
                # approximate logic to go back quarters
                q_date = now - timedelta(days=90 * i)
                year = str(q_date.year)
                month = q_date.month
                quarter = "1" if month <= 3 else "2" if month <= 6 else "3" if month <= 9 else "4"

                # Fetch Balance Sheet (for BVPS/Debt) and Profit (for EPS/ROE)
                # This is expensive, so just trying once or twice might be enough.

                # Simplified: just try to get a valid result
                df_profit = baostock_client.get_profit_statement(code, year, quarter)
                if not df_profit.empty:
                    row = df_profit.iloc[0]
                    # Map Baostock fields to our schema
                    # pubDate, statDate, epsTTM, mbEPS, ...
                    baostock_res = {
                        "code": code,
                        "reportDate": f"{year}-Q{quarter}",
                        "eps": parse_numeric(row.get("epsTTM")), # or mbEPS
                        "roe": parse_numeric(row.get("roeAvg")),
                        "grossProfitMargin": parse_numeric(row.get("grossMargin")),
                        "netProfitMargin": parse_numeric(row.get("netProfitMargin")),
                        "source": "baostock"
                    }
                    if baostock_res:
                        break
        except Exception as e:
            print(f"Baostock financial fetch failed for {code}: {e}", file=sys.stderr)
            baostock_res = None
            fallback_reason.append(f"baostock_financials failed: {e}")

        if baostock_res:
            merged = _merge_financial_payload(best_payload or db_result, baostock_res)
            if merged:
                best_payload = merged
        else:
            fallback_reason.append("baostock_financials returned empty")

    if best_payload and _financial_payload_is_usable(best_payload):
        if _financial_payload_needs_enrichment(best_payload):
            fallback_reason.append(f"final payload partial: {_financial_gap_summary(best_payload)}")
        cache.set(
            f"financials_{code}",
            _build_financial_cache_entry(
                best_payload,
                source_chain=source_chain,
                fallback_reason=fallback_reason,
            ),
        )
        return _ok_financial(
            best_payload,
            source_chain=source_chain,
            fallback_reason=fallback_reason,
            started_at=started_at,
        )

    if db_result and _financial_payload_is_usable(db_result):
        best_payload = normalize_financial_payload(db_result, source_label="timescaledb") or db_result
        if _financial_payload_needs_enrichment(best_payload):
            fallback_reason.append(f"final payload partial: {_financial_gap_summary(best_payload)}")
        cache.set(
            f"financials_{code}",
            _build_financial_cache_entry(
                best_payload,
                source_chain=source_chain,
                fallback_reason=fallback_reason,
            ),
        )
        return _ok_financial(
            best_payload,
            source_chain=source_chain,
            fallback_reason=fallback_reason,
            started_at=started_at,
        )

    return _fail_financial(
        f"所有数据源均无法获取 {code} 的财务数据 (AkShare & Baostock)",
        source_chain=source_chain,
        fallback_reason=fallback_reason,
        started_at=started_at,
    )

def _get_financials_akshare(code: str) -> Optional[dict]:
    try:
        df = _call_with_retry(lambda: ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期"))
        if df is None or df.empty:
            # Fallback to EM
            return _get_financials_akshare_em(code)

        row = df.iloc[-1]
        report_date = str(row.get("报告期", ""))

        # 尝试多个可能的ROA字段名
        roa = (
            parse_numeric(row.get("总资产收益率")) or
            parse_numeric(row.get("总资产报酬率")) or
            parse_numeric(row.get("ROA")) or
            parse_numeric(row.get("资产收益率")) or
            parse_numeric(row.get("总资产净利率"))
        )

        return {
            "code": code,
            "reportDate": report_date,
            "eps": parse_numeric(row.get("基本每股收益")),
            "bvps": parse_numeric(row.get("每股净资产")),
            "roe": parse_numeric(row.get("净资产收益率")) or parse_numeric(row.get("净资产收益率-摊薄")),
            "roa": roa,
            "grossProfitMargin": parse_numeric(row.get("销售毛利率")),
            "netProfitMargin": parse_numeric(row.get("销售净利率")),
            "debtRatio": parse_numeric(row.get("资产负债率")),
            "currentRatio": parse_numeric(row.get("流动比率")),
            "source": "akshare_ths"
        }
    except Exception as e:
        print(f"[Finance] AkShare THS failed: {e}", file=sys.stderr)
        return _get_financials_akshare_em(code)

def _get_financials_akshare_em(code: str) -> Optional[dict]:
    df = _call_with_retry(lambda: ak.stock_financial_abstract(symbol=code))
    if df is None or df.empty:
        return None

    date_cols = [c for c in df.columns if str(c).isdigit()]
    if not date_cols:
        return None
    latest_col = sorted(date_cols)[-1]

    def pick_metric(metric: str) -> Optional[float]:
        rows = df[df["指标"] == metric]
        if rows.empty:
            return None
        return parse_numeric(rows.iloc[0].get(latest_col))

    # 尝试多个可能的ROA指标名称
    roa = (
        pick_metric("总资产收益率") or
        pick_metric("总资产报酬率") or
        pick_metric("总资产净利率") or
        pick_metric("资产收益率")
    )

    return {
        "code": code,
        "reportDate": str(latest_col),
        "eps": pick_metric("基本每股收益"),
        "bvps": pick_metric("每股净资产"),
        "roe": pick_metric("净资产收益率"),
        "roa": roa,
        "grossProfitMargin": pick_metric("销售毛利率"),
        "netProfitMargin": pick_metric("销售净利率"),
        "debtRatio": pick_metric("资产负债率"),
        "currentRatio": pick_metric("流动比率"),
        "source": "akshare_em"
    }


@cached(ttl=86400.0)  # 24h cache for stock info
def get_stock_info(stock_code: str) -> dict:
    """
    获取股票基本信息

    Args:
        stock_code: 股票代码
    """
    # Rate limiting
    limiter = get_limiter("info", max_calls=5, period=1.0)
    limiter.acquire()

    try:
        code = normalize_code(stock_code)
        df = None

        # 1. Try Tushare Pro
        try:
            pro = data_source.get_tushare_pro()
            if pro:
                ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
                df = pro.stock_basic(
                    ts_code=ts_code,
                    list_status="L",
                    fields="ts_code,symbol,name,market,industry,list_date",
                )
        except Exception:
            df = None

        if df is not None and not df.empty:
            row = df.iloc[0]
            total_shares = ""
            float_shares = ""
            total_market_cap = ""
            float_market_cap = ""
            # Try to enrich with daily_basic for share/cap data
            try:
                if pro:
                    ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
                    from datetime import datetime, timedelta
                    for days_back in range(1, 8):
                        trade_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
                        db_df = pro.daily_basic(ts_code=ts_code, trade_date=trade_date,
                                                fields='ts_code,total_share,float_share,total_mv,circ_mv')
                        if db_df is not None and not db_df.empty:
                            db_row = db_df.iloc[0]
                            ts_val = db_row.get('total_share')
                            total_shares = f"{float(ts_val) * 10000:.0f}" if ts_val and ts_val == ts_val else ""
                            fs_val = db_row.get('float_share')
                            float_shares = f"{float(fs_val) * 10000:.0f}" if fs_val and fs_val == fs_val else ""
                            tm_val = db_row.get('total_mv')
                            total_market_cap = f"{float(tm_val) * 10000:.0f}" if tm_val and tm_val == tm_val else ""
                            cm_val = db_row.get('circ_mv')
                            float_market_cap = f"{float(cm_val) * 10000:.0f}" if cm_val and cm_val == cm_val else ""
                            break
            except Exception:
                pass
            return ok(
                {
                    "code": code,
                    "name": str(row.get("name") or ""),
                    "industry": str(row.get("industry") or ""),
                    "listDate": str(row.get("list_date") or ""),
                    "totalShares": total_shares,
                    "floatShares": float_shares,
                    "totalMarketCap": total_market_cap,
                    "floatMarketCap": float_market_cap,
                    "raw": {k: str(row.get(k, "")) for k in df.columns},
                }
            )

        try:
            df = _call_with_retry(lambda: ak.stock_individual_info_em(symbol=code))
        except Exception:
            df = None
        if df is None or df.empty:
            df = ak.stock_profile_cninfo(symbol=code)
            if df is None or df.empty:
                return fail(f"未找到股票 {code} 的信息")

        info: dict[str, str] = {}
        if "item" in df.columns and "value" in df.columns:
            for _, row in df.iterrows():
                key = str(row.get("item", "")).strip()
                value = row.get("value", "")
                if not key:
                    continue
                info[key] = str(value) if value is not None else ""
        else:
            row = df.iloc[0]
            info = {str(k): str(row.get(k, "")) for k in df.columns}

        return ok(
            {
                "code": code,
                "name": info.get("股票简称", info.get("A股简称", "")),
                "industry": info.get("行业", info.get("所属行业", "")),
                "listDate": info.get("上市时间", info.get("上市日期", "")),
                "totalShares": info.get("总股本", ""),
                "floatShares": info.get("流通股", ""),
                "totalMarketCap": info.get("总市值", ""),
                "floatMarketCap": info.get("流通市值", ""),
                "raw": info,
            }
        )
    except Exception as e:
        return fail(e)

def register(mcp):
    mcp.tool()(get_financials)
    mcp.tool()(get_stock_info)
