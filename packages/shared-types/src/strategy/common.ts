import type {
    PaperTradingAccount,
    PaperTradingNavPoint,
    PaperTradingPendingOrder,
    PaperTradingPosition,
} from '../paper-trading';
export {
    STRATEGY_MANAGER_ACTIONS,
    STRATEGY_MANAGER_CONTRACT_VERSION,
    type StrategyManagerAction,
} from './contracts.generated';

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

export type StrategyIncubationSurface = {
    entered_incubator?: boolean;
    pipeline_stage?: string | null;
    stage_source?: string | null;
    account_stage?: string | null;
    account_status?: string | null;
    promotion_ready?: boolean;
    latest_decision?: string | null;
    execution_audit_gate_status?: string | null;
    blocker_count?: number;
    risk_count?: number;
};

export type StrategyRuntimeActionId =
    | 'save_as_personal_strategy'
    | 'open_personal_paper_session'
    | 'view_factory_source'
    | 'ai_analyze_strategy'
    | 'ai_modify_personal_strategy';

export type StrategyRuntimeActionStatus = 'clickable' | 'confirm_required' | 'unavailable';

export type StrategyRuntimeActionEffect = 'navigation' | 'readonly' | 'advisory' | 'stateful';

export type StrategyRuntimeActionEndpoint = {
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE';
    path: string;
    body?: Record<string, unknown> | null;
};

export type StrategyRuntimeActionNavigation = {
    href: string;
    target?: '_self' | '_blank';
};

export type StrategyRuntimeActionConfirm = {
    title?: string;
    message: string;
    confirm_label?: string;
};

export type StrategyRuntimeActionContractItem = {
    id: StrategyRuntimeActionId;
    label: string;
    short_label?: string;
    description?: string;
    status: StrategyRuntimeActionStatus;
    enabled: boolean;
    requires_confirmation: boolean;
    effect: StrategyRuntimeActionEffect;
    endpoint?: StrategyRuntimeActionEndpoint | null;
    navigation?: StrategyRuntimeActionNavigation | null;
    confirm?: StrategyRuntimeActionConfirm | null;
    unavailable_reason?: string | null;
    reason_code?: string | null;
    telemetry_key?: string;
};

export type StrategyRuntimeActionContract = {
    dto_version: 'strategy_market.runtime_actions.v1';
    strategy_id: string;
    generated_at: string;
    source: 'bff.strategy_market.runtime_action_contract';
    actor: {
        authenticated: boolean;
        user_id?: string | null;
        role?: string | null;
        is_admin?: boolean;
    };
    state: {
        owned?: boolean;
        editable?: boolean;
        personal_strategy?: boolean;
        favorited?: boolean;
        paper_session_available?: boolean;
        has_paper_session?: boolean;
        source_strategy_id?: string | null;
    };
    actions: StrategyRuntimeActionContractItem[];
    default_order: StrategyRuntimeActionId[];
    summary: {
        executable_now: StrategyRuntimeActionId[];
        blocked: Array<{
            id: StrategyRuntimeActionId;
            reason: string;
            reason_code?: string | null;
        }>;
    };
};

export type StrategySourceStage = 'candidate' | 'research' | 'governance' | 'available';

export type StrategySourceKind =
    | 'factory_market_view'
    | 'factory_run'
    | 'research_window'
    | 'governance_pool'
    | 'personal_copy'
    | 'manual_market'
    | 'degraded_snapshot'
    | 'unknown';

export type StrategySourceStageEvidence = {
    key: string;
    label: string;
    value: string;
};

export type StrategySourceStageAction = {
    id?: StrategyRuntimeActionId | string;
    label: string;
    status?: StrategyRuntimeActionStatus | string;
    effect?: StrategyRuntimeActionEffect | string;
    href?: string | null;
};

export type StrategySourceStageRestriction = {
    id?: StrategyRuntimeActionId | string;
    label: string;
    reason: string;
    reason_code?: string | null;
};

export type StrategySourceStageExplanation = {
    dto_version: 'strategy_market.source_stage_explanation.v1';
    source_kind: StrategySourceKind;
    source_label: string;
    source_summary: string;
    current_stage: StrategySourceStage;
    stage_label: string;
    stage_summary: string;
    maturity_label: string;
    why_visible: string;
    available_actions: StrategySourceStageAction[];
    restricted_actions: StrategySourceStageRestriction[];
    action_summary: string;
    limitation_reason?: string | null;
    evidence: StrategySourceStageEvidence[];
};

export type Strategy = {
    id: string;
    name: string;
    status?: string;
    strategy_type?: string;
    description?: string;
    subscriber_count?: number;
    favorite_count?: number;
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
    incubation_surface?: StrategyIncubationSurface;
    source_stage_explanation?: StrategySourceStageExplanation;
    runtime_action_contract?: StrategyRuntimeActionContract | null;
    runtime_actions?: StrategyRuntimeActionContractItem[];
} & StrategyTrustedInfo;

export type RankingResponse = { strategies?: Strategy[] } | Strategy[];
