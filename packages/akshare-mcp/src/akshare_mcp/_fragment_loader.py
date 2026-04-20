from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _parts_dir(module_globals: dict[str, object], parts_dir_name: str) -> Path:
    return Path(str(module_globals["__file__"])).resolve().with_name(parts_dir_name)


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
        source = fragment_path.read_text(encoding="utf-8")
        if future_annotations and "from __future__ import annotations" not in "\n".join(source.splitlines()[:3]):
            source = "from __future__ import annotations\n" + source
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
    body = "".join((parts_dir / fragment).read_text(encoding="utf-8") for fragment in fragments)
    source = header_source.rstrip() + "\n" + body
    if future_annotations:
        source = "from __future__ import annotations\n" + source
    exec(compile(source, f"{module_globals['__file__']}::{parts_dir_name}", "exec"), module_globals)
