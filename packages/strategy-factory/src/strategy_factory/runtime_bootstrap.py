"""Lightweight runtime bootstrap for factory runner scripts.

This module must stay stdlib-only so runner scripts can import it before
numerical/runtime dependencies such as ``numpy`` are available in the current
interpreter.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable, Sequence

DEFAULT_RUNTIME_MODULES: tuple[str, ...] = ("numpy", "pandas")
DEFAULT_EDITABLE_PACKAGES: tuple[str, ...] = (
    "packages/strategy-factory",
    "packages/aiask-quant-core",
    "packages/akshare-mcp",
)

BOOTSTRAP_ENV_KEY = "AIASK_FACTORY_RUNTIME_BOOTSTRAPPED"
BOOTSTRAP_PYTHON_ENV_KEY = "AIASK_FACTORY_RUNTIME_PYTHON"
BOOTSTRAP_UV_ENV_KEY = "AIASK_FACTORY_UV_BIN"


def missing_runtime_modules(module_names: Iterable[str] = DEFAULT_RUNTIME_MODULES) -> list[str]:
    missing: list[str] = []
    for raw_name in module_names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    return missing


def build_uv_reexec_command(
    project_root: Path,
    script_path: Path,
    argv: Sequence[str] | None = None,
    *,
    python_version: str | None = None,
    editable_packages: Sequence[str] = DEFAULT_EDITABLE_PACKAGES,
) -> list[str]:
    del project_root
    version = str(
        python_version
        or os.getenv(BOOTSTRAP_PYTHON_ENV_KEY)
        or "3.12"
    ).strip() or "3.12"
    uv_bin = str(
        os.getenv(BOOTSTRAP_UV_ENV_KEY)
        or shutil.which("uv")
        or "uv"
    ).strip() or "uv"
    command = [uv_bin, "run", "--python", version]
    for raw_package in editable_packages:
        package = str(raw_package or "").strip()
        if package:
            command.extend(["--with-editable", package])
    command.extend(["python", str(Path(script_path).resolve())])
    command.extend(str(arg) for arg in list(argv or ()))
    return command


def ensure_factory_runtime(
    project_root: Path,
    script_path: Path,
    argv: Sequence[str] | None = None,
    *,
    module_names: Sequence[str] = DEFAULT_RUNTIME_MODULES,
    editable_packages: Sequence[str] = DEFAULT_EDITABLE_PACKAGES,
) -> None:
    if str(os.getenv(BOOTSTRAP_ENV_KEY) or "").strip() == "1":
        return
    missing = missing_runtime_modules(module_names)
    if not missing:
        return
    uv_bin = shutil.which(str(os.getenv(BOOTSTRAP_UV_ENV_KEY) or "uv"))
    if not uv_bin:
        sys.stderr.write(
            "AIASK factory runtime bootstrap: missing modules "
            f"{', '.join(missing)} and 'uv' was not found; "
            "continuing with the current interpreter may fail.\n"
        )
        return
    command = build_uv_reexec_command(
        Path(project_root).resolve(),
        Path(script_path).resolve(),
        argv=argv,
        editable_packages=editable_packages,
    )
    env = dict(os.environ)
    env[BOOTSTRAP_ENV_KEY] = "1"
    completed = subprocess.run(
        command,
        cwd=str(Path(project_root).resolve()),
        env=env,
        check=False,
    )
    raise SystemExit(int(completed.returncode))
