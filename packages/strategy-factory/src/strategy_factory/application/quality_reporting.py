"""Shared quality-gate normalization and reporting helpers.

These helpers live in the strategy_factory service layer so both the
factory pipeline and strategy_manager lifecycle can share the same gate
report contract without creating reverse dependencies on manager helpers.
"""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'quality_reporting_parts', ['normalizers.py', 'policy.py', 'evaluation.py'], future_annotations=True)
