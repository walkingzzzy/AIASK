"""StrategySpec data model facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from akshare_mcp._fragment_loader import exec_block as _exec_block

from . import constants as _constants
from . import defaults as _defaults
from . import dsl_builder as _dsl_builder
from . import normalizers as _normalizers
from . import runtime_contracts as _runtime_contracts

for _module in (
    _constants,
    _normalizers,
    _defaults,
    _dsl_builder,
    _runtime_contracts,
):
    globals().update(
        {
            name: getattr(_module, name)
            for name in dir(_module)
            if not name.startswith("__")
        }
    )

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
