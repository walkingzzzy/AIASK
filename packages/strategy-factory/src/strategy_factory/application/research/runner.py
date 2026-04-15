"""Research plane runner for the strategy factory.

P3 goal: make factor research, task planning, local rule generation, and
external autonomy generation observable as one independent research plane that
only outputs candidates and evidence.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any

from .candidate_origin import count_candidate_origins
from ..candidate_contract import apply_resolved_candidate_envelope
from .contracts import build_research_plane_artifact
from ...domain.constants import (
    FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
    is_factory_factor_auto_refresh_enabled,
)
from ...domain.strategy_profile import apply_candidate_strategy_profile
from ..services.readiness_service import resolve_factor_refresh_trigger

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ResearchGenerationResult:
    local_candidates: list[dict[str, Any]] = field(default_factory=list)
    autonomy_candidates: list[dict[str, Any]] = field(default_factory=list)
    generated_candidates: list[dict[str, Any]] = field(default_factory=list)
    local_spawn_report: dict[str, Any] = field(default_factory=dict)
    autonomy_stage: dict[str, Any] = field(default_factory=dict)
    experiments: list[dict[str, Any]] = field(default_factory=list)
    autonomy_error: str | None = None
    candidate_origin_counts: dict[str, int] = field(default_factory=dict)

    @property
    def local_rule_candidate_count(self) -> int:
        return int(self.candidate_origin_counts.get("local_rule") or 0)

    @property
    def external_autonomy_candidate_count(self) -> int:
        return int(self.candidate_origin_counts.get("external_autonomy") or 0)

    @property
    def governed_candidate_activation_count(self) -> int:
        return int(self.candidate_origin_counts.get("governed_candidate_activation") or 0)


class ResearchPlaneRunner:
    """Owns research-plane generation before governance begins."""

    def __init__(self, scheduler: Any, factory_pkg: Any) -> None:
        self._scheduler = scheduler
        self._factory_pkg = factory_pkg

    async def build_factor_research_artifact(
        self,
        factor_gateway: Any,
        db: Any,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        gateway_db = self._scheduler._adapt_gateway_repository(db)
        auto_refresh_enabled = is_factory_factor_auto_refresh_enabled()
        self_heal_refresh_enabled = bool(snapshot.get("_factor_refresh_self_heal"))
        refresh_meta: dict[str, Any] = {
            "auto_refresh_enabled": auto_refresh_enabled,
            "refresh_attempted": False,
            "refresh_status": "not_needed",
            "refresh_trigger": None,
            "refresh_error": None,
            "refreshed_before_build": False,
            "refresh_result": {},
            "refresh_timeout_sec": FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
            "refresh_mode": (
                "auto"
                if auto_refresh_enabled
                else ("self_heal_enabled" if self_heal_refresh_enabled else "manual_disabled")
            ),
        }
        artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
        summary = dict(artifact.get("summary") or {})
        refresh_trigger = resolve_factor_refresh_trigger(artifact, factor_summary=summary)
        refresh = getattr(factor_gateway, "refresh", None)
        self_heal_refresh_allowed = bool(
            refresh_trigger
            and callable(refresh)
            and self_heal_refresh_enabled
            and refresh_trigger in {
                "stale_artifact",
                "seed_fallback_without_governed_pool",
                "scheduler_warmup_missing_governed_pool",
                "governed_pool_missing_after_scheduler_success",
            }
        )
        should_refresh = bool(
            refresh_trigger
            and callable(refresh)
            and (auto_refresh_enabled or self_heal_refresh_allowed)
        )
        if should_refresh:
            refresh_meta["refresh_attempted"] = True
            refresh_meta["refresh_trigger"] = refresh_trigger
            refresh_meta["refresh_mode"] = (
                "auto" if auto_refresh_enabled else "self_heal"
            )
            try:
                refresh_result = refresh()
                if inspect.isawaitable(refresh_result):
                    refresh_result = await asyncio.wait_for(
                        refresh_result,
                        timeout=FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
                    )
                refresh_meta["refresh_status"] = "success"
                refresh_meta["refresh_result"] = self._scheduler._summarize_refresh_result(
                    refresh_result
                )
                refresh_meta["refreshed_before_build"] = True
                artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
            except asyncio.TimeoutError:
                refresh_meta["refresh_status"] = "timeout"
                refresh_meta["refresh_error"] = (
                    f"factor refresh exceeded {FACTORY_FACTOR_REFRESH_TIMEOUT_SEC}s"
                )
            except Exception as exc:
                refresh_meta["refresh_status"] = "failed"
                refresh_meta["refresh_error"] = str(exc)
        elif not auto_refresh_enabled:
            refresh_meta["refresh_status"] = "disabled"
        return self._scheduler._inject_factor_refresh_meta(artifact, refresh_meta)

    def build_research_plane(
        self,
        *,
        snapshot: dict[str, Any],
        readiness: dict[str, Any] | None = None,
        autonomy_stage: dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
        experiments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return build_research_plane_artifact(
            factor_research=snapshot.get("factor_research"),
            readiness=readiness,
            autonomy_stage=autonomy_stage,
            candidates=candidates,
            experiments=experiments,
        )

    async def run_generation(
        self,
        db: Any,
        snapshot: dict[str, Any],
    ) -> ResearchGenerationResult:
        spawner = self._factory_pkg.StrategySpawner()
        local_candidates = list(spawner.spawn(snapshot) or [])
        local_spawn_report = (
            spawner.get_last_report()
            if hasattr(spawner, "get_last_report")
            else {"summary": {"candidate_count": len(local_candidates)}}
        )
        autonomy_stage: dict[str, Any] = {"generated_count": 0}
        autonomy_candidates: list[dict[str, Any]] = []
        experiments: list[dict[str, Any]] = []
        autonomy_error: str | None = None
        try:
            autonomy_batch = await self._scheduler._run_autonomy_batches(db, snapshot)
            autonomy_stage = dict(autonomy_batch.get("stage") or {})
            autonomy_candidates = list(autonomy_batch.get("candidates") or [])
            experiments = list(autonomy_batch.get("experiments") or [])
            self._annotate_autonomy_candidates(autonomy_candidates, autonomy_stage)
        except Exception as exc:
            logger.warning("StrategyFactory: autonomy cycle failed: %s", exc)
            autonomy_error = str(exc)
            autonomy_stage = {"error": autonomy_error, "generated_count": 0}

        profiled_local_candidates = [
            apply_resolved_candidate_envelope(
                apply_candidate_strategy_profile(candidate, snapshot=snapshot)
            )
            for candidate in local_candidates
        ]
        profiled_autonomy_candidates = [
            apply_resolved_candidate_envelope(
                apply_candidate_strategy_profile(candidate, snapshot=snapshot)
            )
            for candidate in autonomy_candidates
        ]
        generated_candidates = [
            *profiled_local_candidates,
            *profiled_autonomy_candidates,
        ]
        return ResearchGenerationResult(
            local_candidates=profiled_local_candidates,
            autonomy_candidates=profiled_autonomy_candidates,
            generated_candidates=generated_candidates,
            local_spawn_report=dict(local_spawn_report or {}),
            autonomy_stage=autonomy_stage,
            experiments=experiments,
            autonomy_error=autonomy_error,
            candidate_origin_counts=count_candidate_origins(generated_candidates),
        )

    @staticmethod
    def _annotate_autonomy_candidates(
        candidates: list[dict[str, Any]],
        autonomy_stage: dict[str, Any],
    ) -> None:
        factory_attempt_count = int(autonomy_stage.get("external_llm_attempt_count") or 0)
        factory_stage_attempt_count = int(
            autonomy_stage.get("external_llm_stage_attempt_count")
            or factory_attempt_count
        )
        factory_network_request_count = int(
            autonomy_stage.get("external_llm_network_request_count") or 0
        )
        factory_compatibility_skip_count = int(
            autonomy_stage.get("external_llm_compatibility_skip_count") or 0
        )
        factory_cooldown_skip_count = int(
            autonomy_stage.get("external_llm_cooldown_skip_count") or 0
        )
        factory_selected_count = int(autonomy_stage.get("external_llm_selected_count") or 0)
        for ai_candidate in list(candidates or []):
            params = dict(ai_candidate.get("params") or {})
            params["factory_global_attempt_count"] = factory_attempt_count
            params["factory_global_selected_count"] = factory_selected_count
            params["factory_attempt_count"] = factory_attempt_count
            params["factory_stage_attempt_count"] = factory_stage_attempt_count
            params["factory_network_request_count"] = factory_network_request_count
            params["factory_compatibility_skip_count"] = factory_compatibility_skip_count
            params["factory_cooldown_skip_count"] = factory_cooldown_skip_count
            params["factory_selected_count"] = factory_selected_count
            ai_candidate["params"] = params


__all__ = [
    "ResearchGenerationResult",
    "ResearchPlaneRunner",
]
