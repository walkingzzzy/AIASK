"""
TdxQuant 行情订阅与缓存管理模块 (Phase 4)

封装通达信行情订阅管理、数据缓存刷新、自定义K线公式计算：
- 行情订阅管理：订阅/取消订阅/查询已订阅列表
- 数据缓存刷新：刷新行情缓存/K线缓存
- 自定义K线公式计算：用户传入自定义K线数据进行公式计算
"""

from ..data_source import data_source
import json
import os
import sys


def _build_official_env_diag(tq) -> dict:
    """官方环境前置条件诊断（依据 docs/tdx-quant/faq.md 与 overview/install-tdx.md）。"""
    cwd = os.getcwd()
    user_path_in_sys = any("PYPlugins" in p and "user" in p for p in sys.path)
    cwd_is_user = ("PYPlugins" in cwd and "user" in cwd)

    return {
        "official_requirements": {
            "client_started_and_logged_in": "需先启动并登录通达信客户端（install-tdx.md, faq.md）",
            "initialize_required": "调用其他 tq API 前需先 initialize（api/common/initialize.md）",
            "pyplugins_user_required": "建议在 PYPlugins/user 目录运行，或在 import 前 append 该目录（faq.md）",
        },
        "runtime_observation": {
            "cwd": cwd,
            "cwd_like_pyplugins_user": cwd_is_user,
            "sys_path_has_pyplugins_user": user_path_in_sys,
            "has_initialize": hasattr(tq, "initialize") and callable(getattr(tq, "initialize", None)),
        },
        "suggestions": [
            "确认通达信客户端已启动并登录",
            "优先在通达信安装目录/PYPlugins/user 作为工作目录运行",
            "若脚本不在 user 目录，需在 import tqcenter 前追加 PYPlugins/user 到 sys.path",
            "确认客户端已下载盘后数据，避免取数为空",
        ],
    }


def _official_subscribe_callback(datas):
    """官方订阅回调格式：on_data(datas)（依据 api/common/subscribe_hq.md）。"""
    try:
        if isinstance(datas, str):
            json.loads(datas)
    except Exception:
        # 回调中不抛异常，避免影响订阅通道
        pass
    return None


# 兼容不同版本回调函数命名习惯
_on_data = _official_subscribe_callback
_on_subscribe_data = _official_subscribe_callback
_on_hq_data = _official_subscribe_callback


def _formula_guidance_payload(missing: list[str] | None = None) -> dict:
    """构造公式 API 缺失时的统一引导信息。"""
    missing = missing or []
    return {
        "missing_methods": missing,
        "solutions": [
            "方案A（推荐）：升级到支持公式 API 的 TdxQuant/tqcenter 版本（需包含 formula_set_data_info、formula_zb）",
            "方案B：在通达信客户端 公式管理器 手动执行对应公式",
        ],
        "alternatives": [
            "使用 tdx_calculate_macd / tdx_calculate_kdj / tdx_calculate_rsi / tdx_calculate_boll（Python 回退可用）",
            "使用 calculate_technical_indicators（AkShare 技术指标计算）",
            "使用 get_kline + 本地 TA 库（如 pandas-ta）自行计算",
        ],
        "checks": [
            "确认客户端已启动并登录",
            "确认 initialize 成功",
            "确认 hasattr(tq, 'formula_zb') 和 hasattr(tq, 'formula_set_data_info') 均为 True",
        ],
    }



def tdx_manage_subscription(
    action: str,
    stock_codes: list[str] = None,
) -> dict:
    """
    [TDX] 行情订阅管理

    官方依据：
    - subscribe_hq: docs/tdx-quant/api/common/subscribe_hq.md
      签名 subscribe_hq(stock_list, callback)，回调格式 on_data(datas)
    - unsubscribe_hq: docs/tdx-quant/api/common/unsubscribe_hq.md
    - get_subscribe_hq_stock_list: docs/tdx-quant/api/common/get_subscribe_hq_stock_list.md
    """
    action = action.lower().strip()
    if action not in ("subscribe", "unsubscribe", "list"):
        return {
            "success": False,
            "error": f"未知的 action: {action}，可选 subscribe/unsubscribe/list",
            "capability": "invalid_action",
        }

    if action in ("subscribe", "unsubscribe") and not stock_codes:
        return {"success": False, "error": "stock_codes 不能为空", "capability": "invalid_params"}

    if not data_source.is_tdx_available():
        return {
            "success": False,
            "error": "TdxQuant 不可用，请确保通达信客户端已启动并登录",
            "capability": "tdx_not_available",
            "env_diag": _build_official_env_diag(None),
            "guidance": _formula_guidance_payload(["tdx_runtime"]),
        }

    tq = None
    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {
                "success": False,
                "error": "TdxQuant 初始化失败",
                "capability": "tdx_init_failed",
                "env_diag": _build_official_env_diag(None),
                "guidance": _formula_guidance_payload(["tdx_initialize"]),
            }

        has_subscribe = hasattr(tq, "subscribe_hq") and callable(getattr(tq, "subscribe_hq", None))
        has_unsubscribe = hasattr(tq, "unsubscribe_hq") and callable(getattr(tq, "unsubscribe_hq", None))
        has_list = hasattr(tq, "get_subscribe_hq_stock_list") and callable(getattr(tq, "get_subscribe_hq_stock_list", None))

        if action == "list":
            # 官方有 get_subscribe_hq_stock_list；若当前环境缺失该能力，按要求稳定返回空数组
            if not has_list:
                return {
                    "success": True,
                    "data": [],
                    "source": "tdxquant",
                    "capability": "list_not_supported",
                    "message": "当前 TdxQuant 版本不支持查询订阅列表，返回空数组",
                }

            try:
                result = tq.get_subscribe_hq_stock_list()
                return {
                    "success": True,
                    "data": result if isinstance(result, list) else (result or []),
                    "source": "tdxquant",
                    "capability": "supported",
                }
            except Exception as e:
                return {
                    "success": True,
                    "data": [],
                    "source": "tdxquant",
                    "capability": "list_fallback_empty",
                    "message": f"获取订阅列表失败，已降级为空数组: {e}",
                }

        # subscribe / unsubscribe
        tdx_codes = [data_source._convert_to_tdx_code(c) for c in stock_codes]
        env_diag = _build_official_env_diag(tq)

        if action == "subscribe":
            if not has_subscribe:
                return {
                    "success": False,
                    "error": "当前 TdxQuant 版本不支持 subscribe_hq",
                    "capability": "subscribe_not_supported",
                    "env_diag": env_diag,
                }

            result = None
            errors = []

            # 兼容路径 1：优先 data_source 封装，传入官方 on_data(datas) 形态回调
            if hasattr(data_source, "subscribe_hq_tdxquant") and callable(getattr(data_source, "subscribe_hq_tdxquant", None)):
                try:
                    wrapped = data_source.subscribe_hq_tdxquant(stock_codes, callback=_on_data)
                    if isinstance(wrapped, dict) and wrapped.get("success"):
                        wrapped.setdefault("source", "tdxquant")
                        wrapped.setdefault("capability", "supported")
                        wrapped.setdefault("mode", "data_source_wrapper")
                        return wrapped
                    errors.append(f"wrapper_failed: {wrapped}")
                except Exception as e:
                    errors.append(f"wrapper_exception: {e}")

            # 兼容路径 2：严格按官方签名优先，再回退旧签名
            subscribe_attempts = [
                ("official_kw_on_data", lambda: tq.subscribe_hq(stock_list=tdx_codes, callback=_on_data)),
                ("official_kw_on_subscribe_data", lambda: tq.subscribe_hq(stock_list=tdx_codes, callback=_on_subscribe_data)),
                ("official_kw_on_hq_data", lambda: tq.subscribe_hq(stock_list=tdx_codes, callback=_on_hq_data)),
                ("positional_with_on_data", lambda: tq.subscribe_hq(tdx_codes, _on_data)),
                ("stock_list_only_legacy", lambda: tq.subscribe_hq(stock_list=tdx_codes)),
            ]

            for method_name, subscribe_call in subscribe_attempts:
                try:
                    result = subscribe_call()
                    break
                except Exception as e:
                    errors.append(f"{method_name}: {e}")

            if result is None:
                return {
                    "success": False,
                    "error": "订阅失败，subscribe_hq 兼容调用均未成功",
                    "capability": "subscribe_call_failed",
                    "details": errors,
                    "env_diag": env_diag,
                }

            if isinstance(result, dict) and result.get("ErrorId") and result["ErrorId"] != "0":
                return {
                    "success": False,
                    "error": result.get("Error", result.get("Msg", "订阅失败")),
                    "capability": "subscribe_rejected",
                    "data": result,
                    "env_diag": env_diag,
                }

            return {
                "success": True,
                "message": "订阅成功",
                "data": result,
                "source": "tdxquant",
                "capability": "supported",
                "mode": "official_callback",
            }

        if not has_unsubscribe:
            return {
                "success": False,
                "error": "当前 TdxQuant 版本不支持 unsubscribe_hq",
                "capability": "unsubscribe_not_supported",
                "env_diag": env_diag,
            }

        unsubscribe_attempts = [
            ("stock_list_kw", lambda: tq.unsubscribe_hq(stock_list=tdx_codes)),
            ("positional_only", lambda: tq.unsubscribe_hq(tdx_codes)),
        ]

        result = None
        errors = []
        for method_name, unsubscribe_call in unsubscribe_attempts:
            try:
                result = unsubscribe_call()
                break
            except Exception as e:
                errors.append(f"{method_name}: {e}")

        if result is None:
            return {
                "success": False,
                "error": "取消订阅失败，unsubscribe_hq 兼容调用均未成功",
                "capability": "unsubscribe_call_failed",
                "details": errors,
                "env_diag": env_diag,
            }

        if isinstance(result, dict) and result.get("ErrorId") and result["ErrorId"] != "0":
            return {
                "success": False,
                "error": result.get("Error", "取消订阅失败"),
                "capability": "unsubscribe_rejected",
                "data": result,
                "env_diag": env_diag,
            }

        return {
            "success": True,
            "message": "取消订阅成功",
            "data": result,
            "source": "tdxquant",
            "capability": "supported",
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"操作异常: {e}",
            "capability": "runtime_exception",
            "env_diag": _build_official_env_diag(tq) if tq is not None else _build_official_env_diag(None),
        }



def tdx_refresh_data(
    refresh_type: str = "all",
    market: str = "AG",
    force: bool = False,
    stock_codes: list[str] = None,
    period: str = "1d",
) -> dict:
    """
    [TDX] 刷新数据缓存

    刷新通达信行情缓存或K线缓存。行情缓存包括最新 snapshot 和K线数据；
    K线缓存可针对指定股票和周期定向下载历史K线。

    Args:
        refresh_type (str, optional): 刷新类型，可选 "cache"/"kline"/"all"，默认 "all"
            - cache: 刷新行情缓存（snapshot + K线）
            - kline: 刷新指定股票的K线缓存
            - all: 同时刷新行情缓存和K线缓存
        market (str, optional): 市场类型（仅 cache 模式），默认 "AG"
            可选: "AG"(A股)/"HK"(港股)/"US"(美股)/"QH"(期货)/"QQ"(期权)/"NQ"(新三板)/"ZZ"(中证国证指数)
        force (bool, optional): 是否强制刷新（仅 cache 模式），默认 False
            False 时距上次刷新不足10分钟则不刷新
        stock_codes (list[str], optional): 股票代码列表（仅 kline 模式），如 ["600519", "000001"]
        period (str, optional): K线周期（仅 kline 模式），默认 "1d"
            可选: "1d"(日线)/"1m"(1分钟)/"5m"(5分钟)

    Returns:
        dict: {"success": bool, "data": dict, "source": "tdxquant"}
        data 包含各刷新操作的返回结果

    Errors:
        - refresh_type 不在可选范围时返回 success=false
        - kline 模式下 stock_codes 为空返回 success=false
        - TdxQuant 不可用时返回 success=false

    Examples:
        tdx_refresh_data("cache")
        tdx_refresh_data("kline", stock_codes=["600519"], period="1d")
        tdx_refresh_data("all", stock_codes=["600519"])
    """
    refresh_type = refresh_type.lower().strip()
    if refresh_type not in ("cache", "kline", "all"):
        return {"success": False, "error": f"未知的 refresh_type: {refresh_type}，可选 cache/kline/all"}

    if refresh_type in ("kline", "all") and not stock_codes:
        if refresh_type == "kline":
            return {"success": False, "error": "kline 模式下 stock_codes 不能为空"}
        # all 模式下 stock_codes 为空时只刷新 cache
        refresh_type = "cache"

    if not data_source.is_tdx_available():
        return {"success": False, "error": "TdxQuant 不可用，请确保通达信客户端已启动"}

    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {"success": False, "error": "TdxQuant 初始化失败"}

        results = {}

        if refresh_type in ("cache", "all"):
            # 兼容不同版本 TdxQuant 的 refresh_cache 签名差异
            cache_attempts = [
                ("market+force_pos", lambda: tq.refresh_cache(market, force)),
                ("market+force_kw", lambda: tq.refresh_cache(market=market, force=force)),
                ("force_kw", lambda: tq.refresh_cache(force=force)),
                ("market_kw", lambda: tq.refresh_cache(market=market)),
                ("no_args", lambda: tq.refresh_cache()),
            ]

            cache_result = None
            cache_errors = []
            for method_name, cache_call in cache_attempts:
                try:
                    cache_result = cache_call()
                    break
                except Exception as e:
                    cache_errors.append(f"{method_name}: {e}")
                    continue

            if cache_result is None:
                return {
                    "success": False,
                    "error": "刷新行情缓存失败，refresh_cache 多签名兼容均未成功: " + " | ".join(cache_errors),
                    "data": results,
                }

            results["cache"] = cache_result
            if isinstance(cache_result, dict) and cache_result.get("ErrorId") and cache_result["ErrorId"] != "0":
                return {"success": False, "error": cache_result.get("Error", "刷新行情缓存失败"), "data": results}

        if refresh_type in ("kline", "all") and stock_codes:
            tdx_codes = [data_source._convert_to_tdx_code(c) for c in stock_codes]
            kline_result = tq.refresh_kline(stock_list=tdx_codes, period=period)
            results["kline"] = kline_result
            if isinstance(kline_result, dict) and kline_result.get("ErrorId") and kline_result["ErrorId"] != "0":
                return {"success": False, "error": kline_result.get("Error", "刷新K线缓存失败"), "data": results}

        return {"success": True, "data": results, "source": "tdxquant"}
    except Exception as e:
        return {"success": False, "error": f"刷新异常: {e}"}


def tdx_custom_formula_calc(
    stock_code: str,
    kline_data: list[dict] | None = None,
    formula_name: str = "MACD",
    formula_args: str = "",
    period: str = "1d",
    dividend_type: int = 0,
) -> dict:
    """
    [TDX] 自定义K线公式计算

    官方依据：
    - docs/tdx-quant/api/formula/formula_set_data_info.md
    - docs/tdx-quant/api/formula/formula_zb.md
    - docs/tdx-quant/api/formula/formula_format_data.md
    - docs/tdx-quant/api/formula/formula_set_data.md

    执行优先级（按官方推荐链路）：
    1) 无 kline_data: formula_set_data_info -> formula_zb
    2) 有 kline_data: formula_format_data -> formula_set_data -> formula_zb
    3) 若缺少 formula_format_data 且传入 kline_data，返回 custom_kline_not_supported

    ⚠️ 环境要求：当前 TdxQuant 需支持公式 API。
    检测方法：hasattr(tq, 'formula_zb') 和 hasattr(tq, 'formula_set_data_info')。

    如当前环境不支持，请：
    - 方案A（推荐）：升级到支持公式 API 的 TdxQuant/tqcenter 版本；
    - 方案B：使用通达信客户端公式管理器手动计算；
    - 方案C：改用 tdx_calculate_macd / tdx_calculate_kdj 等支持 Python 回退的工具。
    """
    if not stock_code:
        return {"success": False, "error": "stock_code 不能为空", "capability": "invalid_params"}

    if not data_source.is_tdx_available():
        return {
            "success": False,
            "error": "TdxQuant 不可用，请确保通达信客户端已启动并登录",
            "capability": "tdx_not_available",
            "env_diag": _build_official_env_diag(None),
            "guidance": _formula_guidance_payload(["tdx_runtime"]),
        }

    tq = None
    try:
        tq = data_source.get_tdxquant()
        if tq is None:
            return {
                "success": False,
                "error": "TdxQuant 初始化失败",
                "capability": "tdx_init_failed",
                "env_diag": _build_official_env_diag(None),
                "guidance": _formula_guidance_payload(["tdx_initialize"]),
            }

        env_diag = _build_official_env_diag(tq)
        tdx_code = data_source._convert_to_tdx_code(stock_code)
        has_format_data = hasattr(tq, "formula_format_data") and callable(getattr(tq, "formula_format_data", None))
        has_set_data_info = hasattr(tq, "formula_set_data_info") and callable(getattr(tq, "formula_set_data_info", None))
        has_set_data = hasattr(tq, "formula_set_data") and callable(getattr(tq, "formula_set_data", None))
        has_formula_zb = hasattr(tq, "formula_zb") and callable(getattr(tq, "formula_zb", None))

        # 方案2-场景4：缺少 format_data + 用户传入自定义K线 => 明确能力错误
        if not has_format_data and kline_data is not None:
            return {
                "success": False,
                "error": (
                    "当前 TdxQuant 版本不支持自定义K线注入（缺少 formula_format_data）。"
                    "请升级 TdxQuant 或移除 kline_data 后使用内置K线计算。"
                ),
                "capability": "custom_kline_not_supported",
                "env_diag": env_diag,
                "guidance": _formula_guidance_payload(["formula_format_data"]),
            }

        if not has_formula_zb:
            return {
                "success": False,
                "error": "当前 TdxQuant 版本不支持 formula_zb，无法执行公式计算",
                "capability": "formula_zb_not_supported",
                "env_diag": env_diag,
                "guidance": _formula_guidance_payload(["formula_zb"]),
            }

        period_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "60m": "1h",
            "1h": "1h",
            "1d": "1d",
            "daily": "1d",
            "1w": "1w",
            "weekly": "1w",
            "1mo": "1M",
            "monthly": "1M",
        }
        tdx_period = period_map.get(period.lower(), "1d")

        # 官方主链路：formula_set_data_info -> formula_zb
        if not kline_data:
            if not has_set_data_info:
                return {
                    "success": False,
                    "error": "当前 TdxQuant 版本不支持 formula_set_data_info，无法按官方主链路执行",
                    "capability": "formula_set_data_info_not_supported",
                    "env_diag": env_diag,
                    "guidance": _formula_guidance_payload(["formula_set_data_info"]),
                }

            set_result = tq.formula_set_data_info(
                stock_code=tdx_code,
                stock_period=tdx_period,
                count=120,
                dividend_type=dividend_type,
            )
            if isinstance(set_result, dict) and set_result.get("ErrorId") and set_result["ErrorId"] != "0":
                return {
                    "success": False,
                    "error": set_result.get("Error", "设置公式数据失败"),
                    "capability": "formula_set_data_info_failed",
                    "data": set_result,
                    "env_diag": env_diag,
                }

            calc_result = tq.formula_zb(formula_name=formula_name, formula_arg=formula_args)
            if isinstance(calc_result, dict) and calc_result.get("ErrorId") and calc_result["ErrorId"] != "0":
                return {
                    "success": False,
                    "error": calc_result.get("Error", "公式计算失败"),
                    "capability": "formula_calc_failed",
                    "data": calc_result,
                    "env_diag": env_diag,
                }

            data = calc_result.get("Data", calc_result) if isinstance(calc_result, dict) else calc_result
            return {
                "success": True,
                "data": data,
                "source": "tdxquant",
                "mode": "official_formula_set_data_info_then_formula_zb",
                "capability": "supported",
            }

        # 自定义K线链路：formula_format_data -> formula_set_data -> formula_zb
        if not has_set_data:
            return {
                "success": False,
                "error": "当前 TdxQuant 版本不支持 formula_set_data，无法注入公式数据",
                "capability": "formula_set_data_not_supported",
                "env_diag": env_diag,
                "guidance": _formula_guidance_payload(["formula_set_data"]),
            }

        normalized_klines = []
        for item in kline_data:
            date_val = item.get("Date") or item.get("date") or ""
            open_val = item.get("Open", item.get("open"))
            high_val = item.get("High", item.get("high"))
            low_val = item.get("Low", item.get("low"))
            close_val = item.get("Close", item.get("close"))
            volume_val = item.get("Volume", item.get("volume", 0))
            amount_val = item.get("Amount", item.get("amount", 0))

            if close_val is None:
                continue

            normalized_klines.append(
                {
                    "Date": str(date_val),
                    "Open": float(open_val) if open_val is not None else float(close_val),
                    "High": float(high_val) if high_val is not None else float(close_val),
                    "Low": float(low_val) if low_val is not None else float(close_val),
                    "Close": float(close_val),
                    "Volume": float(volume_val or 0),
                    "Amount": float(amount_val or 0),
                }
            )

        if not normalized_klines:
            return {
                "success": False,
                "error": "K线数据为空或字段不完整，无法执行公式计算",
                "capability": "invalid_kline_data",
                "env_diag": env_diag,
            }

        raw_data = {tdx_code: normalized_klines}
        try:
            formatted = tq.formula_format_data(data_dict=raw_data)
        except TypeError:
            # 兼容部分版本仅支持位置参数
            formatted = tq.formula_format_data(raw_data)

        if isinstance(formatted, dict) and formatted.get("ErrorId") and formatted["ErrorId"] != "0":
            return {
                "success": False,
                "error": formatted.get("Error", "格式化K线数据失败"),
                "capability": "format_kline_failed",
                "data": formatted,
                "env_diag": env_diag,
            }

        formatted_list = formatted.get(tdx_code, []) if isinstance(formatted, dict) else []
        if not formatted_list and isinstance(formatted, list):
            formatted_list = formatted
        if not formatted_list:
            return {
                "success": False,
                "error": "格式化K线数据返回为空",
                "capability": "empty_formatted_kline",
                "env_diag": env_diag,
            }

        set_result = tq.formula_set_data(
            stock_code=tdx_code,
            stock_period=tdx_period,
            stock_data=formatted_list,
            count=len(formatted_list),
            dividend_type=dividend_type,
        )

        if isinstance(set_result, dict) and set_result.get("ErrorId") and set_result["ErrorId"] != "0":
            return {
                "success": False,
                "error": set_result.get("Error", "设置公式数据失败"),
                "capability": "formula_set_data_failed",
                "data": set_result,
                "env_diag": env_diag,
            }

        calc_result = tq.formula_zb(formula_name=formula_name, formula_arg=formula_args)
        if isinstance(calc_result, dict) and calc_result.get("ErrorId") and calc_result["ErrorId"] != "0":
            return {
                "success": False,
                "error": calc_result.get("Error", "公式计算失败"),
                "capability": "formula_calc_failed",
                "data": calc_result,
                "env_diag": env_diag,
            }

        data = calc_result.get("Data", calc_result) if isinstance(calc_result, dict) else calc_result
        return {
            "success": True,
            "data": data,
            "source": "tdxquant",
            "mode": "official_custom_kline_formula_chain",
            "capability": "supported",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"计算异常: {e}",
            "capability": "runtime_exception",
            "env_diag": _build_official_env_diag(tq) if tq is not None else _build_official_env_diag(None),
        }



def register(mcp):
    """注册 TDX 行情订阅与缓存管理工具"""
    mcp.tool()(tdx_manage_subscription)
    mcp.tool()(tdx_refresh_data)
    mcp.tool()(tdx_custom_formula_calc)
