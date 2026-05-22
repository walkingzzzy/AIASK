
        @classmethod
        def _pipeline_candidate_to_spec(
            cls,
            candidate: dict[str, Any],
            provenance: dict[str, Any],
        ) -> Optional[StrategySpec]:
            """将 pipeline 产出的 candidate dict 转为 StrategySpec。"""
            if not candidate or not isinstance(candidate, dict):
                return None
            original_candidate = candidate
            candidate = _normalize_snapshot_pipeline_candidate(candidate)
            if candidate is None:
                return None
            research_task = normalize_research_task_contract(candidate.get('research_task') or {})
            target_symbols = cls._normalize_code_list(candidate.get('target_symbols'))
            strategy_type = str(candidate.get('strategy_type') or 'dsl_rule').strip() or 'dsl_rule'
            default_validation_focus = 'candidate_target_only' if strategy_type == 'event_structure_breakout' else 'target_plus_representative'
            validation_focus = str((research_task.get('validation_focus') or default_validation_focus)).strip().lower()
            portfolio_spec = dict(candidate.get('portfolio_spec') or {
                'position_assumption': 'equal_weight_proxy' if len(target_symbols) > 1 else 'single_name_full_notional',
                'target_weight_scheme': 'equal_weight' if len(target_symbols) > 1 else 'single_name',
            })
            execution_assumptions = dict(candidate.get('execution_assumptions') or {
                'commission_rate': 0.00025,
                'slippage_bps': 5,
                'tradability_filter': True,
                'slippage_model': 'fixed',
            })
            validation_profile = dict(candidate.get('validation_profile') or {
                'profile': 'event_trade_validation' if validation_focus in {'event_target_only', 'candidate_target_only'} and strategy_type == 'event_structure_breakout' else 'trade_rule_validation',
                'validation_focus': validation_focus,
                'primary_validation_layer': 'target' if validation_focus in {'event_target_only', 'candidate_target_only', 'target_only'} else 'combined',
            })
            precompile_validation = validate_precompile_candidate_contract(
                {
                    **candidate,
                    'research_task': dict(research_task),
                    'strategy_type': strategy_type,
                    'target_symbols': list(target_symbols),
                    'stock_pool': dict(
                        candidate.get('stock_pool')
                        or ({'selection_mode': 'explicit', 'symbols': list(target_symbols)} if target_symbols else {})
                    ),
                    'portfolio_spec': dict(portfolio_spec),
                    'execution_assumptions': dict(execution_assumptions),
                    'validation_profile': dict(validation_profile),
                    'constraint_check': dict(candidate.get('constraint_check') or {}),
                },
                research_task=research_task,
                source='pipeline_staged',
            )
            if not precompile_validation.accepted:
                original_candidate["_generator_precompile_reject_reasons"] = list(precompile_validation.reject_reasons)
                original_candidate["_generator_precompile_validation"] = precompile_validation.to_dict()
                candidate["_generator_precompile_reject_reasons"] = list(precompile_validation.reject_reasons)
                candidate["_generator_precompile_validation"] = precompile_validation.to_dict()
                return None
            target_symbols = list(precompile_validation.target_symbols)
            candidate = {
                **candidate,
                'research_task': dict(research_task),
                'target_symbols': list(target_symbols),
                'stock_pool': dict(precompile_validation.stock_pool),
                'constraint_check': dict(precompile_validation.constraint_check),
            }

            # 尝试通过 DSL 编译获得可执行策略
            compiled: Optional[dict] = None
            dsl = candidate.get('dsl')
            if dsl and isinstance(dsl, dict):
                try:
                    compiled = compile_strategy_blueprint(candidate, tune_for_factory=True)
                except Exception:
                    compiled = None

            if compiled:
                compiled_meta = dict(compiled.get('metadata') or {})
                params = dict(compiled.get('params') or {})
                strategy_type = str(compiled.get('strategy_type') or 'dsl_rule')
                name = str(compiled.get('name') or candidate.get('name') or 'AI Pipeline 策略')
                description = str(compiled.get('description') or candidate.get('description') or '')
            else:
                # DSL 编译失败时，尝试直接用 strategy_type + params
                strategy_type = str(candidate.get('strategy_type') or 'dsl_rule')
                params = dict(candidate.get('params') or {})
                if not params and dsl:
                    params = {'dsl': dsl}
                name = str(candidate.get('name') or 'AI Pipeline 策略')
                description = str(candidate.get('description') or '')
                compiled_meta = {}

            if target_symbols and strategy_type == 'dsl_rule':
                dsl_params = dict(params.get('dsl') or {})
                dsl_metadata = dict(dsl_params.get('metadata') or {})
                dsl_metadata['target_symbols'] = list(target_symbols)
                dsl_params['metadata'] = dsl_metadata
                params['dsl'] = dsl_params

            tags = ['pipeline_staged', *(compiled_meta.get('tags') or []), *(candidate.get('tags') or [])]
            if target_symbols:
                tags.append('targeted_universe')

            metadata = {
                **compiled_meta,
                'generator_type': 'pipeline_staged',
                'hypothesis': str(candidate.get('hypothesis') or candidate.get('description') or ''),
                'holding_horizon': dict(candidate.get('holding_horizon') or {}),
                'trade_plan': dict(candidate.get('trade_plan') or {}),
                'risk_rules': dict(candidate.get('risk_rules') or ((params.get('dsl') or {}).get('risk_rules') or {})),
                'position_sizing': dict(candidate.get('position_sizing') or {}),
                'execution_notes': candidate.get('execution_notes'),
                'rebalance_rule': dict(candidate.get('rebalance_rule') or {'mode': 'signal_rebalance'}),
                'portfolio_spec': dict(precompile_validation.portfolio_spec),
                'execution_assumptions': dict(precompile_validation.execution_assumptions),
                'validation_profile': dict(precompile_validation.validation_profile),
                'targeting_policy': dict(candidate.get('targeting_policy') or {}),
                'constraint_check': dict(precompile_validation.constraint_check),
                'market_regime_assumption': candidate.get('market_regime_assumption'),
                'position_sizing_rationale': candidate.get('position_sizing_rationale'),
                'capacity_bucket': candidate.get('capacity_bucket'),
                'turnover_cost_class': candidate.get('turnover_cost_class'),
                'expected_turnover_band': candidate.get('expected_turnover_band'),
                'economic_semantics_score': candidate.get('economic_semantics_score'),
                'economic_semantics_missing_fields': list(candidate.get('economic_semantics_missing_fields') or []),
                'target_symbols': list(target_symbols),
                'stock_pool': dict(
                    candidate.get('stock_pool')
                    or ((params.get('dsl') or {}).get('metadata') or {}).get('stock_pool')
                    or ({'selection_mode': 'explicit', 'symbols': list(target_symbols)} if target_symbols else {})
                ),
                'selection_logic': list(candidate.get('selection_logic') or []),
                'research_scope': dict(candidate.get('research_scope') or {}),
                'event_context': dict(candidate.get('event_context') or {}),
                'research_task': dict(candidate.get('research_task') or {}),
                'pipeline_provenance': provenance,
                'source_candidate': candidate,
            }

            return StrategySpec(
                strategy_type=strategy_type,
                params=params,
                name=name,
                description=description,
                tags=list(dict.fromkeys(tags)),
                metadata=metadata,
            )
