"""根目录 MD 归类脚本

执行步骤:
1. 创建 docs/diagnostics/ + docs/diagnostics/mcp/ + docs/diagnostics/mcp/regression-2026-05-26/ 子目录
2. Move 11 个根目录 MD 到目标位置(AGENT.md 保留;删除根目录旧版 05-08)
3. 在新位置更新所有跨文件引用(相对路径修正)
4. 同步更新 docs/README.md / RFC 文件 / 2 个 pytest 文件 / docs 副本 05-08 / docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md 内自身互引用

执行前 DRY_RUN=True 仅打印计划; 设 False 才落地。
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Iterable

DRY_RUN = False
REPO = Path(r"c:\Users\walking\Desktop\aiask")

# ----------------------------------------------------------------------------
# 1. 移动计划 (源 -> 目标)
# ----------------------------------------------------------------------------
MOVES = [
    # 事件驱动当前生效方案 -> docs/event-driven/
    (
        "事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
        "docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
    ),
    # 5 篇 MCP 主诊断 + Phase 修复 -> docs/diagnostics/mcp/
    (
        "MCP服务诊断报告-2026-05-24.md",
        "docs/diagnostics/mcp/MCP服务诊断报告-2026-05-24.md",
    ),
    (
        "MCP服务诊断报告-修复执行清单-2026-05-24.md",
        "docs/diagnostics/mcp/MCP服务诊断报告-修复执行清单-2026-05-24.md",
    ),
    (
        "MCP服务诊断报告-修复执行清单-Phase2-2026-05-24.md",
        "docs/diagnostics/mcp/MCP服务诊断报告-修复执行清单-Phase2-2026-05-24.md",
    ),
    (
        "MCP服务诊断报告-修复执行清单-Phase3-2026-05-24.md",
        "docs/diagnostics/mcp/MCP服务诊断报告-修复执行清单-Phase3-2026-05-24.md",
    ),
    (
        "MCP服务诊断报告-最终核对清单-2026-05-26.md",
        "docs/diagnostics/mcp/MCP服务诊断报告-最终核对清单-2026-05-26.md",
    ),
    # 3 篇对话式复测 -> docs/diagnostics/mcp/regression-2026-05-26/
    (
        "MCP服务对话式复测报告-2026-05-26.md",
        "docs/diagnostics/mcp/regression-2026-05-26/MCP服务对话式复测报告-2026-05-26.md",
    ),
    (
        "MCP服务对话式复测-B1-B8修复报告-2026-05-26.md",
        "docs/diagnostics/mcp/regression-2026-05-26/MCP服务对话式复测-B1-B8修复报告-2026-05-26.md",
    ),
    (
        "MCP服务对话式复测-B1-B8修复验证最终报告-2026-05-26.md",
        "docs/diagnostics/mcp/regression-2026-05-26/MCP服务对话式复测-B1-B8修复验证最终报告-2026-05-26.md",
    ),
    # TDX 测试报告 -> docs/data/
    (
        "TDX数据源测试报告-2026-05-25.md",
        "docs/data/TDX数据源测试报告-2026-05-25.md",
    ),
]

# 删除根目录的旧版 05-08(docs/event-driven 下已有更新的 v4 版本)
DELETIONS = [
    "事件驱动主题联动-策略工厂升级方案-2026-05-08.md",
]

# ----------------------------------------------------------------------------
# 2. 跨文件引用更新计划
#    (target_file_after_move, [(old_text, new_text), ...])
#    target_file_after_move 是相对 REPO 的路径
# ----------------------------------------------------------------------------
EDITS: list[tuple[str, list[tuple[str, str]]]] = []

# --- 2.1 docs/README.md ---
# 旧: ../../事件驱动主题联动-结合当前代码升级方案-2026-05-24.md
# 新: 同 docs 下 -> event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md
# 旧: event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md
# 新: 同前(没移动)
EDITS.append(
    (
        "docs/README.md",
        [
            (
                "[../../事件驱动主题联动-结合当前代码升级方案-2026-05-24.md](../../事件驱动主题联动-结合当前代码升级方案-2026-05-24.md)",
                "[event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md](event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md)",
            ),
        ],
    )
)

# --- 2.2 docs/event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md ---
# 已用 ../../ 前缀指向根目录的 05-24 文件; 移动后新位置在 docs/event-driven/, 同目录, 改为同目录引用
EDITS.append(
    (
        "docs/event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md",
        [
            (
                "[`事件驱动主题联动-结合当前代码升级方案-2026-05-24.md`](../../事件驱动主题联动-结合当前代码升级方案-2026-05-24.md)",
                "[`事件驱动主题联动-结合当前代码升级方案-2026-05-24.md`](事件驱动主题联动-结合当前代码升级方案-2026-05-24.md)",
            ),
        ],
    )
)

# --- 2.3 docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md (移动后) ---
# 内部引用 docs/event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md
# 移到 docs/event-driven/ 后, 应改为同目录相对路径
EDITS.append(
    (
        "docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md",
        [
            (
                "`docs/event-driven/事件驱动主题联动-策略工厂升级方案-2026-05-08.md`",
                "`事件驱动主题联动-策略工厂升级方案-2026-05-08.md`",
            ),
        ],
    )
)

# --- 2.4 MCP服务诊断报告-最终核对清单-2026-05-26.md (移动后) ---
# 内部引用 TDX数据源测试报告-2026-05-25.md (同原根目录), 移动后:
#   核对清单 -> docs/diagnostics/mcp/
#   TDX 报告 -> docs/data/
# 跨目录: ../../data/TDX数据源测试报告-2026-05-25.md
EDITS.append(
    (
        "docs/diagnostics/mcp/MCP服务诊断报告-最终核对清单-2026-05-26.md",
        [
            (
                "`TDX数据源测试报告-2026-05-25.md`",
                "[../../data/TDX数据源测试报告-2026-05-25.md](../../data/TDX数据源测试报告-2026-05-25.md)",
            ),
        ],
    )
)

# --- 2.5 docs/plans/RFC-001..004 各引用 MCP服务诊断报告-2026-05-24.md ---
# 移动到 docs/diagnostics/mcp/ 后, RFC 在 docs/plans/, 跨目录:
#   ../diagnostics/mcp/MCP服务诊断报告-2026-05-24.md
RFC_EDIT = [
    (
        "`MCP服务诊断报告-2026-05-24.md`",
        "[`docs/diagnostics/mcp/MCP服务诊断报告-2026-05-24.md`](../diagnostics/mcp/MCP服务诊断报告-2026-05-24.md)",
    ),
]
for rfc in [
    "docs/plans/RFC-001-quant-naming-unification.md",
    "docs/plans/RFC-002-rsi-algorithm-unification.md",
    "docs/plans/RFC-003-user-id-mandatory-managers.md",
    "docs/plans/RFC-004-marketcap-unit-unification.md",
]:
    EDITS.append((rfc, list(RFC_EDIT)))

# --- 2.6 两个 pytest 文件: 引用文件名(无路径), 文件名不变, 加注路径 ---
# test_theme_graph_schema.py: ``事件驱动主题联动-结合当前代码升级方案-2026-05-24.md``
# 改为 ``docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md``
PYTEST_EDIT = [
    (
        "``事件驱动主题联动-结合当前代码升级方案-2026-05-24.md``",
        "``docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md``",
    ),
    (
        "事件驱动主题联动-结合当前代码升级方案-2026-05-24.md §",
        "docs/event-driven/事件驱动主题联动-结合当前代码升级方案-2026-05-24.md §",
    ),
]
EDITS.append(
    (
        "packages/akshare-mcp/tests/test_theme_graph_schema.py",
        list(PYTEST_EDIT),
    )
)
EDITS.append(
    (
        "packages/strategy-factory/tests/test_package_decoupling_boundary.py",
        list(PYTEST_EDIT),
    )
)


# ----------------------------------------------------------------------------
# 3. 实施
# ----------------------------------------------------------------------------
def log(msg: str) -> None:
    print(msg, flush=True)


def step1_create_dirs() -> None:
    targets = {Path(MOVES[i][1]).parent for i in range(len(MOVES))}
    for t in sorted(targets, key=lambda p: str(p)):
        full = REPO / t
        if full.exists():
            log(f"[SKIP-DIR-EXISTS] {t}")
        else:
            log(f"[MKDIR] {t}")
            if not DRY_RUN:
                full.mkdir(parents=True, exist_ok=True)


def step2_move() -> None:
    for src, dst in MOVES:
        sp = REPO / src
        dp = REPO / dst
        if not sp.exists():
            log(f"[ERR] missing source: {src}")
            continue
        if dp.exists():
            log(f"[ERR] dest exists, will OVERWRITE: {dst}")
            if not DRY_RUN:
                dp.unlink()
        log(f"[MOVE] {src} -> {dst}")
        if not DRY_RUN:
            shutil.move(str(sp), str(dp))


def step3_delete() -> None:
    for f in DELETIONS:
        p = REPO / f
        if not p.exists():
            log(f"[SKIP-DEL-MISSING] {f}")
            continue
        log(f"[DELETE] {f}")
        if not DRY_RUN:
            p.unlink()


def step4_edits() -> None:
    for target, replaces in EDITS:
        path = REPO / target
        # DRY_RUN 时, 如果目标是 step2 之后才存在的位置, 退化检查源
        if not path.exists() and DRY_RUN:
            # 反查 MOVES 找它的源
            src_for_target = None
            for src, dst in MOVES:
                if dst == target:
                    src_for_target = src
                    break
            if src_for_target is not None:
                fallback = REPO / src_for_target
                if fallback.exists():
                    log(f"[EDIT-PREVIEW-USING-SOURCE] {target} (preview against {src_for_target})")
                    path = fallback
        if not path.exists():
            log(f"[ERR-EDIT] missing: {target}")
            continue
        text = path.read_text(encoding="utf-8")
        original = text
        applied = []
        not_found = []
        for old, new in replaces:
            if old in text:
                text = text.replace(old, new)
                applied.append(old[:60] + "...")
            else:
                not_found.append(old[:60] + "...")
        if text != original:
            log(f"[EDIT] {target} ({len(applied)} replaced, {len(not_found)} not-found)")
            for nf in not_found:
                log(f"       NOT FOUND: {nf}")
            if not DRY_RUN:
                # write back to actual path (after move)
                actual = REPO / target
                actual.write_text(text, encoding="utf-8")
        else:
            log(f"[NO-CHANGE] {target} ({len(not_found)} expected patterns not found)")
            for nf in not_found:
                log(f"       NOT FOUND: {nf}")


def main() -> int:
    log(f"DRY_RUN = {DRY_RUN}")
    log(f"REPO = {REPO}")
    log("")
    log("STEP 1: create dirs")
    log("-" * 78)
    step1_create_dirs()
    log("")
    log("STEP 2: move files")
    log("-" * 78)
    step2_move()
    log("")
    log("STEP 3: delete obsolete duplicates")
    log("-" * 78)
    step3_delete()
    log("")
    log("STEP 4: update cross-references")
    log("-" * 78)
    step4_edits()
    log("")
    log("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
