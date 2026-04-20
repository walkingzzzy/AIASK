"""Build an AI-ready knowledge pack from mixed local research materials.

The script scans a source directory, extracts text/OCR/table data from common
research formats, converts narrative materials into Markdown, exports tables to
CSV, groups artifacts by content dimension, and writes retrieval-oriented
metadata compatible with the project's market document / chunk conventions.
"""

from pathlib import Path
from typing import Iterable


def _exec_fragments(module_globals: dict[str, object], parts_dir_name: str, fragments: Iterable[str], *, future_annotations: bool = False) -> None:
    parts_dir = Path(str(module_globals["__file__"])).resolve().with_name(parts_dir_name)
    for fragment in fragments:
        fragment_path = parts_dir / fragment
        source = fragment_path.read_text(encoding="utf-8")
        if future_annotations and "from __future__ import annotations" not in "\n".join(source.splitlines()[:3]):
            source = "from __future__ import annotations\n" + source
        exec(compile(source, str(fragment_path), "exec"), module_globals)


_exec_fragments(globals(), 'build_ai_ready_knowledge_pack_parts', ['config.py', 'discovery.py', 'packaging.py'], future_annotations=True)

