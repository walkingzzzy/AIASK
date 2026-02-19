import type { CacheMeta } from './envelope';

export type NormalizedValuation = {
  pe: number | null;
  pb: number | null;
  ps: number | null;
  marketCap: number | null;
};

export type NormalizedFinancials = {
  roe: number | null;
  netProfit: number | null;
  revenue: number | null;
  debtRatio: number | null;
};

export type FundamentalResponse = {
  valuation?: NormalizedValuation;
  financials?: NormalizedFinancials;
  tool?: string;
  meta?: CacheMeta;
};
