#!/usr/bin/env python3
"""Compatibility entrypoint for the cleaned factory supervisor.

The old implementation mixed the three factory processes with SignalTracker.
That made the root startup story ambiguous. Keep this filename for existing
operator habits, but delegate to run_three_factories.py, which starts only:

- Strategy Factory
- Factor Mining Factory
- Incubation Factory
- Market Event Ingest

Run SignalTracker separately through run_signal_tracker.py when it is needed.
"""

from __future__ import annotations

import sys

from run_three_factories import main


_LEGACY_VALUE_OPTIONS = {
    "--console-queue-size",
    "--factor-silent-restart",
    "--incubation-silent-restart",
    "--signal-tracker-run-time",
    "--signal-tracker-silent-restart",
    "--silent-restart",
    "--strategy-silent-restart",
}

_LEGACY_FLAG_OPTIONS = {
    "--no-signal-tracker",
    "--signal-tracker-verbose",
}


def _drop_legacy_options(argv: list[str]) -> list[str]:
    cleaned: list[str] = []
    dropped: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in _LEGACY_FLAG_OPTIONS:
            dropped.append(arg)
            index += 1
            continue
        if arg in _LEGACY_VALUE_OPTIONS:
            dropped.append(arg)
            index += 2
            continue
        cleaned.append(arg)
        index += 1
    if dropped:
        joined = ", ".join(dropped)
        print(f"run_all_factories.py: ignored legacy options: {joined}", file=sys.stderr)
    return cleaned


if __name__ == "__main__":
    raise SystemExit(main(_drop_legacy_options(sys.argv[1:])))
