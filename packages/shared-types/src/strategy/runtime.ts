import type {
    SignalQualitySnapshot,
    ExecutionQualitySnapshot,
    FactoryCompletionIssue,
    FactoryGateStageResult,
    StrategyPredictionTraceLedgerView,
} from './factory';
import type { StrategyTrustedInfo } from './common';
import type {
    PaperTradingAccount,
    PaperTradingNavPoint,
    PaperTradingPendingOrder,
    PaperTradingPosition,
} from '../paper-trading';

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

export type StrategySignalQuality = {
    coverage_ratio?: number | null;
    primary_skill_lcb?: number | null;
};

export type StrategyExecutionAuditSummary = {
    execution_conversion_efficiency?: number | null;
};

export type StrategyExecutionQuality = {
    audit?: StrategyExecutionAuditSummary;
    execution_quality_label?: string | null;
    execution_conversion_efficiency?: number | null;
    nav_conversion_proxy?: number | null;
};

export type StrategyExecutionDiagnostics = {
    diagnostic_only?: boolean;
    execution_conversion_efficiency?: number | null;
    remediation_action?: string | null;
};

export type StrategyRuntimePlaybookProvenance = {
    derivation_labels?: string[];
    derived_from_defaults?: boolean | null;
};

export type StrategySemanticLineage = {
    claim_to_trade_plan_map?: {
        claim_to_trade_step_ids?: Record<string, unknown>;
    };
    trade_plan_to_dsl_map?: {
        trade_step_to_dsl_sections?: Record<string, unknown>;
    };
    runtime_playbook_provenance?: StrategyRuntimePlaybookProvenance;
};

export type StrategyExecutionLineageAction = {
    signal_id?: string | number | null;
    signal_date?: string;
    code?: string;
    runtime_action_reason?: string | null;
    applied_claim_id?: string | null;
    applied_trade_step_id?: string | null;
    lineage_status?: string | null;
    runtime_action_source?: string | null;
};

export type StrategyExecutionLineage = {
    claim_count?: number | null;
    trade_step_count?: number | null;
    mapped_trade_step_count?: number | null;
    runtime_action_count?: number | null;
    unmapped_runtime_action_count?: number | null;
    lineage_status_counts?: Record<string, number>;
    runtime_action_reason_counts?: Record<string, number>;
    recent_runtime_actions?: StrategyExecutionLineageAction[];
};

export type StrategyQualityLabel = 'weak' | 'insufficient_evidence' | 'mixed' | 'strong';

export type StrategyConfidenceContractStatus =
    | 'missing'
    | 'insufficient'
    | 'diagnostic_ready'
    | 'comparable_ready';

export type StrategyHardGateResult = {
    passed?: boolean;
    pipeline_stage?: string | null;
    signal_stage_without_execution_gate?: string | null;
    execution_audit_gate_status?: string | null;
    reasons?: string[];
};

export type StrategyEvidenceAlignmentAudit = {
    market_fact_gate_status?: string | null;
    evidence_debt_reasons?: string[];
};

export type StrategyReviewReportSummary = {
    status_after_review?: string;
    validation_grade?: string;
    raw_validation_grade?: string;
    effective_validation_grade?: string;
    validation_grade_adjustment_reason?: string;
    validation_total_score?: number;
    raw_validation_total_score?: number;
    review_source?: string;
    primary_validation_layer?: string;
    refresh_mode?: string;
    committee_decision?: string;
    committee_final_score?: number;
    evidence_alignment_status?: string | null;
    evidence_gate_status?: string | null;
    pool_profile?: string | null;
    volatility_bucket?: string | null;
    hard_fact_count?: number;
    degraded_fact_count?: number;
    evidence_debt_reasons?: string[];
    risk_regime_fit?: string | null;
    stop_rule_source?: string | null;
    contradiction_count?: number;
    proxy_dependency_score?: number;
    legacy_semantic_contract?: boolean;
    prediction_trace_id?: string | null;
    trace_id?: string | null;
    research_protocol_version?: string;
    candidate_contract_version?: string;
    spec_completeness?: string;
    field_provenance_summary?: Record<string, unknown>;
    completion_issues?: FactoryCompletionIssue[];
    gate_a?: FactoryGateStageResult;
    gate_b?: FactoryGateStageResult;
    gate_c?: FactoryGateStageResult;
    signal_quality_snapshot?: SignalQualitySnapshot;
    execution_quality_snapshot?: ExecutionQualitySnapshot;
    prediction_trace_ledger?: StrategyPredictionTraceLedgerView;
    signal_quality?: StrategySignalQuality;
    execution_quality?: StrategyExecutionQuality;
    prediction_quality_label?: StrategyQualityLabel;
    execution_quality_label?: StrategyQualityLabel;
    quality_diagnosis?: string | null;
    quality_diagnosis_reasons?: string[];
    confidence_contract_status?: StrategyConfidenceContractStatus;
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
    raw_signal_count?: number;
    signals_with_forward_returns_count?: number;
    observed_forward_return_count?: number;
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
    pool_profile?: string | null;
    volatility_bucket?: string | null;
    liquidity_bucket?: string | null;
    evidence_chain?: Record<string, unknown>;
    prediction_contract?: Record<string, unknown>;
    confidence_contract?: Record<string, unknown>;
    evidence_alignment_audit?: StrategyEvidenceAlignmentAudit;
    legacy_semantic_contract?: boolean;
    contradiction_count?: number;
    proxy_dependency_score?: number;
    reports?: Array<{
        report_type?: string;
        updated_at?: string;
        prediction_trace_id?: string | null;
        trace_id?: string | null;
        research_protocol_version?: string;
        candidate_contract_version?: string;
        spec_completeness?: string;
        field_provenance_summary?: Record<string, unknown>;
        completion_issues?: FactoryCompletionIssue[];
        gate_a?: FactoryGateStageResult;
        gate_b?: FactoryGateStageResult;
        gate_c?: FactoryGateStageResult;
        summary?: StrategyReviewReportSummary;
    }>;
    prediction_trace_id?: string | null;
    trace_id?: string | null;
    research_protocol_version?: string;
    candidate_contract_version?: string;
    spec_completeness?: string;
    field_provenance_summary?: Record<string, unknown>;
    completion_issues?: FactoryCompletionIssue[];
    gate_a?: FactoryGateStageResult;
    gate_b?: FactoryGateStageResult;
    gate_c?: FactoryGateStageResult;
    summary?: StrategyReviewReportSummary;
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
    strategy_id?: string;
    strategy_name?: string;
    status?: string;
    sharpe_ratio?: number;
    max_drawdown?: number;
    total_signals?: number;
    raw_signal_count?: number;
    signals_with_forward_returns_count?: number;
    observed_forward_return_count?: number;
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
    raw_validation_grade?: string | null;
    effective_validation_grade?: string | null;
    validation_grade_adjustment_reason?: string | null;
    raw_b_or_above?: boolean;
    raw_validation_total_score?: number | null;
    validation_total_score?: number | null;
    candidate_family?: string | null;
    holding_period_bucket?: string | null;
    validation_focus?: string | null;
    trade_density?: number | null;
    post_cost_sharpe?: number | null;
    deflated_sharpe_ratio?: number | null;
    pbo?: number | null;
    quality_passed?: boolean;
    strict_incubation_ready?: boolean | null;
    strict_incubation_blocked?: boolean | null;
    incubation_candidate_ready?: boolean | null;
    live_candidate_ready?: boolean | null;
    admission_stage?: string | null;
    incubation_pass_mode?: string | null;
    admission_block_reasons?: string[];
    gate_blockers?: string[];
    strict_live_alignment_gap?: boolean;
    strict_live_alignment_status?: string | null;
    signal_quality?: StrategySignalQuality;
    signal_quality_snapshot?: SignalQualitySnapshot;
    execution_quality?: StrategyExecutionQuality;
    execution_quality_snapshot?: ExecutionQualitySnapshot;
    execution_diagnostics?: StrategyExecutionDiagnostics;
    prediction_trace_ledger?: StrategyPredictionTraceLedgerView;
    prediction_quality_label?: StrategyQualityLabel;
    execution_quality_label?: StrategyQualityLabel;
    quality_diagnosis?: string | null;
    quality_diagnosis_reasons?: string[];
    confidence_contract_status?: StrategyConfidenceContractStatus;
    confidence_diagnostics?: Record<string, unknown>;
    runtime_bootstrap_eligible?: boolean | null;
    runtime_bootstrap_reason?: string | null;
    runtime_bootstrap_budget_tier?: string | null;
    runtime_playbook_present?: boolean | null;
    execution_semantic_mode?: 'compiled_dsl' | 'builtin_legacy' | 'missing_executable_contract' | string | null;
    execution_semantic_gap?: boolean | null;
    execution_semantic_gap_reasons?: string[];
    dsl_required?: boolean | null;
    dsl_compiled?: boolean | null;
    instrument_profile?: Record<string, unknown>;
    runtime_playbook_provenance?: StrategyRuntimePlaybookProvenance;
    semantic_lineage?: StrategySemanticLineage;
    execution_lineage?: StrategyExecutionLineage;
    hard_gate_result?: StrategyHardGateResult;
    pipeline_stage?: string | null;
    execution_audit_gate_status?: string | null;
    signal_vacuum_days?: number | null;
    stage_clock_days?: number | null;
    remediation_action?: string | null;
    remediation_reason?: string | null;
    budget_action?: string | null;
    runtime_control_mode?: string | null;
    revision_required?: boolean;
    cleanup_recommended?: boolean;
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
    hit_rate_lcb_5d?: number;
    skill_lcb_5d?: number;
    effective_n_5d?: number;
    recent_hit_rate_5d?: number;
    recent_skill_lcb_5d?: number;
    stability_gap_5d?: number;
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
        filled_orders?: number;
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
    priority_score?: number;
    gate_status?: string;
    gate_reasons?: string[];
    hard_gate_result?: StrategyHardGateResult;
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

export type ExecutionAuditAcceptanceMatrix = {
    schema_ready?: boolean;
    migration_ready?: boolean;
    orders_position_link_ready?: boolean;
    trades_position_link_ready?: boolean;
    native_lineage_ready?: boolean;
    fill_round_trip_ready?: boolean;
    hard_gate_ready?: boolean;
    trade_evidence_ready?: boolean;
    overall_ready?: boolean;
};

export type ExecutionAuditCoverageSummary = {
    position_id_ratio?: number | null;
};

export type ExecutionAuditVerification = {
    coverage?: {
        paper_orders?: ExecutionAuditCoverageSummary;
        paper_trades?: ExecutionAuditCoverageSummary;
    };
};

export type ExecutionAuditTradeAuditSummary = {
    realized_trade_count?: number | null;
    incomplete_position_count?: number | null;
    execution_audit_gate_status?: string | null;
};

export type ExecutionAuditAcceptanceResponse = {
    status?: string;
    strategy_id?: string | null;
    method?: string;
    backfill_executed?: boolean;
    backfill_result?: Record<string, unknown> | null;
    acceptance_matrix?: ExecutionAuditAcceptanceMatrix;
    blockers?: string[];
    verification?: ExecutionAuditVerification;
    trade_audit_summary?: ExecutionAuditTradeAuditSummary | null;
    recommendations?: string[];
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

export type StrategyDetailViewModel = {
    quality?: {
        latest_report?: ReviewReportResponse | null;
    };
    incubation?: {
        overview?: IncubationOverviewResponse | null;
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

export type StrategyDetailResponse = {
    dto_version?: string;
    strategy?: StrategyCore;
    metrics?: StrategyMetric[];
    reviews?: StrategyReview[];
    nav_series?: number[];
    latest_quality_report?: ReviewReportResponse | null;
    incubation_overview?: IncubationOverviewResponse | null;
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
    view_model?: StrategyDetailViewModel;
};
