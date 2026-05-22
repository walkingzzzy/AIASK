"""规则种子引擎 — 包装现有 llm_alpha.py + factor_candidate_seed.py。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .base import EngineStatus, FactorCandidate, SearchBudget

logger = logging.getLogger(__name__)


class RuleSeedEngine:
    """规则种子引擎 — 从预定义模板和本地规则生成候选因子。

    复用现有：
    - factor_candidate_seed._EXPRESSION_BY_FACTOR
    - llm_alpha.LLMAlphaMiner._build_local_candidate_pool()
    """

    engine_id: str
    engine_type: str = "rule"

    def __init__(self, engine_id: str = "rule_seed"):
        self.engine_id = engine_id
        self._success_count = 0
        self._failure_count = 0
        self._last_run_at: str | None = None
        self._last_error: str | None = None

    async def generate(
        self,
        context: Any,
        budget: SearchBudget,
    ) -> list[FactorCandidate]:
        """从种子库和本地规则生成候选。"""
        try:
            candidates = []
            candidates.extend(
                self._from_blueprints(context, max(1, budget.candidate_count // 2))
            )

            # 1. 从种子库生成
            seed_candidates = self._from_seed_library(budget.candidate_count // 2)
            candidates.extend(seed_candidates)

            # 2. 从本地规则生成（组合变体）
            variant_candidates = self._generate_variants(budget.candidate_count - len(candidates))
            variant_candidates = self._generate_variants(budget.candidate_count - len(candidates))
            candidates.extend(variant_candidates)

            self._success_count += 1
            self._last_run_at = datetime.now(timezone.utc).isoformat()
            self._last_error = None
            return self._dedupe(candidates)[:budget.candidate_count]

        except Exception as exc:
            self._failure_count += 1
            self._last_error = str(exc)
            self._last_run_at = datetime.now(timezone.utc).isoformat()
            logger.warning("RuleSeedEngine: failed: %s", exc)
            return []

    def _from_blueprints(self, context: Any, count: int) -> list[FactorCandidate]:
        from ..blueprints import candidate_from_blueprint

        candidates: list[FactorCandidate] = []
        for index, blueprint in enumerate(
            list(getattr(context, "alpha_blueprints", []) or [])[: max(0, count)]
        ):
            candidate = candidate_from_blueprint(
                blueprint,
                engine_id=self.engine_id,
                index=index,
                mode="rule_blueprint_seed",
            )
            candidate.generation_trace["source"] = "alpha_blueprint_library"
            candidates.append(candidate)
        return candidates

    def _from_seed_library(self, count: int) -> list[FactorCandidate]:
        """从种子因子库生成。"""
        from ...factor_candidate_seed import _EXPRESSION_BY_FACTOR

        candidates = []
        for name, (expr, inputs) in list(_EXPRESSION_BY_FACTOR.items())[:count]:
            candidates.append(FactorCandidate(
                name=f"seed_{name}",
                hypothesis=f"Seed factor from established library: {name}",
                family=name.split("_")[0] if "_" in name else name,
                inputs=inputs,
                expression_dsl=expr,
                expected_holding_period=10,
                complexity_hint="low",
                novelty_rationale="Established factor from seed library",
                generation_engine=self.engine_id,
                generation_trace={"mode": "seed_library", "seed_name": name},
            ))

        return candidates

    def _generate_variants(self, count: int) -> list[FactorCandidate]:
        """生成种子因子的组合变体。"""
        import random

        from ...factor_candidate_seed import _EXPRESSION_BY_FACTOR

        templates = list(_EXPRESSION_BY_FACTOR.items())
        candidates = []

        # 组合模板：A + B, A - B, A * sign(B)
        combinators = [
            ("{a} + {b}", "combined_sum"),
            ("{a} - {b}", "combined_diff"),
            ("({a}) * sign({b})", "conditional_sign"),
            ("zscore({a}, 20) + zscore({b}, 20)", "dual_zscore"),
        ]

        for _ in range(count):
            if len(templates) < 2:
                break
            (name_a, (expr_a, inputs_a)), (name_b, (expr_b, inputs_b)) = random.sample(templates, 2)
            combinator, combo_type = random.choice(combinators)

            combined_expr = combinator.format(a=expr_a, b=expr_b)
            combined_inputs = list(set(inputs_a + inputs_b))

            candidates.append(FactorCandidate(
                name=f"rule_combo_{name_a}_{name_b}_{combo_type}",
                hypothesis=f"Rule-based combination of {name_a} and {name_b}",
                family="custom",
                inputs=combined_inputs,
                expression_dsl=combined_expr,
                expected_holding_period=10,
                complexity_hint="medium",
                novelty_rationale=f"Combinatorial variant: {combo_type}({name_a}, {name_b})",
                generation_engine=self.engine_id,
                generation_trace={
                    "mode": "rule_variant",
                    "parent_a": name_a,
                    "parent_b": name_b,
                    "combinator": combo_type,
                },
            ))

        return candidates

    @staticmethod
    def _dedupe(candidates: list[FactorCandidate]) -> list[FactorCandidate]:
        seen: set[str] = set()
        unique: list[FactorCandidate] = []
        for candidate in candidates:
            key = str(candidate.expression_dsl or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def get_status(self) -> EngineStatus:
        return EngineStatus(
            engine_id=self.engine_id,
            engine_type=self.engine_type,
            enabled=True,
            ready=True,
            last_run_at=self._last_run_at,
            last_error=self._last_error,
            success_count=self._success_count,
            failure_count=self._failure_count,
        )
