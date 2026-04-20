import type { FactoryRunSummary } from './runs';
import type {
    FactoryFeedbackSummary,
    FactoryValidationFamilyQualityPanelItem,
} from './core';

export type FactoryGovernanceReasonTopEntry = {
    reason?: string;
    reason_code?: string;
    count?: number;
};

export type FactoryGovernanceCountMap = Record<string, number>;

export type FactoryGovernanceSupportMap = Record<string, boolean>;

export type FactoryGovernanceBacktestThresholdsByType = Record<string, Record<string, unknown>>;

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
    submission_action_trigger?: string | null;
    submission_action_type?: string | null;
    primary_validation_layer?: string | null;
    refresh_mode?: string | null;
    position_assumption?: string | null;
    task_signature?: string | null;
    candidate_family?: string | null;
    holding_period_bucket?: string | null;
    validation_grade?: string | null;
    raw_validation_grade?: string | null;
    effective_validation_grade?: string | null;
    validation_grade_adjustment_reason?: string | null;
    raw_validation_total_score?: number | null;
    validation_total_score?: number | null;
    raw_b_or_above?: boolean;
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
    candidate_local_attempt_count?: number;
    task_local_attempt_count?: number;
    cohort_effective_trials?: number;
    economic_semantics_missing?: boolean;
    created_strategy_pool?: boolean;
    created_audit_only?: boolean;
    refreshed_existing?: boolean;
    formal_track_requested?: boolean;
    formal_track_eligible?: boolean;
    formal_track_blockers?: string[];
    hard_failures?: FactoryHardFailure[];
    live_candidate_ready?: boolean;
    live_review_ready?: boolean;
    runtime_bootstrap_eligible?: boolean | null;
    runtime_bootstrap_reason?: string | null;
    runtime_bootstrap_budget_tier?: string | null;
    runtime_playbook_present?: boolean | null;
    stage_clock_days?: number | null;
    signal_vacuum_days?: number | null;
    remediation_action?: string | null;
    remediation_reason?: string | null;
    paper_lane_ready?: boolean | null;
    direct_trade_candidate?: boolean;
};

export type FactoryGovernanceEvidenceStrategyBrief = FactoryGovernanceStrategyBrief & {
    lineage_id?: string | null;
    vector_backend?: string | null;
    has_cost_assumptions?: boolean;
    has_execution_reality?: boolean;
    has_multiple_testing_registry?: boolean;
};

export type FactoryGateStageResult = {
    contract_version?: string;
    gate_name?: string;
    stage?: string;
    decision?: string;
    status?: string;
    blocking_reasons?: Array<string | FactoryGovernanceReasonTopEntry>;
    hard_failures?: FactoryHardFailure[];
    evidence_gap_codes?: string[];
    artifact_ids?: string[];
    retrieval_context_ids?: string[];
    trace_ids?: string[];
    family_outcome_summary?: FactoryGateFamilyOutcomeSummary;
    warnings?: string[];
    revision_actions?: string[];
    evidence_refs?: string[];
    legacy_gate_mapping?: string[];
    spec_completeness?: string;
    input_count?: number;
    gate_0_passed?: number;
    pre_gate_passed?: number;
    gate_1_passed?: number;
    spec_completeness_counts?: Record<string, number>;
    gate_2_input?: number;
    gate_2_passed?: number;
    gate_2_failed?: number;
    gate_3_input?: number;
    gate_3_passed?: number;
    gate_3_failed?: number;
    gate_3_provisional_passed?: number;
    signal_quality_distribution?: Record<string, number>;
    execution_quality_distribution?: Record<string, number>;
    execution_audit_gate_status_distribution?: Record<string, number>;
    hard_gate_result_distribution?: Record<string, number>;
    promotion_ready_count?: number;
    promotion_ready_rate?: number;
};

export type FactoryProtocolVersionsSummary = {
    research_protocol_version_counts?: Record<string, number>;
    candidate_contract_version_counts?: Record<string, number>;
    spec_completeness_counts?: Record<string, number>;
};

export type FactoryHardFailure = {
    reason_code?: string;
    issue?: string;
    field?: string;
    severity?: string;
    decision?: string;
    message?: string;
    detail?: string;
};

export type FactoryCompletionIssue = {
    field?: string;
    issue?: string;
    reason_code?: string;
    severity?: string;
    decision?: string;
    provenance?: string;
    message?: string;
};

export type FactoryGateFamilyOutcomeSummary = {
    family_counts?: FactoryGovernanceCountMap;
    status_counts?: FactoryGovernanceCountMap;
    submission_lane_counts?: FactoryGovernanceCountMap;
};

export type FactoryPredictionTraceSummary = {
    contract_version?: string;
    trace_count?: number;
    missing_count?: number;
    sample_trace_ids?: string[];
};

export type FactoryPredictionTraceLedgerNode = Record<string, unknown> & {
    available?: boolean;
    source_mode?: 'entity_backed' | 'summary_fallback' | string;
    count?: number;
    ids?: string[];
    status?: string | null;
    as_of?: string | null;
};

export type FactoryPredictionTraceLedgerEntry = {
    prediction_trace_id?: string | null;
    source_count?: number;
    artifact_ids?: string[];
    retrieval_context_ids?: string[];
    family_outcome_summary?: FactoryGateFamilyOutcomeSummary;
    hypothesis_spec?: FactoryPredictionTraceLedgerNode;
    signal_event?: FactoryPredictionTraceLedgerNode;
    intended_order?: FactoryPredictionTraceLedgerNode;
    actual_fill?: FactoryPredictionTraceLedgerNode;
    position_round_trip?: FactoryPredictionTraceLedgerNode;
    pnl_audit_summary?: FactoryPredictionTraceLedgerNode;
    gate_decisions?: StrategyPredictionTraceGateDecisions;
    evidence_gap_codes?: string[];
};

export type FactoryPredictionTraceLedgerSummary = {
    contract_version?: string;
    trace_count?: number;
    missing_trace_count?: number;
    entries?: FactoryPredictionTraceLedgerEntry[];
};

export type StrategyPredictionTraceGateDecisions = {
    execution_audit_gate_status?: string | null;
    promotion_ready?: boolean;
    hard_gate_passed?: boolean;
    failure_reasons?: string[];
};

export type StrategyPredictionTraceLedgerView = {
    contract_version?: string;
    prediction_trace_id?: string | null;
    strategy_id?: string | null;
    hypothesis_spec?: FactoryPredictionTraceLedgerNode;
    signal_event?: FactoryPredictionTraceLedgerNode;
    intended_order?: FactoryPredictionTraceLedgerNode;
    actual_fill?: FactoryPredictionTraceLedgerNode;
    position_round_trip?: FactoryPredictionTraceLedgerNode;
    pnl_audit_summary?: FactoryPredictionTraceLedgerNode;
    gate_decisions?: StrategyPredictionTraceGateDecisions;
    evidence_gap_codes?: string[];
};

export type SignalQualitySnapshot = {
    contract_version?: string;
    status?: 'insufficient_evidence' | 'weak' | 'candidate' | 'strong' | string;
    primary_horizon?: number;
    secondary_horizon?: number;
    primary_effective_n?: number;
    secondary_effective_n?: number;
    primary_skill_lcb?: number | null;
    secondary_skill_lcb?: number | null;
    recent_primary_skill_lcb?: number | null;
    stability_gap?: number | null;
    coverage_ratio?: number;
    signal_coverage_ratio?: number | null;
    observed_forward_days?: number[];
    missing_forward_days?: number[];
};

export type ExecutionQualitySnapshot = {
    contract_version?: string;
    status?: 'passed' | 'insufficient_evidence' | string;
    evidence_status?: string | null;
    evidence_gap_codes?: string[];
    execution_audit_gate_status?: string;
    realized_trade_count?: number;
    order_count?: number;
    trade_count?: number;
    mapped_position_count?: number;
    incomplete_position_count?: number;
    realized_pnl_total?: number | null;
    fill_rate?: number | null;
    round_trip_close_rate?: number | null;
    trade_expectancy?: number | null;
    pnl_conversion_efficiency?: number | null;
    execution_conversion_efficiency?: number | null;
    realized_slippage_vs_model?: number | null;
    missed_trade_ratio?: number | null;
    hard_gate_ready?: boolean;
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
    backtest_thresholds_by_type?: FactoryGovernanceBacktestThresholdsByType;
    gate_3_failure_reason_topn?: FactoryGovernanceReasonTopEntry[];
    gate_a?: FactoryGateStageResult;
    gate_b?: FactoryGateStageResult;
    gate_c?: FactoryGateStageResult;
    legacy_gate_mapping?: Record<string, unknown>;
    protocol_versions?: FactoryProtocolVersionsSummary;
    prediction_trace_summary?: FactoryPredictionTraceSummary;
    prediction_trace_ledger?: FactoryPredictionTraceLedgerSummary;
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
    validation_family_quality_panel?: FactoryValidationFamilyQualityPanelItem[];
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
    gate_artifact_v2?: FactoryGovernanceGateArtifact;
    dedup_artifact?: FactoryGovernanceDedupArtifact;
    submission_artifact?: FactoryGovernanceSubmissionArtifact;
    evidence_artifact?: FactoryGovernanceEvidenceArtifact;
    source_chain?: string[];
    gate_a?: FactoryGateStageResult;
    gate_b?: FactoryGateStageResult;
    gate_c?: FactoryGateStageResult;
    legacy_gate_mapping?: Record<string, unknown>;
    protocol_versions?: FactoryProtocolVersionsSummary;
    prediction_trace_summary?: FactoryPredictionTraceSummary;
    prediction_trace_ledger?: FactoryPredictionTraceLedgerSummary;
};

export type FactoryRunDetailResponse = {
    dto_version?: string;
    run_id?: string;
    trace_id?: string | null;
    prediction_trace_id?: string | null;
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
    gate_artifact_v2?: FactoryGovernanceGateArtifact;
    dedup_artifact?: FactoryGovernanceDedupArtifact;
    submission_artifact?: FactoryGovernanceSubmissionArtifact;
    governance_evidence_artifact?: FactoryGovernanceEvidenceArtifact;
    gate_a?: FactoryGateStageResult;
    gate_b?: FactoryGateStageResult;
    gate_c?: FactoryGateStageResult;
    protocol_versions?: FactoryProtocolVersionsSummary;
    prediction_trace_summary?: FactoryPredictionTraceSummary;
    prediction_trace_ledger?: FactoryPredictionTraceLedgerSummary;
    feedback_summary?: FactoryFeedbackSummary;
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
