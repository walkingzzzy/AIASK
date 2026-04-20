"""Supporting services for strategy autonomy orchestration."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'strategy_autonomy_components_parts', ['context.py', 'specs.py'], future_annotations=True)
