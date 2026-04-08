import type {
    PaperTradingAccount,
    PaperTradingNavPoint,
    PaperTradingPendingOrder,
    PaperTradingPosition,
} from './paper-trading';

export const STRATEGY_MANAGER_ACTIONS = [
    'help',
    'create',
    'publish',
    'archive',
    'list',
    'detail',
    'review_report',
    'events',
    'update_metrics',
    'review',
    'subscribe',
    'unsubscribe',
    'my_subscriptions',
    'rank',
    'capabilities',
    'daily_snapshot',
    'daily_snapshots',
    'get_signals',
    'get_forward_returns',
    'get_signal_stats',
    'review_report_recheck',
    'submit',
    'lifecycle_scan',
    'incubation_overview',
    'factory_status',
    'factory_run_once',
    'factory_runs',
    'factory_run_detail',
    'incubation_accounts',
    'incubation_metrics',
    'paper_account',
    'paper_orders',
    'paper_nav',
    'incubation_sync_run',
    'incubation_pipeline',
    'incubation_pipeline_run',
    'risk_events',
    'risk_snapshots',
    'risk_scan_run',
    'risk_recovery',
    'resolve_risk_event',
    'runtime_alerts',
    'runtime_alert_dispatch_run',
    'runtime_alert_ack',
    'runtime_control',
    'runtime_control_set',
    'promotion_reviews',
    'promotion_review_run',
    'runtime_cycle_status',
    'runtime_cycle_run',
    'domain_events',
    'domain_projection',
    'domain_projection_snapshot',
    'domain_projection_rebuild',
    'vector_profiles',
    'vector_indexes',
    'vector_index_snapshots',
    'vector_ann_search',
    'vector_reconcile',
    'vector_rebuild',
    'vector_health',
    'vector_cleanup',
    'ai_generate',
    'ai_experiments',
    'task_runs',
] as const;

export type StrategyManagerAction = typeof STRATEGY_MANAGER_ACTIONS[number];

export const STRATEGY_MANAGER_ERROR_CODES = [
    'STRATEGY_MANAGER_INVALID_ACTION',
    'STRATEGY_MANAGER_INVALID_PARAMS',
    'STRATEGY_MANAGER_NOT_FOUND',
    'STRATEGY_MANAGER_GATE_FAILED',
    'STRATEGY_MANAGER_UNSUPPORTED',
    'STRATEGY_MANAGER_BACKEND_ERROR',
] as const;

export type StrategyManagerErrorCode = typeof STRATEGY_MANAGER_ERROR_CODES[number];

export type StrategyTrustedInfo = {
    sample_start_date?: string;
    sample_end_date?: string;
    turnover_rate?: number | null;
    capacity?: number | null;
    capacity_label?: string;
};

export type Strategy = {
    id: string;
    name: string;
    strategy_type?: string;
    description?: string;
    subscriber_count?: number;
    avg_rating?: number;
    review_count?: number;
    metrics?: {
        total_return?: number;
        annual_return?: number;
        sharpe_ratio?: number;
        max_drawdown?: number;
        win_rate?: number;
    };
    nav_series?: number[];
} & StrategyTrustedInfo;

export type RankingResponse = { strategies?: Strategy[] } | Strategy[];

export type FactoryAutonomyTaskBrief = {
    task_id?: string;
    task_source?: string;
    opportunity_type?: string;
    generation_limit?: number;
    generated_count?: number;
};

export type FactoryRunSummary = {
    trace_id?: string;
    lifecycle_feedback_input_contract_version?: string;
    lifecycle_feedback_input_available?: boolean;
    budget_feedback_available?: boolean;
    budget_feedback_family_count?: number;
    budget_feedback_strategy_count?: number;
    budget_feedback_target_pool_scope_count?: number;
    budget_feedback_generator_mode_scope_count?: number;
    budget_feedback_runtime_alert_count?: number;
    budget_feedback_runtime_risk_event_count?: number;
    budget_feedback_promotion_review_count?: number;
    budget_feedback_promotion_review_status_counts?: Record<string, number>;
    blocked_feedback_task_count?: number;
    planned_feedback_cooldown_task_count?: number;
    planned_feedback_control_mode_counts?: Record<string, number>;
    planned_feedback_target_pool_control_mode_counts?: Record<string, number>;
    planned_feedback_generator_mode_control_mode_counts?: Record<string, number>;
    selected_feedback_control_mode_counts?: Record<string, number>;
    selected_feedback_target_pool_control_mode_counts?: Record<string, number>;
    selected_feedback_generator_mode_control_mode_counts?: Record<string, number>;
    feedback_control_mode_counts?: Record<string, number>;
    feedback_target_pool_control_mode_counts?: Record<string, number>;
    feedback_generator_mode_control_mode_counts?: Record<string, number>;
    suppressed_families?: string[];
    suppressed_target_pools?: string[];
    suppressed_generator_modes?: string[];
    external_llm_provider_control_mode?: string;
    generator_mode_controls?: Record<string, unknown>;
    stage_status_counts?: Record<string, number>;
    failed_stage_count?: number;
    partial_stage_count?: number;
    skipped_stage_count?: number;
    hard_failure_count?: number;
    degraded_stage_count?: number;
    failed_stages?: string[];
    partial_stages?: string[];
    skipped_stages?: string[];
    skip_reason?: string;
    skip_reasons?: string[];
    persistence_failure_count?: number;
    persistence_failures?: Array<{
        operation?: string;
        stage?: string | null;
        error_type?: string;
        error?: string;
    }>;
    candidates_spawned?: number;
    candidates_passed_backtest?: number;
    candidates_after_dedup?: number;
    passed_quality_gate?: number;
    autonomy_generated?: number;
    autonomy_task_count?: number;
    event_task_count?: number;
    snapshot_task_count?: number;
    snapshot_degraded?: boolean;
    snapshot_completion_ratio?: number;
    snapshot_failure_reason_count?: number;
    task_source_counts?: Record<string, number>;
    scanner_task_types?: Record<string, number>;
    event_snapshot_mixed?: boolean;
    autonomy_task_briefs?: FactoryAutonomyTaskBrief[];
    submitted?: number;
    eliminated?: number;
    elapsed_seconds?: number;
    constraint_violation_count?: number;
    target_symbol_intersection_ratio_avg?: number;
    universe_expansion_count?: number;
    preference_mismatch_warning_count?: number;
    attempt_adjusted_gate_failed?: number;
    attempt_adjusted_score_avg?: number;
    event_window_contamination_warning_count?: number;
    cost_audit_missing_count?: number;
    deflated_sharpe_proxy_avg?: number;
    deflated_sharpe_ratio_avg?: number;
    high_pbo_proxy_count?: number;
    high_pbo_count?: number;
    formal_multiple_testing_count?: number;
    weak_white_reality_check_count?: number;
    weak_hansen_spa_count?: number;
    refresh_metrics_only_count?: number;
    spawn_revision_from_existing_count?: number;
};

export type FactoryStatusResponse = {
    running?: boolean;
    run_time?: string;
    last_run?: string | null;
    last_summary?: FactoryRunSummary;
    last_result?: {
        status?: string;
        error?: string;
    };
};

export type CapabilityResponse = {
    daily_snapshot?: boolean;
    paper_incubation?: boolean;
    incubation_pipeline?: boolean;
    runtime_risk?: boolean;
    risk_snapshots?: boolean;
    risk_recovery?: boolean;
    execution_risk?: boolean;
    runtime_controls?: boolean;
    promotion_pipeline?: boolean;
    projection_snapshots?: boolean;
    event_replay?: boolean;
    vector_platform?: boolean;
    vector_governance?: boolean;
    persistent_vector_index?: boolean;
    ann_vector_search?: boolean;
    ai_generation?: boolean;
    multi_agent_review?: boolean;
    quality_governance?: boolean;
    domain_events?: boolean;
    domain_projection?: boolean;
    runtime_cycle?: boolean;
};

export type DailySnapshotResponse = {
    snapshot_date?: string;
    fear_greed_index?: number;
    degraded?: boolean;
    failure_reasons?: string[];
    missing_fields?: string[];
    hot_sectors?: string[];
    cold_sectors?: string[];
    summary?: {
        listed_count?: number;
    };
    completeness?: {
        completion_ratio?: number;
    };
};

export type FactoryRunsResponse = {
    dto_version?: string;
    latest?: {
        run_id?: string;
        status?: string;
        trace_id?: string | null;
    } | null;
    items?: Array<{
        run_id?: string;
        trace_id?: string | null;
        status?: string;
        started_at?: string;
        completed_at?: string | null;
        elapsed_seconds?: number;
        error?: string | null;
        summary?: FactoryRunSummary;
        stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
        pipeline?: {
            trace_id?: string | null;
            failed_stage?: string | null;
            partial_stage?: string | null;
            skipped_stage?: string | null;
            stage_order?: string[];
            total_stage_count?: number;
            completed_stage_count?: number;
            partial_stage_count?: number;
            skipped_stage_count?: number;
            failed_stage_count?: number;
            stage_status_counts?: Record<string, number>;
        };
    }>;
    count?: number;
};

export type FactoryGovernanceReasonTopEntry = {
    reason?: string;
    count?: number;
};

export type FactoryGovernanceCountMap = Record<string, number>;

export type FactoryGovernanceSupportMap = Record<string, boolean>;

export type FactoryGovernanceValidationProfile = {
    profile?: string | null;
    validation_focus?: string | null;
    primary_validation_layer?: string | null;
};

export type FactoryGovernanceConstraintCheck = {
    constraint_violation?: string | null;
    intersection_ratio?: number;
    expansion_applied?: boolean;
    expansion_reason?: string | null;
    expansion_source?: string | null;
    alignment_contract_violation?: string | null;
};

export type FactoryGovernanceAttemptAdjustment = {
    attempt_count?: number;
    selected_count?: number;
    selection_ratio?: number;
    penalty?: number;
    applied?: boolean;
};

export type FactoryGovernanceCommitteeReview = {
    decision?: string;
    review_mode?: string;
    final_score?: number;
    rank?: number;
    is_champion?: boolean;
    execution_score?: number;
    capacity_score?: number;
    task_alignment_score?: number;
    novelty_score?: number;
    alignment_issues?: string[];
    execution_issues?: string[];
    capacity_issues?: string[];
    accept_blockers?: string[];
};

export type FactoryGovernanceDedupBrief = {
    strategy_type?: string | null;
    generator_type?: string | null;
    candidate_family_id?: string | null;
    target_symbols?: string[];
    duplicate?: boolean;
    duplicate_level?: string | null;
    refresh_existing?: boolean;
    refresh_mode?: string | null;
    matched_strategy_id?: string | null;
    refresh_decision_basis?: string | null;
    revision_trigger_reason?: string | null;
    target_overlap?: number;
};

export type FactoryGovernanceStrategyBrief = {
    strategy_id?: string | null;
    name?: string | null;
    status?: string | null;
    submission_lane?: string | null;
    submission_action_type?: string | null;
    primary_validation_layer?: string | null;
    refresh_mode?: string | null;
    position_assumption?: string | null;
    task_signature?: string | null;
    candidate_family?: string | null;
    generator_mode?: string | null;
    source_candidate_artifact_id?: string | null;
    target_pool_id?: string | null;
    vector_profile_id?: string | null;
    multiple_testing_registry_record_id?: string | null;
    constraint_check?: FactoryGovernanceConstraintCheck;
    validation_profile?: FactoryGovernanceValidationProfile;
    event_window_config?: Record<string, unknown>;
    cost_assumptions?: Record<string, unknown>;
    explicit_cost_breakdown?: Record<string, unknown>;
    implicit_cost_breakdown?: Record<string, unknown>;
    attempt_adjustment?: FactoryGovernanceAttemptAdjustment;
    committee_review?: FactoryGovernanceCommitteeReview;
    has_constraint_check?: boolean;
    has_validation_profile?: boolean;
    has_event_window_config?: boolean;
    has_cost_assumptions?: boolean;
    has_explicit_cost_breakdown?: boolean;
    has_implicit_cost_breakdown?: boolean;
    has_attempt_adjustment?: boolean;
    has_committee_review?: boolean;
    created_strategy_pool?: boolean;
    created_audit_only?: boolean;
    refreshed_existing?: boolean;
    live_candidate_ready?: boolean;
    live_review_ready?: boolean;
    direct_trade_candidate?: boolean;
};

export type FactoryGovernanceEvidenceStrategyBrief = FactoryGovernanceStrategyBrief & {
    lineage_id?: string | null;
    vector_backend?: string | null;
    has_cost_assumptions?: boolean;
    has_execution_reality?: boolean;
    has_multiple_testing_registry?: boolean;
};

export type FactoryGovernanceGateArtifact = {
    contract_version?: string;
    available?: boolean;
    gate_0_passed?: number;
    gate_0_failed?: number;
    pre_gate_passed?: number;
    pre_gate_failed?: number;
    gate_1_passed?: number;
    gate_1_failed?: number;
    gate_2_input?: number;
    gate_2_passed?: number;
    gate_2_failed?: number;
    gate_3_input?: number;
    gate_3_pending_count?: number;
    gate_3_passed?: number;
    gate_3_failed?: number;
    gate_3_provisional_passed?: number;
    backtest_failed_reason_counts?: FactoryGovernanceCountMap;
    backtest_thresholds_by_type?: Record<string, Record<string, unknown>>;
    gate_3_failure_reason_topn?: FactoryGovernanceReasonTopEntry[];
};

export type FactoryGovernanceDedupArtifact = {
    contract_version?: string;
    available?: boolean;
    input_count?: number;
    existing_count?: number;
    existing_scan_count?: number;
    kept_count?: number;
    dropped_count?: number;
    refreshed_existing_count?: number;
    vector_checks?: number;
    coarse_hit_ratio?: number;
    refresh_mode_counts?: FactoryGovernanceCountMap;
    duplicate_level_counts?: FactoryGovernanceCountMap;
    refresh_decision_basis_counts?: FactoryGovernanceCountMap;
    revision_trigger_reason_counts?: FactoryGovernanceCountMap;
    tested_object_hash_changed_count?: number;
    existing_identity_available_count?: number;
    existing_tested_object_available_count?: number;
    kept_briefs?: FactoryGovernanceDedupBrief[];
    dropped_briefs?: FactoryGovernanceDedupBrief[];
};

export type FactoryGovernanceIncubationBudgetSummary = Record<string, unknown> & {
    family_counts?: FactoryGovernanceCountMap;
};

export type FactoryGovernanceSubmissionArtifact = {
    contract_version?: string;
    available?: boolean;
    strategy_count?: number;
    created_count?: number;
    created_total_count?: number;
    created_strategy_pool_count?: number;
    created_audit_only_count?: number;
    refreshed_count?: number;
    gate_3_input?: number;
    submitted_count?: number;
    passed_quality_gate_count?: number;
    gate_3_passed?: number;
    gate_3_failed?: number;
    gate_3_provisional_passed?: number;
    incubation_budget_summary?: FactoryGovernanceIncubationBudgetSummary;
    gate_3_failure_reason_topn?: FactoryGovernanceReasonTopEntry[];
    submission_lane_counts?: FactoryGovernanceCountMap;
    submission_action_type_counts?: FactoryGovernanceCountMap;
    strategy_status_counts?: FactoryGovernanceCountMap;
    committee_decision_counts?: FactoryGovernanceCountMap;
    refresh_mode_counts?: FactoryGovernanceCountMap;
    committee_review_count?: number;
    primary_validation_layer_counts?: FactoryGovernanceCountMap;
    validation_profile_counts?: FactoryGovernanceCountMap;
    constraint_violation_counts?: FactoryGovernanceCountMap;
    constraint_check_count?: number;
    validation_profile_count?: number;
    event_window_config_count?: number;
    position_assumption_count?: number;
    cost_assumptions_count?: number;
    explicit_cost_breakdown_count?: number;
    implicit_cost_breakdown_count?: number;
    attempt_adjustment_count?: number;
    task_signature_count?: number;
    strategy_briefs?: FactoryGovernanceStrategyBrief[];
};

export type FactoryGovernanceEvidenceArtifact = {
    contract_version?: string;
    available?: boolean;
    quality_report_count?: number;
    multiple_testing_registry_count?: number;
    multiple_testing_registry_record_count?: number;
    lineage_contract_count?: number;
    lineage_id_count?: number;
    committee_review_count?: number;
    constraint_check_count?: number;
    validation_profile_count?: number;
    event_window_config_count?: number;
    position_assumption_count?: number;
    vector_profile_count?: number;
    vector_backend_counts?: FactoryGovernanceCountMap;
    cost_assumptions_count?: number;
    explicit_cost_breakdown_count?: number;
    implicit_cost_breakdown_count?: number;
    execution_reality_count?: number;
    attempt_adjustment_count?: number;
    task_signature_count?: number;
    refresh_mode_count?: number;
    primary_validation_layer_count?: number;
    slippage_assumption_count?: number;
    market_impact_assumption_count?: number;
    capacity_assumption_count?: number;
    tradability_filter_count?: number;
    extension_interface_support?: FactoryGovernanceSupportMap;
    strategy_evidence_briefs?: FactoryGovernanceEvidenceStrategyBrief[];
};

export type FactoryGovernancePlaneArtifact = {
    contract_version?: string;
    available?: boolean;
    plane?: string;
    gate_artifact?: FactoryGovernanceGateArtifact;
    dedup_artifact?: FactoryGovernanceDedupArtifact;
    submission_artifact?: FactoryGovernanceSubmissionArtifact;
    evidence_artifact?: FactoryGovernanceEvidenceArtifact;
    source_chain?: string[];
};

export type FactoryRunDetailResponse = {
    dto_version?: string;
    run_id?: string;
    trace_id?: string | null;
    status?: string;
    started_at?: string;
    completed_at?: string | null;
    elapsed_seconds?: number;
    error?: string | null;
    summary?: FactoryRunSummary;
    snapshot_summary?: Record<string, string | number | null | undefined>;
    quality_gate?: Record<string, unknown>;
    research_summary?: Record<string, unknown>;
    research_plane?: Record<string, unknown>;
    research_artifact?: Record<string, unknown>;
    task_artifact?: Record<string, unknown>;
    candidate_artifact?: Record<string, unknown>;
    evidence_artifact?: Record<string, unknown>;
    governance_plane?: FactoryGovernancePlaneArtifact;
    gate_artifact?: FactoryGovernanceGateArtifact;
    dedup_artifact?: FactoryGovernanceDedupArtifact;
    submission_artifact?: FactoryGovernanceSubmissionArtifact;
    governance_evidence_artifact?: FactoryGovernanceEvidenceArtifact;
    feedback_summary?: Record<string, unknown>;
    incubation_summary?: Record<string, unknown>;
    live_ready_summary?: Record<string, unknown>;
    stages?: Record<string, Record<string, string | number | boolean | null | undefined>>;
    pipeline?: {
        trace_id?: string | null;
        failed_stage?: string | null;
        partial_stage?: string | null;
        skipped_stage?: string | null;
        stage_order?: string[];
        total_stage_count?: number;
        completed_stage_count?: number;
        partial_stage_count?: number;
        skipped_stage_count?: number;
        failed_stage_count?: number;
        stage_status_counts?: Record<string, number>;
    };
};

export type StrategyMetric = {
    period?: string;
    total_return?: number;
    annual_return?: number;
    sharpe_ratio?: number;
    max_drawdown?: number;
    win_rate?: number;
    calmar_ratio?: number;
    trade_count?: number;
};

export type StrategyReview = {
    user_id: string;
    rating: number;
    comment?: string;
    created_at?: string;
};

export type StrategyCore = {
    id: string;
    name: string;
    description?: string;
    strategy_type?: string;
    status?: string;
    author_id?: string;
    subscriber_count?: number;
    avg_rating?: number;
    review_count?: number;
    factor_weights?: Record<string, number>;
    metrics?: StrategyMetric[];
    reviews?: StrategyReview[];
} & StrategyTrustedInfo;

export type SignalStatsResponse = {
    hit_rate?: Record<string, number>;
    forward_ic?: Record<string, number>;
    forward_sharpe?: Record<string, number>;
    total_signals?: number;
};

export type Signal = {
    signal_date?: string;
    code?: string;
    signal?: number;
    score?: number;
};

export type SignalsResponse = {
    signals?: Signal[];
    count?: number;
    subscriber?: boolean;
};

export type ReviewReportResponse = {
    passed?: boolean;
    report_type?: string;
    reports?: Array<{
        report_type?: string;
        updated_at?: string;
        summary?: {
            review_source?: string;
            validation_grade?: string;
        };
    }>;
    summary?: {
        status_after_review?: string;
        validation_grade?: string;
        review_source?: string;
        primary_validation_layer?: string;
        refresh_mode?: string;
        committee_decision?: string;
        committee_final_score?: number;
    };
    quality_gate?: {
        wf_ic_ir?: number;
        pkf_ic?: number;
        bootstrap_ci_lower?: number;
        param_sensitivity?: number;
        run_correction_mode?: string;
        deflated_sharpe_proxy?: number;
        pbo_proxy?: number;
        reality_check_pvalue_proxy?: number;
        spa_pvalue_proxy?: number;
        multiple_testing_mode?: string;
        deflated_sharpe_ratio?: number;
        deflated_sharpe_reference_sharpe?: number;
        deflated_sharpe_effective_trials?: number;
        pbo?: number;
        white_reality_check_pvalue?: number;
        hansen_spa_pvalue?: number;
        multiple_testing?: Record<string, unknown>;
        reasons?: string[];
        reason_codes?: string[];
    };
    run_correction?: {
        mode?: string;
        raw_sharpe_proxy?: number;
        deflated_sharpe_proxy?: number;
        pbo_proxy?: number;
        reality_check_pvalue_proxy?: number;
        spa_pvalue_proxy?: number;
        multiple_testing_mode?: string;
        deflated_sharpe_ratio?: number;
        deflated_sharpe_reference_sharpe?: number;
        deflated_sharpe_effective_trials?: number;
        pbo?: number;
        white_reality_check_pvalue?: number;
        hansen_spa_pvalue?: number;
        multiple_testing?: Record<string, unknown>;
    };
    constraint_check?: {
        intersection_ratio?: number;
        constraint_violation?: string | null;
        expansion_applied?: boolean;
        expansion_reason?: string | null;
        expansion_source?: string | null;
        target_symbol_policy?: string | null;
    };
    validation_profile?: {
        profile?: string | null;
        validation_focus?: string | null;
        primary_validation_layer?: string | null;
    };
    event_window_config?: Record<string, unknown>;
    position_assumption?: string | null;
    cost_assumptions?: Record<string, unknown>;
    explicit_cost_breakdown?: Record<string, unknown>;
    implicit_cost_breakdown?: Record<string, unknown>;
    backtest_assumptions?: Record<string, unknown>;
    attempt_adjustment?: {
        attempt_count?: number;
        task_attempt_count?: number;
        external_llm_attempt_count?: number;
        selection_ratio?: number;
        penalty?: number;
        factory_attempt_count?: number;
        factory_selected_count?: number;
        task_selected_count?: number;
        external_llm_selected_count?: number;
    };
    committee_review?: {
        decision?: string;
        final_score?: number;
        rank?: number;
        is_champion?: boolean;
        planner_score?: number;
        risk_score?: number;
        feasibility_score?: number;
        execution_score?: number;
        capacity_score?: number;
        task_alignment_score?: number;
        novelty_score?: number;
        planner_context?: Record<string, unknown>;
        task_alignment_context?: Record<string, unknown>;
        alignment_issues?: string[];
        execution_issues?: string[];
        capacity_issues?: string[];
        suggestions?: string[];
        accept_blockers?: string[];
    };
    task_signature?: string | null;
    refresh_mode?: string | null;
    task_preference?: {
        preferred_strategy_types?: string[];
        preference_strength?: string | null;
        preference_reason?: string | null;
        override_applied?: boolean;
    };
    dedup_report?: {
        duplicate?: boolean;
        match_type?: string | null;
        param_similarity?: number;
        vector_similarity?: number;
        reason?: string;
    };
};

export type StrategyEventsResponse = {
    events?: Array<{
        event_type?: string;
        from_status?: string | null;
        to_status?: string;
        actor_id?: string;
        reason?: string;
        created_at?: string;
        metadata?: Record<string, unknown>;
    }>;
    count?: number;
};

export type IncubationOverviewResponse = {
    status?: string;
    sharpe_ratio?: number;
    max_drawdown?: number;
    total_signals?: number;
    minimum_signal_count?: number;
    hit_rate_5d?: number | null;
    forward_ic_5d?: number | null;
    forward_sharpe_5d?: number | null;
    promotion_ready?: boolean;
    deprecation_risk?: boolean;
    blockers?: string[];
    risk_flags?: string[];
    observed_forward_days?: number[];
    missing_forward_days?: number[];
    forward_returns?: Array<{
        label?: string;
        hit_rate?: number | null;
        forward_ic?: number | null;
        forward_sharpe?: number | null;
    }>;
    blockers_by_period?: Record<string, string[]>;
    risk_flags_by_period?: Record<string, string[]>;
    validation_grade?: string | null;
};

export type IncubationAccount = {
    strategy_id?: string;
    account_id?: string;
    stage?: string;
    status?: string;
    source_run_id?: string;
    metadata?: Record<string, unknown>;
};

export type IncubationMetric = {
    metric_date?: string;
    account_id?: string;
    stage?: string;
    decision?: string;
    nav?: number;
    total_value?: number;
    cash?: number;
    market_value?: number;
    daily_return?: number;
    max_drawdown?: number;
    sharpe_ratio?: number;
    hit_rate_5d?: number;
    forward_ic_5d?: number;
    forward_sharpe_5d?: number;
    total_signals?: number;
    total_orders?: number;
    total_trades?: number;
    turnover_rate?: number;
    exposure_rate?: number;
    alpha_decay?: number;
    drift_score?: number;
};

export type PaperAccount = PaperTradingAccount & {
    id?: string;
    name?: string;
};

export type PaperPosition = PaperTradingPosition;

export type PaperOrder = PaperTradingPendingOrder;

export type PaperNav = PaperTradingNavPoint;

export type PaperAccountResponse = {
    account?: PaperAccount | null;
    binding?: IncubationAccount | null;
    positions?: PaperPosition[];
    latest_nav?: PaperNav | null;
    order_summary?: {
        total_orders?: number;
        total_trades?: number;
        trade_amount?: number;
    };
};

export type IncubationPipelineSnapshot = {
    id?: number;
    strategy_id?: string;
    account_id?: string | null;
    pipeline_stage?: string;
    pipeline_status?: string;
    observed_days?: number;
    promote_streak?: number;
    halt_streak?: number;
    latest_decision?: string;
    readiness_score?: number;
    next_action?: string;
    auto_review?: boolean;
    auto_promoted?: boolean;
    blockers?: string[];
    risk_flags?: string[];
    summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    evaluated_at?: string;
};

export type RuntimeRiskSnapshot = {
    id?: number;
    strategy_id?: string;
    account_id?: string | null;
    posture_level?: string;
    escalation_level?: number;
    control_mode?: string;
    open_event_count?: number;
    critical_open_count?: number;
    warning_open_count?: number;
    recommended_action?: string;
    recovery_eligible?: boolean;
    blockers?: string[];
    summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    evaluated_at?: string;
};

export type RiskEvent = {
    id?: number;
    severity?: string;
    event_type?: string;
    action?: string;
    status?: string;
    title?: string;
    reason?: string;
    detected_at?: string;
    payload?: Record<string, unknown>;
};

export type RuntimeControl = {
    strategy_id?: string;
    account_id?: string | null;
    control_mode?: string;
    status?: string;
    source?: string;
    trigger_event_type?: string | null;
    reason?: string | null;
    action_summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    activated_at?: string;
    released_at?: string | null;
    updated_at?: string;
};

export type RuntimeAlert = {
    alert_id?: number;
    strategy_id?: string;
    account_id?: string | null;
    alert_key?: string;
    category?: string;
    severity?: string;
    status?: string;
    title?: string;
    message?: string;
    escalation_level?: number;
    channels?: string[];
    related_event_ids?: number[];
    metadata?: Record<string, unknown>;
    source?: string;
    acknowledged_by?: string | null;
    acknowledged_at?: string | null;
    resolved_at?: string | null;
    created_at?: string;
    updated_at?: string;
};

export type PromotionReview = {
    id?: number;
    strategy_id?: string;
    account_id?: string | null;
    review_source?: string;
    stage?: string;
    status?: string;
    recommendation?: string;
    score?: number;
    blockers?: string[];
    risk_flags?: string[];
    summary?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
    reviewed_at?: string;
};

export type DomainProjection = {
    strategy_id?: string;
    current_status?: string;
    aggregate_version?: number;
    status_event_count?: number;
    domain_event_count?: number;
    open_risk_count?: number;
    runtime_control_mode?: string;
    runtime_control_status?: string;
    latest_promotion_status?: string;
    latest_promotion_recommendation?: string;
    latest_incubation_decision?: string;
    ai_cycle_count?: number;
    runtime_cycle_count?: number;
    last_status_event_at?: string;
    last_domain_event_at?: string;
    phases?: Record<string, boolean>;
    timeline?: Array<{
        timestamp?: string;
        event_type?: string;
        source?: string;
        summary?: string;
    }>;
};

export type ProjectionSnapshot = {
    id?: number;
    strategy_id?: string;
    projection_type?: string;
    aggregate_version?: number;
    current_status?: string;
    runtime_control_mode?: string;
    timeline_count?: number;
    projection?: DomainProjection;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    rebuilt_at?: string;
};

export type VectorProfile = {
    id?: number;
    profile_id?: number;
    strategy_id?: string;
    profile_type?: string;
    vector_method?: string;
    metric?: string;
    vector_dim?: number;
    signature?: string;
    backend?: string;
    index_name?: string;
    index_version?: string;
    similarity?: number;
    coarse_score?: number;
    bucket_id?: string | null;
    query_bucket_id?: string | null;
    candidate_count?: number;
    retrieval_mode?: string;
    metadata?: Record<string, unknown>;
};

export type VectorIndexSnapshot = {
    id?: number;
    index_name?: string;
    index_version?: string;
    status?: string;
    profile_type?: string;
    vector_method?: string;
    metric?: string;
    backend?: string;
    profile_count?: number;
    bucket_count?: number;
    vector_dim?: number;
    centroids?: Array<{
        bucket_id?: string;
        size?: number;
        neighbors?: string[];
        mean_similarity?: number;
    }>;
    metadata?: Record<string, unknown>;
    task_run_id?: number | null;
    source?: string;
    built_at?: string;
    activated_at?: string;
    created_at?: string;
};

export type DomainEvent = {
    id?: number;
    strategy_id?: string | null;
    aggregate_type?: string;
    aggregate_id?: string | null;
    event_type?: string;
    source?: string;
    severity?: string;
    correlation_id?: string | null;
    payload?: Record<string, unknown>;
    created_at?: string;
};

export type AiExperiment = {
    experiment_id?: string;
    strategy_id?: string | null;
    parent_strategy_id?: string | null;
    generated_strategy_id?: string | null;
    task_run_id?: number | null;
    source?: string;
    generator_type?: string;
    optimizer_type?: string;
    status?: string;
    hypothesis?: string;
    evaluation?: {
        committee_review?: {
            final_score?: number;
            decision?: string;
            review_mode?: string;
            rank?: number;
            is_champion?: boolean;
            planner_score?: number;
            risk_score?: number;
            feasibility_score?: number;
            execution_score?: number;
            capacity_score?: number;
            task_alignment_score?: number;
            novelty_score?: number;
            planner_context?: Record<string, unknown>;
            task_alignment_context?: Record<string, unknown>;
            alignment_issues?: string[];
            execution_issues?: string[];
            capacity_issues?: string[];
            suggestions?: string[];
            accept_blockers?: string[];
        };
    };
    result?: Record<string, unknown>;
    created_at?: string;
    updated_at?: string;
};

export type TaskRun = {
    id?: number;
    strategy_id?: string | null;
    task_name?: string;
    task_scope?: string;
    task_key?: string;
    status?: string;
    trace_id?: string;
    payload?: Record<string, unknown>;
    result?: Record<string, unknown>;
    error?: string | null;
    started_at?: string;
    completed_at?: string | null;
};

export type ListResponse<T> = {
    items?: T[];
    count?: number;
    latest?: T | null;
};

export type StrategyDetailResponse = {
    dto_version?: string;
    strategy?: StrategyCore;
    metrics?: StrategyMetric[];
    reviews?: StrategyReview[];
    nav_series?: number[];
    latest_quality_report?: ReviewReportResponse | null;
    incubation_account?: IncubationAccount | null;
    latest_incubation_metric?: IncubationMetric | null;
    latest_promotion_review?: PromotionReview | null;
    latest_projection_snapshot?: ProjectionSnapshot | null;
    latest_vector_index_snapshot?: VectorIndexSnapshot | null;
    latest_incubation_pipeline_snapshot?: IncubationPipelineSnapshot | null;
    latest_runtime_risk_snapshot?: RuntimeRiskSnapshot | null;
    runtime_control?: RuntimeControl | null;
    runtime_alerts?: RuntimeAlert[];
    open_risk_events?: RiskEvent[];
    vector_profiles?: VectorProfile[];
    similar_vector_profiles?: VectorProfile[];
    domain_events?: DomainEvent[];
    task_runs?: TaskRun[];
    view_model?: {
        quality?: {
            latest_report?: ReviewReportResponse | null;
        };
        incubation?: {
            account?: IncubationAccount | null;
            latest_metric?: IncubationMetric | null;
            latest_pipeline_snapshot?: IncubationPipelineSnapshot | null;
        };
        runtime?: {
            control?: RuntimeControl | null;
            latest_risk_snapshot?: RuntimeRiskSnapshot | null;
            alerts?: RuntimeAlert[];
            risk_events?: RiskEvent[];
        };
        vectors?: {
            profiles?: VectorProfile[];
            similar_profiles?: VectorProfile[];
            latest_index_snapshot?: VectorIndexSnapshot | null;
        };
        domain?: {
            events?: DomainEvent[];
            task_runs?: TaskRun[];
            latest_projection_snapshot?: ProjectionSnapshot | null;
        };
    };
};
