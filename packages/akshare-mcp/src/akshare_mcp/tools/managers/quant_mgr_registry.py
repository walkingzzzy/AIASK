"""Registry and memory handlers for quant_manager artifact workflows."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'quant_mgr_registry_parts', ['parsers.py', 'payloads.py', 'formatters.py'], future_annotations=True)
