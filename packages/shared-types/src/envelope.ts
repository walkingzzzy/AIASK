export type CacheMeta = {
  fetchedAt?: string;
  cache?: {
    hit?: boolean;
    backend?: 'redis' | 'memory' | 'none';
    key?: string;
    ttlSeconds?: number;
  };
};

export type Envelope<T> = {
  success?: boolean;
  data?: T;
  traceId?: string;
};

export type ErrorEnvelope = {
  success: false;
  error: { code: string; message: string; detail?: unknown };
  traceId: string;
  path: string;
  timestamp: string;
};
