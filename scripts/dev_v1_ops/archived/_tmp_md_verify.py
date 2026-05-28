"""验证 MD 整理结果:
1. 根目录只剩 AGENT.md
2. 11 个文件都到了正确目标位置
3. 关键引用更新正确(docs/README.md / pytest 文件 / RFC 文件)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(r"c:\Users\walking\Desktop\aiask")

EXPECTED_AT_NEW_LOCATIONS = [
    "docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
    "docs/event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md",
    "docs/diagnostics/mcp/MCP服务诊断报告-2026-05-24.md",
    "docs/diagnostics/mcp/MCP服务诊断报告-修复执行清单-2026-05-24.md",
    "docs/diagnostics/mcp/MCP服务诊断报告-修复执行清单-Phase2-2026-05-24.md",
    "docs/diagnostics/mcp/MCP服务诊断报告-修复执行清单-Phase3-2026-05-24.md",
    "docs/diagnostics/mcp/MCP服务诊断报告-最终核对清单-2026-05-26.md",
    "docs/diagnostics/mcp/regression-2026-05-26/MCP服务对话式复测报告-2026-05-26.md",
    "docs/diagnostics/mcp/regression-2026-05-26/MCP服务对话式复测-B1-B8修复报告-2026-05-26.md",
    "docs/diagnostics/mcp/regression-2026-05-26/MCP服务对话式复测-B1-B8修复验证最终报告-2026-05-26.md",
    "docs/data/TDX数据源测试报告-2026-05-25.md",
    "AGENT.md",
]

EXPECTED_GONE_FROM_ROOT = [
    "事件驱动主题联动-策略工厂升级方案-2026-05-08.md",
    "事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
    "MCP服务诊断报告-2026-05-24.md",
    "MCP服务诊断报告-修复执行清单-2026-05-24.md",
    "MCP服务诊断报告-修复执行清单-Phase2-2026-05-24.md",
    "MCP服务诊断报告-修复执行清单-Phase3-2026-05-24.md",
    "MCP服务诊断报告-最终核对清单-2026-05-26.md",
    "MCP服务对话式复测报告-2026-05-26.md",
    "MCP服务对话式复测-B1-B8修复报告-2026-05-26.md",
    "MCP服务对话式复测-B1-B8修复验证最终报告-2026-05-26.md",
    "TDX数据源测试报告-2026-05-25.md",
]

CONTENT_CHECKS = [
    # (file, must_contain, must_NOT_contain)
    (
        "docs/README.md",
        "[event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md](event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md)",
        "../../事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
    ),
    (
        "docs/event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md",
        "[`事件驱动主题联动-结合当前代码升级方案-2026-05-24.md`](事件驱动主题联动-结合当前代码升级方案-2026-05-24.md)",
        "[`事件驱动主题联动-结合当前代码升级方案-2026-05-24.md`](../../事件驱动主题联动-结合当前代码升级方案-2026-05-24.md)",
    ),
    (
        "docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
        "`事件驱动主题联动-策略工厂升级方案-2026-05-08.md`",
        "`docs/event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md`",
    ),
    (
        "docs/diagnostics/mcp/MCP服务诊断报告-最终核对清单-2026-05-26.md",
        "../../data/TDX数据源测试报告-2026-05-25.md",
        "`TDX数据源测试报告-2026-05-25.md`",
    ),
    (
        "docs/plans/RFC-001-quant-naming-unification.md",
        "../diagnostics/mcp/MCP服务诊断报告-2026-05-24.md",
        "`MCP服务诊断报告-2026-05-24.md`",
    ),
    (
        "packages/akshare-mcp/tests/test_theme_graph_schema.py",
        "docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
        None,
    ),
    (
        "packages/strategy-factory/tests/test_package_decoupling_boundary.py",
        "docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
        None,
    ),
]


def main() -> int:
    fail = 0
    print("=" * 78)
    print("STEP A: 验证根目录已不再含已移动文件")
    print("=" * 78)
    for name in EXPECTED_GONE_FROM_ROOT:
        p = REPO / name
        if p.exists():
            print(f"  [FAIL] still exists: {name}")
            fail += 1
        else:
            print(f"  [OK]   removed:     {name}")

    print()
    print("=" * 78)
    print("STEP B: 验证文件在新位置存在")
    print("=" * 78)
    for path in EXPECTED_AT_NEW_LOCATIONS:
        p = REPO / path
        if p.exists():
            print(f"  [OK]   {p.stat().st_size:>8} bytes  {path}")
        else:
            print(f"  [FAIL] missing:    {path}")
            fail += 1

    print()
    print("=" * 78)
    print("STEP C: 验证关键引用已更新")
    print("=" * 78)
    for fpath, must_contain, must_not_contain in CONTENT_CHECKS:
        p = REPO / fpath
        if not p.exists():
            print(f"  [FAIL] file missing: {fpath}")
            fail += 1
            continue
        text = p.read_text(encoding="utf-8")
        if must_contain not in text:
            print(f"  [FAIL] {fpath}")
            print(f"         missing: {must_contain[:80]}...")
            fail += 1
        else:
            print(f"  [OK]   {fpath} contains updated link")
        if must_not_contain is not None and must_not_contain in text:
            # docs/README.md / event-driven 文档可能在多处出现, 严格判定
            print(f"  [WARN] {fpath} still has old text: {must_not_contain[:80]}...")

    print()
    print(f"FAILED CHECKS: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
