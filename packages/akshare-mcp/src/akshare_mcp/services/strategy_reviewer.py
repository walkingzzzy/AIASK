"""MultiAgentStrategyReviewer — multi-agent committee review (planner/risk/feasibility/novelty)."""

from __future__ import annotations

from typing import Any, Optional

from .strategy_spec import StrategySpec


class MultiAgentStrategyReviewer:
    SUPPORTED_TYPES = {'momentum', 'ma_cross', 'rsi', 'value_factor', 'quality_factor', 'growth_factor', 'multi_factor', 'macro_timing', 'dsl_rule'}

    @staticmethod
    def _planner_score(spec: StrategySpec, snapshot: dict) -> float:
        fg = int(snapshot.get('fear_greed_index') or 50)
        stype = spec.strategy_type
        if fg >= 60 and stype in {'momentum', 'ma_cross'}:
            return 0.9
        if fg < 45 and stype in {'rsi', 'value_factor', 'quality_factor'}:
            return 0.85
        if stype == 'multi_factor':
            return 0.82
        if stype == 'macro_timing':
            return 0.78
        if stype == 'dsl_rule':
            return 0.74
        return 0.6

    @staticmethod
    def _risk_score(spec: StrategySpec) -> float:
        params = dict(spec.params or {})
        penalty = 0.0
        for key, value in params.items():
            if not isinstance(value, (int, float)):
                continue
            lowered = str(key).lower()
            if 'threshold' in lowered and float(value) > 0.05:
                penalty += 0.25
            if 'period' in lowered and float(value) < 3:
                penalty += 0.15
            if 'lookback' in lowered and float(value) < 5:
                penalty += 0.2
        return max(0.05, 1.0 - penalty)

    @staticmethod
    def _feasibility_score(spec: StrategySpec) -> float:
        return 1.0 if spec.strategy_type in MultiAgentStrategyReviewer.SUPPORTED_TYPES else 0.0

    @staticmethod
    def _novelty_score(spec: StrategySpec) -> float:
        tags = set(spec.tags or [])
        if 'external_llm' in tags:
            return 0.9
        if 'rl_evolved' in tags:
            return 0.82
        if 'llm_proxy' in tags or 'llm_proxy_fallback' in tags or 'local_rule_v1' in tags:
            return 0.76
        if 'rule' in tags:
            return 0.62
        return 0.55

    @staticmethod
    def _revise_params(params: dict[str, Any]) -> dict[str, Any]:
        revised: dict[str, Any] = {}
        for key, value in (params or {}).items():
            if isinstance(value, bool):
                revised[key] = value
                continue
            if isinstance(value, int):
                lowered = str(key).lower()
                if 'period' in lowered or 'lookback' in lowered:
                    revised[key] = max(3, min(value, 120))
                else:
                    revised[key] = value
                continue
            if isinstance(value, float):
                lowered = str(key).lower()
                if 'threshold' in lowered:
                    revised[key] = round(min(max(value, 0.003), 0.03), 6)
                else:
                    revised[key] = round(value, 6)
                continue
            revised[key] = value
        return revised

    def review(self, spec: StrategySpec, snapshot: dict) -> tuple[Optional[StrategySpec], dict[str, Any]]:
        planner = self._planner_score(spec, snapshot)
        risk = self._risk_score(spec)
        feasibility = self._feasibility_score(spec)
        novelty = self._novelty_score(spec)
        final_score = round(planner * 0.35 + risk * 0.25 + feasibility * 0.25 + novelty * 0.15, 4)
        decision = 'accept' if final_score >= 0.62 and feasibility > 0 else ('revise' if final_score >= 0.45 and feasibility > 0 else 'reject')
        suggestions: list[str] = []
        if feasibility <= 0:
            suggestions.append('策略类型未注册，拒绝进入自治工厂。')
        if risk < 0.7:
            suggestions.append('参数存在高风险取值，建议收敛阈值与周期。')
        if planner < 0.65:
            suggestions.append('策略与当前市场环境匹配度一般，建议进入观察或微调。')

        reviewed = spec
        if decision == 'revise':
            reviewed = StrategySpec(
                strategy_type=spec.strategy_type,
                params=self._revise_params(spec.params),
                name=spec.name,
                description=spec.description,
                tags=list(dict.fromkeys([*(spec.tags or []), 'committee_revised'])),
                metadata=dict(spec.metadata or {}),
            )
        review = {
            'planner_score': planner,
            'risk_score': risk,
            'feasibility_score': feasibility,
            'novelty_score': novelty,
            'final_score': final_score,
            'decision': decision,
            'suggestions': suggestions,
        }
        if decision == 'reject':
            return None, review
        reviewed.metadata = {
            **dict(reviewed.metadata or {}),
            'committee_review': review,
        }
        return reviewed, review
