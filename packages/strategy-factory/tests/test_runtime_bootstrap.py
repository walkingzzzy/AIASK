from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]


def test_missing_runtime_modules_reports_unavailable_specs(monkeypatch):
    from strategy_factory import runtime_bootstrap as rb

    monkeypatch.setattr(
        rb.importlib.util,
        "find_spec",
        lambda name: None if name == "numpy" else object(),
    )

    assert rb.missing_runtime_modules(("numpy", "pandas")) == ["numpy"]


def test_build_uv_reexec_command_includes_editable_packages(monkeypatch):
    from strategy_factory import runtime_bootstrap as rb

    monkeypatch.setenv(rb.BOOTSTRAP_PYTHON_ENV_KEY, "3.12")
    monkeypatch.setenv(rb.BOOTSTRAP_UV_ENV_KEY, "uv")

    command = rb.build_uv_reexec_command(
        project_root=Path("C:/repo"),
        script_path=Path("C:/repo/run_strategy_factory.py"),
        argv=["--once", "--codes", "601288"],
    )

    assert command[:4] == ["uv", "run", "--python", "3.12"]
    assert "--with-editable" in command
    assert "packages/strategy-factory" in command
    assert command[-5:] == [
        "python",
        str(Path("C:/repo/run_strategy_factory.py").resolve()),
        "--once",
        "--codes",
        "601288",
    ]


def test_ensure_factory_runtime_reexecs_with_uv_when_modules_missing(monkeypatch):
    from strategy_factory import runtime_bootstrap as rb

    monkeypatch.setattr(rb, "missing_runtime_modules", lambda module_names=None: ["numpy"])
    monkeypatch.setattr(rb.shutil, "which", lambda name: "uv" if name == "uv" else None)

    captured: dict[str, object] = {}

    def _fake_run(command, *, cwd, env, check):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        captured["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(rb.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit) as exc:
        rb.ensure_factory_runtime(
            project_root=Path("C:/repo"),
            script_path=Path("C:/repo/run_strategy_factory.py"),
            argv=["--once"],
        )

    assert exc.value.code == 0
    assert captured["cwd"] == str(Path("C:/repo").resolve())
    assert captured["env"][rb.BOOTSTRAP_ENV_KEY] == "1"
    assert captured["command"][:4] == ["uv", "run", "--python", "3.12"]


def test_signal_tracker_launchers_preflight_runtime_before_akshare_imports():
    launchers = [
        ROOT / "scripts" / "factories" / "run_signal_tracker.py",
        ROOT / "packages" / "akshare-mcp" / "scripts" / "run_signal_tracker.py",
    ]

    for path in launchers:
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "from strategy_factory.runtime_bootstrap import ensure_factory_runtime" in text
        assert "ensure_factory_runtime(" in text
        assert text.index("ensure_factory_runtime(") < text.index("from akshare_mcp")
