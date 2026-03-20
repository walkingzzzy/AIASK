"""Supporting services for strategy autonomy orchestration."""

from __future__ import annotations

import json
import time
from datetime import date
from typing import Any, Optional
from uuid import uuid4

from strategy_factory import extract_event_context as _extract_event_context

from .artifact_registry import register_experiment
from .strategy_generators import LLMProxyStrategyGenerator, RuleStrategyGenerator
from .strategy_optimizer import BanditParameterOptimizer
from .strategy_reviewer import MultiAgentStrategyReviewer
from .strategy_spec import StrategySpec


class CandidateGenerationService:
    def __init__(
        self,
        *,
        rule_generator: Optional[RuleStrategyGenerator] = None,
        llm_generator: Optional[LLMProxyStrategyGenerator] = None,
        optimizer: Optional[BanditParameterOptimizer] = None,
    ):
        self.rule_generator = rule_generator or RuleStrategyGenerator()
        self.llm_generator = llm_generator or LLMProxyStrategyGenerator()
        self.optimizer = optimizer or BanditParameterOptimizer()

    async def select_parents(self, db, parent_strategy_id: Optional[str] = None) -> list[dict]:
        if parent_strategy_id:
            strategy = await db.get_strategy(parent_strategy_id)
            return [strategy] if strategy else []
        parents = []
        for status in ("incubating", "listed"):
            parents.extend(await db.list_strategies(status, limit=5))
        return parents[:3]

    async def build_shared_generation_context(
        self,
        db,
        *,
        snapshot: dict,
        parent_strategy_id: Optional[str] = None,
    ) -> dict[str, Any]:
        parents = await self.select_parents(db, parent_strategy_id=parent_strategy_id)
        history_summary = await self.llm_generator._recent_experiments(db, parent_strategies=parents)
        research_context = await self.llm_generator.build_shared_research_context(
            db,
            snapshot=snapshot,
            parent_strategies=parents,
            history_summary=history_summary,
        )
        return {
            "parent_strategies": parents,
            "history_summary": history_summary,
            "research_context": research_context,
        }

    async def generate(
        self,
        db,
        *,
        snapshot: dict,
        limit: int,
        research_task: dict[str, Any],
        parent_strategy_id: Optional[str] = None,
    ) -> dict:
        shared_generation_context = dict(snapshot.get("_shared_generation_context") or {})
        parents = [dict(item or {}) for item in list(shared_generation_context.get("parent_strategies") or [])]
        if parent_strategy_id:
            parents = await self.select_parents(db, parent_strategy_id=parent_strategy_id)
        elif not parents:
            parents = await self.select_parents(db, parent_strategy_id=parent_strategy_id)
        task_preferences = list(research_task.get("strategy_preferences") or [])
        rule_limit = max(0, limit // 3) if research_task else max(1, limit // 2 or 1)
        rule_specs = self.rule_generator.generate(snapshot, limit=rule_limit) if rule_limit > 0 else []
        if task_preferences:
            rule_specs = [spec for spec in rule_specs if spec.strategy_type in set(task_preferences)] or rule_specs
        llm_specs = await self.llm_generator.generate(
            db,
            limit=max(1, limit),
            snapshot=snapshot,
            parent_strategies=parents,
            research_task=research_task,
        )
        llm_report = self.llm_generator.get_last_report() if hasattr(self.llm_generator, "get_last_report") else {}
        evolved_specs: list[StrategySpec] = []
        for parent in parents[:2]:
            evolved_specs.extend(await self.optimizer.evolve(db, parent, limit=2))

        merged_specs: list[StrategySpec] = []
        seen = set()
        for spec in [*rule_specs, *llm_specs, *evolved_specs]:
            if research_task and not dict(spec.metadata or {}).get("research_task"):
                spec.metadata = {**dict(spec.metadata or {}), "research_task": research_task}
            key = (spec.strategy_type, json.dumps(spec.params or {}, sort_keys=True, ensure_ascii=False, default=str))
            if key in seen:
                continue
            seen.add(key)
            merged_specs.append(spec)
            if len(merged_specs) >= max(1, min(int(limit or 3), 10)):
                break

        return {
            "parents": parents,
            "rule_specs": rule_specs,
            "llm_specs": llm_specs,
            "evolved_specs": evolved_specs,
            "merged_specs": merged_specs,
            "llm_report": llm_report,
        }


class CommitteeReviewService:
    def __init__(self, *, reviewer: Optional[MultiAgentStrategyReviewer] = None):
        self.reviewer = reviewer or MultiAgentStrategyReviewer()

    @staticmethod
    def attach_lineage(
        spec: StrategySpec,
        *,
        parent_strategy_id: Optional[str],
        task_run_id: Optional[int],
        review_rank: Optional[int] = None,
        is_champion: bool = False,
    ) -> StrategySpec:
        metadata = dict(spec.metadata or {})
        if parent_strategy_id and not metadata.get("parent_strategy_id"):
            metadata["parent_strategy_id"] = parent_strategy_id
        if task_run_id is not None:
            metadata["task_run_id"] = task_run_id
        committee_review = dict(metadata.get("committee_review") or {})
        if review_rank is not None:
            committee_review["rank"] = int(review_rank)
        if is_champion:
            committee_review["is_champion"] = True
        elif review_rank is not None:
            committee_review.setdefault("is_champion", False)
        if committee_review:
            metadata["committee_review"] = committee_review
        spec.metadata = metadata
        return spec

    @staticmethod
    def review_score(spec: StrategySpec) -> float:
        review = dict((spec.metadata or {}).get("committee_review") or {})
        value = review.get("final_score")
        try:
            return float(value)
        except Exception:
            return 0.0

    def review_candidates(
        self,
        specs: list[StrategySpec],
        *,
        snapshot: dict,
        parent_strategy_id: Optional[str],
        task_run_id: Optional[int],
    ) -> dict:
        reviewed_specs: list[StrategySpec] = []
        committee_reviews: list[dict[str, Any]] = []
        rejected_count = 0
        for spec in list(specs or []):
            reviewed_spec, review = self.reviewer.review(spec, snapshot)
            committee_reviews.append({
                "strategy_type": spec.strategy_type,
                "name": spec.name,
                **review,
            })
            if reviewed_spec is None:
                rejected_count += 1
                continue
            reviewed_specs.append(
                self.attach_lineage(
                    reviewed_spec,
                    parent_strategy_id=parent_strategy_id,
                    task_run_id=task_run_id,
                )
            )

        reviewed_specs.sort(key=self.review_score, reverse=True)
        for rank, spec in enumerate(reviewed_specs, 1):
            self.attach_lineage(
                spec,
                parent_strategy_id=parent_strategy_id,
                task_run_id=task_run_id,
                review_rank=rank,
                is_champion=rank == 1,
            )
        return {
            "reviewed_specs": reviewed_specs,
            "committee_reviews": committee_reviews,
            "rejected_count": rejected_count,
        }


class ExperimentRecorder:
    async def record_experiment(self, db, spec: StrategySpec, source: str, snapshot: dict, task_run: dict) -> dict:
        experiment_id = f"exp_{int(time.time())}_{uuid4().hex[:8]}"
        hypothesis = spec.description or f"{source}:{spec.strategy_type}"
        artifact = register_experiment({
            "experiment_id": experiment_id,
            "hypothesis": hypothesis,
            "method": spec.metadata.get("generator_type") or source,
            "parameters": spec.params,
            "status": "running",
            "tags": spec.tags,
            "conclusion": "",
        })
        parent_strategy_id = spec.metadata.get("parent_strategy_id")
        prompt_payload = spec.metadata.get("llm_prompt")
        research_task = dict(spec.metadata.get("research_task") or {})
        event_context = dict(spec.metadata.get("event_context") or {}) or _extract_event_context(research_task)
        return await db.save_strategy_generation_experiment({
            "experiment_id": experiment_id,
            "strategy_id": parent_strategy_id,
            "parent_strategy_id": parent_strategy_id,
            "generated_strategy_id": spec.metadata.get("generated_strategy_id"),
            "task_run_id": task_run.get("id"),
            "source": source,
            "generator_type": spec.metadata.get("generator_type") or source,
            "optimizer_type": spec.metadata.get("optimizer_type"),
            "status": "generated",
            "hypothesis": hypothesis,
            "prompt": (str(prompt_payload) if prompt_payload is not None else str(snapshot.get("date") or date.today())),
            "parameters": spec.params,
            "strategy_spec": {
                "strategy_type": spec.strategy_type,
                "name": spec.name,
                "description": spec.description,
                "tags": spec.tags,
                "params": spec.params,
                "target_symbols": spec.metadata.get("target_symbols") or [],
                "stock_pool": spec.metadata.get("stock_pool") or {},
                "selection_logic": spec.metadata.get("selection_logic") or [],
                "research_task": research_task,
                "event_context": event_context,
            },
            "evaluation": {
                "source": source,
                "task_run_id": task_run.get("id"),
                "generation_reason": spec.metadata.get("generation_reason") or {},
                "committee_review": spec.metadata.get("committee_review") or {},
                "llm_analysis": spec.metadata.get("llm_analysis") or {},
                "llm_research_context": spec.metadata.get("llm_research_context") or {},
                "llm_response": spec.metadata.get("llm_response") or {},
                "target_symbols": spec.metadata.get("target_symbols") or [],
                "stock_pool": spec.metadata.get("stock_pool") or {},
                "selection_logic": spec.metadata.get("selection_logic") or [],
                "research_scope": spec.metadata.get("research_scope") or {},
                "research_task": research_task,
                "event_context": event_context,
            },
            "result": {},
            "parent_experiment_id": None,
            "artifact_id": artifact.get("artifact_id"),
        })

    async def record_candidates(self, db, specs: list[StrategySpec], *, source: str, snapshot: dict, task_run: dict) -> dict:
        experiments = []
        candidates = []
        champion = None
        for spec in list(specs or []):
            experiment = await self.record_experiment(db, spec, source, snapshot, task_run)
            experiments.append(experiment)
            candidate = spec.to_candidate(source, experiment["experiment_id"])
            candidates.append(candidate)
            if champion is None:
                committee_review = dict((experiment.get("evaluation") or {}).get("committee_review") or {})
                champion = {
                    "experiment_id": experiment.get("experiment_id"),
                    "strategy_type": spec.strategy_type,
                    "name": spec.name,
                    "final_score": committee_review.get("final_score"),
                    "decision": committee_review.get("decision"),
                    "parent_strategy_id": experiment.get("parent_strategy_id") or experiment.get("strategy_id"),
                }
        return {
            "experiments": experiments,
            "candidates": candidates,
            "champion": champion,
        }

    async def apply_submission_results(self, db, experiments: list[dict], submit_result: Optional[dict]) -> dict:
        payload = dict(submit_result or {})
        submission_items = list(payload.get("items") or payload.get("strategies") or [])
        by_experiment = {item.get("experiment_id"): item for item in submission_items}
        updated_experiments = []
        for experiment in list(experiments or []):
            item = by_experiment.get(experiment.get("experiment_id")) or {}
            evaluation = dict(experiment.get("evaluation") or {})
            evaluation["submission_result"] = item
            updated = await db.save_strategy_generation_experiment({
                **experiment,
                "strategy_id": experiment.get("parent_strategy_id") or experiment.get("strategy_id"),
                "generated_strategy_id": item.get("strategy_id") or experiment.get("generated_strategy_id"),
                "status": "accepted" if item.get("passed") else "rejected",
                "evaluation": evaluation,
                "result": item,
            })
            updated_experiments.append(updated)
        return {
            "experiments": updated_experiments,
            "items_by_experiment": by_experiment,
        }
