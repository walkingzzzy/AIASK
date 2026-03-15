"""Shared submission-stage quality gate evaluation.

This module centralizes the Gate-3 quality evaluation used by both
strategy_manager submit/recheck flows and strategy_factory submitter.
"""

from __future__ import annotations

from typing import Any, Dict

from .constants import QUALITY_GATE_THRESHOLDS
from .quality_reporting import maybe_grant_provisional_incubation, normalize_quality_gate_result
from .targets import _extract_target_codes_from_payload


async def run_submission_quality_gate(
    db,
    strategy: dict,
    *,
    validation_report: dict | None = None,
    risk_report: dict | None = None,
    backtest_metrics: dict | None = None,
) -> Dict[str, Any]:
    """Run the submission-stage quality gate and return the final authority result."""
    try:
        from ..validation import (
            WalkForwardValidator,
            PurgedKFoldCV,
            bootstrap_ic_ci,
        )
        from ..backtest.strategy_registry import StrategyRegistry
        import numpy as np

        strategy_type = strategy.get("strategy_type", "")
        klass = StrategyRegistry.get(strategy_type)
        if klass is None:
            return {"passed": False, "reason": f"Strategy type not in registry: {strategy_type}"}

        instance = klass()
        strategy_params = strategy.get("params") or {}
        instance.set_parameters(strategy_params)

        target_codes = _extract_target_codes_from_payload(strategy)
        codes = list(dict.fromkeys([*target_codes, "600519", "000858", "601318", "600036", "000333"]))
        all_closes = []
        for code in codes:
            klines = await db.get_klines(code, limit=500)
            if klines and len(klines) >= 100:
                closes = np.array([float(k.get("close", 0)) for k in klines])
                all_closes.append(closes)

        if not all_closes:
            return {"passed": False, "reason": "Insufficient kline data for quality gate"}

        min_len = min(len(c) for c in all_closes)
        n_stocks = len(all_closes)
        factor_panel = np.zeros((min_len, n_stocks))
        return_panel = np.zeros((min_len, n_stocks))
        for j, closes in enumerate(all_closes):
            closes = closes[:min_len]
            signals = instance.generate_signals(closes)
            factor_panel[:, j] = signals[:min_len].astype(float)
            for i in range(min_len - 1):
                return_panel[i, j] = (closes[i + 1] - closes[i]) / closes[i] if closes[i] > 0 else 0

        flat_factors = factor_panel.flatten()
        flat_returns = return_panel.flatten()

        reasons = []

        # 1. Walk-Forward OOS IC IR
        _wf_min = QUALITY_GATE_THRESHOLDS["walk_forward_ic_ir_min"]
        try:
            wf = WalkForwardValidator(train_window=60, test_window=20, step=20)
            wf_summary = wf.validate(factor_panel, return_panel)
            wf_sharpe = wf_summary.oos_ic_ir
            if wf_sharpe < _wf_min:
                reasons.append(f"Walk-Forward IC IR {wf_sharpe:.3f} < {_wf_min}")
        except Exception as e:
            reasons.append(f"Walk-Forward error: {e}")
            wf_sharpe = 0

        # 2. Purged K-Fold IC
        _pkf_min = QUALITY_GATE_THRESHOLDS["purged_kfold_ic_min"]
        try:
            pkf = PurgedKFoldCV(n_folds=5, purge_gap=5)
            pkf_summary = pkf.validate(factor_panel, return_panel)
            pkf_ic = pkf_summary.oos_ic_mean
            if pkf_ic < _pkf_min:
                reasons.append(f"Purged K-Fold IC {pkf_ic:.4f} < {_pkf_min}")
        except Exception as e:
            reasons.append(f"Purged K-Fold error: {e}")
            pkf_ic = 0

        # 3. Bootstrap CI lower bound
        _bs_min = QUALITY_GATE_THRESHOLDS["bootstrap_ci_lower_min"]
        try:
            bs = bootstrap_ic_ci(flat_factors, flat_returns)
            ci_lower = bs.get("ci_lower", 0)
            if ci_lower < _bs_min:
                reasons.append(f"Bootstrap CI lower {ci_lower:.4f} < {_bs_min}")
        except Exception as e:
            reasons.append(f"Bootstrap error: {e}")
            ci_lower = 0

        # 4. Parameter sensitivity
        _sens_max = QUALITY_GATE_THRESHOLDS["param_sensitivity_max"]
        sensitivity = 0.0
        try:
            ref_closes = all_closes[0][:min_len]
            ref_returns = return_panel[:, 0]
            base_signals = instance.generate_signals(ref_closes)[:min_len]
            base_ic = float(np.corrcoef(base_signals.astype(float), ref_returns)[0, 1])
            if not np.isnan(base_ic) and abs(base_ic) > 0.001:
                variations = []
                for key, val in strategy_params.items():
                    if isinstance(val, (int, float)) and val != 0:
                        for mult in [0.8, 1.2]:
                            test_params = {**strategy_params, key: type(val)(val * mult)}
                            test_instance = klass()
                            test_instance.set_parameters(test_params)
                            test_signals = test_instance.generate_signals(ref_closes)[:min_len]
                            test_ic = float(np.corrcoef(test_signals.astype(float), ref_returns)[0, 1])
                            if not np.isnan(test_ic):
                                variations.append(abs(test_ic - base_ic) / abs(base_ic))
                if variations:
                    sensitivity = float(np.mean(variations))
            if sensitivity > _sens_max:
                reasons.append(f"Parameter sensitivity {sensitivity:.2%} > {_sens_max:.0%}")
        except Exception as e:
            reasons.append(f"Sensitivity error: {e}")

        # 5. Multi-period robustness
        period_robustness = {"first_half_ic": 0.0, "second_half_ic": 0.0, "ic_consistency": 0.0}
        try:
            half = min_len // 2
            if half >= 50:
                first_factors = factor_panel[:half, :].flatten()
                first_returns = return_panel[:half, :].flatten()
                second_factors = factor_panel[half:, :].flatten()
                second_returns = return_panel[half:, :].flatten()
                ic_first = float(np.corrcoef(first_factors, first_returns)[0, 1])
                ic_second = float(np.corrcoef(second_factors, second_returns)[0, 1])
                if np.isnan(ic_first):
                    ic_first = 0.0
                if np.isnan(ic_second):
                    ic_second = 0.0
                period_robustness = {
                    "first_half_ic": round(ic_first, 4),
                    "second_half_ic": round(ic_second, 4),
                    "ic_consistency": round(min(ic_first, ic_second), 4),
                }
                if ic_first < -0.02 or ic_second < -0.02:
                    reasons.append(
                        f"Multi-period IC inconsistent: first_half={ic_first:.4f}, second_half={ic_second:.4f} (both must be >= -0.02)"
                    )
                elif ic_first > 0.01 and ic_second < -0.01:
                    reasons.append(
                        f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                    )
                elif ic_first < -0.01 and ic_second > 0.01:
                    reasons.append(
                        f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                    )
        except Exception as e:
            reasons.append(f"Multi-period robustness error: {e}")

        passed = len(reasons) == 0
        gate = {
            "passed": passed,
            "wf_ic_ir": round(wf_sharpe, 4),
            "pkf_ic": round(pkf_ic, 4),
            "bootstrap_ci_lower": round(ci_lower, 4),
            "param_sensitivity": round(sensitivity, 4),
            "period_robustness": period_robustness,
            "reasons": reasons,
        }
        normalized = normalize_quality_gate_result(gate)
        return maybe_grant_provisional_incubation(
            strategy,
            normalized,
            validation_report=validation_report,
            risk_report=risk_report,
            backtest_metrics=backtest_metrics,
        )
    except Exception as e:
        return normalize_quality_gate_result({"passed": False, "reason": str(e)})
