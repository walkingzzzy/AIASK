"""Risk manager tools: VaR, stress test, and exposure analysis."""

from __future__ import annotations

import json
from typing import Any, List

import numpy as np

from ...storage import get_db
from ...utils import fail, normalize_code, ok


def _normalize_kwargs(kwargs: dict) -> dict:
    """Merge kwargs payload when passed as kwargs='{"k": "v"}' or kwargs={...}."""
    raw = kwargs.get("kwargs")
    if isinstance(raw, dict):
        kwargs = {**kwargs, **raw}
    elif isinstance(raw, str):
        try:
            extra = json.loads(raw or "{}")
            if isinstance(extra, dict):
                kwargs = {**kwargs, **extra}
        except Exception:
            pass
    return kwargs


def _safe_portfolio_id(value: Any) -> int | None | Any:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _parse_list_param(value: Any) -> list:
    """Normalize list-like inputs: list / json-string / comma-string."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [item.strip() for item in text.split(",") if item.strip()]
    return [value]


def _parse_codes_weights(kwargs: dict) -> tuple[list[str], list[float], str | None]:
    """Parse codes/weights and normalize weights to sum to 1."""
    raw_codes = _parse_list_param(kwargs.get("codes"))
    codes = [normalize_code(str(c)) for c in raw_codes if str(c).strip()]
    if not codes:
        return [], [], None

    raw_weights = _parse_list_param(kwargs.get("weights"))
    if not raw_weights:
        return codes, [1.0 / len(codes)] * len(codes), None

    try:
        weights = [float(w) for w in raw_weights]
    except Exception:
        return [], [], "weights parse failed; numeric list required"

    if len(weights) != len(codes):
        return [], [], "codes and weights length mismatch"
    if any(w < 0 for w in weights):
        return [], [], "weights cannot be negative"

    total = float(sum(weights))
    if total <= 0:
        return [], [], "weights sum must be > 0"

    weights = [w / total for w in weights]
    return codes, weights, None


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_float(keys: list[str], *sources: dict | None, positive_only: bool = False) -> float | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key not in source:
                continue
            value = _safe_float(source.get(key), None)
            if value is None:
                continue
            if positive_only and value <= 0:
                continue
            return float(value)
    return None


def _format_pct(ratio: float) -> str:
    return f"{ratio * 100:.2f}%"


def _classify_size_bucket(market_cap: float | None) -> str:
    # CNY market-cap buckets: large >= 200B, mid >= 50B, else small.
    if market_cap is None or market_cap <= 0:
        return "unknown"
    if market_cap >= 2e11:
        return "large"
    if market_cap >= 5e10:
        return "mid"
    return "small"


def _liquidity_level(days_to_exit: float | None) -> str:
    if days_to_exit is None:
        return "unknown"
    if days_to_exit > 5:
        return "high"
    if days_to_exit > 2:
        return "medium"
    return "low"


def _empty_var_payload(portfolio_id: Any, input_mode: str, confidence: float, method: str) -> dict:
    """Return a stable, parseable zero-risk payload for empty portfolios."""
    return {
        "portfolio_id": portfolio_id,
        "input_mode": input_mode,
        "method": method,
        "confidence": confidence,
        "total_value": 0.0,
        "constituents": [],
        "empty_portfolio": True,
        "var": {
            "percentage": 0.0,
            "amount": 0.0,
            "description": "empty portfolio",
        },
        "cvar": {
            "percentage": 0.0,
            "amount": 0.0,
            "description": "empty portfolio",
        },
        "volatility": 0.0,
        "max_drawdown": 0.0,
        "message": "empty portfolio, add holdings first",
        "quick_start": {
            "step1": 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
            "step2": 'risk_manager(action="calculate_var", portfolio_id="xxx")',
        },
    }


def _empty_stress_payload(portfolio_id: Any, input_mode: str, scenario_name: str, description: str) -> dict:
    return {
        "portfolio_id": portfolio_id,
        "input_mode": input_mode,
        "scenario": scenario_name,
        "description": description,
        "current_value": 0.0,
        "stressed_value": 0.0,
        "loss": 0.0,
        "loss_percentage": "0.00%",
        "severity": "low",
        "recommendation": "add holdings first",
        "empty_portfolio": True,
        "message": "empty portfolio, add holdings first",
        "quick_start": {
            "step1": 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
            "step2": 'risk_manager(action="stress_test", portfolio_id="xxx", scenario="market_crash")',
        },
    }


def register_risk_manager(mcp):
    """Register risk manager tool."""

    @mcp.tool()
    async def risk_manager(action: str, **kwargs):
        """
        Risk manager with unified action + kwargs protocol.

        Actions:
        - help
        - list
        - calculate_var
        - stress_test
        - risk_exposure
        """
        try:
            db = get_db()
            kwargs = _normalize_kwargs(dict(kwargs))

            if action == "help":
                return ok(
                    {
                        "supported_actions": {
                            "list": "list available actions and parameter hints",
                            "calculate_var": "calculate VaR/CVaR using portfolio_id or codes+weights",
                            "stress_test": "run scenario stress tests using portfolio_id or codes+weights",
                            "risk_exposure": "exposure and concentration analysis using portfolio_id or codes+weights",
                            "help": "show help information",
                        }
                    }
                )

            if action == "list":
                return ok(
                    {
                        "actions": [
                            {
                                "action": "calculate_var",
                                "description": "calculate portfolio VaR/CVaR",
                                "kwargs": "portfolio_id or codes+weights, confidence(0.95), method(historical|parametric|monte_carlo), lookback_days(252)",
                            },
                            {
                                "action": "stress_test",
                                "description": "run scenario stress tests",
                                "kwargs": "portfolio_id or codes+weights, scenario/scenarios, portfolio_value(1000000)",
                            },
                            {
                                "action": "risk_exposure",
                                "description": "portfolio exposure and concentration",
                                "kwargs": "portfolio_id or codes+weights, portfolio_value(1000000)",
                            },
                        ],
                        "count": 3,
                    }
                )

            if action == "calculate_var":
                portfolio_id = _safe_portfolio_id(kwargs.get("portfolio_id"))
                confidence = float(kwargs.get("confidence", 0.95) or 0.95)
                confidence = max(0.5, min(0.999, confidence))
                method = str(kwargs.get("method", "historical") or "historical")
                lookback_days = int(kwargs.get("lookback_days", 252) or 252)
                lookback_days = max(30, min(2000, lookback_days))
                portfolio_value_input = float(kwargs.get("portfolio_value", 1_000_000) or 1_000_000)

                returns_data: list[dict] = []
                total_value = 0.0
                input_mode = "portfolio_id"

                if portfolio_id is not None:
                    async with db.acquire() as conn:
                        holdings = await conn.fetch("SELECT * FROM holdings WHERE portfolio_id = $1", portfolio_id)

                    if not holdings:
                        return ok(_empty_var_payload(portfolio_id, input_mode, confidence, method))

                    for holding in holdings:
                        code = normalize_code(str(holding["code"]))
                        shares = float(holding["shares"])
                        klines = await db.get_klines(code, limit=lookback_days)
                        if len(klines) < 2:
                            continue

                        prices = [float(k["close"]) for k in klines]
                        if prices[-1] <= 0:
                            continue

                        returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0]
                        if not returns:
                            continue

                        current_value = shares * prices[-1]
                        total_value += current_value
                        returns_data.append(
                            {
                                "code": code,
                                "returns": returns,
                                "weight": 0.0,
                                "current_value": current_value,
                            }
                        )

                    if total_value > 0:
                        for item in returns_data:
                            item["weight"] = item["current_value"] / total_value
                else:
                    codes, weights, parse_error = _parse_codes_weights(kwargs)
                    if parse_error:
                        return fail(parse_error)
                    if not codes:
                        return fail("portfolio_id or codes+weights required")

                    input_mode = "codes_weights"
                    total_value = portfolio_value_input

                    for code, weight in zip(codes, weights):
                        klines = await db.get_klines(code, limit=lookback_days)
                        if len(klines) < 2:
                            continue

                        prices = [float(k["close"]) for k in klines]
                        returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices)) if prices[i - 1] > 0]
                        if not returns:
                            continue

                        returns_data.append(
                            {
                                "code": code,
                                "returns": returns,
                                "weight": float(weight),
                                "current_value": float(weight * total_value),
                            }
                        )

                    if returns_data:
                        total_weight = float(sum(item["weight"] for item in returns_data))
                        if total_weight > 0:
                            for item in returns_data:
                                item["weight"] = item["weight"] / total_weight
                                item["current_value"] = item["weight"] * total_value

                if not returns_data:
                    return fail("no available kline data for VaR calculation")

                min_length = min(len(item["returns"]) for item in returns_data)
                portfolio_returns = np.array(
                    [sum(item["returns"][i] * item["weight"] for item in returns_data) for i in range(min_length)]
                )

                if method == "historical":
                    var = float(np.percentile(portfolio_returns, (1 - confidence) * 100))
                elif method == "parametric":
                    mean = float(np.mean(portfolio_returns))
                    std = float(np.std(portfolio_returns))
                    try:
                        from scipy import stats

                        var = float(stats.norm.ppf(1 - confidence, mean, std))
                    except Exception:
                        # fallback when scipy is unavailable
                        var = float(np.percentile(portfolio_returns, (1 - confidence) * 100))
                else:
                    mean = float(np.mean(portfolio_returns))
                    std = float(np.std(portfolio_returns))
                    simulations = np.random.normal(mean, std, 10000)
                    var = float(np.percentile(simulations, (1 - confidence) * 100))

                var_amount = abs(var * total_value)
                cvar_returns = portfolio_returns[portfolio_returns <= var]
                cvar = float(np.mean(cvar_returns)) if len(cvar_returns) > 0 else var
                cvar_amount = abs(cvar * total_value)

                return ok(
                    {
                        "portfolio_id": portfolio_id,
                        "input_mode": input_mode,
                        "method": method,
                        "confidence": confidence,
                        "total_value": float(total_value),
                        "constituents": [item["code"] for item in returns_data],
                        "var": {
                            "percentage": float(var),
                            "amount": float(var_amount),
                            "description": f"{confidence*100:.0f}% confidence 1-day VaR",
                        },
                        "cvar": {
                            "percentage": float(cvar),
                            "amount": float(cvar_amount),
                            "description": "expected tail loss beyond VaR",
                        },
                        "volatility": float(np.std(portfolio_returns)),
                        "max_drawdown": float(np.min(portfolio_returns)),
                    }
                )

            if action == "stress_test":
                portfolio_id = _safe_portfolio_id(kwargs.get("portfolio_id"))
                scenario = kwargs.get("scenario")
                scenarios_input = _parse_list_param(kwargs.get("scenarios")) or [scenario or "market_crash"]

                scenario_defs = {
                    "market_crash": {"market": -0.20, "volatility": 2.0, "description": "market down 20%"},
                    "black_swan": {"market": -0.30, "volatility": 3.0, "description": "black swan event"},
                    "interest_rate_hike": {"market": -0.10, "volatility": 1.5, "description": "sharp rate hike"},
                    "sector_rotation": {"market": -0.05, "volatility": 1.2, "description": "sector rotation"},
                    "liquidity_crisis": {"market": -0.15, "volatility": 2.5, "description": "liquidity crunch"},
                }

                input_mode = "portfolio_id"
                holdings_values: list[dict] = []

                if portfolio_id is not None:
                    async with db.acquire() as conn:
                        holdings = await conn.fetch("SELECT * FROM holdings WHERE portfolio_id = $1", portfolio_id)

                    if not holdings:
                        first_name = str(scenarios_input[0]) if scenarios_input else "market_crash"
                        if first_name not in scenario_defs:
                            first_name = "market_crash"
                        return ok(_empty_stress_payload(portfolio_id, input_mode, first_name, scenario_defs[first_name]["description"]))

                    for holding in holdings:
                        code = normalize_code(str(holding["code"]))
                        shares = float(holding["shares"])
                        klines = await db.get_klines(code, limit=1)
                        if not klines:
                            continue
                        stock_info = await db.get_stock_info(code)
                        sector = stock_info.get("industry", "unknown") if stock_info else "unknown"
                        current_price = float(klines[0]["close"])
                        holdings_values.append({"code": code, "value": float(shares * current_price), "sector": sector})
                else:
                    codes, weights, parse_error = _parse_codes_weights(kwargs)
                    if parse_error:
                        return fail(parse_error)
                    if not codes:
                        return fail("portfolio_id or codes+weights required")

                    input_mode = "codes_weights"
                    portfolio_value = float(kwargs.get("portfolio_value", 1_000_000) or 1_000_000)
                    for code, weight in zip(codes, weights):
                        stock_info = await db.get_stock_info(code)
                        sector = stock_info.get("industry", "unknown") if stock_info else "unknown"
                        holdings_values.append({"code": code, "value": float(weight * portfolio_value), "sector": sector})

                if not holdings_values:
                    return fail("no positions or quotes available for stress test")

                total_value = float(sum(item["value"] for item in holdings_values))

                def _run_one_scenario(name: str) -> dict:
                    scenario_name = name if name in scenario_defs else "market_crash"
                    params = scenario_defs[scenario_name]
                    market_shock = float(params.get("market", -0.2))
                    stressed_value = float(sum(item["value"] * (1 + market_shock) for item in holdings_values))
                    loss = float(total_value - stressed_value)
                    loss_pct = (loss / total_value) if total_value > 0 else 0.0
                    # Explainability layers for stress decomposition
                    volatility_multiplier = float(params.get("volatility", 1.0))
                    volatility_penalty_pct = max(0.0, (volatility_multiplier - 1.0) * 0.01)
                    volatility_penalty = total_value * volatility_penalty_pct
                    liquidity_penalty_pct = 0.003 if scenario_name in {"liquidity_crisis", "black_swan"} else 0.0
                    liquidity_penalty = total_value * liquidity_penalty_pct
                    adjusted_loss = loss + volatility_penalty + liquidity_penalty
                    adjusted_loss_pct = (adjusted_loss / total_value) if total_value > 0 else 0.0
                    return {
                        "scenario": scenario_name,
                        "description": params["description"],
                        "current_value": float(total_value),
                        "stressed_value": stressed_value,
                        "loss": float(adjusted_loss),
                        "loss_percentage": f"{adjusted_loss_pct * 100:.2f}%",
                        "severity": "high" if adjusted_loss_pct > 0.15 else ("medium" if adjusted_loss_pct > 0.08 else "low"),
                        "recommendation": "consider hedging" if adjusted_loss_pct > 0.15 else "risk acceptable",
                        "assumptions": {
                            "market_shock": market_shock,
                            "volatility_multiplier": volatility_multiplier,
                            "liquidity_penalty_pct": liquidity_penalty_pct,
                        },
                        "layer_losses": {
                            "market_loss": float(loss),
                            "volatility_penalty": float(volatility_penalty),
                            "liquidity_penalty": float(liquidity_penalty),
                        },
                    }

                if len(scenarios_input) == 1:
                    result = _run_one_scenario(str(scenarios_input[0]))
                    result["portfolio_id"] = portfolio_id
                    result["input_mode"] = input_mode
                    return ok(result)

                batch = {}
                for name in scenarios_input:
                    one = _run_one_scenario(str(name))
                    batch[one["scenario"]] = one

                return ok(
                    {
                        "portfolio_id": portfolio_id,
                        "input_mode": input_mode,
                        "scenarios": batch,
                        "current_value": total_value,
                        "count": len(batch),
                    }
                )

            if action == "risk_exposure":
                portfolio_id = _safe_portfolio_id(kwargs.get("portfolio_id"))
                input_mode = "portfolio_id"
                position_rows = []
                lookback_days = int(kwargs.get("lookback_days", 20) or 20)
                lookback_days = max(5, min(120, lookback_days))
                monitor_points = int(kwargs.get("monitor_points", lookback_days) or lookback_days)
                monitor_points = max(5, min(60, monitor_points))
                max_participation_rate = float(kwargs.get("max_participation_rate", 0.2) or 0.2)
                max_participation_rate = max(0.01, min(0.5, max_participation_rate))

                if portfolio_id is not None:
                    async with db.acquire() as conn:
                        holdings = await conn.fetch("SELECT * FROM holdings WHERE portfolio_id = $1", portfolio_id)

                    if not holdings:
                        return ok(
                            {
                                "message": "empty portfolio, add holdings first",
                                "quick_start": {
                                    "step1": 'portfolio_manager(action="add_holding", portfolio_id="xxx", code="600519", shares=100)',
                                    "step2": 'risk_manager(action="risk_exposure", portfolio_id="xxx")',
                                },
                            }
                        )

                    for holding in holdings:
                        code = normalize_code(str(holding["code"]))
                        shares = float(holding["shares"])
                        stock_info = await db.get_stock_info(code)
                        klines = await db.get_klines(code, limit=max(lookback_days, monitor_points, 2))
                        if not klines:
                            continue
                        financial_row = None
                        try:
                            financials = await db.get_financials(code, limit=1)
                            if isinstance(financials, list) and financials:
                                financial_row = financials[0]
                            elif isinstance(financials, dict):
                                financial_row = financials
                        except Exception:
                            financial_row = None

                        current_price = float(klines[0]["close"])
                        current_value = shares * current_price
                        sector = stock_info.get("industry", "unknown") if stock_info else "unknown"
                        market_cap = _first_float(
                            ["market_cap", "total_market_cap", "total_mv", "circ_mv", "float_market_cap", "mkt_cap"],
                            stock_info,
                            financial_row,
                            positive_only=True,
                        )
                        beta = _first_float(["beta", "beta_1y", "beta_250d", "beta_60d"], stock_info, financial_row)
                        pe = _first_float(["pe_ratio", "pe", "ttm_pe"], stock_info, financial_row, positive_only=True)
                        pb = _first_float(["pb_ratio", "pb", "ttm_pb"], stock_info, financial_row, positive_only=True)
                        roe = _first_float(["roe", "roe_ttm"], financial_row, stock_info)
                        debt_ratio = _first_float(["debt_ratio", "debt_to_asset"], financial_row, stock_info)

                        amount_samples = []
                        for row in klines[:lookback_days]:
                            close_px = _safe_float(row.get("close"), 0.0) or 0.0
                            volume = _safe_float(row.get("volume"), 0.0) or 0.0
                            amount = _safe_float(row.get("amount"), None)
                            amount_samples.append(amount if amount is not None and amount > 0 else close_px * volume)
                        avg_daily_amount = float(np.mean(amount_samples)) if amount_samples else 0.0

                        price_series = []
                        for row in klines[:monitor_points]:
                            close_px = _safe_float(row.get("close"), 0.0) or 0.0
                            if close_px <= 0:
                                continue
                            price_series.append((str(row.get("date", "")), float(close_px)))

                        position_rows.append(
                            {
                                "code": code,
                                "name": stock_info.get("stock_name", code) if stock_info else code,
                                "value": float(current_value),
                                "sector": sector,
                                "current_price": float(current_price),
                                "shares_proxy": float(shares),
                                "market_cap": market_cap,
                                "beta": beta,
                                "pe": pe,
                                "pb": pb,
                                "roe": roe,
                                "debt_ratio": debt_ratio,
                                "avg_daily_amount": float(avg_daily_amount),
                                "price_series": price_series,
                            }
                        )
                else:
                    codes, weights, parse_error = _parse_codes_weights(kwargs)
                    if parse_error:
                        return fail(parse_error)
                    if not codes:
                        return fail("portfolio_id or codes+weights required")

                    input_mode = "codes_weights"
                    portfolio_value = float(kwargs.get("portfolio_value", 1_000_000) or 1_000_000)
                    for code, weight in zip(codes, weights):
                        stock_info = await db.get_stock_info(code)
                        klines = await db.get_klines(code, limit=max(lookback_days, monitor_points, 2))
                        if not klines:
                            continue
                        financial_row = None
                        try:
                            financials = await db.get_financials(code, limit=1)
                            if isinstance(financials, list) and financials:
                                financial_row = financials[0]
                            elif isinstance(financials, dict):
                                financial_row = financials
                        except Exception:
                            financial_row = None

                        current_price = float(klines[0]["close"])
                        current_value = float(weight * portfolio_value)
                        shares_proxy = (current_value / current_price) if current_price > 0 else 0.0
                        sector = stock_info.get("industry", "unknown") if stock_info else "unknown"
                        market_cap = _first_float(
                            ["market_cap", "total_market_cap", "total_mv", "circ_mv", "float_market_cap", "mkt_cap"],
                            stock_info,
                            financial_row,
                            positive_only=True,
                        )
                        beta = _first_float(["beta", "beta_1y", "beta_250d", "beta_60d"], stock_info, financial_row)
                        pe = _first_float(["pe_ratio", "pe", "ttm_pe"], stock_info, financial_row, positive_only=True)
                        pb = _first_float(["pb_ratio", "pb", "ttm_pb"], stock_info, financial_row, positive_only=True)
                        roe = _first_float(["roe", "roe_ttm"], financial_row, stock_info)
                        debt_ratio = _first_float(["debt_ratio", "debt_to_asset"], financial_row, stock_info)

                        amount_samples = []
                        for row in klines[:lookback_days]:
                            close_px = _safe_float(row.get("close"), 0.0) or 0.0
                            volume = _safe_float(row.get("volume"), 0.0) or 0.0
                            amount = _safe_float(row.get("amount"), None)
                            amount_samples.append(amount if amount is not None and amount > 0 else close_px * volume)
                        avg_daily_amount = float(np.mean(amount_samples)) if amount_samples else 0.0

                        price_series = []
                        for row in klines[:monitor_points]:
                            close_px = _safe_float(row.get("close"), 0.0) or 0.0
                            if close_px <= 0:
                                continue
                            price_series.append((str(row.get("date", "")), float(close_px)))

                        position_rows.append(
                            {
                                "code": code,
                                "name": stock_info.get("stock_name", code) if stock_info else code,
                                "value": current_value,
                                "sector": sector,
                                "current_price": float(current_price),
                                "shares_proxy": float(shares_proxy),
                                "market_cap": market_cap,
                                "beta": beta,
                                "pe": pe,
                                "pb": pb,
                                "roe": roe,
                                "debt_ratio": debt_ratio,
                                "avg_daily_amount": float(avg_daily_amount),
                                "price_series": price_series,
                            }
                        )

                if not position_rows:
                    return fail("no positions or quotes available for exposure analysis")

                total_value = float(sum(item["value"] for item in position_rows))
                sector_totals: dict[str, float] = {}
                stock_exposure = []

                for item in position_rows:
                    code = item["code"]
                    value = float(item["value"])
                    sector = item["sector"]
                    sector_totals[sector] = sector_totals.get(sector, 0.0) + value
                    stock_exposure.append(
                        {
                            "code": code,
                            "name": item.get("name", code),
                            "value": value,
                            "weight": "0%",
                            "sector": sector,
                            "liquidity_level": "unknown",
                        }
                    )

                if total_value > 0:
                    for row in stock_exposure:
                        row["weight"] = f"{(row['value'] / total_value * 100):.2f}%"

                sector_exposure = {
                    sector: (f"{(value / total_value * 100):.2f}%" if total_value > 0 else "0%")
                    for sector, value in sector_totals.items()
                }

                max_weight = (max(item["value"] for item in stock_exposure) / total_value) if total_value > 0 else 0.0
                hhi = sum((item["value"] / total_value) ** 2 for item in stock_exposure) if total_value > 0 else 0.0
                effective_positions = (1.0 / hhi) if hhi > 0 else 0.0
                top3_weight = (
                    sum(sorted((item["value"] / total_value for item in stock_exposure), reverse=True)[:3])
                    if total_value > 0
                    else 0.0
                )
                sector_hhi = (
                    sum((value / total_value) ** 2 for value in sector_totals.values()) if total_value > 0 else 0.0
                )
                if max_weight > 0.3:
                    concentration_level = "high"
                    concentration_desc = "single-stock concentration is too high"
                elif max_weight > 0.2:
                    concentration_level = "medium"
                    concentration_desc = "single-stock concentration is relatively high"
                else:
                    concentration_level = "low"
                    concentration_desc = "holdings are reasonably diversified"

                # Style exposure (size/value/quality/beta)
                size_bucket_weights = {"large": 0.0, "mid": 0.0, "small": 0.0, "unknown": 0.0}
                beta_weight_num = 0.0
                beta_weight_den = 0.0
                pe_weight_num = 0.0
                pe_weight_den = 0.0
                pb_weight_num = 0.0
                pb_weight_den = 0.0
                roe_weight_num = 0.0
                roe_weight_den = 0.0
                debt_weight_num = 0.0
                debt_weight_den = 0.0

                for item in position_rows:
                    value = float(item["value"])
                    weight = (value / total_value) if total_value > 0 else 0.0
                    bucket = _classify_size_bucket(item.get("market_cap"))
                    size_bucket_weights[bucket] = size_bucket_weights.get(bucket, 0.0) + weight

                    beta = item.get("beta")
                    if beta is not None:
                        beta_weight_num += weight * float(beta)
                        beta_weight_den += weight

                    pe = item.get("pe")
                    if pe is not None and pe > 0:
                        pe_weight_num += weight * float(pe)
                        pe_weight_den += weight

                    pb = item.get("pb")
                    if pb is not None and pb > 0:
                        pb_weight_num += weight * float(pb)
                        pb_weight_den += weight

                    roe = item.get("roe")
                    if roe is not None:
                        roe_weight_num += weight * float(roe)
                        roe_weight_den += weight

                    debt_ratio = item.get("debt_ratio")
                    if debt_ratio is not None:
                        debt_weight_num += weight * float(debt_ratio)
                        debt_weight_den += weight

                weighted_beta = (beta_weight_num / beta_weight_den) if beta_weight_den > 0 else None
                weighted_pe = (pe_weight_num / pe_weight_den) if pe_weight_den > 0 else None
                weighted_pb = (pb_weight_num / pb_weight_den) if pb_weight_den > 0 else None
                weighted_roe = (roe_weight_num / roe_weight_den) if roe_weight_den > 0 else None
                weighted_debt = (debt_weight_num / debt_weight_den) if debt_weight_den > 0 else None

                if weighted_pe is None:
                    valuation_tilt = "unknown"
                elif weighted_pe <= 15:
                    valuation_tilt = "value"
                elif weighted_pe >= 30:
                    valuation_tilt = "growth"
                else:
                    valuation_tilt = "balanced"

                # Liquidity risk: estimated days to exit under participation cap.
                liquidity_rows = []
                weighted_days_to_exit = 0.0
                weighted_days_den = 0.0
                illiquid_weight = 0.0
                for item in position_rows:
                    value = float(item["value"])
                    weight = (value / total_value) if total_value > 0 else 0.0
                    avg_daily_amount = float(item.get("avg_daily_amount", 0.0) or 0.0)
                    capacity = avg_daily_amount * max_participation_rate
                    days_to_exit = (value / capacity) if capacity > 0 else None
                    level = _liquidity_level(days_to_exit)
                    if level in {"medium", "high"}:
                        illiquid_weight += weight
                    if days_to_exit is not None:
                        weighted_days_to_exit += weight * days_to_exit
                        weighted_days_den += weight

                    liquidity_rows.append(
                        {
                            "code": item["code"],
                            "name": item.get("name", item["code"]),
                            "avg_daily_amount": float(avg_daily_amount),
                            "days_to_exit": round(float(days_to_exit), 2) if days_to_exit is not None else None,
                            "level": level,
                        }
                    )

                for row in stock_exposure:
                    match = next((x for x in liquidity_rows if x["code"] == row["code"]), None)
                    if match:
                        row["liquidity_level"] = match["level"]

                portfolio_days_to_exit = (
                    weighted_days_to_exit / weighted_days_den if weighted_days_den > 0 else None
                )
                if portfolio_days_to_exit is None:
                    liquidity_level = "unknown"
                elif portfolio_days_to_exit > 5 or illiquid_weight > 0.35:
                    liquidity_level = "high"
                elif portfolio_days_to_exit > 2 or illiquid_weight > 0.2:
                    liquidity_level = "medium"
                else:
                    liquidity_level = "low"

                # Daily monitor series: concentration + liquidity coverage snapshots.
                daily_monitor = []
                max_series_len = max((len(item.get("price_series", [])) for item in position_rows), default=0)
                for idx in range(min(monitor_points, max_series_len)):
                    daily_values = []
                    day_label = None
                    total_capacity = 0.0
                    for item in position_rows:
                        series = item.get("price_series", [])
                        if idx >= len(series):
                            continue
                        day, day_close = series[idx]
                        if day_close <= 0 or item.get("current_price", 0.0) <= 0:
                            continue
                        day_label = day_label or day
                        base_value = float(item["value"])
                        scaled_value = base_value * float(day_close / item["current_price"])
                        daily_values.append(scaled_value)
                        total_capacity += float(item.get("avg_daily_amount", 0.0) or 0.0) * max_participation_rate

                    if not daily_values:
                        continue
                    total_day_value = float(sum(daily_values))
                    hhi_day = (
                        sum((value / total_day_value) ** 2 for value in daily_values) if total_day_value > 0 else 0.0
                    )
                    top3_day = (
                        sum(sorted((value / total_day_value for value in daily_values), reverse=True)[:3])
                        if total_day_value > 0
                        else 0.0
                    )
                    liquidity_coverage = (total_capacity / total_day_value) if total_day_value > 0 else 0.0
                    daily_monitor.append(
                        {
                            "date": day_label or f"t-{idx}",
                            "hhi": float(hhi_day),
                            "top3_weight_pct": _format_pct(top3_day),
                            "effective_positions": float(1.0 / hhi_day) if hhi_day > 0 else 0.0,
                            "liquidity_coverage_pct": _format_pct(liquidity_coverage),
                        }
                    )

                stock_exposure.sort(key=lambda x: x["value"], reverse=True)
                liquidity_rows.sort(
                    key=lambda x: (x["days_to_exit"] is None, -(x["days_to_exit"] or 0.0)),
                )

                return ok(
                    {
                        "portfolio_id": portfolio_id,
                        "input_mode": input_mode,
                        "total_value": total_value,
                        "stock_exposure": stock_exposure[:10],
                        "sector_exposure": sector_exposure,
                        "concentration_risk": {
                            "level": concentration_level,
                            "max_weight": f"{max_weight * 100:.2f}%",
                            "description": concentration_desc,
                        },
                        "diversification": {
                            "stock_count": len(stock_exposure),
                            "sector_count": len(sector_exposure),
                            "recommendation": "consider more holdings" if len(stock_exposure) < 10 else "holding count is reasonable",
                        },
                        "explainability": {
                            "hhi": float(hhi),
                            "effective_positions": float(effective_positions),
                            "top3_weight_pct": f"{top3_weight * 100:.2f}%",
                            "sector_hhi": float(sector_hhi),
                        },
                        "risk_dashboard": {
                            "data_window": {
                                "lookback_days": lookback_days,
                                "monitor_points": monitor_points,
                                "max_participation_rate": max_participation_rate,
                            },
                            "industry_concentration": {
                                "sector_count": len(sector_exposure),
                                "sector_hhi": float(sector_hhi),
                                "top_sector": max(sector_totals, key=sector_totals.get) if sector_totals else "unknown",
                                "top_sector_weight_pct": (
                                    _format_pct(max(sector_totals.values()) / total_value) if total_value > 0 else "0.00%"
                                ),
                            },
                            "style_exposure": {
                                "beta_weighted": round(float(weighted_beta), 4) if weighted_beta is not None else None,
                                "size_bucket_weights": {k: _format_pct(v) for k, v in size_bucket_weights.items()},
                                "valuation_tilt": valuation_tilt,
                                "weighted_pe": round(float(weighted_pe), 2) if weighted_pe is not None else None,
                                "weighted_pb": round(float(weighted_pb), 2) if weighted_pb is not None else None,
                                "weighted_roe": round(float(weighted_roe), 4) if weighted_roe is not None else None,
                                "weighted_debt_ratio": (
                                    round(float(weighted_debt), 4) if weighted_debt is not None else None
                                ),
                            },
                            "liquidity_risk": {
                                "level": liquidity_level,
                                "portfolio_days_to_exit": (
                                    round(float(portfolio_days_to_exit), 2)
                                    if portfolio_days_to_exit is not None
                                    else None
                                ),
                                "illiquid_weight_pct": _format_pct(float(illiquid_weight)),
                                "positions": liquidity_rows[:10],
                            },
                            "daily_monitor": {
                                "as_of": daily_monitor[0]["date"] if daily_monitor else None,
                                "series_count": len(daily_monitor),
                                "series": daily_monitor,
                            },
                        },
                    }
                )

            return fail(
                f"Unknown action: {action}. Supported: help, list, calculate_var, stress_test, risk_exposure"
            )
        except Exception as exc:
            return fail(str(exc))
