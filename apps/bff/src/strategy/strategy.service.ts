import {
  BadGatewayException,
  Injectable,
  Logger,
  NotFoundException,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

@Injectable()
export class StrategyMarketService implements OnModuleInit, OnModuleDestroy {
  private static readonly RANKING_TTL = 1500; // 25 min
  private static readonly AUTO_REFRESH_CHECK_MS = 5 * 60 * 1000; // 5 min
  private static readonly AUTO_REFRESH_HOUR = 15;
  private static readonly AUTO_REFRESH_MINUTE = 5;

  private readonly logger = new Logger(StrategyMarketService.name);
  private autoRefreshTimer?: ReturnType<typeof setInterval>;
  private lastAutoRefreshDate?: string;

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cache: CommonCacheService,
  ) {}

  onModuleInit() {
    this.startAutoRefreshTimer();
  }

  onModuleDestroy() {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = undefined;
    }
  }

  private startAutoRefreshTimer() {
    if (this.autoRefreshTimer) return;
    this.autoRefreshTimer = setInterval(() => {
      void this.runAutoRefreshTick();
    }, StrategyMarketService.AUTO_REFRESH_CHECK_MS);
    void this.runAutoRefreshTick();
    this.logger.log(
      `策略排名自动刷新已启动（每 ${StrategyMarketService.AUTO_REFRESH_CHECK_MS / 60000} 分钟检查，收盘后 ${StrategyMarketService.AUTO_REFRESH_HOUR}:${String(StrategyMarketService.AUTO_REFRESH_MINUTE).padStart(2, '0')} 触发）`,
    );
  }

  private isAfterMarketClose(now: Date) {
    const hour = now.getHours();
    const minute = now.getMinutes();
    if (hour > StrategyMarketService.AUTO_REFRESH_HOUR) return true;
    if (hour < StrategyMarketService.AUTO_REFRESH_HOUR) return false;
    return minute >= StrategyMarketService.AUTO_REFRESH_MINUTE;
  }

  private dateKey(now: Date) {
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  private async runAutoRefreshTick() {
    const now = new Date();
    if (!this.isAfterMarketClose(now)) return;

    const today = this.dateKey(now);
    if (this.lastAutoRefreshDate === today) return;

    try {
      const result = await this.refreshRankingCaches();
      this.lastAutoRefreshDate = today;
      this.logger.log(
        `策略排名自动刷新完成 date=${today} refreshed_count=${result.refreshed_count}`,
      );
    } catch (error) {
      this.logger.error(
        `策略排名自动刷新失败 date=${today}: ${String(error)}`,
      );
    }
  }

  private async call(action: string, params: Record<string, unknown> = {}) {
    try {
      const result = await this.mcp.callTool('strategy_manager', {
        action,
        kwargs: JSON.stringify(params),
      });
      if (result && typeof result === 'object') {
        const obj = result as Record<string, unknown>;
        if (obj.success === false) {
          throw new Error(String(obj.error || obj.message || `${action} 操作失败`));
        }
        if ('data' in obj) return obj.data;
      }
      return result;
    } catch (error) {
      if (error instanceof BadGatewayException) throw error;
      throw new BadGatewayException({
        success: false,
        message: `调用 strategy_manager.${action} 失败`,
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  private buildRankingCacheKey(params: { strategy_type?: string; limit?: number; rank_keys?: string[] }) {
    const type = params.strategy_type || 'all';
    const limit = params.limit || 50;
    const rankKeys = (params.rank_keys || []).join(',');
    return `strategy:ranking:${type}:${limit}:${rankKeys}`;
  }

  private async fetchRankingWithCache(
    params: { strategy_type?: string; limit?: number; rank_keys?: string[]; offset?: number },
    forceRefresh = false,
  ) {
    const cacheKey = this.buildRankingCacheKey(params);
    const ttl = this.cache.resolveTtl('strategy.ranking', StrategyMarketService.RANKING_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta(cacheKey);
      if (cached.value) return { data: cached.value, cacheKey, ttl, cacheHit: true };
    } else {
      await this.cache.del(cacheKey);
    }

    const data = await this.call('rank', { status: 'published', ...params });
    await this.cache.set(cacheKey, data, ttl);
    return { data, cacheKey, ttl, cacheHit: false };
  }

  async list(params: { status?: string; strategy_type?: string; limit?: number; offset?: number }) {
    return this.call('list', params);
  }

  async detail(id: string) {
    const result = await this.call('detail', { strategy_id: id });
    if (!result) throw new NotFoundException(`策略 ${id} 不存在`);
    return result;
  }

  async rank(params: { strategy_type?: string; limit?: number; rank_keys?: string[]; offset?: number }) {
    const res = await this.fetchRankingWithCache(params, false);
    return res.data;
  }

  async refreshRankingCaches(params?: { strategy_types?: string[]; limits?: number[]; rank_keys_sets?: string[][] }) {
    const strategyTypes = (params?.strategy_types?.length ? params.strategy_types : ['all']).slice(0, 10);
    const limits = (params?.limits?.length ? params.limits : [20, 50]).map((x) => Math.max(1, Math.min(200, Number(x) || 50)));
    const rankKeySets = (params?.rank_keys_sets?.length ? params.rank_keys_sets : [[]]).slice(0, 5);

    const refreshed: Array<{ cacheKey: string; count: number; strategy_type?: string; limit: number; rank_keys: string[] }> = [];
    for (const strategyType of strategyTypes) {
      for (const limit of limits) {
        for (const rankKeys of rankKeySets) {
          const res = await this.fetchRankingWithCache({ strategy_type: strategyType === 'all' ? undefined : strategyType, limit, rank_keys: rankKeys }, true);
          const count = Number((res.data as Record<string, unknown>)?.count ?? 0) || 0;
          refreshed.push({ cacheKey: res.cacheKey, count, strategy_type: strategyType, limit, rank_keys: rankKeys || [] });
        }
      }
    }

    return {
      refreshed_count: refreshed.length,
      refreshed,
    };
  }

  async create(params: object) {
    return this.call('create', params as Record<string, unknown>);
  }

  async publish(id: string) {
    return this.call('publish', { strategy_id: id });
  }

  async archive(id: string) {
    return this.call('archive', { strategy_id: id });
  }

  async updateMetrics(id: string, metrics: object) {
    return this.call('update_metrics', {
      strategy_id: id,
      ...(metrics as Record<string, unknown>),
    });
  }

  async subscribe(id: string, userId: string) {
    return this.call('subscribe', { strategy_id: id, user_id: userId });
  }

  async unsubscribe(id: string, userId: string) {
    return this.call('unsubscribe', { strategy_id: id, user_id: userId });
  }

  async review(id: string, userId: string, rating: number, comment?: string) {
    return this.call('review', { strategy_id: id, user_id: userId, rating, comment });
  }

  async mySubscriptions(userId: string) {
    return this.call('my_subscriptions', { user_id: userId });
  }

  async submit(id: string) {
    return this.call('submit', { strategy_id: id });
  }

  async getSignals(id: string, userId: string, params: { limit?: number } = {}) {
    return this.call('get_signals', { strategy_id: id, user_id: userId, ...params });
  }

  async getForwardReturns(id: string) {
    return this.call('get_forward_returns', { strategy_id: id });
  }

  async getSignalStats(id: string) {
    return this.call('get_signal_stats', { strategy_id: id });
  }

  async lifecycleScan() {
    return this.call('lifecycle_scan');
  }
}
