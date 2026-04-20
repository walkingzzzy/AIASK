export type FactoryAutonomyTaskBrief = {
    task_id?: string;
    task_source?: string;
    opportunity_type?: string;
    generation_limit?: number;
    generated_count?: number;
};

export type FactoryValidationFamilyQualityPanelItem = {
    strategy_family?: string;
    holding_period_bucket?: string;
    validation_focus?: string;
    strategy_count?: number;
    raw_validation_grade_distribution?: Record<string, number>;
    effective_validation_grade_distribution?: Record<string, number>;
    raw_validation_total_score_mean?: number;
    raw_validation_a_rate?: number;
    raw_validation_b_rate?: number;
    raw_validation_c_rate?: number;
    raw_validation_d_rate?: number;
    strict_incubation_ready_count?: number;
    strict_incubation_ready_rate?: number;
    live_candidate_ready_count?: number;
    live_candidate_ready_rate?: number;
    raw_b_or_above_count?: number;
    raw_b_or_above_rate?: number;
    strict_ready_given_raw_b_count?: number;
    strict_ready_given_raw_b_rate?: number;
    live_ready_given_raw_b_count?: number;
    live_ready_given_raw_b_rate?: number;
    mean_trade_density?: number;
    mean_post_cost_sharpe?: number;
    mean_deflated_sharpe_ratio?: number;
    mean_pbo?: number;
    family_raw_a_rate?: number;
    family_raw_b_rate?: number;
    family_raw_c_rate?: number;
    family_raw_d_rate?: number;
    family_strict_incubation_ready_rate?: number;
    family_live_candidate_ready_rate?: number;
    family_mean_trade_density?: number;
    family_mean_post_cost_sharpe?: number;
    family_mean_dsr?: number;
    family_mean_pbo?: number;
};

export type FactoryGenerationLaneQualityItem = {
    lane_key?: string;
    lane_label?: string;
    generation_tier?: string;
    strategy_count?: number;
    status_counts?: Record<string, number>;
    generator_mode_counts?: Record<string, number>;
    strategy_family_counts?: Record<string, number>;
    raw_validation_grade_distribution?: Record<string, number>;
    effective_validation_grade_distribution?: Record<string, number>;
    raw_validation_total_score_mean?: number;
    raw_validation_a_rate?: number;
    raw_validation_b_rate?: number;
    raw_validation_c_rate?: number;
    raw_validation_d_rate?: number;
    strict_incubation_ready_count?: number;
    strict_incubation_ready_rate?: number;
    live_candidate_ready_count?: number;
    live_candidate_ready_rate?: number;
    promotion_ready_count?: number;
    promotion_ready_rate?: number;
    quality_passed_count?: number;
    quality_pass_rate?: number;
    raw_b_or_above_count?: number;
    raw_b_or_above_rate?: number;
    strict_ready_given_raw_b_count?: number;
    strict_ready_given_raw_b_rate?: number;
    live_ready_given_raw_b_count?: number;
    live_ready_given_raw_b_rate?: number;
};

export type FactoryQualitySummarySnapshot = {
    run_id?: string | null;
    status?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    candidates_spawned?: number;
    submitted?: number;
    research_only_count?: number;
    deferred_submission_count?: number;
    validation_grade_distribution?: Record<string, number>;
    raw_validation_grade_distribution?: Record<string, number>;
    effective_validation_grade_distribution?: Record<string, number>;
    raw_validation_total_score_mean?: number;
    raw_validation_total_score_p50?: number;
    raw_validation_total_score_p90?: number;
    raw_validation_a_rate?: number;
    raw_validation_b_rate?: number;
    raw_validation_c_rate?: number;
    raw_validation_d_rate?: number;
    strict_incubation_ready_count?: number;
    strict_incubation_ready_rate?: number;
    live_candidate_ready_count?: number;
    live_candidate_ready_rate?: number;
    raw_b_or_above_count?: number;
    raw_b_or_above_rate?: number;
    strict_ready_given_raw_b_count?: number;
    strict_ready_given_raw_b_rate?: number;
    live_ready_given_raw_b_count?: number;
    live_ready_given_raw_b_rate?: number;
    strict_live_alignment_gap_count?: number;
    strict_live_alignment_gap_rate?: number;
    strict_live_alignment_status_counts?: Record<string, number>;
    validation_family_quality_panel?: FactoryValidationFamilyQualityPanelItem[];
    generation_lane_definition?: string;
    generation_lane_quality_panel?: FactoryGenerationLaneQualityItem[];
    generation_mode_counts?: Record<string, number>;
    external_llm_provider_health_status?: string | null;
    external_llm_provider_control_mode?: string | null;
    prediction_quality_distribution?: Record<string, number>;
    execution_quality_distribution?: Record<string, number>;
    evidence_alignment_distribution?: Record<string, number>;
    confidence_contract_ready_rate?: number;
};

export type FactoryRecentRunBrief = {
    run_id?: string | null;
    status?: string;
    started_at?: string | null;
    completed_at?: string | null;
    readiness_decision?: string;
    readiness_score?: number | null;
    submit_stage_entered?: boolean;
    submitted?: number;
    research_only_count?: number;
    deferred_submission_count?: number;
    blocking_reason_codes?: string[];
    warning_reason_codes?: string[];
    external_llm_provider_control_mode?: string | null;
    external_llm_provider_control_reasons?: string[];
    suppressed_generator_modes?: string[];
    external_llm_provider_suppressed?: boolean;
    external_llm_provider_cooldown?: boolean;
    governed_blocked_ratio?: number | null;
    governed_candidate_pool_strict_shortfall_count?: number | null;
    governed_blocked_candidate_count?: number | null;
    governed_source_candidate_count?: number | null;
    budget_feedback_evidence_debt_ratio?: number | null;
    budget_feedback_zero_signal_ratio?: number | null;
    budget_feedback_forward_window_coverage_ratio?: number | null;
    budget_feedback_promotion_ready_ratio?: number | null;
    budget_feedback_promotion_review_coverage_ratio?: number | null;
    external_llm_stage_attempt_count?: number;
    external_llm_real_request_count?: number;
    external_llm_compatibility_skip_ratio?: number;
    external_llm_compatibility_failure_ratio?: number;
    external_llm_effective_response_ratio?: number;
    external_llm_empty_200_response_ratio?: number;
    raw_b_or_above_rate?: number | null;
    strict_ready_given_raw_b_rate?: number | null;
    live_ready_given_raw_b_rate?: number | null;
    strict_live_alignment_gap_count?: number | null;
    strict_live_alignment_gap_rate?: number | null;
};

export type FactoryRecentRunDiagnostics = {
    contract_version?: string;
    window_size?: number;
    analyzed_run_count?: number;
    status_counts?: Record<string, number>;
    readiness_decision_counts?: Record<string, number>;
    readiness_blocked_count?: number;
    readiness_blocked_rate?: number;
    submit_stage_entered_count?: number;
    submit_stage_entered_rate?: number;
    submitted_positive_count?: number;
    submitted_positive_rate?: number;
    blocker_reason_topn?: Array<{ reason_code?: string; count?: number }>;
    warning_reason_topn?: Array<{ reason_code?: string; count?: number }>;
    external_llm_provider_control_mode_counts?: Record<string, number>;
    external_llm_provider_suppressed_run_count?: number;
    external_llm_provider_suppressed_run_rate?: number;
    external_llm_provider_cooldown_run_count?: number;
    external_llm_provider_cooldown_run_rate?: number;
    external_llm_provider_control_reason_topn?: Array<{ reason_code?: string; count?: number }>;
    suppressed_generator_mode_topn?: Array<{ mode?: string; count?: number }>;
    governed_pool_diagnostics?: {
        measurement_run_count?: number;
        latest_governed_blocked_ratio?: number;
        recent_governed_blocked_ratio_mean?: number;
        latest_governed_candidate_pool_strict_shortfall_count?: number;
        recent_governed_candidate_pool_strict_shortfall_mean?: number;
        latest_governed_blocked_candidate_count?: number;
        recent_governed_blocked_candidate_count_mean?: number;
        latest_governed_source_candidate_count?: number;
        recent_governed_source_candidate_count_mean?: number;
        warning_reason_topn?: Array<{ reason_code?: string; count?: number }>;
        blocking_reason_topn?: Array<{ reason_code?: string; count?: number }>;
        exclusion_reason_topn?: Array<{ reason_code?: string; count?: number }>;
        pending_reason_topn?: Array<{ reason_code?: string; count?: number }>;
        ineligible_reason_topn?: Array<{ reason_code?: string; count?: number }>;
    };
    evidence_debt_diagnostics?: {
        measurement_run_count?: number;
        latest_budget_feedback_evidence_debt_ratio?: number;
        recent_budget_feedback_evidence_debt_ratio_mean?: number;
        latest_budget_feedback_zero_signal_ratio?: number;
        recent_budget_feedback_zero_signal_ratio_mean?: number;
        latest_budget_feedback_forward_window_coverage_ratio?: number;
        recent_budget_feedback_forward_window_coverage_ratio_mean?: number;
        latest_budget_feedback_promotion_ready_ratio?: number;
        recent_budget_feedback_promotion_ready_ratio_mean?: number;
        latest_budget_feedback_promotion_review_coverage_ratio?: number;
        recent_budget_feedback_promotion_review_coverage_ratio_mean?: number;
        warning_reason_topn?: Array<{ reason_code?: string; count?: number }>;
    };
    provider_control_diagnostics?: {
        measurement_run_count?: number;
        active_attempt_run_count?: number;
        zero_attempt_run_count?: number;
        latest_stage_attempt_count?: number;
        recent_stage_attempt_count_mean?: number;
        latest_real_request_count?: number;
        recent_real_request_count_mean?: number;
        latest_compatibility_skip_ratio?: number;
        recent_compatibility_skip_ratio_mean?: number;
        latest_compatibility_failure_ratio?: number;
        recent_compatibility_failure_ratio_mean?: number;
        latest_effective_response_ratio?: number;
        recent_effective_response_ratio_mean?: number;
        latest_empty_200_response_ratio?: number;
        recent_empty_200_response_ratio_mean?: number;
    };
    quality_progress?: {
        quality_measurement_run_count?: number;
        latest_raw_b_or_above_rate?: number;
        recent_raw_b_or_above_rate_mean?: number;
        latest_strict_ready_given_raw_b_rate?: number;
        recent_strict_ready_given_raw_b_rate_mean?: number;
        latest_live_ready_given_raw_b_rate?: number;
        recent_live_ready_given_raw_b_rate_mean?: number;
        strict_live_gap_measurement_run_count?: number;
        latest_strict_live_alignment_gap_rate?: number;
        recent_strict_live_alignment_gap_rate_mean?: number;
        strict_live_gap_run_count?: number;
        strict_live_gap_run_rate?: number;
    };
    recent_runs?: FactoryRecentRunBrief[];
};

export type FactoryQualityBaseline = {
    contract_version?: string;
    captured_at?: string;
    latest_run?: FactoryQualitySummarySnapshot;
    recent_run_diagnostics?: FactoryRecentRunDiagnostics;
    submitted_strategy_cohort?: FactoryQualitySummarySnapshot & {
        statuses?: string[];
        factory_strategy_count?: number;
        status_counts?: Record<string, number>;
        zero_signal_count?: number;
        zero_signal_rate?: number;
        forward_coverage_count?: number;
        forward_coverage_rate?: number;
        promotion_ready_count?: number;
        promotion_ready_rate?: number;
        quality_passed_count?: number;
        quality_pass_rate?: number;
        baseline_forward_days?: number[];
        quality_report_missing_count?: number;
        zero_signal_definition?: string;
        forward_coverage_definition?: string;
        live_gate_ready_count?: number;
        live_gate_ready_rate?: number;
        strict_live_alignment_gap_count?: number;
        strict_live_alignment_gap_rate?: number;
        strict_live_alignment_status_counts?: Record<string, number>;
        validation_grade_d_strict_incubation_pass_count?: number;
        validation_grade_d_strict_incubation_pass_rate?: number;
        validation_grade_d_promotion_ready_count?: number;
        validation_grade_d_promotion_ready_rate?: number;
    };
};

export type FactorySignalQualityMetricAggregate = {
    mean?: number | null;
    min?: number | null;
    max?: number | null;
    p50?: number | null;
    p90?: number | null;
    count?: number | null;
};

export type FactorySignalQualityRegistryProbabilitySummary = {
    entry_count?: number;
    brier_score?: FactorySignalQualityMetricAggregate;
    ece?: FactorySignalQualityMetricAggregate;
    calibration_gap?: FactorySignalQualityMetricAggregate;
    coverage_gap?: FactorySignalQualityMetricAggregate;
    quality_distribution?: Record<string, number>;
};

export type FactorySignalQualityRegistrySentimentSummary = {
    entry_count?: number;
    news_oos_available_ratio?: number | null;
    news_alpha_5d?: FactorySignalQualityMetricAggregate;
    price_momentum_hit_rate_5d?: FactorySignalQualityMetricAggregate;
    sentiment_distribution?: Record<string, number>;
    stability_distribution?: Record<string, number>;
};

export type FactorySignalQualityRegistryFactorSummary = {
    entry_count?: number;
    oos_rank_ic_mean?: FactorySignalQualityMetricAggregate;
    purged_kfold_stability_ratio?: FactorySignalQualityMetricAggregate;
    rating_distribution?: Record<string, number>;
    lookahead_risk_distribution?: Record<string, number>;
};

export type FactorySignalQualityRegistrySnapshot = {
    snapshot_at?: string;
    buy_probability?: FactorySignalQualityRegistryProbabilitySummary;
    sentiment?: FactorySignalQualityRegistrySentimentSummary;
    factor?: FactorySignalQualityRegistryFactorSummary;
    total_entries?: number;
};

export type FactorySignalQualityRegistryDriftCheck = {
    current?: number | null;
    baseline?: number | null;
    status?: string | null;
    note?: string | null;
};

export type FactorySignalQualityRegistryDrift = {
    drift_checked_at?: string;
    overall_status?: string | null;
    degraded_dimensions?: string[];
    checks?: Record<string, FactorySignalQualityRegistryDriftCheck>;
};

export type FactorySignalQualityRegistryProbabilityEntry = Record<string, unknown> & {
    code?: string | null;
    quality?: string | null;
};

export type FactorySignalQualityRegistrySentimentEntry = Record<string, unknown> & {
    code?: string | null;
    sentiment?: string | null;
};

export type FactorySignalQualityRegistryFactorEntry = Record<string, unknown> & {
    factor_name?: string | null;
    rating?: string | null;
};

export type FactorySignalQualityRegistry = FactorySignalQualityRegistrySnapshot & {
    snapshot?: FactorySignalQualityRegistrySnapshot;
    drift?: FactorySignalQualityRegistryDrift;
    recent_probability?: FactorySignalQualityRegistryProbabilityEntry[];
    recent_sentiment?: FactorySignalQualityRegistrySentimentEntry[];
    recent_factor?: FactorySignalQualityRegistryFactorEntry[];
};

export type FactoryFeedbackGeneratorModeControl = {
    control_mode?: string | null;
    source?: string | string[] | null;
    families?: string[];
    control_reasons?: string[];
    feedback_observed_count?: number;
    stagnant_runs?: number;
    metrics?: Record<string, unknown>;
};

export type FactoryFeedbackSummary = {
    lifecycle_feedback_input_contract_version?: string | null;
    lifecycle_feedback_input_observed?: boolean;
    feedback_available?: boolean;
    family_count?: number;
    strategy_count?: number;
    target_pool_scope_count?: number;
    generator_mode_scope_count?: number;
    runtime_alert_count?: number;
    runtime_risk_event_count?: number;
    promotion_review_count?: number;
    blocked_task_count?: number;
    planned_cooldown_task_count?: number;
    promotion_review_status_counts?: Record<string, number>;
    planned_control_mode_counts?: Record<string, number>;
    planned_target_pool_control_mode_counts?: Record<string, number>;
    planned_generator_mode_control_mode_counts?: Record<string, number>;
    selected_control_mode_counts?: Record<string, number>;
    selected_target_pool_control_mode_counts?: Record<string, number>;
    selected_generator_mode_control_mode_counts?: Record<string, number>;
    submission_control_mode_counts?: Record<string, number>;
    submission_target_pool_control_mode_counts?: Record<string, number>;
    submission_generator_mode_control_mode_counts?: Record<string, number>;
    suppressed_families?: string[];
    suppressed_target_pools?: string[];
    suppressed_generator_modes?: string[];
    generator_mode_controls?: Record<string, FactoryFeedbackGeneratorModeControl>;
};
