"""通达信 tqcenter SDK 数据源适配器。

本模块是项目获取金融数据的**主路径**。通过通达信量化平台 Python SDK
(tqcenter) 与本地运行的通达信客户端通信，覆盖行情、财务、交易、板块、
ETF/可转债 等数据维度。

设计与契约：
- 单例模式 + 线程安全。SDK 调用本身是同步的；调用方在异步路径需用
  ``asyncio.to_thread`` 包裹。
- 所有公开函数失败时返回空 (``None`` / ``[]`` / ``{}``)，不抛异常上溢。
  调用方依据空值判断是否需要降级。
- 输出字段命名与 ``data_source.quotes.py`` / ``market_data.py`` 现有
  契约保持一致：``date='YYYY-MM-DD'`` / ``open/high/low/close/volume/amount``
  / ``source='tqcenter'``。
- 数据归一化：tqcenter 大量字符串字段（含价格、量、PE/PB 等），统一通过
  ``_safe_float`` 转 float；交易日整数 ``YYYYMMDD`` 转 ``YYYY-MM-DD``。

实测的数据形态 (来源 scripts/tdx_probe/result*.json + probe_shapes.py)：
- ``get_market_data`` 返回 ``{field: DataFrame}``；columns 永远是 stock_code，
  index 永远是 ``pd.Timestamp``。单股 shape=(N,1)，多股 shape=(N,M)。
- ``get_market_snapshot`` 返回 26 字段 dict（字符串），含五档盘口数组。
- ``get_more_info`` 返回 88 字段 dict（字符串），含涨跌停价/PE/PB/换手/
  量比/总市值/封单/涨停天/最近大事日。
- ``get_relation`` 返回 list[dict]，每个 ``{BlockCode, BlockName, BlockType,
  GPNume}``；BlockType 取值 行业/地区/概念/风格/指数。
- ``get_divid_factors`` 返回 DataFrame，列 ``Type/Bonus/AllotPrice/
  ShareBonus/Allotment``，index 为 Timestamp。

环境变量：
- ``TDX_INSTALL_DIR``     通达信安装目录（默认 C:\\new_tdx_test）
- ``TDX_PYPLUGINS_PATH``  tqcenter.py 所在目录（默认 ${TDX_INSTALL_DIR}\\PYPlugins\\sys）
- ``TDX_TQCENTER_REQUIRED``  ``1`` 时客户端不可用直接 raise；``0`` (默认) 让
  调用方按空返回降级到 tdx_local
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import contextlib
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SDK 加载（线程安全单例）
# ---------------------------------------------------------------------------

_tq: Any = None
_tq_lock = threading.Lock()
_tq_initialized = False


def _resolve_pyplugins_path() -> str:
    explicit = os.getenv("TDX_PYPLUGINS_PATH", "").strip()
    if explicit:
        return explicit
    tdx_dir = os.getenv("TDX_INSTALL_DIR", r"C:\new_tdx_test").strip()
    return str(Path(tdx_dir) / "PYPlugins" / "sys")


def _is_required() -> bool:
    return os.getenv("TDX_TQCENTER_REQUIRED", "0") == "1"


def get_tq():
    """获取 tqcenter ``tq`` 单例。失败返回 None（除非 TDX_TQCENTER_REQUIRED=1）。"""
    global _tq, _tq_initialized
    if _tq_initialized:
        return _tq
    with _tq_lock:
        if _tq_initialized:
            return _tq
        pyplugins = _resolve_pyplugins_path()
        if pyplugins not in sys.path:
            sys.path.insert(0, pyplugins)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                from tqcenter import tq  # type: ignore
                tq_file = str(Path(pyplugins) / "tqcenter.py")
                tq.initialize(tq_file)
            _tq = tq
            _tq_initialized = True
            logger.info("[TdxTQ] tqcenter SDK initialized: %s", pyplugins)
        except Exception as exc:
            logger.error("[TdxTQ] tqcenter init failed: %s", exc)
            _tq = None
            _tq_initialized = True  # 不再重试
            if _is_required():
                raise
    return _tq


def reset_tq() -> None:
    """测试或客户端重启场景下用——清空已 init 状态。"""
    global _tq, _tq_initialized
    with _tq_lock:
        _tq = None
        _tq_initialized = False


# ---------------------------------------------------------------------------
# 通用辅助
# ---------------------------------------------------------------------------

def _normalize_code(code: str) -> str:
    """将纯数字代码转为 TDX 格式（如 600519.SH）。

    实测代码段（来源 ``tq.get_stock_list``）：

    - ``6xx / 688xxx`` 沪市主板/科创板 → ``.SH``
    - ``9xxxxx`` 沪市 B 股 → ``.SH``
    - ``5xxxxx`` 沪市基金/REITs/ETF → ``.SH``
    - ``110/111/113/118 xxx`` 沪市可转债 → ``.SH``
    - ``920xxx`` 北交所主板 → ``.BJ``
    - ``810xxx`` 北交所可转债 → ``.BJ``
    - 其余 → ``.SZ``（含深市主板 0xxxxx、创业板 30xxxx、深可转债 123/127/128 xxx 等）
    """
    code = str(code).strip()
    if "." in code:
        return code
    # 北交所
    if code.startswith(("920", "810")):
        return f"{code}.BJ"
    # 沪市 6/9/5 + 沪市可转债 110/111/113/118
    if code.startswith(("6", "9", "5")):
        return f"{code}.SH"
    if code.startswith(("110", "111", "113", "118")):
        return f"{code}.SH"
    return f"{code}.SZ"


def _format_date(val: Any) -> str:
    """把 TDX 返回的日期值统一成 ``YYYY-MM-DD``。"""
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    try:
        s = str(int(float(s)))
    except (ValueError, TypeError):
        pass
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    return s


def _safe_float(val: Any) -> Optional[float]:
    """字符串 / numpy 类型兜底转 float。"""
    if val is None or val == "" or val == "--":
        return None
    try:
        v = float(val)
        return v if v == v else None  # NaN 检测
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    f = _safe_float(val)
    return int(f) if f is not None else None


def _call_with_retry(fn, *args, retries: int = 1, **kwargs):
    """tqcenter 偶发首次返回 None / "server return none"，重试 1 次即可。"""
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                v = fn(*args, **kwargs)
            if v is not None:
                return v
        except Exception as exc:  # pragma: no cover - SDK 内部错误
            last_exc = exc
            logger.debug("[TdxTQ] %s attempt %s failed: %s", fn.__name__, attempt, exc)
    if last_exc is not None:
        logger.warning("[TdxTQ] %s exhausted retries: %s", fn.__name__, last_exc)
    return None


# ---------------------------------------------------------------------------
# 1. K 线
# ---------------------------------------------------------------------------

# 项目内部 period 与 tqcenter period 之间的别名映射（实测 tqcenter 接受
# 1d/1w/1mon/1q/1y/1m/5m/15m/30m/1h/tick）
_TQ_PERIOD_MAP: Dict[str, str] = {
    "daily": "1d", "1d": "1d", "d": "1d",
    "weekly": "1w", "1w": "1w", "w": "1w",
    "monthly": "1mon", "1m_period": "1mon", "1mon": "1mon", "month": "1mon",
    "quarterly": "1q", "1q": "1q", "q": "1q",
    "yearly": "1y", "1y": "1y", "y": "1y",
    "1m": "1m", "1min": "1m",
    "5m": "5m", "5min": "5m",
    "15m": "15m", "15min": "15m",
    "30m": "30m", "30min": "30m",
    "60m": "1h", "1h": "1h", "60min": "1h", "1hour": "1h",
    "tick": "tick",
}


def _to_tq_period(period: str) -> str:
    return _TQ_PERIOD_MAP.get(str(period or "").strip().lower(), "1d")


def get_kline(
    code: str,
    period: str = "1d",
    limit: int = 2000,
    dividend_type: str = "front",
) -> list[dict]:
    """获取 K 线数据。返回 list[dict]，单只股票按时间升序。

    每行字段：date / open / high / low / close / volume(股) / amount(元) /
    change_pct / source='tqcenter'。
    """
    tq = get_tq()
    if tq is None:
        return []

    stock = _normalize_code(code)
    tq_period = _to_tq_period(period)

    try:
        data = _call_with_retry(
            tq.get_market_data,
            field_list=[],
            stock_list=[stock],
            period=tq_period,
            start_time="",
            end_time="",
            count=int(limit),
            dividend_type=dividend_type,
            fill_data=True,
        )
    except Exception as exc:
        logger.warning("[TdxTQ] get_market_data raise %s: %s", code, exc)
        return []

    if not data:
        return []

    close_df = data.get("Close")
    if close_df is None or getattr(close_df, "empty", True):
        return []

    # 实测：columns 永远是 stock_code，index 永远是 Timestamp。
    # 多股 shape=(N,M)；单股 shape=(N,1)。
    if stock not in getattr(close_df, "columns", []):
        # 回退：用第 0 列（理论上不会发生，但保留）
        try:
            col = close_df.columns[0]
        except Exception:
            return []
    else:
        col = stock

    rows: list[dict] = []
    try:
        n = len(close_df.index)
        for i in range(n):
            ts = close_df.index[i]
            row = {
                "date": _format_date(ts),
                "open": _safe_float(data["Open"][col].iloc[i]) if "Open" in data else None,
                "high": _safe_float(data["High"][col].iloc[i]) if "High" in data else None,
                "low": _safe_float(data["Low"][col].iloc[i]) if "Low" in data else None,
                "close": _safe_float(data["Close"][col].iloc[i]),
                "volume": _safe_int(data["Volume"][col].iloc[i]) if "Volume" in data else None,
                "amount": _safe_float(data["Amount"][col].iloc[i]) if "Amount" in data else None,
                "source": "tqcenter",
            }
            rows.append(row)
    except Exception as exc:
        logger.warning("[TdxTQ] kline parse error %s: %s", code, exc)
        return []

    # 计算 change_pct
    for i in range(1, len(rows)):
        prev = rows[i - 1].get("close")
        cur = rows[i].get("close")
        if prev and cur is not None and prev > 0:
            rows[i]["pre_close"] = prev
            rows[i]["change_pct"] = round((cur - prev) / prev * 100, 4)

    return rows


# ---------------------------------------------------------------------------
# 2. 实时报价（snapshot + more_info 拼接）
# ---------------------------------------------------------------------------

def _to_bid_ask(seq: Any, conv) -> List[Optional[Any]]:
    if not isinstance(seq, list):
        return [None, None, None, None, None]
    out: List[Optional[Any]] = []
    for i in range(5):
        out.append(conv(seq[i]) if i < len(seq) else None)
    return out


def get_realtime_quote(code: str) -> Optional[dict]:
    """实时行情。snapshot (26 字段) + more_info (88 字段) 合并。

    返回值字段稳定契约（用于上层 tools/market/quote.py / order_book.py）：
    code, name, price, change, changePercent, open, high, low, preClose,
    volume, amount, turnoverRate, pe_ttm, pb, market_cap, float_market_cap,
    up_limit, down_limit, ma5, hist_high_52w, hist_low_52w,
    bid1..bid5, bid_vol1..bid_vol5, ask1..ask5, ask_vol1..ask_vol5,
    inside, outside, even_zt_count, last_zt_continuous_days,
    fund_main_net, latest_report_date, source.
    """
    tq = get_tq()
    if tq is None:
        return None

    stock = _normalize_code(code)
    snap: Dict[str, Any] = {}
    more: Dict[str, Any] = {}

    try:
        snap = _call_with_retry(tq.get_market_snapshot, stock_code=stock, field_list=[]) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] snapshot fail %s: %s", code, exc)
        snap = {}

    try:
        more = _call_with_retry(tq.get_more_info, stock_code=stock, field_list=[]) or {}
    except Exception as exc:
        logger.debug("[TdxTQ] more_info fail %s: %s", code, exc)
        more = {}

    # snapshot 必备字段都没有就视为失败
    price = _safe_float(snap.get("Now"))
    if price is None and not more:
        return None

    pre_close = _safe_float(snap.get("LastClose"))
    change = (price - pre_close) if (price is not None and pre_close is not None) else None
    change_pct = _safe_float(more.get("ZAF"))
    if change_pct is None and change is not None and pre_close:
        change_pct = round((change / pre_close) * 100, 4)

    bare_code = stock.split(".")[0] if "." in stock else stock

    out: dict = {
        "code": bare_code,
        "name": more.get("Name") or "",
        "price": price,
        "change": change,
        "changePercent": change_pct,
        "open": _safe_float(snap.get("Open")),
        "high": _safe_float(snap.get("Max")),
        "low": _safe_float(snap.get("Min")),
        "preClose": pre_close,
        "volume": _safe_int(snap.get("Volume")),
        "amount": _safe_float(snap.get("Amount")),
        "turnoverRate": _safe_float(more.get("fHSL")),
        "volumeRatio": _safe_float(more.get("fLianB")),
        "pe_ttm": _safe_float(more.get("StaticPE_TTM")),
        "pe_dynamic": _safe_float(more.get("DynaPE")),
        "pb": _safe_float(more.get("PB_MRQ")),
        "market_cap": _safe_float(more.get("Zsz")),  # 总市值(亿)
        "float_market_cap": _safe_float(more.get("Ltsz")),  # 流通市值(亿)
        "up_limit": _safe_float(more.get("ZTPrice")),
        "down_limit": _safe_float(more.get("DTPrice")),
        "ma5": _safe_float(more.get("MA5Value")),
        "hist_high_52w": _safe_float(more.get("HisHigh")),
        "hist_low_52w": _safe_float(more.get("HisLow")),
        "dividend_yield": _safe_float(more.get("DYRatio")),
        "inside": _safe_int(snap.get("Inside")),
        "outside": _safe_int(snap.get("Outside")),
        "even_zt_count": _safe_int(more.get("EverZTCount")),
        "consecutive_up_days": _safe_int(more.get("ConZAFDateNum")),
        "fund_main_net": _safe_float(more.get("Zjl_HB")),
        "latest_report_date": _format_date(more.get("ReportDate")),
        "trade_date": _format_date(more.get("HqDate")),
        "halted": more.get("TPFlag") == "1",
        "source": "tqcenter",
    }

    # 五档盘口
    bids = _to_bid_ask(snap.get("Buyp"), _safe_float)
    bid_vols = _to_bid_ask(snap.get("Buyv"), _safe_int)
    asks = _to_bid_ask(snap.get("Sellp"), _safe_float)
    ask_vols = _to_bid_ask(snap.get("Sellv"), _safe_int)
    for i in range(5):
        out[f"bid{i+1}"] = bids[i]
        out[f"bid_vol{i+1}"] = bid_vols[i]
        out[f"ask{i+1}"] = asks[i]
        out[f"ask_vol{i+1}"] = ask_vols[i]

    return out


# ---------------------------------------------------------------------------
# 3. more_info 88 字段透传
# ---------------------------------------------------------------------------

def get_more_info(code: str) -> Optional[dict]:
    tq = get_tq()
    if tq is None:
        return None
    stock = _normalize_code(code)
    try:
        info = _call_with_retry(tq.get_more_info, stock_code=stock, field_list=[])
    except Exception as exc:
        logger.warning("[TdxTQ] get_more_info fail %s: %s", code, exc)
        return None
    if not info:
        return None
    return dict(info)


# ---------------------------------------------------------------------------
# 4. 板块归属
# ---------------------------------------------------------------------------

def get_relation(code: str) -> list[dict]:
    """股票所属板块。返回 list[{block_code, block_name, block_type, gp_num}]。

    block_type 取值：行业 / 概念 / 风格 / 地区 / 指数。
    """
    tq = get_tq()
    if tq is None:
        return []
    stock = _normalize_code(code)
    try:
        rel = _call_with_retry(tq.get_relation, stock_code=stock)
    except Exception as exc:
        logger.warning("[TdxTQ] get_relation fail %s: %s", code, exc)
        return []
    if not rel:
        return []
    out: list[dict] = []
    for item in rel:
        if not isinstance(item, dict):
            continue
        out.append({
            "block_code": str(item.get("BlockCode", "") or ""),
            "block_name": str(item.get("BlockName", "") or ""),
            "block_type": str(item.get("BlockType", "") or ""),
            "gp_num": _safe_int(item.get("GPNume")),
        })
    return out


# ---------------------------------------------------------------------------
# 5. 分红送配
# ---------------------------------------------------------------------------

def get_divid_factors(code: str, start_time: str = "", end_time: str = "") -> list[dict]:
    """除权除息 / 送股 / 配股 历史。

    每条 dict：date / type / bonus(派息) / allot_price / share_bonus / allotment。
    Type=1 除权除息, 11 扩缩股, 15 重新调整。
    """
    tq = get_tq()
    if tq is None:
        return []
    stock = _normalize_code(code)
    try:
        df = _call_with_retry(tq.get_divid_factors,
                              stock_code=stock,
                              start_time=start_time,
                              end_time=end_time)
    except Exception as exc:
        logger.warning("[TdxTQ] divid_factors fail %s: %s", code, exc)
        return []
    if df is None or getattr(df, "empty", True):
        return []
    rows: list[dict] = []
    try:
        for ts, row in df.iterrows():
            rows.append({
                "date": _format_date(ts),
                "type": _safe_int(row.get("Type")),
                "bonus": _safe_float(row.get("Bonus")),
                "allot_price": _safe_float(row.get("AllotPrice")) or _safe_float(row.get("AlloPrice")),
                "share_bonus": _safe_float(row.get("ShareBonus")),
                "allotment": _safe_float(row.get("Allotment")),
            })
    except Exception as exc:
        logger.warning("[TdxTQ] divid_factors parse %s: %s", code, exc)
        return []
    return rows


# ---------------------------------------------------------------------------
# 6. 新股 / 新债申购
# ---------------------------------------------------------------------------

def get_ipo_info(ipo_type: int = 2, ipo_date: int = 1) -> list[dict]:
    """新股+新债申购信息。

    参数：
    - ipo_type：0 新股，1 新债，2 全部
    - ipo_date：0 今天，1 今天及以后

    返回：每条 ``{code, name, sg_code, sg_date, sg_price, max_sg, pe_issue, set_code, type}``。
    """
    tq = get_tq()
    if tq is None:
        return []
    try:
        items = _call_with_retry(tq.get_ipo_info, ipo_type=int(ipo_type), ipo_date=int(ipo_date))
    except Exception as exc:
        logger.warning("[TdxTQ] get_ipo_info fail: %s", exc)
        return []
    if not items:
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        set_code = str(item.get("SetCode", "") or item.get("setcode", "") or "")
        # 区分股票/债券：通达信文档里 SGCode 7 位 (787xxx/371xxx 等) 表示新债
        sg_code = str(item.get("SGCode", "") or "")
        is_bond = sg_code.startswith(("371", "718", "787", "072", "070", "073", "077", "082"))
        out.append({
            "code": str(item.get("code", "")),
            "name": str(item.get("name", "")),
            "sg_code": sg_code,
            "sg_date": _format_date(item.get("SGDate")),
            "sg_price": _safe_float(item.get("SGPrice")),
            "max_sg": _safe_float(item.get("MaxSG")),
            "pe_issue": _safe_float(item.get("PE_Issue")),
            "set_code": set_code,
            "type": "bond" if is_bond else "stock",
        })
    return out


# ---------------------------------------------------------------------------
# 7. 股本数据
# ---------------------------------------------------------------------------

def get_gb_info(code: str, dates: list[str]) -> list[dict]:
    """每日总股本/流通股本。

    ``dates`` 必须升序 (TDX 文档要求)，``YYYYMMDD``。返回 list[{date, total_shares,
    float_shares}]。
    """
    tq = get_tq()
    if tq is None:
        return []
    stock = _normalize_code(code)
    cleaned = [str(d).replace("-", "") for d in (dates or []) if d]
    if not cleaned:
        return []
    cleaned.sort()
    try:
        items = _call_with_retry(tq.get_gb_info,
                                 stock_code=stock,
                                 date_list=cleaned,
                                 count=len(cleaned))
    except Exception as exc:
        logger.warning("[TdxTQ] get_gb_info fail %s: %s", code, exc)
        return []
    if not items:
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append({
            "date": _format_date(item.get("Date")),
            "total_shares": _safe_float(item.get("Zgb")),  # 股
            "float_shares": _safe_float(item.get("Ltgb")),  # 股
        })
    return out


# ---------------------------------------------------------------------------
# 8. 可转债基础数据
# ---------------------------------------------------------------------------

def get_kzz_info(code: str) -> Optional[dict]:
    """单只可转债基础信息。25 字段透传 + 数值归一化。"""
    tq = get_tq()
    if tq is None:
        return None
    stock = _normalize_code(code)
    try:
        info = _call_with_retry(tq.get_kzz_info, stock_code=stock, field_list=[])
    except Exception as exc:
        logger.warning("[TdxTQ] get_kzz_info fail %s: %s", code, exc)
        return None
    if not info:
        return None
    out: dict = {
        "kzz_code": str(info.get("KZZCode", "")),
        "stock_code": str(info.get("HSCode", "")),
        "set_code": str(info.get("SetCode", "") or info.get("setcode", "")),
        "convert_price": _safe_float(info.get("ZGPrice")),
        "current_rate": _safe_float(info.get("CurRate")),
        "remain_size_wan": _safe_float(info.get("RestScope")),
        "putback_price": _safe_float(info.get("PutBack")),
        "force_redeem_price": _safe_float(info.get("ForceRedeem")),
        "convert_date": _format_date(info.get("ZGDate")),
        "end_price": _safe_float(info.get("EndPrice")),
        "end_date": _format_date(info.get("EndDate")),
        "convert_rate": _safe_float(info.get("ZGRate")),
        "real_value": _safe_float(info.get("RealValue")),
        "expire_yield": _safe_float(info.get("ExpireYield")),
        "kzz_score": str(info.get("KZZScore", "")),
        "stock_score": str(info.get("HSScore", "")),
        "redeem_date": _format_date(info.get("RedeemDate")),
        "redeem_price": _safe_float(info.get("RedeemPrice")),
        "put_date": _format_date(info.get("PutDate")),
        "put_price": _safe_float(info.get("PutPrice")),
        "convert_code": str(info.get("ZGCode", "")),
        "stock_price": _safe_float(info.get("AGPrice")),
        "kzz_price": _safe_float(info.get("KZZPrice")),
        "premium_rate": _safe_float(info.get("KZZYj")),
        "convert_value": _safe_float(info.get("ZGValue")),
    }
    return out


# ---------------------------------------------------------------------------
# 9. 一致预期 / 业绩预告 / 业绩快报 (GO 字段)
# ---------------------------------------------------------------------------

def get_gp_one_data(codes: list[str], fields: list[str]) -> dict:
    """单个数据点查询：一致预期、解禁、机构持股、业绩预告/快报、派现/募资。

    fields 形如 ``["GO1","GO2","GO3","GO5",...]``。返回 ``{code: {field: value}}``，
    value 为字符串（保留 SDK 原貌；上层选择性转 float）。
    """
    tq = get_tq()
    if tq is None:
        return {}
    stock_list = [_normalize_code(c) for c in (codes or [])]
    if not stock_list or not fields:
        return {}
    try:
        data = _call_with_retry(tq.get_gp_one_data, stock_list=stock_list, field_list=list(fields))
    except Exception as exc:
        logger.warning("[TdxTQ] get_gp_one_data fail: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# 10. 个股交易数据 (GP 字段) — 龙虎榜/融资融券/陆股通/大宗交易/涨跌停盘中
# ---------------------------------------------------------------------------

def get_gpjy_value(
    codes: list[str],
    fields: list[str],
    start_time: str = "",
    end_time: str = "",
) -> dict:
    tq = get_tq()
    if tq is None:
        return {}
    stock_list = [_normalize_code(c) for c in (codes or [])]
    if not stock_list or not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_gpjy_value,
            stock_list=stock_list,
            field_list=list(fields),
            start_time=start_time,
            end_time=end_time,
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_gpjy_value fail: %s", exc)
        return {}


def get_gpjy_value_by_date(
    codes: list[str],
    fields: list[str],
    year: int = 0,
    mmdd: int = 0,
) -> dict:
    tq = get_tq()
    if tq is None:
        return {}
    stock_list = [_normalize_code(c) for c in (codes or [])]
    if not stock_list or not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_gpjy_value_by_date,
            stock_list=stock_list,
            field_list=list(fields),
            year=int(year),
            mmdd=int(mmdd),
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_gpjy_value_by_date fail: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# 11. 板块交易数据 (BK 字段)
# ---------------------------------------------------------------------------

def get_bkjy_value(
    blocks: list[str],
    fields: list[str],
    start_time: str = "",
    end_time: str = "",
) -> dict:
    tq = get_tq()
    if tq is None:
        return {}
    if not blocks or not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_bkjy_value,
            stock_list=list(blocks),
            field_list=list(fields),
            start_time=start_time,
            end_time=end_time,
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_bkjy_value fail: %s", exc)
        return {}


def get_bkjy_value_by_date(
    blocks: list[str],
    fields: list[str],
    year: int = 0,
    mmdd: int = 0,
) -> dict:
    tq = get_tq()
    if tq is None:
        return {}
    if not blocks or not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_bkjy_value_by_date,
            stock_list=list(blocks),
            field_list=list(fields),
            year=int(year),
            mmdd=int(mmdd),
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_bkjy_value_by_date fail: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# 12. 市场交易数据 (SC 字段)
# ---------------------------------------------------------------------------

def get_scjy_value(fields: list[str], start_time: str = "", end_time: str = "") -> dict:
    tq = get_tq()
    if tq is None:
        return {}
    if not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_scjy_value,
            field_list=list(fields),
            start_time=start_time,
            end_time=end_time,
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_scjy_value fail: %s", exc)
        return {}


def get_scjy_value_by_date(fields: list[str], year: int = 0, mmdd: int = 0) -> dict:
    tq = get_tq()
    if tq is None:
        return {}
    if not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_scjy_value_by_date,
            field_list=list(fields),
            year=int(year),
            mmdd=int(mmdd),
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_scjy_value_by_date fail: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# 13. 专业财务 (FN 字段)
# ---------------------------------------------------------------------------

def get_financial_data(
    codes: list[str],
    fields: list[str],
    start_time: str = "",
    end_time: str = "",
    report_type: str = "announce_time",
) -> dict:
    """专业财务数据 (FN1-FN584)。

    需要客户端预先下载"专业财务数据包"，否则字段全部返回 ``"--"``。

    report_type: ``"announce_time"`` 按公告日期 / ``"tag_time"`` 按报告期。
    """
    tq = get_tq()
    if tq is None:
        return {}
    stock_list = [_normalize_code(c) for c in (codes or [])]
    if not stock_list or not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_financial_data,
            stock_list=stock_list,
            field_list=list(fields),
            start_time=start_time,
            end_time=end_time,
            report_type=report_type,
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_financial_data fail: %s", exc)
        return {}


def get_financial_data_by_date(
    codes: list[str],
    fields: list[str],
    year: int = 0,
    mmdd: int = 0,
) -> dict:
    """指定日期专业财务数据。

    year=0,mmdd=0 取最新；mmdd in {331,630,930,1231} 指定季度。
    """
    tq = get_tq()
    if tq is None:
        return {}
    stock_list = [_normalize_code(c) for c in (codes or [])]
    if not stock_list or not fields:
        return {}
    try:
        return _call_with_retry(
            tq.get_financial_data_by_date,
            stock_list=stock_list,
            field_list=list(fields),
            year=int(year),
            mmdd=int(mmdd),
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] get_financial_data_by_date fail: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# 14. 股票列表 / 板块列表 / 板块成份股
# ---------------------------------------------------------------------------

def get_stock_list(market: str = "5", list_type: int = 1) -> list[dict]:
    """市场代码 ``5`` 全 A，``23`` HS300，``24`` ZZ500，``25`` ZZ1000，``28`` A500，
    ``31`` ETF，``32`` 可转债，``51`` 创业板，``52`` 科创板，``53`` 北交所，
    ``16/17/18`` 研究行业一/二/三级。详见 Dict.md。
    """
    tq = get_tq()
    if tq is None:
        return []
    try:
        result = _call_with_retry(tq.get_stock_list, market=str(market), list_type=int(list_type))
    except Exception as exc:
        logger.warning("[TdxTQ] get_stock_list fail %s: %s", market, exc)
        return []
    if not result:
        return []
    if list_type == 0:
        # 仅代码
        return [{"code": str(c), "full_code": str(c)} for c in result]
    out: list[dict] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        full = str(item.get("Code", ""))
        out.append({
            "code": full.split(".")[0] if "." in full else full,
            "full_code": full,
            "name": str(item.get("Name", "")),
        })
    return out


def get_sector_list(list_type: int = 1) -> list[dict]:
    tq = get_tq()
    if tq is None:
        return []
    try:
        result = _call_with_retry(tq.get_sector_list, list_type=int(list_type))
    except Exception as exc:
        logger.warning("[TdxTQ] get_sector_list fail: %s", exc)
        return []
    if not result:
        return []
    if list_type == 0:
        return [{"block_code": str(c)} for c in result]
    return [
        {
            "block_code": str(item.get("Code", "")),
            "block_name": str(item.get("Name", "")),
        }
        for item in result if isinstance(item, dict)
    ]


def get_stock_info(code: str) -> Optional[dict]:
    """``tq.get_stock_info`` 透传：63 字段含基础财务（J_yysy 营收 / J_jly 净利润 /
    J_jyl ROE / J_mgsy EPS / J_mgjzc BVPS 等，单位多为万元）。"""
    tq = get_tq()
    if tq is None:
        return None
    stock = _normalize_code(code)
    try:
        info = _call_with_retry(tq.get_stock_info, stock_code=stock, field_list=[])
    except Exception as exc:
        logger.warning("[TdxTQ] get_stock_info fail %s: %s", code, exc)
        return None
    if not info:
        return None
    return dict(info)


def get_stock_list_in_sector(
    block_code: str,
    block_type: int = 0,
    list_type: int = 0,
) -> list[Any]:
    tq = get_tq()
    if tq is None:
        return []
    if not block_code:
        return []
    try:
        return _call_with_retry(
            tq.get_stock_list_in_sector,
            block_code=str(block_code),
            block_type=int(block_type),
            list_type=int(list_type),
        ) or []
    except Exception as exc:
        logger.warning("[TdxTQ] get_stock_list_in_sector fail %s: %s", block_code, exc)
        return []


# ---------------------------------------------------------------------------
# 15. 交易日历
# ---------------------------------------------------------------------------

def get_trading_dates(
    start_time: str = "",
    end_time: str = "",
    count: int = -1,
) -> list[str]:
    """A 股交易日列表，``YYYYMMDD`` 升序。需客户端下载上证指数 999999 盘后数据。"""
    tq = get_tq()
    if tq is None:
        return []
    try:
        dates = _call_with_retry(
            tq.get_trading_dates,
            market="SH",
            start_time=start_time,
            end_time=end_time,
            count=int(count),
        )
    except Exception as exc:
        logger.warning("[TdxTQ] get_trading_dates fail: %s", exc)
        return []
    if not isinstance(dates, list):
        return []
    return [str(d) for d in dates if d]


# ---------------------------------------------------------------------------
# 16. 公式互通 (formula_*)
# ---------------------------------------------------------------------------

def formula_zb_batch(
    formula_name: str,
    formula_arg: str,
    codes: list[str],
    period: str = "1d",
    count: int = 30,
    return_count: int = 1,
    return_date: bool = False,
    dividend_type: int = 1,
) -> dict:
    """批量调用通达信指标公式 (formula_process_mul_zb)。

    返回 ``{code: {sub_name: [values]}, "ErrorId": "0"}``。
    """
    tq = get_tq()
    if tq is None:
        return {}
    stock_list = [_normalize_code(c) for c in (codes or [])]
    if not stock_list or not formula_name:
        return {}
    try:
        return _call_with_retry(
            tq.formula_process_mul_zb,
            formula_name=str(formula_name),
            formula_arg=str(formula_arg or ""),
            return_count=int(return_count),
            return_date=bool(return_date),
            stock_list=stock_list,
            stock_period=str(period),
            count=int(count),
            dividend_type=int(dividend_type),
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] formula_process_mul_zb fail %s: %s", formula_name, exc)
        return {}


def formula_xg_batch(
    formula_name: str,
    formula_arg: str,
    codes: list[str],
    period: str = "1d",
    count: int = 30,
    return_count: int = 1,
    return_date: bool = False,
    dividend_type: int = 1,
    start_time: str = "",
    end_time: str = "",
) -> dict:
    """批量条件选股 (formula_process_mul_xg)。"""
    tq = get_tq()
    if tq is None:
        return {}
    stock_list = [_normalize_code(c) for c in (codes or [])]
    if not stock_list or not formula_name:
        return {}
    try:
        return _call_with_retry(
            tq.formula_process_mul_xg,
            formula_name=str(formula_name),
            formula_arg=str(formula_arg or ""),
            return_count=int(return_count),
            return_date=bool(return_date),
            start_time=start_time,
            end_time=end_time,
            stock_list=stock_list,
            stock_period=str(period),
            count=int(count),
            dividend_type=int(dividend_type),
        ) or {}
    except Exception as exc:
        logger.warning("[TdxTQ] formula_process_mul_xg fail %s: %s", formula_name, exc)
        return {}


# ---------------------------------------------------------------------------
# 17. download_file (10 大股东 / ETF 申赎 / 舆情 / 综合信息)
# ---------------------------------------------------------------------------

def download_tdx_file(
    code: str = "",
    down_time: str = "",
    down_type: int = 3,
) -> dict:
    """下载文件到 ``$TDX_DOWNLOAD_DIR`` (默认 ``${TDX_INSTALL_DIR}/PYPlugins/data``)。

    down_type:
    - 1 = 10 大股东 (down_time 仅取年份)
    - 2 = ETF 申赎清单 (down_time 取到日期)
    - 3 = 最近舆情 (其余参数无效)
    - 4 = 综合信息文件 (其余参数无效)

    返回 ``{ok, msg, raw}``。
    """
    tq = get_tq()
    if tq is None:
        return {"ok": False, "msg": "tqcenter unavailable", "raw": ""}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            raw = tq.download_file(stock_code=str(code), down_time=str(down_time),
                                   down_type=int(down_type))
    except Exception as exc:
        logger.warning("[TdxTQ] download_file fail type=%s: %s", down_type, exc)
        return {"ok": False, "msg": str(exc), "raw": ""}
    raw_str = str(raw or "")
    ok = '"ErrorId":"0"' in raw_str or '"ErrorId": "0"' in raw_str
    return {"ok": ok, "msg": raw_str, "raw": raw_str}


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------

def status() -> dict:
    """供运维 / 诊断使用。"""
    return {
        "initialized": _tq_initialized,
        "tq_available": _tq is not None,
        "pyplugins": _resolve_pyplugins_path(),
        "required": _is_required(),
    }
