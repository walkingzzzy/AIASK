
import random


class RuleStrategyGenerator:
    @staticmethod
    def _factor_research_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
        factor_research = dict(snapshot.get('factor_research') or {})
        summary = dict(factor_research.get('summary') or {})
        return {
            'top_factor_names': list(summary.get('top_factor_names') or factor_research.get('active_factors') or [])[:3],
            'preferred_strategy_types': [
                str(item).strip()
                for item in list(factor_research.get('preferred_strategy_types') or [])
                if str(item).strip()
            ][:4],
            'degraded': bool(factor_research.get('degraded')),
        }

    @classmethod
    def _jitter_params(cls, strategy_type: str, params: dict[str, Any]) -> dict[str, Any]:
        """Add random perturbation to strategy params for differentiation.

        Each call produces a unique param set even for the same strategy type,
        ensuring dedup and backtest cache keys can distinguish candidates.
        """
        jittered = {}
        for key, value in params.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if isinstance(value, int):
                    delta = max(2, int(abs(value) * 0.30 * random.random()))
                    delta = random.randint(-delta, delta)
                    jittered[key] = max(1, value + delta)
                else:
                    factor = 1.0 + (random.random() - 0.5) * 0.40
                    jittered[key] = round(value * factor, 6)
            elif isinstance(value, dict):
                jittered[key] = cls._jitter_params(strategy_type, dict(value))
            else:
                jittered[key] = value
        return jittered

    @classmethod
    def _build_rule_spec(
        cls,
        strategy_type: str,
        *,
        fg: int,
        regime: str,
        source: str,
        factor_summary: dict[str, Any],
    ) -> Optional[StrategySpec]:
        templates: dict[str, dict[str, Any]] = {
            'momentum': {
                'params': {'lookback': 20, 'threshold': 0.013},
                'name': 'AI 动量强化',
                'description': '趋势持续且量价确认阶段偏向动量追随，并过滤假突破。',
            },
            'ma_cross': {
                'params': {'short_period': 8, 'long_period': 34},
                'name': 'AI 均线趋势',
                'description': '趋势确认阶段用自适应均线跨度、横盘过滤和量能确认过滤噪音。',
            },
            'rsi': {
                'params': {
                    'rsi_period': 12,
                    'oversold': 18,
                    'overbought': 64,
                    'regime_filter_enabled': True,
                    'allowed_entry_regimes': ['bear_calm', 'bear_volatile'],
                    'noise_filter_enabled': True,
                    'noise_window': 6,
                    'noise_ceiling': 6.0,
                    'regime_break_threshold': 0.015,
                    'repair_confirmation_enabled': True,
                    'repair_confirmation_window': 6,
                    'repair_confirmation_rebound_pct': 0.008,
                    'repair_confirmation_rsi_reclaim': 24.0,
                    'liquidity_confirmation_enabled': True,
                    'liquidity_window': 8,
                    'liquidity_volume_floor_ratio': 0.8,
                    'structure_confirmation_enabled': True,
                    'structure_window': 4,
                    'structure_close_location_min': 0.55,
                    'structure_body_return_min': 0.0015,
                    'max_active_symbols': 2,
                    'universe_selection_profile': 'repair_liquidity_fit_v1',
                    'mean_reversion_exit_min_hold_bars': 4,
                    'mean_reversion_exit_buffer': -0.002,
                    'max_hold_bars': 6,
                    'adverse_regime_exit_enabled': True,
                    'adverse_exit_regimes': ['range_volatile'],
                    'adverse_noise_ceiling': 6.0,
                },
                'name': 'AI RSI 反转',
                'description': '仅在熊市超跌后的止跌修复阶段参与高精度反转，并过滤高噪声触发。',
            },
            'value_factor': {
                'params': {'lookback': 60, 'buy_quantile': 0.8, 'sell_quantile': 0.2},
                'name': 'AI 价值回归',
                'description': '估值修复阶段偏向价值/反转组合。',
            },
            'quality_factor': {
                'params': {'lookback': 72, 'buy_quantile': 0.82, 'sell_quantile': 0.18},
                'name': 'AI 质量精选',
                'description': '质量因子占优阶段偏向低频再平衡、质量稳定与价格趋势共振筛选。',
            },
            'growth_factor': {
                'params': {'lookback': 40, 'buy_quantile': 0.78, 'sell_quantile': 0.22},
                'name': 'AI 成长加速',
                'description': '成长因子活跃阶段偏向高景气扩张。',
            },
            'multi_factor': {
                'params': {'factor_weights': {'value': 0.4, 'quality': 0.35, 'momentum': 0.25}},
                'name': 'AI 多因子平衡',
                'description': '因子共振时优先使用多因子组合。',
            },
            'macro_timing': {
                'params': {'fear_threshold': 24, 'greed_threshold': 74, 'lookback': 36},
                'name': 'AI 宏观择时',
                'description': '只在恐慌修复与波动稳定共振时参与宏观择时。',
            },
            'event_structure_breakout': {
                'params': {
                    'breakout_window': 12,
                    'breakout_buffer_pct': 0.002,
                    'contraction_window': 5,
                    'contraction_max_range_ratio': 0.06,
                    'volume_window': 8,
                    'breakout_volume_ratio_min': 1.0,
                    'structure_window': 4,
                    'structure_close_location_min': 0.62,
                    'structure_body_return_min': 0.003,
                    'event_impulse_window': 5,
                    'event_impulse_threshold': 0.015,
                    'max_hold_bars': 8,
                    'breakout_failure_close_buffer': -0.012,
                    'adverse_volume_ratio_max': 0.85,
                    'event_prefilter_enabled': True,
                    'event_prefilter_profile': 'announcement_flow_sector_v1',
                    'event_prefilter_min_confirmations': 1,
                },
                'name': 'AI 事件结构突破',
                'description': '只做催化后缩量整理再放量突破的结构延续，优先低频高把握。',
            },
            'volatility_breakout': {
                'params': {'lookback': 20, 'threshold': 0.025},
                'name': 'AI 波动突破',
                'description': '趋势扩张与波动放大阶段偏向波动率突破。',
            },
            'gap_fill': {
                'params': {'gap_threshold': 0.02, 'rsi_period': 5, 'oversold': 24, 'overbought': 58},
                'name': 'AI 跳空回补',
                'description': '情绪错杀或事件冲击后偏向短线回补机会。',
            },
            'mean_reversion_short': {
                'params': {'rsi_period': 6, 'oversold': 26, 'overbought': 62},
                'name': 'AI 短线回归',
                'description': '震荡与防御环境下偏向短周期均值回归。',
            },
            'sector_rotation': {
                'params': {'lookback': 20, 'factor_weights': {'momentum': 0.45, 'quality': 0.30, 'value': 0.25}},
                'name': 'AI 行业轮动',
                'description': '主题扩散与风格切换阶段偏向行业轮动打分。',
            },
            'north_capital_track': {
                'params': {'lookback': 15, 'threshold': 0.015},
                'name': 'AI 北向跟踪',
                'description': '资金偏好明确时偏向价量共振的北向跟踪。',
            },
            'margin_divergence': {
                'params': {
                    'fear_threshold': 43,
                    'greed_threshold': 60,
                    'lookback': 12,
                    'rebound_window': 3,
                    'repair_drawdown_floor': -0.06,
                    'repair_rebound_pct': 0.012,
                    'dryup_window': 3,
                    'dryup_max_ratio': 0.9,
                    'liquidity_window': 8,
                    'entry_volume_floor_ratio': 1.0,
                    'structure_window': 4,
                    'structure_close_location_min': 0.58,
                    'structure_body_return_min': 0.002,
                    'max_hold_bars': 8,
                    'adverse_volume_break_ratio': 0.72,
                    'adverse_close_break_pct': -0.012,
                    'max_active_symbols': 2,
                    'universe_selection_profile': 'liquidity_divergence_fit_v1',
                },
                'name': 'AI 流动性背离修复',
                'description': '只在缩量止跌后出现放量修复和结构转强时参与高精度修复。',
            },
        }
        template = templates.get(strategy_type)
        if template is None:
            return None
        jittered_params = cls._jitter_params(strategy_type, dict(template['params']))
        template_contract = _rule_template_contract(strategy_type)
        semantic_contract_bundle = _build_rule_semantic_contract_bundle(
            strategy_type,
            strategy_name=str(template["name"]),
            description=str(template["description"]),
            source=source,
            regime=regime,
            fg=fg,
            factor_summary=factor_summary,
            trade_plan=dict(template_contract.get("trade_plan") or {}),
            holding_horizon=dict(template_contract.get("holding_horizon") or {}),
            risk_rules=dict(template_contract.get("risk_rules") or {}),
            template_contract=template_contract,
        )
        metadata = {
            'generator_type': 'rule',
            'generation_reason': {
                'source': source,
                'fg': fg,
                'regime': regime,
                'factor_research': factor_summary,
                'template_generation_profile': template_contract.get('template_generation_profile'),
                'rule_template_contract': dict(template_contract.get('rule_template_contract') or {}),
            },
        }
        for key in (
            'holding_horizon',
            'trade_plan',
            'risk_rules',
            'position_sizing',
            'rebalance_rule',
            'portfolio_spec',
            'execution_assumptions',
            'validation_profile',
            'targeting_policy',
            'family_specialization',
            'holding_rationale',
            'alpha_half_life',
            'cost_sensitivity_grid',
            'position_model',
            'capacity_assumption',
            'market_regime_assumption',
            'failure_mode',
            'rule_template_contract',
        ):
            value = template_contract.get(key)
            if value:
                metadata[key] = deepcopy(value)
        for key in (
            "trade_plan",
            "evidence_chain",
            "prediction_contract",
            "confidence_contract",
            "claim_to_trade_plan_map",
        ):
            value = semantic_contract_bundle.get(key)
            if value:
                metadata[key] = deepcopy(value)
        return StrategySpec(
            strategy_type=strategy_type,
            params=jittered_params,
            name=str(template['name']),
            description=str(template['description']),
            tags=['rule', 'factor_research' if source == 'factor_research' else 'fear_greed'],
            metadata=metadata,
        )

    def generate(
        self,
        snapshot: dict,
        limit: int = 2,
        *,
        preferred_types: Optional[list[str]] = None,
    ) -> list[StrategySpec]:
        fg = int(snapshot.get('fear_greed_index') or 50)
        regime = 'greed' if fg >= 60 else ('fear' if fg < 45 else 'neutral')
        factor_summary = self._factor_research_summary(snapshot)
        factor_preferred_types = [
            item for item in factor_summary.get('preferred_strategy_types') or []
            if item in CATEGORY_MINIMUMS
        ]
        requested_types = [
            str(item).strip()
            for item in list(preferred_types or [])
            if str(item).strip() in CATEGORY_MINIMUMS
        ]
        if not factor_preferred_types:
            for factor_name in list(factor_summary.get('top_factor_names') or []):
                for strategy_type in preferred_strategy_types_for_factor(factor_name):
                    if strategy_type in CATEGORY_MINIMUMS and strategy_type not in factor_preferred_types:
                        factor_preferred_types.append(strategy_type)
        regime_defaults = (
            ['momentum', 'volatility_breakout', 'north_capital_track', 'ma_cross', 'quality_factor']
            if regime == 'greed'
            else ['value_factor', 'quality_factor', 'mean_reversion_short', 'gap_fill', 'rsi']
        )
        preferred_anchor = requested_types or factor_preferred_types
        strategy_order = list(dict.fromkeys([*requested_types, *factor_preferred_types, *regime_defaults]))
        specs: list[StrategySpec] = []
        for index, strategy_type in enumerate(strategy_order):
            source = 'factor_research' if index < len(preferred_anchor) and preferred_anchor else 'fear_greed'
            spec = self._build_rule_spec(
                strategy_type,
                fg=fg,
                regime=regime,
                source=source,
                factor_summary=factor_summary,
            )
            if spec is not None:
                specs.append(spec)
        return specs[: max(1, min(int(limit or 2), 10))]

from ._strategy_generators_external import _LLMProxyStrategyGeneratorExternalMixin
from ._strategy_generators_context import _LLMProxyStrategyGeneratorContextMixin
from ._strategy_generators_specs import _LLMProxyStrategyGeneratorSpecsMixin
from ._strategy_generators_generate import _LLMProxyStrategyGeneratorGenerateMixin


class LLMProxyStrategyGenerator(_LLMProxyStrategyGeneratorExternalMixin, _LLMProxyStrategyGeneratorContextMixin, _LLMProxyStrategyGeneratorSpecsMixin, _LLMProxyStrategyGeneratorGenerateMixin):
        def __init__(self):
            self.miner = LLMAlphaMiner()
            self.external_provider = get_strategy_llm_provider()
            self.last_report: dict[str, Any] = {}

        def get_last_report(self) -> dict[str, Any]:
            return dict(self.last_report)
