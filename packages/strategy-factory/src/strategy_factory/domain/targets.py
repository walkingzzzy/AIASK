"""策略工厂状态与目标池工具。"""

from __future__ import annotations

from typing import Any, List, Optional

from .constants import REPRESENTATIVE_STOCKS


async def _update_strategy_status(db, strategy_id: str, status: str, **kwargs) -> None:
    try:
        await db.update_strategy_status(strategy_id, status, **kwargs)
    except TypeError:
        await db.update_strategy_status(strategy_id, status)


def _normalize_target_codes(values: Any, limit: int = 12) -> List[str]:
    codes: List[str] = []
    seen: set[str] = set()

    def visit(value: Any):
        if value is None:
            return
        if isinstance(value, dict):
            for key in ("code", "symbol", "stock_code"):
                if value.get(key) is not None:
                    visit(value.get(key))
            for key in ("codes", "symbols", "stock_codes", "target_symbols"):
                if value.get(key) is not None:
                    visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        raw = str(value or "").strip()
        if not raw:
            return
        if any(sep in raw for sep in [",", ";", "|", "\n", "\t", " "]):
            normalized = raw.replace(";", ",").replace("|", ",").replace("\n", ",").replace("\t", ",").replace(" ", ",")
            for part in normalized.split(","):
                visit(part)
            return
        code = raw.split(".")[0].strip()
        if not code or code in seen:
            return
        seen.add(code)
        codes.append(code)

    visit(values)
    return codes[: max(1, min(int(limit or 12), 40))]


def _extract_target_codes_from_payload(payload: Optional[dict], limit: int = 12) -> List[str]:
    item = dict(payload or {})
    params = dict(item.get("params") or {})
    dsl = dict(params.get("dsl") or {})
    dsl_metadata = dict(dsl.get("metadata") or {})
    generation_reason = dict(item.get("generation_reason") or {})
    return _normalize_target_codes([
        item.get("target_symbols"),
        item.get("stock_pool"),
        params.get("target_symbols"),
        params.get("stock_pool"),
        dsl_metadata.get("target_symbols"),
        dsl_metadata.get("stock_pool"),
        generation_reason.get("target_symbols"),
        generation_reason.get("stock_pool"),
    ], limit=limit)


def _resolve_strategy_sample_codes(strategy_type: str, params: dict, sample_size: int = 6) -> List[str]:
    target_codes = _extract_target_codes_from_payload(
        {"strategy_type": strategy_type, "params": params},
        limit=max(sample_size, 12),
    )
    combined = list(dict.fromkeys([*target_codes, *REPRESENTATIVE_STOCKS]))
    return combined[: max(sample_size, min(len(combined), max(sample_size, len(target_codes))))]
