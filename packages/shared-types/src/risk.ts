import type { CacheMeta } from './common';

export type RiskModuleStatus = {
    ok?: boolean;
    reason?: string | null;
};

export type RiskSourceContext =
    | { mode: 'portfolio'; portfolioId: number }
    | { mode: 'paper-trading'; accountId?: string; codes: string[]; weights: number[]; portfolioValue: number }
    | { mode: 'empty'; reason: string };

export type RiskSummaryData = {
    portfolioId: number | null;
    lookbackDays: number;
    injectedFail: 'var' | 'stress' | 'exposure' | null;
    sourceContext: RiskSourceContext;
    sourceTools: {
        var: 'risk_manager';
        stress: 'risk_manager';
        exposure: 'risk_manager';
    };
    argsMatched: {
        var: Record<string, unknown> | null;
        stress: Record<string, unknown> | null;
        exposure: Record<string, unknown> | null;
    };
    varResult: unknown;
    stressResult: unknown;
    exposureResult: unknown;
    moduleStatus: Record<'var' | 'stress' | 'exposure', RiskModuleStatus>;
    degraded: boolean;
    empty: boolean;
    degradeReasons: string[];
    meta: CacheMeta;
};

export type RiskVarOnlyData = {
    portfolioId: number | null;
    lookbackDays: number;
    sourceContext: RiskSourceContext | null;
    sourceTool: 'risk_manager';
    argsMatched: Record<string, unknown> | null;
    result: unknown;
    degraded: boolean;
    degradedReason: string | null;
    meta: CacheMeta;
};
