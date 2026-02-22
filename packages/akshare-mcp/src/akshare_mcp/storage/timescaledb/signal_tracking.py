"""TimescaleDB 适配器 — 信号跟踪 Mixin"""

import random
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SignalTrackingMixin:
    """前向信号记录与收益验证"""

    async def save_signals(
        self, strategy_id: str, signal_date: date, signals: List[Dict[str, Any]]
    ) -> int:
        """批量写入信号。每个 dict: {code, signal, score}"""
        if not signals:
            return 0
        async with self.acquire() as conn:
            count = 0
            for s in signals:
                try:
                    await conn.execute(
                        """INSERT INTO strategy_signals (strategy_id, signal_date, code, signal, score)
                           VALUES ($1, $2, $3, $4, $5)
                           ON CONFLICT (strategy_id, signal_date, code) DO UPDATE
                           SET signal = EXCLUDED.signal, score = EXCLUDED.score""",
                        strategy_id, signal_date,
                        str(s["code"]), int(s["signal"]),
                        float(s.get("score") or 0),
                    )
                    count += 1
                except Exception as e:
                    logger.warning("save_signal error: %s", e)
            return count

    async def get_signals(
        self,
        strategy_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
    ) -> List[dict]:
        """查询信号（实时，无延迟）"""
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_signals WHERE strategy_id = $1"
            params: list = [strategy_id]
            idx = 2
            if start_date:
                sql += f" AND signal_date >= ${idx}"
                params.append(start_date)
                idx += 1
            if end_date:
                sql += f" AND signal_date <= ${idx}"
                params.append(end_date)
                idx += 1
            sql += f" ORDER BY signal_date DESC, code LIMIT ${idx}"
            params.append(limit)
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def get_signals_public(
        self, strategy_id: str, limit: int = 100
    ) -> List[dict]:
        """公开 API：信号延迟 1-3 个交易日（IP 保护）"""
        delay_days = random.randint(1, 3)
        cutoff = date.today() - timedelta(days=delay_days)
        return await self.get_signals(strategy_id, end_date=cutoff, limit=limit)

    async def save_forward_returns(
        self, signal_id: int, forward_days: int, actual_return: float
    ) -> None:
        async with self.acquire() as conn:
            await conn.execute(
                """INSERT INTO signal_forward_returns (signal_id, forward_days, actual_return)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (signal_id, forward_days) DO UPDATE
                   SET actual_return = EXCLUDED.actual_return, calculated_at = NOW()""",
                signal_id, forward_days, actual_return,
            )

    async def get_pending_forward_returns(self, forward_days: int) -> List[dict]:
        """找到 N 天前的信号中尚未计算前向收益的记录"""
        cutoff = date.today() - timedelta(days=forward_days)
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """SELECT ss.id, ss.strategy_id, ss.signal_date, ss.code, ss.signal
                   FROM strategy_signals ss
                   WHERE ss.signal_date <= $1
                     AND NOT EXISTS (
                         SELECT 1 FROM signal_forward_returns sfr
                         WHERE sfr.signal_id = ss.id AND sfr.forward_days = $2
                     )
                   ORDER BY ss.signal_date
                   LIMIT 500""",
                cutoff, forward_days,
            )
        return [dict(r) for r in rows]

    async def get_signal_stats(self, strategy_id: str) -> dict:
        """聚合统计：命中率、前向 IC、前向 Sharpe"""
        async with self.acquire() as conn:
            # 命中率：信号方向与实际收益方向一致的比例
            rows = await conn.fetch(
                """SELECT ss.signal, sfr.forward_days, sfr.actual_return
                   FROM strategy_signals ss
                   JOIN signal_forward_returns sfr ON sfr.signal_id = ss.id
                   WHERE ss.strategy_id = $1
                   ORDER BY sfr.forward_days""",
                strategy_id,
            )

        if not rows:
            return {"hit_rate": {}, "forward_ic": {}, "forward_sharpe": {}, "total_signals": 0}

        by_days: Dict[int, list] = {}
        for r in rows:
            fd = r["forward_days"]
            by_days.setdefault(fd, []).append(r)

        hit_rate = {}
        forward_ic = {}
        forward_sharpe = {}

        for fd, records in by_days.items():
            signals_arr = np.array([r["signal"] for r in records], dtype=float)
            returns_arr = np.array([r["actual_return"] or 0 for r in records], dtype=float)

            # 命中率
            hits = np.sum((signals_arr * returns_arr) > 0)
            hit_rate[fd] = round(float(hits / len(records)), 4) if records else 0

            # 前向 IC (Spearman rank correlation)
            if len(records) >= 5:
                from scipy import stats as sp_stats
                ic, _ = sp_stats.spearmanr(signals_arr, returns_arr)
                forward_ic[fd] = round(float(ic), 4) if not np.isnan(ic) else 0
            else:
                forward_ic[fd] = 0

            # 前向 Sharpe (信号方向加权收益的 Sharpe)
            directed_returns = signals_arr * returns_arr
            mean_r = float(np.mean(directed_returns))
            std_r = float(np.std(directed_returns))
            forward_sharpe[fd] = round(mean_r / std_r, 4) if std_r > 0 else 0

        return {
            "hit_rate": hit_rate,
            "forward_ic": forward_ic,
            "forward_sharpe": forward_sharpe,
            "total_signals": len(rows),
        }

    async def is_subscribed(self, strategy_id: str, user_id: str) -> bool:
        """检查用户是否订阅了策略"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT 1 FROM strategy_subscriptions
                   WHERE strategy_id = $1 AND user_id = $2 AND status = 'active'""",
                strategy_id, user_id,
            )
        return row is not None
