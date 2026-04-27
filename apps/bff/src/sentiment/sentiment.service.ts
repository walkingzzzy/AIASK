import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import {
  FastDataTimeoutError,
  attachFastDataMeta,
  buildFastDataSnapshot,
  snapshotAgeMs,
  withFastDataTimeout,
  type FastDataSnapshot,
} from '../common/fast-data-response';

type FearGreedResponse = {
  sourceTool: 'calculate_fear_greed_index';
  data: unknown;
  result: unknown;
};

@Injectable()
export class SentimentService {
  private static readonly FEAR_GREED_TTL_SECONDS = 30;
  private static readonly FEAR_GREED_STALE_SECONDS = 120;
  private static readonly FAST_TIMEOUT_MS = 1800;
  private readonly fearGreedInflight = new Map<string, Promise<FastDataSnapshot<FearGreedResponse>>>();

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async analyzeStock(code: string) {
    const payload = await this.callTool('analyze_stock_sentiment', { code });
    return { sourceTool: 'analyze_stock_sentiment' as const, data: this.extractToolData(payload), result: payload };
  }

  async fearGreedIndex(): Promise<FearGreedResponse> {
    const cacheKey = 'sentiment:fear-greed';
    const ttlSeconds = this.cacheService.resolveTtl('sentiment.fear_greed', SentimentService.FEAR_GREED_TTL_SECONDS);
    const staleSeconds = this.cacheService.resolveTtl('sentiment.fear_greed_stale', SentimentService.FEAR_GREED_STALE_SECONDS);
    const fresh = await this.cacheService.getWithMeta<FastDataSnapshot<FearGreedResponse>>(cacheKey);
    if (fresh.value) {
      return attachFastDataMeta(fresh.value.payload, {
        source: 'cache',
        ageMs: snapshotAgeMs(fresh.value),
      });
    }

    const staleKey = `${cacheKey}:stale`;
    const stale = await this.cacheService.getWithMeta<FastDataSnapshot<FearGreedResponse>>(staleKey);
    const refresh = this.refreshFearGreed(cacheKey, staleKey, ttlSeconds, staleSeconds);
    if (stale.value) {
      void refresh.catch(() => undefined);
      return attachFastDataMeta(stale.value.payload, {
        source: 'stale',
        ageMs: snapshotAgeMs(stale.value),
      });
    }

    try {
      const snapshot = await withFastDataTimeout(refresh, SentimentService.FAST_TIMEOUT_MS);
      return attachFastDataMeta(snapshot.payload, { source: 'live', ageMs: snapshotAgeMs(snapshot) });
    } catch (error) {
      const fallbackReason = error instanceof FastDataTimeoutError ? 'mcp_timeout' : 'mcp_unavailable';
      return attachFastDataMeta(this.buildFearGreedFallback(), {
        source: 'stale',
        ageMs: 0,
        fallbackReason,
      });
    }
  }

  private refreshFearGreed(
    cacheKey: string,
    staleKey: string,
    ttlSeconds: number,
    staleSeconds: number,
  ): Promise<FastDataSnapshot<FearGreedResponse>> {
    const existing = this.fearGreedInflight.get(cacheKey);
    if (existing) return existing;

    const refresh = this.loadFearGreed()
      .then(async (payload) => {
        const snapshot = buildFastDataSnapshot(payload);
        await Promise.all([
          this.cacheService.set(cacheKey, snapshot, ttlSeconds),
          this.cacheService.set(staleKey, snapshot, staleSeconds),
        ]);
        return snapshot;
      })
      .finally(() => {
        this.fearGreedInflight.delete(cacheKey);
      });
    this.fearGreedInflight.set(cacheKey, refresh);
    return refresh;
  }

  private async loadFearGreed(): Promise<FearGreedResponse> {
    const payload = await this.callTool('calculate_fear_greed_index', {});
    return { sourceTool: 'calculate_fear_greed_index' as const, data: this.extractToolData(payload), result: payload };
  }

  private buildFearGreedFallback(): FearGreedResponse {
    return {
      sourceTool: 'calculate_fear_greed_index',
      data: { index: 50, value: 50, fallback: true },
      result: { index: 50, value: 50, fallback: true },
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      return await this.mcpGatewayService.callTool(name, args);
    } catch (error) {
      throw new BadGatewayException({
        success: false, message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private extractToolData(payload: unknown): unknown {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return payload;
    }
    const record = payload as Record<string, unknown>;
    return Object.prototype.hasOwnProperty.call(record, 'data') ? record.data : payload;
  }
}
