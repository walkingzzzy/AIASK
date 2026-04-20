"""Execution-quality evaluation helpers."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'execution_quality_parts', ['execution_metrics.py', 'execution_distributions.py'], future_annotations=True)
