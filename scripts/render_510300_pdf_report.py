from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties


ROOT = Path(__file__).resolve().parents[1]
V3_REPORT_ROOT = ROOT / "reports" / "backtests" / "510300_v3"
DEFAULT_OUTPUT_NAME = "formal_report_charted.pdf"
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/53fe5be564086fefc7523ccd0a31200acf92e0e5.asset/AssetData/STHEITI.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def _pick_font() -> FontProperties:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return FontProperties(fname=str(path))
    raise FileNotFoundError("No usable Chinese font file found for PDF rendering.")


FONT = _pick_font()
mpl.rcParams["axes.unicode_minus"] = False
mpl.rcParams["pdf.fonttype"] = 42
mpl.rcParams["ps.fonttype"] = 42


def _pct(value: float) -> str:
    return f"{float(value) * 100:.2f}%"


def _ccy(value: float) -> str:
    return f"{float(value):,.2f}"


def resolve_bundle_dir(bundle_dir: str | Path | None = None) -> Path:
    if bundle_dir:
        candidate = Path(bundle_dir).expanduser().resolve()
    else:
        latest_path = V3_REPORT_ROOT / "latest.json"
        if not latest_path.exists():
            raise FileNotFoundError(f"latest bundle pointer not found: {latest_path}")
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        candidate = Path(latest["artifacts"]["bundle_dir"]).resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"bundle directory not found: {candidate}")
    return candidate


def load_bundle_payload(bundle_dir: Path) -> tuple[dict[str, Any], str, dict[str, pd.DataFrame]]:
    summary = json.loads((bundle_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (bundle_dir / "formal_report.md").read_text(encoding="utf-8")
    csv_dir = bundle_dir / "csv"
    frames: dict[str, pd.DataFrame] = {}
    for csv_path in sorted(csv_dir.glob("*.csv")):
        frame = pd.read_csv(csv_path)
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
        frames[csv_path.stem] = frame
    return summary, markdown, frames


def _add_title(fig: plt.Figure, title: str) -> None:
    fig.text(0.06, 0.95, title, fontproperties=FONT, fontsize=20, fontweight="bold")


def _apply_axis_style(ax: plt.Axes, title: str, ylabel: str | None = None) -> None:
    ax.set_title(title, fontproperties=FONT, fontsize=14, pad=12)
    if ylabel:
        ax.set_ylabel(ylabel, fontproperties=FONT, fontsize=11)
    ax.grid(True, alpha=0.25)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for label in ax.get_xticklabels():
        label.set_fontsize(9)
    for label in ax.get_yticklabels():
        label.set_fontsize(9)


def _render_cover(pdf: PdfPages, summary: dict[str, Any], markdown_text: str) -> None:
    protocol = summary["research_protocol"]
    recommendation = summary["final_recommendation"]
    fig = plt.figure(figsize=(11.69, 8.27))
    _add_title(fig, "510300 研究升级 v3 图表版报告")
    fig.text(
        0.06,
        0.88,
        f"截止日期：{protocol['end_date']}\n"
        f"Walk-forward：{protocol['train_months']}/{protocol['test_months']}/{protocol['step_months']} 月\n"
        f"主场景滑点：{protocol['baseline_slippage_bps']:.1f} bps\n"
        f"压力场景滑点：{protocol['stress_slippage_bps']:.1f} bps",
        fontproperties=FONT,
        fontsize=12,
        va="top",
    )
    fig.text(0.06, 0.66, "最终结论", fontproperties=FONT, fontsize=15, fontweight="bold")
    fig.text(
        0.07,
        0.62,
        f"- 决策枚举：{recommendation['decision']}\n- 摘要：{recommendation['summary']}",
        fontproperties=FONT,
        fontsize=11,
        va="top",
        linespacing=1.6,
    )
    preview_lines = []
    for raw_line in markdown_text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            continue
        if stripped:
            preview_lines.append(stripped)
        if len(preview_lines) >= 6:
            break
    fig.text(0.06, 0.32, "正文摘要", fontproperties=FONT, fontsize=15, fontweight="bold")
    fig.text(
        0.07,
        0.28,
        "\n".join(preview_lines),
        fontproperties=FONT,
        fontsize=10,
        va="top",
        linespacing=1.5,
    )
    fig.text(0.06, 0.05, f"bundle: {summary['artifacts']['bundle_dir']}", fontproperties=FONT, fontsize=9, color="#555555")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _render_cost_table(pdf: PdfPages, summary: dict[str, Any]) -> None:
    rows = []
    for item in summary["cost_scenarios"]:
        metrics = item["strategy_metrics"]
        rows.append(
            [
                item["scenario"],
                f"{item['slippage_bps']:.1f}",
                _pct(metrics["scheme1"]["cagr"]),
                _pct(metrics["scheme2"]["cagr"]),
                _pct(metrics["optimized_regime"]["cagr"]),
                _pct(metrics["scheme1"]["max_drawdown"]),
            ]
        )
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")
    _add_title(fig, "成本场景对比")
    table = ax.table(
        cellText=rows,
        colLabels=["场景", "滑点(bps)", "scheme1 CAGR", "scheme2 CAGR", "optimized CAGR", "scheme1 MDD"],
        colLoc="center",
        cellLoc="center",
        bbox=[0.05, 0.48, 0.90, 0.25],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, _col), cell in table.get_celld().items():
        cell.get_text().set_fontproperties(FONT)
        cell.set_height(0.08 if row else 0.07)
        if row == 0:
            cell.set_facecolor("#dbe8f6")
    fig.text(
        0.06,
        0.30,
        "主结论和推荐均固定读取 main 场景；historical_control 与 stress 仅作单调性和稳健性对照。",
        fontproperties=FONT,
        fontsize=11,
    )
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _render_selection_gate(pdf: PdfPages, summary: dict[str, Any]) -> None:
    rows = []
    for gate in summary["selection_gate"]:
        rows.append(
            [
                gate["family"],
                _pct(gate["oos_cagr"]),
                _pct(gate["benchmark_oos_cagr"]),
                _pct(gate["oos_max_drawdown"]),
                _pct(gate["benchmark_oos_max_drawdown"]),
                "是" if gate["passed"] else "否",
            ]
        )
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")
    _add_title(fig, "样本外门槛与推荐")
    table = ax.table(
        cellText=rows,
        colLabels=["家族", "OOS CAGR", "基准 CAGR", "OOS MDD", "基准 MDD", "通过"],
        colLoc="center",
        cellLoc="center",
        bbox=[0.05, 0.40, 0.90, 0.35],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, _col), cell in table.get_celld().items():
        cell.get_text().set_fontproperties(FONT)
        cell.set_height(0.07 if row == 0 else 0.08)
        if row == 0:
            cell.set_facecolor("#dbe8f6")
    recommendation = summary["final_recommendation"]
    fig.text(
        0.06,
        0.22,
        f"最终推荐：{recommendation['summary']}",
        fontproperties=FONT,
        fontsize=12,
        fontweight="bold",
    )
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _render_equity_curves(pdf: PdfPages, frames: dict[str, pd.DataFrame]) -> None:
    curve_keys = [key for key in frames if key.endswith("_equity_curve")]
    if not curve_keys:
        return
    fig, axes = plt.subplots(2, 1, figsize=(11.69, 8.27), sharex=True)
    _add_title(fig, "主场景净值与资产曲线")
    colors = ["#1f4e79", "#c65d07", "#1b7f3b", "#6c4a9b", "#006d77", "#bc4749"]
    for idx, key in enumerate(curve_keys[:6]):
        frame = frames[key]
        if frame.empty or "date" not in frame or "tw_nav" not in frame:
            continue
        label = key.replace("main_", "").replace("_equity_curve", "")
        color = colors[idx % len(colors)]
        axes[0].plot(frame["date"], frame["tw_nav"], label=label, color=color, linewidth=1.8)
        if "total_asset" in frame:
            axes[1].plot(frame["date"], frame["total_asset"], label=label, color=color, linewidth=1.8)
    _apply_axis_style(axes[0], "时间加权净值", "净值")
    _apply_axis_style(axes[1], "期末总资产", "资产（元）")
    legend = axes[0].legend(frameon=False, loc="upper left", ncol=2)
    for text in legend.get_texts():
        text.set_fontproperties(FONT)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _render_instrument_page(pdf: PdfPages, summary: dict[str, Any]) -> None:
    resolved = summary["instrument_resolution"]["resolved"]
    rows = []
    for key, payload in resolved.items():
        rows.append(
            [
                key,
                payload["code"] or "-",
                payload["name"] or "-",
                str(payload["history_rows"]),
                payload["first_trade_date"] or "-",
                payload["last_trade_date"] or "-",
            ]
        )
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")
    _add_title(fig, "标的解析结果")
    table = ax.table(
        cellText=rows,
        colLabels=["类别", "代码", "名称", "样本行数", "首日", "末日"],
        colLoc="center",
        cellLoc="center",
        bbox=[0.05, 0.42, 0.90, 0.40],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, _col), cell in table.get_celld().items():
        cell.get_text().set_fontproperties(FONT)
        cell.set_height(0.08 if row else 0.07)
        if row == 0:
            cell.set_facecolor("#dbe8f6")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def render_pdf_report(bundle_dir: str | Path | None = None, output_path: str | Path | None = None) -> Path:
    resolved_bundle = resolve_bundle_dir(bundle_dir)
    summary, markdown_text, frames = load_bundle_payload(resolved_bundle)
    final_output = Path(output_path).resolve() if output_path else (resolved_bundle / DEFAULT_OUTPUT_NAME)
    with PdfPages(final_output) as pdf:
        _render_cover(pdf, summary, markdown_text)
        _render_instrument_page(pdf, summary)
        _render_cost_table(pdf, summary)
        _render_selection_gate(pdf, summary)
        _render_equity_curves(pdf, frames)
    return final_output


def main() -> None:
    parser = argparse.ArgumentParser(description="Render charted PDF for 510300 v3 research bundle.")
    parser.add_argument("--bundle-dir", type=str, default=None, help="Bundle directory under reports/backtests/510300_v3/runs/<timestamp>.")
    parser.add_argument("--output", type=str, default=None, help="Optional output PDF path.")
    args = parser.parse_args()
    output_path = render_pdf_report(bundle_dir=args.bundle_dir, output_path=args.output)
    print(output_path)


if __name__ == "__main__":
    main()
