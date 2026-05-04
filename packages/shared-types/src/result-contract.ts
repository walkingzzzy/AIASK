import type { ToolArgs } from './common';

export const RESULT_VIEWS = [
    'summary',
    'compare',
    'visual',
    'next_step',
] as const;

export type ResultView = typeof RESULT_VIEWS[number];
export const RESULT_STATUSES = [
    'ready',
    'loading',
    'empty',
    'degraded',
    'unavailable',
] as const;

export type ResultStatus = typeof RESULT_STATUSES[number];

export type ResultAction = {
    id: string;
    label: string;
    description?: string;
    actionId?: string;
    payload?: Record<string, unknown>;
};

export type ResultLink = {
    id: string;
    label: string;
    description?: string;
    href: string;
};

export type ResultEvidenceItem = {
    label: string;
    value: string;
    tone?: 'neutral' | 'positive' | 'warning';
};

export type ResultFreshness = {
    updatedAt?: string | null;
    asOf?: string | null;
    label?: string | null;
};

export type ResultPlatformMeta = {
    sourceTool?: string | null;
    sourceChain?: string[];
    degraded?: boolean;
    fallbackReason?: string[];
    requested_keyword?: string | null;
    matched_keyword?: string | null;
    match_confidence?: number | null;
    degraded_reason?: string | null;
    freshnessLabel?: string | null;
    referencePath?: string | null;
};

export type ResultSkillSuggestion = {
    skillId: string;
    label?: string;
    reason?: string;
    supportedTask?: string;
};

export type ResultStrategySuggestion = {
    id: string;
    label: string;
    description?: string;
    href?: string;
    query?: string;
    category?: string;
    task?: string;
};

export type ResultWorkbenchTask = {
    title: string;
    href?: string;
    kind?: string;
    payload?: Record<string, unknown>;
};

export type ResultStateBlock = {
    title: string;
    description: string;
    reason?: string;
    primaryAction?: ResultAction | null;
    secondaryActions?: ResultAction[];
    example?: string;
};

export type ResultContractAliasHit = {
    canonical: string;
    matched: string;
    deprecated?: boolean;
};

export type ResultContractMeta = {
    canonicalTool: string;
    canonicalArgs: ToolArgs;
    argsMatched?: ToolArgs;
    aliasHits?: ResultContractAliasHit[];
    contractVersion: string;
};

export type ResultContract = {
    summary: string;
    status?: ResultStatus;
    availableViews: ResultView[];
    primaryAction?: ResultAction | null;
    secondaryActions?: ResultAction[];
    recommendedActions?: ResultAction[];
    recommendedLinks?: ResultLink[];
    recommendedNextActions?: string[];
    evidence?: ResultEvidenceItem[];
    riskNotes?: string[];
    emptyState?: ResultStateBlock | null;
    degradedState?: ResultStateBlock | null;
    freshness?: ResultFreshness | null;
    platformMeta?: ResultPlatformMeta | null;
    skillSuggestions?: ResultSkillSuggestion[];
    strategySuggestions?: ResultStrategySuggestion[];
    workbenchTask?: ResultWorkbenchTask | null;
};
