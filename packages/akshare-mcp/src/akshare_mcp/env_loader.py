"""MCP 服务统一 .env 加载器。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional


def get_mcp_env_candidates(explicit_path: Optional[str] = None) -> list[Path]:
    env_from_var = explicit_path or os.getenv('AKSHARE_MCP_ENV', '').strip()
    candidates = [
        Path(__file__).resolve().parent.parent.parent / '.env',
        Path.cwd() / 'packages' / 'akshare-mcp' / '.env',
        Path.cwd() / '.env',
    ]
    if env_from_var:
        candidates.insert(0, Path(env_from_var))
    seen: set[str] = set()
    result: list[Path] = []
    for item in candidates:
        try:
            key = str(item.resolve())
        except Exception:
            key = str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _parse_env_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in str(text or '').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip()
    return values


def load_mcp_env(
    *,
    explicit_path: Optional[str] = None,
    override: bool = False,
    only_keys: Optional[Iterable[str]] = None,
    only_prefixes: Optional[Iterable[str]] = None,
) -> Optional[Path]:
    key_filter = set(str(item).strip() for item in (only_keys or []) if str(item).strip())
    prefix_filter = tuple(str(item).strip() for item in (only_prefixes or []) if str(item).strip())
    for env_path in get_mcp_env_candidates(explicit_path=explicit_path):
        if not env_path.exists() or not env_path.is_file():
            continue
        try:
            content = env_path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        values = _parse_env_lines(content)
        for key, value in values.items():
            if key_filter and key not in key_filter:
                continue
            if prefix_filter and not any(key.startswith(prefix) for prefix in prefix_filter):
                continue
            if override:
                os.environ[key] = value
            else:
                os.environ.setdefault(key, value)
        return env_path
    return None
