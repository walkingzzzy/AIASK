"""Strategy generators: rule-based and LLM-proxy strategy candidate generation."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'strategy_generators_parts', ['context.py', 'specs.py', 'runtime.py'], future_annotations=True)
