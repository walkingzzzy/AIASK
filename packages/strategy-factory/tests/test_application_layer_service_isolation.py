import ast
from pathlib import Path


APPLICATION_DIR = Path(__file__).resolve().parents[1] / "src" / "strategy_factory" / "application"


def test_application_layer_has_no_static_akshare_service_imports():
    violations: list[str] = []
    for path in sorted(APPLICATION_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = str(node.module or "")
                if module.startswith("akshare_mcp.services"):
                    violations.append(f"{path.name}:{node.lineno}:{module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = str(alias.name or "")
                    if module.startswith("akshare_mcp.services"):
                        violations.append(f"{path.name}:{node.lineno}:{module}")
    assert violations == []
