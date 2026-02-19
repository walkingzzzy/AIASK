import type { CacheMeta } from './envelope';

export type NormalizedFlowItem = {
  date: string;
  name: string;
  netInflow: number | null;
  mainInflow: number | null;
  mainOutflow: number | null;
  retailInflow: number | null;
  retailOutflow: number | null;
};

export type FundFlowResponse = {
  flows?: NormalizedFlowItem[];
  tool?: string;
  meta?: CacheMeta;
};
