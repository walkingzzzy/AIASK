import ast
from pathlib import Path


APPLICATION_DIR = Path(__file__).resolve().parents[1] / "src" / "strategy_factory" / "application"


def test_application_layer_has_no_static_akshare_imports():
    violations: list[str] = []
    for path in sorted(APPLICATION_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = str(node.module or "")
                if module == "akshare_mcp" or module.startswith("akshare_mcp."):
                    violations.append(f"{path.name}:{node.lineno}:{module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = str(alias.name or "")
                    if module == "akshare_mcp" or module.startswith("akshare_mcp."):
                        violations.append(f"{path.name}:{node.lineno}:{module}")
    assert violations == []


def test_application_layer_has_no_dynamic_akshare_imports():
    violations: list[str] = []
    for path in sorted(APPLICATION_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            is_import_module = isinstance(func, ast.Name) and func.id == "import_module"
            is_importlib_import_module = (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
                and isinstance(func.value, ast.Name)
                and func.value.id == "importlib"
            )
            if not (is_import_module or is_importlib_import_module):
                continue
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                module = first_arg.value
                if module == "akshare_mcp" or module.startswith("akshare_mcp."):
                    violations.append(f"{path.name}:{node.lineno}:{module}")
    assert violations == []
