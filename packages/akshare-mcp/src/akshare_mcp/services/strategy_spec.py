"""StrategySpec data class and configuration constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


DEFAULT_CODES = ['000300', '600519', '000858', '601318']
RESEARCH_UNIVERSE_PAGE_SIZE = _env_int('STRATEGY_LLM_RESEARCH_PAGE_SIZE', 120, minimum=20, maximum=500)
RESEARCH_UNIVERSE_SCAN_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_SCAN_LIMIT', 300, minimum=20, maximum=2000)
RESEARCH_KLINE_SCAN_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_KLINE_SCAN_LIMIT', 60, minimum=10, maximum=300)
RESEARCH_SYMBOL_DETAIL_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_SYMBOL_DETAIL_LIMIT', 24, minimum=4, maximum=80)
RESEARCH_CANDIDATE_POOL_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_CANDIDATE_POOL_LIMIT', 12, minimum=3, maximum=40)
RESEARCH_FINANCIAL_DETAIL_LIMIT = _env_int('STRATEGY_LLM_RESEARCH_FINANCIAL_DETAIL_LIMIT', 8, minimum=2, maximum=20)

_FACTOR_VALIDATION_TYPES = {"value_factor", "quality_factor", "growth_factor", "multi_factor"}


def _normalize_code_list(*values: Any, limit: int = 12) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for key in ("code", "symbol", "stock_code"):
                if value.get(key) is not None:
                    visit(value.get(key))
            for key in ("codes", "symbols", "stock_codes", "target_symbols"):
                if value.get(key) is not None:
                    visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        raw = str(value or "").strip()
        if not raw:
            return
        if any(sep in raw for sep in [",", ";", "|", "\n", "\t", " "]):
            normalized = (
                raw.replace(";", ",")
                .replace("|", ",")
                .replace("\n", ",")
                .replace("\t", ",")
                .replace(" ", ",")
            )
            for part in normalized.split(","):
                visit(part)
            return
        code = raw.split(".")[0].strip()
        if not code or code in seen:
            return
        seen.add(code)
        codes.append(code)

    for value in values:
        visit(value)
    return codes[: max(1, min(int(limit or 12), 40))]


def _safe_normalize_research_task(task: Any) -> dict[str, Any]:
    payload = dict(task or {})
    if not payload:
        return {}
    try:
        from strategy_factory.domain.targets import _normalize_research_task_contract

        return dict(_normalize_research_task_contract(payload))
    except Exception:
        task_source = str(payload.get("task_source") or "snapshot").strip().lower() or "snapshot"
        target_symbols = _normalize_code_list(
            [
                payload.get("target_symbols"),
                payload.get("stock_pool"),
                (payload.get("event_context") or {}).get("target_symbols"),
            ],
            limit=12,
        )
        stock_pool = dict(payload.get("stock_pool") or {})
        if target_symbols and not stock_pool:
            stock_pool = {"selection_mode": "explicit", "symbols": list(target_symbols)}
        holding_window = dict(payload.get("holding_window") or {})
        if not holding_window:
            holding_window = {"max_days": 10 if task_source == "event_driven" else 20}
        return {
            **payload,
            "task_source": task_source,
            "target_symbols": list(target_symbols),
            "stock_pool": stock_pool,
            "target_symbol_policy": str(
                payload.get("target_symbol_policy")
                or ("strict_intersection" if task_source == "event_driven" else "prefer_intersection")
            ).strip().lower(),
            "universe_expansion_policy": str(
                payload.get("universe_expansion_policy")
                or ("allow_same_theme_only" if task_source == "event_driven" else "allow_market_fallback")
            ).strip().lower(),
            "validation_focus": str(
                payload.get("validation_focus")
                or ("event_target_only" if task_source == "event_driven" else "target_plus_representative")
            ).strip().lower(),
            "holding_window": holding_window,
        }


def _task_source(research_task: dict[str, Any], event_context: dict[str, Any]) -> str:
    source = str(research_task.get("task_source") or "").strip().lower()
    if source:
        return source
    return "event_driven" if event_context else "snapshot"


def _default_holding_horizon(
    strategy_type: str,
    research_task: dict[str, Any],
    task_source: str,
) -> dict[str, Any]:
    holding_window = dict(research_task.get("holding_window") or {})
    if holding_window:
        return holding_window
    if task_source == "event_driven":
        return {"max_days": 10}
    if strategy_type in _FACTOR_VALIDATION_TYPES or strategy_type in {"macro_timing", "sector_rotation"}:
        return {"max_days": 20}
    return {"max_days": 10}


def _default_trade_plan(strategy_type: str, task_source: str) -> dict[str, Any]:
    if task_source == "event_driven":
        return {
            "entry_bias": "event_follow_through",
            "exit_bias": "time_stop_or_signal_reversal",
        }
    if strategy_type in _FACTOR_VALIDATION_TYPES:
        return {
            "entry_bias": "cross_sectional_rank",
            "exit_bias": "rank_decay_or_periodic_rebalance",
        }
    if strategy_type == "macro_timing":
        return {
            "entry_bias": "regime_confirmed",
            "exit_bias": "regime_flip_or_time_stop",
        }
    return {
        "entry_bias": "signal_confirmed",
        "exit_bias": "signal_or_time_stop",
    }


def _default_risk_rules(task_source: str, holding_horizon: dict[str, Any]) -> dict[str, Any]:
    max_holding_days = int(holding_horizon.get("max_days") or 0)
    return {
        "stop_loss_pct": 0.08 if task_source == "event_driven" else 0.1,
        "take_profit_pct": 0.18 if task_source == "event_driven" else 0.2,
        "max_holding_days": max_holding_days or (10 if task_source == "event_driven" else 20),
    }


def _default_position_sizing(target_symbols: list[str]) -> dict[str, Any]:
    multiple_names = len(target_symbols) > 1
    return {
        "mode": "equal_weight" if multiple_names else "single_name",
        "position_assumption": "equal_weight_proxy" if multiple_names else "single_name_full_notional",
    }


def _default_rebalance_rule(strategy_type: str, task_source: str) -> dict[str, Any]:
    if task_source == "event_driven":
        return {"mode": "event_driven_hold"}
    if strategy_type in _FACTOR_VALIDATION_TYPES or strategy_type == "sector_rotation":
        return {"mode": "periodic_rebalance", "frequency_days": 5}
    if strategy_type == "macro_timing":
        return {"mode": "regime_rebalance", "frequency_days": 10}
    return {"mode": "signal_rebalance"}


def _default_portfolio_spec(target_symbols: list[str]) -> dict[str, Any]:
    multiple_names = len(target_symbols) > 1
    return {
        "position_assumption": "equal_weight_proxy" if multiple_names else "single_name_full_notional",
        "target_weight_scheme": "equal_weight" if multiple_names else "single_name",
    }


def _default_execution_assumptions(task_source: str) -> dict[str, Any]:
    return {
        "commission_rate": 0.00025,
        "slippage_bps": 8 if task_source == "event_driven" else 5,
        "tradability_filter": True,
        "slippage_model": "fixed",
    }


def _default_validation_profile(
    strategy_type: str,
    research_task: dict[str, Any],
    task_source: str,
) -> dict[str, Any]:
    validation_focus = str(
        research_task.get("validation_focus")
        or ("event_target_only" if task_source == "event_driven" else "target_plus_representative")
    ).strip().lower()
    if strategy_type in _FACTOR_VALIDATION_TYPES:
        profile = "factor_rank_validation"
    elif strategy_type == "macro_timing":
        profile = "macro_regime_validation"
    elif task_source == "event_driven" or validation_focus == "event_target_only":
        profile = "event_trade_validation"
    else:
        profile = "trade_rule_validation"
    return {
        "profile": profile,
        "validation_focus": validation_focus,
        "primary_validation_layer": "target" if validation_focus == "event_target_only" else "combined",
    }


def _default_targeting_policy(research_task: dict[str, Any]) -> dict[str, Any]:
    if not research_task:
        return {}
    return {
        "target_symbol_policy": research_task.get("target_symbol_policy"),
        "universe_expansion_policy": research_task.get("universe_expansion_policy"),
        "validation_focus": research_task.get("validation_focus"),
    }


def _default_constraint_check(
    *,
    target_symbols: list[str],
    research_task: dict[str, Any],
    targeting_policy: dict[str, Any],
) -> dict[str, Any]:
    research_symbols = _normalize_code_list(
        [
            research_task.get("target_symbols"),
            research_task.get("stock_pool"),
        ],
        limit=12,
    )
    overlap_count = len(set(target_symbols).intersection(research_symbols))
    coverage_ratio = round(overlap_count / max(1, len(target_symbols)), 4) if target_symbols else 0.0
    intersection_ratio = round(overlap_count / max(1, len(research_symbols)), 4) if research_symbols else None
    violation = None
    if (
        str(targeting_policy.get("target_symbol_policy") or "").strip().lower() == "strict_intersection"
        and research_symbols
        and target_symbols
        and overlap_count == 0
    ):
        violation = "strict_intersection_empty"
    return {
        "target_symbols_before_normalize": list(target_symbols),
        "target_symbols_after_normalize": list(target_symbols),
        "research_target_symbols": list(research_symbols),
        "target_symbol_policy": targeting_policy.get("target_symbol_policy"),
        "universe_expansion_policy": targeting_policy.get("universe_expansion_policy"),
        "expansion_applied": False,
        "expansion_reason": None,
        "expansion_source": None,
        "constraint_violation": violation,
        "coverage_ratio": coverage_ratio,
        "intersection_ratio": intersection_ratio,
    }


@dataclass
class StrategySpec:
    strategy_type: str
    params: dict[str, Any]
    name: str = ''
    description: str = ''
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_candidate(self, source: str, experiment_id: str) -> dict:
        metadata = dict(self.metadata or {})
        source_candidate = dict(metadata.get("source_candidate") or {})
        source_candidate_params = dict(source_candidate.get("params") or {})

        def _list_value(*values: Any) -> list[Any]:
            for value in values:
                if isinstance(value, (list, tuple, set)) and value:
                    return list(value)
            return []

        def _dict_value(*values: Any) -> dict[str, Any]:
            for value in values:
                if isinstance(value, dict) and value:
                    return dict(value)
            return {}

        def _scalar_value(*values: Any) -> Any:
            for value in values:
                if value not in (None, "", [], {}):
                    return value
            return None

        target_symbols = _normalize_code_list(
            metadata.get("target_symbols"),
            source_candidate.get("target_symbols"),
            metadata.get("stock_pool"),
            source_candidate.get("stock_pool"),
            dict(self.params or {}).get("target_symbols"),
            source_candidate_params.get("target_symbols"),
            dict(self.params or {}).get("stock_pool"),
            source_candidate_params.get("stock_pool"),
        )
        stock_pool = _dict_value(
            metadata.get("stock_pool"),
            source_candidate.get("stock_pool"),
            dict(self.params or {}).get("stock_pool"),
            source_candidate_params.get("stock_pool"),
            {"selection_mode": "explicit", "symbols": list(target_symbols)} if target_symbols else {},
        )
        research_task = _safe_normalize_research_task(_dict_value(
            metadata.get("research_task"),
            source_candidate.get("research_task"),
            dict(self.params or {}).get("research_task"),
            source_candidate_params.get("research_task"),
        ))
        event_context = _dict_value(
            metadata.get("event_context"),
            source_candidate.get("event_context"),
            dict(self.params or {}).get("event_context"),
            source_candidate_params.get("event_context"),
        )
        selection_logic = _list_value(
            metadata.get("selection_logic"),
            source_candidate.get("selection_logic"),
        )
        research_scope = _dict_value(
            metadata.get("research_scope"),
            source_candidate.get("research_scope"),
        )
        task_source = _task_source(research_task, event_context)
        holding_horizon = _dict_value(
            metadata.get("holding_horizon"),
            source_candidate.get("holding_horizon"),
            dict(self.params or {}).get("holding_horizon"),
            source_candidate_params.get("holding_horizon"),
        )
        if not holding_horizon:
            holding_horizon = _default_holding_horizon(self.strategy_type, research_task, task_source)
        trade_plan = _dict_value(
            metadata.get("trade_plan"),
            source_candidate.get("trade_plan"),
            dict(self.params or {}).get("trade_plan"),
            source_candidate_params.get("trade_plan"),
        )
        if not trade_plan:
            trade_plan = _default_trade_plan(self.strategy_type, task_source)
        risk_rules = _dict_value(
            metadata.get("risk_rules"),
            source_candidate.get("risk_rules"),
            dict(self.params or {}).get("risk_rules"),
            source_candidate_params.get("risk_rules"),
        )
        if not risk_rules:
            risk_rules = _default_risk_rules(task_source, holding_horizon)
        position_sizing = _dict_value(
            metadata.get("position_sizing"),
            source_candidate.get("position_sizing"),
            dict(self.params or {}).get("position_sizing"),
            source_candidate_params.get("position_sizing"),
        )
        if not position_sizing:
            position_sizing = _default_position_sizing(target_symbols)
        rebalance_rule = _dict_value(
            metadata.get("rebalance_rule"),
            source_candidate.get("rebalance_rule"),
            dict(self.params or {}).get("rebalance_rule"),
            source_candidate_params.get("rebalance_rule"),
        )
        if not rebalance_rule:
            rebalance_rule = _default_rebalance_rule(self.strategy_type, task_source)
        portfolio_spec = _dict_value(
            metadata.get("portfolio_spec"),
            source_candidate.get("portfolio_spec"),
            dict(self.params or {}).get("portfolio_spec"),
            source_candidate_params.get("portfolio_spec"),
        )
        if not portfolio_spec:
            portfolio_spec = _default_portfolio_spec(target_symbols)
        execution_assumptions = _dict_value(
            metadata.get("execution_assumptions"),
            source_candidate.get("execution_assumptions"),
            dict(self.params or {}).get("execution_assumptions"),
            source_candidate_params.get("execution_assumptions"),
        )
        if not execution_assumptions:
            execution_assumptions = _default_execution_assumptions(task_source)
        validation_profile = _dict_value(
            metadata.get("validation_profile"),
            source_candidate.get("validation_profile"),
            dict(self.params or {}).get("validation_profile"),
            source_candidate_params.get("validation_profile"),
        )
        if not validation_profile:
            validation_profile = _default_validation_profile(self.strategy_type, research_task, task_source)
        targeting_policy = _dict_value(
            metadata.get("targeting_policy"),
            source_candidate.get("targeting_policy"),
            dict(self.params or {}).get("targeting_policy"),
            source_candidate_params.get("targeting_policy"),
        )
        if not targeting_policy:
            targeting_policy = _default_targeting_policy(research_task)
        constraint_check = _dict_value(
            metadata.get("constraint_check"),
            source_candidate.get("constraint_check"),
            dict(self.params or {}).get("constraint_check"),
            source_candidate_params.get("constraint_check"),
        )
        if not constraint_check:
            constraint_check = _default_constraint_check(
                target_symbols=list(target_symbols),
                research_task=research_task,
                targeting_policy=targeting_policy,
            )
        candidate_params = {
            **dict(self.params or {}),
            "target_symbols": list(target_symbols),
            "stock_pool": dict(stock_pool),
            "research_task": dict(research_task),
            "event_context": dict(event_context),
            "holding_horizon": dict(holding_horizon),
            "trade_plan": dict(trade_plan),
            "risk_rules": dict(risk_rules),
            "position_sizing": dict(position_sizing),
            "rebalance_rule": dict(rebalance_rule),
            "portfolio_spec": dict(portfolio_spec),
            "execution_assumptions": dict(execution_assumptions),
            "validation_profile": dict(validation_profile),
            "targeting_policy": dict(targeting_policy),
            "constraint_check": dict(constraint_check),
        }
        return {
            'name': self.name or str(source_candidate.get('name') or ''),
            'description': self.description or str(source_candidate.get('description') or ''),
            'strategy_type': self.strategy_type,
            'params': candidate_params,
            'spawn_reason': self.description or self.name or f'{source}:{self.strategy_type}',
            'hypothesis': _scalar_value(metadata.get('hypothesis'), source_candidate.get('hypothesis')),
            'holding_horizon': dict(holding_horizon),
            'trade_plan': dict(trade_plan),
            'risk_rules': dict(risk_rules),
            'position_sizing': dict(position_sizing),
            'execution_notes': _scalar_value(metadata.get('execution_notes'), source_candidate.get('execution_notes')),
            'rebalance_rule': dict(rebalance_rule),
            'portfolio_spec': dict(portfolio_spec),
            'execution_assumptions': dict(execution_assumptions),
            'validation_profile': dict(validation_profile),
            'targeting_policy': dict(targeting_policy),
            'constraint_check': dict(constraint_check),
            'generation_reason': _dict_value(metadata.get('generation_reason'), source_candidate.get('generation_reason')),
            'generator_type': _scalar_value(metadata.get('generator_type'), source_candidate.get('generator_type'), source) or source,
            'optimizer_type': _scalar_value(metadata.get('optimizer_type'), source_candidate.get('optimizer_type')),
            'llm_prompt': _dict_value(metadata.get('llm_prompt'), source_candidate.get('llm_prompt')),
            'llm_response': _dict_value(metadata.get('llm_response'), source_candidate.get('llm_response')),
            'target_symbols': list(target_symbols),
            'stock_pool': dict(stock_pool),
            'selection_logic': list(selection_logic),
            'research_scope': dict(research_scope),
            'research_task': dict(research_task),
            'event_context': dict(event_context),
            'task_run_id': _scalar_value(metadata.get('task_run_id'), source_candidate.get('task_run_id')),
            'parent_strategy_id': _scalar_value(metadata.get('parent_strategy_id'), source_candidate.get('parent_strategy_id')),
            'pipeline_provenance': _dict_value(metadata.get('pipeline_provenance')),
            'experiment_id': experiment_id,
            'tags': list(dict.fromkeys(['ai_generated', source, self.strategy_type, *(self.tags or [])])),
        }
