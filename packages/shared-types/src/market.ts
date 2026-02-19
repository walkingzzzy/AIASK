import type { CacheMeta } from './envelope';

export type NormalizedQuote = {
  code: string;
  name: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  volume: number | null;
  amount: number | null;
  high: number | null;
  low: number | null;
  open: number | null;
  prevClose: number | null;
  timestamp: string | null;
};

export type NormalizedKlinePoint = {
  date: string;
  open: number;
  close: number;
  low: number;
  high: number;
  volume: number;
};

export type NormalizedOrderBook = {
  bids: Array<{ price: number; volume: number }>;
  asks: Array<{ price: number; volume: number }>;
  timestamp: number | null;
};

export type QuoteResponse = {
  quote?: NormalizedQuote;
  tool?: string;
  meta?: CacheMeta;
};

export type KlineResponse = {
  kline?: NormalizedKlinePoint[];
  tool?: string;
  meta?: CacheMeta;
};

export type OrderBookResponse = {
  orderBook?: NormalizedOrderBook;
  tool?: string;
  meta?: CacheMeta;
};
