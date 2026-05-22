#!/usr/bin/env python3
"""Run the three autonomous factory runners as independent long-lived processes.

This supervisor only owns process lifecycle. It does not import or execute MCP or
Agent services, and it does not run factory code in-process. Each factory keeps
its own runner semantics:

    - Strategy Factory: ``run_strategy_factory.py`` continuous interval mode.
    - Factor Mining Factory: ``run_factor_mining_factory.py`` schedule mode by default.
    - Incubation Factory: ``run_incubation_factory.py --daemon``.

The supervisor runs until Ctrl+C/SIGTERM and restarts a child if it exits.
"""

from __future__ import annotations

import argparse
import asyncio
import codecs
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


PROJECT_ROOT = Path(__file__).resolve().parent
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


def _configure_stdio_utf8() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleCP(65001)
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _load_dotenv(env: dict[str, str]) -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in env:
            env[key] = value.strip()


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    _load_dotenv(env)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("STRATEGY_FACTORY_ENABLED", "false")
    env.setdefault("STRATEGY_FACTORY_INLINE_EXECUTION_ENABLED", "false")
    return env


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


_CONSOLE_QUEUE: asyncio.Queue[str] | None = None
_CONSOLE_DROPPED = 0


def _elapsed_seconds(started_at: datetime | None) -> int:
    if started_at is None:
        return 0
    return int((datetime.now(timezone.utc) - started_at).total_seconds())


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
        # Keep child stdout drains alive even if the supervisor console breaks.
        pass


def _print_console_line(line: str) -> None:
    print(line, flush=True)


async def _console_writer_loop(
    queue: asyncio.Queue[str],
    *,
    stop_event: asyncio.Event,
) -> None:
    """Drain supervisor console messages without blocking child stdout readers."""
    global _CONSOLE_DROPPED
    while not stop_event.is_set() or not queue.empty():
        try:
            line = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        dropped = _CONSOLE_DROPPED
        if dropped:
            _CONSOLE_DROPPED = 0
            line = f"{line} | supervisor_console_dropped={dropped}"
        try:
            await asyncio.to_thread(_print_console_line, line)
        except Exception:
            pass
        finally:
            queue.task_done()


def _write_log_header(log_file: TextIO, spec: FactorySpec) -> None:
    log_file.write("\n" + "=" * 100 + "\n")
    log_file.write(f"{_timestamp()} starting {spec.name}\n")
    log_file.write("command: " + subprocess.list2cmdline(spec.command) + "\n")
    log_file.write("=" * 100 + "\n")
    log_file.flush()


async def _wait_for_process_exit(
    process: asyncio.subprocess.Process,
    *,
    wait_task: asyncio.Task[int] | None = None,
    timeout_sec: int = 30,
) -> int | None:
    if process.returncode is not None:
        return process.returncode
    try:
        waiter = asyncio.shield(wait_task) if wait_task is not None else process.wait()
        return await asyncio.wait_for(waiter, timeout=max(0.1, timeout_sec))
    except asyncio.TimeoutError:
        return None


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    if sys.platform != "win32" or process.pid is None:
        return
    try:
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(killer.wait(), timeout=10)
    except Exception:
        pass


async def _terminate_process(
    process: asyncio.subprocess.Process,
    *,
    timeout_sec: int = 30,
    wait_task: asyncio.Task[int] | None = None,
) -> int | None:
    if process.returncode is not None:
        return process.returncode
    try:
        process.terminate()
    except ProcessLookupError:
        return await _wait_for_process_exit(process, wait_task=wait_task, timeout_sec=5)
    except Exception:
        pass
    return_code = await _wait_for_process_exit(
        process,
        wait_task=wait_task,
        timeout_sec=timeout_sec,
    )
    if return_code is not None:
        return return_code
    await _kill_process_tree(process)
    try:
        process.kill()
    except ProcessLookupError:
        return await _wait_for_process_exit(process, wait_task=wait_task, timeout_sec=5)
    except Exception:
        pass
    return await _wait_for_process_exit(process, wait_task=wait_task, timeout_sec=10)

async def _cancel_task(task: asyncio.Task[object]) -> None:
    if task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _restart_silent_child(
    spec: FactorySpec,
    process: asyncio.subprocess.Process,
    state: FactoryState,
    *,
    silent_restart_sec: int,
    wait_task: asyncio.Task[int] | None = None,
) -> None:
    if process.returncode is not None or silent_restart_sec <= 0:
        return
    state.status = "restarting_silent"
    state.last_message = f"no output for {silent_restart_sec}s; restarting"
    _console(
        f"[{spec.name}] no output for {silent_restart_sec}s; "
        f"restarting pid={process.pid}"
    )
    return_code = await _terminate_process(
        process,
        timeout_sec=15,
        wait_task=wait_task,
    )
    if return_code is None and process.returncode is None:
        state.status = "terminate_timeout"
        state.last_message = f"failed to stop silent child pid={process.pid}"
        _console(f"[{spec.name}] failed to stop silent child pid={process.pid}")


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


def _record_child_output(
    spec: FactorySpec,
    text: str,
    log_file: TextIO,
    *,
    stream_logs: bool,
    state: FactoryState,
) -> None:
    state.last_output_at = datetime.now(timezone.utc)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    state.last_message = normalized[-240:]
    log_file.write(text)
    log_file.flush()
    if not stream_logs:
        return
    for part in _iter_console_output_parts(text):
        _console(f"[{spec.name}] {part}")


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


async def _run_factory(
    spec: FactorySpec,
    *,
    stop_event: asyncio.Event,
    log_dir: Path,
    restart_delay_sec: int,
    stream_logs: bool,
    state: FactoryState,
) -> None:
    log_path = log_dir / f"{spec.name}.log"
    env = _child_env()

    while not stop_event.is_set():
        if not spec.script.exists():
            state.status = "missing_script"
            state.last_message = f"missing script: {spec.script}"
            _console(f"[{spec.name}] {state.last_message}")
            await _sleep_until_stop(stop_event, restart_delay_sec)
            continue

        with log_path.open("a", encoding="utf-8", buffering=1) as log_file:
            _write_log_header(log_file, spec)
            state.status = "starting"
            state.started_at = datetime.now(timezone.utc)
            state.last_output_at = state.started_at
            state.last_exit_code = None
            _console(f"[{spec.name}] starting; log={log_path}")
            process = await asyncio.create_subprocess_exec(
                *spec.command,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            state.pid = process.pid
            state.status = "running"
            state.last_message = f"pid={process.pid}"
            _console(f"[{spec.name}] running pid={process.pid}")

            output_task = asyncio.create_task(
                _tee_child_output(
                    spec,
                    process.stdout,
                    log_file,
                    stream_logs=stream_logs,
                    state=state,
                ),
                name=f"{spec.name}:output",
            )
            wait_task = asyncio.create_task(process.wait(), name=f"{spec.name}:wait")
            stop_task = asyncio.create_task(stop_event.wait(), name=f"{spec.name}:stop")
            silent_task: asyncio.Task[None] | None = None
            if spec.silent_restart_sec > 0:
                silent_task = asyncio.create_task(
                    _watch_silent_child(
                        spec,
                        process,
                        state,
                        stop_event=stop_event,
                        silent_restart_sec=spec.silent_restart_sec,
                    ),
                    name=f"{spec.name}:silent-watch",
                )

            watched_tasks: set[asyncio.Task[object]] = {wait_task, stop_task, output_task}
            if silent_task is not None:
                watched_tasks.add(silent_task)
            done, pending = await asyncio.wait(
                watched_tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if output_task in done and not wait_task.done() and not stop_task.done():
                output_results = await asyncio.gather(output_task, return_exceptions=True)
                output_error = output_results[0] if output_results else None
                state.status = "output_reader_failed"
                if isinstance(output_error, Exception):
                    state.last_message = f"output reader exited: {output_error}"
                    _console(f"[{spec.name}] output reader exited; restarting child pid={process.pid}: {output_error}")
                else:
                    state.last_message = "output reader exited while child still running"
                    _console(f"[{spec.name}] output reader exited while child still running; restarting child pid={process.pid}")
                await _terminate_process(process, timeout_sec=15, wait_task=wait_task)
            elif stop_task in done and not wait_task.done():
                state.status = "stopping"
                state.last_message = "supervisor stop requested"
                _console(f"[{spec.name}] stopping pid={process.pid}")
                await _terminate_process(process, wait_task=wait_task)
            elif silent_task is not None and silent_task in done and not wait_task.done() and not stop_task.done():
                await _restart_silent_child(
                    spec,
                    process,
                    state,
                    silent_restart_sec=spec.silent_restart_sec,
                    wait_task=wait_task,
                )

            await _cancel_task(stop_task)
            if silent_task is not None:
                await _cancel_task(silent_task)
            return_code = await _wait_for_process_exit(
                process,
                wait_task=wait_task,
                timeout_sec=10,
            )
            if return_code is None and process.returncode is None:
                state.status = "terminate_timeout"
                state.last_message = f"pid={process.pid} did not exit after termination"
                _console(f"[{spec.name}] pid={process.pid} did not exit after termination; waiting")
                await _kill_process_tree(process)
                stop_wait_task = asyncio.create_task(
                    stop_event.wait(),
                    name=f"{spec.name}:terminate-timeout-stop",
                )
                done_after_timeout, _ = await asyncio.wait(
                    {wait_task, stop_wait_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                await _cancel_task(stop_wait_task)
                if wait_task in done_after_timeout:
                    return_code = await wait_task
                else:
                    await _cancel_task(wait_task)
                    await _cancel_task(output_task)
                    return
            elif return_code is None:
                return_code = process.returncode
            await _cancel_task(wait_task)
            if output_task.done():
                output_results = await asyncio.gather(output_task, return_exceptions=True)
                output_error = output_results[0] if output_results else None
                if isinstance(output_error, Exception):
                    state.last_message = f"output reader error: {output_error}"
            else:
                try:
                    await asyncio.wait_for(asyncio.shield(output_task), timeout=5)
                except asyncio.TimeoutError:
                    _console(f"[{spec.name}] output pipe did not close; detaching reader")
                    state.last_message = "output pipe did not close after process exit"
                    await _cancel_task(output_task)
                else:
                    output_results = await asyncio.gather(output_task, return_exceptions=True)
                    output_error = output_results[0] if output_results else None
                    if isinstance(output_error, Exception):
                        state.last_message = f"output reader error: {output_error}"

            finished_at = _timestamp()
            log_file.write(f"\n{finished_at} {spec.name} exited with code {return_code}\n")
            log_file.flush()

        state.pid = None
        state.status = "stopped" if stop_event.is_set() else "exited"
        state.last_exit_code = return_code
        state.last_message = f"exit_code={return_code}"
        if stop_event.is_set():
            break
        state.restart_count += 1
        _console(
            f"[{spec.name}] exited with code {return_code}; "
            f"restart #{state.restart_count} in {restart_delay_sec}s"
        )
        await _sleep_until_stop(stop_event, restart_delay_sec)


async def _watch_silent_child(
    spec: FactorySpec,
    process: asyncio.subprocess.Process,
    state: FactoryState,
    *,
    stop_event: asyncio.Event,
    silent_restart_sec: int,
) -> None:
    if silent_restart_sec <= 0:
        await stop_event.wait()
        return
    while process.returncode is None and not stop_event.is_set():
        await _sleep_until_stop(stop_event, min(30, silent_restart_sec))
        if process.returncode is not None or stop_event.is_set():
            return
        last_output_at = state.last_output_at or state.started_at
        if last_output_at is None:
            continue
        silent_for = int((datetime.now(timezone.utc) - last_output_at).total_seconds())
        if silent_for >= silent_restart_sec:
            return


async def _sleep_until_stop(stop_event: asyncio.Event, seconds: int) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(0, seconds))
    except asyncio.TimeoutError:
        return


async def _heartbeat_loop(
    states: dict[str, FactoryState],
    *,
    stop_event: asyncio.Event,
    interval_sec: int,
) -> None:
    if interval_sec <= 0:
        return
    while not stop_event.is_set():
        await _sleep_until_stop(stop_event, interval_sec)
        if stop_event.is_set():
            break
        chunks: list[str] = []
        for state in states.values():
            runtime = _elapsed_seconds(state.started_at)
            pid = state.pid if state.pid is not None else "-"
            chunks.append(
                f"{state.name}: status={state.status} pid={pid} "
                f"uptime={runtime}s silent={_elapsed_seconds(state.last_output_at)}s "
                f"restarts={state.restart_count}"
            )
        _console("[supervisor] heartbeat | " + " | ".join(chunks))


def _build_specs(args: argparse.Namespace) -> list[FactorySpec]:
    specs: list[FactorySpec] = []
    strategy_silent_restart = (
        args.strategy_silent_restart
        if args.strategy_silent_restart is not None
        else args.silent_restart
    )

    if not args.no_strategy:
        strategy_args: list[str] = []
        if args.strategy_interval is not None:
            strategy_args.extend(["--interval", str(args.strategy_interval)])
        if args.strategy_codes:
            strategy_args.extend(["--codes", *args.strategy_codes])
        specs.append(
            FactorySpec(
                name="strategy_factory",
                script=PROJECT_ROOT / "run_strategy_factory.py",
                args=tuple(strategy_args),
                silent_restart_sec=_non_negative_seconds(strategy_silent_restart),
            )
        )

    if not args.no_factor:
        factor_args: list[str] = []
        if args.factor_interval > 0:
            factor_args.extend(["--interval", str(args.factor_interval)])
        if args.factor_candidates is not None:
            factor_args.extend(["--candidates", str(args.factor_candidates)])
        if args.factor_generations is not None:
            factor_args.extend(["--generations", str(args.factor_generations)])
        if args.factor_engines:
            factor_args.extend(["--engines", *args.factor_engines])
        if args.factor_codes:
            factor_args.extend(["--codes", *args.factor_codes])
        specs.append(
            FactorySpec(
                name="factor_mining_factory",
                script=PROJECT_ROOT / "run_factor_mining_factory.py",
                args=tuple(factor_args),
                silent_restart_sec=_non_negative_seconds(args.factor_silent_restart),
            )
        )

    if not args.no_incubation:
        incubation_args: list[str] = ["--daemon", "--run-time", args.incubation_run_time]
        if args.incubation_dry_run:
            incubation_args.append("--dry-run")
        if args.incubation_verbose:
            incubation_args.append("--verbose")
        specs.append(
            FactorySpec(
                name="incubation_factory",
                script=PROJECT_ROOT / "run_incubation_factory.py",
                args=tuple(incubation_args),
                silent_restart_sec=_non_negative_seconds(args.incubation_silent_restart),
            )
        )

    return specs


async def _run_supervisor(args: argparse.Namespace) -> int:
    global _CONSOLE_QUEUE
    log_dir = Path(args.log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    specs = _build_specs(args)
    if not specs:
        print("No factories selected.", file=sys.stderr)
        return 2
    states = {spec.name: FactoryState(name=spec.name) for spec in specs}

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    _CONSOLE_QUEUE = asyncio.Queue(maxsize=max(1000, int(args.console_queue_size or 0)))

    def request_stop(signum: int | None = None, _frame: object | None = None) -> None:
        name = signal.Signals(signum).name if signum is not None else "manual"
        print(f"\nReceived {name}; stopping child factory processes...", flush=True)
        loop.call_soon_threadsafe(stop_event.set)

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(signum, request_stop)
        except Exception:
            pass

    print("=" * 100)
    print(f"{_timestamp()} AIASK factory supervisor started")
    print(f"{_timestamp()} project_root: {PROJECT_ROOT}")
    print(f"{_timestamp()} log_dir:      {log_dir}")
    print(f"{_timestamp()} stream_logs:  {not args.quiet}")
    print(f"{_timestamp()} heartbeat:    {args.heartbeat_interval}s")
    print(f"{_timestamp()} factories:")
    for spec in specs:
        silent_restart = (
            f"{spec.silent_restart_sec}s"
            if spec.silent_restart_sec > 0
            else "disabled"
        )
        print(
            f"{_timestamp()}   - {spec.name}: "
            f"{subprocess.list2cmdline(spec.command)} "
            f"(silent_restart={silent_restart})"
        )
    print(f"{_timestamp()} Press Ctrl+C to stop.")
    print("=" * 100, flush=True)

    tasks = [
        asyncio.create_task(
            _run_factory(
                spec,
                stop_event=stop_event,
                log_dir=log_dir,
                restart_delay_sec=args.restart_delay,
                stream_logs=not args.quiet,
                state=states[spec.name],
            ),
            name=spec.name,
        )
        for spec in specs
    ]
    tasks.append(
        asyncio.create_task(
            _heartbeat_loop(
                states,
                stop_event=stop_event,
                interval_sec=args.heartbeat_interval,
            ),
            name="supervisor:heartbeat",
        )
    )
    tasks.append(
        asyncio.create_task(
            _console_writer_loop(
                _CONSOLE_QUEUE,
                stop_event=stop_event,
            ),
            name="supervisor:console-writer",
        )
    )
    try:
        await stop_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        _CONSOLE_QUEUE = None
    _console("Factory supervisor stopped.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Strategy Factory, Factor Mining Factory, and Incubation Factory continuously.",
    )
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for child process logs.")
    parser.add_argument("--restart-delay", type=int, default=30, help="Seconds to wait before restarting an exited child.")
    parser.add_argument("--heartbeat-interval", type=int, default=60, help="Seconds between supervisor heartbeat logs; 0 disables.")
    parser.add_argument(
        "--console-queue-size",
        type=int,
        default=10000,
        help="Max queued supervisor console lines before dropping; protects child stdout drains.",
    )
    parser.add_argument(
        "--silent-restart",
        type=int,
        default=0,
        help=(
            "Compatibility alias for --strategy-silent-restart. "
            "Schedule-based factor/incubation daemons are not restarted for silence unless their own options are set."
        ),
    )
    parser.add_argument("--quiet", action="store_true", help="Do not stream child logs to console; still writes log files.")

    parser.add_argument("--no-strategy", action="store_true", help="Do not start Strategy Factory.")
    parser.add_argument(
        "--strategy-interval",
        type=int,
        default=None,
        help="Strategy Factory interval seconds; omit to let the runner resolve env-based cadence.",
    )
    parser.add_argument("--strategy-codes", nargs="*", help="Optional Strategy Factory target codes.")
    parser.add_argument(
        "--strategy-silent-restart",
        type=int,
        default=None,
        help="Restart Strategy Factory after this many seconds without output; defaults to --silent-restart.",
    )

    parser.add_argument("--no-factor", action="store_true", help="Do not start Factor Mining Factory.")
    parser.add_argument("--factor-interval", type=int, default=0, help="Factor Mining fixed interval seconds; 0 uses schedule mode.")
    parser.add_argument("--factor-candidates", type=int, default=None, help="Factor candidates per mining cycle.")
    parser.add_argument("--factor-generations", type=int, default=None, help="Factor evolution generations.")
    parser.add_argument("--factor-engines", nargs="*", help="Optional factor engines.")
    parser.add_argument("--factor-codes", nargs="*", help="Optional Factor Mining target codes.")
    parser.add_argument(
        "--factor-silent-restart",
        type=int,
        default=0,
        help="Restart Factor Mining after this many seconds without output; 0 disables. Keep disabled for schedule mode.",
    )

    parser.add_argument("--no-incubation", action="store_true", help="Do not start Incubation Factory.")
    parser.add_argument("--incubation-run-time", default="18:30", help="Daily incubation run time, HH:MM.")
    parser.add_argument("--incubation-dry-run", action="store_true", help="Run Incubation Factory daemon in dry-run mode.")
    parser.add_argument("--incubation-verbose", action="store_true", help="Enable verbose Incubation Factory logging.")
    parser.add_argument(
        "--incubation-silent-restart",
        type=int,
        default=0,
        help="Restart Incubation Factory after this many seconds without output; 0 disables. Keep disabled for daemon mode.",
    )
    return parser.parse_args()


def main() -> int:
    _configure_stdio_utf8()
    args = parse_args()
    try:
        return asyncio.run(_run_supervisor(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
