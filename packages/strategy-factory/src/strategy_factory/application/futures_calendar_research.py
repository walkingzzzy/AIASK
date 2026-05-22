"""Futures calendar-spread research adapter for SC crude oil.

This module keeps the futures research path separate from the stock-oriented
factory backtest runtime. It rebuilds the SC curve from local spread inputs,
runs directional / spread backtests, produces Gate-3 candidate bundles, and
prepares a structured research_context payload that can be injected into the
existing StrategyLLMProvider.
"""


from __future__ import annotations

import asyncio
import json
import math
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd


def _resolve_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "package.json").exists() and (parent / "docs").is_dir():
            return parent
    return current.parents[5]


def _resolve_sc_pack_artifact(pattern: str, fallback: str) -> Path:
    matches = sorted(DEFAULT_SC_PACK_DIR.glob(pattern))
    if matches:
        return matches[0]
    return DEFAULT_SC_PACK_DIR / fallback


DEFAULT_SC_PACK_DIR = _resolve_repo_root() / "docs" / "原油" / "ai_ready"
DEFAULT_SC_DATA_PATH = _resolve_sc_pack_artifact(
    "tables/timeseries/dataset_*_sc_spread_timeseries_all_daily.csv",
    "tables/timeseries/dataset_18_sc_spread_timeseries_all_daily.csv",
)
DEFAULT_SC_MEMO_PATH = _resolve_sc_pack_artifact(
    "strategy_notes/doc_*_crude_oil_strategy_memo.md",
    "strategy_notes/doc_05_crude_oil_strategy_memo.md",
)
DEFAULT_SC_NOTES_PATH = _resolve_sc_pack_artifact(
    "strategy_notes/doc_*_sc_spread_data_notes.md",
    "strategy_notes/doc_07_sc_spread_data_notes.md",
)
DEFAULT_OUTPUT_DIR = DEFAULT_SC_PACK_DIR / "outputs" / "sc_calendar_research"
CAPITAL_BUCKETS = (1_000_000.0, 5_000_000.0, 10_000_000.0, 30_000_000.0, 100_000_000.0)
GENERALIZATION_UNDERLYINGS = (
    ("I", "铁矿石"),
    ("EC", "集运"),
    ("CU", "沪铜"),
    ("AL", "沪铝"),
    ("ZN", "沪锌"),
    ("NI", "沪镍"),
)
_EMPTY_VALUES = (None, "", [], {})


@dataclass(frozen=True)
class ExecutionProfile:
    commission_rate: float
    slippage_bps: float
    market_impact_bps: float
    margin_rate: float
    contract_multiplier: int
    capacity_participation_rate: float
    liquidity_bucket: str
    max_contracts_per_rebalance: int
    liquidity_reference_contracts: int
    far_month_liquidity_haircut: float
    margin_budget_fraction: float
    drawdown_budget_fraction: float
    market_ruleset: str = "cn_futures"


@dataclass(frozen=True)
class TrendConfig:
    leg_month: int
    carry_threshold: float
    volatility_cap: float
    price_to_ma60_cap: float
    stop_loss_pct: float
    near_premium_floor: float = -2.0
    exit_premium_floor: float = -3.0
    ma_fast_window: int = 20
    ma_slow_window: int = 60
    slope_window: int = 10

    @property
    def family_name(self) -> str:
        return "trend"

    @property
    def strategy_code(self) -> str:
        carry_token = str(self.carry_threshold).replace(".", "p")
        vol_token = str(self.volatility_cap).replace(".", "p")
        stop_token = str(self.stop_loss_pct).replace(".", "p")
        return f"trend_m{self.leg_month}_carry{carry_token}_vol{vol_token}_stop{stop_token}"


@dataclass(frozen=True)
class SpreadConfig:
    leg_name: str
    entry_z_low: float
    entry_z_high: float
    exit_z: float
    stop_move: float
    slope_floor: float
    max_holding_days: int = 40
    require_price_trend: bool = True
    z_window: int = 40
    near_premium_floor: float = -2.0
    exit_premium_floor: float = -3.0

    @property
    def family_name(self) -> str:
        return "spread"

    @property
    def strategy_code(self) -> str:
        entry_low_token = str(self.entry_z_low).replace(".", "p").replace("-", "n")
        entry_high_token = str(self.entry_z_high).replace(".", "p").replace("-", "n")
        exit_token = str(self.exit_z).replace(".", "p").replace("-", "n")
        stop_token = str(abs(self.stop_move)).replace(".", "p")
        hold_token = str(int(self.max_holding_days))
        trend_token = "trend" if self.require_price_trend else "carry"
        return (
            f"spread_{self.leg_name}_band{entry_low_token}_to_{entry_high_token}"
            f"_exit{exit_token}_stop{stop_token}_hold{hold_token}_{trend_token}"
        )


@dataclass(frozen=True)
class StrategyResult:
    family: str
    strategy_code: str
    name: str
    config: dict[str, Any]
    execution_profile: dict[str, Any]
    summary: dict[str, Any]
    regime_panel: dict[str, Any]
    capacity_panel: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    candidate: dict[str, Any]
    raw_dsl: dict[str, Any]
    compiled_dsl: dict[str, Any]


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


def _normalize_contract_code(contract_code: str) -> str:
    token = str(contract_code or "").strip().lower()
    if token:
        return token
    return "sc0000"


def _shift_contract_code(contract_code: str, months: int) -> str:
    normalized = _normalize_contract_code(contract_code)
    prefix = "".join(ch for ch in normalized if not ch.isdigit()) or "sc"
    digits = "".join(ch for ch in normalized if ch.isdigit())
    if len(digits) < 4:
        return normalized
    year = 2000 + int(digits[:2])
    month = int(digits[2:4])
    absolute_month = (year * 12 + (month - 1)) + int(months)
    shifted_year = absolute_month // 12
    shifted_month = absolute_month % 12 + 1
    return f"{prefix}{str(shifted_year % 100).zfill(2)}{str(shifted_month).zfill(2)}"


def _annualized_return(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    initial = _safe_float(equity.iloc[0], 0.0)
    final = _safe_float(equity.iloc[-1], 0.0)
    if initial <= 0 or final <= 0:
        return -1.0
    periods = max(len(equity), 1)
    return float((final / initial) ** (252.0 / periods) - 1.0)


def _sharpe_ratio(returns: pd.Series, annualization: float = 252.0) -> float:
    series = pd.Series(returns).replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < 2:
        return 0.0
    std = float(series.std(ddof=1) or 0.0)
    if std <= 1e-12:
        return 0.0
    return float(series.mean() / std * math.sqrt(annualization))


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_peak = equity.cummax().replace(0.0, np.nan)
    drawdown = equity.div(running_peak).replace([np.inf, -np.inf], np.nan) - 1.0
    return float(drawdown.min(skipna=True) or 0.0)


def _trade_win_rate(trades: list[dict[str, Any]]) -> float:
    closed = [trade for trade in trades if trade.get("status") == "closed"]
    if not closed:
        return 0.0
    wins = sum(1 for trade in closed if _safe_float(trade.get("net_pnl")) > 0)
    return float(wins / len(closed))


def _forward_sharpe_5d(forward_returns: pd.Series) -> float:
    return _sharpe_ratio(forward_returns, annualization=252.0 / 5.0)


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body_lines = []
    for row in rows:
        body_lines.append(
            "| "
            + " | ".join(str(row.get(key, "")) for _, key in columns)
            + " |"
        )
    return "\n".join([header, divider, *body_lines])


def _round_dict_values(payload: dict[str, Any], *, digits: int = 6) -> dict[str, Any]:
    rounded: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, float):
            rounded[key] = round(value, digits)
        elif isinstance(value, dict):
            rounded[key] = _round_dict_values(value, digits=digits)
        elif isinstance(value, list):
            rounded[key] = [
                _round_dict_values(item, digits=digits) if isinstance(item, dict) else round(item, digits) if isinstance(item, float) else item
                for item in value
            ]
        else:
            rounded[key] = value
    return rounded


def _ensure_output_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _to_ohlcv_projection(series: pd.Series) -> pd.DataFrame:
    close = pd.Series(series).astype(float)
    open_ = close.shift(1).fillna(close)
    high = pd.concat([open_, close], axis=1).max(axis=1)
    low = pd.concat([open_, close], axis=1).min(axis=1)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(len(close), 1.0),
        }
    )


def _load_optional_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'futures_calendar_research_parts',
    'class FuturesCalendarResearchAdapter:\n',
    ['data_loading.py', 'feature_engineering.py', 'evaluation.py', 'reporting.py', 'part_5.py'],
    future_annotations=True,
)



def run_sc_calendar_research(
    *,
    data_path: Path = DEFAULT_SC_DATA_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    enable_online_generalization: bool = False,
) -> dict[str, Any]:
    adapter = FuturesCalendarResearchAdapter(
        data_path=data_path,
        output_dir=output_dir,
    )
    return asyncio.run(
        adapter.run(enable_online_generalization=enable_online_generalization)
    )


__all__ = [
    "CAPITAL_BUCKETS",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_SC_PACK_DIR",
    "DEFAULT_SC_DATA_PATH",
    "FuturesCalendarResearchAdapter",
    "run_sc_calendar_research",
]
