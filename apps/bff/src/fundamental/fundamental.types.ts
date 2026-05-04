import type { ResultContract, ResultContractMeta } from '@aiask/shared-types';
import type { DataQuality } from '../common/data-quality';

export type FundamentalOverviewDto = {
  code: string;
  financials: NormalizedFinancials;
  valuation: NormalizedValuation;
  sourceTools: {
    financials: 'get_financials';
    valuation: 'get_valuation_metrics';
  };
  argsMatched: {
    financials: Record<string, unknown>;
    valuation: Record<string, unknown>;
  };
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
  result_contract?: ResultContract | null;
  degraded?: boolean;
  fallbackReason?: string;
  fallbackSource?: string;
  data_quality?: DataQuality | null;
  contract_meta?: {
    financials: ResultContractMeta;
    valuation: ResultContractMeta;
  };
};

export type FundamentalHistoryDto = {
  code: string;
  days: number;
  points: Array<{ date: string; pe: number | null; pb: number | null; ps: number | null; close: number | null }>;
  sourceTool: string;
  argsMatched: Record<string, unknown>;
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
  result_contract?: ResultContract | null;
  contract_meta?: ResultContractMeta | null;
};

export type FundamentalCapitalDto = {
  code: string;
  totalShares: number | null;
  total_shares: number | null;
  floatShares: number | null;
  float_shares: number | null;
  restrictedShares: number | null;
  restricted_shares: number | null;
  capitalData: Array<{
    date: string;
    totalShares: number | null;
    total_shares: number | null;
    floatShares: number | null;
    float_shares: number | null;
    restrictedShares: number | null;
    restricted_shares: number | null;
  }>;
  holders: Array<never>;
  sourceTool: 'get_stock_capital';
  argsMatched: Record<string, unknown>;
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
  contract_meta?: ResultContractMeta | null;
};

export type FundamentalPeersDto = {
  code: string;
  name: string;
  industry: string;
  peerCount: number;
  peer_count: number;
  peers: Array<Record<string, unknown>>;
  targetMetrics: Record<string, unknown>;
  target_metrics: Record<string, unknown>;
  comparison: Record<string, unknown>;
  industryStats: Record<string, unknown>;
  industry_stats: Record<string, unknown>;
  fallbackSource?: string;
  fallbackReason?: string;
  sourceTool: 'relative_valuation';
  argsMatched: Record<string, unknown>;
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
  contract_meta?: ResultContractMeta | null;
};

export type NormalizedValuation = {
  pe: number | null; pb: number | null; ps: number | null; marketCap: number | null;
};
export type NormalizedFinancials = {
  roe: number | null;
  netProfit: number | null;
  revenue: number | null;
  debtRatio: number | null;
  grossProfitMargin: number | null;
  netProfitMargin: number | null;
  operatingCashFlow: number | null;
};

/** 兼容历史财务字段编码，统一归一到可读字段名。 */
export const LEGACY_FIELD_ALIASES: Record<string, string> = {
  FN1: 'eps',
  FN2: 'eps_deducted',
  FN3: 'undistributed_profit_per_share',
  FN4: 'bvps',
  FN6: 'roe',
  FN193: 'cost_profit_rate',
  FN194: 'operating_profit_rate',
  FN197: 'roe_diluted',
  FN199: 'net_profit_margin',
  FN210: 'debt_ratio',
  FN230: 'revenue',
  FN231: 'operating_profit',
  FN232: 'net_profit',
};
