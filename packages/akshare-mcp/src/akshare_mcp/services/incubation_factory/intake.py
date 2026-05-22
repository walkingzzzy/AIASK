"""孵化工厂 · 自动识别与接纳模块。

负责扫描策略工厂新产出的合格策略，自动创建孵化账户并绑定。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class IncubationIntake:
    """自动识别和接纳策略工厂产出的新策略。"""

    async def scan_and_accept(self, db: Any) -> dict[str, Any]:
        """
        扫描 status='incubating' 且尚未绑定孵化账户的策略，自动接纳。

        识别条件：
        1. status = 'incubating'（策略工厂 Gate-3 通过后设置）
        2. 尚未有 incubation_account 绑定
        3. 有有效的策略记录

        接纳动作：
        1. 确认策略有效
        2. 创建 incubation_account 记录
        3. 初始化 pipeline_snapshot（stage='warmup'）
        4. 记录 domain_event（incubation.strategy_accepted）
        """
        from ..incubation import get_strategy_incubation_service

        incubation_service = get_strategy_incubation_service()

        # 加载所有 incubating 状态的策略
        incubating = await self._list_incubating_strategies(db)
        if not incubating:
            return {
                "scanned": 0,
                "accepted": 0,
                "skipped": 0,
                "errors": 0,
                "details": [],
            }

        accepted: list[dict[str, Any]] = []
        skipped = 0
        errors = 0

        for strategy in incubating:
            sid = str(strategy.get("id") or "").strip()
            if not sid:
                skipped += 1
                continue

            try:
                # 检查是否已有孵化账户
                existing_account = None
                if hasattr(db, "get_strategy_incubation_account"):
                    existing_account = await db.get_strategy_incubation_account(sid)

                if existing_account:
                    skipped += 1
                    continue

                # 自动创建孵化账户
                ensure_result = await incubation_service.ensure_account(
                    db,
                    strategy,
                    stage="warmup",
                    source_run_id="incubation_factory_intake",
                )

                account = dict(ensure_result.get("account") or {})
                accepted.append({
                    "strategy_id": sid,
                    "strategy_name": strategy.get("name"),
                    "strategy_type": strategy.get("strategy_type"),
                    "account_id": account.get("account_id") or account.get("id"),
                    "accepted_at": datetime.now(timezone.utc).isoformat(),
                })

                # 记录领域事件
                await self._record_acceptance_event(db, strategy, account)

                logger.info(
                    "IncubationIntake: accepted strategy %s (%s)",
                    sid,
                    strategy.get("name"),
                )

            except Exception as exc:
                errors += 1
                logger.warning(
                    "IncubationIntake: failed to accept strategy %s: %s",
                    sid,
                    exc,
                )

        result = {
            "scanned": len(incubating),
            "accepted": len(accepted),
            "skipped": skipped,
            "errors": errors,
            "details": accepted,
        }

        if accepted:
            logger.info(
                "IncubationIntake: accepted %d new strategies (scanned=%d, skipped=%d, errors=%d)",
                len(accepted),
                len(incubating),
                skipped,
                errors,
            )

        return result

    async def _list_incubating_strategies(self, db: Any) -> list[dict[str, Any]]:
        """加载所有 incubating 状态的策略。"""
        if hasattr(db, "list_strategies"):
            return await db.list_strategies("incubating", limit=500)
        return []

    async def _record_acceptance_event(
        self,
        db: Any,
        strategy: dict[str, Any],
        account: dict[str, Any],
    ) -> None:
        """记录策略被孵化工厂接纳的领域事件。"""
        if not hasattr(db, "save_strategy_domain_event"):
            return
        try:
            await db.save_strategy_domain_event({
                "strategy_id": strategy.get("id"),
                "aggregate_type": "incubation_factory",
                "aggregate_id": str(strategy.get("id")),
                "event_type": "incubation_factory.strategy_accepted",
                "source": "incubation_factory_intake",
                "severity": "info",
                "payload": {
                    "strategy_name": strategy.get("name"),
                    "strategy_type": strategy.get("strategy_type"),
                    "account_id": account.get("account_id") or account.get("id"),
                    "initial_stage": "warmup",
                },
            })
        except Exception as exc:
            logger.debug("IncubationIntake: domain event save failed: %s", exc)
