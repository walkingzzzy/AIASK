#!/usr/bin/env python3
"""Fail on banned factory-architecture documentation phrases.

This keeps review-spec wording aligned with current code facts:
- default topology is "at most 4" supervised runtimes, not an immutable set
- required bootstrap providers are exactly 19
- lifecycle edge is rejected -> draft only
- hard-gate 20 is a minimum floor, not a frozen immutable constant
- maturity claims need evidence labels
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAN_ROOTS = (
    REPO_ROOT / "docs" / "factory-architecture",
    REPO_ROOT / "docs" / "specs",
)

# Patterns that should not appear as current-state claims in docs.
# Note: the report of banned phrases itself is allowed via allowlist paths.
BANNED_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "immutable-four-processes",
        "Use 'default at most 4 runtimes' instead of claiming actual/immutable 4 processes.",
        re.compile(
            r"(实际拉起\s*4|实际启动四个|实际启动四运行体|实际监督\s*4|必然拉起\s*4|"
            r"(?<!不是[“\"'])(?<!不是[“\"']必然/)(?<!不是[“\"']必然/)实际恒为\s*4|"
            r"(?<![不非])恒为\s*4\s*个)"
        ),
    ),
    (
        "required-providers-20-plus",
        "Canonical required providers are 19; do not claim '20+/20 required providers'.",
        re.compile(
            r"(20\+\s*必需\s*provider|必需\s*provider[s]?\s*20\+|20\+\s*required\s*provider|"
            r"required\s*providers?\s*20\+|20\s*个必需\s*provider|必需\s*20\+?\s*个?\s*provider|"
            r"required providers 20\+|required providers = 20\b)"
        ),
    ),
    (
        "rejected-draft-bidirectional",
        "Lifecycle edge is rejected -> draft only; do not write rejected <-> draft.",
        re.compile(r"rejected\s*(↔|⇄|<->|⇔)\s*draft|draft\s*(↔|⇄|<->|⇔)\s*rejected"),
    ),
    (
        "hard-gate-fixed-immutable-20",
        "production_trade_floor=20 is a minimum floor; do not claim it is immutable/unraisable.",
        re.compile(
            r"(固定不可提高|永远不能提高|不可提高的固定值|不可提高的固定门槛)"
        ),
    ),
    (
        "ungrounded-maturity-claim",
        "Maturity adjectives need tests/runtime/non-empty evidence; avoid bare claims.",
        re.compile(
            r"(已扎实落地|明显缺失|半完成)"
            r"(?![^。\n]{0,80}(证据|测试|运行窗口|非空|工程判断|见\s*§|见 §))"
        ),
    ),
    (
        "evidence-starvation-as-code-fact",
        "Mark 'evidence starvation' style conclusions as engineering judgment, not pure code fact.",
        re.compile(r"(formal\s*=\s*0|formal=0).{0,20}(证据饿死)|证据饿死"),
    ),
)

# Paths that intentionally document the ban list or historical corrections.
ALLOWLIST_PATH_PARTS = (
    "check_factory_doc_banned_phrases.py",
    # The review report intentionally records banned phrases and corrections.
    Path("docs") / "factory-architecture" / "09-深度架构审查报告.md",
)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: Path
    line_no: int
    line: str
    message: str


def _configure_stdio_utf8() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _is_allowlisted(path: Path) -> bool:
    resolved = path.resolve()
    text = str(resolved).replace("\\", "/").lower()
    for item in ALLOWLIST_PATH_PARTS:
        token = str(item).replace("\\", "/").lower()
        if token in text:
            return True
    return False


def _is_negated_claim(line: str, match_start: int) -> bool:
    """Skip phrases that appear only as corrected/forbidden examples."""
    window = line[max(0, match_start - 24) : match_start]
    # e.g. 不是“必然/实际恒为 4...”、“禁止写成...”、“不要写...”
    negative_markers = (
        "不是",
        "而非",
        "禁止",
        "不得",
        "不要",
        "勿",
        "避免",
        "应改为",
        "改为",
        "正确说法",
        "错误写法",
        "禁止写法",
        "do not",
        "instead of",
        "not ",
    )
    return any(marker in window for marker in negative_markers)


def _iter_markdown_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".md":
            files.append(root)
            continue
        files.extend(sorted(root.rglob("*.md")))
    return files


def scan_file(path: Path) -> list[Finding]:
    if _is_allowlisted(path):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule_id, message, pattern in BANNED_RULES:
            for match in pattern.finditer(line):
                if _is_negated_claim(line, match.start()):
                    continue
                findings.append(
                    Finding(
                        rule_id=rule_id,
                        path=path,
                        line_no=line_no,
                        line=line.strip(),
                        message=message,
                    )
                )
                break
    return findings


def main(argv: list[str] | None = None) -> int:
    _configure_stdio_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional files/directories to scan (default: factory-architecture + specs)",
    )
    args = parser.parse_args(argv)
    roots = [path if path.is_absolute() else (REPO_ROOT / path) for path in args.paths]
    if not roots:
        roots = list(DEFAULT_SCAN_ROOTS)

    findings: list[Finding] = []
    for path in _iter_markdown_files(roots):
        findings.extend(scan_file(path))

    if not findings:
        print("factory doc banned-phrase check: OK")
        return 0

    print(f"factory doc banned-phrase check: {len(findings)} finding(s)")
    for item in findings:
        rel = item.path
        try:
            rel = item.path.relative_to(REPO_ROOT)
        except ValueError:
            pass
        print(f"- [{item.rule_id}] {rel}:{item.line_no}: {item.message}")
        print(f"  > {item.line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
