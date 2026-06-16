
import asyncio
import logging
import os
from contextlib import suppress
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# P2-2：前向收益采集窗口。默认 [1,5,10,20]（零变化）；可经
# STRATEGY_FACTORY_FORWARD_DAYS 覆盖（逗号分隔，如 "1,5,10,20,40" 纳入长线 40 日窗口）。
def _resolve_forward_days() -> list[int]:
    raw = os.getenv("STRATEGY_FACTORY_FORWARD_DAYS")
    if not raw:
        return [1, 5, 10, 20]
    out: list[int] = []
    for tok in str(raw).split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            val = int(tok)
        except ValueError:
            continue
        if val > 0 and val not in out:
            out.append(val)
    return out or [1, 5, 10, 20]


FORWARD_DAYS = _resolve_forward_days()
FORWARD_RETURN_BATCH_LIMIT = 2000
FORWARD_RETURN_MAX_ROUNDS = 100
RECENT_SIGNAL_EVENT_LIMIT = 8


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _forward_return_provider_refresh_enabled() -> bool:
    return _env_bool("STRATEGY_FACTORY_FORWARD_RETURN_PROVIDER_REFRESH_ENABLED", default=True)


def _forward_return_provider_refresh_limit() -> int:
    raw = os.getenv("STRATEGY_FACTORY_FORWARD_RETURN_PROVIDER_LIMIT", "260")
    try:
        value = int(str(raw).strip())
    except Exception:
        value = 260
    return max(60, min(value, 5000))


def _signal_series_from_events(length: int, events: list[dict[str, Any]] | None) -> np.ndarray:
    signals = np.zeros(max(0, int(length)), dtype=np.int8)
    for event in list(events or []):
        idx = int(event.get("index") or 0)
        signal = int(event.get("signal") or 0)
        if 0 <= idx < len(signals) and signal != 0:
            signals[idx] = 1 if signal > 0 else -1
    return signals


def _signal_series_from_masks(entry_mask: np.ndarray, exit_mask: np.ndarray) -> np.ndarray:
    entry = np.asarray(entry_mask, dtype=bool)
    exit_ = np.asarray(exit_mask, dtype=bool)
    size = max(len(entry), len(exit_))
    signals = np.zeros(size, dtype=np.int8)
    if len(entry):
        signals[: len(entry)][entry] = 1
    if len(exit_):
        exit_slice = signals[: len(exit_)]
        exit_slice[np.asarray(exit_, dtype=bool) & (exit_slice == 0)] = -1
    return signals


def _coerce_event_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized).date()
    except Exception:
        pass
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _default_event_action(signal: int) -> str:
    return "enter" if int(signal or 0) > 0 else ("exit" if int(signal or 0) < 0 else "hold")


def _classify_action_source(
    *,
    execution_semantic_mode: str,
    signal: int,
    action: Optional[str],
    reason: Optional[str],
) -> str:
    normalized_mode = str(execution_semantic_mode or "").strip().lower()
    normalized_action = str(action or "").strip().lower()
    normalized_reason = str(reason or "").strip().lower()
    if normalized_mode != "compiled_dsl":
        return "builtin_legacy_signal"
    if normalized_action == "enter" or int(signal or 0) > 0:
        return "dsl_entry"
    if normalized_action == "reduce":
        return "runtime_playbook_reduce"
    if normalized_action in {"freeze_reentry", "stop"}:
        return "runtime_playbook_stop"
    runtime_stop_tokens = (
        "stop",
        "take_profit",
        "trailing",
        "time_stop",
        "freeze",
        "band",
    )
    if any(token in normalized_reason for token in runtime_stop_tokens):
        return "runtime_playbook_stop"
    return "dsl_exit"


def _normalize_signal_events(
    klines: list[dict[str, Any]],
    events: list[dict[str, Any]] | None,
    *,
    execution_semantic_mode: str,
) -> list[dict[str, Any]]:
    ordered = list(klines or [])
    normalized: list[dict[str, Any]] = []
    max_length = len(ordered)
    for sequence, raw_event in enumerate(list(events or [])):
        try:
            index = int(raw_event.get("index") or 0)
        except Exception:
            continue
        if index < 0 or index >= max_length:
            continue
        raw_signal = int(raw_event.get("signal") or 0)
        signal = 1 if raw_signal > 0 else (-1 if raw_signal < 0 else 0)
        action = str(raw_event.get("action") or _default_event_action(signal)).strip().lower() or _default_event_action(signal)
        reason = str(raw_event.get("reason") or "").strip() or None
        units = _coerce_optional_float(raw_event.get("units"))
        remaining_units = _coerce_optional_float(raw_event.get("remaining_units"))
        bar = ordered[index] if 0 <= index < len(ordered) else {}
        event_date = _coerce_event_date(bar.get("date") or bar.get("time"))
        action_source = _classify_action_source(
            execution_semantic_mode=execution_semantic_mode,
            signal=signal,
            action=action,
            reason=reason,
        )
        normalized.append(
            {
                "sequence": sequence,
                "index": index,
                "date": event_date.isoformat() if event_date else None,
                "signal": signal,
                "action": action,
                "action_source": action_source,
                "reason": reason,
                "units": units,
                "remaining_units": remaining_units,
            }
        )
    return normalized


def _synthesize_events_from_masks(
    klines: list[dict[str, Any]],
    entry_mask: np.ndarray,
    exit_mask: np.ndarray,
    *,
    execution_semantic_mode: str,
) -> list[dict[str, Any]]:
    entry = np.asarray(entry_mask, dtype=bool)
    exit_ = np.asarray(exit_mask, dtype=bool)
    size = max(len(entry), len(exit_))
    events: list[dict[str, Any]] = []
    for index in range(size):
        if index < len(entry) and bool(entry[index]):
            events.append(
                {
                    "index": index,
                    "signal": 1,
                    "action": "enter",
                    "reason": "legacy_entry_mask",
                }
            )
        if index < len(exit_) and bool(exit_[index]):
            events.append(
                {
                    "index": index,
                    "signal": -1,
                    "action": "exit",
                    "reason": "legacy_exit_mask",
                }
            )
    return _normalize_signal_events(
        klines,
        events,
        execution_semantic_mode=execution_semantic_mode,
    )


def _synthesize_events_from_signal_series(
    klines: list[dict[str, Any]],
    signal_series: np.ndarray,
    *,
    execution_semantic_mode: str,
) -> list[dict[str, Any]]:
    signals = np.asarray(signal_series, dtype=np.int8)
    events: list[dict[str, Any]] = []
    last_nonzero_signal = 0
    for index, raw_signal in enumerate(signals):
        signal = 1 if int(raw_signal) > 0 else (-1 if int(raw_signal) < 0 else 0)
        if signal == 0 or signal == last_nonzero_signal:
            continue
        events.append(
            {
                "index": index,
                "signal": signal,
                "action": _default_event_action(signal),
                "reason": "legacy_signal_series",
            }
        )
        last_nonzero_signal = signal
    return _normalize_signal_events(
        klines,
        events,
        execution_semantic_mode=execution_semantic_mode,
    )


def _build_signal_tracking_artifacts(
    instance: Any,
    klines: list[dict[str, Any]],
    *,
    execution_semantic_mode: str,
) -> dict[str, Any]:
    ordered = list(klines or [])
    if not ordered:
        return {
            "signal_series": np.zeros(0, dtype=np.int8),
            "events": [],
            "latest_bar_signal": 0,
            "latest_bar_date": None,
            "signal_row": None,
            "snapshot": None,
        }

    signal_series: Optional[np.ndarray] = None
    normalized_events: list[dict[str, Any]] = []
    if hasattr(instance, "generate_signal_events_from_klines"):
        events = instance.generate_signal_events_from_klines(ordered)
        if events is not None:
            normalized_events = _normalize_signal_events(
                ordered,
                events,
                execution_semantic_mode=execution_semantic_mode,
            )
            signal_series = _signal_series_from_events(len(ordered), normalized_events)
    if signal_series is None and hasattr(instance, "generate_entry_exit_masks_from_klines"):
        entry_mask, exit_mask = instance.generate_entry_exit_masks_from_klines(ordered)
        signal_series = _signal_series_from_masks(entry_mask, exit_mask)
        normalized_events = _synthesize_events_from_masks(
            ordered,
            entry_mask,
            exit_mask,
            execution_semantic_mode=execution_semantic_mode,
        )
    if signal_series is None:
        closes = np.array([float(k.get("close", 0) or 0.0) for k in ordered], dtype=float)
        volumes = np.array([float(k.get("volume", 0) or 0.0) for k in ordered], dtype=float)
        try:
            signal_series = np.asarray(instance.generate_signals(closes, volumes), dtype=np.int8)
        except TypeError:
            signal_series = np.asarray(instance.generate_signals(closes), dtype=np.int8)
        normalized_events = _synthesize_events_from_signal_series(
            ordered,
            signal_series,
            execution_semantic_mode=execution_semantic_mode,
        )

    latest_bar_signal = int(signal_series[-1]) if len(signal_series) > 0 else 0
    latest_bar_date = _coerce_event_date((ordered[-1] or {}).get("date") or (ordered[-1] or {}).get("time"))
    latest_bar_index = len(signal_series) - 1
    latest_bar_event = next(
        (event for event in reversed(normalized_events) if int(event.get("index") or -1) == latest_bar_index),
        None,
    )
    latest_event = normalized_events[-1] if normalized_events else None
    latest_entry = next((event for event in reversed(normalized_events) if str(event.get("action") or "") == "enter"), None)
    latest_exit = next((event for event in reversed(normalized_events) if str(event.get("action") or "") == "exit"), None)
    nonzero_indexes = np.flatnonzero(np.asarray(signal_series, dtype=np.int8) != 0)
    latest_nonzero_index = int(nonzero_indexes[-1]) if len(nonzero_indexes) > 0 else None
    latest_nonzero_date = None
    latest_nonzero_signal = None
    if latest_nonzero_index is not None and 0 <= latest_nonzero_index < len(ordered):
        latest_nonzero_date = _coerce_event_date(
            (ordered[latest_nonzero_index] or {}).get("date") or (ordered[latest_nonzero_index] or {}).get("time")
        )
        latest_nonzero_signal = int(signal_series[latest_nonzero_index])

    default_action_source = _classify_action_source(
        execution_semantic_mode=execution_semantic_mode,
        signal=latest_bar_signal,
        action=_default_event_action(latest_bar_signal) if latest_bar_signal != 0 else None,
        reason=None,
    ) if latest_bar_signal != 0 else None
    signal_row = None
    if latest_bar_signal != 0:
        signal_row = {
            "signal": latest_bar_signal,
            "score": float(latest_bar_signal),
            "execution_semantic_mode": execution_semantic_mode,
            "action_source": (
                str(latest_bar_event.get("action_source") or "").strip() or default_action_source
                if latest_bar_event
                else default_action_source
            ),
            "event_action": (
                str(latest_bar_event.get("action") or "").strip() or _default_event_action(latest_bar_signal)
                if latest_bar_event
                else _default_event_action(latest_bar_signal)
            ),
            "action_reason": (
                str(latest_bar_event.get("reason") or "").strip() or None
                if latest_bar_event
                else None
            ),
            "signal_metadata": {
                "latest_bar_date": latest_bar_date.isoformat() if latest_bar_date else None,
                "latest_event_index": latest_event.get("index") if latest_event else None,
                "latest_event_date": latest_event.get("date") if latest_event else None,
                "latest_nonzero_signal_index": latest_nonzero_index,
                "latest_nonzero_signal_date": latest_nonzero_date.isoformat() if latest_nonzero_date else None,
                "latest_nonzero_signal": latest_nonzero_signal,
                "event_count": len(normalized_events),
                "latest_bar_has_event": latest_bar_event is not None,
                "execution_semantic_mode": execution_semantic_mode,
                "action_source": (
                    str(latest_bar_event.get("action_source") or "").strip() or default_action_source
                    if latest_bar_event
                    else default_action_source
                ),
                "event_action": (
                    str(latest_bar_event.get("action") or "").strip() or _default_event_action(latest_bar_signal)
                    if latest_bar_event
                    else _default_event_action(latest_bar_signal)
                ),
                "action_reason": (
                    str(latest_bar_event.get("reason") or "").strip() or None
                    if latest_bar_event
                    else None
                ),
            },
        }

    recent_events = []
    for event in normalized_events[-RECENT_SIGNAL_EVENT_LIMIT:]:
        recent_events.append(
            {
                "index": int(event.get("index") or 0),
                "date": event.get("date"),
                "signal": int(event.get("signal") or 0),
                "action": event.get("action"),
                "action_source": event.get("action_source"),
                "reason": event.get("reason"),
                "units": event.get("units"),
                "remaining_units": event.get("remaining_units"),
            }
        )

    snapshot = {
        "latest_bar_date": latest_bar_date,
        "latest_bar_signal": latest_bar_signal,
        "execution_semantic_mode": execution_semantic_mode,
        "latest_event_index": latest_event.get("index") if latest_event else None,
        "latest_event_date": latest_event.get("date") if latest_event else None,
        "latest_event_signal": latest_event.get("signal") if latest_event else None,
        "latest_event_action": latest_event.get("action") if latest_event else None,
        "latest_event_action_source": latest_event.get("action_source") if latest_event else None,
        "latest_event_reason": latest_event.get("reason") if latest_event else None,
        "latest_event_units": latest_event.get("units") if latest_event else None,
        "latest_entry_date": latest_entry.get("date") if latest_entry else None,
        "latest_exit_date": latest_exit.get("date") if latest_exit else None,
        "event_count": len(normalized_events),
        "recent_events": recent_events,
        "metadata": {
            "latest_bar_has_event": latest_bar_event is not None,
            "recent_event_window": RECENT_SIGNAL_EVENT_LIMIT,
            "latest_nonzero_signal_index": latest_nonzero_index,
            "latest_nonzero_signal_date": latest_nonzero_date.isoformat() if latest_nonzero_date else None,
            "latest_nonzero_signal": latest_nonzero_signal,
        },
    }
    return {
        "signal_series": signal_series,
        "events": normalized_events,
        "latest_bar_signal": latest_bar_signal,
        "latest_bar_date": latest_bar_date,
        "signal_row": signal_row,
        "snapshot": snapshot,
    }
