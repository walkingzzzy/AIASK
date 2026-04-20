"""Strategy manager helpers: NAV calculation, state management, quality report, incubation overview."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'strategy_mgr_helpers_parts', ['parsers.py', 'payloads.py', 'formatters.py', 'actions.py', 'orchestrator.py', 'part_6.py', 'part_7.py'], future_annotations=False)
