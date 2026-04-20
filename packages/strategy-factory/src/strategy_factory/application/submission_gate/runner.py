"""Shared submission-stage quality gate evaluation.

This module centralizes the Gate-3 quality evaluation used by both
strategy_manager submit/recheck flows and strategy_factory submitter.
"""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'runner_parts', ['normalizers.py', 'semantic_context.py', 'attempt_adjustment.py', 'multiple_testing.py', 'trade_profile.py'], future_annotations=True)
