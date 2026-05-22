from __future__ import annotations

import os
import types
import warnings
from pathlib import Path
from typing import Iterable

_CHECK_ENABLED = os.getenv("STRATEGY_FACTORY_FRAGMENT_CHECK", "").strip().lower() in ("1", "true", "yes")


def _parts_dir(module_globals: dict[str, object], parts_dir_name: str) -> Path:
    return Path(str(module_globals["__file__"])).resolve().with_name(parts_dir_name)


def _read_fragment(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _warn_redefinitions(
    module_globals: dict[str, object],
    source: str,
    fragment_path: str,
) -> None:
    """Emit warnings if a fragment redefines existing callables in the namespace."""
    if not _CHECK_ENABLED:
        return
    probe: dict[str, object] = {}
    try:
        exec(compile(source, str(fragment_path), "exec"), probe)
    except Exception:
        return
    for name, value in probe.items():
        if name.startswith("__"):
            continue
        if not isinstance(value, (types.FunctionType, type)):
            continue
        existing = module_globals.get(name)
        if existing is None or not isinstance(existing, (types.FunctionType, type)):
            continue
        existing_file = getattr(
            getattr(existing, "__code__", None), "co_filename", None
        ) or "unknown"
        warnings.warn(
            f"Fragment '{fragment_path}' redefines '{name}' "
            f"(previously defined in '{existing_file}')",
            stacklevel=4,
        )


def exec_fragments(
    module_globals: dict[str, object],
    parts_dir_name: str,
    fragments: Iterable[str],
    *,
    future_annotations: bool = False,
) -> None:
    parts_dir = _parts_dir(module_globals, parts_dir_name)
    for fragment in fragments:
        fragment_path = parts_dir / fragment
        source = _read_fragment(fragment_path)
        if future_annotations and "from __future__ import annotations" not in "\n".join(source.splitlines()[:3]):
            source = "from __future__ import annotations\n" + source
        _warn_redefinitions(module_globals, source, str(fragment_path))
        exec(compile(source, str(fragment_path), "exec"), module_globals)


def exec_block(
    module_globals: dict[str, object],
    parts_dir_name: str,
    header_source: str,
    fragments: Iterable[str],
    *,
    future_annotations: bool = False,
) -> None:
    parts_dir = _parts_dir(module_globals, parts_dir_name)
    body = "".join(_read_fragment(parts_dir / fragment) for fragment in fragments)
    source = header_source.rstrip() + "\n" + body
    if future_annotations:
        source = "from __future__ import annotations\n" + source
    exec(compile(source, f"{module_globals['__file__']}::{parts_dir_name}", "exec"), module_globals)
