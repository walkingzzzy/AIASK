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
import {
  type BackgroundFactoryRunStatus,
  type BackgroundFactoryRunState,
  type StrategyManagerCallOptions,
  buildFactoryRunDetailCacheKey,
  buildFactoryStatusCacheKey,
  buildFactoryRunsCacheKey,
  buildRankingCacheKey,
  detachTimer,
  getMarketTimeParts,
  normalizeStrategyDetailResponse,
} from './strategy.service.shared';
import { loadFactoryObservability } from './strategy.service.factory-observability';

@Injectable()
export class StrategyMarketService implements OnModuleInit, OnModuleDestroy {
  private static readonly RANKING_TTL = 1500; // 25 min
  private static readonly FACTORY_STATUS_TTL = 15;
  private static readonly FACTORY_STATUS_WARMUP_DELAY_MS = 5_000;
  private static readonly FACTORY_RUNS_TTL = 60;
  private static readonly FACTORY_RUN_DETAIL_TTL = 60;
  private static readonly AUTO_REFRESH_CHECK_MS = 5 * 60 * 1000; // 5 min
  private static readonly AUTO_REFRESH_HOUR = 15;
  private static readonly AUTO_REFRESH_MINUTE = 5;
  private static readonly AUTO_REFRESH_TIMEZONE = process.env.STRATEGY_MARKET_TIMEZONE || 'Asia/Shanghai';
  private static readonly AUTO_REFRESH_ENABLED = !['0', 'false', 'no'].includes(
    String(
      process.env.STRATEGY_MARKET_AUTO_REFRESH_ENABLED
      ?? ((process.env.NODE_ENV === 'test' || (process.env.NODE_ENV !== 'production' && Number(process.env.MCP_POOL_SIZE ?? '8') <= 1)) ? '0' : '1'),
    )
      .trim()
      .toLowerCase(),
  );

  private readonly logger = new Logger(StrategyMarketService.name);
  private autoRefreshTimer?: ReturnType<typeof setInterval>;
  private factoryStatusWarmupTimer?: ReturnType<typeof setTimeout>;
  private lastAutoRefreshDate?: string;
  private latestFactoryDispatchId: string | null = null;
  private inFlightFactoryStatus: Promise<Record<string, unknown>> | null = null;

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cache: CommonCacheService,
  ) {}

  onModuleInit() {
    if (!StrategyMarketService.AUTO_REFRESH_ENABLED) {
      this.logger.log('策略排名自动刷新已禁用');
    } else {
      this.startAutoRefreshTimer();
    }
    this.scheduleFactoryStatusWarmup();
  }

  onModuleDestroy() {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = undefined;
    }
    if (this.factoryStatusWarmupTimer) {
      clearTimeout(this.factoryStatusWarmupTimer);
      this.factoryStatusWarmupTimer = undefined;
    }
  }

  private startAutoRefreshTimer() {
    if (this.autoRefreshTimer) return;
    this.autoRefreshTimer = detachTimer(setInterval(() => {
      void this.runAutoRefreshTick();
    }, StrategyMarketService.AUTO_REFRESH_CHECK_MS));
    void this.runAutoRefreshTick();
    this.logger.log(
      `策略排名自动刷新已启动（每 ${StrategyMarketService.AUTO_REFRESH_CHECK_MS / 60000} 分钟检查，收盘后 ${StrategyMarketService.AUTO_REFRESH_HOUR}:${String(StrategyMarketService.AUTO_REFRESH_MINUTE).padStart(2, '0')} 触发）`,
    );
  }

  private scheduleFactoryStatusWarmup() {
    if (this.factoryStatusWarmupTimer) {
      clearTimeout(this.factoryStatusWarmupTimer);
    }
    this.factoryStatusWarmupTimer = detachTimer(setTimeout(() => {
      this.factoryStatusWarmupTimer = undefined;
      void this.fetchFactoryStatusWithCache().catch((error) => {
        this.logger.debug(`预热 factory/status 缓存失败: ${String(error)}`);
      });
    }, StrategyMarketService.FACTORY_STATUS_WARMUP_DELAY_MS));
  }

  private isAfterMarketClose(now: Date) {
    const { hour, minute } = getMarketTimeParts(now, StrategyMarketService.AUTO_REFRESH_TIMEZONE);
    if (hour > StrategyMarketService.AUTO_REFRESH_HOUR) return true;
    if (hour < StrategyMarketService.AUTO_REFRESH_HOUR) return false;
    return minute >= StrategyMarketService.AUTO_REFRESH_MINUTE;
  }

  private dateKey(now: Date) {
    const { year, month, day } = getMarketTimeParts(now, StrategyMarketService.AUTO_REFRESH_TIMEZONE);
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

  private async call(
    action: StrategyManagerAction,
    params: Record<string, unknown> = {},
    options: StrategyManagerCallOptions = {},
  ) {
    try {
      const result = await this.mcp.callTool(
        'strategy_manager',
        {
          action,
          params,
        },
        {
          timeoutMs: options.timeoutMs,
        },
      );
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

  private async clearFactoryRunCaches() {
    await this.cache.del(buildFactoryStatusCacheKey());
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

  private normalizeFactoryStatusResponse(payload: unknown): Record<string, unknown> {
    const status = this.asRecord(payload);
    const normalized: Record<string, unknown> = {};

    const passthroughKeys = [
      'running',
      'run_time',
      'last_run',
      'last_summary',
      'last_validation_grade_distribution',
      'last_raw_validation_grade_distribution',
      'last_effective_validation_grade_distribution',
      'last_raw_validation_total_score_mean',
      'last_raw_validation_total_score_p50',
      'last_raw_validation_total_score_p90',
      'last_raw_validation_a_rate',
      'last_raw_validation_b_rate',
      'last_raw_validation_c_rate',
      'last_raw_validation_d_rate',
      'last_strict_incubation_ready_count',
      'last_strict_incubation_ready_rate',
      'last_live_candidate_ready_count',
      'last_live_candidate_ready_rate',
      'last_raw_b_or_above_count',
      'last_raw_b_or_above_rate',
      'last_strict_ready_given_raw_b_count',
      'last_strict_ready_given_raw_b_rate',
      'last_live_ready_given_raw_b_count',
      'last_live_ready_given_raw_b_rate',
      'recent_run_diagnostics',
      'last_validation_family_quality_panel',
      'quality_baseline',
      'high_confidence_enabled',
      'evidence_contract_enabled',
      'confidence_diagnostics_enabled',
      'execution_audit_enabled',
      'quality_ui_v2_enabled',
      'research_protocol_v2_enabled',
      'gate_model_v2_enabled',
      'trace_ledger_v2_enabled',
      'feedback_v2_enabled',
      'trace_ledger_v2_implemented',
      'governance_gate_report_v2_implemented',
      'execution_audit_entity_chain_available',
      'spec_completeness_mode',
      'signal_quality_registry',
      'research_window',
      'full_market_topn',
      'feature_flags',
      'schedule_mode',
      'execution_mode',
      'engine_version',
      'runtime_enabled',
      'event_runtime_mode',
      'readiness_hard_block_enabled',
      'readiness_min_score',
      'readiness_min_completion_ratio',
      'factor_auto_refresh_enabled',
      'factor_refresh_timeout_sec',
    ] as const;

    for (const key of passthroughKeys) {
      if (key in status) {
        normalized[key] = status[key];
      }
    }

    const rawLastResult = this.asRecord(status.last_result);
    const compactLastResult: Record<string, unknown> = {};
    const lastResultStatus = String(rawLastResult.status ?? status.last_status ?? '').trim();
    if (lastResultStatus) compactLastResult.status = lastResultStatus;
    if (rawLastResult.error != null) compactLastResult.error = String(rawLastResult.error);
    if (Object.keys(compactLastResult).length > 0) {
      normalized.last_result = compactLastResult;
    }

    return normalized;
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

  private buildActorPermissions(input?: { userId?: string | null; role?: string | null }) {
    const userId = String(input?.userId ?? '').trim();
    const role = String(input?.role ?? 'user').trim().toLowerCase();
    const isAdmin = role === 'admin';
    return {
      can_run_factory: isAdmin,
      can_ai_generate: isAdmin,
      can_create_personal_strategy: Boolean(userId),
      can_edit_own_strategy: Boolean(userId),
      can_create_paper_session: Boolean(userId),
      can_view_operator_panels: isAdmin,
    };
  }

  private managerActorParams(input?: { actorId?: string | null; role?: string | null }) {
    const actorId = String(input?.actorId ?? '').trim();
    const role = String(input?.role ?? '').trim();
    return {
      ...(actorId ? { actor_id: actorId, user_id: actorId } : {}),
      ...(role ? { actor_role: role, actor_roles: [role] } : {}),
    };
  }

  private normalizeStrategyDetail<T>(payload: T): T {
    return normalizeStrategyDetailResponse(payload) as T;
  }

  private async fetchRankingWithCache(
    params: { status?: string; strategy_type?: string; limit?: number; rank_keys?: string[]; offset?: number },
    forceRefresh = false,
  ) {
    const cacheKey = buildRankingCacheKey(params);
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
    const cacheKey = buildFactoryRunsCacheKey(limit);
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

  private async fetchFactoryStatusWithCache(forceRefresh = false) {
    const cacheKey = buildFactoryStatusCacheKey();
    const ttl = this.cache.resolveTtl('strategy.factory_status', StrategyMarketService.FACTORY_STATUS_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta<Record<string, unknown>>(cacheKey);
      if (cached.value) return cached.value;
      if (this.inFlightFactoryStatus) return this.inFlightFactoryStatus;
    } else {
      await this.cache.del(cacheKey);
    }

    const request = (async () => {
      const data = this.normalizeFactoryStatusResponse(await this.call('factory_status'));
      await this.cache.set(cacheKey, data, ttl);
      return data;
    })();
    this.inFlightFactoryStatus = request;
    try {
      return await request;
    } finally {
      if (this.inFlightFactoryStatus === request) {
        this.inFlightFactoryStatus = null;
      }
    }
  }

  private async fetchFactoryRunDetailWithCache(runId: string, forceRefresh = false) {
    const cacheKey = buildFactoryRunDetailCacheKey(runId);
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

  private async callQuantManager(action: string, params: Record<string, unknown> = {}) {
    return this.mcp.callTool('quant_manager', {
      action,
      params,
    });
  }

  private flattenMcpResult(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object') return { raw: payload };
    const obj = payload as Record<string, unknown>;
    if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) {
      const { data: inner, ...rest } = obj;
      return { ...rest, ...(inner as Record<string, unknown>) };
    }
    return obj;
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  }

  private asRecordArray(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) return [];
    return value.filter(
      (item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
    );
  }

  private toNum(value: unknown): number | null {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  private unwrapSettledObject(
    result: PromiseSettledResult<unknown>,
    section: string,
  ): { data: Record<string, unknown>; error: string | null } {
    if (result.status === 'fulfilled') {
      return { data: this.asRecord(result.value), error: null };
    }
    const message = result.reason instanceof Error ? result.reason.message : String(result.reason);
    return {
      data: {},
      error: `${section}: ${message}`,
    };
  }

  private normalizeBackgroundFactoryRunState(payload: unknown): BackgroundFactoryRunState | null {
    const data = this.asRecord(payload);
    const dispatchId = String(data.dispatch_id ?? '').trim();
    if (!dispatchId) return null;
    const rawStatus = String(data.status ?? 'queued').trim().toLowerCase();
    const status: BackgroundFactoryRunStatus =
      rawStatus === 'success' || rawStatus === 'failed' || rawStatus === 'running' ? rawStatus : 'queued';
    return {
      request_id: dispatchId,
      status,
      started_at: String(data.started_at ?? data.requested_at ?? new Date().toISOString()),
      completed_at: data.completed_at == null ? null : String(data.completed_at),
      message:
        String(data.message ?? '')
          .trim() || (status === 'failed' ? '策略工厂后台运行失败。' : '策略工厂后台调度中。'),
      error: data.error == null ? null : String(data.error),
      upstream_run_id: data.run_id == null ? null : String(data.run_id),
    };
  }

  private async loadBackgroundFactoryRunState(dispatchId: string | null | undefined = this.latestFactoryDispatchId) {
    const targetId = String(dispatchId ?? '').trim();
    if (!targetId) return null;
    try {
      const payload = await this.call('factory_dispatch_status', { dispatch_id: targetId });
      const state = this.normalizeBackgroundFactoryRunState(payload);
      if (state) {
        this.latestFactoryDispatchId = state.request_id;
        if (state.status === 'success' || state.status === 'failed') {
          await this.clearFactoryRunCaches();
        }
      }
      return state;
    } catch (error) {
      this.logger.debug(`读取策略工厂 dispatch 状态失败 dispatch_id=${targetId}: ${String(error)}`);
      return null;
    }
  }

  private mergeFactoryStatusWithBackgroundRun<T>(payload: T, backgroundRun?: BackgroundFactoryRunState | null): T {
    if (!backgroundRun || !payload || typeof payload !== 'object') return payload;

    const data = payload as Record<string, unknown>;
    return {
      ...(data as object),
      running:
        backgroundRun.status === 'queued' || backgroundRun.status === 'running'
          ? true
          : Boolean(data.running),
      local_background_run: backgroundRun,
    } as T;
  }

  private mergeFactoryRunsWithBackgroundRun<T>(
    payload: T,
    limit?: number,
    backgroundRun?: BackgroundFactoryRunState | null,
  ): T {
    if (!backgroundRun || !payload || typeof payload !== 'object') return payload;

    const data = payload as Record<string, unknown>;
    const items = Array.isArray(data.items) ? [...data.items] : [];
    const alreadyIncluded = items.some((item) => {
      if (!item || typeof item !== 'object') return false;
      const runId = String((item as Record<string, unknown>).run_id ?? '');
      return runId === backgroundRun.request_id || runId === String(backgroundRun.upstream_run_id ?? '');
    });

    if (!alreadyIncluded) {
      items.unshift(
        this.normalizeFactoryRun({
          run_id: backgroundRun.request_id,
          status:
            backgroundRun.status === 'queued' || backgroundRun.status === 'running'
              ? 'running'
              : backgroundRun.status,
          started_at: backgroundRun.started_at,
          completed_at: backgroundRun.completed_at,
          error: backgroundRun.error,
          summary: {
            run_id: backgroundRun.upstream_run_id ?? backgroundRun.request_id,
            status: backgroundRun.status,
            source: 'bff_background_dispatch',
          },
          trace_id: backgroundRun.request_id,
          local_background_run: backgroundRun,
        }),
      );
    }

    const boundedItems = items.slice(0, Math.max(1, Math.min(200, Number(limit) || items.length || 20)));
    const baseCount = Number.isFinite(Number(data.count)) ? Number(data.count) : 0;
    return {
      ...(data as object),
      items: boundedItems,
      latest: boundedItems[0] ?? null,
      count: Math.max(baseCount, boundedItems.length),
      local_background_run: backgroundRun,
    } as T;
  }

  async list(params: { status?: string; strategy_type?: string; limit?: number; offset?: number }) {
    return this.call('list', params);
  }

  async detail(id: string, actor?: { userId?: string | null; role?: string | null }) {
    const result = await this.call('detail', {
      strategy_id: id,
      ...this.managerActorParams({ actorId: actor?.userId, role: actor?.role }),
    });
    if (!result) throw new NotFoundException(`策略 ${id} 不存在`);
    const detail = this.normalizeStrategyDetail(result) as Record<string, unknown>;
    const strategy = this.asRecord(detail.strategy);
    if (String(strategy.id ?? '').trim() === '') {
      throw new BadGatewayException({
        success: false,
        message: `策略 ${id} 详情契约异常`,
        detail: 'detail response missing strategy.id',
      });
    }
    return detail;
  }

  async reviewReport(id: string) {
    return this.call('review_report', { strategy_id: id });
  }

  async reviewReportRecheck(id: string) {
    return this.call('review_report_recheck', { strategy_id: id });
  }

  async reviewWorkflow(
    id: string,
    params: {
      include_factory_status?: boolean;
      include_review_report?: boolean;
      include_runtime_alerts?: boolean;
      run_factory_once?: boolean;
      run_runtime_cycle?: boolean;
      idempotency_key?: string;
      as_of?: string;
    } = {},
    actor?: { userId?: string | null; role?: string | null },
  ) {
    const payload = await this.mcp.callTool('strategy_review_workflow', {
      strategy_id: id,
      include_factory_status: params.include_factory_status,
      include_review_report: params.include_review_report,
      include_runtime_alerts: params.include_runtime_alerts,
      run_factory_once: params.run_factory_once,
      run_runtime_cycle: params.run_runtime_cycle,
      idempotency_key: params.idempotency_key,
      as_of: params.as_of,
      actor_id: actor?.userId,
      actor_roles: actor?.role ? [actor.role] : undefined,
    });
    const result = this.asRecord(this.flattenMcpResult(payload));
    if (!result.owner_state && this.asRecord(result.closure_review).owner_state) {
      result.owner_state = this.asRecord(result.closure_review).owner_state;
      result.favorite_state = this.asRecord(result.closure_review).favorite_state;
      result.paper_session_state = this.asRecord(result.closure_review).paper_session_state;
      result.presentation = this.asRecord(result.closure_review).presentation;
    }
    return result;
  }

  async closureReview(
    id: string,
    params: {
      as_of?: string;
      correlation_id?: string;
      user_id?: string;
      role?: string;
    } = {},
  ) {
    return this.call('closure_review', {
      strategy_id: id,
      as_of: params.as_of,
      correlation_id: params.correlation_id,
      ...this.managerActorParams({ actorId: params.user_id, role: params.role }),
    });
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

  async favorite(id: string, userId: string) {
    return this.subscribe(id, userId);
  }

  async unfavorite(id: string, userId: string) {
    return this.unsubscribe(id, userId);
  }

  async myFavorites(userId: string) {
    const payload = this.asRecord(await this.mySubscriptions(userId));
    return {
      ...payload,
      favorites: Array.isArray(payload.subscriptions) ? payload.subscriptions : (Array.isArray(payload.items) ? payload.items : []),
    };
  }

  async myStrategies(
    actorId: string,
    role: string,
    params: { include_archived?: boolean; limit?: number; offset?: number } = {},
  ) {
    return this.call('my_strategies', {
      ...this.managerActorParams({ actorId, role }),
      include_archived: params.include_archived,
      limit: params.limit,
      offset: params.offset,
    });
  }

  async forkStrategy(id: string, actor: { actorId: string; role: string }) {
    return this.call('fork_strategy', {
      strategy_id: id,
      ...this.managerActorParams(actor),
    });
  }

  async updateStrategy(id: string, updates: Record<string, unknown>, actor: { actorId: string; role: string }) {
    return this.call('update_strategy', {
      strategy_id: id,
      updates,
      ...this.managerActorParams(actor),
    });
  }

  async deletePersonalStrategy(id: string, actor: { actorId: string; role: string }) {
    return this.call('delete_personal_strategy', {
      strategy_id: id,
      ...this.managerActorParams(actor),
    });
  }

  async paperSession(id: string, actor: { actorId: string; role: string }) {
    return this.call('paper_session_get', {
      strategy_id: id,
      ...this.managerActorParams(actor),
    });
  }

  async getOrCreatePaperSession(id: string, actor: { actorId: string; role: string }) {
    return this.call('paper_session_get_or_create', {
      strategy_id: id,
      ...this.managerActorParams(actor),
    });
  }

  async aiOptimizePersonalStrategy(id: string, actor: { actorId: string; role: string }) {
    return this.call('ai_optimize_personal_strategy', {
      strategy_id: id,
      ...this.managerActorParams(actor),
    });
  }

  async submit(id: string) {
    return this.call('submit', { strategy_id: id });
  }

  async factoryStatus() {
    const backgroundRun = await this.loadBackgroundFactoryRunState();
    return this.mergeFactoryStatusWithBackgroundRun(await this.fetchFactoryStatusWithCache(), backgroundRun);
  }

  async factoryRunOnce() {
    const activeRun = await this.loadBackgroundFactoryRunState();
    if (activeRun && (activeRun.status === 'queued' || activeRun.status === 'running')) {
      return {
        accepted: true,
        already_running: true,
        queued: false,
        request_id: activeRun.request_id,
        status: activeRun.status,
        started_at: activeRun.started_at,
        message: activeRun.message,
      };
    }
    const dispatchPayload = this.asRecord(await this.call('factory_dispatch_run'));
    const backgroundRun = this.normalizeBackgroundFactoryRunState(dispatchPayload);
    if (backgroundRun) {
      this.latestFactoryDispatchId = backgroundRun.request_id;
    }
    await this.cache.del(buildFactoryStatusCacheKey());

    return {
      accepted: Boolean(dispatchPayload.accepted ?? true),
      already_running: Boolean(dispatchPayload.already_running ?? false),
      queued: Boolean(dispatchPayload.queued ?? true),
      request_id: backgroundRun?.request_id ?? String(dispatchPayload.dispatch_id ?? ''),
      dispatch_id: backgroundRun?.request_id ?? String(dispatchPayload.dispatch_id ?? ''),
      status: backgroundRun?.status ?? String(dispatchPayload.status ?? 'queued'),
      started_at: backgroundRun?.started_at ?? new Date().toISOString(),
      message: backgroundRun?.message ?? '策略工厂请求已受理，正在后台调度。',
    };
  }

  async factoryRuns(limit?: number) {
    const backgroundRun = await this.loadBackgroundFactoryRunState();
    return this.mergeFactoryRunsWithBackgroundRun(await this.fetchFactoryRunsWithCache(limit), limit, backgroundRun);
  }

  async factoryRunDetail(runId: string) {
    return this.fetchFactoryRunDetailWithCache(runId);
  }

  async factoryTopnLatest(limit?: number) {
    return this.call('factory_topn_latest', {
      limit: limit == null ? undefined : Math.max(1, Math.min(Number(limit) || 20, 100)),
    });
  }

  async factoryRunTopn(runId: string, limit?: number) {
    return this.call('factory_run_topn', {
      run_id: runId,
      limit: limit == null ? undefined : Math.max(1, Math.min(Number(limit) || 20, 100)),
    });
  }

  async factoryDispatchStatus(dispatchId: string) {
    const payload = await this.call('factory_dispatch_status', { dispatch_id: dispatchId });
    const backgroundRun = this.normalizeBackgroundFactoryRunState(payload);
    if (backgroundRun) {
      this.latestFactoryDispatchId = backgroundRun.request_id;
    }
    await this.cache.del(buildFactoryStatusCacheKey());
    return {
      ...(this.asRecord(payload) as object),
      local_background_run: backgroundRun,
    };
  }

  async factoryObservability() {
    return loadFactoryObservability({
      factoryStatus: () => this.factoryStatus(),
      factoryRuns: (limit) => this.factoryRuns(limit),
      callQuantManager: (action, params) => this.callQuantManager(action, params),
      flattenMcpResult: (payload) => this.flattenMcpResult(payload),
      unwrapSettledObject: (result, section) => this.unwrapSettledObject(result, section),
      asRecord: (value) => this.asRecord(value),
      asRecordArray: (value) => this.asRecordArray(value),
      toNum: (value) => this.toNum(value),
    });
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

  async capabilities(actor?: { userId?: string | null; role?: string | null }) {
    const capabilities = this.asRecord(await this.call('capabilities'));
    return {
      ...capabilities,
      system_capabilities: capabilities,
      actor_permissions: this.buildActorPermissions(actor),
    };
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

  async executionAuditAcceptance(id: string, params: { backfill?: boolean } = {}) {
    return this.call('execution_audit_acceptance', { strategy_id: id, ...params });
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
      scope?: string;
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
