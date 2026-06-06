#!/usr/bin/env python3
"""Compatibility supervisor entrypoint for AIASK factory runners.

The canonical factory supervisor lives at
``scripts/factories/run_three_factories.py``. This module keeps the historical
root import surface alive while delegating CLI execution to the canonical
supervisor.
"""

from __future__ import annotations

import argparse
import asyncio
import codecs
import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import TextIO


PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPT_DIR = PROJECT_ROOT / "scripts" / "factories"
CANONICAL_SUPERVISOR = SCRIPT_DIR / "run_three_factories.py"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "factory_supervisor"
CHILD_OUTPUT_READ_CHUNK_SIZE = 32 * 1024
CHILD_OUTPUT_CONSOLE_CHUNK_CHARS = 6000


@dataclass(frozen=True)
class FactorySpec:
    name: str
    script: Path
    args: tuple[str, ...] = ()
    silent_restart_sec: int = 0

    @property
    def command(self) -> list[str]:
        return [sys.executable, str(self.script), *self.args]


@dataclass
class FactoryState:
    name: str
    pid: int | None = None
    status: str = "pending"
    started_at: datetime | None = None
    last_output_at: datetime | None = None
    restart_count: int = 0
    last_exit_code: int | None = None
    last_message: str = ""


_CONSOLE_QUEUE: asyncio.Queue[str] | None = None
_CONSOLE_DROPPED = 0


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _non_negative_seconds(value: int | None) -> int:
    return max(0, int(value or 0))


def _console(message: str) -> None:
    global _CONSOLE_DROPPED
    line = f"{_timestamp()} {message}"
    queue = _CONSOLE_QUEUE
    if queue is not None:
        try:
            queue.put_nowait(line)
        except asyncio.QueueFull:
            _CONSOLE_DROPPED += 1
        return
    try:
        print(line, flush=True)
    except Exception:
        pass


def _iter_console_output_parts(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    for line in normalized.split("\n"):
        if not line:
            continue
        remaining = line
        while remaining:
            parts.append(remaining[:CHILD_OUTPUT_CONSOLE_CHUNK_CHARS])
            remaining = remaining[CHILD_OUTPUT_CONSOLE_CHUNK_CHARS:]
    return parts


def _record_child_output(
    spec: FactorySpec,
    text: str,
    log_file: TextIO,
    *,
    stream_logs: bool,
    state: FactoryState,
) -> None:
    state.last_output_at = datetime.now(timezone.utc)
    state.last_message = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")[-240:]
    log_file.write(text)
    log_file.flush()
    if not stream_logs:
        return
    for part in _iter_console_output_parts(text):
        _console(f"[{spec.name}] {part}")


async def _tee_child_output(
    spec: FactorySpec,
    stream: asyncio.StreamReader | None,
    log_file: TextIO,
    *,
    stream_logs: bool,
    state: FactoryState,
) -> None:
    if stream is None:
        return
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while True:
        chunk = await stream.read(CHILD_OUTPUT_READ_CHUNK_SIZE)
        if not chunk:
            break
        text = decoder.decode(chunk)
        if text:
            _record_child_output(spec, text, log_file, stream_logs=stream_logs, state=state)
    tail = decoder.decode(b"", final=True)
    if tail:
        _record_child_output(spec, tail, log_file, stream_logs=stream_logs, state=state)


def _build_specs(args: argparse.Namespace) -> list[FactorySpec]:
    specs: list[FactorySpec] = []

    if not getattr(args, "no_strategy", False):
        strategy_args: list[str] = []
        if getattr(args, "strategy_interval", None) is not None:
            strategy_args.extend(["--interval", str(args.strategy_interval)])
        if getattr(args, "strategy_codes", None):
            strategy_args.extend(["--codes", *[str(code) for code in args.strategy_codes]])
        specs.append(
            FactorySpec(
                name="strategy_factory",
                script=PROJECT_ROOT / "run_strategy_factory.py",
                args=tuple(strategy_args),
                silent_restart_sec=_non_negative_seconds(
                    getattr(args, "strategy_silent_restart", None)
                    if getattr(args, "strategy_silent_restart", None) is not None
                    else getattr(args, "silent_restart", 0)
                ),
            )
        )

    if not getattr(args, "no_factor", False):
        factor_args: list[str] = []
        if int(getattr(args, "factor_interval", 0) or 0) > 0:
            factor_args.extend(["--interval", str(args.factor_interval)])
        if getattr(args, "factor_candidates", None) is not None:
            factor_args.extend(["--candidates", str(args.factor_candidates)])
        if getattr(args, "factor_generations", None) is not None:
            factor_args.extend(["--generations", str(args.factor_generations)])
        if getattr(args, "factor_engines", None):
            factor_args.extend(["--engines", *[str(item) for item in args.factor_engines]])
        if getattr(args, "factor_codes", None):
            factor_args.extend(["--codes", *[str(code) for code in args.factor_codes]])
        specs.append(
            FactorySpec(
                name="factor_mining_factory",
                script=SCRIPT_DIR / "run_factor_mining_factory.py",
                args=tuple(factor_args),
                silent_restart_sec=_non_negative_seconds(getattr(args, "factor_silent_restart", 0)),
            )
        )

    if not getattr(args, "no_incubation", False):
        incubation_args = [
            "--daemon",
            "--run-time",
            str(getattr(args, "incubation_run_time", "18:30") or "18:30"),
        ]
        if getattr(args, "incubation_dry_run", False):
            incubation_args.append("--dry-run")
        if getattr(args, "incubation_verbose", False):
            incubation_args.append("--verbose")
        specs.append(
            FactorySpec(
                name="incubation_factory",
                script=SCRIPT_DIR / "run_incubation_factory.py",
                args=tuple(incubation_args),
                silent_restart_sec=_non_negative_seconds(getattr(args, "incubation_silent_restart", 0)),
            )
        )

    if not getattr(args, "no_signal_tracker", True):
        signal_args = [
            "--daemon",
            "--run-time",
            str(getattr(args, "signal_tracker_run_time", "17:00") or "17:00"),
        ]
        if getattr(args, "signal_tracker_verbose", False):
            signal_args.append("--verbose")
        specs.append(
            FactorySpec(
                name="signal_tracker",
                script=SCRIPT_DIR / "run_signal_tracker.py",
                args=tuple(signal_args),
                silent_restart_sec=_non_negative_seconds(getattr(args, "signal_tracker_silent_restart", 0)),
            )
        )

    return specs


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
        print(f"run_all_factories.py: ignored legacy options: {', '.join(dropped)}", file=sys.stderr)
    return cleaned


def _load_canonical_supervisor() -> ModuleType:
    module_name = "_aiask_canonical_run_three_factories"
    spec = importlib.util.spec_from_file_location(
        module_name,
        CANONICAL_SUPERVISOR,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load canonical factory supervisor: {CANONICAL_SUPERVISOR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    module = _load_canonical_supervisor()
    return int(module.main(_drop_legacy_options(list(argv or []))) or 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
