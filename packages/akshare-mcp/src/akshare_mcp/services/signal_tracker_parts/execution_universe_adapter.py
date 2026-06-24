"""SignalTracker ExecutionUniverseContract 适配层。

P1-1: SignalTracker 集成 ExecutionUniverseContract
规范要求: SignalTracker 必须通过统一执行宇宙契约查询可执行策略
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


async def load_executable_strategies_via_contract(
    db: Any,
    *,
    limit: int = 500,
) -> list[dict]:
    """通过 ExecutionUniverseContract 加载可执行策略。

    替代旧的查询路径:
    - list_active_paper_observation_strategies
    - list_paper_observation_strategies
    - list_incubating_strategies
    - list_strategies("submitted")

    Args:
        db: 数据库连接
        limit: 返回策略数量上限

    Returns:
        可执行策略列表 (转换为兼容格式)
    """
    try:
        # 导入统一契约
        from akshare_mcp.services.strategy_lifecycle_shared.execution_universe_contract import (
            ExecutionUniverseContract,
            ExecutionUniverseQuery,
        )

        contract = ExecutionUniverseContract()
        query = ExecutionUniverseQuery(
            as_of=date.today(),
            include_incubating=True,
            include_paper=True,
            include_diagnostic=False,  # SignalTracker 不处理 diagnostic
            include_listed=False,  # listed 策略走单独逻辑
            limit=limit,
        )

        # 查询执行宇宙
        universe_strategies = await contract.list_executable_strategies(db, query)

        # 转换为 SignalTracker 兼容格式
        strategies: list[dict] = []
        for strategy in universe_strategies:
            strategies.append({
                "id": strategy.strategy_id,
                "name": strategy.strategy_name,
                "strategy_type": strategy.strategy_type,
                "status": strategy.status,
                "incubation_stage": strategy.incubation_stage,
                "incubation_status": strategy.incubation_status,
                "account_id": strategy.account_id,
                "created_at": strategy.created_at,
            })

        logger.info(
            "SignalTracker: loaded %d executable strategies via ExecutionUniverseContract",
            len(strategies)
        )
        return strategies

    except ImportError as exc:
        logger.warning(
            "SignalTracker: ExecutionUniverseContract not available, falling back to legacy paths: %s",
            exc
        )
        return []
    except Exception as exc:
        logger.error(
            "SignalTracker: ExecutionUniverseContract query failed: %s",
            exc,
            exc_info=True
        )
        return []


async def load_executable_strategies_with_fallback(
    db: Any,
    *,
    limit: int = 500,
    use_contract: bool = True,
) -> list[dict]:
    """加载可执行策略，支持契约优先 + 降级到旧路径。

    Args:
        db: 数据库连接
        limit: 返回策略数量上限
        use_contract: 是否优先使用 ExecutionUniverseContract

    Returns:
        可执行策略列表
    """
    # 1. 尝试使用统一契约
    if use_contract:
        strategies = await load_executable_strategies_via_contract(db, limit=limit)
        if strategies:
            return strategies
        logger.warning(
            "SignalTracker: ExecutionUniverseContract returned empty, falling back to legacy paths"
        )

    # 2. 降级到旧查询路径（向后兼容）
    logger.info("SignalTracker: using legacy query paths")
    candidates: list[dict] = []

    # 旧路径 1: list_active_paper_observation_strategies
    for method_name in (
        "list_active_paper_observation_strategies",
        "list_paper_observation_strategies",
    ):
        method = getattr(db, method_name, None)
        if not callable(method):
            continue
        try:
            rows = await method(limit=limit)
            candidates.extend(list(rows or []))
        except Exception as exc:
            logger.warning("SignalTracker: %s failed: %s", method_name, exc)

    # 旧路径 2: list_strategies("incubating")
    if hasattr(db, "list_strategies"):
        try:
            rows = await db.list_strategies("incubating", limit=limit)
            candidates.extend(list(rows or []))
        except Exception as exc:
            logger.warning("SignalTracker: list_strategies(incubating) failed: %s", exc)

    # 去重
    seen: set[str] = set()
    unique_strategies: list[dict] = []
    for strategy in candidates:
        strategy_id = str((strategy or {}).get("id") or "").strip()
        if strategy_id and strategy_id not in seen:
            seen.add(strategy_id)
            unique_strategies.append(strategy)

    logger.info(
        "SignalTracker: loaded %d executable strategies via legacy paths",
        len(unique_strategies)
    )
    return unique_strategies
