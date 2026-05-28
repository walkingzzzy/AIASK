"""临时脚本: 比对根目录 12 个 MD 文件 + 检查 docs/event-driven 重复, 输出 audit 报告
归并根目录 MD 整理工作完成后将删除本脚本。
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

REPO = Path(r"c:\Users\walking\Desktop\aiask")

ROOT_MDS = [
    "AGENT.md",
    "MCP服务对话式复测-B1-B8修复报告-2026-05-26.md",
    "MCP服务对话式复测-B1-B8修复验证最终报告-2026-05-26.md",
    "MCP服务对话式复测报告-2026-05-26.md",
    "MCP服务诊断报告-2026-05-24.md",
    "MCP服务诊断报告-修复执行清单-2026-05-24.md",
    "MCP服务诊断报告-修复执行清单-Phase2-2026-05-24.md",
    "MCP服务诊断报告-修复执行清单-Phase3-2026-05-24.md",
    "MCP服务诊断报告-最终核对清单-2026-05-26.md",
    "TDX数据源测试报告-2026-05-25.md",
    "事件驱动主题联动-策略工厂升级方案-2026-05-08.md",
    "事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    print("=" * 78)
    print("ROOT MD AUDIT")
    print("=" * 78)
    for name in ROOT_MDS:
        p = REPO / name
        if not p.exists():
            print(f"[MISSING] {name}")
            continue
        print(f"  {p.stat().st_size:>8} bytes  {name}")

    print()
    print("=" * 78)
    print("DUPLICATE CHECK: 事件驱动主题联动-策略工厂升级方案-2026-05-08.md")
    print("=" * 78)
    root_v = REPO / "事件驱动主题联动-策略工厂升级方案-2026-05-08.md"
    docs_v = REPO / "docs" / "event-driven" / "事件驱动主题联动-策略工厂升级方案-2026-05-08.md"
    if root_v.exists() and docs_v.exists():
        rh = sha(root_v)
        dh = sha(docs_v)
        print(f"  ROOT  size={root_v.stat().st_size}  sha256={rh[:16]}...")
        print(f"  DOCS  size={docs_v.stat().st_size}  sha256={dh[:16]}...")
        print("  RESULT:", "IDENTICAL" if rh == dh else "DIFFERENT")
    else:
        print(f"  root exists={root_v.exists()}")
        print(f"  docs exists={docs_v.exists()}")

    print()
    print("=" * 78)
    print("CHECK: docs/event-driven 现状")
    print("=" * 78)
    ev = REPO / "docs" / "event-driven"
    for p in sorted(ev.iterdir()):
        print(f"  {p.stat().st_size:>8} bytes  {p.name}")

    print()
    print("=" * 78)
    print("CHECK: docs/data 现状")
    print("=" * 78)
    dt = REPO / "docs" / "data"
    for p in sorted(dt.iterdir()):
        print(f"  {p.stat().st_size:>8} bytes  {p.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
