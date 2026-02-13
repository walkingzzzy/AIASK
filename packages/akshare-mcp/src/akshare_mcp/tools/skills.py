"""Skill tools with safe orchestrated execution."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np

from ..utils import normalize_code, ok, fail


_FALLBACK_SKILLS: List[Dict[str, Any]] = [
    {
        "id": "momentum_screen",
        "name": "Momentum Screen",
        "category": "screening",
        "description": "fallback demo",
    },
    {
        "id": "value_screen",
        "name": "Value Screen",
        "category": "screening",
        "description": "fallback demo",
    },
    {
        "id": "trend_follow",
        "name": "Trend Follow",
        "category": "strategy",
        "description": "fallback demo",
    },
]


def _find_skills_root() -> Path | None:
    """Find .codex/skills from current package location."""
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        candidate = parent / ".codex" / "skills"
        if candidate.is_dir():
            return candidate
    return None


def _parse_skill_md(md_path: Path) -> Dict[str, Any]:
    """Parse SKILL.md front matter."""
    skill_id = md_path.parent.name
    name = skill_id
    description = ""

    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            for line in lines[1:]:
                s = line.strip()
                if s == "---":
                    break
                if s.startswith("name:"):
                    name = s.split(":", 1)[1].strip() or name
                elif s.startswith("description:"):
                    description = s.split(":", 1)[1].strip()
    except Exception:
        pass

    category = "general"
    if "-" in skill_id:
        parts = skill_id.split("-")
        if len(parts) >= 2:
            category = parts[1]

    return {
        "id": skill_id,
        "name": name,
        "category": category,
        "description": description,
        "path": str(md_path),
    }


def _load_skills() -> List[Dict[str, Any]]:
    skills_root = _find_skills_root()
    if not skills_root:
        return _FALLBACK_SKILLS

    skills: List[Dict[str, Any]] = []
    for md in skills_root.glob("*/SKILL.md"):
        if md.parent.name.startswith("_"):
            continue
        skills.append(_parse_skill_md(md))

    if not skills:
        return _FALLBACK_SKILLS

    skills.sort(key=lambda x: x.get("id", ""))
    return skills


def _normalize_params(params: Any) -> Dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, dict):
        return dict(params)
    if isinstance(params, str):
        raw = params.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"raw_params": params}
    return {"raw_params": params}


def _step_result(step: str, output: Any = None, error: str | None = None) -> Dict[str, Any]:
    if error is not None:
        return {"step": step, "success": False, "error": error}
    if isinstance(output, dict):
        return {"step": step, "success": bool(output.get("success", True)), "output": output}
    return {"step": step, "success": True, "output": output}


def _run_step(step: str, fn: Callable[..., Any], **kwargs: Any) -> Dict[str, Any]:
    try:
        return _step_result(step, output=fn(**kwargs))
    except Exception as e:
        return _step_result(step, error=f"{type(e).__name__}: {e}")


def _finalize_skill_result(task: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [s["step"] for s in steps if not s.get("success")]
    return {
        "task": task,
        "status": "completed" if not failed else "partial_failed",
        "steps": steps,
        "summary": {
            "total_steps": len(steps),
            "failed_steps": failed,
            "success_count": len(steps) - len(failed),
            "failed_count": len(failed),
        },
    }


def _exec_tdx_runtime_ops(params: Dict[str, Any]) -> Dict[str, Any]:
    from .tdx_realtime import tdx_manage_subscription, tdx_refresh_data
    from .tdx_trading_data import tdx_list_available_fields

    task = str(params.get("task") or "runtime_precheck").strip().lower()
    market = str(params.get("market") or "AG").strip().upper()
    data_type = str(params.get("data_type") or "all").strip().lower()

    steps: List[Dict[str, Any]] = []
    if task in {"runtime_precheck", "precheck", "smoke_test"}:
        steps.append(_run_step("tdx_refresh_data", tdx_refresh_data, refresh_type="cache", market=market, force=False))
        steps.append(_run_step("tdx_manage_subscription", tdx_manage_subscription, action="list"))
        steps.append(_run_step("tdx_list_available_fields", tdx_list_available_fields, data_type=data_type))
        return _finalize_skill_result(task, steps)

    if task in {"refresh_cache", "refresh"}:
        steps.append(_run_step("tdx_refresh_data", tdx_refresh_data, refresh_type="cache", market=market, force=bool(params.get("force", False))))
        return _finalize_skill_result(task, steps)

    if task in {"refresh_kline", "kline_refresh"}:
        stock_codes = params.get("stock_codes") or [str(params.get("code") or "600519")]
        period = str(params.get("period") or "1d")
        steps.append(
            _run_step(
                "tdx_refresh_data",
                tdx_refresh_data,
                refresh_type="kline",
                stock_codes=stock_codes,
                period=period,
            )
        )
        return _finalize_skill_result(task, steps)

    return {
        "task": task,
        "status": "unsupported_task",
        "steps": [],
        "summary": {
            "total_steps": 0,
            "failed_steps": [],
            "supported_tasks": ["runtime_precheck", "refresh_cache", "refresh_kline"],
        },
    }


def _exec_market(params: Dict[str, Any]) -> Dict[str, Any]:
    from .market.kline import get_kline, get_kline_data, get_minute_kline
    from .market.order_book import get_order_book
    from .market.quote import get_realtime_quote

    task = str(params.get("task") or "smoke_test").strip().lower()
    code = normalize_code(str(params.get("code") or "600519"))

    daily_limit = int(params.get("daily_limit", 30) or 30)
    minute_limit = int(params.get("minute_limit", 30) or 30)
    minute_period = str(params.get("minute_period") or "5m")
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    steps: List[Dict[str, Any]] = []
    if task in {"smoke_test", "quick_scan"}:
        steps.append(_run_step("get_realtime_quote", get_realtime_quote, stock_code=code))
        if start_date or end_date:
            steps.append(
                _run_step(
                    "get_kline_data",
                    get_kline_data,
                    code=code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    limit=daily_limit,
                )
            )
        else:
            steps.append(_run_step("get_kline", get_kline, stock_code=code, period="daily", limit=daily_limit))
        steps.append(
            _run_step("get_minute_kline", get_minute_kline, stock_code=code, period=minute_period, limit=minute_limit)
        )
        steps.append(_run_step("get_order_book", get_order_book, stock_code=code))
        return _finalize_skill_result(task, steps)

    if task in {"quote_only", "quote"}:
        steps.append(_run_step("get_realtime_quote", get_realtime_quote, stock_code=code))
        return _finalize_skill_result(task, steps)

    return {
        "task": task,
        "status": "unsupported_task",
        "steps": [],
        "summary": {
            "total_steps": 0,
            "failed_steps": [],
            "supported_tasks": ["smoke_test", "quick_scan", "quote_only"],
        },
    }


def _exec_tdx_formula_research(params: Dict[str, Any]) -> Dict[str, Any]:
    from .tdx_formula.api import calculate_indicator, get_formula_data, screen_stocks

    task = str(params.get("task") or "formula_check").strip().lower()
    code = normalize_code(str(params.get("code") or "600519"))
    period = str(params.get("period") or "1d")
    count = int(params.get("count", 100) or 100)
    formula_name = str(params.get("formula_name") or "MACD").strip().upper()
    formula_args = str(params.get("formula_args") or "12,26,9")

    steps: List[Dict[str, Any]] = []
    if task in {"formula_check", "smoke_test"}:
        steps.append(_run_step("tdx_get_formula_data", get_formula_data, stock_code=code, period=period, count=count))
        steps.append(
            _run_step(
                "tdx_calculate_indicator",
                calculate_indicator,
                stock_code=code,
                formula_name=formula_name,
                formula_args=formula_args,
                period=period,
                count=count,
                dividend_type=1,
            )
        )
        run_screen = bool(params.get("run_screen", True))
        if run_screen:
            stock_pool = params.get("stock_pool") or ["600519", "000001", "000858", "600036", "601318"]
            steps.append(
                _run_step(
                    "tdx_screen_stocks",
                    screen_stocks,
                    formula_name=params.get("screen_formula", "MACD金叉"),
                    formula_args=str(params.get("screen_args") or ""),
                    stock_pool=stock_pool,
                    period=period,
                    count=min(count, 120),
                )
            )
        return _finalize_skill_result(task, steps)

    return {
        "task": task,
        "status": "unsupported_task",
        "steps": [],
        "summary": {
            "total_steps": 0,
            "failed_steps": [],
            "supported_tasks": ["formula_check", "smoke_test"],
        },
    }


def _exec_fund_manager_pro(params: Dict[str, Any]) -> Dict[str, Any]:
    from .market.kline import get_kline
    from .market.quote import get_realtime_quote
    from .news import get_stock_notices, get_stock_research
    from ..services import backtest_engine
    from ..services.portfolio_optimizer import portfolio_optimizer
    from ..services.risk_model import risk_model

    task = str(params.get("task") or "full_cycle").strip().lower()

    raw_codes = params.get("codes")
    if isinstance(raw_codes, str):
        raw_codes = [x.strip() for x in raw_codes.split(",") if x and str(x).strip()]
    if not isinstance(raw_codes, list) or not raw_codes:
        raw_codes = [params.get("code") or "600519", "000001", "000858"]

    dedup_codes: List[str] = []
    seen: set[str] = set()
    for raw in raw_codes:
        code = normalize_code(str(raw or ""))
        if not code or code in seen:
            continue
        seen.add(code)
        dedup_codes.append(code)
    if not dedup_codes:
        dedup_codes = ["600519", "000001", "000858"]

    lead_code = dedup_codes[0]
    lookback_days = max(30, int(params.get("lookback_days", 120) or 120))
    total_capital = float(params.get("total_capital", 1_000_000) or 1_000_000)
    optimization_method = str(params.get("method") or "equal_weight").strip().lower()
    confidence = float(params.get("confidence", 0.95) or 0.95)

    context: Dict[str, Any] = {
        "codes": dedup_codes,
        "lead_code": lead_code,
        "lookback_days": lookback_days,
        "total_capital": total_capital,
        "optimization_method": optimization_method,
        "confidence": confidence,
    }
    steps: List[Dict[str, Any]] = []

    def _research_step() -> Dict[str, Any]:
        end_date = str(params.get("end_date") or datetime.now().strftime("%Y-%m-%d"))
        start_date = str(
            params.get("start_date")
            or (datetime.now() - timedelta(days=int(params.get("event_window_days", 30) or 30))).strftime("%Y-%m-%d")
        )

        research_res = get_stock_research(stock_code=lead_code, limit=int(params.get("research_limit", 5) or 5))
        notices_res = get_stock_notices(start_date=start_date, end_date=end_date, stock_code=lead_code)

        context["research"] = {"reports": research_res, "events": notices_res}

        reports_count = 0
        if isinstance(research_res, dict) and research_res.get("success"):
            reports_count = int((research_res.get("data") or {}).get("total") or 0)

        events_count = 0
        if isinstance(notices_res, dict) and notices_res.get("success"):
            events_count = len(((notices_res.get("data") or {}).get("events") or []))

        return ok(
            {
                "lead_code": lead_code,
                "window": {"start_date": start_date, "end_date": end_date},
                "reports_count": reports_count,
                "events_count": events_count,
                "fallback_used": [
                    "research_reports_empty" if reports_count == 0 else None,
                    "events_empty" if events_count == 0 else None,
                ],
            }
        )

    def _portfolio_step() -> Dict[str, Any]:
        market_data: Dict[str, Dict[str, Any]] = {}
        dropped: List[str] = []
        returns_list: List[np.ndarray] = []
        valid_codes: List[str] = []

        for code in dedup_codes:
            kline_res = get_kline(stock_code=code, period="daily", limit=max(lookback_days + 10, 80))
            if not (isinstance(kline_res, dict) and kline_res.get("success")):
                dropped.append(code)
                continue

            rows = kline_res.get("data") or []
            cleaned_rows = [r for r in rows if isinstance(r, dict) and r.get("close") is not None]
            if len(cleaned_rows) < 30:
                dropped.append(code)
                continue

            closes = []
            for row in cleaned_rows:
                try:
                    closes.append(float(row.get("close")))
                except Exception:
                    pass
            if len(closes) < 30:
                dropped.append(code)
                continue

            returns = np.diff(np.array(closes, dtype=float)) / np.array(closes[:-1], dtype=float)
            if len(returns) < 20:
                dropped.append(code)
                continue

            valid_codes.append(code)
            returns_list.append(returns)
            market_data[code] = {
                "rows": cleaned_rows,
                "latest_close": float(closes[-1]),
                "series_len": len(closes),
            }

        if not valid_codes:
            return fail("No valid codes with sufficient kline data for portfolio construction")

        min_len = min(len(x) for x in returns_list)
        returns_matrix = np.array([x[-min_len:] for x in returns_list], dtype=float)

        weights_map: Dict[str, float]
        method_used = optimization_method
        try:
            if optimization_method == "risk_parity" and len(valid_codes) >= 2:
                weights_map = portfolio_optimizer.optimize_risk_parity(valid_codes, returns_matrix)
            elif optimization_method == "mean_variance" and len(valid_codes) >= 2:
                expected_returns = np.mean(returns_matrix, axis=1)
                weights_map = portfolio_optimizer.optimize_mean_variance(
                    valid_codes, returns_matrix, expected_returns, risk_aversion=float(params.get("risk_aversion", 1.0) or 1.0)
                )
            elif optimization_method == "max_sharpe" and len(valid_codes) >= 2:
                expected_returns = np.mean(returns_matrix, axis=1)
                weights_map = portfolio_optimizer.optimize_max_sharpe(
                    valid_codes,
                    returns_matrix,
                    expected_returns,
                    risk_free_rate=float(params.get("risk_free_rate", 0.03) or 0.03),
                ).get("weights", {})
            else:
                method_used = "equal_weight"
                weights_map = portfolio_optimizer.optimize_equal_weight(valid_codes)
        except Exception:
            method_used = "equal_weight_fallback"
            weights_map = portfolio_optimizer.optimize_equal_weight(valid_codes)

        weight_sum = sum(float(v) for v in weights_map.values()) or 1.0
        normalized_weights = {code: float(weights_map.get(code, 0.0)) / weight_sum for code in valid_codes}

        holdings: List[Dict[str, Any]] = []
        for code in valid_codes:
            w = float(normalized_weights.get(code, 0.0))
            latest = float(market_data[code]["latest_close"])
            value = total_capital * w
            holdings.append({"code": code, "weight": w, "value": value, "latest_close": latest})

        context["portfolio"] = {
            "valid_codes": valid_codes,
            "dropped_codes": dropped,
            "weights": normalized_weights,
            "returns_matrix": returns_matrix,
            "holdings": holdings,
            "market_data": market_data,
            "method_used": method_used,
        }

        return ok(
            {
                "method_used": method_used,
                "valid_codes": valid_codes,
                "dropped_codes": dropped,
                "weights": normalized_weights,
                "lookback_days": lookback_days,
            }
        )

    def _risk_step() -> Dict[str, Any]:
        portfolio_ctx = context.get("portfolio") or {}
        holdings = portfolio_ctx.get("holdings") or []
        returns_matrix = portfolio_ctx.get("returns_matrix")
        if not holdings or returns_matrix is None:
            return fail("Portfolio context missing; cannot run risk stage")

        weights = np.array([float(h["weight"]) for h in holdings], dtype=float)
        if len(weights) == 1:
            portfolio_returns = returns_matrix[0]
            var_result = risk_model.calculate_var(
                portfolio_returns.tolist(), confidence=confidence, portfolio_value=total_capital
            )
            risk_result = {
                "volatility": float(np.std(portfolio_returns)),
                "annual_volatility": float(np.std(portfolio_returns) * np.sqrt(252)),
                "variance": float(np.var(portfolio_returns)),
            }
        else:
            portfolio_returns = np.dot(weights, returns_matrix)
            var_result = risk_model.calculate_var(
                portfolio_returns.tolist(), confidence=confidence, portfolio_value=total_capital
            )
            risk_result = risk_model.calculate_portfolio_risk(
                [{"code": h["code"], "weight": float(h["weight"])} for h in holdings], returns_matrix
            )

        scenario_list = params.get("scenarios") or ["market_crash", "sector_rotation"]
        if isinstance(scenario_list, str):
            scenario_list = [x.strip() for x in scenario_list.split(",") if x.strip()]
        stress_results = []
        for scenario in scenario_list:
            stress_results.append(risk_model.stress_test(holdings, scenario=scenario))

        context["risk"] = {
            "var": var_result,
            "risk": risk_result,
            "stress_tests": stress_results,
            "portfolio_returns": portfolio_returns,
        }

        return ok(
            {
                "confidence": confidence,
                "var": var_result,
                "risk": risk_result,
                "stress_tests": stress_results,
            }
        )

    def _compliance_step() -> Dict[str, Any]:
        portfolio_ctx = context.get("portfolio") or {}
        holdings = portfolio_ctx.get("holdings") or []
        if not holdings:
            return fail("Portfolio context missing; cannot run compliance stage")

        first = holdings[0]
        order_code = str(params.get("order_code") or first["code"])
        direction = str(params.get("direction") or "buy").strip().lower()

        price = None
        for h in holdings:
            if h["code"] == order_code:
                price = h.get("latest_close")
                break

        try:
            quote_res = get_realtime_quote(stock_code=order_code)
            if isinstance(quote_res, dict):
                if quote_res.get("success"):
                    quote_price = (quote_res.get("data") or {}).get("price")
                    if quote_price is not None:
                        price = quote_price
                elif quote_res.get("price") is not None:
                    price = quote_res.get("price")
        except Exception:
            quote_res = None
        if price is None:
            return fail(f"Cannot resolve price for compliance check: {order_code}")

        target_value = total_capital * float(first["weight"])
        quantity = int(params.get("quantity") or (target_value / float(price) // 100) * 100)
        order_value = float(quantity) * float(price)
        max_single_order_pct = float(params.get("max_single_order_pct", 0.40) or 0.40)
        max_position_pct = float(params.get("max_position_pct", 0.40) or 0.40)

        checks = {
            "lot_size_100": quantity > 0 and quantity % 100 == 0,
            "price_positive": float(price) > 0,
            "single_order_limit": order_value <= total_capital * max_single_order_pct,
            "position_limit": float(first["weight"]) <= max_position_pct,
            "direction_valid": direction in {"buy", "sell"},
        }
        issues = [k for k, passed in checks.items() if not passed]
        passed = len(issues) == 0

        context["compliance"] = {
            "passed": passed,
            "issues": issues,
            "order": {
                "code": order_code,
                "direction": direction,
                "quantity": quantity,
                "price": float(price),
                "order_value": order_value,
            },
            "checks": checks,
        }

        return ok(
            {
                "mode": "equivalent_check",
                "passed": passed,
                "issues": issues,
                "checks": checks,
                "order": context["compliance"]["order"],
            }
        )

    def _execution_step() -> Dict[str, Any]:
        compliance_ctx = context.get("compliance") or {}
        if not compliance_ctx:
            return fail("Compliance context missing; cannot build execution plan")

        if not compliance_ctx.get("passed"):
            return fail(f"Compliance gate not passed: {compliance_ctx.get('issues')}")

        order = compliance_ctx.get("order") or {}
        quantity = int(order.get("quantity") or 0)
        duration_minutes = max(5, int(params.get("duration_minutes", 60) or 60))
        slices = max(1, int(params.get("slices", 6) or 6))
        interval = max(1, duration_minutes // slices)

        base = quantity // slices
        remainder = quantity % slices
        plan: List[Dict[str, Any]] = []
        for idx in range(slices):
            plan.append(
                {
                    "slice": idx + 1,
                    "offset_min": idx * interval,
                    "quantity": base + (1 if idx < remainder else 0),
                    "algo": "twap",
                }
            )

        context["execution"] = {
            "task": "twap_plan_only",
            "duration_minutes": duration_minutes,
            "slices": slices,
            "plan": plan,
            "order": order,
        }
        return ok(context["execution"])

    def _review_step() -> Dict[str, Any]:
        portfolio_ctx = context.get("portfolio") or {}
        market_data = portfolio_ctx.get("market_data") or {}
        lead_rows = (market_data.get(lead_code) or {}).get("rows") or []
        if len(lead_rows) < 30:
            return fail(f"Insufficient kline rows for review: {lead_code}")

        benchmark = normalize_code(str(params.get("benchmark") or "000300"))
        benchmark_rows: List[Dict[str, Any]] = []
        benchmark_res = get_kline(stock_code=benchmark, period="daily", limit=len(lead_rows))
        if isinstance(benchmark_res, dict) and benchmark_res.get("success"):
            benchmark_rows = benchmark_res.get("data") or []

        backtest_params = {
            "initial_capital": float(total_capital * float(portfolio_ctx.get("weights", {}).get(lead_code, 1.0))),
            "commission": float(params.get("commission", 0.0003) or 0.0003),
            "slippage": float(params.get("slippage", 0.0001) or 0.0001),
            "short_period": int(params.get("short_period", 5) or 5),
            "long_period": int(params.get("long_period", 20) or 20),
            "benchmark": benchmark,
            "benchmark_klines": benchmark_rows,
        }
        backtest_result = backtest_engine.run_backtest(
            lead_code,
            lead_rows,
            strategy=str(params.get("strategy") or "ma_cross"),
            params=backtest_params,
        )
        if not backtest_result.get("success"):
            return fail(backtest_result.get("error") or "Backtest failed")

        risk_ctx = context.get("risk") or {}
        review_data = {
            "lead_code": lead_code,
            "backtest": backtest_result.get("data"),
            "risk_snapshot": {
                "var": risk_ctx.get("var"),
                "volatility": (risk_ctx.get("risk") or {}).get("annual_volatility"),
            },
        }
        context["review"] = review_data
        return ok(review_data)

    if task in {"full_cycle", "daily_brief", "smoke_test"}:
        steps.append(_run_step("research", _research_step))
        steps.append(_run_step("portfolio_construction", _portfolio_step))
        steps.append(_run_step("risk_assessment", _risk_step))
        steps.append(_run_step("compliance_check", _compliance_step))
        steps.append(_run_step("execution_plan", _execution_step))
        steps.append(_run_step("performance_review", _review_step))

        result = _finalize_skill_result(task, steps)
        ring_names = [
            "research",
            "portfolio_construction",
            "risk_assessment",
            "compliance_check",
            "execution_plan",
            "performance_review",
        ]
        ring_status = {
            ring: next((bool(s.get("success")) for s in steps if s.get("step") == ring), False)
            for ring in ring_names
        }
        result["summary"]["ring_status"] = ring_status
        result["summary"]["ring_count"] = len(ring_names)
        result["summary"]["ring_passed"] = sum(1 for v in ring_status.values() if v)
        result["summary"]["closed_loop_gate"] = all(ring_status.values())
        result["summary"]["note"] = (
            "Equivalent compliance and execution planning are used inside run_skill orchestrator; "
            "no live order is sent."
        )
        return result

    return {
        "task": task,
        "status": "unsupported_task",
        "steps": [],
        "summary": {
            "total_steps": 0,
            "failed_steps": [],
            "supported_tasks": ["full_cycle", "daily_brief", "smoke_test"],
        },
    }


_SKILL_EXECUTORS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "akshare-tdx-runtime-ops": _exec_tdx_runtime_ops,
    "akshare-market": _exec_market,
    "akshare-tdx-formula-research": _exec_tdx_formula_research,
    "akshare-fund-manager-pro": _exec_fund_manager_pro,
}


def register(mcp):
    @mcp.tool()
    def list_skills():
        skills = _load_skills()
        source = "codex_registry" if skills and skills[0].get("path") else "fallback_demo"
        return ok({"skills": skills, "count": len(skills), "source": source})

    @mcp.tool()
    def search_skills(keyword: str):
        skills = _load_skills()
        keyword_lower = (keyword or "").strip().lower()
        if not keyword_lower:
            return ok({"skills": skills, "keyword": keyword, "count": len(skills)})

        matched = [
            skill
            for skill in skills
            if keyword_lower in skill.get("id", "").lower()
            or keyword_lower in skill.get("name", "").lower()
            or keyword_lower in skill.get("category", "").lower()
            or keyword_lower in skill.get("description", "").lower()
        ]
        return ok({"skills": matched, "keyword": keyword, "count": len(matched)})

    @mcp.tool()
    def run_skill(skill_id: str, params: dict = None):
        normalized_params = _normalize_params(params)
        skills = _load_skills()
        skill = next((s for s in skills if s.get("id") == skill_id), None)
        if not skill:
            return fail(f"Skill {skill_id} not found")

        executor = _SKILL_EXECUTORS.get(skill_id)
        if executor is None:
            return ok(
                {
                    "skill_id": skill_id,
                    "skill_name": skill.get("name", ""),
                    "params": normalized_params,
                    "skill_path": skill.get("path", ""),
                    "execution_mode": "no_handler",
                    "result": {
                        "task": str(normalized_params.get("task") or "default"),
                        "status": "handler_not_implemented",
                        "summary": {
                            "message": f"Skill {skill_id} is registered but has no executable handler yet",
                            "available_handlers": sorted(_SKILL_EXECUTORS.keys()),
                        },
                    },
                    "message": "Skill resolved from registry (no executable handler)",
                }
            )

        try:
            execution = executor(normalized_params)
        except Exception as e:
            return fail(f"Skill {skill_id} execution failed: {type(e).__name__}: {e}")

        return ok(
            {
                "skill_id": skill_id,
                "skill_name": skill.get("name", ""),
                "params": normalized_params,
                "skill_path": skill.get("path", ""),
                "execution_mode": "orchestrated",
                "result": execution,
                "message": "Skill executed via built-in orchestrator",
            }
        )
