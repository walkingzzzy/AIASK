import type { StrategyManagerAction } from './contracts.generated';

export const STRATEGY_CAPABILITY_GAP_ISSUE_KINDS = [
    'backend_without_frontend',
    'frontend_without_backend',
    'internal_not_user_exposed',
    'naming_or_field_mismatch',
] as const;

export type StrategyCapabilityGapIssueKind = typeof STRATEGY_CAPABILITY_GAP_ISSUE_KINDS[number];

export type StrategyCapabilityGapSeverity = 'p0' | 'p1' | 'p2' | 'p3';

export type StrategyCapabilityLayerStatus = 'present' | 'partial' | 'absent' | 'internal' | 'unknown';

export type StrategyCapabilityGapIssue = {
    kind: StrategyCapabilityGapIssueKind;
    severity: StrategyCapabilityGapSeverity;
    summary: string;
    user_impact: string;
    evidence: string[];
};

export type StrategyCapabilityMcpLayer = {
    status: StrategyCapabilityLayerStatus;
    tool_names: string[];
    manager_actions: StrategyManagerAction[];
    workflow_tools?: string[];
    registered: boolean;
    notes?: string | null;
};

export type StrategyCapabilityArtifactLayer = {
    status: StrategyCapabilityLayerStatus;
    artifact_ids: string[];
    artifact_tables?: string[];
    notes?: string | null;
};

export type StrategyCapabilityBffLayer = {
    status: StrategyCapabilityLayerStatus;
    endpoints: string[];
    dto_versions?: string[];
    notes?: string | null;
};

export type StrategyCapabilityFrontendLayer = {
    status: StrategyCapabilityLayerStatus;
    entry_points: string[];
    consumed_endpoints: string[];
    page_surfaces: string[];
    exposed_to_user: boolean;
    notes?: string | null;
};

export type StrategyCapabilityMatchStatus = 'matched' | 'gap' | 'mismatch' | 'internal';

export type StrategyCapabilityMatchRow = {
    id: string;
    label: string;
    domain: 'market' | 'personal' | 'factory' | 'incubation' | 'runtime' | 'vector' | 'domain' | 'ai' | 'operator';
    user_intent: string;
    status: StrategyCapabilityMatchStatus;
    severity: StrategyCapabilityGapSeverity;
    mcp: StrategyCapabilityMcpLayer;
    factory_artifacts: StrategyCapabilityArtifactLayer;
    bff: StrategyCapabilityBffLayer;
    frontend: StrategyCapabilityFrontendLayer;
    issues: StrategyCapabilityGapIssue[];
    user_visible_impact: string;
};

export type StrategyCapabilityGapSummary = {
    total: number;
    matched: number;
    gap: number;
    mismatch: number;
    internal: number;
    backend_without_frontend: number;
    frontend_without_backend: number;
    internal_not_user_exposed: number;
    naming_or_field_mismatch: number;
    p0: number;
    p1: number;
    p2: number;
    p3: number;
};

export type StrategyCapabilityDiagnosticsResponse = {
    dto_version: 'strategy_market.capability_diagnostics.v1';
    generated_at: string;
    mcp_contract_version: string;
    layers: ['mcp_manager', 'strategy_factory_artifacts', 'bff_api', 'frontend_surface'];
    mcp_runtime?: {
        reachable: boolean;
        tool_count: number | null;
        expected_tools: number | null;
        matched: boolean;
        source: string;
        message: string;
    } | null;
    summary: StrategyCapabilityGapSummary;
    items: StrategyCapabilityMatchRow[];
    critical_unmatched: StrategyCapabilityMatchRow[];
};
