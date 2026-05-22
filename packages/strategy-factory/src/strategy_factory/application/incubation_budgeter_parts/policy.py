    @classmethod
    def _candidate_feedback(
        cls,
        candidate: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        budget_feedback_root: Any = None,
    ) -> dict[str, Any]:
        feedback_root = (
            dict(budget_feedback_root or {})
            if isinstance(budget_feedback_root, dict)
            else cls._resolve_budget_feedback_root(snapshot)
        )
        family_name = cls._candidate_family(candidate)
        feedback_metrics = resolve_feedback_metrics(
            feedback_root,
            family=family_name,
            target_pool_id=extract_target_pool_id(candidate),
            generator_mode=extract_generator_mode(candidate),
        )
        task_feedback_override = cls._task_feedback_override(candidate)
        if task_feedback_override:
            feedback_metrics = {
                **feedback_metrics,
                **task_feedback_override,
            }
        feedback_scope = {
            "family": family_name,
            "target_pool_id": feedback_metrics.get("target_pool_id"),
            "generator_mode": feedback_metrics.get("generator_mode"),
            "family_feedback_available": bool(feedback_metrics.get("family_feedback_available")),
            "target_pool_feedback_available": bool(feedback_metrics.get("target_pool_feedback_available")),
            "generator_mode_feedback_available": bool(feedback_metrics.get("generator_mode_feedback_available")),
            "control_mode": feedback_metrics.get("control_mode"),
            "legacy_control_mode": feedback_metrics.get("legacy_control_mode"),
            "skill_control_mode": feedback_metrics.get("skill_control_mode"),
            "cooldown_active": bool(feedback_metrics.get("cooldown_active")),
            "suppressed": bool(feedback_metrics.get("suppressed")),
            "family_freeze_active": bool(feedback_metrics.get("family_freeze_active")),
            "target_pool_freeze_active": bool(feedback_metrics.get("target_pool_freeze_active")),
            "generator_mode_freeze_active": bool(feedback_metrics.get("generator_mode_freeze_active")),
            "skill_cooldown_active": bool(feedback_metrics.get("skill_cooldown_active")),
            "skill_suppressed": bool(feedback_metrics.get("skill_suppressed")),
            "skill_family_freeze_active": bool(feedback_metrics.get("skill_family_freeze_active")),
            "skill_target_pool_freeze_active": bool(
                feedback_metrics.get("skill_target_pool_freeze_active")
            ),
            "skill_generator_mode_freeze_active": bool(
                feedback_metrics.get("skill_generator_mode_freeze_active")
            ),
            "paper_skill_lcb": cls._safe_float(feedback_metrics.get("paper_skill_lcb")),
            "paper_recent_skill_lcb": cls._safe_float(
                feedback_metrics.get("paper_recent_skill_lcb")
            ),
            "paper_stability_gap": cls._safe_float(feedback_metrics.get("paper_stability_gap")),
            "paper_coverage_ratio": cls._safe_float(
                feedback_metrics.get("paper_coverage_ratio"),
                1.0,
            ),
            "execution_conversion_efficiency": (
                cls._safe_float(feedback_metrics.get("execution_conversion_efficiency"))
                if feedback_metrics.get("execution_conversion_efficiency_available")
                else None
            ),
            "execution_conversion_efficiency_available": bool(
                feedback_metrics.get("execution_conversion_efficiency_available")
            ),
            "budget_feedback_action": feedback_metrics.get("budget_feedback_action"),
            "budget_action_applied": bool(feedback_metrics.get("budget_action_applied")),
            "prediction_axis": feedback_metrics.get("prediction_axis"),
            "execution_axis": feedback_metrics.get("execution_axis"),
            "execution_optimization_queue": bool(
                feedback_metrics.get("execution_optimization_queue")
            ),
            "small_budget_observe": bool(feedback_metrics.get("small_budget_observe")),
            "prioritize_scale": bool(feedback_metrics.get("prioritize_scale")),
            "cool_or_freeze": bool(feedback_metrics.get("cool_or_freeze")),
            "retain_family": bool(feedback_metrics.get("retain_family")),
            "reduce_budget": bool(feedback_metrics.get("reduce_budget")),
            "no_expansion": bool(feedback_metrics.get("no_expansion")),
        }
        feedback_scope["feedback_available"] = any(
            bool(feedback_scope.get(key))
            for key in (
                "family_feedback_available",
                "target_pool_feedback_available",
                "generator_mode_feedback_available",
            )
        )
        return {
            "root": feedback_root,
            "metrics": feedback_metrics,
            "scope": feedback_scope,
        }

    @staticmethod
    def _expected_regimes(candidate: dict[str, Any]) -> list[str]:
        payload = dict(candidate or {})
        params = dict(payload.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})
        values = (
            payload.get("expected_regime")
            or params.get("expected_regime")
            or candidate_provenance.get("expected_regime")
            or []
        )
        if not isinstance(values, list):
            values = [values]
        return [
            str(item or "").strip().lower()
            for item in list(values or [])
            if str(item or "").strip()
        ]

    @staticmethod
    def _market_regime(snapshot: dict[str, Any]) -> str:
        fg = IncubationBudgeter._safe_float(snapshot.get("fear_greed_index"), 50.0)
        if fg >= 60:
            return "trend"
        if fg <= 40:
            return "mean_reversion"
        return "rotation"

    @classmethod
    def _regime_match_bonus(cls, candidate: dict[str, Any], snapshot: dict[str, Any]) -> float:
        market_regime = cls._market_regime(snapshot)
        expected_regimes = cls._expected_regimes(candidate)
        regime_fit = str(
            dict(candidate.get("research_task") or {}).get("regime_fit")
            or candidate.get("regime_fit")
            or dict(candidate.get("params") or {}).get("regime_fit")
            or ""
        ).strip().lower()
        if market_regime == "trend" and (
            "trend" in expected_regimes or "trend" in regime_fit or "breakout" in regime_fit
        ):
            return 6.0
        if market_regime == "mean_reversion" and (
            "mean_reversion" in expected_regimes
            or "mean_reversion" in regime_fit
            or "reversal" in regime_fit
        ):
            return 6.0
        if market_regime == "rotation" and (
            "rotation" in expected_regimes or "rotation" in regime_fit or "balanced" in regime_fit
        ):
            return 5.0
        return 0.0

    @classmethod
    def _priority_score(
        cls,
        candidate: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        budget_feedback_root: Any = None,
    ) -> float:
        payload = dict(candidate or {})
        metrics = dict(payload.get("backtest_metrics") or {})
        research_task = dict(payload.get("research_task") or {})
        params = dict(payload.get("params") or {})
        candidate_provenance = dict(params.get("candidate_provenance") or {})

        sharpe = cls._safe_float(metrics.get("sharpe_ratio"))
        total_return = cls._safe_float(metrics.get("total_return"))
        max_drawdown = max(0.0, cls._safe_float(metrics.get("max_drawdown")))
        validation_score = cls._safe_float(
            payload.get("candidate_validation_score")
            or candidate_provenance.get("validation_score")
            or params.get("candidate_validation_score")
        )
        task_priority = cls._safe_float(
            payload.get("priority")
            or research_task.get("priority")
            or payload.get("matrix_priority_score")
            or research_task.get("matrix_priority_score")
        )
        stock_family_priority = cls._safe_float(
            payload.get("stock_family_priority")
            or research_task.get("stock_family_priority")
        )
        registry_stage = str(
            payload.get("candidate_registry_stage")
            or candidate_provenance.get("candidate_registry_stage")
            or params.get("candidate_registry_stage")
            or ""
        ).strip().lower()
        risk_level = str(
            payload.get("risk_level")
            or research_task.get("risk_level")
            or params.get("risk_level")
            or candidate_provenance.get("risk_level")
            or ""
        ).strip().lower()
        active_family_names = {
            str(item or "").strip().lower()
            for item in list(((snapshot.get("factor_research") or {}).get("summary") or {}).get("active_family_names") or [])
            if str(item or "").strip()
        }
        family_name = cls._candidate_family(payload)

        score = 0.0
        score += max(-1.0, min(sharpe, 3.0)) * _BASE_PRIORITY_SHARPE_WEIGHT
        score += max(-0.2, min(total_return, 0.6)) * _BASE_PRIORITY_TOTAL_RETURN_WEIGHT
        score -= min(max_drawdown, 0.6) * _BASE_PRIORITY_MAX_DRAWDOWN_WEIGHT
        score += min(max(validation_score, 0.0), 100.0) * 0.25
        score += max(task_priority, 0.0) * 0.18
        score += max(stock_family_priority, 0.0) * 12.0
        score += cls._regime_match_bonus(payload, snapshot)
        if family_name in active_family_names:
            score += 4.0
        if registry_stage == "champion":
            score += 5.0
        elif registry_stage == "challenger":
            score += 4.0
        elif registry_stage == "governed":
            score += 3.0
        if risk_level == "low":
            score += 3.0
        elif risk_level == "high":
            score -= 4.0

        feedback_payload = cls._candidate_feedback(
            payload,
            snapshot,
            budget_feedback_root=budget_feedback_root,
        )
        feedback_metrics = dict(feedback_payload.get("metrics") or {})
        feedback_scope = dict(feedback_payload.get("scope") or {})
        feedback_priority_adjustment = cls._safe_float(feedback_metrics.get("priority_adjustment"))
        feedback_budget_multiplier = cls._safe_float(feedback_metrics.get("budget_multiplier"), 1.0)
        if bool(feedback_scope.get("feedback_available")):
            feedback_skill_priority_adjustment = cls._safe_float(
                feedback_metrics.get("skill_priority_adjustment")
            )
            feedback_skill_budget_multiplier = cls._safe_float(
                feedback_metrics.get("skill_budget_multiplier"),
                1.0,
            )
            paper_skill_lcb = cls._safe_float(feedback_metrics.get("paper_skill_lcb"))
            paper_recent_skill_lcb = cls._safe_float(
                feedback_metrics.get("paper_recent_skill_lcb"),
                paper_skill_lcb,
            )
            paper_stability_gap = max(
                0.0,
                cls._safe_float(feedback_metrics.get("paper_stability_gap")),
            )
            paper_coverage_ratio = max(
                0.0,
                min(cls._safe_float(feedback_metrics.get("paper_coverage_ratio"), 1.0), 1.0),
            )
            execution_conversion_efficiency_available = bool(
                feedback_metrics.get("execution_conversion_efficiency_available")
            )
            execution_conversion_efficiency = cls._safe_float(
                feedback_metrics.get("execution_conversion_efficiency")
            )
            score += feedback_priority_adjustment * 0.45
            score += feedback_skill_priority_adjustment
            score += max(-0.12, min(paper_skill_lcb, 0.18)) * 55.0
            score += max(-0.12, min(paper_recent_skill_lcb, 0.18)) * 34.0
            score -= max(paper_stability_gap - 0.05, 0.0) * 40.0
            score += max(min(paper_coverage_ratio, 1.0) - 0.50, -0.50) * 14.0
            if execution_conversion_efficiency_available:
                score += max(min(execution_conversion_efficiency, 0.40), -0.10) * 28.0
            combined_budget_multiplier = (
                feedback_budget_multiplier * 0.35
                + feedback_skill_budget_multiplier * 0.65
            )
            score *= max(0.68, min(1.35, 0.45 + combined_budget_multiplier * 0.55))
        else:
            score += feedback_priority_adjustment
            score *= max(0.7, min(1.3, 0.7 + feedback_budget_multiplier * 0.3))
        control_mode = str(feedback_metrics.get("control_mode") or "").strip().lower()
        skill_control_mode = str(feedback_metrics.get("skill_control_mode") or "").strip().lower()
        if control_mode == "cooldown":
            score -= 9.0
        elif control_mode == "suppress":
            score -= 24.0
        elif control_mode == "freeze":
            score -= 36.0
        if skill_control_mode == "cooldown":
            score -= 6.0
        elif skill_control_mode == "suppress":
            score -= 16.0
        elif skill_control_mode == "freeze":
            score -= 28.0

        # P2-D 反馈回路：对纯 family EMA 的轻量兼容，避免没有 P3 feedback 时退化。
        if not bool(feedback_scope.get("feedback_available")):
            family_feedback = dict((snapshot.get("family_gate_feedback") or {}).get(family_name) or {})
            ema_submit = cls._safe_float(family_feedback.get("ema_submit_count"), -1.0)
            if ema_submit >= 0.0:
                if ema_submit > 3.0:
                    score += 5.0
                elif ema_submit > 1.0:
                    score += 2.5
                elif ema_submit < 0.3:
                    score -= 2.0

        return round(score, 4)
