"""Stable Data Transfer Objects for the strategy factory product interface.

These DTOs decouple the BFF / MCP tool layer from the raw run result dicts,
providing versioned, stable contracts for:

- FactoryStatusDTO        → factory_status tool
- FactoryRunSummaryDTO    → factory_runs list item
- FactoryRunDetailDTO     → factory_run_detail tool
- StageResultDTO          → single stage within a run detail

P5 implementation: product layer reads from DTOs, not from raw run dicts.
"""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'dto_parts', ['common.py', 'factory.py', 'review.py', 'runtime.py', 'incubation.py'], future_annotations=True)
