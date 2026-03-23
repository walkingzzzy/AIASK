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
        return {
            'strategy_type': self.strategy_type,
            'params': self.params,
            'spawn_reason': self.description or self.name or f'{source}:{self.strategy_type}',
            'hypothesis': metadata.get('hypothesis'),
            'holding_horizon': dict(metadata.get('holding_horizon') or {}),
            'trade_plan': dict(metadata.get('trade_plan') or {}),
            'risk_rules': dict(metadata.get('risk_rules') or {}),
            'position_sizing': dict(metadata.get('position_sizing') or {}),
            'execution_notes': metadata.get('execution_notes'),
            'rebalance_rule': dict(metadata.get('rebalance_rule') or {}),
            'portfolio_spec': dict(metadata.get('portfolio_spec') or {}),
            'execution_assumptions': dict(metadata.get('execution_assumptions') or {}),
            'validation_profile': dict(metadata.get('validation_profile') or {}),
            'targeting_policy': dict(metadata.get('targeting_policy') or {}),
            'constraint_check': dict(metadata.get('constraint_check') or {}),
            'generation_reason': metadata.get('generation_reason') or {},
            'generator_type': metadata.get('generator_type') or source,
            'optimizer_type': metadata.get('optimizer_type'),
            'llm_prompt': metadata.get('llm_prompt') or {},
            'llm_response': metadata.get('llm_response') or {},
            'target_symbols': list(metadata.get('target_symbols') or []),
            'stock_pool': dict(metadata.get('stock_pool') or {}),
            'selection_logic': list(metadata.get('selection_logic') or []),
            'research_scope': dict(metadata.get('research_scope') or {}),
            'research_task': dict(metadata.get('research_task') or {}),
            'event_context': dict(metadata.get('event_context') or {}),
            'task_run_id': metadata.get('task_run_id'),
            'parent_strategy_id': metadata.get('parent_strategy_id'),
            'experiment_id': experiment_id,
            'tags': list(dict.fromkeys(['ai_generated', source, self.strategy_type, *(self.tags or [])])),
        }
