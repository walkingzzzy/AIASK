"""
AKShare MCP Server Utilities
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

SOURCE_NAME = "akshare"


def now_iso() -> str:
    return datetime.now().isoformat()


def ok(data: Any, *, cached: bool = False) -> dict:
    return {
        "success": True,
        "data": data,
        "error": None,
        "source": SOURCE_NAME,
        "cached": cached,
        "timestamp": now_iso(),
    }


def fail(error: Any) -> dict:
    return {
        "success": False,
        "data": None,
        "error": str(error),
        "source": SOURCE_NAME,
        "cached": False,
        "timestamp": now_iso(),
    }


def safe_float(val: Any) -> Optional[float]:
    """安全转换为浮点数：缺失/异常返回 None（避免用 0 伪装缺失）"""
    try:
        if val is None or pd.isna(val):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val: Any) -> Optional[int]:
    """安全转换为整数：缺失/异常返回 None（避免用 0 伪装缺失）"""
    try:
        if val is None or pd.isna(val):
            return None
        return int(float(val))
    except (ValueError, TypeError):
        return None


def parse_numeric(val: Any) -> Optional[float]:
    """解析带单位/百分号的数值字符串，无法解析返回 None。"""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in {"none", "nan", "false", "--"}:
        return None

    multiplier = 1.0
    if s.endswith("%"):
        s = s[:-1].strip()
    if s.endswith("万亿"):
        multiplier = 1e12
        s = s[:-2].strip()
    elif s.endswith("亿"):
        multiplier = 1e8
        s = s[:-1].strip()
    elif s.endswith("万"):
        multiplier = 1e4
        s = s[:-1].strip()
    elif s.endswith("元"):
        s = s[:-1].strip()

    s = s.replace(",", "")
    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return None


def normalize_code(code: str) -> str:
    """
    规范化股票/指数代码为 6 位数字（补零）。
    兼容输入: '1', '000001', 'sh600519', 'SZ000001' 等。
    """
    s = str(code or "").strip()
    m = re.search(r"(\d{1,6})", s)
    if not m:
        return s
    return m.group(1).zfill(6)


def format_period(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    if not s or s.lower() in {"none", "nan", "--"}:
        return ""
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if re.fullmatch(r"\d{6}", s):
        return f"{s[:4]}-{s[4:6]}"
    return s


def format_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def format_publish_date(value: Any, fallback: str) -> Optional[str]:
    formatted = format_period(value)
    if formatted:
        return formatted
    return fallback or None


def parse_date_input(value: str) -> Optional[date]:
    s = str(value or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    if re.fullmatch(r"\d{6}", s):
        try:
            return datetime.strptime(s + "01", "%Y%m%d").date()
        except ValueError:
            return None
    return None


def fetch_mofcom_shrzgm_via_curl() -> pd.DataFrame:
    import json
    url = "https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery"
    try:
        result = subprocess.run(
            ["curl", "-k", "--tlsv1", "-s", "-X", "POST", url],
            check=False,
            text=True,
            capture_output=True,
            timeout=15,
        )
    except Exception as exc:
        raise RuntimeError(f"curl 请求失败: {exc}") from exc

    if result.returncode != 0:
        raise RuntimeError(f"curl 退出码异常: {result.returncode} {result.stderr.strip()}")

    payload = result.stdout.strip()
    if not payload:
        raise RuntimeError("curl 返回为空")

    data = json.loads(payload)
    if not isinstance(data, list) or not data:
        raise RuntimeError("Mofcom 返回数据为空")

    df = pd.DataFrame(data)
    if df.empty:
        return df

    rename_map = {
        "date": "月份",
        "tiosfs": "社会融资规模增量",
        "rmblaon": "其中-人民币贷款",
        "forcloan": "其中-委托贷款外币贷款",
        "entrustloan": "其中-委托贷款",
        "trustloan": "其中-信托贷款",
        "ndbab": "其中-未贴现银行承兑汇票",
        "bibae": "其中-企业债券",
        "sfinfe": "其中-非金融企业境内股票融资",
    }
    df.rename(columns=rename_map, inplace=True)

    if "月份" in df.columns:
        df["月份"] = df["月份"].astype(str)

    for col in rename_map.values():
        if col == "月份" or col not in df.columns:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")

    ordered_cols = [
        "月份",
        "社会融资规模增量",
        "其中-人民币贷款",
        "其中-委托贷款外币贷款",
        "其中-委托贷款",
        "其中-信托贷款",
        "其中-未贴现银行承兑汇票",
        "其中-企业债券",
        "其中-非金融企业境内股票融资",
    ]
    available_cols = [col for col in ordered_cols if col in df.columns]
    if available_cols:
        df = df[available_cols]

    df.sort_values(["月份"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def pick_value(row: pd.Series, keys: list[str]) -> Any:
    """从 Series 中尝试获取列表中的 key，返回第一个非空值"""
    for k in keys:
        if k in row and pd.notna(row[k]) and str(row[k]).strip() != "":
            return row[k]
    return None
