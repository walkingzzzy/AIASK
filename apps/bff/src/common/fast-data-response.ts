import type { Response } from 'express';

export type FastDataSource = 'live' | 'cache' | 'stale';

export type FastDataResponseMeta = {
  source: FastDataSource;
  ageMs?: number;
  fallbackReason?: string;
};

export type FastDataSnapshot<T> = {
  payload: T;
  fetchedAt: string;
};

export class FastDataTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`fast data refresh timed out after ${timeoutMs}ms`);
    this.name = 'FastDataTimeoutError';
  }
}

const FAST_DATA_META = Symbol('fastDataResponseMeta');

export function buildFastDataSnapshot<T>(payload: T, fetchedAt = new Date().toISOString()): FastDataSnapshot<T> {
  return { payload, fetchedAt };
}

export function attachFastDataMeta<T>(payload: T, meta: FastDataResponseMeta): T {
  if (payload && typeof payload === 'object') {
    Object.defineProperty(payload, FAST_DATA_META, {
      value: meta,
      enumerable: false,
      configurable: true,
    });
  }
  return payload;
}

export function getFastDataMeta(payload: unknown): FastDataResponseMeta | null {
  if (!payload || typeof payload !== 'object') return null;
  const meta = (payload as { [FAST_DATA_META]?: FastDataResponseMeta })[FAST_DATA_META];
  return meta ?? null;
}

export function setFastDataHeaders(res: Response | undefined, payload: unknown): void {
  if (!res) return;
  const meta = getFastDataMeta(payload);
  if (!meta) return;
  res.setHeader('X-Data-Source', meta.source);
  if (Number.isFinite(meta.ageMs)) {
    res.setHeader('X-Data-Age-Ms', String(Math.max(0, Math.floor(meta.ageMs ?? 0))));
  }
  if (meta.source === 'stale') {
    res.setHeader('X-Data-Stale', 'true');
  }
  if (meta.fallbackReason) {
    res.setHeader('X-Data-Fallback', meta.fallbackReason);
  }
}

export function snapshotAgeMs(snapshot: { fetchedAt?: string } | null | undefined, now = Date.now()): number {
  if (!snapshot?.fetchedAt) return 0;
  const parsed = Date.parse(snapshot.fetchedAt);
  return Number.isFinite(parsed) ? Math.max(0, now - parsed) : 0;
}

export async function withFastDataTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return await new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new FastDataTimeoutError(timeoutMs)), timeoutMs);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}
