"""High-value MCP prompts built from server-side context."""

from __future__ import annotations

import json

from mcp.server.fastmcp.prompts.base import AssistantMessage, UserMessage

from ..services.factor_prompt_builder import build_factor_mining_prompt
from ..storage import get_db
from ..resources.strategy import build_strategy_review_payload


def _parse_codes(raw_codes: str) -> list[str]:
    text = str(raw_codes or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    return [item.strip() for item in text.split(",") if item.strip()]


def register(mcp) -> None:
    """Register prompt templates."""

    @mcp.prompt(
        name="factor-mining",
        title="Factor Mining",
        description="Build a structured factor-mining prompt from recent market, fund-flow and financial context",
    )
    async def factor_mining(codes: str, candidate_count: int = 8, focus: str | None = None):
        normalized_codes = _parse_codes(codes)
        if not normalized_codes:
            raise ValueError("codes is required")

        db = get_db()
        prompt = await build_factor_mining_prompt(
            db,
            normalized_codes,
            candidate_count=max(1, min(int(candidate_count or 8), 24)),
        )

        user_text = str(prompt.user_prompt or "")
        if focus:
            user_text = f"{user_text}\n\n额外关注点:\n{focus}"

        return [
            AssistantMessage(content=str(prompt.system_prompt or "")),
            UserMessage(content=user_text),
        ]

    @mcp.prompt(
        name="strategy-review",
        title="Strategy Review",
        description="Assemble a strategy review prompt from lifecycle projection, runtime control and latest review state",
    )
    async def strategy_review(strategy_id: str, focus: str | None = None, include_projection: bool = True):
        payload = await build_strategy_review_payload(strategy_id)
        if not payload.get("found"):
            raise ValueError(str(payload.get("error") or f"strategy not found: {strategy_id}"))

        strategy = dict(payload.get("strategy") or {})
        projection = dict(payload.get("projection") or {}) if include_projection else {}
        review = dict(payload.get("latest_promotion_review") or {})
        runtime_control = dict(payload.get("runtime_control") or {})
        open_risks = list(payload.get("open_risks") or [])

        review_context = {
            "strategy": strategy,
            "projection": projection,
            "latest_promotion_review": review,
            "runtime_control": runtime_control,
            "open_risks": open_risks,
            "summary": payload.get("summary") or {},
            "focus": focus or "",
            "resource_uri": f"resource://strategy/{strategy_id}/review",
        }

        rubric = "\n".join(
            [
                "请从以下维度评审该策略：",
                "1. 生命周期阶段与当前状态是否一致。",
                "2. 最新推广评审、运行时控制和风险事件是否存在冲突。",
                "3. 是否需要补充投影重建、风控动作或指标回补。",
                "4. 给出优先级明确的整改建议。",
            ]
        )

        return [
            AssistantMessage(content=rubric),
            UserMessage(content=json.dumps(review_context, ensure_ascii=False, indent=2, default=str)),
        ]
