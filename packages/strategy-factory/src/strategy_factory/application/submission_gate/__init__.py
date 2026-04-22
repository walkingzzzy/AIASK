"""Submission-gate facade package."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from . import runner as _runner

globals().update(
    {
        name: getattr(_runner, name)
        for name in dir(_runner)
        if not name.startswith("__")
    }
)

_legacy_module_path = Path(__file__).resolve().parent.parent / "submission_gate.py"
if _legacy_module_path.exists():
    _legacy_spec = spec_from_file_location(
        "strategy_factory.application._legacy_submission_gate_module",
        _legacy_module_path,
    )
    if _legacy_spec and _legacy_spec.loader:
        _legacy_module = module_from_spec(_legacy_spec)
        _legacy_spec.loader.exec_module(_legacy_module)
        for _name in ("run_submission_quality_gate",):
            if hasattr(_legacy_module, _name):
                globals()[_name] = getattr(_legacy_module, _name)

__all__ = [name for name in globals() if not name.startswith("_")]
