import os
import subprocess
import sys
import textwrap
from pathlib import Path


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"


def _run_isolated_python(code: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PACKAGE_SRC)
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def test_strategy_factory_public_api_imports_without_akshare_mcp(tmp_path):
    code = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class _AkshareBlocker(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "akshare_mcp" or fullname.startswith("akshare_mcp."):
                    raise ModuleNotFoundError(fullname)
                return None

        sys.meta_path.insert(0, _AkshareBlocker())

        import strategy_factory
        import strategy_factory.api as api
        import strategy_factory.api.facade as facade

        for name in strategy_factory.__all__:
            getattr(strategy_factory, name)

        for name in api.__all__:
            getattr(api, name)

        constants = api.get_factory_constants()
        assert constants["LLM_FAN_OUT_COUNT"] >= 1
        assert "strategy_generation" in constants["PIPELINE_STAGE_TIMEOUTS"]
        assert strategy_factory.auto_name("ma_cross", {"short_period": 8, "long_period": 21}) == "均线交叉·快8慢21"
        assert api.StrategyFactoryRepository.__name__ == "StrategyFactoryRepository"
        assert facade.StrategyFactoryScheduler.__name__ == "StrategyFactoryScheduler"
        """
    )
    result = _run_isolated_python(code, cwd=tmp_path)
    assert result.returncode == 0, result.stderr or result.stdout
