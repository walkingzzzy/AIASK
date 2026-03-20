import os
import subprocess
import sys
from pathlib import Path

from akshare_mcp.tool_registry import build_tool_registry


def test_tool_description_audit_should_use_runtime_tool_count(tmp_path):
    package_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "TOOL_DESCRIPTION_IMPROVEMENT_PLAN.md"
    env = os.environ.copy()

    proc = subprocess.run(
        [sys.executable, "scripts/generate_tool_description_audit.py", "--output", str(output_path)],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    markdown = output_path.read_text(encoding="utf-8")
    runtime_count = len(build_tool_registry())
    assert f"{runtime_count} 工具逐条矩阵" in markdown
    assert f"工具总数：**{runtime_count}**" in markdown
