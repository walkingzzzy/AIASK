"""Helpers for P3 budget feedback normalization and scoring."""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), '_budget_feedback_parts', ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py', 'models.py', 'orchestrator.py'], future_annotations=True)
