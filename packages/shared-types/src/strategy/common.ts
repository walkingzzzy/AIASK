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
