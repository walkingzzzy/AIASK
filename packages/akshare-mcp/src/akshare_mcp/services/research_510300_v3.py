"""Modularized loader for research_510300_v3.py."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'research_510300_v3_parts', ['data_loading.py', 'feature_engineering.py', 'evaluation.py', 'reporting.py', 'part_5.py'], future_annotations=True)
