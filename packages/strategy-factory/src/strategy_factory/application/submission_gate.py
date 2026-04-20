"""Shared submission-stage quality gate evaluation.

This module centralizes the Gate-3 quality evaluation used by both
strategy_manager submit/recheck flows and strategy_factory submitter.
"""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'submission_gate_parts', ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py', 'models.py', 'orchestrator.py', 'part_7.py'], future_annotations=True)
