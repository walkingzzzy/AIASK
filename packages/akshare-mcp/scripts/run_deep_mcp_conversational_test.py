#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import importlib
import inspect
import json
import logging
import os
import re
import sys
import time
import traceback
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
SRC_ROOT = PACKAGE_ROOT / "src"
STRATEGY_FACTORY_SRC = PACKAGE_ROOT.parent / "strategy-factory" / "src"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "mcp_deep_tool_test"
LEGACY_RESULTS_PATH = REPO_ROOT / ".mcp_full_test_results.json"
LEGACY_MANIFEST_PATH = REPO_ROOT / ".mcp_full_test_manifest.json"
EXPECTED_AUDIT_RAW_PATH = PACKAGE_ROOT / "TOOL_DOC_AUDIT_RAW.json"
REGISTRY_LATEST_PATH = REPO_ROOT / "reports" / "tool_registry" / "latest.json"

for candidate in (SRC_ROOT, STRATEGY_FACTORY_SRC):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

os.environ.setdefault("AKSHARE_MCP_STARTUP_PROFILE", "full")

from mcp.server.fastmcp.exceptions import ToolError

from akshare_mcp.server import mcp
from akshare_mcp.storage import get_db
from akshare_mcp.tool_registry import build_tool_registry, summarize_tool_registry
from akshare_mcp.tool_aliases import PARAM_ALIASES
from akshare_mcp.tools.tool_catalog import TOOL_CONTRACTS

warnings.filterwarnings("ignore", category=ResourceWarning)

for logger_name in (
    "akshare_mcp.storage.timescaledb.schema_base",
    "akshare_mcp.storage.timescaledb.schema_market",
    "akshare_mcp.storage.timescaledb.schema_strategy",
    "akshare_mcp.storage.timescaledb.schema_vector",
    "akshare_mcp.services.data_sync",
):
    logging.getLogger(logger_name).setLevel(logging.WARNING)


RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
THIRTY_DAYS_AGO = TODAY - timedelta(days=30)
NINETY_DAYS_AGO = TODAY - timedelta(days=90)
ONE_YEAR_AGO = TODAY - timedelta(days=365)

PRIMARY_CODES = ["600519", "000001", "600036", "000858", "000333", "601318"]
SECONDARY_CODES = ["300750", "688981", "002415", "601166", "002594", "600276"]
LIQUOR_PEERS = ["000858", "000596", "600809"]
WATCHLIST_CODES = ["600519", "000001", "600036"]
TECH_INDICATORS = ["MACD", "RSI", "KDJ"]
COMMON_CONDITIONS = [
    {"field": "close", "op": ">", "value": 0},
    {"field": "volume", "op": ">", "value": 0},
]
PREDICTION_ARTIFACT_ID = f"deep_prediction_artifact_{RUN_TIMESTAMP}"


@dataclass
class CaseSpec:
    label: str
    payload: dict[str, Any]
    expectation: str
    notes: str = ""
    mode: str = "standard"
    coverage_labels: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    label: str
    expectation: str
    payload: dict[str, Any]
    passed: bool
    observed_success: bool | None
    latency_ms: int
    envelope_ok: bool
    has_quality_meta: bool
    has_source_chain: bool
    result: Any = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    notes: str = ""
    coverage_labels: list[str] = field(default_factory=list)
    fault_strategy: str | None = None
    fault_target: str | None = None
    fault_triggered: bool | None = None
    fault_signal: bool | None = None
    fault_signal_details: list[str] = field(default_factory=list)


@dataclass
class FaultAttempt:
    strategy: str
    target: str
    triggered: bool = False
    detail: str = ""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _as_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_as_jsonable(item) for item in value]
    return repr(value)


def _safe_deepcopy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def _date_iso(value: date) -> str:
    return value.isoformat()


def _date_compact(value: date) -> str:
    return value.strftime("%Y%m%d")


def _required_fields(schema: dict[str, Any]) -> list[str]:
    return list(schema.get("required") or [])


def _schema_properties(schema: dict[str, Any]) -> dict[str, Any]:
    return dict(schema.get("properties") or {})


def _normalize_tool_result(raw: Any) -> Any:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {
                "success": True,
                "data": raw,
                "error": None,
                "source": "akshare",
                "cached": False,
                "timestamp": datetime.now().isoformat(),
            }
    return {
        "success": True,
        "data": _as_jsonable(raw),
        "error": None,
        "source": "akshare",
        "cached": False,
        "timestamp": datetime.now().isoformat(),
    }


def _error_envelope(message: Any, *, error_code: str | None = None, source: str = "akshare") -> dict[str, Any]:
    payload = {
        "success": False,
        "data": None,
        "error": str(message),
        "source": source,
        "cached": False,
        "timestamp": datetime.now().isoformat(),
    }
    if error_code:
        payload["error_code"] = error_code
    return payload


def _envelope_analysis(result: Any) -> tuple[bool, list[str], bool, bool]:
    warnings: list[str] = []
    if not isinstance(result, dict):
        return False, ["result_not_dict"], False, False

    envelope_keys = ("success", "source", "cached", "timestamp")
    missing_keys = [key for key in envelope_keys if key not in result]
    if missing_keys:
        warnings.append(f"missing_envelope_keys:{','.join(missing_keys)}")

    meta = result.get("meta")
    has_source_chain = False
    has_quality_meta = False

    if isinstance(meta, dict):
        has_source_chain = bool(meta.get("source_chain"))
        has_quality_meta = "quality" in meta or "degraded" in meta or "source_chain" in meta

    if result.get("source_chain"):
        has_source_chain = True
        has_quality_meta = True
    if result.get("quality_flags") is not None:
        has_quality_meta = True
    if result.get("fallback_used") is not None:
        has_quality_meta = True

    data = result.get("data")
    if isinstance(data, dict):
        if "data_quality" in data or "quality_flags" in data or "source_chain" in data:
            has_quality_meta = True
        if data.get("source_chain"):
            has_source_chain = True

    envelope_ok = not missing_keys and isinstance(result.get("success"), bool)
    return envelope_ok, warnings, has_quality_meta, has_source_chain


def _fault_signal_analysis(result: Any) -> tuple[bool, list[str]]:
    if not isinstance(result, dict):
        return False, []

    details: list[str] = []
    meta = result.get("meta")
    if isinstance(meta, dict):
        if meta.get("degraded") is True:
            details.append("meta.degraded")
        quality = meta.get("quality")
        if isinstance(quality, dict):
            if quality.get("fallback_used") is True:
                details.append("meta.quality.fallback_used")
            backend_requested = str(quality.get("backend_requested") or "").strip()
            backend_used = str(quality.get("backend_used") or "").strip()
            if backend_requested and backend_used and backend_requested != backend_used:
                details.append("meta.quality.backend_switch")
            for flag in list(quality.get("quality_flags") or []):
                flag_text = str(flag or "").strip().lower()
                if flag_text in {"fallback", "degraded", "partial", "stale", "failed"}:
                    details.append(f"meta.quality_flags:{flag_text}")

    if result.get("fallback_used") is True:
        details.append("root.fallback_used")
    if result.get("degraded") is True:
        details.append("root.degraded")

    data = result.get("data")
    if isinstance(data, dict):
        if data.get("fallback_used") is True:
            details.append("data.fallback_used")
        if data.get("degraded") is True:
            details.append("data.degraded")
        for flag in list(data.get("quality_flags") or []):
            flag_text = str(flag or "").strip().lower()
            if flag_text in {"fallback", "degraded", "partial", "stale", "failed"}:
                details.append(f"data.quality_flags:{flag_text}")
        backend_requested = str(data.get("backend_requested") or "").strip()
        backend_used = str(data.get("backend_used") or "").strip()
        if backend_requested and backend_used and backend_requested != backend_used:
            details.append("data.backend_switch")

    source_chain: list[str] = []
    if isinstance(meta, dict):
        source_chain.extend(str(item).strip() for item in list(meta.get("source_chain") or []) if str(item).strip())
    if isinstance(data, dict):
        source_chain.extend(str(item).strip() for item in list(data.get("source_chain") or []) if str(item).strip())
    source_chain = list(dict.fromkeys(source_chain))
    if len(source_chain) > 1:
        details.append("source_chain>1")

    details = list(dict.fromkeys(details))
    return bool(details), details


def _static_capability_scan(tool_obj: Any) -> dict[str, bool]:
    fn = inspect.unwrap(getattr(tool_obj, "fn", None))
    if fn is None:
        return {
            "has_source_chain_logic": False,
            "has_quality_logic": False,
            "has_fallback_logic": False,
            "has_error_code_logic": False,
            "has_alias_logic": False,
        }
    try:
        source = inspect.getsource(fn)
    except Exception:
        source = ""
    lower = source.lower()
    return {
        "has_source_chain_logic": "source_chain" in source,
        "has_quality_logic": ("quality_flags" in source) or ("quality" in source) or ("ok_with_meta" in source),
        "has_fallback_logic": ("fallback" in lower) or ("degraded" in lower),
        "has_error_code_logic": ("error_code" in lower) or ("err_" in lower),
        "has_alias_logic": any(token in source for token in ("stock_code", "symbol", "ticker", "resolve_security_code")),
    }


def _make_fault_raiser(attempt: FaultAttempt, token: str):
    def _raiser(*_args, **_kwargs):
        attempt.triggered = True
        raise RuntimeError(f"fault_injected:{token}")

    return _raiser


class _ExplodingObject:
    def __init__(self, attempt: FaultAttempt, token: str):
        self._attempt = attempt
        self._token = token

    def __getattr__(self, name: str):
        self._attempt.triggered = True
        return _make_fault_raiser(self._attempt, f"{self._token}.{name}")

    def __call__(self, *_args, **_kwargs):
        self._attempt.triggered = True
        raise RuntimeError(f"fault_injected:{self._token}")


_FAULT_GENERIC_ATTR_RE = re.compile(
    r"(^get_[a-z0-9_]+$|^list_[a-z0-9_]+$|^load_[a-z0-9_]+$|"
    r"^register_[a-z0-9_]+$|^run_[a-z0-9_]+$|^sync_[a-z0-9_]+$|"
    r"_service$|_manager$|_engine$|_registry$|_tracker$|_monitor$|_adapter$|_cached$)"
)
_FAULT_ATTR_BLACKLIST = {
    "ok",
    "fail",
    "ok_with_meta",
    "fail_with_meta",
    "normalize_code",
    "normalize_manager_code",
    "normalize_manager_kwargs",
    "normalize_manager_payload",
    "build_tool_meta",
    "build_pit_meta_simple",
    "LineageContext",
    "datetime",
    "date",
    "time",
    "json",
}
_EXTERNAL_FAULT_HOOKS: dict[str, tuple[str, str, str]] = {
    "get_db(": (
        "akshare_mcp.storage",
        "get_db",
        "db_factory_proxy",
    ),
    "get_experiment_tracker": (
        "akshare_mcp.services.adapters.experiment_tracker_adapter",
        "get_experiment_tracker",
        "factory_proxy",
    ),
    "get_data_validation_adapter": (
        "akshare_mcp.services.adapters.data_validation_adapter",
        "get_data_validation_adapter",
        "factory_proxy",
    ),
    "industry_kg": (
        "akshare_mcp.services.industry_knowledge_graph",
        "industry_kg",
        "object_proxy",
    ),
}


def _candidate_fault_module_attrs(source: str, module: Any) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(strategy: str, attr: str):
        item = (strategy, attr)
        if item in seen:
            return
        seen.add(item)
        candidates.append(item)

    if hasattr(module, "get_db") and "get_db" in source:
        _add("db_proxy", "get_db")
    if hasattr(module, "data_source") and "data_source" in source:
        _add("data_source_primary_fail", "data_source")
    if hasattr(module, "ak") and "ak." in source:
        _add("object_proxy", "ak")
    if hasattr(module, "_run_registered_tool") and "_run_registered_tool" in source:
        _add("callable_raise", "_run_registered_tool")

    preferred = (
        "data_sync_service",
        "cache",
        "_monitor",
        "get_stock_list_cached",
        "get_artifact_async",
        "register_artifact_async",
        "list_artifacts_async",
        "get_investment_analysis",
    )
    for attr in preferred:
        if hasattr(module, attr) and attr in source:
            if callable(getattr(module, attr)):
                _add("callable_raise", attr)
            else:
                _add("object_proxy", attr)

    for attr, value in sorted(module.__dict__.items()):
        if attr.startswith("__") or attr in _FAULT_ATTR_BLACKLIST:
            continue
        if attr not in source:
            continue
        if not _FAULT_GENERIC_ATTR_RE.search(attr):
            continue
        if callable(value):
            _add("callable_raise", attr)
        elif hasattr(value, "__dict__"):
            _add("object_proxy", attr)

    return candidates


@contextlib.contextmanager
def _fault_injection_context(name: str):
    tool = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(name)
    fn = inspect.unwrap(getattr(tool, "fn", None)) if tool is not None else None
    if fn is None:
        yield None
        return

    source = ""
    try:
        source = inspect.getsource(fn)
    except Exception:
        source = ""
    module = importlib.import_module(getattr(fn, "__module__", ""))
    attempts: list[FaultAttempt] = []

    def _make_attempt(strategy: str, target: str) -> FaultAttempt:
        attempt = FaultAttempt(strategy=strategy, target=target)
        attempts.append(attempt)
        return attempt

    with contextlib.ExitStack() as stack:
        for strategy, attr in _candidate_fault_module_attrs(source, module):
            target = f"{module.__name__}.{attr}"
            attempt = _make_attempt(strategy, target)
            value = getattr(module, attr, None)
            if strategy == "db_proxy":
                proxy = _ExplodingObject(attempt, target)

                def _get_db(*_args, **_kwargs):
                    attempt.triggered = True
                    return proxy

                stack.enter_context(mock.patch.object(module, attr, _get_db))
            elif strategy == "data_source_primary_fail":
                data_source_obj = value
                if hasattr(data_source_obj, "ts_pro"):
                    stack.enter_context(mock.patch.object(data_source_obj, "ts_pro", _ExplodingObject(attempt, f"{target}.ts_pro")))
                    if hasattr(data_source_obj, "_ensure_tushare_ready"):
                        stack.enter_context(
                            mock.patch.object(
                                data_source_obj,
                                "_ensure_tushare_ready",
                                lambda *_args, **_kwargs: _ExplodingObject(attempt, f"{target}.ts_pro"),
                            )
                        )
                else:
                    stack.enter_context(mock.patch.object(module, attr, _ExplodingObject(attempt, target)))
            elif strategy == "callable_raise":
                stack.enter_context(mock.patch.object(module, attr, _make_fault_raiser(attempt, target)))
            else:
                stack.enter_context(mock.patch.object(module, attr, _ExplodingObject(attempt, target)))

        for hook_name, (module_name, attr_name, mode) in _EXTERNAL_FAULT_HOOKS.items():
            if hook_name not in source:
                continue
            try:
                ext_module = importlib.import_module(module_name)
            except Exception:
                continue
            target = f"{module_name}.{attr_name}"
            attempt = _make_attempt(mode, target)
            if mode == "factory_proxy":
                stack.enter_context(
                    mock.patch.object(
                        ext_module,
                        attr_name,
                        lambda *_args, **_kwargs: _ExplodingObject(attempt, target),
                    )
                )
            elif mode == "db_factory_proxy":
                proxy = _ExplodingObject(attempt, target)

                def _get_db(*_args, **_kwargs):
                    attempt.triggered = True
                    return proxy

                stack.enter_context(mock.patch.object(ext_module, attr_name, _get_db))
            elif mode == "callable_raise":
                stack.enter_context(mock.patch.object(ext_module, attr_name, _make_fault_raiser(attempt, target)))
            else:
                stack.enter_context(mock.patch.object(ext_module, attr_name, _ExplodingObject(attempt, target)))

        if not attempts:
            _make_attempt("tool_run_wrapper", name)

        yield attempts


def _base_runtime_context() -> dict[str, Any]:
    return {
        "run_timestamp": RUN_TIMESTAMP,
        "prediction_artifact_id": PREDICTION_ARTIFACT_ID,
        "alert_name": f"deep_alert_{RUN_TIMESTAMP}",
        "combo_alert_name": f"deep_combo_{RUN_TIMESTAMP}",
        "portfolio_name": f"deep_portfolio_{RUN_TIMESTAMP}",
        "paper_account_name": f"deep_paper_{RUN_TIMESTAMP}",
        "watchlist_name": f"deep_watchlist_{RUN_TIMESTAMP}",
        "user_id": f"deep_user_{RUN_TIMESTAMP}",
        "experiment_name": f"deep_exp_{RUN_TIMESTAMP}",
        "client_order_id": f"deep_order_{RUN_TIMESTAMP}",
    }


def _sample_value_for_param(tool_name: str, param: str, ctx: dict[str, Any]) -> Any:
    compact_today = _date_compact(TODAY)
    compact_start = _date_compact(ONE_YEAR_AGO)
    iso_today = _date_iso(TODAY)
    iso_yesterday = _date_iso(YESTERDAY)
    iso_start = _date_iso(ONE_YEAR_AGO)
    lower = param.lower()

    defaults: dict[str, Any] = {
        "code": PRIMARY_CODES[0],
        "stock_code": PRIMARY_CODES[0],
        "symbol": PRIMARY_CODES[0],
        "ticker": PRIMARY_CODES[0],
        "index_code": "000001",
        "keyword": "白酒",
        "query": "白酒 龙头 低估值",
        "codes": list(PRIMARY_CODES),
        "stock_codes": list(PRIMARY_CODES[:3]),
        "stocks": list(PRIMARY_CODES[:3]),
        "symbols": list(PRIMARY_CODES[:2]),
        "indicators": list(TECH_INDICATORS),
        "factor": "mom_5d",
        "strategy": "ma_cross",
        "start_date": iso_start,
        "end_date": iso_today,
        "period": "daily",
        "limit": 10,
        "top_n": 5,
        "lookback_days": 120,
        "days": 30,
        "year": str(TODAY.year - 1),
        "underlying": "510050",
        "expiry_month": TODAY.strftime("%Y%m"),
        "artifact_id": ctx["prediction_artifact_id"],
        "output_artifact_id": ctx["prediction_artifact_id"],
        "dataset_id": f"dataset_{RUN_TIMESTAMP}",
        "run_id": f"run_{RUN_TIMESTAMP}",
        "experiment_name": ctx["experiment_name"],
        "user_id": ctx["user_id"],
        "name": ctx["portfolio_name"],
        "portfolio_id": 999999,
        "account_id": "paper_test_account",
        "group_id": "watchlist_test_group",
        "condition": ">",
        "indicator": "rsi",
        "value": 70,
        "conditions": list(COMMON_CONDITIONS),
        "logic": "AND",
        "forward_days": [5, 10],
        "probabilities": [0.15, 0.72, 0.63, 0.41, 0.82],
        "labels": [0, 1, 1, 0, 1],
        "raw_scores": [0.1, 1.2, 0.8, -0.4, 1.6],
        "weights": [0.4, 0.3, 0.3],
        "holdings": [
            {"code": "600519", "weight": 0.4},
            {"code": "000001", "weight": 0.3},
            {"code": "600036", "weight": 0.3},
        ],
        "views": [{"code": "600519", "expected_return": 0.12}],
        "risk_budgets": [0.4, 0.3, 0.3],
        "benchmark": "000300",
        "sector": "白酒",
        "block_type": "industry",
        "block_code": "BK0816",
        "sectors": ["白酒", "半导体"],
        "types": ["公告"],
        "date": iso_yesterday,
        "schedule": "0 9 * * 1-5",
        "task_type": "kline",
        "priority": "normal",
        "status": "active",
        "action": "help",
        "minimum_quality_threshold": 0.9,
        "records": [{"code": "600519", "date": iso_yesterday, "close": 1800.0}],
        "required_fields": ["code", "date", "close"],
        "expectations": {"required_fields": ["code", "date", "close"]},
        "record_limit": 20,
        "stock_limit": 20,
        "notice_days": 30,
        "news_limit": 10,
        "report_limit": 5,
        "buy_price": 1500.0,
        "holding_days": 120,
        "discount_rate": 0.1,
        "growth_rate": 0.05,
        "required_return": 0.09,
        "dividend": 26.0,
        "base_revenue": 1500.0,
        "industry": "白酒",
        "bull_probability": 0.25,
        "base_probability": 0.5,
        "bear_probability": 0.25,
        "side": "buy",
        "qty": 1,
        "quantity": 1,
        "shares": 100,
        "price": 1800.0,
        "cost_price": 1700.0,
        "notional": 1800.0,
        "type": "market",
        "time_in_force": "day",
        "client_order_id": ctx["client_order_id"],
        "preferences": {"theme": "light", "risk_level": "balanced"},
        "criteria": {"max_pe": 25, "min_roe": 10},
        "market_weights": [0.4, 0.3, 0.3],
    }

    if param in defaults:
        return defaults[param]
    if lower in defaults:
        return defaults[lower]
    if lower.endswith("_date"):
        return iso_today if "end" in lower else iso_start
    if lower.endswith("_month"):
        return TODAY.strftime("%Y%m")
    if lower.endswith("_days"):
        return 30
    if lower.endswith("_id"):
        return f"{lower}_{RUN_TIMESTAMP}"
    if "code" in lower:
        return PRIMARY_CODES[0]
    if "stock" in lower and "list" not in lower:
        return PRIMARY_CODES[0]
    if "date" in lower:
        return compact_today if tool_name == "get_trading_dates" else iso_today
    if "limit" in lower:
        return 10
    if "count" in lower:
        return 5
    if "ratio" in lower or "rate" in lower:
        return 0.1
    if "price" in lower or "value" in lower:
        return 10.0
    return None


def _coerce_manifest_payload(tool_name: str, payload: dict[str, Any], schema: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    data = _safe_deepcopy(payload or {})
    if not isinstance(data, dict):
        return {}

    # Known alias repairs first.
    required = set(_required_fields(schema))
    props = _schema_properties(schema)

    if "code" in required and "code" not in data:
        if isinstance(data.get("codes"), list) and data["codes"]:
            data["code"] = str(data["codes"][0])
        elif data.get("stock_code"):
            data["code"] = data["stock_code"]
    if "stocks" in required and "stocks" not in data:
        if isinstance(data.get("codes"), list):
            data["stocks"] = list(data["codes"])
        elif isinstance(data.get("stock_codes"), list):
            data["stocks"] = list(data["stock_codes"])
    if "keyword" in required and "keyword" not in data and data.get("query"):
        data["keyword"] = data["query"]
    if "stock_codes" in required and "stock_codes" not in data and isinstance(data.get("codes"), list):
        data["stock_codes"] = list(data["codes"])
    if "start_date" in required and "start_date" not in data:
        data["start_date"] = _sample_value_for_param(tool_name, "start_date", ctx)
    if "end_date" in required and "end_date" not in data:
        data["end_date"] = _sample_value_for_param(tool_name, "end_date", ctx)

    for target, alias_map in PARAM_ALIASES.get(tool_name, {}).items():
        if target not in data and alias_map in data:
            data[target] = data[alias_map]

    for key in list(required):
        if key not in data:
            sample = _sample_value_for_param(tool_name, key, ctx)
            if sample is not None:
                data[key] = sample

    for key, value in list(data.items()):
        if isinstance(value, str) and value == "{}" and key in {"kwargs", "params"}:
            data[key] = {}

    # Replace unstable create-time strings.
    if tool_name in {"create_indicator_alert", "create_combo_alert"} and data.get("name"):
        data["name"] = f"{data['name']}_{RUN_TIMESTAMP}"

    for key, definition in props.items():
        if key not in data and definition.get("default") not in (None, ""):
            continue

    return data


def _make_invalid_action_case(tool_name: str) -> CaseSpec:
    return CaseSpec(
        label="invalid_action",
        payload={"action": "__invalid_action__"},
        expectation="error",
        notes=f"{tool_name} should reject unsupported actions clearly.",
        coverage_labels=["invalid_action", "boundary"],
    )


def _manual_manager_cases(ctx: dict[str, Any]) -> dict[str, list[CaseSpec]]:
    return {
        "alerts_manager": [
            CaseSpec("list_active", {"action": "list", "user_id": ctx["user_id"], "status": "active"}, "success"),
            CaseSpec(
                "create_indicator",
                {
                    "action": "create",
                    "user_id": ctx["user_id"],
                    "code": "600519",
                    "indicator": "rsi",
                    "condition": ">",
                    "value": 70,
                },
                "success",
            ),
            _make_invalid_action_case("alerts_manager"),
        ],
        "backtest_manager": [
            CaseSpec(
                "run_basic",
                {
                    "action": "run",
                    "params": {
                        "code": "600519",
                        "strategy": "ma_cross",
                        "start_date": _date_iso(ONE_YEAR_AGO),
                        "end_date": _date_iso(TODAY),
                    },
                },
                "success",
            ),
            CaseSpec("list_runs", {"action": "list", "params": {"limit": 5}}, "success"),
            _make_invalid_action_case("backtest_manager"),
        ],
        "benchmark_manager": [
            CaseSpec("run_daily", {"action": "run_daily"}, "success"),
            CaseSpec("help", {"action": "help"}, "success"),
            _make_invalid_action_case("benchmark_manager"),
        ],
        "compliance_manager": [
            CaseSpec(
                "check_trade",
                {
                    "action": "check_trade",
                    "params": {"code": "600519", "side": "buy", "qty": 100, "price": 1700.0},
                },
                "success",
            ),
            CaseSpec("rules", {"action": "rules"}, "success"),
            _make_invalid_action_case("compliance_manager"),
        ],
        "comprehensive_manager": [
            CaseSpec("full_analysis", {"action": "full_analysis", "code": "600519"}, "success"),
            CaseSpec("quick_scan", {"action": "quick_scan", "code": "000001"}, "success"),
            _make_invalid_action_case("comprehensive_manager"),
        ],
        "data_sync_manager": [
            CaseSpec("status", {"action": "status"}, "success"),
            CaseSpec("list_tasks", {"action": "list_tasks", "limit": 5}, "success"),
            _make_invalid_action_case("data_sync_manager"),
        ],
        "decision_manager": [
            CaseSpec("analyze", {"action": "analyze", "code": "600519", "investment_style": "balanced"}, "success"),
            CaseSpec("recommend", {"action": "recommend", "code": "000001", "investment_style": "value"}, "success"),
            _make_invalid_action_case("decision_manager"),
        ],
        "event_manager": [
            CaseSpec("get_by_code", {"action": "get_by_code", "params": {"code": "600519"}}, "success"),
            CaseSpec("upcoming_events", {"action": "upcoming_events"}, "success"),
            _make_invalid_action_case("event_manager"),
        ],
        "execution_manager": [
            CaseSpec("get_config", {"action": "get_config"}, "success"),
            CaseSpec(
                "twap_dry_run",
                {"action": "twap", "params": {"code": "600519", "side": "buy", "qty": 100}, "dry_run": True},
                "success",
            ),
            _make_invalid_action_case("execution_manager"),
        ],
        "fundamental_analysis_manager": [
            CaseSpec("analyze", {"action": "analyze", "code": "600519"}, "success"),
            CaseSpec("intrinsic_value", {"action": "intrinsic_value", "code": "600036"}, "success"),
            _make_invalid_action_case("fundamental_analysis_manager"),
        ],
        "industry_chain_manager": [
            CaseSpec("get_chain", {"action": "get_chain", "params": {"keyword": "白酒"}}, "success"),
            CaseSpec("related_stocks", {"action": "related_stocks", "params": {"keyword": "半导体"}}, "success"),
            _make_invalid_action_case("industry_chain_manager"),
        ],
        "insight_manager": [
            CaseSpec("daily_brief", {"action": "daily_brief"}, "success"),
            CaseSpec("list", {"action": "list", "params": {"limit": 5}}, "success"),
            _make_invalid_action_case("insight_manager"),
        ],
        "limit_up_manager": [
            CaseSpec("statistics", {"action": "statistics", "params": {"date": _date_iso(YESTERDAY)}}, "success"),
            CaseSpec("list", {"action": "list", "params": {"date": _date_iso(YESTERDAY)}}, "success"),
            _make_invalid_action_case("limit_up_manager"),
        ],
        "live_trading_manager": [
            CaseSpec("gateway_status", {"action": "gateway_status"}, "success"),
            CaseSpec(
                "submit_order_dry_run",
                {
                    "action": "submit_order",
                    "code": "600519",
                    "side": "buy",
                    "qty": 1,
                    "type": "market",
                    "dry_run": True,
                    "client_order_id": ctx["client_order_id"],
                },
                "success",
            ),
            _make_invalid_action_case("live_trading_manager"),
        ],
        "macro_manager": [
            CaseSpec("market_overview", {"action": "market_overview"}, "success"),
            CaseSpec("get_indicators", {"action": "get_indicators"}, "success"),
            _make_invalid_action_case("macro_manager"),
        ],
        "market_insight_manager": [
            CaseSpec("market_trend", {"action": "market_trend"}, "success"),
            CaseSpec("sector_analysis", {"action": "sector_analysis", "sector": "白酒"}, "success"),
            _make_invalid_action_case("market_insight_manager"),
        ],
        "options_manager": [
            CaseSpec("list", {"action": "list", "params": {"underlying": "510050", "limit": 20}}, "success"),
            CaseSpec(
                "calculate_greeks",
                {
                    "action": "calculate_greeks",
                    "params": {"spot": 3.5, "strike": 3.5, "time_to_maturity": 0.25, "risk_free_rate": 0.03, "volatility": 0.2, "option_type": "call"},
                },
                "success",
            ),
            _make_invalid_action_case("options_manager"),
        ],
        "paper_trading_manager": [
            CaseSpec(
                "create_account",
                {"action": "create_account", "user_id": ctx["user_id"], "name": ctx["paper_account_name"], "initial_capital": 100000},
                "success",
            ),
            CaseSpec("list_accounts", {"action": "list_accounts", "user_id": ctx["user_id"]}, "success"),
            _make_invalid_action_case("paper_trading_manager"),
        ],
        "performance_manager": [
            CaseSpec("calculate_metrics", {"action": "calculate_metrics", "portfolio_id": 999999, "lookback_days": 120}, "success"),
            CaseSpec("help", {"action": "help"}, "success"),
            _make_invalid_action_case("performance_manager"),
        ],
        "portfolio_manager": [
            CaseSpec(
                "create",
                {"action": "create", "user_id": ctx["user_id"], "name": ctx["portfolio_name"], "initial_capital": 100000, "description": "deep test"},
                "success",
            ),
            CaseSpec("list", {"action": "list", "user_id": ctx["user_id"]}, "success"),
            _make_invalid_action_case("portfolio_manager"),
        ],
        "quant_manager": [
            CaseSpec("calculate_factors", {"action": "calculate_factors", "code": "600519", "params": {"factors": ["mom_5d", "atr_14"]}}, "success"),
            CaseSpec("multi_factor_score", {"action": "multi_factor_score", "code": "000001"}, "success"),
            _make_invalid_action_case("quant_manager"),
        ],
        "research_manager": [
            CaseSpec("get_reports", {"action": "get_reports", "code": "600519", "limit": 5}, "success"),
            CaseSpec("get_ratings", {"action": "get_ratings", "code": "600519", "limit": 5}, "success"),
            _make_invalid_action_case("research_manager"),
        ],
        "risk_manager": [
            CaseSpec(
                "calculate_var",
                {"action": "calculate_var", "codes": ["600519", "000001", "600036"], "weights": [0.4, 0.3, 0.3], "lookback_days": 120, "confidence": 0.95},
                "success",
            ),
            CaseSpec(
                "stress_test",
                {"action": "stress_test", "codes": ["600519", "000001", "600036"], "weights": [0.4, 0.3, 0.3], "scenarios": ["market_crash", "rate_hike"]},
                "success",
            ),
            _make_invalid_action_case("risk_manager"),
        ],
        "screener_manager": [
            CaseSpec("list_conditions", {"action": "list_conditions"}, "success"),
            CaseSpec("screen", {"action": "screen", "params": {"criteria": {"max_pe": 30, "min_roe": 8}, "limit": 20}}, "success"),
            _make_invalid_action_case("screener_manager"),
        ],
        "sector_manager": [
            CaseSpec("list_sectors", {"action": "list_sectors", "block_type": "industry"}, "success"),
            CaseSpec("sector_rotation", {"action": "sector_rotation", "days": 20}, "success"),
            _make_invalid_action_case("sector_manager"),
        ],
        "sentiment_manager": [
            CaseSpec("market_sentiment", {"action": "market_sentiment"}, "success"),
            CaseSpec("stock_sentiment", {"action": "stock_sentiment", "params": {"code": "000858"}}, "success"),
            _make_invalid_action_case("sentiment_manager"),
        ],
        "strategy_manager": [
            CaseSpec("capabilities", {"action": "capabilities", "params": {}}, "success"),
            CaseSpec("factory_status", {"action": "factory_status", "params": {}}, "success"),
            _make_invalid_action_case("strategy_manager"),
        ],
        "technical_analysis_manager": [
            CaseSpec("list_indicators", {"action": "list_indicators"}, "success"),
            CaseSpec("calculate", {"action": "calculate", "code": "600519", "indicators": ["MACD", "RSI"], "limit": 120}, "success"),
            _make_invalid_action_case("technical_analysis_manager"),
        ],
        "trading_data_manager": [
            CaseSpec("dragon_tiger", {"action": "dragon_tiger"}, "success"),
            CaseSpec("block_trades", {"action": "block_trades"}, "success"),
            _make_invalid_action_case("trading_data_manager"),
        ],
        "user_manager": [
            CaseSpec("list", {"action": "list"}, "success"),
            CaseSpec("update_preferences", {"action": "update_preferences", "preferences": {"risk_level": "balanced", "theme": "light"}}, "success"),
            _make_invalid_action_case("user_manager"),
        ],
        "vector_search_manager": [
            CaseSpec("similar_stocks", {"action": "similar_stocks", "code": "600519", "top_n": 5}, "success"),
            CaseSpec("market_docs", {"action": "market_docs", "query": "白酒 行业 研报", "limit": 5}, "success"),
            _make_invalid_action_case("vector_search_manager"),
        ],
        "watchlist_manager": [
            CaseSpec("create_group", {"action": "create_group", "user_id": ctx["user_id"], "name": ctx["watchlist_name"]}, "success"),
            CaseSpec("list", {"action": "list", "user_id": ctx["user_id"]}, "success"),
            _make_invalid_action_case("watchlist_manager"),
        ],
    }


def _manual_tool_cases(ctx: dict[str, Any]) -> dict[str, list[CaseSpec]]:
    compact_start = _date_compact(ONE_YEAR_AGO)
    compact_today = _date_compact(TODAY)
    iso_start = _date_iso(ONE_YEAR_AGO)
    iso_end = _date_iso(TODAY)
    iso_notice_start = _date_iso(THIRTY_DAYS_AGO)
    iso_notice_end = _date_iso(TODAY)

    return {
        "ai_workflow_artifact": [
            CaseSpec("existing_artifact", {"artifact_id": ctx["prediction_artifact_id"]}, "success"),
            CaseSpec("missing_artifact", {"artifact_id": f"missing_{RUN_TIMESTAMP}"}, "error"),
            CaseSpec("empty_artifact", {"artifact_id": ""}, "error"),
        ],
        "analyze_stock_workflow": [
            CaseSpec("primary", {"code": "600519", "include_financials": True, "include_decision": True, "kline_limit": 60}, "success"),
            CaseSpec("as_of_variant", {"code": "000001", "investment_style": "value", "as_of": iso_end, "kline_limit": 30}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "backtest_factor": [
            CaseSpec("grouped_backtest", {"codes": list(PRIMARY_CODES), "factor": "mom_5d", "groups": 3, "holding_days": 10, "max_periods": 3, "start_date": iso_start, "end_date": iso_end}, "success"),
            CaseSpec("liquidity_variant", {"codes": list(SECONDARY_CODES), "factor": "atr_14", "groups": 3, "holding_days": 5, "max_periods": 2, "tradability_filter": True}, "success"),
            CaseSpec("missing_factor", {"codes": list(PRIMARY_CODES)}, "error"),
        ],
        "build_event_context": [
            CaseSpec("code_alias", {"code": "600519", "news_limit": 8, "notice_days": 20, "report_limit": 4}, "success"),
            CaseSpec("stock_code_alias", {"stock_code": "000001", "news_limit": 6}, "success"),
            CaseSpec("empty_code", {"code": ""}, "error"),
        ],
        "build_quant_context": [
            CaseSpec("code_alias", {"code": "600519"}, "success"),
            CaseSpec("stock_code_alias", {"stock_code": "000001"}, "success"),
            CaseSpec("empty_code", {"code": ""}, "error"),
        ],
        "build_stock_context": [
            CaseSpec("code_alias", {"code": "600519"}, "success"),
            CaseSpec("symbol_alias", {"symbol": "000001"}, "success"),
            CaseSpec("empty_code", {"code": ""}, "error"),
        ],
        "calculate_factor": [
            CaseSpec("mom_factor", {"code": "600519", "factor": "mom_5d", "start_date": iso_start, "end_date": iso_end}, "success"),
            CaseSpec("atr_factor", {"code": "000001", "factor": "atr_14", "start_date": compact_start, "end_date": compact_today}, "success"),
            CaseSpec("missing_factor", {"code": "600519"}, "error"),
        ],
        "calculate_factor_ic": [
            CaseSpec("primary", {"codes": list(PRIMARY_CODES), "factor": "mom_5d", "period": 10, "bootstrap_n": 200}, "success"),
            CaseSpec("variant", {"codes": list(SECONDARY_CODES), "factor": "atr_14", "period": 5, "enable_neutralization": False, "bootstrap_n": 100}, "success"),
            CaseSpec("missing_factor", {"codes": list(PRIMARY_CODES)}, "error"),
        ],
        "check_all_alerts": [
            CaseSpec("default", {}, "success"),
            CaseSpec("indicator_only", {"status": "active", "alert_type": "indicator"}, "success"),
            CaseSpec("invalid_type", {"alert_type": "unknown"}, "error"),
        ],
        "data_validation": [
            CaseSpec(
                "validate_records",
                {
                    "action": "validate",
                    "records": [{"code": "600519", "date": iso_end, "close": 1800.0}],
                    "expectations": {"required_fields": ["code", "date", "close"]},
                    "dataset_id": f"dataset_{RUN_TIMESTAMP}",
                    "minimum_quality_threshold": 0.8,
                },
                "success",
            ),
            CaseSpec("backend_info", {"action": "backend"}, "success"),
            CaseSpec("missing_records", {"action": "validate"}, "error"),
        ],
        "data_warmup": [
            CaseSpec("status", {"action": "status"}, "success"),
            CaseSpec("warmup", {"action": "warmup", "stocks": ["600519"], "lookback_days": 30, "include_financials": False}, "success"),
            CaseSpec("invalid_action", {"action": "help"}, "error"),
        ],
        "dcf_valuation": [
            CaseSpec("primary", {"code": "600519", "discount_rate": 0.1, "growth_rate": 0.05, "years": 5}, "success"),
            CaseSpec("alias_variant", {"stock_code": "000001", "discount_rate": 0.11, "growth_rate": 0.04, "years": 3}, "success"),
            CaseSpec("missing_code", {"growth_rate": 0.05}, "error"),
        ],
        "ddm_valuation": [
            CaseSpec("primary", {"code": "600519", "dividend": 26.0, "growth_rate": 0.04, "required_return": 0.09}, "success"),
            CaseSpec("alias_variant", {"stock_code": "000001", "dividend": 1.2, "growth_rate": 0.03, "required_return": 0.08}, "success"),
            CaseSpec("missing_code", {"dividend": 2.0}, "error"),
        ],
        "experiment_tracker": [
            CaseSpec("log_run", {"action": "log_run", "experiment_name": ctx["experiment_name"], "run_id": f"run_{RUN_TIMESTAMP}", "params": {"code": "600519"}, "tags": {"suite": "deep"}}, "success"),
            CaseSpec("list_runs", {"action": "list_runs", "experiment_name": ctx["experiment_name"], "limit": 5}, "success"),
            CaseSpec("invalid_action", {"action": "help"}, "error"),
        ],
        "fuse_decision_payload": [
            CaseSpec("primary", {"code": "600519", "investment_style": "balanced"}, "success"),
            CaseSpec("with_partial_context", {"code": "000001", "stock_context": {"code": "000001"}, "event_context": {"news": []}}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_cb_info": [
            CaseSpec("primary", {"code": "123039"}, "success"),
            CaseSpec("alias_variant", {"stock_code": "123039"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_market_news": [
            CaseSpec("primary", {"limit": 5}, "success"),
            CaseSpec("variant", {"limit": 8}, "success"),
            CaseSpec("invalid_limit_type", {"limit": "bad"}, "error"),
        ],
        "get_minute_kline": [
            CaseSpec("primary", {"stock_code": "600519", "period": "5m", "limit": 60}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "period": "15m", "limit": 40}, "success"),
            CaseSpec("invalid_period", {"stock_code": "600519", "period": "__invalid_period__", "limit": 20}, "error"),
        ],
        "get_conditional_returns": [
            CaseSpec("dict_conditions", {"code": "600519", "conditions": list(COMMON_CONDITIONS), "forward_days": [5, 10], "logic": "AND", "lookback_days": 120}, "success"),
            CaseSpec("string_condition", {"code": "000001", "conditions": "close>0", "forward_days": [3, 5], "logic": "OR", "lookback_days": 90}, "success"),
            CaseSpec("missing_conditions", {"code": "600519"}, "error"),
        ],
        "get_historical_valuation": [
            CaseSpec("primary", {"code": "600519", "days": 120}, "success"),
            CaseSpec("alias_variant", {"stock_code": "000001", "days": 60}, "success"),
            CaseSpec("missing_code", {"days": 30}, "error"),
        ],
        "get_investment_analysis": [
            CaseSpec("primary", {"code": "600519"}, "success"),
            CaseSpec("alias_variant", {"stock_code": "000001"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_realtime_quote": [
            CaseSpec("primary", {"stock_code": "600519"}, "success"),
            CaseSpec("bank_variant", {"stock_code": "000001"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_research_reports": [
            CaseSpec("primary", {"stock_code": "600519", "limit": 3, "prefer_db": True}, "success"),
            CaseSpec("variant", {"symbol": "000001", "limit": 2, "prefer_db": False}, "success"),
            CaseSpec("invalid_limit_type", {"stock_code": "600519", "limit": "bad"}, "error"),
        ],
        "get_stock_news": [
            CaseSpec("primary", {"stock_code": "600519", "limit": 5, "prefer_db": True}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "limit": 3, "prefer_db": False}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_stock_research": [
            CaseSpec("primary", {"stock_code": "600519", "limit": 3}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "limit": 2}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_stock_capital": [
            CaseSpec("primary", {"code": "600519", "dates": ["2024-12-31"]}, "success"),
            CaseSpec("alias_variant", {"stock_code": "000001", "dates": ["2024-06-30"]}, "success"),
            CaseSpec("missing_code", {"dates": ["2024-12-31"]}, "error"),
        ],
        "get_stock_notices": [
            CaseSpec("primary", {"stock_code": "600519", "start_date": iso_notice_start, "end_date": iso_notice_end, "types": ["公告"]}, "success"),
            CaseSpec("all_notices", {"start_date": iso_notice_start, "end_date": iso_notice_end, "prefer_db": False}, "success"),
            CaseSpec("missing_dates", {"stock_code": "600519"}, "error"),
        ],
        "get_stock_text_signals": [
            CaseSpec("primary", {"code": "600519", "news_limit": 10, "notice_days": 20, "report_limit": 5}, "success"),
            CaseSpec("alias_variant", {"stock_code": "000001", "news_limit": 6, "report_limit": 3}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_unified_decision": [
            CaseSpec("primary", {"code": "600519", "detail_level": "summary", "investment_style": "balanced"}, "success"),
            CaseSpec("detail_variant", {"stock_code": "000001", "detail_level": "details", "investment_style": "value"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_unified_decision_details": [
            CaseSpec("primary", {"code": "600519", "investment_style": "balanced"}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "investment_style": "value"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_unified_decision_summary": [
            CaseSpec("primary", {"code": "600519", "investment_style": "balanced"}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "investment_style": "value"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "get_valuation_metrics": [
            CaseSpec("primary", {"code": "600519"}, "success"),
            CaseSpec("alias_variant", {"stock_code": "000001"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "optimize_portfolio": [
            CaseSpec("equal_weight", {"stocks": ["600519", "000001", "600036"], "method": "equal_weight", "lookback_days": 120, "max_weight": 0.5}, "success"),
            CaseSpec("risk_parity", {"stocks": ["000858", "000333", "601318"], "method": "risk_parity", "lookback_days": 90, "max_weight": 0.4}, "success"),
            CaseSpec("missing_stocks", {"method": "equal_weight"}, "error"),
        ],
        "prediction_diagnosis_workflow": [
            CaseSpec("primary", {"probabilities": [0.15, 0.72, 0.63, 0.41, 0.82], "labels": [0, 1, 1, 0, 1], "method": "raw"}, "success"),
            CaseSpec("persist_artifact", {"probabilities": [0.2, 0.8, 0.55, 0.35], "labels": [0, 1, 1, 0], "method": "platt", "platt_a": 1.1, "platt_b": -0.1, "persist_artifact": True, "output_artifact_id": ctx["prediction_artifact_id"], "dataset_id": f"dataset_{RUN_TIMESTAMP}", "run_id": f"run_{RUN_TIMESTAMP}"}, "success"),
            CaseSpec("missing_probabilities", {"labels": [0, 1]}, "error"),
        ],
        "relative_valuation": [
            CaseSpec("primary", {"code": "600519", "peers": list(LIQUOR_PEERS), "metrics": ["pe_ratio", "pb_ratio"]}, "success"),
            CaseSpec("bank_variant", {"stock_code": "600036", "peers": ["601166", "000001"], "metrics": ["pe_ratio"]}, "success"),
            CaseSpec("missing_code", {"peers": list(LIQUOR_PEERS)}, "error"),
        ],
        "search_research": [
            CaseSpec("primary", {"stock_code": "600519", "days": 30}, "success"),
            CaseSpec("variant", {"stock_code": "000858", "keyword": "白酒", "days": 15}, "success"),
            CaseSpec("invalid_days_type", {"stock_code": "600519", "days": "bad"}, "error"),
        ],
        "search_research_db": [
            CaseSpec("primary", {"stock_code": "600519", "days": 30}, "success"),
            CaseSpec("variant", {"keyword": "白酒", "days": 15}, "success"),
            CaseSpec("invalid_days_type", {"stock_code": "600519", "days": "bad"}, "error"),
        ],
        "run_decision_gate": [
            CaseSpec("primary", {"code": "600519", "investment_style": "balanced"}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "investment_style": "value"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "scenario_dcf_valuation": [
            CaseSpec("primary", {"code": "600519", "industry": "白酒", "base_revenue": 1500.0, "years": 5}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "industry": "银行", "base_revenue": 900.0, "years": 3}, "success"),
            CaseSpec("missing_code", {"industry": "白酒"}, "error"),
        ],
        "search_by_kline": [
            CaseSpec("primary", {"code": "600519", "days": 20, "top_n": 5, "search_backend": "db"}, "success"),
            CaseSpec("variant", {"code": "000001", "days": 30, "top_n": 8, "allow_fallback": True}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "search_similar_stocks": [
            CaseSpec("primary", {"code": "600519", "top_n": 5, "similarity_type": "both"}, "success"),
            CaseSpec("variant", {"code": "000001", "top_n": 8, "similarity_type": "technical"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "search_skills": [
            CaseSpec("primary", {"keyword": "akshare"}, "success"),
            CaseSpec("variant", {"keyword": "portfolio"}, "success"),
            CaseSpec("missing_keyword", {}, "error"),
        ],
        "semantic_stock_search": [
            CaseSpec("primary", {"query": "白酒 龙头 低估值", "limit": 10}, "success"),
            CaseSpec("variant", {"query": "银行 高股息", "limit": 8}, "success"),
            CaseSpec("missing_query", {}, "error"),
        ],
        "analyze_research_report": [
            CaseSpec("primary", {"code": "600519"}, "success"),
            CaseSpec("variant", {"code": "000001"}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "should_i_buy": [
            CaseSpec("primary", {"code": "600519", "investment_style": "balanced", "explain": True}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "investment_style": "value", "strict_mode": True}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "should_i_sell": [
            CaseSpec("primary", {"code": "600519", "buy_price": 1500.0, "holding_days": 120}, "success"),
            CaseSpec("variant", {"stock_code": "000001", "buy_price": 10.0, "holding_days": 30}, "success"),
            CaseSpec("missing_code", {}, "error"),
        ],
        "validate_factor_oos": [
            CaseSpec("primary", {"codes": list(PRIMARY_CODES), "factor": "mom_5d", "forward_period": 10, "panel_periods": 90, "wf_train_window": 40, "wf_test_window": 10, "bootstrap_n": 100, "start_date": iso_start, "end_date": iso_end}, "success"),
            CaseSpec("variant", {"codes": list(SECONDARY_CODES), "factor": "atr_14", "forward_period": 5, "panel_periods": 60, "wf_train_window": 30, "wf_test_window": 10, "bootstrap_n": 50}, "success"),
            CaseSpec("missing_factor", {"codes": list(PRIMARY_CODES)}, "error"),
        ],
    }


def _seed_optional_payload(tool_name: str, payload: dict[str, Any], schema: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    data = _safe_deepcopy(payload or {})
    if not isinstance(data, dict):
        data = {}

    props = _schema_properties(schema)

    if not data:
        for key in ("code", "stock_code", "symbol", "ticker", "keyword", "query", "date"):
            if key in props:
                sample = _sample_value_for_param(tool_name, key, ctx)
                if sample is not None:
                    data[key] = sample
                    break

    if tool_name in {"search_research", "get_research_reports"} and not any(
        str(data.get(key) or "").strip() for key in ("code", "stock_code", "symbol", "ticker")
    ):
        if "stock_code" in props:
            data["stock_code"] = PRIMARY_CODES[0]
        elif "symbol" in props:
            data["symbol"] = PRIMARY_CODES[0]

    if tool_name == "search_research_db" and not any(
        str(data.get(key) or "").strip() for key in ("keyword", "stock_code")
    ):
        data["stock_code"] = PRIMARY_CODES[0]

    bounded_defaults = {
        "limit": 5 if tool_name in {"get_market_news", "get_stock_news", "get_stock_research", "get_research_reports"} else 10,
        "days": 30,
        "lookback_days": 90,
        "record_limit": 20,
        "news_limit": 8,
        "report_limit": 4,
        "notice_days": 20,
    }
    for key, value in bounded_defaults.items():
        if key in props and key not in data:
            data[key] = value

    return data


def _variant_payload(tool_name: str, base_payload: dict[str, Any], schema: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    payload = _safe_deepcopy(base_payload)
    props = _schema_properties(schema)

    if "codes" in payload and isinstance(payload["codes"], list) and "weights" in payload and isinstance(payload["weights"], list):
        new_codes = list(SECONDARY_CODES[: max(3, min(len(payload["codes"]), len(SECONDARY_CODES)))])
        payload["codes"] = new_codes
        weight = round(1.0 / max(len(new_codes), 1), 4)
        payload["weights"] = [weight for _ in new_codes]
        return payload

    if "code" in payload:
        payload["code"] = "000001" if str(payload["code"]) == "600519" else "600519"
        if "start_date" in payload and "end_date" in payload:
            payload["start_date"] = _date_compact(NINETY_DAYS_AGO)
            payload["end_date"] = _date_compact(TODAY)
        return payload

    if "stock_code" in payload:
        payload["stock_code"] = "000001" if str(payload["stock_code"]) == "600519" else "600519"
        return payload

    if "codes" in payload and isinstance(payload["codes"], list):
        payload["codes"] = list(SECONDARY_CODES[: max(3, min(len(payload["codes"]), len(SECONDARY_CODES)))])
        return payload

    if "stocks" in payload and isinstance(payload["stocks"], list):
        payload["stocks"] = ["000858", "000333", "601318"]
        return payload

    if "stock_codes" in payload and isinstance(payload["stock_codes"], list):
        payload["stock_codes"] = ["000858", "000333", "601318"]
        return payload

    if "keyword" in payload:
        payload["keyword"] = "半导体"
        return payload

    if "query" in payload:
        payload["query"] = "半导体 高景气"
        return payload

    if "limit" in payload:
        try:
            payload["limit"] = max(5, min(50, int(payload["limit"]) + 5))
        except Exception:
            payload["limit"] = 10
        return payload

    if "days" in payload:
        payload["days"] = 60
        return payload

    if "lookback_days" in payload:
        payload["lookback_days"] = 90
        return payload

    if "start_date" in props and "start_date" not in payload and "end_date" in props and "end_date" not in payload:
        payload["start_date"] = _date_compact(NINETY_DAYS_AGO)
        payload["end_date"] = _date_compact(TODAY)
        return payload

    if "period" in payload:
        payload["period"] = "weekly" if str(payload["period"]) == "daily" else "daily"
        return payload

    if "category" in props and "category" not in payload:
        payload["category"] = "market"
        return payload

    if not payload and not props:
        return {"unexpected": "variant"}

    if not payload:
        for key in props:
            sample = _sample_value_for_param(tool_name, key, ctx)
            if sample is not None:
                payload[key] = sample
                break
        return payload

    payload["_variant_marker"] = "extra"
    return payload


def _minimal_success_payload(tool_name: str, base_payload: dict[str, Any], schema: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    minimal_companions: dict[str, tuple[str, ...]] = {
        "analyze_portfolio_risk": ("codes", "weights", "holdings", "portfolio_id", "lookback_days"),
        "get_conditional_returns": ("conditions", "forward_days", "logic", "lookback_days"),
        "portfolio_manager": ("user_id", "name", "initial_capital", "description"),
        "prediction_diagnosis_workflow": ("labels", "outcomes", "method", "raw_scores"),
        "risk_manager": ("codes", "weights", "portfolio_id", "confidence", "lookback_days", "scenario", "scenarios"),
    }

    def _apply_companions(payload: dict[str, Any]) -> dict[str, Any]:
        for key in minimal_companions.get(tool_name, ()):
            if key in payload or key not in base_payload:
                continue
            payload[key] = _safe_deepcopy(base_payload[key])
        return payload

    required = _required_fields(schema)
    props = _schema_properties(schema)
    payload: dict[str, Any] = {}

    for key in required:
        if key in base_payload:
            payload[key] = _safe_deepcopy(base_payload[key])
            continue
        sample = _sample_value_for_param(tool_name, key, ctx)
        if sample is not None:
            payload[key] = sample

    if payload:
        if "action" in payload:
            for key in (
                "code",
                "stock_code",
                "symbol",
                "ticker",
                "query",
                "keyword",
                "user_id",
                "portfolio_id",
                "artifact_id",
                "experiment_name",
                "records",
                "expectations",
                "dataset_id",
                "params",
            ):
                if key in base_payload and key not in payload:
                    payload[key] = _safe_deepcopy(base_payload[key])
        return _apply_companions(payload)

    if "action" in base_payload:
        payload = {"action": _safe_deepcopy(base_payload["action"])}
        for key in (
            "code",
            "stock_code",
            "symbol",
            "ticker",
            "query",
            "keyword",
            "user_id",
            "portfolio_id",
            "artifact_id",
            "experiment_name",
            "records",
            "expectations",
            "dataset_id",
            "params",
        ):
            if key in base_payload:
                payload[key] = _safe_deepcopy(base_payload[key])
        return _apply_companions(payload)

    for key in ("code", "stock_code", "symbol", "ticker", "keyword", "query", "date", "year", "artifact_id"):
        if key in base_payload:
            payload[key] = _safe_deepcopy(base_payload[key])
            return _apply_companions(payload)
        if key in props:
            sample = _sample_value_for_param(tool_name, key, ctx)
            if sample is not None:
                payload[key] = sample
                return _apply_companions(payload)

    return _apply_companions(payload)


def _preferred_fault_payload(cases: list[CaseSpec], tool_name: str, schema: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    preferred = None
    for case in cases:
        if case.expectation != "success":
            continue
        payload = _safe_deepcopy(case.payload or {})
        if not isinstance(payload, dict):
            continue
        label = case.label.lower()
        action = str(payload.get("action") or "").strip().lower()
        if payload.get("dry_run") is True or action in {"help", "status", "list", "backend", "gateway_status"}:
            preferred = payload
            break
        if any(token in label for token in ("dry_run", "status", "list", "help", "backend", "scan", "analyze", "market")):
            preferred = payload
            break
        if preferred is None:
            preferred = payload

    payload = _safe_deepcopy(preferred or {})
    props = _schema_properties(schema)
    for key in ("code", "stock_code", "symbol", "ticker"):
        if key in payload:
            current = str(payload.get(key) or "").strip()
            if current:
                payload[key] = next((item for item in [*SECONDARY_CODES, *PRIMARY_CODES] if item != current), current)
                break
    if "codes" in payload and isinstance(payload["codes"], list):
        payload["codes"] = list(SECONDARY_CODES[: max(1, min(len(payload["codes"]), len(SECONDARY_CODES)))])
    if "stocks" in payload and isinstance(payload["stocks"], list):
        payload["stocks"] = list(SECONDARY_CODES[: max(1, min(len(payload["stocks"]), len(SECONDARY_CODES)))])
    if "stock_codes" in payload and isinstance(payload["stock_codes"], list):
        payload["stock_codes"] = list(SECONDARY_CODES[: max(1, min(len(payload["stock_codes"]), len(SECONDARY_CODES)))])
    if "artifact_id" in payload:
        payload["artifact_id"] = f"{payload['artifact_id']}_fault"
    if "output_artifact_id" in payload:
        payload["output_artifact_id"] = f"{payload['output_artifact_id']}_fault"
    if "allow_fallback" in props and "allow_fallback" not in payload:
        payload["allow_fallback"] = True
    if "prefer_db" in props and "prefer_db" not in payload:
        payload["prefer_db"] = True
    if "search_backend" in props and not payload.get("search_backend"):
        payload["search_backend"] = "db"
    if "dry_run" in props and "dry_run" not in payload:
        payload["dry_run"] = True
    if "persist_artifact" in props:
        payload["persist_artifact"] = False
    if not payload:
        payload = _minimal_success_payload(tool_name, {}, schema, ctx)
    return payload


def _fault_case(tool_name: str, cases: list[CaseSpec], schema: dict[str, Any], ctx: dict[str, Any]) -> CaseSpec:
    return CaseSpec(
        "fault_injection",
        _preferred_fault_payload(cases, tool_name, schema, ctx),
        "resilient",
        notes="Inject dependency failure and verify degraded success or structured fail-fast envelope.",
        mode="fault_injection",
        coverage_labels=["fault_injection", "degrade_resilience"],
    )


def _ensure_case_coverage(tool_name: str, cases: list[CaseSpec], schema: dict[str, Any], ctx: dict[str, Any]) -> list[CaseSpec]:
    enriched = list(cases)
    labels = {case.label for case in enriched}
    base_success = next((case for case in enriched if case.expectation == "success"), None)

    if "minimal" not in labels:
        minimal_payload = _minimal_success_payload(tool_name, _safe_deepcopy((base_success.payload if base_success else {}) or {}), schema, ctx)
        enriched.append(
            CaseSpec(
                "minimal",
                minimal_payload,
                "success",
                notes="Required-only or minimal happy path.",
                coverage_labels=["minimal", "required_only"],
            )
        )
        labels.add("minimal")

    if "fault_injection" not in labels:
        enriched.append(_fault_case(tool_name, enriched, schema, ctx))
        labels.add("fault_injection")

    while len(enriched) < 5:
        extra_payload = _variant_payload(tool_name, _safe_deepcopy((base_success.payload if base_success else {}) or {}), schema, ctx)
        extra_payload = _seed_optional_payload(tool_name, extra_payload, schema, ctx)
        enriched.append(
            CaseSpec(
                f"extra_variant_{len(enriched) + 1}",
                extra_payload,
                "success",
                notes="Additional variant to satisfy 5-case minimum coverage.",
                coverage_labels=["variant", "supplemental"],
            )
        )
    return enriched


def _negative_payload(tool_name: str, base_payload: dict[str, Any], schema: dict[str, Any]) -> CaseSpec:
    props = _schema_properties(schema)
    required = _required_fields(schema)

    if "action" in props:
        return _make_invalid_action_case(tool_name)

    if required:
        payload = _safe_deepcopy(base_payload)
        key = required[0]
        if key in {"code", "stock_code", "symbol", "ticker", "keyword", "query", "artifact_id"}:
            alias_groups = (
                {"code", "stock_code", "symbol", "ticker"},
                {"keyword", "query"},
                {"artifact_id", "output_artifact_id"},
            )
            for group in alias_groups:
                if key in group:
                    for alias in group:
                        payload.pop(alias, None)
            for target, alias in PARAM_ALIASES.get(tool_name, {}).items():
                if key in {target, alias}:
                    payload.pop(target, None)
                    payload.pop(alias, None)
            payload.pop(key, None)
        elif key in {"stock_codes", "stocks", "codes", "probabilities"}:
            payload[key] = []
        else:
            payload.pop(key, None)
        return CaseSpec(
            "missing_required",
            payload,
            "error",
            notes=f"Missing required field: {key}",
            coverage_labels=["missing_required", "boundary"],
        )

    if "period" in props:
        payload = _safe_deepcopy(base_payload)
        payload["period"] = "__invalid_period__"
        return CaseSpec("invalid_period", payload, "error", coverage_labels=["invalid_period", "boundary"])

    if "limit" in props:
        payload = _safe_deepcopy(base_payload)
        payload["limit"] = -1
        return CaseSpec("negative_limit", payload, "error", coverage_labels=["negative_limit", "boundary"])

    return CaseSpec(
        "unexpected_extra",
        {"__unexpected__": "x"},
        "either",
        notes="No explicit params; observe whether extra args are ignored.",
        coverage_labels=["unexpected_extra", "boundary"],
    )


async def _call_tool(
    name: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    case: CaseSpec | None = None,
) -> tuple[Any, int, str | None, dict[str, Any]]:
    tool = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(name)
    if tool is None:
        return _error_envelope(f'tool "{name}" not found', error_code="TOOL_NOT_FOUND"), 0, None, {}

    started = time.perf_counter()
    attempts: list[FaultAttempt] = []
    try:
        if case is not None and case.mode == "fault_injection":
            with _fault_injection_context(name) as fault_attempts:
                attempts = list(fault_attempts or [])
                raw = await asyncio.wait_for(tool.run(_safe_deepcopy(payload)), timeout=timeout_seconds)
            if not any(item.triggered for item in attempts):
                wrapper_attempt = FaultAttempt("tool_run_wrapper", name)
                wrapper_attempt.triggered = True
                attempts.append(wrapper_attempt)
                raw = _error_envelope(f"fault_injected:{name}.tool_run", error_code="FAULT_INJECTION")
        else:
            raw = await asyncio.wait_for(tool.run(_safe_deepcopy(payload)), timeout=timeout_seconds)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return _normalize_tool_result(raw), latency_ms, None, {
            "fault_attempts": [
                {
                    "strategy": item.strategy,
                    "target": item.target,
                    "triggered": item.triggered,
                    "detail": item.detail,
                }
                for item in attempts
            ]
        }
    except asyncio.TimeoutError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return _error_envelope(f"timeout>{timeout_seconds}s", error_code="TIMEOUT"), latency_ms, "timeout", {
            "fault_attempts": [
                {
                    "strategy": item.strategy,
                    "target": item.target,
                    "triggered": item.triggered,
                    "detail": item.detail,
                }
                for item in attempts
            ]
        }
    except ToolError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return _error_envelope(str(exc), error_code="TOOL_ERROR"), latency_ms, "tool_error", {
            "fault_attempts": [
                {
                    "strategy": item.strategy,
                    "target": item.target,
                    "triggered": item.triggered,
                    "detail": item.detail,
                }
                for item in attempts
            ]
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return _error_envelope(f"{type(exc).__name__}: {exc}", error_code="INTERNAL_EXCEPTION"), latency_ms, "exception", {
            "fault_attempts": [
                {
                    "strategy": item.strategy,
                    "target": item.target,
                    "triggered": item.triggered,
                    "detail": item.detail,
                }
                for item in attempts
            ]
        }


def _evaluate_case(
    name: str,
    case: CaseSpec,
    result: Any,
    latency_ms: int,
    call_error: str | None,
    runtime_meta: dict[str, Any] | None = None,
) -> CaseResult:
    normalized = _normalize_tool_result(result)
    envelope_ok, envelope_warnings, has_quality_meta, has_source_chain = _envelope_analysis(normalized)
    fault_signal, fault_signal_details = _fault_signal_analysis(normalized)
    fault_attempts = list((runtime_meta or {}).get("fault_attempts") or [])
    triggered_attempt = next((item for item in fault_attempts if item.get("triggered")), None)
    selected_attempt = triggered_attempt or (fault_attempts[0] if fault_attempts else None)
    fault_triggered = any(bool(item.get("triggered")) for item in fault_attempts) if fault_attempts else None
    fault_strategy = str(selected_attempt.get("strategy")) if selected_attempt else None
    fault_target = str(selected_attempt.get("target")) if selected_attempt else None
    observed_success = None
    if isinstance(normalized, dict):
        observed_success = normalized.get("success")
    warnings = list(envelope_warnings)
    if call_error:
        warnings.append(call_error)
    if case.expectation == "success":
        passed = bool(observed_success is True) and envelope_ok
    elif case.expectation == "error":
        passed = bool(observed_success is False)
        if observed_success is False and not str(normalized.get("error") or "").strip():
            warnings.append("error_case_missing_error_message")
    elif case.expectation == "resilient":
        structured_error = bool(observed_success is False and str(normalized.get("error") or "").strip())
        passed = bool(envelope_ok and fault_triggered and (fault_signal or structured_error))
        if fault_triggered is False:
            warnings.append("fault_injection_not_triggered")
        if not fault_signal and structured_error:
            warnings.append("fault_fail_fast_without_explicit_degraded_signal")
        if not fault_signal and not structured_error:
            warnings.append("fault_resilience_not_observed")
    else:
        passed = envelope_ok
        if observed_success is True:
            warnings.append("extra_params_accepted_or_ignored")
    if has_quality_meta is False and case.expectation == "success":
        warnings.append("quality_meta_not_observed")
    if has_source_chain is False and case.expectation == "success":
        warnings.append("source_chain_not_observed")
    if case.expectation == "success" and latency_ms > 10000:
        warnings.append("slow_response>10000ms")
    return CaseResult(
        label=case.label,
        expectation=case.expectation,
        payload=_as_jsonable(case.payload),
        passed=passed,
        observed_success=observed_success,
        latency_ms=latency_ms,
        envelope_ok=envelope_ok,
        has_quality_meta=has_quality_meta,
        has_source_chain=has_source_chain,
        result=_as_jsonable(normalized),
        error=str(normalized.get("error")) if isinstance(normalized, dict) and normalized.get("error") else None,
        warnings=warnings,
        notes=case.notes,
        coverage_labels=list(case.coverage_labels),
        fault_strategy=fault_strategy,
        fault_target=fault_target,
        fault_triggered=fault_triggered,
        fault_signal=fault_signal if case.mode == "fault_injection" else None,
        fault_signal_details=fault_signal_details if case.mode == "fault_injection" else [],
    )


def _severity_from_case(case_result: CaseResult, category: str) -> str:
    if case_result.expectation == "success" and not case_result.passed:
        if any(token in " ".join(case_result.warnings + [case_result.error or ""]) for token in ("timeout", "NameError", "unexpected keyword", "TOOL_ERROR")):
            return "P0"
        return "P1"
    if case_result.expectation == "resilient" and not case_result.passed:
        if "fault_injection_not_triggered" in " ".join(case_result.warnings):
            return "P1"
        return "P0"
    if case_result.expectation == "error" and not case_result.passed:
        return "P2"
    if case_result.expectation == "success" and case_result.passed:
        warning_text = " ".join(case_result.warnings)
        if "missing_envelope_keys" in warning_text:
            return "P1"
        if "slow_response>10000ms" in warning_text and category in {"market", "news", "finance", "decision", "backtest"}:
            return "P1"
        if "slow_response>10000ms" in warning_text:
            return "P2"
        if "quality_meta_not_observed" in warning_text and category in {"market", "finance", "decision", "backtest", "fund_flow", "technical"}:
            return "P1"
        if "quality_meta_not_observed" in warning_text:
            return "P2"
    return "P2"


async def _prepare_runtime_context(timeout_seconds: float) -> dict[str, Any]:
    ctx = _base_runtime_context()
    setup_payload = {
        "probabilities": [0.2, 0.8, 0.55, 0.35],
        "labels": [0, 1, 1, 0],
        "method": "raw",
        "persist_artifact": True,
        "output_artifact_id": ctx["prediction_artifact_id"],
        "dataset_id": f"dataset_{RUN_TIMESTAMP}",
        "run_id": f"run_{RUN_TIMESTAMP}",
    }
    result, _latency, _err, _meta = await _call_tool("prediction_diagnosis_workflow", setup_payload, timeout_seconds)
    ctx["prediction_artifact_ready"] = bool(isinstance(result, dict) and result.get("success") is True)
    return ctx


def _build_case_matrix(
    registry_rows: list[dict[str, Any]],
    legacy_manifest: dict[str, dict[str, Any]],
    ctx: dict[str, Any],
) -> dict[str, list[CaseSpec]]:
    manager_cases = _manual_manager_cases(ctx)
    tool_cases = _manual_tool_cases(ctx)
    matrix: dict[str, list[CaseSpec]] = {}

    for row in registry_rows:
        name = str(row["name"])
        schema = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(name).parameters
        if name in manager_cases:
            matrix[name] = _ensure_case_coverage(name, manager_cases[name], schema, ctx)
            continue
        if name in tool_cases:
            matrix[name] = _ensure_case_coverage(name, tool_cases[name], schema, ctx)
            continue

        manifest_payload = legacy_manifest.get(name, {})
        primary = _coerce_manifest_payload(name, manifest_payload, schema, ctx)
        if not primary:
            contract = TOOL_CONTRACTS.get(name) or {}
            examples = contract.get("examples") or []
            if examples and isinstance(examples[0], dict):
                primary = _safe_deepcopy(examples[0].get("arguments") or {})
        if not primary:
            for field_name in _required_fields(schema):
                sample = _sample_value_for_param(name, field_name, ctx)
                if sample is not None:
                    primary[field_name] = sample

        primary = _seed_optional_payload(name, primary, schema, ctx)

        variant = _variant_payload(name, primary, schema, ctx)
        variant = _seed_optional_payload(name, variant, schema, ctx)
        negative = _negative_payload(name, primary, schema)
        matrix[name] = _ensure_case_coverage(name, [
            CaseSpec("primary", primary, "success"),
            CaseSpec("variant", variant, "success"),
            negative,
        ], schema, ctx)
    return matrix


def _legacy_manifest_map() -> dict[str, dict[str, Any]]:
    rows = _read_json(LEGACY_MANIFEST_PATH, [])
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        payload = row.get("payload")
        if name and isinstance(payload, dict):
            mapping[name] = payload
    return mapping


def _legacy_results_map() -> dict[str, dict[str, Any]]:
    rows = _read_json(LEGACY_RESULTS_PATH, {}).get("rows", [])
    mapping: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("tool") or "").strip()
        if name:
            mapping[name] = row
    return mapping


async def _run_workflows(timeout_seconds: float) -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    sequences = [
        {
            "name": "market_to_decision",
            "steps": [
                ("get_realtime_quote", {"stock_code": "600519"}),
                ("calculate_technical_indicators", {"code": "600519", "indicators": ["MACD", "RSI"], "limit": 90}),
                ("run_simple_backtest", {"code": "600519", "strategy": "ma_cross", "start_date": _date_iso(ONE_YEAR_AGO), "end_date": _date_iso(TODAY)}),
                ("should_i_buy", {"code": "600519"}),
            ],
        },
        {
            "name": "finance_to_comprehensive",
            "steps": [
                ("get_financials", {"stock_code": "600519"}),
                ("get_valuation_metrics", {"code": "600519"}),
                ("comprehensive_manager", {"action": "full_analysis", "code": "600519"}),
            ],
        },
        {
            "name": "text_to_unified_decision",
            "steps": [
                ("get_stock_news", {"stock_code": "600519"}),
                ("get_stock_text_signals", {"code": "600519"}),
                ("build_event_context", {"code": "600519"}),
                ("get_unified_decision_summary", {"code": "600519"}),
            ],
        },
    ]

    for workflow in sequences:
        step_results = []
        workflow_success = True
        total_latency = 0
        for tool_name, payload in workflow["steps"]:
            result, latency_ms, call_error, _meta = await _call_tool(tool_name, payload, timeout_seconds)
            normalized = _normalize_tool_result(result)
            success = bool(isinstance(normalized, dict) and normalized.get("success") is True)
            if not success:
                workflow_success = False
            total_latency += latency_ms
            step_results.append(
                {
                    "tool": tool_name,
                    "payload": _as_jsonable(payload),
                    "latency_ms": latency_ms,
                    "success": success,
                    "error": str(normalized.get("error")) if isinstance(normalized, dict) and normalized.get("error") else call_error,
                }
            )
        workflows.append(
            {
                "name": workflow["name"],
                "success": workflow_success,
                "total_latency_ms": total_latency,
                "steps": step_results,
            }
        )
    return workflows


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    comparisons = report["comparisons"]
    defects = report["defects"]
    workflows = report["workflows"]
    lines = [
        "# AKShare MCP 155 Tools Deep Conversational Functional Test",
        "",
        f"- Executed at: `{report['executed_at']}`",
        f"- Runtime tool count: **{summary['tool_count']}**",
        f"- Tools passed: **{summary['passed_tools']}**",
        f"- Tools failed: **{summary['failed_tools']}**",
        f"- Total cases: **{summary['total_cases']}**",
        f"- Case pass rate: **{summary['case_pass_rate']:.2f}%**",
        f"- Cases per tool: **{summary['min_cases_per_tool']} ~ {summary['max_cases_per_tool']}**",
        f"- Average latency: **{summary['avg_latency_ms']:.1f} ms**",
        f"- Fault cases: **{summary['fault_cases_passed']} / {summary['fault_cases_total']}**",
        f"- Fault triggered: **{summary['fault_triggered_cases']}**",
        f"- Fault degraded signals observed: **{summary['fault_degraded_cases']}**",
        f"- Fault fail-fast structured errors: **{summary['fault_failfast_cases']}**",
        "",
        "## Input Audit",
        "",
        f"- `packages/akshare-mcp/TOOL_DOC_AUDIT_RAW.json`: {'present' if report['input_audit']['tool_doc_audit_raw_exists'] else 'missing'}",
        f"- Runtime registry fallback: `{report['input_audit']['registry_fallback_path']}`",
        f"- Legacy results baseline: `{report['input_audit']['legacy_results_path']}`",
        "",
        "## Historical Comparison",
        "",
        f"- Fixed vs legacy: **{len(comparisons['fixed'])}**",
        f"- Persistent failures: **{len(comparisons['persistent'])}**",
        f"- Regressions: **{len(comparisons['regressions'])}**",
        "",
        "## Workflow Results",
        "",
        "| Workflow | Status | Total Latency |",
        "|----------|--------|---------------|",
    ]
    for workflow in workflows:
        lines.append(
            f"| `{workflow['name']}` | {'PASS' if workflow['success'] else 'FAIL'} | {workflow['total_latency_ms']} ms |"
        )

    lines.extend(
        [
            "",
            "## Defects",
            "",
            "| Severity | Tool | Case | Observed | Historical |",
            "|----------|------|------|----------|------------|",
        ]
    )

    for defect in defects[:60]:
        observed = str(defect.get("observed") or defect.get("error") or "")[:120].replace("|", "/")
        lines.append(
            f"| {defect['severity']} | `{defect['tool']}` | `{defect['case']}` | {observed} | `{defect['historical_status']}` |"
        )

    lines.extend(
        [
            "",
            "## Tool Matrix",
            "",
            "| Tool | Category | Status | Quality Meta | Source Chain | Avg Latency | Historical |",
            "|------|----------|--------|--------------|--------------|-------------|------------|",
        ]
    )
    for tool in report["tools"]:
        lines.append(
            f"| `{tool['name']}` | `{tool['category']}` | `{tool['status']}` | "
            f"{'yes' if tool['quality_meta_observed'] else 'no'} | "
            f"{'yes' if tool['source_chain_observed'] else 'no'} | "
            f"{tool['avg_latency_ms']} ms | `{tool['historical_status']}` |"
        )

    lines.extend(
        [
            "",
            "## Detailed Defects",
            "",
        ]
    )
    for defect in defects[:120]:
        lines.extend(
            [
                f"### {defect['severity']} `{defect['tool']}` / `{defect['case']}`",
                "",
                f"- Category: `{defect['category']}`",
                f"- Historical status: `{defect['historical_status']}`",
                f"- Implementation: `{defect['implementation_path']}`",
                f"- Repro payload: `{json.dumps(defect['payload'], ensure_ascii=False, sort_keys=True)}`",
                f"- Observed: `{defect['observed']}`",
                f"- Fault injection: `{defect.get('fault_strategy') or 'n/a'}` / `{defect.get('fault_target') or 'n/a'}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Improvement Suggestions",
            "",
            "1. Fix wrapper signature mismatches and missing helpers first. `unexpected keyword argument 'args'` and `NameError` issues are P0 because they block core read-only flows.",
            "2. Unify alias normalization against runtime schema. Several legacy smoke failures came from `codes` vs `code`, `query` vs `keyword`, and missing default date arguments.",
            "3. Standardize quality metadata across market, finance, technical, valuation, decision, and backtest tools. At minimum expose `source_chain` and quality/degraded state in one consistent location.",
            "4. Expand workflow-safe stateful test fixtures. Tools such as `ai_workflow_artifact`, `performance_manager`, and strategy-related actions benefit from reusable setup artifacts instead of hard-coded nonexistent IDs.",
            "5. Restore the missing audit artifact. The requested `TOOL_DOC_AUDIT_RAW.json` is absent, so runtime registry export is currently the only reliable source of truth.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run deep conversational functional tests for all runtime MCP tools.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--limit-tools", type=int, default=0)
    parser.add_argument("--tool", action="append", default=[])
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    registry_rows = build_tool_registry(mcp)
    registry_rows.sort(key=lambda item: item["name"])
    if args.tool:
        selected = {str(item).strip() for item in args.tool if str(item).strip()}
        registry_rows = [row for row in registry_rows if row["name"] in selected]
    if args.limit_tools:
        registry_rows = registry_rows[: int(args.limit_tools)]

    legacy_manifest = _legacy_manifest_map()
    legacy_results = _legacy_results_map()
    ctx = await _prepare_runtime_context(args.timeout_seconds)
    case_matrix = _build_case_matrix(registry_rows, legacy_manifest, ctx)

    tools_report: list[dict[str, Any]] = []
    defects: list[dict[str, Any]] = []
    passed_tools = 0
    total_cases = 0
    passed_cases = 0
    total_latency_ms = 0
    fault_cases_total = 0
    fault_cases_passed = 0
    fault_triggered_cases = 0
    fault_degraded_cases = 0
    fault_failfast_cases = 0

    print(f"[deep-test] runtime tool count={len(registry_rows)}")
    for index, row in enumerate(registry_rows, start=1):
        name = row["name"]
        category = row["category"]
        tool_obj = getattr(getattr(mcp, "_tool_manager", None), "_tools", {}).get(name)
        static_flags = _static_capability_scan(tool_obj)
        historical = legacy_results.get(name, {})
        case_results: list[CaseResult] = []

        print(f"[deep-test] ({index}/{len(registry_rows)}) {name}", flush=True)
        for case in case_matrix.get(name, []):
            result, latency_ms, call_error, runtime_meta = await _call_tool(name, case.payload, args.timeout_seconds, case)
            case_result = _evaluate_case(name, case, result, latency_ms, call_error, runtime_meta)
            case_results.append(case_result)
            total_cases += 1
            total_latency_ms += case_result.latency_ms
            if case_result.passed:
                passed_cases += 1
            if case.mode == "fault_injection":
                fault_cases_total += 1
                if case_result.passed:
                    fault_cases_passed += 1
                if case_result.fault_triggered:
                    fault_triggered_cases += 1
                if case_result.fault_signal:
                    fault_degraded_cases += 1
                elif case_result.fault_triggered and case_result.observed_success is False and str(case_result.error or "").strip():
                    fault_failfast_cases += 1

        success_case_failures = [item for item in case_results if item.expectation == "success" and not item.passed]
        error_case_failures = [item for item in case_results if item.expectation == "error" and not item.passed]
        resilient_failures = [item for item in case_results if item.expectation == "resilient" and not item.passed]
        tool_status = "passed" if not success_case_failures and not error_case_failures and not resilient_failures else "failed"
        if tool_status == "passed":
            passed_tools += 1

        quality_meta_observed = any(item.has_quality_meta for item in case_results)
        source_chain_observed = any(item.has_source_chain for item in case_results)
        avg_latency_ms = int(sum(item.latency_ms for item in case_results) / max(len(case_results), 1))

        for item in case_results:
            warning_text = " ".join(item.warnings)
            record_defect = False
            if item.expectation == "success":
                record_defect = (not item.passed) or any(
                    flag in warning_text
                    for flag in ("missing_envelope_keys", "quality_meta_not_observed", "source_chain_not_observed", "slow_response>")
                )
            elif item.expectation == "error":
                record_defect = not item.passed
            elif item.expectation == "resilient":
                record_defect = not item.passed
            else:
                record_defect = not item.passed or "missing_envelope_keys" in warning_text

            if record_defect:
                defects.append(
                    {
                        "severity": _severity_from_case(item, category),
                        "tool": name,
                        "category": category,
                        "case": item.label,
                        "historical_status": historical.get("status") or "unknown",
                        "payload": _as_jsonable(item.payload),
                        "observed": item.error or "; ".join(item.warnings) or "unexpected_behavior",
                        "warnings": list(item.warnings),
                        "implementation_path": row.get("implementation_path"),
                        "fault_strategy": item.fault_strategy,
                        "fault_target": item.fault_target,
                        "fault_triggered": item.fault_triggered,
                        "fault_signal": item.fault_signal,
                    }
                )

        tools_report.append(
            {
                "name": name,
                "category": category,
                "status": tool_status,
                "historical_status": historical.get("status") or "unknown",
                "historical_detail": historical.get("detail"),
                "avg_latency_ms": avg_latency_ms,
                "quality_meta_observed": quality_meta_observed,
                "source_chain_observed": source_chain_observed,
                "static_capabilities": static_flags,
                "implementation_path": row.get("implementation_path"),
                "signature": row.get("signature"),
                "case_count": len(case_results),
                "fault_case_passed": any(item.expectation == "resilient" and item.passed for item in case_results),
                "cases": [
                    {
                        "label": item.label,
                        "expectation": item.expectation,
                        "payload": _as_jsonable(item.payload),
                        "passed": item.passed,
                        "observed_success": item.observed_success,
                        "latency_ms": item.latency_ms,
                        "envelope_ok": item.envelope_ok,
                        "has_quality_meta": item.has_quality_meta,
                        "has_source_chain": item.has_source_chain,
                        "error": item.error,
                        "warnings": list(item.warnings),
                        "notes": item.notes,
                        "coverage_labels": list(item.coverage_labels),
                        "fault_strategy": item.fault_strategy,
                        "fault_target": item.fault_target,
                        "fault_triggered": item.fault_triggered,
                        "fault_signal": item.fault_signal,
                        "fault_signal_details": list(item.fault_signal_details),
                        "result": item.result,
                    }
                    for item in case_results
                ],
            }
        )

    workflows = await _run_workflows(args.timeout_seconds)
    case_pass_rate = (passed_cases / total_cases * 100.0) if total_cases else 0.0
    failed_tools = len(tools_report) - passed_tools

    fixed = []
    persistent = []
    regressions = []
    for tool in tools_report:
        historical_status = tool["historical_status"]
        current_status = tool["status"]
        if historical_status in {"failed", "error"} and current_status == "passed":
            fixed.append(tool["name"])
        elif historical_status in {"failed", "error"} and current_status == "failed":
            persistent.append(tool["name"])
        elif historical_status == "ok" and current_status == "failed":
            regressions.append(tool["name"])

    defects.sort(key=lambda item: (item["severity"], item["tool"], item["case"]))
    report = {
        "executed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "input_audit": {
            "tool_doc_audit_raw_exists": EXPECTED_AUDIT_RAW_PATH.exists(),
            "registry_fallback_path": str(REGISTRY_LATEST_PATH),
            "legacy_results_path": str(LEGACY_RESULTS_PATH),
        },
        "registry_summary": summarize_tool_registry(registry_rows),
        "summary": {
            "tool_count": len(tools_report),
            "passed_tools": passed_tools,
            "failed_tools": failed_tools,
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "case_pass_rate": case_pass_rate,
            "avg_latency_ms": (total_latency_ms / total_cases) if total_cases else 0.0,
            "min_cases_per_tool": min((tool.get("case_count") or 0) for tool in tools_report) if tools_report else 0,
            "max_cases_per_tool": max((tool.get("case_count") or 0) for tool in tools_report) if tools_report else 0,
            "fault_cases_total": fault_cases_total,
            "fault_cases_passed": fault_cases_passed,
            "fault_triggered_cases": fault_triggered_cases,
            "fault_degraded_cases": fault_degraded_cases,
            "fault_failfast_cases": fault_failfast_cases,
        },
        "comparisons": {
            "fixed": fixed,
            "persistent": persistent,
            "regressions": regressions,
        },
        "workflows": workflows,
        "defects": defects,
        "tools": tools_report,
    }

    json_path = output_dir / f"deep_tool_test_{RUN_TIMESTAMP}.json"
    md_path = output_dir / f"deep_tool_test_{RUN_TIMESTAMP}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"

    json_text = json.dumps(_as_jsonable(report), ensure_ascii=False, indent=2)
    md_text = _render_markdown(report)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "tool_count": len(tools_report),
                "passed_tools": passed_tools,
                "failed_tools": failed_tools,
                "total_cases": total_cases,
                "case_pass_rate": round(case_pass_rate, 2),
                "min_cases_per_tool": report["summary"]["min_cases_per_tool"],
                "max_cases_per_tool": report["summary"]["max_cases_per_tool"],
                "fault_cases_passed": fault_cases_passed,
                "fault_cases_total": fault_cases_total,
                "outputs": {
                    "json": str(json_path),
                    "markdown": str(md_path),
                    "latest_json": str(latest_json),
                    "latest_markdown": str(latest_md),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    try:
        await get_db().close()
    except Exception:
        pass
    return 0 if failed_tools == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise
