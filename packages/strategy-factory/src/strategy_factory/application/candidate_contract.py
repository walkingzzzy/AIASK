"""Shared portfolio candidate contract helpers."""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'candidate_contract_parts', ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py'], future_annotations=True)
