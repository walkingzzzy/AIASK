"""回测引擎 - BacktestEngine 核心类"""


from typing import List, Dict, Any, Optional, Union, Tuple
import numpy as np

from aiask_quant_core.slippage import SlippageCalculator
from .utils import _ensure_dict_list, _compute_slippage_rate, _resolve_slippage_model
from .strategies import (
    _backtest_ma_cross_jit,
    _backtest_ma_cross_with_trades_jit,
    _backtest_momentum_jit,
    _backtest_rsi_jit,
)


_SLIPPAGE_NOTE = "JIT路径使用均值化滑点估算，实际交易成本可能偏高"
_ARRIVAL_PRICE_POLICY_BPS = {
    "close_proxy": 1.0,
    "close": 1.0,
    "same_close_proxy": 1.2,
    "twap_proxy": 1.2,
    "twap": 1.2,
    "vwap_proxy": 0.8,
    "vwap": 0.8,
    "next_open_proxy": 2.0,
    "next_open": 2.0,
    "event_open_proxy": 2.5,
}
_CAPACITY_BUCKET_BPS = {
    "mega": -2.0,
    "large": 0.0,
    "mid": 2.0,
    "small": 5.0,
    "micro": 8.0,
}
_POSITION_ASSUMPTION_PCT = {
    "single_name_full_notional": 1.0,
    "single_name": 1.0,
    "equal_weight_proxy": 0.2,
    "equal_weight": 0.2,
    "half_notional": 0.5,
}


def _normalize_portfolio_weight_scheme(params: Optional[Dict[str, Any]], code_count: int) -> str:
    args = dict(params or {})
    scheme = str(args.get("target_weight_scheme") or "").strip().lower()
    if scheme in {"equal", "equal_weight_proxy"}:
        return "equal_weight"
    if scheme == "target_weight_map":
        return "target_weight_map"
    if scheme in {"single_name", "single_name_full_notional"}:
        return "single_name"
    return "equal_weight" if code_count > 1 else "single_name"


def _resolve_portfolio_weights(codes: List[str], params: Optional[Dict[str, Any]]) -> tuple[dict[str, float], str, str]:
    normalized_codes = [str(code or "").strip() for code in list(codes or []) if str(code or "").strip()]
    if not normalized_codes:
        return {}, "single_name", "single_name"

    args = dict(params or {})
    scheme = _normalize_portfolio_weight_scheme(args, len(normalized_codes))
    allocation_mode = "equal_weight"
    weights: dict[str, float] = {}

    if scheme == "single_name":
        weights = {normalized_codes[0]: 1.0}
        allocation_mode = "single_name"
    elif scheme == "target_weight_map":
        raw_map = dict(args.get("target_weight_map") or {})
        for code in normalized_codes:
            try:
                value = float(raw_map.get(code, 0.0) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                weights[code] = value
        total = float(sum(weights.values()))
        if total > 0:
            weights = {code: float(value) / total for code, value in weights.items()}
            allocation_mode = "target_weight_map"
        else:
            scheme = "equal_weight"

    if scheme == "equal_weight":
        equal_weight = 1.0 / float(len(normalized_codes))
        weights = {code: equal_weight for code in normalized_codes}
        allocation_mode = "equal_weight"

    max_position_pct = _safe_float(args.get("max_position_pct"), 0.0)
    if max_position_pct > 0:
        weights = {code: min(weight, max_position_pct) for code, weight in weights.items() if weight > 0}
        total = float(sum(weights.values()))
        if total > 1.0 and total > 0:
            weights = {code: float(value) / total for code, value in weights.items()}
    return weights, scheme, allocation_mode


def _build_buy_and_hold_masks(length: int) -> tuple[np.ndarray, np.ndarray]:
    entry = np.zeros(length, dtype=bool)
    exit_ = np.zeros(length, dtype=bool)
    if length >= 2:
        entry[0] = True
        exit_[length - 2] = True
    return entry, exit_


def _build_portfolio_strategy_masks(
    strategy: str,
    klines: List[Dict[str, Any]],
    closes: np.ndarray,
    volumes: np.ndarray,
    params: Dict[str, Any],
) -> Optional[Tuple[np.ndarray, np.ndarray, Optional[List[Dict[str, Any]]]]]:
    normalized_strategy = str(strategy or "").strip().lower()
    if normalized_strategy == "buy_and_hold":
        entry, exit_ = _build_buy_and_hold_masks(len(closes))
        return entry, exit_, None

    from .strategy_registry import StrategyRegistry as _Reg

    inst, _execution_semantic_mode = _Reg.create_runtime_strategy(normalized_strategy, params)
    if inst is not None:
        signal_events = None
        if hasattr(inst, 'generate_signal_events_from_klines'):
            signal_events = inst.generate_signal_events_from_klines(klines)
        elif hasattr(inst, 'generate_signal_events'):
            signal_events = inst.generate_signal_events(closes, volumes)
        if hasattr(inst, 'generate_entry_exit_masks_from_klines'):
            entry_mask, exit_mask = inst.generate_entry_exit_masks_from_klines(klines)
        else:
            entry_mask, exit_mask = inst.generate_entry_exit_masks(closes, volumes)
        return entry_mask, exit_mask, signal_events

    masks = _build_strategy_masks(normalized_strategy, closes, params, volumes=volumes, klines=klines)
    if masks is not None:
        return masks[0], masks[1], None

    return None


def _summarize_portfolio_equity(equity: np.ndarray, initial_capital: float) -> tuple[float, float, float]:
    final_capital = float(equity[-1]) if equity.size else float(initial_capital)
    total_return = (final_capital - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    max_dd = 0.0
    if equity.size:
        peak = float(equity[0])
        for value in equity:
            if value > peak:
                peak = float(value)
            if peak > 0:
                drawdown = (peak - float(value)) / peak
                if drawdown > max_dd:
                    max_dd = drawdown

    sharpe = 0.0
    if equity.size > 1:
        prev = equity[:-1]
        curr = equity[1:]
        valid = prev > 0
        if np.any(valid):
            returns = (curr[valid] - prev[valid]) / prev[valid]
            returns = returns[np.isfinite(returns)]
            if returns.size > 1:
                std = float(np.std(returns))
                if std > 0:
                    annual_ret = float(np.mean(returns)) * 252.0
                    annual_std = std * np.sqrt(252.0)
                    sharpe = float((annual_ret - 0.02) / annual_std)
    return final_capital, float(total_return), float(max_dd), float(sharpe)

from ._engine_support import (
    _build_strategy_masks,
    _build_tradability_mask,
    _estimate_implementation_shortfall,
    _finalize_backtest_payload,
    _resolve_order_fill,
    _round_down_lot,
    _safe_float,
    _simulate_trades_from_masks,
)

from aiask_quant_core._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'engine_parts',
    'class BacktestEngine:\n',
    ['runtime.py', 'execution.py', 'analytics.py', 'artifacts.py'],
    future_annotations=False,
)



backtest_engine = BacktestEngine()
