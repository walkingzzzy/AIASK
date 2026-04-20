"""TimescaleDB 策略超市 Mixin — 孵化账户 / 孵化指标 / 模拟交易"""


import json
import logging
from datetime import date, datetime
from typing import Any, List, Optional

from ...services.trade_audit_writer import aggregate_trade_position

logger = logging.getLogger(__name__)

_EXECUTION_AUDIT_REQUIRED_TABLES = (
    "strategy_candidate_evidence",
    "strategy_signal_evidence",
    "strategy_trade_positions",
    "strategy_trade_position_fills",
)
_EXECUTION_AUDIT_REQUIRED_COLUMNS = {
    "paper_orders": ("signal_id", "position_id"),
    "paper_trades": ("signal_id", "position_id"),
}
_EXECUTION_AUDIT_REQUIRED_MIGRATIONS = (
    "paper_trades_best_effort_position_backfill_v1",
    "strategy_candidate_evidence_native_backfill_v1",
    "strategy_signal_evidence_native_backfill_v1",
    "strategy_trade_positions_roundtrip_backfill_v1",
)


def _safe_rules_dict(value) -> dict:
    """将 risk_rules 字段安全地转换为 dict，防止反复 json.dumps 造成多层嵌套。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _string(value: Any) -> str:
    return str(value or "").strip()


def _coerce_ts(value: Any) -> Any:
    if value is None or isinstance(value, (datetime, date)):
        return value
    text = _string(value)
    if not text:
        return None
    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
        lambda item: datetime.combine(date.fromisoformat(item[:10]), datetime.min.time()),
    ):
        try:
            return parser(text)
        except Exception:
            continue
    return value

from akshare_mcp._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'strategy_incubation_parts',
    'class StrategyIncubationMixin:\n',
    ['reads.py', 'writes.py', 'queries.py', 'mappers.py'],
    future_annotations=False,
)
