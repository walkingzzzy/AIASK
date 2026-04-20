"""Unified stock deep-analysis workflow service."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'stock_deep_analysis_parts', ['context.py', 'specs.py', 'runtime.py', 'postprocess.py'], future_annotations=True)
