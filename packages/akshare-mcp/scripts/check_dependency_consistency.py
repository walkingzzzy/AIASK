#!/usr/bin/env python3
"""依赖一致性检查脚本。

用途：校验 requirements.txt 是否与 pyproject.toml 的 [project.dependencies] 一致。
返回码：
- 0: 一致
- 1: 不一致/读取失败
"""

from __future__ import annotations

from pathlib import Path
import sys

try:
    import tomllib  # py>=3.11
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"


def _normalize(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        normalized.append(item)
    return normalized


def load_pyproject_deps() -> list[str]:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    if not isinstance(deps, list):
        raise ValueError("pyproject.toml: [project.dependencies] 不是数组")
    return _normalize([str(d) for d in deps])


def load_requirements_deps() -> list[str]:
    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    return _normalize(lines)


def main() -> int:
    try:
        pyproject_deps = load_pyproject_deps()
        requirements_deps = load_requirements_deps()
    except Exception as exc:
        print(f"[ERROR] 读取依赖失败: {exc}")
        return 1

    pset = set(pyproject_deps)
    rset = set(requirements_deps)

    missing_in_requirements = sorted(pset - rset)
    extra_in_requirements = sorted(rset - pset)

    if not missing_in_requirements and not extra_in_requirements:
        print("[OK] requirements.txt 与 pyproject.toml 依赖一致")
        return 0

    print("[FAIL] 依赖不一致")
    if missing_in_requirements:
        print("- requirements.txt 缺失依赖:")
        for dep in missing_in_requirements:
            print(f"  - {dep}")

    if extra_in_requirements:
        print("- requirements.txt 存在额外依赖:")
        for dep in extra_in_requirements:
            print(f"  - {dep}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

