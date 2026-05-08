"""信号-交易归因桥接 (Gap 5).

将已平仓交易与产生它的信号关联，构建 2×2 归因矩阵：

                信号命中          信号错误
交易盈利        技能收益(skill)    运气收益(luck)
交易亏损        执行损耗(slippage)  双重损失(double_loss)

数据源优先级:
1. strategy_trade_positions (closed position, 有 signal_id / net_pnl)
2. paper_trades (fallback)
3. strategy_signals + signal_forward_returns (判定信号方向正确性)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_ATTRIBUTION_LOOKBACK_DAYS = 60
DEFAULT_ATTRIBUTION_NEUTRAL_EPS = 0.0015
DEFAULT_ATTRIBUTION_FORWARD_DAYS = 5


def _string(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class AttributionMatrix:
    """2×2 信号-交易归因矩阵."""

    skill_profit: float = 0.0       # 信号命中 + 交易盈利
    luck_profit: float = 0.0        # 信号错误 + 交易盈利
    slippage_loss: float = 0.0      # 信号命中 + 交易亏损
    double_loss: float = 0.0        # 信号错误 + 交易亏损

    skill_count: int = 0
    luck_count: int = 0
    slippage_count: int = 0
    double_count: int = 0

    @property
    def total_pnl(self) -> float:
        return self.skill_profit + self.luck_profit + self.slippage_loss + self.double_loss

    @property
    def total_linked_trades(self) -> int:
        return self.skill_count + self.luck_count + self.slippage_count + self.double_count

    @property
    def skill_ratio(self) -> float:
        """技能收益在信号命中交易中的占比."""
        total = self.skill_profit + abs(self.slippage_loss)
        return self.skill_profit / total if total > 0 else 0.0

    @property
    def execution_efficiency(self) -> float:
        """执行效率：信号命中的盈亏比."""
        total = self.skill_profit + self.slippage_loss
        return self.skill_profit / abs(total) if total != 0 else 0.0

    @property
    def hit_trade_ratio(self) -> float:
        """命中信号+盈利 占全部关联交易的比例."""
        total = self.total_linked_trades
        return (self.skill_count + self.slippage_count) / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "skill_profit": round(self.skill_profit, 4),
            "luck_profit": round(self.luck_profit, 4),
            "slippage_loss": round(self.slippage_loss, 4),
            "double_loss": round(self.double_loss, 4),
            "skill_count": self.skill_count,
            "luck_count": self.luck_count,
            "slippage_count": self.slippage_count,
            "double_count": self.double_count,
            "total_pnl": round(self.total_pnl, 4),
            "total_linked_trades": self.total_linked_trades,
            "skill_ratio": round(self.skill_ratio, 4),
            "execution_efficiency": round(self.execution_efficiency, 4),
            "hit_trade_ratio": round(self.hit_trade_ratio, 4),
        }


async def _find_signal_forward_return(
    db,
    signal_id: str,
    forward_days: int = DEFAULT_ATTRIBUTION_FORWARD_DAYS,
) -> Optional[float]:
    """查找信号的前向收益.

    优先从 signal_forward_returns 表查找；fallback 到 strategy_signals 自身的
    signal_metadata->forward_returns 字段。
    """
    # 尝试整数 ID 路径
    numeric_id = None
    try:
        numeric_id = int(signal_id)
    except (TypeError, ValueError):
        pass

    if numeric_id is not None and hasattr(db, "get_forward_returns_by_signal_id"):
        fr = await db.get_forward_returns_by_signal_id(numeric_id, forward_days)
        if fr is not None:
            return float(fr)

    # Fallback: 查找 signal_forward_returns 表
    if hasattr(db, "get_signal_forward_return"):
        try:
            fr = await db.get_signal_forward_return(signal_id, forward_days)
            if fr is not None:
                return float(fr)
        except Exception:
            pass

    return None


async def _get_closed_positions(db, strategy_id: str, lookback_days: int) -> List[dict]:
    """获取已平仓的 strategy trade positions."""
    positions: List[dict] = []

    # 优先使用 strategy_trade_positions
    if hasattr(db, "list_strategy_trade_positions"):
        try:
            rows = await db.list_strategy_trade_positions(
                strategy_id=strategy_id,
                status="closed",
                limit=500,
            )
            positions.extend(dict(r) for r in (rows or []))
        except Exception as exc:
            logger.debug("list_strategy_trade_positions failed: %s", exc)

    # Fallback 到 paper_trades
    if not positions and hasattr(db, "list_strategy_paper_trades"):
        try:
            rows = await db.list_strategy_paper_trades(
                strategy_id,
                limit=500,
            )
            for r in (rows or []):
                row = dict(r)
                if _string(row.get("signal_id")):
                    positions.append(row)
        except Exception as exc:
            logger.debug("list_strategy_paper_trades failed: %s", exc)

    # 按日期过滤
    if lookback_days > 0:
        cutoff = date.today() - timedelta(days=lookback_days)
        positions = [
            p for p in positions
            if _coerce_date(p.get("closed_at") or p.get("trade_time") or p.get("updated_at"))
            and (_coerce_date(p.get("closed_at") or p.get("trade_time") or p.get("updated_at")) or date.min) >= cutoff
        ]

    return positions


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        from datetime import datetime as dt
        return dt.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


async def build_attribution_matrix(
    db,
    strategy_id: str,
    *,
    lookback_days: int = DEFAULT_ATTRIBUTION_LOOKBACK_DAYS,
    forward_days: int = DEFAULT_ATTRIBUTION_FORWARD_DAYS,
    neutral_eps: float = DEFAULT_ATTRIBUTION_NEUTRAL_EPS,
) -> Optional[dict]:
    """构建信号-交易归因矩阵.

    Returns:
        dict with keys: strategy_id, lookback_days, linked_trade_count,
        unlinked_trade_count, matrix (AttributionMatrix fields),
        skill_ratio, execution_efficiency, coverage.
    """
    positions = await _get_closed_positions(db, strategy_id, lookback_days)

    if not positions:
        return None

    matrix = AttributionMatrix()
    linked_count = 0
    unlinked_count = 0

    for pos in positions:
        signal_id = _string(pos.get("signal_id"))
        if not signal_id:
            unlinked_count += 1
            continue

        net_pnl = _safe_float(
            pos.get("net_pnl")
            or pos.get("realized_pnl")
            or pos.get("gross_pnl")
            or pos.get("pnl")
        )

        # 判定信号方向是否正确
        forward_return = await _find_signal_forward_return(db, signal_id, forward_days)

        if forward_return is None:
            unlinked_count += 1
            continue

        linked_count += 1
        signal_value = _safe_float(pos.get("signal") or pos.get("direction"))
        signal_direction = 1 if signal_value > 0 else -1 if signal_value < 0 else 0

        if signal_direction == 0:
            unlinked_count += 1
            continue

        directed_return = signal_direction * forward_return
        signal_hit = directed_return > neutral_eps
        trade_win = net_pnl > 0

        if signal_hit and trade_win:
            matrix.skill_profit += net_pnl
            matrix.skill_count += 1
        elif not signal_hit and trade_win:
            matrix.luck_profit += net_pnl
            matrix.luck_count += 1
        elif signal_hit and not trade_win:
            matrix.slippage_loss += net_pnl
            matrix.slippage_count += 1
        else:
            matrix.double_loss += net_pnl
            matrix.double_count += 1

    total_trades = linked_count + unlinked_count

    return {
        "strategy_id": str(strategy_id),
        "lookback_days": lookback_days,
        "linked_trade_count": linked_count,
        "unlinked_trade_count": unlinked_count,
        "matrix": matrix.to_dict(),
        "skill_ratio": round(matrix.skill_ratio, 4),
        "execution_efficiency": round(matrix.execution_efficiency, 4),
        "coverage": {
            "trade_signal_link_ratio": round(
                linked_count / total_trades, 4
            ) if total_trades > 0 else 0.0,
            "position_signal_link_ratio": round(
                linked_count / len(positions), 4
            ) if positions else 0.0,
        },
        "forward_days_used": forward_days,
        "neutral_eps": neutral_eps,
    }


async def build_attribution_summary(
    db,
    strategy_id: str,
    *,
    lookback_days: int = DEFAULT_ATTRIBUTION_LOOKBACK_DAYS,
) -> Optional[dict]:
    """构建归因摘要（精简版，用于 closure review 或 overview 嵌入）."""
    full = await build_attribution_matrix(db, strategy_id, lookback_days=lookback_days)
    if not full:
        return None
    return {
        "strategy_id": full["strategy_id"],
        "skill_ratio": full["skill_ratio"],
        "execution_efficiency": full["execution_efficiency"],
        "linked_trade_count": full["linked_trade_count"],
        "unlinked_trade_count": full["unlinked_trade_count"],
        "diagnosis": _diagnose(full),
    }


def _diagnose(attribution: dict) -> str:
    """基于归因矩阵产出诊断标签."""
    matrix = attribution.get("matrix", {})
    skill_ratio = attribution.get("skill_ratio", 0)
    exec_eff = attribution.get("execution_efficiency", 0)
    linked = attribution.get("linked_trade_count", 0)

    if linked < 10:
        return "insufficient_data"

    if skill_ratio >= 0.6 and exec_eff >= 0.6:
        return "healthy"
    elif skill_ratio >= 0.6 and exec_eff < 0.4:
        return "execution_drag"
    elif skill_ratio < 0.4 and exec_eff >= 0.6:
        return "prediction_weakness"
    elif skill_ratio < 0.4 and exec_eff < 0.4:
        return "dual_failure"
    else:
        return "mixed"
