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
        return {
            'strategy_type': self.strategy_type,
            'params': self.params,
            'spawn_reason': self.description or self.name or f'{source}:{self.strategy_type}',
            'generation_reason': self.metadata.get('generation_reason') or {},
            'generator_type': self.metadata.get('generator_type') or source,
            'optimizer_type': self.metadata.get('optimizer_type'),
            'llm_prompt': self.metadata.get('llm_prompt') or {},
            'llm_response': self.metadata.get('llm_response') or {},
            'target_symbols': list(self.metadata.get('target_symbols') or []),
            'stock_pool': dict(self.metadata.get('stock_pool') or {}),
            'selection_logic': list(self.metadata.get('selection_logic') or []),
            'research_scope': dict(self.metadata.get('research_scope') or {}),
            'research_task': dict(self.metadata.get('research_task') or {}),
            'event_context': dict(self.metadata.get('event_context') or {}),
            'task_run_id': self.metadata.get('task_run_id'),
            'parent_strategy_id': self.metadata.get('parent_strategy_id'),
            'experiment_id': experiment_id,
            'tags': list(dict.fromkeys(['ai_generated', source, self.strategy_type, *(self.tags or [])])),
        }
