"""Asyncio-based signal tracker — daily forward signal generation & verification.

Runs daily at 18:30 CST (after FactorScheduler at 18:00):
- Phase A: Generate signals for all listed/incubating strategies
- Phase B: Compute forward returns for past signals (1/5/10/20 day)
- Phase C: Run lifecycle scan (auto-promote/demote strategies)

Usage:
    from .signal_tracker import get_signal_tracker
    tracker = get_signal_tracker()
    tracker.start()
"""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'signal_tracker_parts', ['context.py', 'specs.py', 'runtime.py'], future_annotations=False)
