from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "packages" / "akshare-mcp" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from akshare_mcp.tools.managers import insight_manager as im  # type: ignore


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def _build_payload_for_date(report_date: str, old_payload: dict) -> dict:
    kwargs = {
        "report_type": "daily",
        "report_date": report_date,
        "owner": old_payload.get("owner", "default"),
        "data_window": old_payload.get("data_window", "T-20D ~ T"),
    }
    # 保留调用方传入的持仓信息（如存在）
    if isinstance(old_payload.get("holdings"), list):
        kwargs["holdings"] = old_payload["holdings"]
    if isinstance(old_payload.get("codes"), list):
        kwargs["codes"] = old_payload["codes"]

    kwargs = await im._enrich_daily_kwargs(kwargs)
    payload = im._build_payload("daily", kwargs)
    return payload


async def main() -> None:
    reports_dir = ROOT / "reports"
    json_files = sorted(reports_dir.glob("daily_report_*.json"))
    updated = 0

    for jf in json_files:
        old_payload = _load_json(jf)
        report_date = str(old_payload.get("report_date") or "").strip() or "2026-02-16"

        payload = await _build_payload_for_date(report_date, old_payload)

        # 直接覆盖同名 JSON/MD，保持成对一致
        md_path = jf.with_suffix(".md")
        tpl = im._template_path("daily").read_text(encoding="utf-8")
        markdown = im._render_template(tpl, payload)

        jf.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        updated += 1

    print(json.dumps({"updated_reports": updated, "dir": str(reports_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

