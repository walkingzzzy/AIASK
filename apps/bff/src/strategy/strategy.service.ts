import {
  BadRequestException,
  BadGatewayException,
  Injectable,
  Logger,
  NotFoundException,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import type { StrategyManagerAction, StrategyManagerErrorCode } from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

@Injectable()
export class StrategyMarketService implements OnModuleInit, OnModuleDestroy {
  private static readonly RANKING_TTL = 1500; // 25 min
  private static readonly FACTORY_RUNS_TTL = 60;
  private static readonly FACTORY_RUN_DETAIL_TTL = 60;
  private static readonly AUTO_REFRESH_CHECK_MS = 5 * 60 * 1000; // 5 min
  private static readonly AUTO_REFRESH_HOUR = 15;
  private static readonly AUTO_REFRESH_MINUTE = 5;
  private static readonly AUTO_REFRESH_TIMEZONE = process.env.STRATEGY_MARKET_TIMEZONE || 'Asia/Shanghai';
  private static readonly AUTO_REFRESH_ENABLED = !['0', 'false', 'no'].includes(
    String(process.env.STRATEGY_MARKET_AUTO_REFRESH_ENABLED ?? (process.env.NODE_ENV === 'test' ? '0' : '1'))
      .trim()
      .toLowerCase(),
  );

  private readonly logger = new Logger(StrategyMarketService.name);
  private autoRefreshTimer?: ReturnType<typeof setInterval>;
  private lastAutoRefreshDate?: string;

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cache: CommonCacheService,
  ) {}

  onModuleInit() {
    if (!StrategyMarketService.AUTO_REFRESH_ENABLED) {
      this.logger.log('策略排名自动刷新已禁用');
      return;
    }
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
    const { hour, minute } = this.getMarketTimeParts(now);
    if (hour > StrategyMarketService.AUTO_REFRESH_HOUR) return true;
    if (hour < StrategyMarketService.AUTO_REFRESH_HOUR) return false;
    return minute >= StrategyMarketService.AUTO_REFRESH_MINUTE;
  }

  private dateKey(now: Date) {
    const { year, month, day } = this.getMarketTimeParts(now);
    return `${year}-${month}-${day}`;
  }

  private async runAutoRefreshTick() {
    const now = new Date();
    if (!this.isAfterMarketClose(now)) return;

    const today = this.dateKey(now);
    if (this.lastAutoRefreshDate === today) return;

    const ready = await this.isAutoRefreshReady();
    if (!ready) {
      this.logger.debug(`策略排名自动刷新跳过 date=${today}: MCP not ready`);
      return;
    }

    try {
      const result = await this.refreshRankingCaches();
      this.lastAutoRefreshDate = today;
      this.logger.log(`策略排名自动刷新完成 date=${today} refreshed_count=${result.refreshed_count}`);
    } catch (error) {
      this.logger.error(`策略排名自动刷新失败 date=${today}: ${String(error)}`);
    }
  }

  private async isAutoRefreshReady(): Promise<boolean> {
    try {
      const health = await this.mcp.checkAvailableTools();
      return health.reachable;
    } catch {
      return false;
    }
  }

  private async call(action: StrategyManagerAction, params: Record<string, unknown> = {}) {
    try {
      const result = await this.mcp.callTool('strategy_manager', {
        action,
        params,
      });
      if (result && typeof result === 'object') {
        const obj = result as Record<string, unknown>;
        if (obj.success === false) {
          const errorCode = String(obj.error_code || 'STRATEGY_MANAGER_BACKEND_ERROR') as StrategyManagerErrorCode;
          const message = String(obj.error || obj.message || `${action} 操作失败`);
          const detail = {
            action,
            error_code: errorCode,
            detail: obj.detail,
          };
          if (errorCode === 'STRATEGY_MANAGER_INVALID_ACTION' || errorCode === 'STRATEGY_MANAGER_INVALID_PARAMS') {
            throw new BadRequestException({
              success: false,
              code: errorCode,
              message,
              detail,
            });
          }
          if (errorCode === 'STRATEGY_MANAGER_NOT_FOUND') {
            throw new NotFoundException({
              success: false,
              code: errorCode,
              message,
              detail,
            });
          }
          throw new BadGatewayException({
            success: false,
            code: errorCode,
            message,
            detail,
          });
        }
        if ('data' in obj) return obj.data;
      }
      return result;
    } catch (error) {
      if (
        error instanceof BadRequestException ||
        error instanceof NotFoundException ||
        error instanceof BadGatewayException
      ) {
        throw error;
      }
      throw new BadGatewayException({
        success: false,
        message: `调用 strategy_manager.${action} 失败`,
        detail: String(error instanceof Error ? error.message : error),
      });
    }
  }

  private getMarketTimeParts(now: Date): { year: string; month: string; day: string; hour: number; minute: number } {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: StrategyMarketService.AUTO_REFRESH_TIMEZONE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(now);

    const readPart = (type: string) => parts.find((part) => part.type === type)?.value ?? '00';
    return {
      year: readPart('year'),
      month: readPart('month'),
      day: readPart('day'),
      hour: Number(readPart('hour')),
      minute: Number(readPart('minute')),
    };
  }

  private buildRankingCacheKey(params: {
    status?: string;
    strategy_type?: string;
    limit?: number;
    rank_keys?: string[];
    offset?: number;
  }) {
    const status = params.status || 'visible';
    const type = params.strategy_type || 'all';
    const limit = params.limit || 50;
    const offset = params.offset || 0;
    const rankKeys = (params.rank_keys || []).join(',');
    return `strategy:ranking:${status}:${type}:${limit}:${offset}:${rankKeys}`;
  }

  private buildFactoryRunsCacheKey(limit?: number) {
    return `strategy:factory:runs:${Math.max(1, Math.min(200, Number(limit) || 20))}`;
  }

  private buildFactoryRunDetailCacheKey(runId: string) {
    return `strategy:factory:run:${runId}`;
  }

  private async clearFactoryRunCaches() {
    await this.cache.clear('strategy:factory:runs:');
    await this.cache.clear('strategy:factory:run:');
  }

  private normalizeFactoryStage(stageName: string, payload: unknown) {
    const stage = (payload && typeof payload === 'object' ? payload : {}) as Record<string, unknown>;
    const ok = typeof stage.ok === 'boolean' ? stage.ok : true;
    const status = String(stage.status ?? (ok ? 'completed' : 'failed'));
    return {
      stage: String(stage.stage ?? stageName),
      trace_id: stage.trace_id ?? null,
      status,
      ok,
      ...stage,
    };
  }

  private normalizeFactoryRun<T>(payload: T): T {
    if (!payload || typeof payload !== 'object') return payload;
    const run = payload as Record<string, unknown>;
    const rawStages = run.stages && typeof run.stages === 'object' ? (run.stages as Record<string, unknown>) : {};
    const normalizedStages = Object.fromEntries(
      Object.entries(rawStages).map(([stageName, value]) => [stageName, this.normalizeFactoryStage(stageName, value)]),
    );
    const normalizedStageValues = Object.values(normalizedStages) as Record<string, unknown>[];
    const stageStatusCounts = normalizedStageValues.reduce<Record<string, number>>((counts, item) => {
      const status = String(item?.status ?? 'completed');
      counts[status] = (counts[status] ?? 0) + 1;
      return counts;
    }, {});
    const failedStage = normalizedStageValues.find((item) => String(item?.status ?? '') === 'failed');
    const partialStage = normalizedStageValues.find((item) => String(item?.status ?? '') === 'partial');
    const skippedStage = normalizedStageValues.find((item) => String(item?.status ?? '') === 'skipped');
    const rawPipeline =
      run.pipeline && typeof run.pipeline === 'object' ? (run.pipeline as Record<string, unknown>) : {};
    return {
      ...(run as object),
      dto_version: 'strategy_market.factory_run.v2',
      trace_id: run.trace_id ?? (run.summary as Record<string, unknown> | undefined)?.trace_id ?? null,
      stages: normalizedStages,
      pipeline: {
        ...rawPipeline,
        trace_id: run.trace_id ?? (run.summary as Record<string, unknown> | undefined)?.trace_id ?? null,
        failed_stage: rawPipeline.failed_stage ?? (failedStage as Record<string, unknown> | undefined)?.stage ?? null,
        partial_stage:
          rawPipeline.partial_stage ?? (partialStage as Record<string, unknown> | undefined)?.stage ?? null,
        skipped_stage:
          rawPipeline.skipped_stage ?? (skippedStage as Record<string, unknown> | undefined)?.stage ?? null,
        stage_order: Object.keys(normalizedStages),
        total_stage_count: Object.keys(normalizedStages).length,
        completed_stage_count: normalizedStageValues.filter((item) => String(item?.status ?? '') === 'completed')
          .length,
        partial_stage_count: normalizedStageValues.filter((item) => String(item?.status ?? '') === 'partial').length,
        skipped_stage_count: normalizedStageValues.filter((item) => String(item?.status ?? '') === 'skipped').length,
        failed_stage_count: normalizedStageValues.filter((item) => String(item?.status ?? '') === 'failed').length,
        stage_status_counts: stageStatusCounts,
      },
    } as T;
  }

  private normalizeFactoryRunsResponse<T>(payload: T): T {
    if (!payload || typeof payload !== 'object') return payload;
    const data = payload as Record<string, unknown>;
    const items = Array.isArray(data.items) ? data.items.map((item) => this.normalizeFactoryRun(item)) : [];
    const latest = items.length > 0 ? items[0] : null;
    return {
      ...(data as object),
      dto_version: 'strategy_market.factory_runs.v2',
      items,
      latest,
    } as T;
  }

  private normalizeStrategyDetail<T>(payload: T): T {
    if (!payload || typeof payload !== 'object') return payload;
    const data = payload as Record<string, unknown>;
    return {
      ...(data as object),
      dto_version: 'strategy_market.detail.v2',
      view_model: {
        quality: {
          latest_report: data.latest_quality_report ?? null,
        },
        incubation: {
          account: data.incubation_account ?? null,
          latest_metric: data.latest_incubation_metric ?? null,
          latest_pipeline_snapshot: data.latest_incubation_pipeline_snapshot ?? null,
        },
        runtime: {
          control: data.runtime_control ?? null,
          latest_risk_snapshot: data.latest_runtime_risk_snapshot ?? null,
          alerts: data.runtime_alerts ?? [],
          risk_events: data.open_risk_events ?? [],
        },
        vectors: {
          profiles: data.vector_profiles ?? [],
          similar_profiles: data.similar_vector_profiles ?? [],
          latest_index_snapshot: data.latest_vector_index_snapshot ?? null,
        },
        domain: {
          events: data.domain_events ?? [],
          task_runs: data.task_runs ?? [],
          latest_projection_snapshot: data.latest_projection_snapshot ?? null,
        },
      },
    } as T;
  }

  private async fetchRankingWithCache(
    params: { status?: string; strategy_type?: string; limit?: number; rank_keys?: string[]; offset?: number },
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

    const data = await this.call('rank', { status: params.status || 'visible', ...params });
    await this.cache.set(cacheKey, data, ttl);
    return { data, cacheKey, ttl, cacheHit: false };
  }

  private async fetchFactoryRunsWithCache(limit?: number, forceRefresh = false) {
    const cacheKey = this.buildFactoryRunsCacheKey(limit);
    const ttl = this.cache.resolveTtl('strategy.factory_runs', StrategyMarketService.FACTORY_RUNS_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta<Record<string, unknown>>(cacheKey);
      if (cached.value) return cached.value;
    } else {
      await this.cache.del(cacheKey);
    }

    const data = this.normalizeFactoryRunsResponse(await this.call('factory_runs', { limit }));
    await this.cache.set(cacheKey, data, ttl);
    return data;
  }

  private async fetchFactoryRunDetailWithCache(runId: string, forceRefresh = false) {
    const cacheKey = this.buildFactoryRunDetailCacheKey(runId);
    const ttl = this.cache.resolveTtl('strategy.factory_run_detail', StrategyMarketService.FACTORY_RUN_DETAIL_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta<Record<string, unknown>>(cacheKey);
      if (cached.value) return cached.value;
    } else {
      await this.cache.del(cacheKey);
    }

    const data = this.normalizeFactoryRun(await this.call('factory_run_detail', { run_id: runId }));
    await this.cache.set(cacheKey, data, ttl);
    return data;
  }

  async list(params: { status?: string; strategy_type?: string; limit?: number; offset?: number }) {
    return this.call('list', params);
  }

  async detail(id: string) {
    const result = await this.call('detail', { strategy_id: id });
    if (!result) throw new NotFoundException(`策略 ${id} 不存在`);
    return this.normalizeStrategyDetail(result);
  }

  async reviewReport(id: string) {
    return this.call('review_report', { strategy_id: id });
  }

  async reviewReportRecheck(id: string) {
    return this.call('review_report_recheck', { strategy_id: id });
  }

  async events(
    id: string,
    filters?: {
      event_type?: string;
      from_status?: string;
      to_status?: string;
      actor_id?: string;
      start_time?: string;
      end_time?: string;
      limit?: number;
    },
  ) {
    return this.call('events', { strategy_id: id, ...(filters || {}) });
  }

  async incubationOverview(id: string) {
    return this.call('incubation_overview', { strategy_id: id });
  }

  async rank(params: {
    status?: string;
    strategy_type?: string;
    limit?: number;
    rank_keys?: string[];
    offset?: number;
  }) {
    const res = await this.fetchRankingWithCache(params, false);
    return res.data;
  }

  async refreshRankingCaches(params?: { strategy_types?: string[]; limits?: number[]; rank_keys_sets?: string[][] }) {
    const strategyTypes = (params?.strategy_types?.length ? params.strategy_types : ['all']).slice(0, 10);
    const limits = (params?.limits?.length ? params.limits : [20, 50]).map((x) =>
      Math.max(1, Math.min(200, Number(x) || 50)),
    );
    const rankKeySets = (params?.rank_keys_sets?.length ? params.rank_keys_sets : [[]]).slice(0, 5);

    const refreshed: Array<{
      cacheKey: string;
      count: number;
      strategy_type?: string;
      limit: number;
      rank_keys: string[];
    }> = [];
    for (const strategyType of strategyTypes) {
      for (const limit of limits) {
        for (const rankKeys of rankKeySets) {
          const res = await this.fetchRankingWithCache(
            { strategy_type: strategyType === 'all' ? undefined : strategyType, limit, rank_keys: rankKeys },
            true,
          );
          const count = Number((res.data as Record<string, unknown>)?.count ?? 0) || 0;
          refreshed.push({
            cacheKey: res.cacheKey,
            count,
            strategy_type: strategyType,
            limit,
            rank_keys: rankKeys || [],
          });
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

  async factoryStatus() {
    return this.call('factory_status');
  }

  async factoryRunOnce() {
    const result = await this.call('factory_run_once');
    await this.clearFactoryRunCaches();
    return result;
  }

  async factoryRuns(limit?: number) {
    return this.fetchFactoryRunsWithCache(limit);
  }

  async factoryRunDetail(runId: string) {
    return this.fetchFactoryRunDetailWithCache(runId);
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

  async capabilities() {
    return this.call('capabilities');
  }

  async dailySnapshots(params: { limit?: number; start_date?: string; end_date?: string } = {}) {
    return this.call('daily_snapshots', params);
  }

  async dailySnapshot(snapshotDate?: string) {
    return this.call('daily_snapshot', { snapshot_date: snapshotDate });
  }

  async incubationAccounts(id: string, params: { status?: string; limit?: number } = {}) {
    return this.call('incubation_accounts', { strategy_id: id, ...params });
  }

  async incubationMetrics(id: string, params: { limit?: number; start_date?: string; end_date?: string } = {}) {
    return this.call('incubation_metrics', { strategy_id: id, ...params });
  }

  async paperAccount(id: string, params: { limit?: number } = {}) {
    return this.call('paper_account', { strategy_id: id, ...params });
  }

  async paperOrders(id: string, params: { signal_date?: string; status?: string; limit?: number } = {}) {
    return this.call('paper_orders', { strategy_id: id, ...params });
  }

  async paperNav(id: string, params: { limit?: number } = {}) {
    return this.call('paper_nav', { strategy_id: id, ...params });
  }

  async runIncubationSync(id: string, params: { signal_date?: string } = {}) {
    return this.call('incubation_sync_run', { strategy_id: id, ...params });
  }

  async incubationPipeline(
    id: string,
    params: { pipeline_stage?: string; pipeline_status?: string; limit?: number } = {},
  ) {
    return this.call('incubation_pipeline', { strategy_id: id, ...params });
  }

  async runIncubationPipeline(
    id?: string,
    params: { statuses?: string[]; limit?: number; source?: string; auto_apply_review?: boolean } = {},
  ) {
    return this.call('incubation_pipeline_run', { strategy_id: id, ...params });
  }

  async riskEvents(
    id: string,
    params: { account_id?: string; status?: string; severity?: string; limit?: number } = {},
  ) {
    return this.call('risk_events', { strategy_id: id, ...params });
  }

  async riskSnapshots(id: string, params: { posture_level?: string; control_mode?: string; limit?: number } = {}) {
    return this.call('risk_snapshots', { strategy_id: id, ...params });
  }

  async runRiskScan(id?: string, params: { enforce_actions?: boolean } = {}) {
    return this.call('risk_scan_run', { strategy_id: id, ...params });
  }

  async riskRecovery(id: string, params: { source?: string } = {}) {
    return this.call('risk_recovery', { strategy_id: id, ...params });
  }

  async resolveRiskEvent(eventId: number, resolution?: string) {
    return this.call('resolve_risk_event', { event_id: eventId, resolution });
  }

  async runtimeAlerts(
    id: string,
    params: { status?: string; category?: string; severity?: string; limit?: number } = {},
  ) {
    return this.call('runtime_alerts', { strategy_id: id, ...params });
  }

  async runRuntimeAlertDispatch(id?: string, params: { source?: string } = {}) {
    return this.call('runtime_alert_dispatch_run', { strategy_id: id, ...params });
  }

  async acknowledgeRuntimeAlert(alertId: number, params: { acknowledged_by?: string; source?: string } = {}) {
    return this.call('runtime_alert_ack', { alert_id: alertId, ...params });
  }

  async vectorProfiles(id: string, params: { profile_type?: string; limit?: number; similar_to?: string } = {}) {
    return this.call('vector_profiles', { strategy_id: id, ...params });
  }

  async vectorIndexes(params: { index_name?: string; status?: string; limit?: number } = {}) {
    return this.call('vector_indexes', params);
  }

  async vectorIndexSnapshots(
    params: { index_name?: string; index_version?: string; status?: string; limit?: number } = {},
  ) {
    return this.call('vector_index_snapshots', params);
  }

  async vectorAnnSearch(
    id: string,
    params: {
      index_name?: string;
      index_version?: string;
      profile_type?: string;
      candidate_limit?: number;
      limit?: number;
    } = {},
  ) {
    return this.call('vector_ann_search', { strategy_id: id, ...params });
  }

  async vectorReconcile(params: { index_name?: string; profile_type?: string; limit_profiles?: number } = {}) {
    return this.call('vector_reconcile', params);
  }

  async vectorRebuild(
    params: {
      index_name?: string;
      index_version?: string;
      statuses?: string[];
      limit?: number;
      profile_type?: string;
      vector_method?: string;
    } = {},
  ) {
    return this.call('vector_rebuild', params);
  }

  async vectorHealth(params: { index_name?: string; limit_versions?: number; include_hnsw_indexes?: boolean } = {}) {
    return this.call('vector_health', params);
  }

  async vectorCleanup(
    params: {
      index_name?: string;
      keep_versions?: number;
      dry_run?: boolean;
      cleanup_hnsw?: boolean;
      limit_versions?: number;
      protect_versions?: string[];
    } = {},
  ) {
    return this.call('vector_cleanup', params);
  }

  async domainEvents(
    id: string,
    params: {
      aggregate_type?: string;
      event_type?: string;
      source?: string;
      correlation_id?: string;
      limit?: number;
    } = {},
  ) {
    return this.call('domain_events', { strategy_id: id, ...params });
  }

  async domainProjection(id: string, params: { limit?: number } = {}) {
    return this.call('domain_projection', { strategy_id: id, ...params });
  }

  async domainProjectionSnapshot(id: string, params: { limit?: number } = {}) {
    return this.call('domain_projection_snapshot', { strategy_id: id, ...params });
  }

  async rebuildDomainProjection(id?: string, params: { limit?: number; statuses?: string[]; source?: string } = {}) {
    return this.call('domain_projection_rebuild', { strategy_id: id, ...params });
  }

  async runtimeControl(id: string) {
    return this.call('runtime_control', { strategy_id: id });
  }

  async setRuntimeControl(
    id: string,
    params: { control_mode: string; reason?: string; source?: string; trigger_event_type?: string },
  ) {
    return this.call('runtime_control_set', { strategy_id: id, ...params });
  }

  async promotionReviews(id: string, params: { status?: string; limit?: number } = {}) {
    return this.call('promotion_reviews', { strategy_id: id, ...params });
  }

  async runPromotionReview(id: string, params: { auto_apply?: boolean; source?: string } = {}) {
    return this.call('promotion_review_run', { strategy_id: id, ...params });
  }

  async runtimeCycleRun() {
    return this.call('runtime_cycle_run');
  }

  async runtimeCycleStatus() {
    return this.call('runtime_cycle_status');
  }

  async aiGenerate(params: { limit?: number; parent_strategy_id?: string; auto_submit?: boolean } = {}) {
    return this.call('ai_generate', params);
  }

  async aiExperiments(
    params: {
      experiment_id?: string;
      strategy_id?: string;
      parent_strategy_id?: string;
      generated_strategy_id?: string;
      task_run_id?: number;
      status?: string;
      source?: string;
      limit?: number;
    } = {},
  ) {
    return this.call('ai_experiments', params);
  }

  async taskRuns(
    params: { strategy_id?: string; task_name?: string; task_scope?: string; status?: string; limit?: number } = {},
  ) {
    return this.call('task_runs', params);
  }

  async lifecycleScan() {
    return this.call('lifecycle_scan');
  }
}
