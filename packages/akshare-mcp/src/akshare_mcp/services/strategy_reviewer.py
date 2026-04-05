"""MultiAgentStrategyReviewer — multi-agent committee review with execution-aware scoring."""

from __future__ import annotations

from typing import Any, Optional

from .strategy_spec import StrategySpec


class MultiAgentStrategyReviewer:
    SUPPORTED_TYPES = {
        'momentum',
        'ma_cross',
        'rsi',
        'value_factor',
        'quality_factor',
        'growth_factor',
        'multi_factor',
        'macro_timing',
        'volatility_breakout',
        'gap_fill',
        'mean_reversion_short',
        'sector_rotation',
        'north_capital_track',
        'margin_divergence',
        'dsl_rule',
    }

    @staticmethod
    def _factor_research_alignment(spec: StrategySpec, snapshot: dict) -> tuple[float, dict[str, Any]]:
        factor_research = dict(snapshot.get('factor_research') or {})
        preferred_types = [
            str(item).strip()
            for item in list(factor_research.get('preferred_strategy_types') or [])
            if str(item).strip()
        ]
        top_factor_names = [
            str(item).strip()
            for item in list(
                ((factor_research.get('summary') or {}).get('top_factor_names') or factor_research.get('active_factors') or [])
            )
            if str(item).strip()
        ]
        score_delta = 0.0
        if spec.strategy_type in preferred_types[:2]:
            score_delta += 0.16
        elif spec.strategy_type in preferred_types:
            score_delta += 0.1
        if factor_research and bool(factor_research.get('degraded')):
            score_delta -= 0.04
        return max(min(score_delta, 0.2), -0.08), {
            'preferred_strategy_types': preferred_types[:4],
            'top_factor_names': top_factor_names[:3],
            'artifact_degraded': bool(factor_research.get('degraded')),
            'aligned': spec.strategy_type in preferred_types,
        }

    @classmethod
    def _planner_score(cls, spec: StrategySpec, snapshot: dict) -> tuple[float, dict[str, Any]]:
        fg = int(snapshot.get('fear_greed_index') or 50)
        stype = spec.strategy_type
        base_score = 0.6
        if fg >= 60 and stype in {'momentum', 'ma_cross', 'volatility_breakout', 'north_capital_track'}:
            base_score = 0.9
        elif fg < 45 and stype in {'rsi', 'value_factor', 'quality_factor', 'gap_fill', 'mean_reversion_short'}:
            base_score = 0.85
        elif stype == 'multi_factor':
            base_score = 0.82
        elif stype == 'macro_timing':
            base_score = 0.78
        elif stype == 'sector_rotation':
            base_score = 0.8
        elif stype == 'margin_divergence':
            base_score = 0.77
        elif stype == 'dsl_rule':
            base_score = 0.74
        factor_delta, factor_context = cls._factor_research_alignment(spec, snapshot)
        return max(0.05, min(1.0, round(base_score + factor_delta, 4))), {
            'fear_greed_index': fg,
            **factor_context,
        }

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
            return 0.66
        if 'rl_evolved' in tags:
            return 0.7
        if 'llm_proxy' in tags or 'llm_proxy_fallback' in tags or 'local_rule_v1' in tags:
            return 0.62
        if 'rule' in tags:
            return 0.58
        return 0.55

    @staticmethod
    def _target_symbols(spec: StrategySpec) -> list[str]:
        metadata = dict(spec.metadata or {})
        payloads = [
            metadata.get('target_symbols'),
            metadata.get('stock_pool'),
            ((metadata.get('research_task') or {}).get('target_symbols') if isinstance(metadata.get('research_task'), dict) else None),
            spec.params.get('target_symbols') if isinstance(spec.params, dict) else None,
            spec.params.get('stock_pool') if isinstance(spec.params, dict) else None,
            (((spec.params.get('dsl') or {}).get('metadata') or {}).get('target_symbols') if isinstance(spec.params, dict) else None),
        ]
        codes: list[str] = []
        seen: set[str] = set()
        for payload in payloads:
            values = payload
            if isinstance(values, dict):
                values = values.get('symbols') or values.get('codes') or values.get('target_symbols')
            if not isinstance(values, (list, tuple, set)):
                values = [values] if values not in (None, '') else []
            for item in values:
                code = str(item or '').split('.')[0].strip()
                if code and code not in seen:
                    seen.add(code)
                    codes.append(code)
        return codes[:12]

    @staticmethod
    def _research_task(spec: StrategySpec) -> dict[str, Any]:
        metadata = dict(spec.metadata or {})
        return dict(metadata.get('research_task') or {})

    @classmethod
    def _execution_score(cls, spec: StrategySpec) -> tuple[float, list[str]]:
        metadata = dict(spec.metadata or {})
        execution = dict(metadata.get('execution_assumptions') or {})
        holding_horizon = dict(metadata.get('holding_horizon') or {})
        dsl = dict((spec.params or {}).get('dsl') or {})
        risk_rules = dict(metadata.get('risk_rules') or dsl.get('risk_rules') or (spec.params or {}).get('risk_rules') or {})
        issues: list[str] = []
        score = 0.62 if spec.strategy_type in cls.SUPPORTED_TYPES else 0.0

        if not holding_horizon:
            issues.append('missing_holding_horizon')
            score -= 0.12
        if not risk_rules:
            issues.append('missing_risk_rules')
            score -= 0.16
        if not execution:
            issues.append('missing_execution_assumptions')
            score -= 0.12
        else:
            if not execution.get('tradability_filter'):
                issues.append('tradability_filter_disabled')
                score -= 0.08
            if float(execution.get('slippage_bps') or 0.0) <= 0:
                issues.append('missing_slippage_assumption')
                score -= 0.06
            if not str(execution.get('slippage_model') or '').strip():
                issues.append('missing_slippage_model')
                score -= 0.05
        return max(0.05, min(1.0, round(score, 4))), issues

    @classmethod
    def _capacity_score(cls, spec: StrategySpec) -> tuple[float, list[str]]:
        metadata = dict(spec.metadata or {})
        execution = dict(metadata.get('execution_assumptions') or {})
        portfolio_spec = dict(metadata.get('portfolio_spec') or {})
        target_symbols = cls._target_symbols(spec)
        issues: list[str] = []
        score = 0.64 if spec.strategy_type in cls.SUPPORTED_TYPES else 0.0

        if not portfolio_spec:
            issues.append('missing_portfolio_spec')
            score -= 0.12
        if len(target_symbols) > 8:
            issues.append('target_universe_too_wide')
            score -= 0.08
        if float(execution.get('capacity_participation_rate') or 0.0) > 0.2:
            issues.append('capacity_participation_rate_too_high')
            score -= 0.12
        if float(execution.get('adv_ratio_limit') or 0.0) > 0.25:
            issues.append('adv_ratio_limit_too_high')
            score -= 0.1
        if not str(execution.get('capacity_bucket') or '').strip():
            issues.append('missing_capacity_bucket')
            score -= 0.04
        return max(0.05, min(1.0, round(score, 4))), issues

    @classmethod
    def _task_alignment_score(cls, spec: StrategySpec, snapshot: dict) -> tuple[float, list[str], dict[str, Any]]:
        metadata = dict(spec.metadata or {})
        research_task = cls._research_task(spec)
        preferred_types = [
            str(item).strip().lower()
            for item in list(research_task.get('preferred_strategy_types') or research_task.get('strategy_preferences') or [])
            if str(item).strip()
        ]
        allowed_types = {
            str(item).strip().lower()
            for item in list(research_task.get('allowed_strategy_types') or [])
            if str(item).strip()
        }
        task_symbols = cls._target_symbols(StrategySpec(strategy_type=spec.strategy_type, params=spec.params, metadata={'target_symbols': research_task.get('target_symbols'), 'stock_pool': research_task.get('stock_pool')}))
        candidate_symbols = cls._target_symbols(spec)
        factor_delta, factor_context = cls._factor_research_alignment(spec, snapshot)
        issues: list[str] = []
        score = 0.58 + factor_delta

        if allowed_types and spec.strategy_type not in allowed_types:
            issues.append('outside_allowed_strategy_types')
            score -= 0.25
        elif preferred_types and spec.strategy_type not in preferred_types:
            issues.append('not_in_preferred_strategy_types')
            score -= 0.12

        if task_symbols and candidate_symbols:
            overlap = len(set(task_symbols).intersection(candidate_symbols)) / max(1, len(set(candidate_symbols)))
            if overlap < 0.5:
                issues.append('target_universe_drift')
                score -= 0.14
            elif overlap >= 0.8:
                score += 0.08

        return max(0.05, min(1.0, round(score, 4))), issues, factor_context

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
        planner, planner_context = self._planner_score(spec, snapshot)
        risk = self._risk_score(spec)
        feasibility = self._feasibility_score(spec)
        execution, execution_issues = self._execution_score(spec)
        capacity, capacity_issues = self._capacity_score(spec)
        task_alignment, alignment_issues, alignment_context = self._task_alignment_score(spec, snapshot)
        novelty = self._novelty_score(spec)
        final_score = round(
            planner * 0.24
            + risk * 0.18
            + feasibility * 0.18
            + execution * 0.16
            + capacity * 0.12
            + task_alignment * 0.08
            + novelty * 0.04,
            4,
        )
        decision = 'accept' if final_score >= 0.62 and feasibility > 0 else ('revise' if final_score >= 0.45 and feasibility > 0 else 'reject')
        suggestions: list[str] = []
        if feasibility <= 0:
            suggestions.append('策略类型未注册，拒绝进入自治工厂。')
        if risk < 0.7:
            suggestions.append('参数存在高风险取值，建议收敛阈值与周期。')
        if planner < 0.65:
            suggestions.append('策略与当前市场环境匹配度一般，建议进入观察或微调。')
        if planner_context.get('preferred_strategy_types') and not planner_context.get('aligned'):
            suggestions.append('策略未对齐当前 factor_research 偏好，建议优先验证因子主链推荐类型。')
        if alignment_issues:
            suggestions.append('策略与研究任务或目标池存在偏离，建议先修正 task alignment。')
        if execution_issues:
            suggestions.append('执行假设仍不完整，建议补齐 holding horizon / risk rules / execution assumptions。')
        if capacity_issues:
            suggestions.append('容量与仓位语义不足，建议补齐 position sizing / capacity 假设。')

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
            'execution_score': execution,
            'capacity_score': capacity,
            'task_alignment_score': task_alignment,
            'novelty_score': novelty,
            'final_score': final_score,
            'decision': decision,
            'suggestions': suggestions,
            'planner_context': planner_context,
            'task_alignment_context': alignment_context,
            'alignment_issues': alignment_issues,
            'execution_issues': execution_issues,
            'capacity_issues': capacity_issues,
        }
        if decision == 'reject':
            return None, review
        reviewed.metadata = {
            **dict(reviewed.metadata or {}),
            'committee_review': review,
        }
        return reviewed, review
