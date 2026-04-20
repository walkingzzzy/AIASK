"""Governance plane artifact contracts for strategy factory runs.

P2 goal: make gates, dedup, submission, and governance evidence observable as
an explicit governance plane instead of remaining an implicit by-product of the
submission pipeline.
"""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'governance_plane_contract_parts', ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py', 'models.py'], future_annotations=True)
