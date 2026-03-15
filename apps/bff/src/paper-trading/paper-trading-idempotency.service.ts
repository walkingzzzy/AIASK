import { Injectable } from '@nestjs/common';
import { CommonCacheService } from '../common/cache.service';

type PaperTradingIdempotencyScope = 'order' | 'cancel' | 'route-execution';

type IdempotencyRecord<T> = {
  response: T;
  createdAt: string;
};

@Injectable()
export class PaperTradingIdempotencyService {
  private static readonly TTL_SECONDS = 10 * 60;

  private readonly inflight = new Map<string, Promise<unknown>>();

  constructor(private readonly cache: CommonCacheService) {}

  async execute<T>(params: {
    userId: string;
    scope: PaperTradingIdempotencyScope;
    idempotencyKey?: string | null;
    operation: () => Promise<T>;
  }): Promise<T> {
    const normalizedKey = this.normalizeKey(params.idempotencyKey);
    if (!normalizedKey) {
      return params.operation();
    }

    const cacheKey = this.buildCacheKey(params.userId, params.scope, normalizedKey);
    const cached = await this.cache.get<IdempotencyRecord<T>>(cacheKey);
    if (cached?.response !== undefined) {
      return cached.response;
    }

    const inflight = this.inflight.get(cacheKey);
    if (inflight) {
      return inflight as Promise<T>;
    }

    const task = (async () => {
      try {
        const response = await params.operation();
        await this.cache.set(
          cacheKey,
          { response, createdAt: new Date().toISOString() } satisfies IdempotencyRecord<T>,
          PaperTradingIdempotencyService.TTL_SECONDS,
        );
        return response;
      } finally {
        this.inflight.delete(cacheKey);
      }
    })();

    this.inflight.set(cacheKey, task as Promise<unknown>);
    return task;
  }

  private buildCacheKey(userId: string, scope: PaperTradingIdempotencyScope, idempotencyKey: string) {
    return `paper-trading:idempotency:${scope}:${userId}:${idempotencyKey}`;
  }

  private normalizeKey(idempotencyKey?: string | null) {
    const value = String(idempotencyKey ?? '').trim();
    return value.length > 0 ? value.slice(0, 128) : null;
  }
}
