from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import akshare as ak
import numpy as np
import pandas as pd

from strategy_factory.api.contracts import FactoryBacktestAssumptions
from strategy_factory.application.research_protocol_contract import (
    build_research_validation_contract,
)

from ._validation_support import (
    hansen_spa_test,
    probability_of_backtest_overfitting,
    white_reality_check,
)
from .backtest.engine import BacktestEngine
from .validation import PurgedKFoldCV, WalkForwardValidator


MONTHLY_CONTRIBUTION = 10_000.0
MAIN_SCENARIO_SLIPPAGE_BPS = 5.0
CONTROL_SCENARIO_SLIPPAGE_BPS = 0.0
DEFAULT_END_DATE = "2026-04-10"
DEFAULT_TAKE_PROFIT_GRID = (0.15, 0.20, 0.25, 0.30)
DEFAULT_ROTATION_LOOKBACK_MONTHS = (3, 6, 9)
DEFAULT_ROTATION_TREND_WINDOWS = (100, 150)
DEFAULT_LEVERAGE_GRID = (1.5, 2.0)
FUTURES_FALLBACK_COST = {
    "slippage_bps": 2.0,
    "fixed_fee_per_contract": 20.0,
    "margin_rate": 0.12,
    "contract_multiplier": 300,
}
ROOT_REPORT_MD = "510300沪深300ETF定投回测正式报告.md"
ROOT_REPORT_PDF = "510300沪深300ETF定投回测正式报告_图表版.pdf"


def _discover_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "packages").exists() and (parent / "scripts").exists():
            return parent
    return current.parents[6]


REPO_ROOT = _discover_repo_root()
REPORTS_ROOT = REPO_ROOT / "reports" / "backtests"
V3_REPORT_ROOT = REPORTS_ROOT / "510300_v3"
V3_RUNS_ROOT = V3_REPORT_ROOT / "runs"
LEGACY_SCRIPT_PATH = REPO_ROOT / "scripts" / "backtest_510300_etf_dca.py"
BASELINE_REFERENCE_DIR = REPORTS_ROOT


@dataclass(frozen=True)
class ResearchProtocol:
    end_date: str = DEFAULT_END_DATE
    baseline_slippage_bps: float = MAIN_SCENARIO_SLIPPAGE_BPS
    stress_slippage_bps: float = 10.0
    train_months: int = 60
    test_months: int = 12
    step_months: int = 12
    enable_cash_sleeves: bool = False
    enable_enhancements: bool = False
    schedule_clock: str = "prev_close_signal_next_open_execute_same_close_cash_rebuild"
    baseline_reference: str = ""


@dataclass(frozen=True)
class ResolvedInstrument:
    category: str
    keyword_group: str
    code: str
    symbol: str
    name: str
    source: str
    history_rows: int
    first_trade_date: str
    last_trade_date: str
    median_amount_60d: float
    candidates: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None


@dataclass(frozen=True)
class CostScenarioResult:
    scenario: str
    slippage_bps: float
    commission_rate: float
    sell_tax_rate: float
    strategy_metrics: dict[str, dict[str, Any]]
    summary_source: str


@dataclass(frozen=True)
class FoldResult:
    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    selected_candidates: dict[str, dict[str, Any]]
    oos_metrics: dict[str, dict[str, Any]]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CashSleeveResult:
    family: str
    selected_instrument: dict[str, Any] | None
    metrics: dict[str, Any]
    scheduler_audit: dict[str, Any]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EnhancementFamilyResult:
    family: str
    selected_candidate: dict[str, Any] | None
    aggregate_oos: dict[str, Any]
    validation: dict[str, Any]
    candidate_count: int
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SelectionGateResult:
    family: str
    passed: bool
    oos_cagr: float
    benchmark_oos_cagr: float
    oos_max_drawdown: float
    benchmark_oos_max_drawdown: float
    selected_candidate: dict[str, Any] | None
    reason: str


@dataclass(frozen=True)
class FinalRecommendation:
    decision: str
    selected_family: str | None
    selected_candidate: dict[str, Any] | None
    summary: str
    passed_gate: bool


@dataclass
class StrategyArtifact:
    name: str
    metrics: dict[str, Any]
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    daily_returns: pd.Series
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BundleArtifacts:
    bundle_dir: Path
    summary_path: Path
    markdown_path: Path
    csv_dir: Path
    latest_json_path: Path
    latest_markdown_path: Path
    latest_pdf_path: Path


def build_default_research_validation_contract(
    protocol: ResearchProtocol | None = None,
) -> dict[str, Any]:
    resolved = protocol or ResearchProtocol()
    return build_research_validation_contract(
        walk_forward_config={
            "train_months": int(resolved.train_months),
            "test_months": int(resolved.test_months),
            "step_months": int(resolved.step_months),
        },
        baseline_reference={
            "name": str(resolved.baseline_reference or "510300_baseline_reference"),
            "end_date": str(resolved.end_date),
            "baseline_slippage_bps": float(resolved.baseline_slippage_bps),
            "stress_slippage_bps": float(resolved.stress_slippage_bps),
        },
        cash_sleeve_policy={
            "enabled": bool(resolved.enable_cash_sleeves),
            "schedule_clock": str(resolved.schedule_clock),
        },
        cost_sensitivity_grid={
            "base_slippage_bps": float(resolved.baseline_slippage_bps),
            "stress_slippage_bps": float(resolved.stress_slippage_bps),
            "main_scenario_slippage_bps": float(MAIN_SCENARIO_SLIPPAGE_BPS),
            "control_scenario_slippage_bps": float(CONTROL_SCENARIO_SLIPPAGE_BPS),
        },
        capacity_execution={
            "futures_fallback_cost": dict(FUTURES_FALLBACK_COST),
            "schedule_clock": str(resolved.schedule_clock),
        },
        multiple_testing={
            "mode": "formal_runtime",
            "white_reality_check_enabled": True,
            "hansen_spa_enabled": True,
            "pbo_enabled": True,
        },
        admission_thresholds={
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_plus_representative",
                "primary_validation_layer": "target",
            },
            "business_admission_gate": {
                "benchmark_return_multiple_min": 2.0,
                "benchmark_drawdown_mode": "lte",
                "cost_sensitivity_required_bps": [0.0, 5.0, 10.0],
                "cash_sleeve_required": True,
            },
            "take_profit_grid": list(DEFAULT_TAKE_PROFIT_GRID),
            "rotation_lookback_months": list(DEFAULT_ROTATION_LOOKBACK_MONTHS),
            "rotation_trend_windows": list(DEFAULT_ROTATION_TREND_WINDOWS),
            "leverage_grid": list(DEFAULT_LEVERAGE_GRID),
        },
        family_holding_bucket={
            "family": "510300_default",
            "holding_bucket": "medium",
            "enable_enhancements": bool(resolved.enable_enhancements),
        },
        field_provenance={
            "walk_forward_config": "derived",
            "baseline_reference": "derived",
            "cash_sleeve_policy": "derived",
            "cost_sensitivity_grid": "derived",
            "capacity_execution": "derived",
            "multiple_testing": "derived",
            "admission_thresholds": "derived",
            "family_holding_bucket": "derived",
        },
    )


class _ProxyBypass:
    def __enter__(self):
        self._backup = {
            "HTTP_PROXY": os.getenv("HTTP_PROXY"),
            "HTTPS_PROXY": os.getenv("HTTPS_PROXY"),
            "ALL_PROXY": os.getenv("ALL_PROXY"),
            "http_proxy": os.getenv("http_proxy"),
            "https_proxy": os.getenv("https_proxy"),
            "all_proxy": os.getenv("all_proxy"),
            "NO_PROXY": os.getenv("NO_PROXY"),
            "no_proxy": os.getenv("no_proxy"),
        }
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ.pop(key, None)
        return self

    def __exit__(self, exc_type, exc, tb):
        for key, value in self._backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        return False


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _ccy(value: float) -> str:
    return f"{value:,.2f}"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(value).date())
    if isinstance(value, np.generic):
        return value.item()
    if dataclass_is_instance(value):
        return asdict(value)
    raise TypeError(f"unsupported type: {type(value)!r}")


def dataclass_is_instance(value: Any) -> bool:
    return hasattr(value, "__dataclass_fields__")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


@lru_cache(maxsize=1)
def _load_legacy_module():
    spec = importlib.util.spec_from_file_location("backtest_510300_etf_dca_legacy", LEGACY_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load legacy module from {LEGACY_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _load_fund_universe() -> pd.DataFrame:
    with _ProxyBypass():
        universe = ak.fund_name_em().copy()
    universe["基金代码"] = universe["基金代码"].astype(str).str.zfill(6)
    universe["基金简称"] = universe["基金简称"].astype(str)
    universe["基金类型"] = universe["基金类型"].astype(str)
    return universe


def _normalize_symbol(code: str) -> str:
    normalized = str(code or "").strip()
    if normalized.startswith(("sh", "sz")):
        return normalized
    if normalized.startswith(("5", "6", "9")):
        return f"sh{normalized}"
    return f"sz{normalized}"


def _normalize_price_frame(frame: pd.DataFrame, *, end_date: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount"])
    mapping = {
        "日期": "date",
        "date": "date",
        "开盘价": "open",
        "open": "open",
        "最高价": "high",
        "high": "high",
        "最低价": "low",
        "low": "low",
        "收盘价": "close",
        "close": "close",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "amount",
        "amount": "amount",
    }
    normalized = frame.rename(columns=mapping).copy()
    normalized["date"] = pd.to_datetime(normalized["date"])
    for column in ("open", "high", "low", "close", "volume", "amount"):
        if column not in normalized:
            normalized[column] = 0.0
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.loc[normalized["date"] <= pd.Timestamp(end_date)]
    normalized = normalized.loc[:, ["date", "open", "high", "low", "close", "volume", "amount"]]
    normalized = normalized.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    if normalized["amount"].eq(0).all():
        normalized["amount"] = normalized["close"].fillna(0.0) * normalized["volume"].fillna(0.0)
    return normalized


def _normalize_dividend_frame(frame: pd.DataFrame, *, end_date: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["ex_date", "per_share_dividend"])
    normalized = frame.copy()
    if "日期" in normalized.columns:
        normalized["ex_date"] = pd.to_datetime(normalized["日期"])
    elif "ex_date" in normalized.columns:
        normalized["ex_date"] = pd.to_datetime(normalized["ex_date"])
    else:
        return pd.DataFrame(columns=["ex_date", "per_share_dividend"])
    dividend_column = "累计分红" if "累计分红" in normalized.columns else "per_share_dividend"
    normalized = normalized.loc[normalized["ex_date"] <= pd.Timestamp(end_date), ["ex_date", dividend_column]].copy()
    normalized[dividend_column] = pd.to_numeric(normalized[dividend_column], errors="coerce").fillna(0.0)
    if dividend_column == "累计分红":
        normalized["per_share_dividend"] = normalized[dividend_column].diff().fillna(normalized[dividend_column])
    else:
        normalized["per_share_dividend"] = normalized[dividend_column]
    return normalized.loc[:, ["ex_date", "per_share_dividend"]].sort_values("ex_date").reset_index(drop=True)


def _fetch_etf_history(code: str, *, end_date: str) -> pd.DataFrame:
    symbol = _normalize_symbol(code)
    with _ProxyBypass():
        frame = ak.fund_etf_hist_sina(symbol=symbol)
    return _normalize_price_frame(frame, end_date=end_date)


def _fetch_etf_dividends(code: str, *, end_date: str) -> pd.DataFrame:
    symbol = _normalize_symbol(code)
    try:
        with _ProxyBypass():
            frame = ak.fund_etf_dividend_sina(symbol=symbol)
    except Exception:
        frame = pd.DataFrame()
    return _normalize_dividend_frame(frame, end_date=end_date)


def _fetch_futures_history(symbol: str, *, end_date: str) -> pd.DataFrame:
    with _ProxyBypass():
        frame = ak.futures_main_sina(symbol=symbol)
    return _normalize_price_frame(frame, end_date=end_date)


def _median_amount_60(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    window = frame.tail(60)
    return float(pd.to_numeric(window["amount"], errors="coerce").fillna(0.0).median())


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float, str]:
    return (
        -_safe_float(candidate.get("history_rows")),
        -_safe_float(candidate.get("median_amount_60d")),
        str(candidate.get("code") or ""),
    )
