"""Shared strategy lifecycle primitives used by both services and tools layers.

This module exists to break the circular dependency where services
(promotion_pipeline, incubation, runtime_control) imported from the
tools layer (tools.managers.strategy_manager).  Now both sides import
from this services-level module instead.
"""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'strategy_lifecycle_shared_parts', ['context.py', 'specs.py', 'runtime.py', 'postprocess.py'], future_annotations=True)
