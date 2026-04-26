import type { McpJobRecord } from '../common';
import type { StrategyManagerAction } from './contracts.generated';

export type StrategyActionCoverageKind = 'read' | 'mutation_job' | 'admin_job' | 'internal_only';

export type StrategyActionCoverageItem = {
    action: StrategyManagerAction;
    category: StrategyActionCoverageKind;
    mcp_tool: 'strategy_manager';
    bff_endpoint: string | null;
    web_surface: string | null;
    test_coverage: string | null;
    mapped: boolean;
    core: boolean;
    requires_admin: boolean;
    job_action: boolean;
    notes?: string | null;
};

export type StrategyFactoryReadinessRemediation = {
    code: string;
    label: string;
    description: string;
    primary_action: StrategyManagerAction | 'factor_scheduler_run_now' | 'factor_candidate_registry_refresh' | 'production_sample_top_up';
    endpoint: string;
    job_action: boolean;
    requires_admin: boolean;
    params_hint?: Record<string, unknown>;
};

export type StrategyOperatorJobRequest = {
    action: StrategyManagerAction;
    strategy_id?: string | null;
    params?: Record<string, unknown>;
    timeout_ms?: number | null;
    idempotency_key?: string | null;
    confirmed: boolean;
    confirmation_text?: string | null;
    reason?: string | null;
};

export type StrategyOperatorJobRecord = {
    job: McpJobRecord;
    action: StrategyManagerAction;
    strategy_id: string | null;
    accepted: boolean;
    deduplicated: boolean;
    requires_admin: boolean;
    confirmation_required: boolean;
    poll_path: string;
    submitted_params: Record<string, unknown>;
};

export type StrategyOperatorParityResponse = {
    contract_version: string;
    generated_at: string;
    total_actions: number;
    mapped_actions: number;
    unmapped_actions: number;
    core_actions: number;
    core_unmapped_actions: number;
    job_actions: number;
    coverage: StrategyActionCoverageItem[];
    readiness_remediations: StrategyFactoryReadinessRemediation[];
};
