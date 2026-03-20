#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_ROOT = SCRIPT_PATH.parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
REPO_ROOT = SCRIPT_PATH.parents[3]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports/tool_registry"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from akshare_mcp.tool_registry import build_tool_registry, summarize_tool_registry


def _render_markdown(summary: dict, rows: list[dict]) -> str:
    lines = [
        "# AKShare MCP Tool Registry",
        "",
        f"- 导出时间: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 工具总数: **{summary['tool_count']}**",
        f"- 使用 unwrap 定位的工具数: **{summary['decorated_tool_count']}**",
        f"- 缺少实现路径的工具数: **{summary['missing_implementation_path_count']}**",
        f"- 缺少 docstring 的工具数: **{summary['missing_docstring_count']}**",
        "",
        "## 分类统计",
        "",
        "| Category | Count |",
        "|----------|-------|",
    ]
    for category, count in summary["category_counts"].items():
        lines.append(f"| `{category}` | {count} |")

    lines.extend(
        [
            "",
            "## Runtime Registry",
            "",
            "| Tool | Category | Async | Wrapper | Implementation | Signature |",
            "|------|----------|-------|---------|----------------|-----------|",
        ]
    )
    for row in rows:
        wrapper = Path(row["wrapper_path"]).name if row.get("wrapper_path") else "-"
        impl = Path(row["implementation_path"]).name if row.get("implementation_path") else "-"
        signature = (row.get("signature") or "").replace("|", "\\|")
        lines.append(
            f"| `{row['name']}` | `{row['category']}` | "
            f"{'yes' if row['is_async'] else 'no'} | `{wrapper}` | `{impl}` | `{signature}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export AKShare MCP runtime tool registry.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = build_tool_registry()
    summary = summarize_tool_registry(rows)
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary": summary,
        "tools": rows,
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"tool_registry_{timestamp}.json"
    md_path = output_dir / f"tool_registry_{timestamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = _render_markdown(summary, rows)

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "tool_count": summary["tool_count"],
                "outputs": {
                    "json": str(json_path),
                    "markdown": str(md_path),
                    "latest_json": str(latest_json),
                    "latest_markdown": str(latest_md),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["missing_implementation_path_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
