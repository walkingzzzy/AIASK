"""StrategySpec data model facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from akshare_mcp._fragment_loader import exec_block as _exec_block

from .constants import *  # noqa: F401,F403
from .defaults import *  # noqa: F401,F403
from .dsl_builder import *  # noqa: F401,F403
from .normalizers import *  # noqa: F401,F403
from .runtime_contracts import *  # noqa: F401,F403

_exec_block(
    globals(),
    'model_parts',
    'def _strategy_spec_to_candidate(self, source: str, experiment_id: str) -> dict:\n',
    ['spec_types.py', 'spec_validation.py', 'spec_serialization.py', 'part_4.py'],
    future_annotations=True,
)


@dataclass
class StrategySpec:
    strategy_type: str
    params: dict[str, Any]
    name: str = ''
    description: str = ''
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_candidate(self, source: str, experiment_id: str) -> dict:
        return _strategy_spec_to_candidate(self, source, experiment_id)
