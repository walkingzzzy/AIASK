from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
for package_src in (
    REPO_ROOT / "packages" / "strategy-factory" / "src",
    REPO_ROOT / "packages" / "akshare-mcp" / "src",
):
    if str(package_src) not in sys.path:
        sys.path.insert(0, str(package_src))


from akshare_mcp.services.research_510300_v3 import (  # noqa: E402
    ResearchProtocol,
    finalize_bundle_outputs,
    run_510300_research_v3,
)


def _load_renderer():
    renderer_path = REPO_ROOT / "scripts" / "render_510300_pdf_report.py"
    spec = importlib.util.spec_from_file_location("render_510300_pdf_report", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load renderer from {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 510300 v3 research pipeline and emit versioned bundle outputs.")
    parser.add_argument("--end-date", default="2026-04-10")
    parser.add_argument("--baseline-slippage-bps", type=float, default=5.0)
    parser.add_argument("--stress-slippage-bps", type=float, default=10.0)
    parser.add_argument("--train-months", type=int, default=60)
    parser.add_argument("--test-months", type=int, default=12)
    parser.add_argument("--step-months", type=int, default=12)
    parser.add_argument("--enable-cash-sleeves", action="store_true")
    parser.add_argument("--enable-enhancements", action="store_true")
    parser.add_argument("--timestamp", default=None, help="Optional bundle run id override, e.g. 20260414T120000Z")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    protocol = ResearchProtocol(
        end_date=args.end_date,
        baseline_slippage_bps=float(args.baseline_slippage_bps),
        stress_slippage_bps=float(args.stress_slippage_bps),
        train_months=int(args.train_months),
        test_months=int(args.test_months),
        step_months=int(args.step_months),
        enable_cash_sleeves=bool(args.enable_cash_sleeves),
        enable_enhancements=bool(args.enable_enhancements),
    )
    bundle = run_510300_research_v3(protocol, timestamp=args.timestamp)
    renderer = _load_renderer()
    pdf_path = renderer.render_pdf_report(bundle_dir=bundle.bundle_dir)
    promotion = finalize_bundle_outputs(bundle.bundle_dir, pdf_path)
    payload = {
        "bundle_dir": str(bundle.bundle_dir),
        "summary_path": str(bundle.summary_path),
        "markdown_path": str(bundle.markdown_path),
        "pdf_path": str(pdf_path),
        "promotion": promotion,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
