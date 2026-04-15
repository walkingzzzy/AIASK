"""撮合引擎 — 异步后台任务，定期扫描 pending 订单并撮合成交。"""

import asyncio
import json
import logging
from contextlib import suppress
from .slippage import FixedSlippageModel
from datetime import datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 交易时间段（CST）
_MORNING_OPEN = time(9, 30)
_MORNING_CLOSE = time(11, 30)
_AFTERNOON_OPEN = time(13, 0)
_AFTERNOON_CLOSE = time(15, 0)

SCAN_INTERVAL_SECONDS = 30


def _is_trading_time(now: datetime) -> bool:
    """判断当前是否在 A 股交易时间内（工作日 9:30-11:30, 13:00-15:00）"""
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (_MORNING_OPEN <= t <= _MORNING_CLOSE) or (_AFTERNOON_OPEN <= t <= _AFTERNOON_CLOSE)


def _get_limit_ratio(code: str) -> float:
    """涨跌停幅度：创业板/科创板 20%，其余 10%"""
    c = str(code).strip()
    for prefix in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if c.startswith(prefix):
            c = c[len(prefix):]
            break
    if c.startswith("300") or c.startswith("301") or c.startswith("688"):
        return 0.20
    return 0.10


class MatchingEngine:
    """异步撮合引擎"""

    def __init__(self, scan_interval: int = SCAN_INTERVAL_SECONDS):
        self.scan_interval = scan_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.matched_count = 0
        self.scan_count = 0
        self.last_scan: Optional[datetime] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="matching-engine")
        logger.info("[MatchingEngine] started, scan every %ds", self.scan_interval)

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[MatchingEngine] stopped")

    async def shutdown(self, grace_sec: float = 2.0):
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            logger.info("[MatchingEngine] stopped")
            return
        if not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, grace_sec))
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        else:
            with suppress(asyncio.CancelledError):
                await task
        logger.info("[MatchingEngine] stopped")

    def status(self) -> dict:
        return {
            "running": self._running,
            "scan_interval": self.scan_interval,
            "scan_count": self.scan_count,
            "matched_count": self.matched_count,
            "last_scan": str(self.last_scan) if self.last_scan else None,
        }

    async def _loop(self):
        while self._running:
            try:
                now = datetime.now()
                if _is_trading_time(now):
                    await self._scan_and_match()
                else:
                    # 非交易时间也做止损检查（基于上一收盘价）
                    pass
                await asyncio.sleep(self.scan_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[MatchingEngine] loop error: %s", e, exc_info=True)
                await asyncio.sleep(60)

    async def _scan_and_match(self):
        from ..storage import get_db
        db = get_db()
        self.scan_count += 1
        self.last_scan = datetime.now()

        async with db.acquire() as conn:
            pending = await conn.fetch(
                "SELECT * FROM paper_orders WHERE status='pending' ORDER BY created_at"
            )

        for order in pending:
            try:
                await self._try_match_order(db, dict(order))
            except Exception as e:
                logger.warning("[MatchingEngine] match order %s error: %s", order.get('id'), e)

        # 止损检查
        await self._check_stop_loss(db)

        # 风控自动处置
        await self._run_risk_executor(db)

    async def _try_match_order(self, db, order: dict):
        code = order['code']
        direction = order['direction']
        order_type = order.get('order_type', 'limit')
        limit_price = order.get('price')
        stop_price = order.get('stop_price')
        shares = int(order['shares'])
        order_id = order['id']
        account_id = order['account_id']

        # 获取实时价格
        current_price = await self._get_current_price(code, db)
        if current_price is None:
            return

        # 涨跌停检测
        prev_close = await self._get_prev_close(code, db)
        if prev_close and prev_close > 0:
            ratio = _get_limit_ratio(code)
            upper = prev_close * (1 + ratio)
            lower = prev_close * (1 - ratio)
            if direction == 'buy' and current_price >= upper * 0.99:
                return  # 涨停不可买
            if direction == 'sell' and current_price <= lower * 1.01:
                return  # 跌停不可卖

        should_fill = False
        fill_price = current_price

        if order_type == 'limit':
            if direction == 'buy' and limit_price and current_price <= limit_price:
                should_fill = True
                fill_price = min(current_price, limit_price)
            elif direction == 'sell' and limit_price and current_price >= limit_price:
                should_fill = True
                fill_price = max(current_price, limit_price)
        elif order_type == 'stop':
            if direction == 'buy' and stop_price and current_price >= stop_price:
                should_fill = True
            elif direction == 'sell' and stop_price and current_price <= stop_price:
                should_fill = True

        if not should_fill:
            return

        # 滑点调整：买入价上移，卖出价下移
        slippage_model = FixedSlippageModel(slippage_rate=0.0005)
        slip = slippage_model.calculate_slippage(fill_price, 0, shares, is_buy=(direction == 'buy'))
        if direction == 'buy':
            fill_price = fill_price + slip
        else:
            fill_price = max(0.01, fill_price - slip)

        # 执行成交
        from ..tools.managers.paper_trading_manager import _fill_order, _record_order_event
        async with db.acquire() as conn:
            try:
                trade_id, commission = await _fill_order(
                    conn,
                    account_id,
                    code,
                    direction,
                    shares,
                    fill_price,
                    strategy_id=order.get('strategy_id'),
                    source_order_id=str(order_id),
                    signal_id=order.get('signal_id'),
                    position_id=order.get('position_id'),
                )
                await conn.execute(
                    "UPDATE paper_orders SET status='filled', filled_at=NOW(), commission=$1, updated_at=NOW() WHERE id=$2",
                    commission, order_id
                )
                await _record_order_event(
                    conn,
                    str(order_id),
                    'filled_by_engine',
                    account_id=account_id,
                    code=code,
                    payload={
                        'trade_id': str(trade_id),
                        'direction': direction,
                        'shares': shares,
                        'fill_price': fill_price,
                        'commission': round(commission, 4),
                    }
                )
                self.matched_count += 1
                logger.info("[MatchingEngine] filled order %s: %s %s x%d @%.2f",
                            order_id, direction, code, shares, fill_price)
            except ValueError as e:
                # 持仓不足等业务错误 → 拒绝
                await conn.execute(
                    "UPDATE paper_orders SET status='rejected', reason=$1, updated_at=NOW() WHERE id=$2",
                    str(e), order_id
                )
                await _record_order_event(
                    conn,
                    str(order_id),
                    'rejected_by_engine',
                    account_id=account_id,
                    code=code,
                    payload={
                        'direction': direction,
                        'shares': shares,
                        'reason': str(e),
                    }
                )

    async def _check_stop_loss(self, db):
        """检查所有账户持仓，亏损超过止损线的自动卖出"""
        async with db.acquire() as conn:
            accounts = await conn.fetch("SELECT * FROM paper_accounts")

        for acct in accounts:
            rules = acct.get('risk_rules') or {}
            if isinstance(rules, str):
                try:
                    rules = json.loads(rules)
                except Exception:
                    rules = {}
            if not isinstance(rules, dict):
                rules = {}

            stop_loss_pct = float(rules.get('stop_loss_pct', 0))
            if stop_loss_pct <= 0:
                continue

            account_id = acct['id']
            async with db.acquire() as conn:
                positions = await conn.fetch(
                    "SELECT * FROM paper_positions WHERE account_id=$1", account_id
                )
            for pos in positions:
                cost = float(pos.get('cost_price') or 0)
                current = float(pos.get('current_price') or 0)
                if cost <= 0 or current <= 0:
                    continue
                loss_pct = (cost - current) / cost * 100
                if loss_pct >= stop_loss_pct:
                    qty = int(pos.get('quantity') or 0)
                    if qty <= 0:
                        continue
                    code = pos['stock_code']
                    logger.info("[MatchingEngine] stop-loss trigger: %s loss %.1f%% >= %.1f%%",
                                code, loss_pct, stop_loss_pct)
                    try:
                        from ..tools.managers.paper_trading_manager import _fill_order
                        async with db.acquire() as conn:
                            await _fill_order(conn, account_id, code, 'sell', qty, current)
                    except Exception as e:
                        logger.warning("[MatchingEngine] stop-loss sell %s failed: %s", code, e)

    async def _get_current_price(self, code: str, db) -> Optional[float]:
        try:
            from ..tools.market import get_realtime_quote
            from ..utils import normalize_code
            res = get_realtime_quote(normalize_code(code))
            if res and res.get('success') and res.get('data'):
                d = res['data']
                return d.get('price') or d.get('close') or d.get('now')
        except Exception:
            pass
        return None

    async def _get_prev_close(self, code: str, db) -> Optional[float]:
        try:
            from ..tools.market import get_realtime_quote
            from ..utils import normalize_code
            res = get_realtime_quote(normalize_code(code))
            if res and res.get('success') and res.get('data'):
                return res['data'].get('prev_close') or res['data'].get('pre_close')
        except Exception:
            pass
        return None

    async def _run_risk_executor(self, db):
        """对所有账户执行风控自动处置"""
        try:
            from .risk_executor import get_risk_executor
            executor = get_risk_executor()
            async with db.acquire() as conn:
                accounts = await conn.fetch("SELECT id FROM paper_accounts")
            for acct in accounts:
                try:
                    actions = await executor.enforce(acct['id'])
                    if actions:
                        logger.info("[MatchingEngine] risk_executor triggered %d actions for %s",
                                    len(actions), acct['id'])
                except Exception as e:
                    logger.warning("[MatchingEngine] risk_executor error for %s: %s", acct['id'], e, exc_info=True)
        except Exception as e:
            logger.warning("[MatchingEngine] risk_executor import/run error: %s", e)


# Singleton
_engine: Optional[MatchingEngine] = None


def get_matching_engine() -> MatchingEngine:
    global _engine
    if _engine is None:
        _engine = MatchingEngine()
    return _engine
