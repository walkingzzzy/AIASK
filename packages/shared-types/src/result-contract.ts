import type { ToolArgs } from './common';

export const RESULT_VIEWS = [
    'summary',
    'compare',
    'visual',
    'next_step',
] as const;

export type ResultView = typeof RESULT_VIEWS[number];

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
    availableViews: ResultView[];
    recommendedActions?: ResultAction[];
    recommendedLinks?: ResultLink[];
    evidence?: ResultEvidenceItem[];
    riskNotes?: string[];
    freshness?: ResultFreshness | null;
    platformMeta?: ResultPlatformMeta | null;
    skillSuggestions?: ResultSkillSuggestion[];
    strategySuggestions?: ResultStrategySuggestion[];
    workbenchTask?: ResultWorkbenchTask | null;
};
