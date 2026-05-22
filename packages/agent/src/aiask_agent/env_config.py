from __future__ import annotations

import os
from pathlib import Path
from typing import Any


_LOADED_ENV_PATH: Path | None = None
_LOADED_ENV_SOURCE = "none"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _disabled() -> bool:
    explicit = str(os.getenv("AIASK_AGENT_LOAD_PROJECT_ENV", "")).strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return True
    return _truthy(os.getenv("AIASK_AGENT_DISABLE_PROJECT_ENV"))


def discover_project_root(start: Path | None = None) -> Path | None:
    starts = [start or Path.cwd(), Path(__file__).resolve()]
    seen: set[str] = set()
    for raw in starts:
        path = raw if raw.is_dir() else raw.parent
        for candidate in (path, *path.parents):
            try:
                key = str(candidate.resolve())
            except OSError:
                key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if (candidate / "AGENT.md").exists() and (candidate / "packages").is_dir():
                return candidate
            if (candidate / ".env").exists() and (candidate / "packages").is_dir() and (candidate / "desktop").is_dir():
                return candidate
    return None


def _dedupe(paths: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path, source in paths:
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append((path.expanduser(), source))
    return result


def project_env_candidates(explicit_path: str | None = None) -> list[tuple[Path, str]]:
    configured_path = explicit_path or os.getenv("AIASK_AGENT_ENV_FILE", "").strip() or os.getenv("AIASK_ENV_FILE", "").strip()
    candidates: list[tuple[Path, str]] = []
    if configured_path:
        candidates.append((Path(configured_path), "explicit"))
    root = discover_project_root()
    if root is not None:
        candidates.append((root / ".env", "project_root"))
    candidates.append((Path.cwd() / ".env", "cwd"))
    return _dedupe(candidates)


def _parse_env_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _dotenv_values(path: Path) -> dict[str, str]:
    try:
        from dotenv import dotenv_values

        parsed = dotenv_values(path)
        return {str(key): str(value) for key, value in parsed.items() if key and value is not None}
    except Exception:
        pass
    try:
        return _parse_env_lines(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}


def load_project_env(
    *,
    explicit_path: str | None = None,
    override: bool = False,
    force: bool = False,
) -> Path | None:
    """Load the project-root .env into os.environ without exposing values."""
    global _LOADED_ENV_PATH, _LOADED_ENV_SOURCE
    if _disabled() and not force and not explicit_path:
        _LOADED_ENV_PATH = None
        _LOADED_ENV_SOURCE = "disabled"
        return None
    for env_path, source in project_env_candidates(explicit_path=explicit_path):
        if not env_path.exists() or not env_path.is_file():
            continue
        values = _dotenv_values(env_path)
        for key, value in values.items():
            if override:
                os.environ[key] = value
            else:
                os.environ.setdefault(key, value)
        _LOADED_ENV_PATH = env_path
        _LOADED_ENV_SOURCE = source
        return env_path
    return None


def project_env_status() -> dict[str, Any]:
    return {
        "loaded": _LOADED_ENV_PATH is not None,
        "path": str(_LOADED_ENV_PATH) if _LOADED_ENV_PATH is not None else None,
        "source": _LOADED_ENV_SOURCE,
        "secrets_redacted": True,
    }
