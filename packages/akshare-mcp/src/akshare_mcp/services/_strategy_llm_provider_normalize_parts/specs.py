
        @classmethod
        def _normalize_candidate_payload(
            cls,
            candidate: Any,
            research_task: Optional[dict[str, Any]] = None,
            *,
            allow_legacy_contract_defaults: bool = False,
        ) -> Optional[dict[str, Any]]:
            if not isinstance(candidate, dict):
                return None
            normalized_task = normalize_research_task_contract(research_task)
            open_dsl_normalized = cls._normalize_open_dsl_candidate_contract(
                candidate,
                normalized_task=normalized_task,
            )
            if open_dsl_normalized is not None:
                candidate = open_dsl_normalized
            task_source = str(normalized_task.get('task_source') or '').strip().lower()
            research_symbols = cls._normalize_code_list(normalized_task.get('target_symbols'), limit=8)
            target_alignment_contract = dict(
                build_target_alignment_contract(normalized_task, candidate=candidate) or {}
            )
            dsl_payload = candidate.get('dsl')
            if not isinstance(dsl_payload, dict):
                dsl_payload = {
                    'version': candidate.get('version'),
                    'timeframe': candidate.get('timeframe'),
                    'entry': candidate.get('entry'),
                    'exit': candidate.get('exit'),
                    'metadata': candidate.get('metadata') or {},
                    'risk_rules': candidate.get('risk_rules') or {},
                }
            if not isinstance(dsl_payload, dict) or not dsl_payload.get('entry'):
                return None
            dsl = dict(dsl_payload)
            metadata = dict(dsl.get('metadata') or {})
            raw_target_symbols = cls._normalize_code_list([
                candidate.get('target_symbols'),
                candidate.get('stock_pool'),
                metadata.get('target_symbols'),
                metadata.get('stock_pool'),
            ], limit=8)
            stock_pool_payload = candidate.get('stock_pool')
            fallback_symbols = cls._normalize_code_list([
                stock_pool_payload,
                metadata.get('stock_pool'),
                research_symbols,
            ], limit=8)
            policy_result = apply_target_symbol_policy(
                raw_target_symbols,
                normalized_task,
                fallback_symbols=fallback_symbols,
                limit=8,
            )
            target_symbols = list(policy_result.get('target_symbols') or [])
            max_candidate_target_symbols = int(target_alignment_contract.get('max_candidate_target_symbols') or 0)
            if max_candidate_target_symbols > 0 and len(target_symbols) > max_candidate_target_symbols:
                target_symbols = list(target_symbols[:max_candidate_target_symbols])
            stock_pool_payload = candidate.get('stock_pool')
            stock_pool_symbols = cls._normalize_code_list([
                stock_pool_payload,
                metadata.get('stock_pool'),
                target_symbols,
            ], limit=8)
            stock_pool: dict[str, Any] = {
                'selection_mode': 'explicit' if stock_pool_symbols else 'screened',
                'symbols': stock_pool_symbols,
            }
            if isinstance(stock_pool_payload, dict):
                selection_mode = str(stock_pool_payload.get('selection_mode') or stock_pool_payload.get('mode') or stock_pool.get('selection_mode') or '').strip()
                if selection_mode:
                    stock_pool['selection_mode'] = selection_mode
                filters = dict(stock_pool_payload.get('filters') or {})
                if filters:
                    stock_pool['filters'] = filters
                rationale = stock_pool_payload.get('rationale')
                if rationale not in (None, ''):
                    stock_pool['rationale'] = str(rationale)
            constraint_check = dict(policy_result.get('constraint_check') or {})
            if (
                constraint_check.get('expansion_applied')
                and stock_pool_symbols
                and not str(stock_pool.get('rationale') or '').strip()
            ):
                stock_pool['rationale'] = str(
                    constraint_check.get('expansion_reason')
                    or constraint_check.get('constraint_violation')
                    or 'expanded_from_candidate_universe'
                )
            overlap_count = len(set(target_symbols).intersection(research_symbols))
            coverage_ratio = round(overlap_count / max(1, len(target_symbols)), 4) if target_symbols else 0.0
            intersection_ratio = (
                round(overlap_count / max(1, len(research_symbols)), 4)
                if research_symbols
                else None
            )
            min_coverage_ratio = float(target_alignment_contract.get('min_coverage_ratio') or 0.0)
            min_intersection_ratio = float(target_alignment_contract.get('min_intersection_ratio') or 0.0)
            min_required_overlap_count = int(target_alignment_contract.get('min_required_overlap_count') or 0)
            alignment_reject_reasons: list[str] = []
            if target_alignment_contract.get('quality_gate_enabled'):
                if not target_symbols and research_symbols:
                    alignment_reject_reasons.append('empty_target_symbols_after_alignment')
                if coverage_ratio < min_coverage_ratio:
                    alignment_reject_reasons.append('coverage_ratio_below_contract')
                if intersection_ratio is not None and intersection_ratio < min_intersection_ratio:
                    alignment_reject_reasons.append('intersection_ratio_below_contract')
                if min_required_overlap_count > 0 and overlap_count < min_required_overlap_count:
                    alignment_reject_reasons.append('target_overlap_count_below_contract')
            constraint_check['target_symbols_after_normalize'] = list(target_symbols)
            constraint_check['coverage_ratio'] = coverage_ratio
            constraint_check['intersection_ratio'] = intersection_ratio
            constraint_check['target_overlap_count'] = int(overlap_count)
            strategy_type = str(candidate.get('strategy_type') or 'dsl_rule').strip() or 'dsl_rule'
            holding_horizon = dict(candidate.get('holding_horizon') or {})
            if not holding_horizon:
                holding_horizon = dict(normalized_task.get('holding_window') or {})
            if not holding_horizon:
                holding_horizon = _default_holding_horizon(strategy_type, normalized_task, task_source)
            risk_rules = dict(candidate.get('risk_rules') or dsl.get('risk_rules') or {})
            if not risk_rules:
                risk_rules = _default_risk_rules(task_source, holding_horizon)
            rebalance_rule = dict(candidate.get('rebalance_rule') or {})
            if not rebalance_rule:
                rebalance_rule = _default_rebalance_rule(strategy_type, task_source)
            trade_plan = candidate.get('trade_plan')
            if isinstance(trade_plan, dict):
                normalized_trade_plan = dict(trade_plan)
            elif trade_plan not in (None, '', [], {}):
                normalized_trade_plan = {'summary': str(trade_plan)}
            else:
                normalized_trade_plan = _default_trade_plan(strategy_type, task_source)
            position_sizing = candidate.get('position_sizing')
            if isinstance(position_sizing, dict):
                normalized_position_sizing = dict(position_sizing)
            elif position_sizing not in (None, '', [], {}):
                normalized_position_sizing = {'summary': str(position_sizing)}
            else:
                normalized_position_sizing = _default_position_sizing(target_symbols)
            if allow_legacy_contract_defaults:
                portfolio_spec = dict(candidate.get('portfolio_spec') or {})
                if not cls._has_required_contract_keys(portfolio_spec, required_keys=cls._LEGACY_PORTFOLIO_REQUIRED_KEYS):
                    portfolio_spec = {
                        'position_assumption': 'single_name_full_notional' if len(target_symbols) <= 1 else 'equal_weight_proxy',
                        'target_weight_scheme': 'single_name' if len(target_symbols) <= 1 else 'equal_weight',
                    }
                execution_assumptions = dict(candidate.get('execution_assumptions') or {})
                if not cls._has_required_contract_keys(execution_assumptions, required_keys=cls._LEGACY_EXECUTION_REQUIRED_KEYS):
                    execution_assumptions = {
                        'commission_rate': 0.00025,
                        'slippage_bps': 5,
                        'tradability_filter': True,
                        'slippage_model': 'fixed',
                    }
                validation_profile = cls._canonicalize_validation_profile(
                    candidate,
                    strategy_type=strategy_type,
                    normalized_task=normalized_task,
                    validation_profile=candidate.get('validation_profile'),
                )
                validation_profile = cls._merge_precision_preferences(
                    validation_profile,
                    candidate=candidate,
                    normalized_task=normalized_task,
                )
            else:
                portfolio_spec, portfolio_reject_reasons = cls._require_explicit_contract_dict(
                    candidate,
                    'portfolio_spec',
                    required_keys=('position_assumption', 'target_weight_scheme'),
                )
                execution_assumptions, execution_reject_reasons = cls._require_explicit_contract_dict(
                    candidate,
                    'execution_assumptions',
                    required_keys=('commission_rate', 'slippage_bps', 'tradability_filter', 'slippage_model'),
                )
                validation_profile, validation_reject_reasons = cls._require_explicit_contract_dict(
                    candidate,
                    'validation_profile',
                    required_keys=('profile', 'validation_focus', 'primary_validation_layer'),
                )
                explicit_contract_reject_reasons = [
                    *portfolio_reject_reasons,
                    *execution_reject_reasons,
                    *validation_reject_reasons,
                ]
                if explicit_contract_reject_reasons:
                    candidate["_normalize_reject_reasons"] = list(dict.fromkeys(explicit_contract_reject_reasons))
                    return None
            validation = validate_precompile_candidate_contract(
                {
                    **candidate,
                    'research_task': dict(normalized_task),
                    'strategy_type': strategy_type,
                    'target_symbols': list(target_symbols),
                    'stock_pool': dict(stock_pool),
                    'constraint_check': dict(constraint_check),
                    'holding_horizon': dict(holding_horizon),
                    'trade_plan': dict(normalized_trade_plan),
                    'risk_rules': dict(risk_rules),
                    'position_sizing': dict(normalized_position_sizing),
                    'rebalance_rule': dict(rebalance_rule),
                    'portfolio_spec': dict(portfolio_spec),
                    'execution_assumptions': dict(execution_assumptions),
                    'validation_profile': dict(validation_profile),
                },
                research_task=normalized_task,
                source='external_llm',
            )
            constraint_check = dict(validation.constraint_check)
            if not validation.accepted:
                candidate["_normalize_reject_reasons"] = list(validation.reject_reasons)
                candidate["_normalize_precompile_validation"] = validation.to_dict()
                return None
            portfolio_spec = dict(validation.portfolio_spec or portfolio_spec)
            execution_assumptions = dict(validation.execution_assumptions or execution_assumptions)
            validation_profile = dict(validation.validation_profile or validation_profile)
            metadata['target_symbols'] = list(target_symbols)
            metadata['stock_pool'] = stock_pool
            metadata['constraint_check'] = constraint_check
            targeting_policy = cls._normalize_targeting_policy_payload(
                metadata.get('targeting_policy'),
                fallback=_default_targeting_policy(normalized_task),
            )
            metadata['targeting_policy'] = targeting_policy
            metadata['target_alignment_contract'] = dict(target_alignment_contract)
            dsl['metadata'] = metadata
            dsl = cls._sanitize_dsl_for_candidate(dsl)
            tags = candidate.get('tags') or []
            if not isinstance(tags, list):
                tags = [tags]
            hypothesis = str(
                candidate.get('hypothesis')
                or candidate.get('rationale')
                or candidate.get('description')
                or ''
            ).strip()
            dsl['risk_rules'] = dict(risk_rules)
            execution_notes = candidate.get('execution_notes')
            if execution_notes in (None, '', [], {}):
                normalized_execution_notes = 'prefer liquid session execution with tradability filter'
            elif isinstance(execution_notes, list):
                normalized_execution_notes = [str(item) for item in execution_notes[:3] if str(item or '').strip()]
            else:
                normalized_execution_notes = str(execution_notes)
            metadata['portfolio_spec'] = dict(portfolio_spec)
            metadata['execution_assumptions'] = dict(execution_assumptions)
            metadata['validation_profile'] = dict(validation_profile)
            metadata['targeting_policy'] = dict(targeting_policy)
            metadata['constraint_check'] = dict(constraint_check)
            dsl['metadata'] = metadata
            normalized_params = {
                'dsl': dict(dsl),
                'target_symbols': list(target_symbols),
                'stock_pool': dict(stock_pool),
                'research_task': dict(normalized_task),
                'holding_horizon': dict(holding_horizon),
                'trade_plan': dict(normalized_trade_plan),
                'risk_rules': dict(risk_rules),
                'position_sizing': dict(normalized_position_sizing),
                'execution_notes': normalized_execution_notes,
                'rebalance_rule': dict(rebalance_rule),
                'portfolio_spec': dict(portfolio_spec),
                'execution_assumptions': dict(execution_assumptions),
                'validation_profile': dict(validation_profile),
                'targeting_policy': dict(targeting_policy),
                'constraint_check': dict(constraint_check),
            }
            for key in (
                'evidence_chain',
                'prediction_contract',
                'evidence_alignment_audit',
            ):
                value = candidate.get(key)
                if isinstance(value, dict) and value:
                    normalized_params[key] = dict(value)
            for key in ('legacy_semantic_contract', 'contradiction_count', 'proxy_dependency_score'):
                value = candidate.get(key)
                if value not in (None, '', [], {}):
                    normalized_params[key] = value
            normalized: dict[str, Any] = {
                'name': str(candidate.get('name') or '外部 AI 候选策略'),
                'strategy_type': strategy_type,
                'params': normalized_params,
                'target_symbols': list(target_symbols),
                'stock_pool': stock_pool,
                'dsl': dsl,
                'hypothesis': hypothesis,
                'holding_horizon': holding_horizon,
                'trade_plan': normalized_trade_plan,
                'risk_rules': dict(risk_rules),
                'position_sizing': normalized_position_sizing,
                'execution_notes': normalized_execution_notes,
                'rebalance_rule': rebalance_rule,
                'portfolio_spec': portfolio_spec,
                'execution_assumptions': execution_assumptions,
                'validation_profile': validation_profile,
                'targeting_policy': dict(targeting_policy),
                'target_alignment_contract': dict(target_alignment_contract),
                'constraint_check': constraint_check,
                'tags': [str(item) for item in [*tags, 'target_contract_enforced'] if str(item or '').strip()][:8],
            }
            for key in (
                'evidence_chain',
                'prediction_contract',
                'evidence_alignment_audit',
            ):
                value = candidate.get(key)
                if isinstance(value, dict) and value:
                    normalized[key] = dict(value)
            for key in ('legacy_semantic_contract', 'contradiction_count', 'proxy_dependency_score'):
                value = candidate.get(key)
                if value not in (None, '', [], {}):
                    normalized[key] = value
            if allow_legacy_contract_defaults:
                normalized["_legacy_contract_defaults_applied"] = True
            if isinstance(candidate.get('hypothesis_artifact'), dict) and candidate.get('hypothesis_artifact'):
                normalized['hypothesis_artifact'] = dict(candidate.get('hypothesis_artifact') or {})
            elif isinstance(candidate.get('hypothesis_structured'), dict) and candidate.get('hypothesis_structured'):
                normalized['hypothesis_artifact'] = dict(candidate.get('hypothesis_structured') or {})
            for key in (
                'holding_rationale',
                'alpha_half_life',
                'cost_sensitivity_grid',
                'position_model',
                'capacity_assumption',
                'market_regime_assumption',
                'economic_semantics_score',
                'economic_semantics_missing_fields',
                'validation_focus',
                'hypothesis_artifact_id',
            ):
                if candidate.get(key) not in (None, '', [], {}):
                    normalized[key] = candidate.get(key)
            description = candidate.get('description')
            if description not in (None, ''):
                normalized['description'] = str(description)
            rationale = candidate.get('rationale')
            if rationale not in (None, ''):
                normalized['rationale'] = str(rationale)
            selection_logic = candidate.get('selection_logic')
            if selection_logic not in (None, '', [], {}):
                if isinstance(selection_logic, list):
                    normalized['selection_logic'] = [str(item) for item in selection_logic[:4]]
                else:
                    normalized['selection_logic'] = [str(selection_logic)]
            synthesized_confidence_contract = synthesize_confidence_contract(normalized)
            normalized['confidence_contract'] = dict(synthesized_confidence_contract)
            normalized_params['confidence_contract'] = dict(synthesized_confidence_contract)
            return normalized

        @classmethod
        def _minimal_output_example(cls, target_symbols: list[str]) -> dict[str, Any]:
            symbols = cls._normalize_code_list(target_symbols, limit=2)
            if not symbols:
                symbols = ['000300']
            stock_pool = {
                'selection_mode': 'explicit',
                'symbols': list(symbols),
            }
            return {
                'candidates': [{
                    'name': 'single_stock_trend_follow',
                    'strategy_type': 'dsl_rule',
                    'hypothesis': '目标股票在中短期趋势延续中更容易产生顺势机会。',
                    'hypothesis_artifact': {
                        'alpha_hypothesis': '目标股票在中短期趋势延续中更容易产生顺势机会。',
                        'failure_mode': {
                            'primary_failure_mode': 'trend_break_or_time_stop',
                            'stop_loss_pct': 0.08,
                        },
                        'target_universe_hypothesis': {
                            'target_symbols': list(symbols),
                            'stock_pool': stock_pool,
                            'target_symbol_policy': 'prefer_intersection',
                        },
                        'family_hint': 'dsl_rule',
                        'holding_rationale': '趋势确认后持有 10 天以内，直到趋势衰减或时间止损。',
                        'alpha_half_life': 10,
                        'cost_sensitivity_grid': {
                            'base_case': {
                                'commission_rate': 0.00025,
                                'slippage_bps': 5,
                            },
                        },
                        'position_model': 'single_name',
                        'capacity_assumption': {
                            'max_position_pct': 1.0,
                            'symbol_count': len(symbols),
                        },
                        'objective_profile': 'high_precision',
                        'trade_density_preference': 'low',
                        'entry_selectivity': 'strict',
                        'regime_required': True,
                        'cost_robust_required': True,
                        'market_regime_assumption': {
                            'summary': '趋势延续需要市场流动性正常且目标股仍保持相对强势。',
                            'preferred_regime': 'trend_expansion',
                            'avoid_regime': 'range_bound_chop',
                        },
                        'validation_focus': 'target_plus_representative',
                    },
                    'holding_horizon': {'max_days': 10},
                    'evidence_chain': {
                        'evidences': [
                            {
                                'evidence_id': 'ev_1',
                                'source_type': 'price_action',
                                'direction': 'up',
                                'summary': '10 日均线向上，收盘价重新站回均线之上。',
                                'proxy_only': False,
                                'target_symbols': list(symbols),
                            },
                            {
                                'evidence_id': 'ev_2',
                                'source_type': 'volume',
                                'direction': 'up',
                                'summary': '突破伴随量能放大，volume_ratio 保持在 1.2 以上。',
                                'proxy_only': False,
                                'target_symbols': list(symbols),
                            },
                        ],
                    },
                    'prediction_contract': {
                        'claims': [
                            {
                                'claim_id': 'claim_1',
                                'expected_move': 'up',
                                'expected_horizon': 10,
                                'evidence_ids': ['ev_1', 'ev_2'],
                            },
                        ],
                    },
                    'trade_plan': {
                        'entry_bias': 'trend_follow',
                        'exit_bias': 'signal_or_time_stop',
                        'entry': {
                            'node_id': 'entry_1',
                            'claim_ids': ['claim_1'],
                            'evidence_ids': ['ev_1', 'ev_2'],
                        },
                        'exit': {
                            'node_id': 'exit_1',
                            'claim_ids': ['claim_1'],
                        },
                    },
                    'risk_rules': {'stop_loss_pct': 0.08, 'take_profit_pct': 0.18, 'max_holding_days': 10},
                    'position_sizing': {'mode': 'single_name', 'position_assumption': 'single_name_full_notional'},
                    'execution_notes': 'prefer liquid session execution',
                    'rebalance_rule': {'mode': 'signal_rebalance'},
                    'portfolio_spec': {'position_assumption': 'single_name_full_notional', 'target_weight_scheme': 'single_name'},
                    'execution_assumptions': {'commission_rate': 0.00025, 'slippage_bps': 5, 'tradability_filter': True, 'slippage_model': 'fixed'},
                    'validation_profile': {
                        'profile': 'trade_rule_validation',
                        'validation_focus': 'target_plus_representative',
                        'primary_validation_layer': 'target',
                        'objective_profile': 'high_precision',
                        'trade_density_preference': 'low',
                        'entry_selectivity': 'strict',
                        'regime_required': True,
                        'cost_robust_required': True,
                    },
                    'target_symbols': list(symbols),
                    'stock_pool': stock_pool,
                    'dsl': {
                        'version': '1.0',
                        'timeframe': 'daily',
                        'entry': {
                            'trade_plan_node_id': 'entry_1',
                            'any': [{
                                'op': 'cross_above',
                                'left': {'field': 'close'},
                                'right': {'indicator': 'sma', 'field': 'close', 'window': 10},
                            }],
                        },
                        'exit': {
                            'trade_plan_node_id': 'exit_1',
                            'any': [{
                                'op': 'cross_below',
                                'left': {'field': 'close'},
                                'right': {'indicator': 'sma', 'field': 'close', 'window': 10},
                            }],
                        },
                        'metadata': {
                            'target_symbols': list(symbols),
                            'stock_pool': stock_pool,
                        },
                    },
                    'tags': ['external_llm', 'daily_dsl'],
                }],
            }

        @classmethod
        def _sanitize_expr_for_candidate(cls, expr: Any) -> dict[str, Any]:
            if not isinstance(expr, dict):
                return dict(expr or {}) if isinstance(expr, dict) else {}
            payload = dict(expr)
            indicator = str(payload.get('indicator') or '').strip().lower()
            if indicator:
                field = str(payload.get('field') or 'close').strip().lower() or 'close'
                if field not in {'open', 'high', 'low', 'close', 'volume'}:
                    field = 'close'
                payload['field'] = field
            field = str(payload.get('field') or '').strip().lower()
            if field in {'open', 'high', 'low', 'close', 'volume'}:
                payload['field'] = field
            return payload
