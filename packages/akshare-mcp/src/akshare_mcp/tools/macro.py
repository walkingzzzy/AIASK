import os
from typing import Any, Optional

import akshare as ak
import pandas as pd

from ..core.cache_manager import cached
from ..core.rate_limiter import get_limiter
from ..data_source import data_source
from ..utils import (
    fail,
    fetch_mofcom_shrzgm_via_curl,
    format_period,
    format_publish_date,
    ok,
    parse_numeric,
)


def _get_social_financing_df() -> pd.DataFrame:
    try:
        return ak.macro_china_shrzgm()
    except Exception as exc:
        try:
            return fetch_mofcom_shrzgm_via_curl()
        except Exception as curl_exc:
            raise RuntimeError(f"Mofcom TLS 失败且 curl 兜底失败: {curl_exc}") from exc


def _try_tushare_macro(indicator: str, limit: int) -> Optional[dict]:
    pro = data_source.get_tushare_pro()
    if not pro:
        return None

    def _format_month(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        if len(text) == 6 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}"
        return format_period(text)

    try:
        if indicator == "cpi":
            df = pro.cpi()
            if df is None or df.empty:
                return None
            records = []
            for _, row in df.iterrows():
                period = _format_month(row.get("month") or row.get("period"))
                value = parse_numeric(row.get("nt_val"))
                yoy = parse_numeric(row.get("nt_yoy"))
                mom = parse_numeric(row.get("nt_mom"))
                if period and value is not None:
                    records.append({"period": period, "value": value, "yoyChange": yoy, "momChange": mom, "publishDate": period})
            if not records:
                return None
            records = records[-limit:][::-1]
            return ok({"indicator": indicator, "records": records})

        if indicator == "ppi":
            df = pro.ppi()
            if df is None or df.empty:
                return None
            records = []
            for _, row in df.iterrows():
                period = _format_month(row.get("month") or row.get("period"))
                value = parse_numeric(row.get("ppi"))
                yoy = parse_numeric(row.get("ppi_yoy"))
                mom = parse_numeric(row.get("ppi_mom"))
                if period and value is not None:
                    records.append({"period": period, "value": value, "yoyChange": yoy, "momChange": mom, "publishDate": period})
            if not records:
                return None
            records = records[-limit:][::-1]
            return ok({"indicator": indicator, "records": records})

        if indicator in {"m2", "m2_growth"}:
            df = pro.money_supply()
            if df is None or df.empty:
                return None
            records = []
            for _, row in df.iterrows():
                period = _format_month(row.get("month") or row.get("period"))
                value = parse_numeric(row.get("m2")) if indicator == "m2" else parse_numeric(row.get("m2_yoy"))
                mom = parse_numeric(row.get("m2_mom")) if indicator == "m2_growth" else None
                if period and value is not None:
                    records.append({"period": period, "value": value, "yoyChange": None if indicator == "m2" else value, "momChange": mom, "publishDate": period})
            if not records:
                return None
            records = records[-limit:][::-1]
            return ok({"indicator": indicator, "records": records})

        if indicator == "shibor":
            df = pro.shibor()
            if df is None or df.empty:
                return None
            records = []
            for _, row in df.iterrows():
                period = format_period(row.get("date") or row.get("trade_date") or row.get("period"))
                value = parse_numeric(row.get("on")) or parse_numeric(row.get("overnight"))
                if period and value is not None:
                    records.append({"period": period, "value": value, "yoyChange": None, "momChange": None, "publishDate": period})
            if not records:
                return None
            records = records[-limit:][::-1]
            return ok({"indicator": indicator, "records": records})

    except Exception:
        return None
    return None


@cached(ttl=3600.0)  # 1小时缓存，宏观数据更新频率低
def get_macro_indicator(indicator: str, limit: int = 120) -> dict:
    """
    获取宏观经济指标数据（标准化输出）

    Args:
        indicator: 指标代码，如 gdp/cpi/pmi/m2 等
        limit: 返回记录条数，默认120
    """
    limiter = get_limiter("macro", rate=3.0)  # 3次/秒
    limiter.acquire()
    
    try:
        code = str(indicator or "").strip().lower()

        # 0. Try Tushare Pro first for supported macro indicators
        ts_result = _try_tushare_macro(code, min(limit, 480))
        if ts_result and ts_result.get("success"):
            return ts_result

        def _unemployment_df() -> pd.DataFrame:
            df = ak.macro_china_urban_unemployment()
            if df is None or df.empty:
                return df
            if "item" in df.columns:
                df = df[df["item"].astype(str).str.contains("失业率")]
            return df

        macro_specs = {
            "gdp": {
                "func": ak.macro_china_gdp,
                "period": "季度",
                "value": "国内生产总值-绝对值",
                "yoy": "国内生产总值-同比增长",
            },
            "gdp_growth": {
                "func": ak.macro_china_gdp,
                "period": "季度",
                "value": "国内生产总值-同比增长",
            },
            "cpi": {
                "func": ak.macro_china_cpi,
                "period": "月份",
                "value": "全国-同比增长",
                "mom": "全国-环比增长",
            },
            "ppi": {
                "func": ak.macro_china_ppi,
                "period": "月份",
                "value": "当月同比增长",
            },
            "pmi": {
                "func": ak.macro_china_pmi,
                "period": "月份",
                "value": "制造业-指数",
            },
            "pmi_service": {
                "func": ak.macro_china_pmi,
                "period": "月份",
                "value": "非制造业-指数",
            },
            "m2": {
                "func": ak.macro_china_money_supply,
                "period": "月份",
                "value": "货币和准货币(M2)-数量(亿元)",
                "scale": 1 / 10000,
            },
            "m2_growth": {
                "func": ak.macro_china_money_supply,
                "period": "月份",
                "value": "货币和准货币(M2)-同比增长",
                "mom": "货币和准货币(M2)-环比增长",
            },
            "social_financing": {
                "func": _get_social_financing_df,
                "period": "月份",
                "value": "社会融资规模增量",
                "scale": 1 / 10000,
            },
            "lpr_1y": {
                "func": ak.macro_china_lpr,
                "period": "TRADE_DATE",
                "value": "LPR1Y",
            },
            "lpr_5y": {
                "func": ak.macro_china_lpr,
                "period": "TRADE_DATE",
                "value": "LPR5Y",
            },
            "rrr": {
                "func": ak.macro_china_reserve_requirement_ratio,
                "period": "公布时间",
                "value": "大型金融机构-调整后",
                "mom": "大型金融机构-调整幅度",
                "publish": "公布时间",
            },
            "industrial_output": {
                "func": ak.macro_china_industrial_production_yoy,
                "period": "日期",
                "value": "今值",
                "publish": "日期",
            },
            "retail_sales": {
                "func": ak.macro_china_consumer_goods_retail,
                "period": "月份",
                "value": "同比增长",
                "mom": "环比增长",
            },
            "fixed_investment": {
                "func": ak.macro_china_gdzctz,
                "period": "月份",
                "value": "同比增长",
                "mom": "环比增长",
            },
            "export": {
                "func": ak.macro_china_exports_yoy,
                "period": "日期",
                "value": "今值",
                "publish": "日期",
            },
            "import": {
                "func": ak.macro_china_imports_yoy,
                "period": "日期",
                "value": "今值",
                "publish": "日期",
            },
            "trade_balance": {
                "func": ak.macro_china_trade_balance,
                "period": "日期",
                "value": "今值",
                "publish": "日期",
            },
            "fx_reserve": {
                "func": ak.macro_china_fx_reserves_yearly,
                "period": "日期",
                "value": "今值",
                "publish": "日期",
            },
            "usdcny": {
                "func": ak.macro_china_rmb,
                "period": "日期",
                "value": "美元/人民币_中间价",
                "mom": "美元/人民币_涨跌幅",
                "publish": "日期",
            },
            "unemployment": {
                "func": _unemployment_df,
                "period": "date",
                "value": "value",
            },
        }

        spec = macro_specs.get(code)
        if not spec:
            return fail(f"未支持的指标: {indicator}")

        limit = int(limit)
        if limit <= 0:
            limit = 120
        limit = min(limit, 480)

        df = spec["func"]()
        if df is None or df.empty:
            return fail(f"指标 {indicator} 数据为空")

        period_col = spec["period"]
        value_col = spec["value"]
        yoy_col = spec.get("yoy")
        mom_col = spec.get("mom")
        publish_col = spec.get("publish")
        scale = spec.get("scale")

        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            period = format_period(row.get(period_col))
            if not period:
                continue
            value = parse_numeric(row.get(value_col))
            if value is None:
                continue
            if isinstance(scale, (int, float)) and scale != 1:
                value = value * float(scale)

            yoy = parse_numeric(row.get(yoy_col)) if yoy_col else None
            mom = parse_numeric(row.get(mom_col)) if mom_col else None
            publish = format_publish_date(row.get(publish_col) if publish_col else None, period)

            records.append(
                {
                    "period": period,
                    "value": value,
                    "yoyChange": yoy,
                    "momChange": mom,
                    "publishDate": publish,
                }
            )

        if not records:
            return fail(f"指标 {indicator} 无有效数据")

        records = sorted(records, key=lambda x: str(x.get("period") or ""))
        records = records[-limit:]
        records.reverse()

        return ok(
            {
                "indicator": code,
                "records": records,
            }
        )
    except Exception as e:
        return fail(e)


def register(mcp):
    mcp.tool()(get_macro_indicator)
