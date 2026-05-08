import {
  BadRequestException,
  BadGatewayException,
  Injectable,
  Logger,
  NotFoundException,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type {
  StrategyManagerAction,
  StrategyManagerErrorCode,
  StrategyCoreChainAcceptanceResponse,
  StrategyCoreChainStep,
  StrategyCoreChainStepStatus,
  StrategyPaperContextResponse,
  StrategyPaperTrackSnapshot,
  StrategyRuntimeActionContract,
  StrategyRuntimeActionContractItem,
  StrategyRuntimeActionId,
  StrategyRuntimeActionStatus,
  StrategySourceKind,
  StrategySourceStage,
  StrategySourceStageExplanation,
} from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import { buildDataQuality } from '../common/data-quality';
import { DbService } from '../db/db.service';
import { PaperTradingService } from '../paper-trading/paper-trading.service';
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
import { buildFactoryMarketViewResponse } from './strategy.service.factory-market-view';
import { buildStrategyCapabilityDiagnostics } from './strategy-capability-diagnostics';

type AcceptanceRead<T> = {
  value: T | null;
  error: string | null;
};

@Injectable()
export class StrategyMarketService implements OnModuleInit, OnModuleDestroy {
  private static readonly RANKING_TTL = 1500; // 25 min
  private static readonly STRATEGY_SUMMARY_FALLBACK_TTL_MS = 5 * 60 * 1000;
  private static readonly FACTORY_STATUS_TTL = 15;
  private static readonly FACTORY_STATUS_WARMUP_DELAY_MS = Math.max(
    0,
    Number(process.env.STRATEGY_FACTORY_STATUS_WARMUP_DELAY_MS ?? '20000'),
  );
  private static readonly FACTORY_RUNS_TTL = 60;
  private static readonly FACTORY_RUN_DETAIL_TTL = 60;
  private static readonly READ_SURFACE_TIMEOUT_MS = 4_500;
  private static readonly RANKING_READ_TIMEOUT_MS = Math.max(
    StrategyMarketService.READ_SURFACE_TIMEOUT_MS,
    Number(process.env.STRATEGY_RANKING_TIMEOUT_MS ?? '15000'),
  );
  private static readonly DETAIL_FALLBACK_TIMEOUT_MS = 800;
  private static readonly FACTORY_MARKET_FAST_TIMEOUT_MS = 3_500;
  private static readonly FACTORY_MARKET_DETAIL_TIMEOUT_MS = 5_000;
  private static readonly AUTO_REFRESH_CHECK_MS = 5 * 60 * 1000; // 5 min
  private static readonly AUTO_REFRESH_HOUR = 15;
  private static readonly AUTO_REFRESH_MINUTE = 5;
  private static readonly AUTO_REFRESH_TIMEZONE = process.env.STRATEGY_MARKET_TIMEZONE || 'Asia/Shanghai';
  private static readonly AUTO_REFRESH_ENABLED = !['0', 'false', 'no'].includes(
    String(
      process.env.STRATEGY_MARKET_AUTO_REFRESH_ENABLED ??
        (process.env.NODE_ENV === 'test' ||
        (process.env.NODE_ENV !== 'production' && Number(process.env.MCP_POOL_SIZE ?? '8') <= 1)
          ? '0'
          : '1'),
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
  private readonly strategySummaryFallbackCache = new Map<
    string,
    { value: Record<string, unknown>; expiresAt: number }
  >();

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cache: CommonCacheService,
    private readonly db: DbService,
    private readonly paperTrading: PaperTradingService,
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
    this.autoRefreshTimer = detachTimer(
      setInterval(() => {
        void this.runAutoRefreshTick();
      }, StrategyMarketService.AUTO_REFRESH_CHECK_MS),
    );
    void this.runAutoRefreshTick();
    this.logger.log(
      `策略排名自动刷新已启动（每 ${StrategyMarketService.AUTO_REFRESH_CHECK_MS / 60000} 分钟检查，收盘后 ${StrategyMarketService.AUTO_REFRESH_HOUR}:${String(StrategyMarketService.AUTO_REFRESH_MINUTE).padStart(2, '0')} 触发）`,
    );
  }

  private scheduleFactoryStatusWarmup() {
    if (this.factoryStatusWarmupTimer) {
      clearTimeout(this.factoryStatusWarmupTimer);
    }
    this.factoryStatusWarmupTimer = detachTimer(
      setTimeout(() => {
        this.factoryStatusWarmupTimer = undefined;
        void this.fetchFactoryStatusWithCache(false, {
          timeoutMs: StrategyMarketService.FACTORY_MARKET_FAST_TIMEOUT_MS,
          retryOnTransportError: true,
        }).catch((error) => {
          this.logger.debug(`预热 factory/status 缓存失败: ${String(error)}`);
        });
      }, StrategyMarketService.FACTORY_STATUS_WARMUP_DELAY_MS),
    );
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
          retryOnTransportError: options.retryOnTransportError,
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
        if ('data' in obj) {
          if (this.isMcpToolErrorPayload(obj.data)) {
            throw this.asMcpToolError(action, obj.data);
          }
          return obj.data;
        }
      }
      if (this.isMcpToolErrorPayload(result)) {
        throw this.asMcpToolError(action, result);
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

  private isMcpToolErrorPayload(value: unknown): value is string {
    return typeof value === 'string' && /^Error executing tool\b/i.test(value.trim());
  }

  private asMcpToolError(action: StrategyManagerAction, value: string) {
    return new BadGatewayException({
      success: false,
      code: 'STRATEGY_MANAGER_BACKEND_ERROR',
      message: `调用 strategy_manager.${action} 失败`,
      detail: value,
    });
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
      'status',
      'running',
      'status_source',
      'scheduler_attached',
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
    const role = String(input?.role ?? 'user')
      .trim()
      .toLowerCase();
    const isAdmin = role === 'admin';
    return {
      can_run_factory: isAdmin,
      can_ai_generate: isAdmin,
      can_create_personal_strategy: Boolean(userId),
      can_edit_own_strategy: Boolean(userId),
      can_ai_suggest_personal_strategy: Boolean(userId),
      can_ai_optimize_personal_strategy: Boolean(userId),
      can_persist_personal_strategy: Boolean(userId),
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

  private isAdminRole(role?: string | null) {
    return String(role ?? '').trim().toLowerCase() === 'admin';
  }

  private strategyMetadata(strategy: Record<string, unknown>) {
    return this.asRecord(this.asRecord(strategy.params).metadata);
  }

  private buildLocalStrategySurfaceState(
    strategy: Record<string, unknown>,
    actor?: { userId?: string | null; role?: string | null },
  ) {
    const userId = String(actor?.userId ?? '').trim();
    const role = String(actor?.role ?? '').trim().toLowerCase();
    const authorId = String(strategy.author_id ?? '').trim();
    const existingOwnerState = this.asRecord(strategy.owner_state);
    const existingFavoriteState = this.asRecord(strategy.favorite_state);
    const existingPaperSessionState = this.asRecord(strategy.paper_session_state);
    const personalStrategy = Boolean(
      existingOwnerState.personal_strategy === true || this.isPersonalStrategyRecord(strategy),
    );
    const owned =
      typeof existingOwnerState.owned === 'boolean'
        ? existingOwnerState.owned
        : Boolean(userId && authorId && userId === authorId);
    const editable = Boolean(userId && owned && personalStrategy);
    const ownerState = {
      ...existingOwnerState,
      kind: !userId
        ? 'anonymous'
        : editable
          ? 'owned_personal_strategy'
          : owned
            ? 'owned_strategy'
            : 'market_strategy',
      owned,
      editable,
      author_id: authorId || null,
      personal_strategy: personalStrategy,
      admin_override: role === 'admin',
    };
    const favoriteState = {
      available: Boolean(userId),
      favorited: false,
      label: userId ? '收藏策略' : '登录后收藏',
      ...existingFavoriteState,
    };
    const paperSessionState = {
      available: Boolean(userId),
      has_session: false,
      session_type: 'personal-strategy',
      mode: 'personal-strategy',
      ...existingPaperSessionState,
    };
    return { ownerState, favoriteState, paperSessionState };
  }

  private normalizeStrategySurfaceState<T>(
    strategyLike: T,
    actor?: { userId?: string | null; role?: string | null },
  ): T {
    const strategy = this.asRecord(strategyLike);
    const strategyId = String(strategy.id ?? strategy.strategy_id ?? '').trim();
    if (!strategyId) return strategyLike;
    const surface = this.buildLocalStrategySurfaceState(strategy, actor);
    return {
      ...(strategyLike as object),
      owner_state: surface.ownerState,
      favorite_state: surface.favoriteState,
      paper_session_state: surface.paperSessionState,
    } as T;
  }

  private normalizeMyStrategiesPayload<T>(
    payload: T,
    actor: { userId?: string | null; role?: string | null },
  ): T {
    const record = this.asRecord(payload);
    if (Object.keys(record).length === 0) return payload;

    const normalizeRows = (rows: unknown[]) =>
      rows
        .map((row) => this.normalizeStrategySurfaceState(row, actor))
        .filter((row) => this.isPersonalStrategyRecord(this.asRecord(row)))
        .map((row) => this.withRuntimeActionContract(row, actor));

    const normalizedStrategies = Array.isArray(record.strategies) ? normalizeRows(record.strategies) : null;
    const normalizedItems = Array.isArray(record.items)
      ? normalizeRows(record.items)
      : normalizedStrategies;
    const derivedCount = Math.max(normalizedStrategies?.length ?? 0, normalizedItems?.length ?? 0);

    return {
      ...(record as object),
      ...(normalizedStrategies ? { strategies: normalizedStrategies } : {}),
      ...(normalizedItems ? { items: normalizedItems } : {}),
      count: derivedCount,
    } as T;
  }

  private isPersonalStrategyRecord(strategy: Record<string, unknown>) {
    const tags = Array.isArray(strategy.tags)
      ? strategy.tags.map((item) => String(item ?? '').trim().toLowerCase())
      : [];
    const metadata = this.strategyMetadata(strategy);
    return Boolean(
      strategy.personal_strategy === true ||
      metadata.source_strategy_id ||
      tags.includes('personal_strategy') ||
      tags.includes('draft_personal_strategy') ||
      tags.includes('forked_strategy') ||
      String(strategy.status ?? '').trim().toLowerCase() === 'draft',
    );
  }

  private sourceStrategyId(strategy: Record<string, unknown>) {
    const value = String(this.strategyMetadata(strategy).source_strategy_id ?? '').trim();
    return value || null;
  }

  private firstText(...values: unknown[]): string | null {
    for (const value of values) {
      const text = String(value ?? '').trim();
      if (text) return text;
    }
    return null;
  }

  private normalizeCode(value: unknown) {
    return String(value ?? '').trim().toLowerCase();
  }

  private sourceActionLabel(value: unknown) {
    const code = this.normalizeCode(value);
    const labels: Record<string, string> = {
      factory_run_once: '工厂单次运行',
      factory_dispatch_run: '工厂后台调度',
      strategy_factory_submit: '工厂提交',
      execution_audit_verification: '执行审计核验',
      execution_audit_acceptance: '执行审计验收',
      validate_factor_candidate: '因子候选验证',
      incubation_overview: '孵化概览',
    };
    return labels[code] ?? (code ? code.replaceAll('_', ' ') : null);
  }

  private stageSourceLabel(value: unknown) {
    const code = this.normalizeCode(value);
    const labels: Record<string, string> = {
      paper_account: '孵化账户',
      paper_account_status: '孵化账户状态',
      pipeline: '孵化流水线',
      status_fallback: '市场状态回退',
    };
    return labels[code] ?? (code ? code.replaceAll('_', ' ') : null);
  }

  private sourceStageMeta(stage: StrategySourceStage) {
    const meta: Record<StrategySourceStage, { label: string; maturity: string; summary: string }> = {
      candidate: {
        label: '候选',
        maturity: '孵化产物',
        summary: '工厂或策略管理器已经产生候选，但当前未见完整研究、治理或上架证据。',
      },
      research: {
        label: '研究',
        maturity: '研究中',
        summary: '策略已进入研究窗口、全市场 Top N 或工厂运行视图，仍需补齐质量门和治理证据。',
      },
      governance: {
        label: '治理',
        maturity: '治理中',
        summary: '策略已进入孵化、执行审计或治理池，适合继续跟踪，但成熟度仍受阻塞和风险约束。',
      },
      available: {
        label: '可用',
        maturity: '成熟策略',
        summary: '策略已上架或晋级完成，可作为成熟策略查看、复制和纳入模拟测试。',
      },
    };
    return meta[stage];
  }

  private sourceKindLabel(kind: StrategySourceKind) {
    const labels: Record<StrategySourceKind, string> = {
      factory_market_view: '工厂 Market View',
      factory_run: '工厂运行产物',
      research_window: '研究任务产物',
      governance_pool: '治理/孵化池',
      personal_copy: '个人策略副本',
      manual_market: '市场策略',
      degraded_snapshot: '降级快照',
      unknown: '来源待补证据',
    };
    return labels[kind];
  }

  private resolveSourceKind(strategy: Record<string, unknown>, metadata: Record<string, unknown>): StrategySourceKind {
    const id = String(strategy.id ?? strategy.strategy_id ?? '').trim().toLowerCase();
    const source = this.normalizeCode(strategy.source ?? metadata.source);
    const sourceAction = this.normalizeCode(
      strategy.source_action ?? metadata.source_action ?? metadata.submit_source_action,
    );
    if (this.sourceStrategyId(strategy)) return 'personal_copy';
    if (source === 'degraded_minimal_snapshot' || source === 'degraded_snapshot') return 'degraded_snapshot';
    if (
      id.startsWith('factory_topn_') ||
      Boolean(
        this.firstText(
          strategy.portfolio_candidate_id,
          metadata.portfolio_candidate_id,
          strategy.snapshot_id,
          metadata.snapshot_id,
          this.asRecord(strategy.full_market_topn).snapshot_id,
          this.asRecord(metadata.full_market_topn).snapshot_id,
        ),
      )
    ) {
      return 'factory_market_view';
    }
    if (
      sourceAction.includes('factory') ||
      Boolean(this.firstText(strategy.factory_run_id, metadata.factory_run_id, strategy.run_id, metadata.run_id))
    ) {
      return 'factory_run';
    }
    if (
      Boolean(this.firstText(metadata.task_signature, strategy.task_signature)) ||
      Object.keys(this.asRecord(metadata.research_task ?? strategy.research_task)).length > 0
    ) {
      return 'research_window';
    }
    const incubationSurface = this.asRecord(strategy.incubation_surface);
    if (
      Boolean(incubationSurface.entered_incubator) ||
      Boolean(this.firstText(incubationSurface.pipeline_stage, incubationSurface.execution_audit_gate_status))
    ) {
      return 'governance_pool';
    }
    if (source === 'db_snapshot') return 'manual_market';
    return 'unknown';
  }

  private resolveSourceStage(strategy: Record<string, unknown>, kind: StrategySourceKind): StrategySourceStage {
    const status = this.normalizeCode(strategy.status);
    const incubationSurface = this.asRecord(strategy.incubation_surface);
    const pipelineStage = this.normalizeCode(incubationSurface.pipeline_stage);
    const stageSource = this.normalizeCode(incubationSurface.stage_source);
    if (status === 'listed' || status === 'published' || pipelineStage === 'promoted') {
      return 'available';
    }
    if (
      status === 'incubating' ||
      status === 'submitted' ||
      status === 'suspended' ||
      status === 'deprecated' ||
      Boolean(incubationSurface.entered_incubator) ||
      ['paper_account', 'paper_account_status', 'pipeline'].includes(stageSource) ||
      Boolean(this.firstText(incubationSurface.execution_audit_gate_status, incubationSurface.latest_decision))
    ) {
      return 'governance';
    }
    if (kind === 'factory_market_view' || kind === 'research_window') {
      return 'research';
    }
    return 'candidate';
  }

  private collectSourceEvidence(strategy: Record<string, unknown>, metadata: Record<string, unknown>) {
    const incubationSurface = this.asRecord(strategy.incubation_surface);
    const fullMarketTopn = this.asRecord(strategy.full_market_topn ?? metadata.full_market_topn);
    const evidence: Array<{ key: string; label: string; value: string }> = [];
    const add = (key: string, label: string, value: unknown, formatter?: (value: unknown) => string | null) => {
      if (evidence.some((item) => item.key === key)) return;
      const text = formatter ? formatter(value) : this.firstText(value);
      if (text) evidence.push({ key, label, value: text });
    };
    add('source_strategy_id', '来源策略', this.sourceStrategyId(strategy));
    add('factory_run_id', '工厂运行', this.firstText(strategy.factory_run_id, metadata.factory_run_id, fullMarketTopn.run_id));
    add('source_run_id', '来源运行/快照', this.firstText(strategy.source_run_id, metadata.source_run_id));
    add('snapshot_id', 'Market View 快照', this.firstText(strategy.snapshot_id, metadata.snapshot_id, fullMarketTopn.snapshot_id));
    add('portfolio_candidate_id', '组合候选', this.firstText(strategy.portfolio_candidate_id, metadata.portfolio_candidate_id));
    add(
      'source_action',
      '来源动作',
      this.firstText(strategy.source_action, metadata.source_action, fullMarketTopn.source_action),
      (value) => this.sourceActionLabel(value),
    );
    add('research_task', '研究任务', this.firstText(metadata.task_signature, this.asRecord(metadata.research_task).task_id));
    add('stage_source', '阶段证据', incubationSurface.stage_source, (value) => this.stageSourceLabel(value));
    add('pipeline_stage', '孵化阶段', incubationSurface.pipeline_stage);
    add('execution_audit_gate_status', '执行审计', incubationSurface.execution_audit_gate_status);
    add('latest_decision', '最新决策', incubationSurface.latest_decision);
    return evidence.slice(0, 8);
  }

  private buildSourceStageExplanation(input: {
    strategy: Record<string, unknown>;
    actionContract?: StrategyRuntimeActionContract | null;
  }): StrategySourceStageExplanation {
    const strategy = this.asRecord(input.strategy);
    const metadata = this.nestedMetadata(strategy);
    const sourceKind = this.resolveSourceKind(strategy, metadata);
    const currentStage = this.resolveSourceStage(strategy, sourceKind);
    const stageMeta = this.sourceStageMeta(currentStage);
    const sourceLabel = this.sourceKindLabel(sourceKind);
    const status = String(strategy.status ?? '').trim() || 'unknown';
    const incubationSurface = this.asRecord(strategy.incubation_surface);
    const stageSource = this.stageSourceLabel(incubationSurface.stage_source);
    const sourceAction = this.sourceActionLabel(
      strategy.source_action ?? metadata.source_action ?? this.asRecord(strategy.full_market_topn).source_action,
    );
    const evidence = this.collectSourceEvidence(strategy, metadata);
    const sourceSummary = [
      sourceLabel,
      sourceAction ? `动作 ${sourceAction}` : null,
      stageSource ? `阶段来自${stageSource}` : null,
      evidence.find((item) => item.key === 'factory_run_id')?.value
        ? `运行 ${evidence.find((item) => item.key === 'factory_run_id')?.value}`
        : null,
    ].filter((item): item is string => Boolean(item)).join(' · ');
    const whyByStage: Record<StrategySourceStage, string> = {
      candidate: `策略管理器返回该策略作为候选展示，当前市场状态为 ${status}，尚未看到可用阶段证据。`,
      research: `该策略关联工厂 market view、研究窗口或 Top N 产物，因此进入策略超市供用户比较和继续跟踪。`,
      governance: `该策略处于 ${status} 或已进入孵化/治理链路，因此在超市中展示治理进度和可跟踪动作。`,
      available: `该策略处于 ${status} 或已晋级完成，因此作为成熟可用策略展示在超市中。`,
    };
    const limitationByStage: Record<StrategySourceStage, string | null> = {
      candidate: '候选阶段缺少研究、治理和上架证据，适合先查看来源或复制后自行测试。',
      research: '研究阶段仍需质量门、孵化账户和治理证据确认，不能直接视为成熟策略。',
      governance: '治理阶段仍受执行审计、阻塞项、风险事件和登录/所有权权限限制。',
      available: null,
    };
    const actions = input.actionContract?.actions ?? [];
    const availableActions = actions
      .filter((action) => action.status !== 'unavailable')
      .map((action) => ({
        id: action.id,
        label: action.short_label ?? action.label,
        status: action.status,
        effect: action.effect,
        href: action.navigation?.href ?? null,
      }));
    const restrictedActions = actions
      .filter((action) => action.status === 'unavailable')
      .map((action) => ({
        id: action.id,
        label: action.short_label ?? action.label,
        reason: action.unavailable_reason ?? '当前动作不可用',
        reason_code: action.reason_code ?? null,
      }));
    const actionSummary = [
      availableActions.length
        ? `现在可执行：${availableActions.map((action) => action.label).join('、')}`
        : '当前没有可直接执行的动作',
      restrictedActions.length
        ? `受限：${restrictedActions.map((action) => `${action.label}（${action.reason}）`).join('；')}`
        : null,
    ].filter((item): item is string => Boolean(item)).join('。');
    const firstRestrictedReason = restrictedActions[0]?.reason ?? null;

    return {
      dto_version: 'strategy_market.source_stage_explanation.v1',
      source_kind: sourceKind,
      source_label: sourceLabel,
      source_summary: sourceSummary || sourceLabel,
      current_stage: currentStage,
      stage_label: stageMeta.label,
      stage_summary: stageMeta.summary,
      maturity_label: stageMeta.maturity,
      why_visible: whyByStage[currentStage],
      available_actions: availableActions,
      restricted_actions: restrictedActions,
      action_summary: actionSummary,
      limitation_reason: limitationByStage[currentStage] ?? firstRestrictedReason,
      evidence,
    };
  }

  private runtimeAction(
    input: Omit<StrategyRuntimeActionContractItem, 'enabled' | 'requires_confirmation'>,
  ): StrategyRuntimeActionContractItem {
    return {
      ...input,
      enabled: input.status !== 'unavailable',
      requires_confirmation: input.status === 'confirm_required',
      unavailable_reason: input.status === 'unavailable'
        ? (input.unavailable_reason ?? '当前运行时合同未开放该动作')
        : null,
      confirm: input.status === 'confirm_required' ? input.confirm ?? null : null,
    };
  }

  private buildRuntimeActionContract(input: {
    strategy: Record<string, unknown>;
    actor?: { userId?: string | null; role?: string | null };
    ownerState?: Record<string, unknown> | null;
    favoriteState?: Record<string, unknown> | null;
    paperSessionState?: Record<string, unknown> | null;
  }): StrategyRuntimeActionContract {
    const strategy = this.asRecord(input.strategy);
    const strategyId = String(strategy.id ?? strategy.strategy_id ?? '').trim();
    const encodedStrategyId = encodeURIComponent(strategyId);
    const userId = String(input.actor?.userId ?? '').trim();
    const role = String(input.actor?.role ?? 'user').trim() || 'user';
    const isAdmin = this.isAdminRole(role);
    const ownerState = this.asRecord(input.ownerState);
    const favoriteState = this.asRecord(input.favoriteState);
    const paperSessionState = this.asRecord(input.paperSessionState);
    const authorId = String(ownerState.author_id ?? strategy.author_id ?? '').trim();
    const personalStrategy = Boolean(ownerState.personal_strategy === true || this.isPersonalStrategyRecord(strategy));
    const owned =
      typeof ownerState.owned === 'boolean'
        ? ownerState.owned
        : Boolean(userId && authorId && authorId === userId);
    const editable = Boolean(userId && owned && personalStrategy);
    const hasPaperSession = Boolean(paperSessionState.has_session);
    const paperAvailable = Boolean(userId && (paperSessionState.available ?? true));
    const sourceStrategyId = this.sourceStrategyId(strategy);

    const loginRequired = '需要登录后才能执行该动作';
    const order: StrategyRuntimeActionId[] = [
      'save_as_personal_strategy',
      'open_personal_paper_session',
      'view_factory_source',
      'ai_analyze_strategy',
      'ai_modify_personal_strategy',
    ];

    const saveAsPersonalStatus: StrategyRuntimeActionStatus = !userId
      ? 'unavailable'
      : personalStrategy
        ? 'unavailable'
        : 'confirm_required';
    const saveAsPersonalReason = !userId
      ? loginRequired
      : personalStrategy
        ? editable
          ? '当前已经是可编辑个人策略，无需再次收藏为个人策略'
          : '当前已经是个人策略副本，不能再次收藏为个人策略'
        : null;

    const paperStatus: StrategyRuntimeActionStatus = !paperAvailable
      ? 'unavailable'
      : hasPaperSession
        ? 'clickable'
        : 'confirm_required';
    const paperReason = !paperAvailable ? '需要登录后才能创建或打开个人模拟盘测试' : null;

    let aiModifyStatus: StrategyRuntimeActionStatus = 'confirm_required';
    let aiModifyReason: string | null = null;
    let aiModifyReasonCode: string | null = null;
    if (!userId) {
      aiModifyStatus = 'unavailable';
      aiModifyReason = '需要登录后才能交给 AI 修改个人策略';
      aiModifyReasonCode = 'login_required';
    } else if (!personalStrategy) {
      aiModifyStatus = 'unavailable';
      aiModifyReason = '当前是市场策略，只能先收藏为个人策略后再交给 AI 修改';
      aiModifyReasonCode = 'market_strategy_readonly';
    } else if (!editable) {
      aiModifyStatus = 'unavailable';
      aiModifyReason = '只能修改当前用户拥有的个人策略';
      aiModifyReasonCode = 'not_personal_strategy_owner';
    }

    const actions: StrategyRuntimeActionContractItem[] = [
      this.runtimeAction({
        id: 'save_as_personal_strategy',
        label: '收藏为个人策略',
        short_label: '收藏为个人',
        description: '复制当前策略为当前用户的个人策略草稿，后续可编辑、AI 修改和模拟盘测试。',
        status: saveAsPersonalStatus,
        effect: 'stateful',
        endpoint: strategyId ? { method: 'POST', path: `/strategy-market/${encodedStrategyId}/fork`, body: {} } : null,
        confirm: {
          message: '确认把当前市场策略复制成你的个人策略草稿？',
          confirm_label: '收藏为个人策略',
        },
        unavailable_reason: saveAsPersonalReason,
        reason_code: !userId ? 'login_required' : editable ? 'already_personal_strategy' : null,
        telemetry_key: 'strategy.runtime_action.save_as_personal_strategy',
      }),
      this.runtimeAction({
        id: 'open_personal_paper_session',
        label: hasPaperSession ? '打开模拟盘' : '加入模拟盘',
        short_label: hasPaperSession ? '打开模拟盘' : '加入模拟盘',
        description: hasPaperSession
          ? '打开当前策略已有的个人模拟盘测试账户。'
          : '为当前策略创建个人模拟盘测试账户，并跳转到模拟交易页。',
        status: paperStatus,
        effect: 'stateful',
        endpoint: strategyId
          ? { method: 'POST', path: `/strategy-market/${encodedStrategyId}/paper-session`, body: {} }
          : null,
        confirm: {
          message: '确认为当前策略创建个人模拟盘测试？',
          confirm_label: '加入模拟盘',
        },
        unavailable_reason: paperReason,
        reason_code: !paperAvailable ? 'login_required' : null,
        telemetry_key: 'strategy.runtime_action.open_personal_paper_session',
      }),
      this.runtimeAction({
        id: 'view_factory_source',
        label: '查看工厂来源',
        short_label: '工厂来源',
        description: sourceStrategyId
          ? `查看个人策略来源 ${sourceStrategyId} 以及工厂审查证据。`
          : '查看当前策略的工厂审查、来源证据、运行闭环和事件投影。',
        status: strategyId ? 'clickable' : 'unavailable',
        effect: 'navigation',
        navigation: strategyId
          ? { href: `/strategy-market/${encodedStrategyId}?tab=factory`, target: '_self' }
          : null,
        unavailable_reason: strategyId ? null : '策略 ID 缺失，无法打开工厂来源',
        reason_code: strategyId ? null : 'strategy_id_missing',
        telemetry_key: 'strategy.runtime_action.view_factory_source',
      }),
      this.runtimeAction({
        id: 'ai_analyze_strategy',
        label: '交给 AI 分析',
        short_label: 'AI 分析',
        description: '带着策略 ID 和名称打开 AI 助手，让助手基于当前策略上下文继续分析。',
        status: strategyId ? 'clickable' : 'unavailable',
        effect: 'advisory',
        navigation: strategyId
          ? {
              href: `/assistant?from=strategy-market&strategy_id=${encodedStrategyId}&q=${encodeURIComponent(`分析策略 ${String(strategy.name ?? strategyId)}`)}`,
              target: '_self',
            }
          : null,
        unavailable_reason: strategyId ? null : '策略 ID 缺失，无法交给 AI 分析',
        reason_code: strategyId ? null : 'strategy_id_missing',
        telemetry_key: 'strategy.runtime_action.ai_analyze_strategy',
      }),
      this.runtimeAction({
        id: 'ai_modify_personal_strategy',
        label: '交给 AI 修改个人策略',
        short_label: 'AI 修改',
        description: '直接对当前可编辑个人策略执行 AI 优化并写回草稿。',
        status: aiModifyStatus,
        effect: 'stateful',
        endpoint: strategyId
          ? { method: 'POST', path: `/strategy-market/${encodedStrategyId}/ai-optimize`, body: {} }
          : null,
        confirm: {
          message: 'AI 修改会写回当前个人策略草稿，并触发后验校验。确认继续？',
          confirm_label: '交给 AI 修改',
        },
        unavailable_reason: aiModifyReason,
        reason_code: aiModifyReasonCode,
        telemetry_key: 'strategy.runtime_action.ai_modify_personal_strategy',
      }),
    ];

    return {
      dto_version: 'strategy_market.runtime_actions.v1',
      strategy_id: strategyId,
      generated_at: new Date().toISOString(),
      source: 'bff.strategy_market.runtime_action_contract',
      actor: {
        authenticated: Boolean(userId),
        user_id: userId || null,
        role,
        is_admin: isAdmin,
      },
      state: {
        owned,
        editable,
        personal_strategy: personalStrategy,
        favorited: Boolean(favoriteState.favorited),
        paper_session_available: paperAvailable,
        has_paper_session: hasPaperSession,
        source_strategy_id: sourceStrategyId,
      },
      actions,
      default_order: order,
      summary: {
        executable_now: actions
          .filter((action) => action.status !== 'unavailable')
          .map((action) => action.id),
        blocked: actions
          .filter((action) => action.status === 'unavailable')
          .map((action) => ({
            id: action.id,
            reason: action.unavailable_reason ?? '当前运行时合同未开放该动作',
            reason_code: action.reason_code ?? null,
          })),
      },
    };
  }

  private withRuntimeActionContract<T>(
    strategyLike: T,
    actor?: { userId?: string | null; role?: string | null },
  ): T {
    const strategy = this.asRecord(strategyLike);
    const strategyId = String(strategy.id ?? strategy.strategy_id ?? '').trim();
    if (!strategyId) return strategyLike;
    const ownerState = this.asRecord(strategy.owner_state);
    const favoriteState = this.asRecord(strategy.favorite_state);
    const paperSessionState = this.asRecord(strategy.paper_session_state);
    const contract = this.buildRuntimeActionContract({
      strategy,
      actor,
      ownerState,
      favoriteState,
      paperSessionState,
    });
    const favoriteCount = Number(strategy.favorite_count ?? strategy.subscriber_count ?? 0);
    return {
      ...(strategyLike as object),
      favorite_count: Number.isFinite(favoriteCount) ? favoriteCount : 0,
      runtime_action_contract: contract,
      runtime_actions: contract.actions,
    } as T;
  }

  private withRuntimeActionContracts<T>(
    payload: T,
    actor?: { userId?: string | null; role?: string | null },
  ): T {
    if (Array.isArray(payload)) {
      return payload.map((item) => this.withRuntimeActionContract(item, actor)) as T;
    }
    const record = this.asRecord(payload);
    if (Object.keys(record).length === 0) return payload;
    const next: Record<string, unknown> = { ...record };
    for (const key of ['strategies', 'items', 'favorites', 'subscriptions']) {
      if (Array.isArray(next[key])) {
        next[key] = (next[key] as unknown[]).map((item) => this.withRuntimeActionContract(item, actor));
      }
    }
    return next as T;
  }

  private normalizeStrategyDetail<T>(payload: T): T {
    return normalizeStrategyDetailResponse(payload) as T;
  }

  private toIsoTimestamp(value: unknown): string | null {
    if (value instanceof Date) return value.toISOString();
    const text = String(value ?? '').trim();
    return text || null;
  }

  private toIsoDate(value: unknown): string | null {
    if (value instanceof Date) return value.toISOString().slice(0, 10);
    const text = String(value ?? '').trim();
    return text || null;
  }

  private async loadFactoryRunsSurfaceFromDb(limit = 5) {
    const normalizedLimit = Math.max(1, Math.min(Number(limit) || 5, 20));
    const result = await this.db.query<{
      id: number;
      run_id: string;
      status: string;
      started_at: Date | string | null;
      completed_at: Date | string | null;
      elapsed_seconds: number | null;
      summary: Record<string, unknown> | null;
      stages: Record<string, unknown> | null;
      error: string | null;
      execution_mode: string | null;
      engine_version: string | null;
      parity_result: Record<string, unknown> | null;
      artifact_refs: unknown[] | null;
    }>(
      `
        SELECT id, run_id, status, started_at, completed_at, elapsed_seconds, summary, stages, error,
               execution_mode, engine_version, parity_result, artifact_refs
        FROM strategy_factory_runs
        ORDER BY started_at DESC
        LIMIT $1
      `,
      [normalizedLimit],
    );
    const items = result.rows.map((row) => ({
      ...row,
      started_at: this.toIsoTimestamp(row.started_at),
      completed_at: this.toIsoTimestamp(row.completed_at),
      summary: this.asRecord(row.summary),
      stages: this.asRecord(row.stages),
      parity_result: this.asRecord(row.parity_result),
      artifact_refs: Array.isArray(row.artifact_refs) ? row.artifact_refs : [],
    }));
    return this.normalizeFactoryRunsResponse({
      items,
      count: items.length,
    });
  }

  private async loadFactoryTopnSurfaceFromDb(limit = 5) {
    const normalizedLimit = Math.max(1, Math.min(Number(limit) || 5, 100));
    const snapshotResult = await this.db.query<{
      snapshot_id: string;
      run_id: string;
      as_of_date: Date | string | null;
      trace_id: string | null;
      correlation_id: string | null;
      source_action: string | null;
      universe_count: number | null;
      eligible_count: number | null;
      topn_n: number | null;
      selection_rules: Record<string, unknown> | null;
      constituents: Record<string, unknown>[] | null;
      portfolio_candidate_id: string | null;
      metadata: Record<string, unknown> | null;
    }>(
      `
        SELECT snapshot_id, run_id, as_of_date, trace_id, correlation_id, source_action,
               universe_count, eligible_count, topn_n, selection_rules, constituents,
               portfolio_candidate_id, metadata
        FROM strategy_factory_topn_snapshots
        ORDER BY as_of_date DESC NULLS LAST, updated_at DESC
        LIMIT 1
      `,
    );
    const snapshotRow = snapshotResult.rows[0];
    if (!snapshotRow) {
      return {
        available: false,
        snapshot: null,
        top_scores: [],
        score_row_count: 0,
        requested_limit: normalizedLimit,
      };
    }

    const scoreCountResult = await this.db.query<{ count: string }>(
      `
        SELECT COUNT(*)::text AS count
        FROM strategy_factory_full_market_scores
        WHERE run_id = $1
      `,
      [snapshotRow.run_id],
    );
    const scoreRowCount = Number(scoreCountResult.rows[0]?.count ?? 0);
    const snapshot = {
      ...this.asRecord(snapshotRow.metadata),
      snapshot_id: snapshotRow.snapshot_id,
      run_id: snapshotRow.run_id,
      as_of_date: this.toIsoDate(snapshotRow.as_of_date),
      trace_id: snapshotRow.trace_id,
      correlation_id: snapshotRow.correlation_id,
      source_action: snapshotRow.source_action,
      universe_count: snapshotRow.universe_count,
      eligible_count: snapshotRow.eligible_count,
      topn_n: snapshotRow.topn_n,
      selection_rules: this.asRecord(snapshotRow.selection_rules),
      constituents: this.asRecordArray(snapshotRow.constituents),
      portfolio_candidate_id: snapshotRow.portfolio_candidate_id,
      score_row_count: scoreRowCount,
      available: true,
    };

    return {
      available: true,
      snapshot,
      top_scores: [],
      score_row_count: scoreRowCount,
      requested_limit: normalizedLimit,
    };
  }

  private async loadFactoryResearchSurfaceFromDb() {
    const result = await this.db.query<{
      run_id: string;
      status: string;
      started_at: Date | string | null;
      completed_at: Date | string | null;
      summary: Record<string, unknown> | null;
    }>(
      `
        SELECT run_id, status, started_at, completed_at, summary
        FROM strategy_factory_runs
        WHERE COALESCE((summary->'research_window'->>'loaded_stock_count')::int, 0) > 0
           OR COALESCE((summary->'research_window'->>'selected_bulk_task_count')::int, 0) > 0
           OR COALESCE((summary->'research_window'->>'planned_bulk_task_count')::int, 0) > 0
        ORDER BY started_at DESC
        LIMIT 1
      `,
    );
    const row = result.rows[0];
    if (!row) {
      return {
        available: false,
        run: null,
        research_window: null,
      };
    }

    const summary = this.asRecord(row.summary);
    return {
      available: true,
      run: {
        run_id: row.run_id,
        status: row.status,
        started_at: this.toIsoTimestamp(row.started_at),
        completed_at: this.toIsoTimestamp(row.completed_at),
      },
      research_window: this.asRecord(summary.research_window),
    };
  }

  private async loadModelRetrainSurfaceFromDb(limit = 5) {
    const normalizedLimit = Math.max(1, Math.min(Number(limit) || 5, 50));
    const strategyKey = 'quant_model_retrain_plan';
    const [itemsResult, summaryResult] = await Promise.all([
      this.db.query<{
        artifact_id: string;
        strategy: string;
        code: string | null;
        payload: Record<string, unknown> | null;
        registered_at: Date | string | null;
        updated_at: Date | string | null;
      }>(
        `
          SELECT artifact_id, strategy, code, payload, registered_at, updated_at
          FROM strategy_artifacts
          WHERE lower(strategy) = $1
          ORDER BY COALESCE(updated_at, registered_at) DESC
          LIMIT $2
        `,
        [strategyKey, normalizedLimit],
      ),
      this.db.query<{ status: string; scheduler_status: string; count: string }>(
        `
          SELECT
            COALESCE(NULLIF(LOWER(payload->>'status'), ''), 'planned') AS status,
            COALESCE(NULLIF(LOWER(payload->>'scheduler_status'), ''), 'none') AS scheduler_status,
            COUNT(*)::text AS count
          FROM strategy_artifacts
          WHERE lower(strategy) = $1
          GROUP BY 1, 2
        `,
        [strategyKey],
      ),
    ]);

    const items = itemsResult.rows.map((row) => {
      const payload = this.asRecord(row.payload);
      return {
        artifact_id: row.artifact_id,
        plan_id: String(payload.plan_id ?? row.artifact_id).trim() || row.artifact_id,
        status: String(payload.status ?? 'planned')
          .trim()
          .toLowerCase() || 'planned',
        family: String(payload.family ?? '')
          .trim()
          .toLowerCase() || null,
        codes: Array.isArray(payload.codes) ? payload.codes.map((item) => String(item).trim()).filter(Boolean) : [],
        priority: String(payload.priority ?? '')
          .trim()
          .toLowerCase() || null,
        scheduler_status: String(payload.scheduler_status ?? '')
          .trim()
          .toLowerCase() || null,
        execution_mode: String(payload.execution_mode ?? '')
          .trim()
          .toLowerCase() || null,
        schedule_hint: String(payload.schedule_hint ?? '')
          .trim()
          .toLowerCase() || null,
        target_model_count: Number(payload.target_model_count ?? 0) || 0,
        target_models: this.asRecordArray(payload.target_models),
        target_generation_artifact_ids: Array.isArray(payload.target_generation_artifact_ids)
          ? payload.target_generation_artifact_ids.map((item) => String(item).trim()).filter(Boolean)
          : [],
        reason_codes: Array.isArray(payload.reason_codes)
          ? payload.reason_codes.map((item) => String(item).trim()).filter(Boolean)
          : [],
        next_action: String(payload.next_action ?? '')
          .trim()
          .toLowerCase() || null,
        run_count: Number(payload.run_count ?? 0) || 0,
        failure_count: Number(payload.failure_count ?? 0) || 0,
        last_run_status: payload.last_run_status ?? null,
        last_run_artifact_id: payload.last_run_artifact_id ?? null,
        next_run_at: payload.next_run_at ?? null,
        created_at: this.toIsoTimestamp(payload.created_at ?? row.registered_at),
        updated_at: this.toIsoTimestamp(payload.updated_at ?? row.updated_at ?? row.registered_at),
        strategy: row.strategy,
        code: row.code,
      };
    });

    const statusCounts: Record<string, number> = {};
    const schedulerStatusCounts: Record<string, number> = {};
    let totalCount = 0;
    for (const row of summaryResult.rows) {
      const count = Number(row.count ?? 0) || 0;
      const status = String(row.status ?? 'planned').trim().toLowerCase() || 'planned';
      const schedulerStatus = String(row.scheduler_status ?? 'none').trim().toLowerCase() || 'none';
      totalCount += count;
      statusCounts[status] = (statusCounts[status] ?? 0) + count;
      schedulerStatusCounts[schedulerStatus] = (schedulerStatusCounts[schedulerStatus] ?? 0) + count;
    }

    return {
      loaded: true,
      summary: {
        count: totalCount,
        status_counts: statusCounts,
        scheduler_status_counts: schedulerStatusCounts,
      },
      items,
    };
  }

  private async fetchRankingWithCache(
    params: { status?: string; strategy_type?: string; limit?: number; rank_keys?: string[]; offset?: number },
    forceRefresh = false,
  ) {
    const cacheKey = buildRankingCacheKey(params);
    const ttl = this.cache.resolveTtl('strategy.ranking', StrategyMarketService.RANKING_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta(cacheKey);
      if (cached.value && !this.isMcpToolErrorPayload(cached.value)) {
        const data = this.annotateRankingDataQuality(cached.value);
        this.rememberStrategySummaries(data);
        return { data, cacheKey, ttl, cacheHit: true };
      }
      if (this.isMcpToolErrorPayload(cached.value)) {
        await this.cache.del(cacheKey);
      }
    } else {
      await this.cache.del(cacheKey);
    }

    try {
      const data = await this.call(
        'rank',
        { status: params.status || 'visible', ...params },
        { timeoutMs: StrategyMarketService.RANKING_READ_TIMEOUT_MS },
      );
      const annotated = this.annotateRankingDataQuality(data);
      this.rememberStrategySummaries(annotated);
      await this.cache.set(cacheKey, annotated, ttl);
      return { data: annotated, cacheKey, ttl, cacheHit: false };
    } catch (error) {
      if (forceRefresh) {
        throw error;
      }
      const reason = this.describeError(error);
      const fallback = this.annotateRankingDataQuality(await this.loadRankingFallbackFromDb(params), reason);
      this.rememberStrategySummaries(fallback);
      await this.cache.set(cacheKey, fallback, Math.min(ttl, 60));
      this.logger.warn(`策略榜单降级为 DB snapshot: ${reason}`);
      return { data: fallback, cacheKey, ttl, cacheHit: false };
    }
  }

  private annotateRankingDataQuality(data: unknown, fallbackReason?: string | null) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return data;
    const record = data as Record<string, unknown>;
    if (record.data_quality && !fallbackReason) return record;
    const source = String(record.source ?? '').trim();
    const isDbSnapshot = source === 'db_snapshot';
    if (!fallbackReason && !isDbSnapshot) return record;
    const strategies = Array.isArray(record.strategies) ? record.strategies : [];
    const reason = String(
      fallbackReason
        ?? record.fallback_reason
        ?? record.degraded_reason
        ?? 'strategy_ranking_from_db_snapshot',
    ).trim();
    return {
      ...record,
      fallback_used: true,
      fallback_reason: reason,
      data_quality: buildDataQuality({
        status: 'partial',
        reasons: ['strategy_ranking_db_snapshot', reason],
        qualityFlags: ['strategy_ranking_db_snapshot'],
        sources: [
          { name: 'strategy_manager.rank', status: 'failed', error: reason },
          { name: 'strategy_db_snapshot', status: 'trusted', sampleCount: strategies.length },
        ],
      }),
    };
  }

  private async fetchFactoryRunsWithCache(
    limit?: number,
    forceRefresh = false,
    options: StrategyManagerCallOptions = {},
  ) {
    const cacheKey = buildFactoryRunsCacheKey(limit);
    const ttl = this.cache.resolveTtl('strategy.factory_runs', StrategyMarketService.FACTORY_RUNS_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta<Record<string, unknown>>(cacheKey);
      if (cached.value) return cached.value;
    } else {
      await this.cache.del(cacheKey);
    }

    const data = this.normalizeFactoryRunsResponse(await this.call('factory_runs', { limit }, options));
    await this.cache.set(cacheKey, data, ttl);
    return data;
  }

  private withTimeout<T>(promise: Promise<T>, timeoutMs: number | undefined, label: string): Promise<T> {
    if (!timeoutMs) return promise;
    return new Promise<T>((resolve, reject) => {
      const timer = detachTimer(
        setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs),
      );
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

  private async settleWithTimeout<T>(
    label: string,
    promise: Promise<T>,
    timeoutMs: number,
  ): Promise<PromiseSettledResult<T>> {
    try {
      return {
        status: 'fulfilled',
        value: await this.withTimeout(promise, timeoutMs, label),
      };
    } catch (reason) {
      return {
        status: 'rejected',
        reason,
      };
    }
  }

  private async fetchFactoryStatusWithCache(forceRefresh = false, options: StrategyManagerCallOptions = {}) {
    const cacheKey = buildFactoryStatusCacheKey();
    const ttl = this.cache.resolveTtl('strategy.factory_status', StrategyMarketService.FACTORY_STATUS_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta<Record<string, unknown>>(cacheKey);
      if (cached.value) return cached.value;
      if (this.inFlightFactoryStatus) {
        return this.withTimeout(this.inFlightFactoryStatus, options.timeoutMs, 'factory_status');
      }
    } else {
      await this.cache.del(cacheKey);
    }

    const request = (async () => {
      const data = this.normalizeFactoryStatusResponse(await this.call('factory_status', {}, options));
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

  private async fetchFactoryRunDetailWithCache(
    runId: string,
    forceRefresh = false,
    options: StrategyManagerCallOptions = {},
  ) {
    const cacheKey = buildFactoryRunDetailCacheKey(runId);
    const ttl = this.cache.resolveTtl('strategy.factory_run_detail', StrategyMarketService.FACTORY_RUN_DETAIL_TTL);

    if (!forceRefresh) {
      const cached = await this.cache.getWithMeta<Record<string, unknown>>(cacheKey);
      if (cached.value) return cached.value;
    } else {
      await this.cache.del(cacheKey);
    }

    const data = this.normalizeFactoryRun(await this.call('factory_run_detail', { run_id: runId }, options));
    await this.cache.set(cacheKey, data, ttl);
    return data;
  }

  private async callQuantManager(
    action: string,
    params: Record<string, unknown> = {},
    options: StrategyManagerCallOptions = {},
  ) {
    return this.mcp.callTool(
      'quant_manager',
      {
        action,
        params,
      },
      {
        timeoutMs: options.timeoutMs,
      },
    );
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

  private acceptanceRows(payload: unknown): Record<string, unknown>[] {
    if (Array.isArray(payload)) return this.asRecordArray(payload);
    const record = this.asRecord(payload);
    return [
      ...this.asRecordArray(record.strategies),
      ...this.asRecordArray(record.items),
      ...this.asRecordArray(record.favorites),
      ...this.asRecordArray(record.subscriptions),
    ];
  }

  private strategyIdFromRecord(record: unknown): string {
    const row = this.asRecord(record);
    return String(row.id ?? row.strategy_id ?? this.asRecord(row.strategy).id ?? '').trim();
  }

  private nestedMetadata(record: unknown): Record<string, unknown> {
    const row = this.asRecord(record);
    const params = this.asRecord(row.params);
    return {
      ...this.asRecord(row.metadata),
      ...this.asRecord(params.metadata),
    };
  }

  private sourceStrategyIdFromRecord(record: unknown): string | null {
    const row = this.asRecord(record);
    const strategy = this.asRecord(row.strategy);
    const metadata = this.nestedMetadata(row);
    const strategyMetadata = this.nestedMetadata(strategy);
    const sourceId = String(
      row.source_strategy_id ??
        row.parent_strategy_id ??
        metadata.source_strategy_id ??
        metadata.parent_strategy_id ??
        strategy.source_strategy_id ??
        strategy.parent_strategy_id ??
        strategyMetadata.source_strategy_id ??
        strategyMetadata.parent_strategy_id ??
        '',
    ).trim();
    return sourceId || null;
  }

  private isAcceptancePersonalStrategyRecord(record: unknown): boolean {
    const row = this.asRecord(record);
    const ownerState = this.asRecord(row.owner_state);
    const context = this.asRecord(row.personal_strategy_context);
    const tags = Array.isArray(row.tags) ? row.tags.map((item) => String(item).trim().toLowerCase()) : [];
    return Boolean(
      row.personal_strategy ||
        ownerState.personal_strategy ||
        context.personal_strategy ||
        tags.includes('personal_strategy') ||
        this.sourceStrategyIdFromRecord(row),
    );
  }

  private latestTimestampFromRecords(...records: unknown[]): string | null {
    const keys = [
      'completed_at',
      'updated_at',
      'last_used_at',
      'created_at',
      'subscribed_at',
      'forked_at',
      'started_at',
      'registered_at',
      'nav_date',
      'metric_date',
    ];
    const values: string[] = [];
    const collect = (value: unknown) => {
      const text = String(value ?? '').trim();
      if (!text) return;
      const ts = Date.parse(text);
      if (!Number.isNaN(ts)) values.push(text);
    };
    for (const record of records) {
      const row = this.asRecord(record);
      for (const key of keys) collect(row[key]);
      const metadata = this.nestedMetadata(row);
      for (const key of keys) collect(metadata[key]);
      const session = this.asRecord(row.session);
      for (const key of keys) collect(session[key]);
      const account = this.asRecord(row.account);
      for (const key of keys) collect(account[key]);
      const draft = this.asRecord(row.draft_snapshot);
      for (const key of keys) collect(draft[key]);
      const draftMetadata = this.nestedMetadata(draft);
      for (const key of keys) collect(draftMetadata[key]);
    }
    if (!values.length) return null;
    return values.sort((left, right) => Date.parse(right) - Date.parse(left))[0] ?? null;
  }

  private actionModeAvailable(context: unknown, actionKind: string): boolean {
    return this.asRecordArray(this.asRecord(context).action_modes).some(
      (item) => String(item.action_kind ?? '').trim() === actionKind && item.available !== false,
    );
  }

  private async settleAcceptance<T>(section: string, promise: Promise<T>): Promise<AcceptanceRead<T>> {
    try {
      return { value: await promise, error: null };
    } catch (error) {
      const message = this.describeError(error);
      this.logger.warn(`核心链路验收读取 ${section} 失败: ${message}`);
      return { value: null, error: message };
    }
  }

  private buildCoreChainStep(input: Omit<StrategyCoreChainStep, 'status'> & {
    degraded?: boolean;
  }): StrategyCoreChainStep {
    const { degraded, ...step } = input;
    const status: StrategyCoreChainStepStatus = step.completed
      ? 'passed'
      : degraded
        ? 'degraded'
        : step.can_complete
          ? 'ready'
          : 'blocked';
    return {
      ...step,
      status,
    };
  }

  private toNum(value: unknown): number | null {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  private latestPaperNavFromPayload(payload: unknown) {
    const navRows = this.asRecordArray(this.asRecord(payload).nav);
    return navRows.length ? navRows[navRows.length - 1] : null;
  }

  private describeError(error: unknown) {
    return String(error instanceof Error ? error.message : error).trim() || 'unknown_error';
  }

  private degradedReadSurface(section: string, error: unknown, extra: Record<string, unknown> = {}) {
    const reason = this.describeError(error);
    this.logger.warn(`策略工厂只读分区 ${section} 降级: ${reason}`);
    return {
      ...extra,
      degraded: true,
      section_errors: { [section]: reason },
      fallback_reason: reason,
      errors: [reason],
    };
  }

  private async withLocalTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        promise,
        new Promise<T>((_, reject) => {
          timer = setTimeout(() => reject(new Error(message)), timeoutMs);
        }),
      ]);
    } finally {
      if (timer) clearTimeout(timer);
      promise.catch(() => undefined);
    }
  }

  private extractStrategyRows(payload: unknown) {
    const record = this.asRecord(payload);
    return [
      ...this.asRecordArray(record.strategies),
      ...this.asRecordArray(record.items),
      ...this.asRecordArray(record.favorites),
      ...this.asRecordArray(record.subscriptions),
    ];
  }

  private rememberStrategySummary(summary: unknown) {
    const record = this.asRecord(summary);
    const id = String(record.id ?? record.strategy_id ?? '').trim();
    if (!id) return;
    this.strategySummaryFallbackCache.set(id, {
      value: { ...record, id },
      expiresAt: Date.now() + StrategyMarketService.STRATEGY_SUMMARY_FALLBACK_TTL_MS,
    });
  }

  private rememberStrategySummaries(payload: unknown) {
    for (const row of this.extractStrategyRows(payload)) {
      this.rememberStrategySummary(row);
    }
  }

  private getRememberedStrategySummary(id: string) {
    const entry = this.strategySummaryFallbackCache.get(id);
    if (!entry) return null;
    if (entry.expiresAt <= Date.now()) {
      this.strategySummaryFallbackCache.delete(id);
      return null;
    }
    return entry.value;
  }

  private async findStrategySummaryFallback(id: string) {
    const targetId = String(id ?? '').trim();
    if (!targetId) return null;
    const remembered = this.getRememberedStrategySummary(targetId);
    if (remembered) return remembered;
    return this.loadStrategySummaryFromDb(targetId);
  }

  private buildMinimalStrategySummary(id: string, error?: unknown) {
    const strategyId = String(id ?? '').trim() || 'unknown_strategy';
    return {
      id: strategyId,
      name: `策略 ${strategyId}`,
      description: `策略详情服务暂时降级：${this.describeError(error)}`,
      author_id: null,
      strategy_type: null,
      params: {},
      factor_weights: {},
      status: 'degraded',
      tags: [],
      subscriber_count: 0,
      favorite_count: 0,
      avg_rating: 0,
      review_count: 0,
      metrics: {},
      source: 'degraded_minimal_snapshot',
    };
  }

  private normalizeStrategySummaryRow(row: {
    id: string;
    name: string | null;
    description: string | null;
    author_id: string | null;
    strategy_type: string | null;
    params: Record<string, unknown> | null;
    factor_weights: Record<string, unknown> | null;
    status: string | null;
    tags: string[] | null;
    subscriber_count: number | null;
    avg_rating: number | string | null;
    review_count: number | string | null;
    metrics: Record<string, unknown> | null;
    backtest_artifact_id?: string | null;
  }) {
    return {
      id: row.id,
      name: String(row.name ?? row.id),
      description: String(row.description ?? ''),
      author_id: row.author_id ?? null,
      strategy_type: row.strategy_type ?? null,
      params: this.asRecord(row.params),
      factor_weights: this.asRecord(row.factor_weights),
      status: row.status ?? null,
      tags: Array.isArray(row.tags) ? row.tags.map((item) => String(item).trim()).filter(Boolean) : [],
      subscriber_count: Number(row.subscriber_count ?? 0),
      favorite_count: Number(row.subscriber_count ?? 0),
      avg_rating: Number(row.avg_rating ?? 0),
      review_count: Number(row.review_count ?? 0),
      metrics: this.asRecord(row.metrics),
      backtest_artifact_id: row.backtest_artifact_id ?? null,
      source: 'db_snapshot',
    };
  }

  private buildStrategyFilter(params: { status?: string; strategy_type?: string }) {
    const values: unknown[] = [];
    const where: string[] = [];
    const status = String(params.status || 'visible').trim().toLowerCase();
    if (status && status !== 'all') {
      if (status === 'visible') {
        values.push(['listed', 'incubating']);
        where.push(`s.status = ANY($${values.length}::text[])`);
      } else {
        values.push(status);
        where.push(`s.status = $${values.length}`);
      }
    }

    const strategyType = String(params.strategy_type ?? '').trim();
    if (strategyType && strategyType !== 'all') {
      values.push(strategyType);
      where.push(`s.strategy_type = $${values.length}`);
    }

    return {
      values,
      whereSql: where.length ? `WHERE ${where.join(' AND ')}` : '',
    };
  }

  private async loadRankingFallbackFromDb(params: {
    status?: string;
    strategy_type?: string;
    limit?: number;
    offset?: number;
  }) {
    const limit = Math.max(1, Math.min(Number(params.limit) || 50, 200));
    const offset = Math.max(0, Number(params.offset) || 0);
    const filter = this.buildStrategyFilter(params);
    const values = [...filter.values, limit, offset];
    const limitIndex = values.length - 1;
    const offsetIndex = values.length;
    const result = await this.db.query<{
      id: string;
      name: string | null;
      description: string | null;
      author_id: string | null;
      strategy_type: string | null;
      params: Record<string, unknown> | null;
      factor_weights: Record<string, unknown> | null;
      status: string | null;
      tags: string[] | null;
      subscriber_count: number | null;
      avg_rating: number | string | null;
      review_count: number | string | null;
      metrics: Record<string, unknown> | null;
      total_count: number | string | null;
      backtest_artifact_id: string | null;
    }>(
      `
        WITH filtered AS (
          SELECT s.*
          FROM strategies s
          ${filter.whereSql}
        )
        SELECT
          s.id,
          s.name,
          s.description,
          s.author_id,
          s.strategy_type,
          s.params,
          s.factor_weights,
          s.status,
          s.tags,
          s.backtest_artifact_id,
          s.subscriber_count,
          COALESCE(r.avg_rating, 0) AS avg_rating,
          COALESCE(r.review_count, 0) AS review_count,
          jsonb_build_object(
            'total_return', m.total_return,
            'annual_return', m.annual_return,
            'sharpe_ratio', m.sharpe_ratio,
            'max_drawdown', m.max_drawdown,
            'win_rate', m.win_rate
          ) AS metrics,
          (SELECT COUNT(*) FROM filtered) AS total_count
        FROM filtered s
        LEFT JOIN LATERAL (
          SELECT total_return, annual_return, sharpe_ratio, max_drawdown, win_rate
          FROM strategy_metrics
          WHERE strategy_id = s.id
          ORDER BY computed_at DESC NULLS LAST, id DESC
          LIMIT 1
        ) m ON TRUE
        LEFT JOIN LATERAL (
          SELECT AVG(rating)::float AS avg_rating, COUNT(*)::int AS review_count
          FROM strategy_reviews
          WHERE strategy_id = s.id
        ) r ON TRUE
        ORDER BY
          COALESCE(m.total_return, -1000000000) DESC,
          COALESCE(m.sharpe_ratio, -1000000000) DESC,
          COALESCE(s.subscriber_count, 0) DESC,
          s.updated_at DESC NULLS LAST
        LIMIT $${limitIndex}
        OFFSET $${offsetIndex}
      `,
      values,
    );
    const strategies = result.rows.map((row) => this.normalizeStrategySummaryRow(row));
    this.rememberStrategySummaries({ strategies });
    return {
      strategies,
      count: Number(result.rows[0]?.total_count ?? strategies.length),
      limit,
      offset,
      source: 'db_snapshot',
    };
  }

  private async loadMyStrategiesFallbackFromDb(
    actorId: string,
    role: string,
    params: { include_archived?: boolean; limit?: number; offset?: number } = {},
  ) {
    const userId = String(actorId ?? '').trim();
    if (!userId) {
      return { strategies: [], items: [], count: 0, source: 'db_snapshot' };
    }
    const limit = Math.max(1, Math.min(Number(params.limit) || 50, 200));
    const offset = Math.max(0, Number(params.offset) || 0);
    const archivedFilter = params.include_archived === true ? '' : "AND COALESCE(s.status, '') <> 'archived'";
    const result = await this.db.query<{
      id: string;
      name: string | null;
      description: string | null;
      author_id: string | null;
      strategy_type: string | null;
      params: Record<string, unknown> | null;
      factor_weights: Record<string, unknown> | null;
      status: string | null;
      tags: string[] | null;
      backtest_artifact_id: string | null;
      subscriber_count: number | null;
      avg_rating: number | string | null;
      review_count: number | string | null;
      metrics: Record<string, unknown> | null;
      total_count: number | string | null;
    }>(
      `
        WITH filtered AS (
          SELECT s.*
          FROM strategies s
          WHERE s.author_id = $1
            ${archivedFilter}
            AND (
              COALESCE(s.status, '') = 'draft'
              OR COALESCE(s.tags, '{}'::text[]) && ARRAY['personal_strategy', 'draft_personal_strategy', 'forked_strategy']::text[]
              OR NULLIF(s.params #>> '{metadata,source_strategy_id}', '') IS NOT NULL
            )
        )
        SELECT
          s.id,
          s.name,
          s.description,
          s.author_id,
          s.strategy_type,
          s.params,
          s.factor_weights,
          s.status,
          s.tags,
          s.backtest_artifact_id,
          s.subscriber_count,
          COALESCE(r.avg_rating, 0) AS avg_rating,
          COALESCE(r.review_count, 0) AS review_count,
          jsonb_build_object(
            'total_return', m.total_return,
            'annual_return', m.annual_return,
            'sharpe_ratio', m.sharpe_ratio,
            'max_drawdown', m.max_drawdown,
            'win_rate', m.win_rate
          ) AS metrics,
          (SELECT COUNT(*) FROM filtered) AS total_count
        FROM filtered s
        LEFT JOIN LATERAL (
          SELECT total_return, annual_return, sharpe_ratio, max_drawdown, win_rate
          FROM strategy_metrics
          WHERE strategy_id = s.id
          ORDER BY computed_at DESC NULLS LAST, id DESC
          LIMIT 1
        ) m ON TRUE
        LEFT JOIN LATERAL (
          SELECT AVG(rating)::float AS avg_rating, COUNT(*)::int AS review_count
          FROM strategy_reviews
          WHERE strategy_id = s.id
        ) r ON TRUE
        ORDER BY s.updated_at DESC NULLS LAST, s.created_at DESC NULLS LAST
        LIMIT $2
        OFFSET $3
      `,
      [userId, limit, offset],
    );
    const strategies = result.rows.map((row) => {
      const summary = this.normalizeStrategySummaryRow(row);
      const surface = this.buildLocalStrategySurfaceState(summary, { userId, role });
      return {
        ...summary,
        owner_state: surface.ownerState,
        favorite_state: surface.favoriteState,
        paper_session_state: surface.paperSessionState,
      };
    });
    this.rememberStrategySummaries({ strategies });
    return {
      strategies,
      items: strategies,
      count: Number(result.rows[0]?.total_count ?? strategies.length),
      limit,
      offset,
      source: 'db_snapshot',
    };
  }

  private async loadStrategySummaryFromDb(id: string) {
    const result = await this.db.query<{
      id: string;
      name: string | null;
      description: string | null;
      author_id: string | null;
      strategy_type: string | null;
      params: Record<string, unknown> | null;
      factor_weights: Record<string, unknown> | null;
      status: string | null;
      tags: string[] | null;
      subscriber_count: number | null;
      avg_rating: number | string | null;
      review_count: number | string | null;
      metrics: Record<string, unknown> | null;
      backtest_artifact_id: string | null;
    }>(
      `
        SELECT
          s.id,
          s.name,
          s.description,
          s.author_id,
          s.strategy_type,
          s.params,
          s.factor_weights,
          s.status,
          s.tags,
          s.backtest_artifact_id,
          s.subscriber_count,
          COALESCE(r.avg_rating, 0) AS avg_rating,
          COALESCE(r.review_count, 0) AS review_count,
          jsonb_build_object(
            'total_return', m.total_return,
            'annual_return', m.annual_return,
            'sharpe_ratio', m.sharpe_ratio,
            'max_drawdown', m.max_drawdown,
            'win_rate', m.win_rate
          ) AS metrics
        FROM strategies s
        LEFT JOIN LATERAL (
          SELECT total_return, annual_return, sharpe_ratio, max_drawdown, win_rate
          FROM strategy_metrics
          WHERE strategy_id = s.id
          ORDER BY computed_at DESC NULLS LAST, id DESC
          LIMIT 1
        ) m ON TRUE
        LEFT JOIN LATERAL (
          SELECT AVG(rating)::float AS avg_rating, COUNT(*)::int AS review_count
          FROM strategy_reviews
          WHERE strategy_id = s.id
        ) r ON TRUE
        WHERE s.id = $1
        LIMIT 1
      `,
      [id],
    );
    const row = result.rows[0];
    if (!row) return null;
    const summary = this.normalizeStrategySummaryRow(row);
    this.rememberStrategySummary(summary);
    return summary;
  }

  private async forkStrategyFallbackToDb(id: string, actor: { actorId: string; role: string }) {
    const sourceStrategy = await this.loadStrategySummaryFromDb(id);
    if (!sourceStrategy) {
      throw new NotFoundException(`策略 ${id} 不存在`);
    }
    const actorId = String(actor.actorId ?? '').trim();
    if (!actorId) {
      throw new BadRequestException('登录状态无效');
    }
    const forkId = `strat_${Math.floor(Date.now() / 1000)}_${randomUUID().replaceAll('-', '').slice(0, 8)}`;
    const parentTags = Array.isArray(sourceStrategy.tags)
      ? sourceStrategy.tags.map((item) => String(item).trim()).filter(Boolean)
      : [];
    const tags = Array.from(new Set([...parentTags, 'personal_strategy', 'forked_strategy']));
    const parentParams = this.asRecord(sourceStrategy.params);
    const params = {
      ...parentParams,
      metadata: {
        ...this.asRecord(parentParams.metadata),
        source_strategy_id: String(sourceStrategy.id),
        forked_at: new Date().toISOString(),
        forked_by: actorId,
        fallback_source: 'bff.db_fork',
      },
    };
    const factorWeights = this.asRecord(sourceStrategy.factor_weights);
    const forkName = `${String(sourceStrategy.name ?? id).trim() || id} · 我的版本`;

    await this.db.query(
      `
        INSERT INTO strategies (
          id, name, description, author_id, strategy_type, params, factor_weights,
          status, tags, backtest_artifact_id, subscriber_count, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, 'draft', $8::text[], $9, 0, NOW(), NOW())
      `,
      [
        forkId,
        forkName,
        String(sourceStrategy.description ?? ''),
        actorId,
        String(sourceStrategy.strategy_type ?? '').trim() || 'custom',
        JSON.stringify(params),
        JSON.stringify(factorWeights),
        tags,
        sourceStrategy.backtest_artifact_id ?? null,
      ],
    );
    await this.db.query(
      `
        INSERT INTO strategy_lineage (strategy_id, parent_id, spawn_reason, birth_regime, created_at)
        VALUES ($1, $2, 'user_fork', $3::jsonb, NOW())
      `,
      [
        forkId,
        String(sourceStrategy.id),
        JSON.stringify({ source: 'strategy_market_bff_fallback', actor_id: actorId, actor_role: actor.role }),
      ],
    ).catch((error) => {
      this.logger.warn(`策略 ${forkId} lineage 写入失败: ${this.describeError(error)}`);
    });

    const strategy = await this.loadStrategySummaryFromDb(forkId) ?? {
      ...sourceStrategy,
      id: forkId,
      name: forkName,
      author_id: actorId,
      params,
      factor_weights: factorWeights,
      status: 'draft',
      tags,
    };
    const surface = this.buildLocalStrategySurfaceState(strategy, { userId: actorId, role: actor.role });
    const strategyWithSurface = this.withRuntimeActionContract({
      ...strategy,
      owner_state: surface.ownerState,
      favorite_state: surface.favoriteState,
      paper_session_state: surface.paperSessionState,
      local_fallback_used: true,
    }, { userId: actorId, role: actor.role });
    return {
      strategy_id: forkId,
      source_strategy_id: String(sourceStrategy.id),
      strategy: strategyWithSurface,
      owner_state: surface.ownerState,
      favorite_state: surface.favoriteState,
      paper_session_state: surface.paperSessionState,
      local_fallback_used: true,
    };
  }

  private async deletePersonalStrategyFallbackToDb(id: string, actor: { actorId: string; role: string }) {
    const strategy = await this.loadStrategySummaryFromDb(id);
    if (!strategy) {
      throw new NotFoundException(`策略 ${id} 不存在`);
    }
    const actorId = String(actor.actorId ?? '').trim();
    const authorId = String(strategy.author_id ?? '').trim();
    if (!actorId) {
      throw new BadRequestException('登录状态无效');
    }
    if (!this.isPersonalStrategyRecord(strategy)) {
      throw new BadRequestException('市场策略不能通过个人策略清理入口删除');
    }
    if (!authorId || authorId !== actorId) {
      throw new BadRequestException('只有个人策略 owner 可以删除个人策略副本');
    }
    await this.db.query(
      `
        UPDATE strategies
        SET status = 'archived', updated_at = NOW()
        WHERE id = $1 AND author_id = $2
      `,
      [id, actorId],
    );
    return {
      strategy_id: id,
      archived: true,
      status: 'archived',
      local_fallback_used: true,
    };
  }

  private async archiveLocalPersonalStrategyMirror(id: string, actor: { actorId: string; role: string }) {
    try {
      const result = await this.deletePersonalStrategyFallbackToDb(id, actor);
      this.strategySummaryFallbackCache.delete(id);
      return result.archived === true;
    } catch (error) {
      this.logger.debug(`个人策略 ${id} 本地镜像归档跳过: ${this.describeError(error)}`);
      return false;
    }
  }

  private buildFallbackStrategyDetail(
    id: string,
    summary: Record<string, unknown>,
    actor?: { userId?: string | null; role?: string | null },
    error?: unknown,
  ) {
    const strategyId = String(summary.id ?? id).trim() || id;
    const strategyName = String(summary.name ?? '').trim() || `策略 ${strategyId}`;
    const strategyDescription = String(summary.description ?? '').trim();
    const authorId = String(summary.author_id ?? '').trim() || null;
    const subscriberCount = Number(summary.subscriber_count ?? 0);
    const favoriteCount = Number(summary.favorite_count ?? summary.subscriber_count ?? 0);
    const avgRating = Number(summary.avg_rating ?? 0);
    const reviewCount = Number(summary.review_count ?? 0);
    const safeError = this.describeError(error);
    const strategyPayload = {
      id: strategyId,
      name: strategyName,
      description: strategyDescription || '策略详情服务暂时降级，当前先展示基础摘要与可恢复入口。',
      strategy_type: String(summary.strategy_type ?? '').trim() || undefined,
      status: String(summary.status ?? '').trim() || 'degraded',
      author_id: authorId ?? undefined,
      subscriber_count: Number.isFinite(subscriberCount) ? subscriberCount : 0,
      favorite_count: Number.isFinite(favoriteCount) ? favoriteCount : Number.isFinite(subscriberCount) ? subscriberCount : 0,
      avg_rating: Number.isFinite(avgRating) ? avgRating : 0,
      review_count: Number.isFinite(reviewCount) ? reviewCount : 0,
      params: this.asRecord(summary.params),
      factor_weights: this.asRecord(summary.factor_weights),
      tags: Array.isArray(summary.tags) ? summary.tags.map((item) => String(item).trim()).filter(Boolean) : [],
      metrics: [],
      reviews: [],
    };
    const surface = this.buildLocalStrategySurfaceState(strategyPayload, actor);
    const { ownerState, favoriteState, paperSessionState } = surface;
    const contract = this.buildRuntimeActionContract({
      strategy: strategyPayload,
      actor,
      ownerState,
      favoriteState,
      paperSessionState,
    });

    return this.normalizeStrategyDetail({
      dto_version: 'strategy_market.detail.v2',
      strategy: {
        ...strategyPayload,
        runtime_action_contract: contract,
        runtime_actions: contract.actions,
      },
      metrics: [],
      reviews: [],
      nav_series: [],
      runtime_alerts: [],
      open_risk_events: [],
      vector_profiles: [],
      similar_vector_profiles: [],
      domain_events: [],
      task_runs: [],
      owner_state: ownerState,
      favorite_state: favoriteState,
      paper_session_state: paperSessionState,
      presentation: {
        stage_label: '只读降级',
        stage_summary: '策略详情服务暂时降级，当前先展示基础摘要与返回入口。',
        why_watch: strategyDescription || '可先返回策略超市继续比较，稍后再重试详情页。',
        current_risks: [`详情上游暂不可用：${safeError}`],
        recommended_action: '先返回策略超市继续筛选，或稍后重试当前策略详情。',
      },
      runtime_action_contract: contract,
      runtime_actions: contract.actions,
      degraded_detail: true,
      degraded_reason: safeError,
    });
  }

  private settledMessage(result: PromiseSettledResult<unknown>, label: string) {
    if (result.status === 'fulfilled') return null;
    return `${label}: ${result.reason instanceof Error ? result.reason.message : String(result.reason)}`;
  }

  private normalizePaperTrackAccount(
    rawAccount: unknown,
    accountId: string,
    defaults: {
      name?: string | null;
      status?: string | null;
    } = {},
  ) {
    const account = this.asRecord(rawAccount);
    const resolvedAccountId = String(account.id ?? account.account_id ?? accountId).trim();
    if (!resolvedAccountId && Object.keys(account).length === 0 && !defaults.name && !defaults.status) {
      return null;
    }
    const resolvedName = String(account.name ?? defaults.name ?? '').trim();
    const resolvedStatus = String(account.status ?? defaults.status ?? '').trim();
    return {
      ...(account as object),
      ...(resolvedAccountId ? { id: resolvedAccountId, account_id: resolvedAccountId } : {}),
      ...(resolvedName ? { name: resolvedName } : {}),
      ...(resolvedStatus ? { status: resolvedStatus } : {}),
    };
  }

  private async loadPaperTrackSnapshot(input: {
    kind: 'personal' | 'incubation';
    source: 'strategy_paper_session' | 'strategy_binding';
    label: string;
    userId: string;
    accountId: string;
    sessionState?: Record<string, unknown> | null;
    account?: Record<string, unknown> | null;
    latestNav?: Record<string, unknown> | null;
    orderSummary?: Record<string, unknown> | null;
    latestMetric?: Record<string, unknown> | null;
    stage?: string | null;
    accountStatus?: string | null;
  }): Promise<StrategyPaperTrackSnapshot> {
    const [summaryResult, performanceResult, trustStatusResult, navHistoryResult] = await Promise.allSettled([
      this.paperTrading.summary(input.userId, input.accountId),
      this.paperTrading.performance(input.userId, input.accountId, 30),
      this.paperTrading.trustStatus(input.userId, input.accountId),
      this.paperTrading.navHistory(input.userId, input.accountId, 1),
    ]);

    const summary = summaryResult.status === 'fulfilled' ? this.asRecord(summaryResult.value) : null;
    const performance = performanceResult.status === 'fulfilled' ? this.asRecord(performanceResult.value) : null;
    const trustStatus = trustStatusResult.status === 'fulfilled' ? this.asRecord(trustStatusResult.value) : null;
    const latestNav =
      (navHistoryResult.status === 'fulfilled' ? this.latestPaperNavFromPayload(navHistoryResult.value) : null)
      ?? input.latestNav
      ?? null;
    const warnings = [
      this.settledMessage(summaryResult, 'summary'),
      this.settledMessage(performanceResult, 'performance'),
      this.settledMessage(trustStatusResult, 'trust_status'),
      this.settledMessage(navHistoryResult, 'nav_history'),
    ].filter((item): item is string => Boolean(item));
    const account = this.normalizePaperTrackAccount(summary?.account ?? input.account, input.accountId, {
      name: String(input.sessionState?.account_name ?? input.account?.name ?? '').trim() || null,
      status: String(input.sessionState?.account_status ?? input.accountStatus ?? input.account?.status ?? '').trim() || null,
    });
    const resolvedStage = String(input.stage ?? input.account?.incubation_stage ?? '').trim() || null;
    const resolvedAccountStatus =
      String(account?.status ?? input.accountStatus ?? input.sessionState?.account_status ?? '').trim() || null;

    return {
      kind: input.kind,
      source: input.source,
      label: input.label,
      available: true,
      reason: warnings.length ? warnings.join('；') : null,
      account_id: input.accountId,
      account: (account ?? null) as StrategyPaperTrackSnapshot['account'],
      summary: (summary as StrategyPaperTrackSnapshot['summary']) ?? null,
      performance: (performance as StrategyPaperTrackSnapshot['performance']) ?? null,
      trust_status: (trustStatus as StrategyPaperTrackSnapshot['trust_status']) ?? null,
      latest_nav: (latestNav as StrategyPaperTrackSnapshot['latest_nav']) ?? null,
      order_summary: (input.orderSummary as StrategyPaperTrackSnapshot['order_summary']) ?? null,
      latest_metric: (input.latestMetric as StrategyPaperTrackSnapshot['latest_metric']) ?? null,
      session: (input.sessionState as StrategyPaperTrackSnapshot['session']) ?? null,
      stage: resolvedStage,
      account_status: resolvedAccountStatus,
    };
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
    const rawStatus = String(data.status ?? 'queued')
      .trim()
      .toLowerCase();
    const status: BackgroundFactoryRunStatus =
      rawStatus === 'success' || rawStatus === 'failed' || rawStatus === 'running' ? rawStatus : 'queued';
    return {
      request_id: dispatchId,
      status,
      started_at: String(data.started_at ?? data.requested_at ?? new Date().toISOString()),
      completed_at: data.completed_at == null ? null : String(data.completed_at),
      message:
        String(data.message ?? '').trim() || (status === 'failed' ? '策略工厂后台运行失败。' : '策略工厂后台调度中。'),
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
      running: backgroundRun.status === 'queued' || backgroundRun.status === 'running' ? true : Boolean(data.running),
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
            backgroundRun.status === 'queued' || backgroundRun.status === 'running' ? 'running' : backgroundRun.status,
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

  async list(
    params: { status?: string; strategy_type?: string; limit?: number; offset?: number },
    actor?: { userId?: string | null; role?: string | null },
  ) {
    return this.withRuntimeActionContracts(await this.call('list', params), actor);
  }

  async detail(id: string, actor?: { userId?: string | null; role?: string | null }) {
    try {
      const result = await this.call('detail', {
        strategy_id: id,
        ...this.managerActorParams({ actorId: actor?.userId, role: actor?.role }),
      }, { timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS });
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
      const surface = this.buildLocalStrategySurfaceState(strategy, actor);
      const contract = this.buildRuntimeActionContract({
        strategy,
        actor,
        ownerState: surface.ownerState,
        favoriteState: surface.favoriteState,
        paperSessionState: surface.paperSessionState,
      });
      const detailWithActions = {
        ...detail,
        strategy: {
          ...strategy,
          owner_state: surface.ownerState,
          favorite_state: surface.favoriteState,
          paper_session_state: surface.paperSessionState,
          runtime_action_contract: contract,
          runtime_actions: contract.actions,
        },
        owner_state: surface.ownerState,
        favorite_state: surface.favoriteState,
        paper_session_state: surface.paperSessionState,
        runtime_action_contract: contract,
        runtime_actions: contract.actions,
      };
      this.rememberStrategySummary(detailWithActions.strategy);
      return this.normalizeStrategyDetail(detailWithActions);
    } catch (error) {
      if (!(error instanceof BadGatewayException)) {
        throw error;
      }
      let fallback: Record<string, unknown> | null = null;
      try {
        fallback = await this.withLocalTimeout(
          this.findStrategySummaryFallback(id),
          StrategyMarketService.DETAIL_FALLBACK_TIMEOUT_MS,
          `strategy detail fallback timed out after ${StrategyMarketService.DETAIL_FALLBACK_TIMEOUT_MS}ms`,
        );
      } catch (fallbackError) {
        this.logger.warn(`策略 ${id} DB 摘要降级查询失败: ${this.describeError(fallbackError)}`);
      }
      this.logger.warn(`策略 ${id} 详情降级为列表摘要: ${this.describeError(error)}`);
      return this.buildFallbackStrategyDetail(id, fallback ?? this.buildMinimalStrategySummary(id, error), actor, error);
    }
  }

  async paperContext(id: string, actor: { actorId: string; role: string }): Promise<StrategyPaperContextResponse> {
    const [detailResult, paperSessionResult, paperAccountResult, incubationMetricsResult] = await Promise.allSettled([
      this.detail(id, { userId: actor.actorId, role: actor.role }),
      this.paperSession(id, actor),
      this.paperAccount(id, { limit: 20 }),
      this.incubationMetrics(id, { limit: 1 }),
    ]);

    const detailPayload = detailResult.status === 'fulfilled' ? detailResult.value : null;
    const paperSessionPayload = paperSessionResult.status === 'fulfilled' ? paperSessionResult.value : null;
    const paperAccountPayload = paperAccountResult.status === 'fulfilled' ? paperAccountResult.value : null;
    const incubationMetricsPayload = incubationMetricsResult.status === 'fulfilled' ? incubationMetricsResult.value : null;

    const detail = this.asRecord(detailPayload);
    const strategy = this.asRecord(detail.strategy);
    const strategyName = String(strategy.name ?? '').trim() || id;
    const paperSession = this.asRecord(paperSessionPayload);
    const sessionState = this.asRecord(paperSession.paper_session_state);
    const personalAccountId = String(
      sessionState.account_id ?? this.asRecord(paperSession.session).account_id ?? '',
    ).trim();
    const paperAccount = this.asRecord(paperAccountPayload);
    const incubationAccount = this.asRecord(paperAccount.account);
    const incubationAccountId = String(
      incubationAccount.id ?? incubationAccount.account_id ?? '',
    ).trim();
    const incubationSurface = this.asRecord(strategy.incubation_surface);
    const incubationMetrics = this.asRecord(incubationMetricsPayload);
    const incubationMetricItems = this.asRecordArray(incubationMetrics.items);
    const latestIncubationMetric = this.asRecord(
      incubationMetrics.latest ?? incubationMetricItems[0] ?? null,
    );

    const personal: StrategyPaperTrackSnapshot = personalAccountId
      ? await this.loadPaperTrackSnapshot({
          kind: 'personal',
          source: 'strategy_paper_session',
          label: '个人模拟盘测试',
          userId: actor.actorId,
          accountId: personalAccountId,
          sessionState,
          account: null,
          latestNav: null,
          orderSummary: null,
          latestMetric: null,
          stage: null,
          accountStatus: String(sessionState.account_status ?? '').trim() || null,
        })
      : {
          kind: 'personal',
          source: 'strategy_paper_session',
          label: '个人模拟盘测试',
          available: false,
          reason: paperSessionResult.status === 'rejected'
            ? `个人模拟盘服务暂不可用：${this.describeError(paperSessionResult.reason)}`
            : '尚未创建个人模拟盘测试',
          session: (sessionState as StrategyPaperTrackSnapshot['session']) ?? null,
        };

    const incubation: StrategyPaperTrackSnapshot = incubationAccountId
      ? await this.loadPaperTrackSnapshot({
          kind: 'incubation',
          source: 'strategy_binding',
          label: '孵化模拟盘',
          userId: actor.actorId,
          accountId: incubationAccountId,
          sessionState: null,
          account: incubationAccount,
          latestNav: this.asRecord(paperAccount.latest_nav),
          orderSummary: this.asRecord(paperAccount.order_summary),
          latestMetric: latestIncubationMetric,
          stage:
            String(
              incubationAccount.incubation_stage
              ?? incubationSurface.account_stage
              ?? incubationSurface.pipeline_stage
              ?? '',
            ).trim() || null,
          accountStatus:
            String(
              incubationAccount.status
              ?? incubationSurface.account_status
              ?? '',
            ).trim() || null,
        })
      : {
          kind: 'incubation',
          source: 'strategy_binding',
          label: '孵化模拟盘',
          available: false,
          reason: paperAccountResult.status === 'rejected'
            ? `孵化模拟盘服务暂不可用：${this.describeError(paperAccountResult.reason)}`
            : '当前策略尚未绑定孵化模拟盘账户',
          latest_metric: (latestIncubationMetric as StrategyPaperTrackSnapshot['latest_metric']) ?? null,
        };

    return {
      strategy_id: String(strategy.id ?? id).trim() || id,
      strategy_name: strategyName,
      personal,
      incubation,
    };
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
    try {
      return await this.call('closure_review', {
        strategy_id: id,
        as_of: params.as_of,
        correlation_id: params.correlation_id,
        ...this.managerActorParams({ actorId: params.user_id, role: params.role }),
      }, { timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS });
    } catch (error) {
      const detail = this.asRecord(await this.detail(id, { userId: params.user_id, role: params.role }).catch(() => null));
      this.logger.warn(`策略 ${id} 闭环审查降级为详情摘要: ${this.describeError(error)}`);
      return {
        strategy_id: id,
        as_of: params.as_of ?? new Date().toISOString().slice(0, 10),
        correlation_id: params.correlation_id ?? null,
        stale: true,
        owner_state: this.asRecord(detail.owner_state),
        favorite_state: this.asRecord(detail.favorite_state),
        paper_session_state: this.asRecord(detail.paper_session_state),
        presentation: this.asRecord(detail.presentation),
        report: null,
        events: null,
        incubation: null,
        runtime: null,
        vectors: null,
        domain: null,
        data_freshness: {
          degraded: true,
          reason: this.describeError(error),
        },
      };
    }
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
  }, actor?: { userId?: string | null; role?: string | null }) {
    const res = await this.fetchRankingWithCache(params, false);
    return this.withRuntimeActionContracts(res.data, actor);
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
    try {
      return await this.call('my_subscriptions', { user_id: userId }, {
        timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS,
        retryOnTransportError: true,
      });
    } catch (error) {
      this.logger.warn(`策略订阅列表降级为空列表: ${this.describeError(error)}`);
      return {
        subscriptions: [],
        favorites: [],
        items: [],
        count: 0,
        degraded: true,
        degraded_reason: this.describeError(error),
      };
    }
  }

  async favorite(id: string, userId: string) {
    return this.call('favorite', { strategy_id: id, user_id: userId });
  }

  async unfavorite(id: string, userId: string) {
    return this.call('unfavorite', { strategy_id: id, user_id: userId });
  }

  async myFavorites(userId: string, role = 'user') {
    try {
      const payload = this.asRecord(await this.call('my_favorites', { user_id: userId }, {
        timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS,
        retryOnTransportError: true,
      }));
      return this.withRuntimeActionContracts({
        ...payload,
        favorites: Array.isArray(payload.favorites)
          ? payload.favorites
          : Array.isArray(payload.subscriptions)
            ? payload.subscriptions
            : Array.isArray(payload.items)
              ? payload.items
              : [],
      }, { userId, role });
    } catch (error) {
      this.logger.warn(`策略收藏列表降级为空列表: ${this.describeError(error)}`);
      return {
        subscriptions: [],
        favorites: [],
        items: [],
        count: 0,
        degraded: true,
        degraded_reason: this.describeError(error),
      };
    }
  }

  async myStrategies(
    actorId: string,
    role: string,
    params: { include_archived?: boolean; limit?: number; offset?: number } = {},
  ) {
    try {
      return this.normalizeMyStrategiesPayload(await this.call('my_strategies', {
        ...this.managerActorParams({ actorId, role }),
        include_archived: params.include_archived,
        limit: params.limit,
        offset: params.offset,
      }, {
        timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS,
        retryOnTransportError: true,
      }), { userId: actorId, role });
    } catch (error) {
      this.logger.warn(`我的策略列表降级为 DB 快照: ${this.describeError(error)}`);
      const fallback = await this.withLocalTimeout(
        this.loadMyStrategiesFallbackFromDb(actorId, role, params),
        StrategyMarketService.DETAIL_FALLBACK_TIMEOUT_MS,
        `my strategies fallback timed out after ${StrategyMarketService.DETAIL_FALLBACK_TIMEOUT_MS}ms`,
      );
      return this.normalizeMyStrategiesPayload({
        ...fallback,
        local_fallback_used: true,
        upstream_error: this.describeError(error),
      }, { userId: actorId, role });
    }
  }

  async runtimeActions(id: string, actor?: { userId?: string | null; role?: string | null }) {
    const detail = this.asRecord(await this.detail(id, actor));
    const contract = this.asRecord(detail.runtime_action_contract);
    if (contract.dto_version === 'strategy_market.runtime_actions.v1') {
      return contract as StrategyRuntimeActionContract;
    }
    const strategy = this.asRecord(detail.strategy);
    return this.buildRuntimeActionContract({
      strategy,
      actor,
      ownerState: this.asRecord(detail.owner_state),
      favoriteState: this.asRecord(detail.favorite_state),
      paperSessionState: this.asRecord(detail.paper_session_state),
    });
  }

  async forkStrategy(id: string, actor: { actorId: string; role: string }) {
    try {
      return await this.call('fork_strategy', {
        strategy_id: id,
        ...this.managerActorParams(actor),
      });
    } catch (error) {
      if (!(error instanceof BadGatewayException)) {
        throw error;
      }
      this.logger.warn(`策略 ${id} fork 降级为 DB 写入: ${this.describeError(error)}`);
      return this.forkStrategyFallbackToDb(id, actor);
    }
  }

  async personalStrategyContext(id: string, actor: { actorId: string; role: string }) {
    try {
      return await this.call('personal_strategy_context', {
        strategy_id: id,
        ...this.managerActorParams(actor),
      });
    } catch (error) {
      const detail = this.asRecord(await this.detail(id, { userId: actor.actorId, role: actor.role }).catch(() => null));
      const strategy = this.asRecord(detail.strategy);
      this.logger.warn(`个人策略上下文降级为只读视图: ${this.describeError(error)}`);
      return {
        strategy_id: String(strategy.id ?? id).trim() || id,
        strategy_name: String(strategy.name ?? '').trim() || id,
        editable: false,
        personal_strategy: false,
        mutation_guard: {
          allowed: false,
          reason: `个人策略上下文暂不可用：${this.describeError(error)}`,
        },
        draft_snapshot: {
          name: String(strategy.name ?? '').trim() || id,
          description: String(strategy.description ?? '').trim(),
          params: this.asRecord(strategy.params),
          factor_weights: this.asRecord(strategy.factor_weights),
          tags: Array.isArray(strategy.tags) ? strategy.tags.map((item) => String(item).trim()).filter(Boolean) : [],
        },
        draft_stats: {
          description_present: Boolean(String(strategy.description ?? '').trim()),
          tag_count: Array.isArray(strategy.tags) ? strategy.tags.length : 0,
          param_key_count: Object.keys(this.asRecord(strategy.params)).length,
          factor_weight_key_count: Object.keys(this.asRecord(strategy.factor_weights)).length,
        },
        action_modes: [
          {
            action_kind: 'view',
            effect: 'readonly',
            available: true,
            label: '查看当前只读策略上下文',
            reason: `个人策略上下文暂不可用：${this.describeError(error)}`,
          },
        ],
        degraded: true,
        degraded_reason: this.describeError(error),
      };
    }
  }

  async personalStrategySuggestions(
    id: string,
    input: {
      objective?: string;
      instructions?: string;
      focus_fields?: string[];
      persist?: boolean;
      run_post_update_pipeline?: boolean;
    },
    actor: { actorId: string; role: string },
  ) {
    return this.call('personal_strategy_suggestions', {
      strategy_id: id,
      objective: input.objective,
      instructions: input.instructions,
      focus_fields: input.focus_fields,
      persist: input.persist,
      run_post_update_pipeline: input.run_post_update_pipeline,
      ...this.managerActorParams(actor),
    });
  }

  async updateStrategy(id: string, updates: Record<string, unknown>, actor: { actorId: string; role: string }) {
    const sanitizedUpdates = this.sanitizeStrategyUpdates(updates);
    return this.call('update_strategy', {
      strategy_id: id,
      updates: sanitizedUpdates.updates,
      mutation_scope: sanitizedUpdates.mutationScope,
      run_post_update_pipeline: sanitizedUpdates.runPostUpdatePipeline,
      ...this.managerActorParams(actor),
    });
  }

  private sanitizeStrategyUpdates(updates: Record<string, unknown>) {
    const mutationScope = updates.mutationScope === 'lifecycle' ? 'lifecycle' : 'draft';
    const runPostUpdatePipeline = mutationScope === 'lifecycle' && updates.run_post_update_pipeline === true;
    if (mutationScope === 'lifecycle') {
      const rest = Object.fromEntries(
        Object.entries(updates).filter(([key]) => key !== 'mutationScope' && key !== 'run_post_update_pipeline'),
      );
      return { updates: rest, mutationScope, runPostUpdatePipeline };
    }

    const draftKeys = new Set(['name', 'description', 'params', 'factor_weights', 'tags']);
    const draftUpdates = Object.entries(updates).reduce<Record<string, unknown>>((acc, [key, value]) => {
      if (draftKeys.has(key)) acc[key] = value;
      return acc;
    }, {});
    return { updates: draftUpdates, mutationScope, runPostUpdatePipeline: false };
  }

  async deletePersonalStrategy(id: string, actor: { actorId: string; role: string }) {
    try {
      const result = await this.call('delete_personal_strategy', {
        strategy_id: id,
        ...this.managerActorParams(actor),
      });
      const localMirrorArchived = await this.archiveLocalPersonalStrategyMirror(id, actor);
      return {
        ...this.asRecord(result),
        strategy_id: String(this.asRecord(result).strategy_id ?? id),
        local_mirror_archived: localMirrorArchived,
      };
    } catch (error) {
      if (!(error instanceof BadGatewayException)) {
        throw error;
      }
      this.logger.warn(`个人策略 ${id} 删除降级为 DB 归档: ${this.describeError(error)}`);
      const fallback = await this.deletePersonalStrategyFallbackToDb(id, actor);
      this.strategySummaryFallbackCache.delete(id);
      return fallback;
    }
  }

  async paperSession(id: string, actor: { actorId: string; role: string }) {
    return this.call('paper_session_get', {
      strategy_id: id,
      ...this.managerActorParams(actor),
    }, { timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS });
  }

  async getOrCreatePaperSession(id: string, actor: { actorId: string; role: string }) {
    return this.call('paper_session_get_or_create', {
      strategy_id: id,
      ...this.managerActorParams(actor),
    });
  }

  async aiOptimizePersonalStrategy(
    id: string,
    actor: { actorId: string; role: string },
    input: {
      objective?: string;
      instructions?: string;
      focus_fields?: string[];
    } = {},
  ) {
    return this.call('ai_optimize_personal_strategy', {
      strategy_id: id,
      objective: input.objective,
      instructions: input.instructions,
      focus_fields: input.focus_fields,
      ...this.managerActorParams(actor),
    });
  }

  async submit(id: string) {
    return this.call('submit', { strategy_id: id });
  }

  async factoryStatus(options: StrategyManagerCallOptions = {}) {
    const backgroundRun = await this.loadBackgroundFactoryRunState();
    return this.mergeFactoryStatusWithBackgroundRun(await this.fetchFactoryStatusWithCache(false, options), backgroundRun);
  }

  async factoryRunOnce() {
    return {
      ...(await this.factoryDispatchRun()),
      canonical_action: 'factory_dispatch_run',
      legacy_action: 'factory_run_once',
      alias: true,
      deprecated: true,
    };
  }

  async factoryDispatchRun() {
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
        canonical_action: 'factory_dispatch_run',
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
      canonical_action: 'factory_dispatch_run',
    };
  }

  async factoryRuns(limit?: number, options: StrategyManagerCallOptions = {}) {
    const backgroundRun = await this.loadBackgroundFactoryRunState();
    return this.mergeFactoryRunsWithBackgroundRun(
      await this.fetchFactoryRunsWithCache(limit, false, options),
      limit,
      backgroundRun,
    );
  }

  async factoryRunDetail(runId: string, options: StrategyManagerCallOptions = {}) {
    return this.fetchFactoryRunDetailWithCache(runId, false, options);
  }

  async factoryTopnLatest(limit?: number, options: StrategyManagerCallOptions = {}) {
    try {
      return await this.call('factory_topn_latest', {
        limit: limit == null ? undefined : Math.max(1, Math.min(Number(limit) || 20, 100)),
      }, options);
    } catch (error) {
      return this.degradedReadSurface('factory_topn_latest', error, {
        snapshot: null,
        items: [],
        count: 0,
      });
    }
  }

  async factoryRunTopn(runId: string, limit?: number) {
    try {
      return await this.call('factory_run_topn', {
        run_id: runId,
        limit: limit == null ? undefined : Math.max(1, Math.min(Number(limit) || 20, 100)),
      });
    } catch (error) {
      return this.degradedReadSurface('factory_run_topn', error, {
        run_id: runId,
        snapshot: null,
        items: [],
        count: 0,
      });
    }
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

  async factoryObservability(options: StrategyManagerCallOptions = {}) {
    return loadFactoryObservability({
      factoryStatus: (sectionOptions) => this.factoryStatus(sectionOptions),
      factoryRuns: (limit, sectionOptions) => this.factoryRuns(limit, sectionOptions),
      callQuantManager: (action, params, sectionOptions) => this.callQuantManager(action, params, sectionOptions),
      flattenMcpResult: (payload) => this.flattenMcpResult(payload),
      unwrapSettledObject: (result, section) => this.unwrapSettledObject(result, section),
      asRecord: (value) => this.asRecord(value),
      asRecordArray: (value) => this.asRecordArray(value),
      toNum: (value) => this.toNum(value),
    }, options);
  }

  async factoryMarketView(
    options: {
      runId?: string | null;
      includeDetails?: boolean;
      actor?: { userId?: string | null; role?: string | null };
    } = {},
  ) {
    const includeDetails = Boolean(options.includeDetails);
    const selectedRunId = String(options.runId ?? '').trim() || null;
    const actor = options.actor;
    const fastOptions = { timeoutMs: StrategyMarketService.FACTORY_MARKET_FAST_TIMEOUT_MS };
    const detailOptions = { timeoutMs: StrategyMarketService.FACTORY_MARKET_DETAIL_TIMEOUT_MS };
    const sections = await Promise.all([
      this.settleWithTimeout('capabilities', this.capabilities(actor, fastOptions), fastOptions.timeoutMs),
      this.settleWithTimeout('factory_status', this.factoryStatus(fastOptions), fastOptions.timeoutMs),
      this.settleWithTimeout('daily_snapshot', this.dailySnapshot(undefined, fastOptions), fastOptions.timeoutMs),
      this.settleWithTimeout('factory_runs_surface', this.loadFactoryRunsSurfaceFromDb(5), fastOptions.timeoutMs),
      this.settleWithTimeout('factory_research_surface', this.loadFactoryResearchSurfaceFromDb(), fastOptions.timeoutMs),
      this.settleWithTimeout('factory_topn_surface', this.loadFactoryTopnSurfaceFromDb(5), fastOptions.timeoutMs),
      this.settleWithTimeout('factory_retrain_surface', this.loadModelRetrainSurfaceFromDb(5), fastOptions.timeoutMs),
      includeDetails
        ? this.settleWithTimeout(
            'factory_observability',
            this.factoryObservability(detailOptions),
            detailOptions.timeoutMs,
          )
        : Promise.resolve({ status: 'fulfilled', value: null } as PromiseFulfilledResult<null>),
      includeDetails && selectedRunId
        ? this.settleWithTimeout(
            'factory_run_detail',
            this.factoryRunDetail(selectedRunId, detailOptions),
            detailOptions.timeoutMs,
          )
        : Promise.resolve({ status: 'fulfilled', value: null } as PromiseFulfilledResult<null>),
    ]);

    const [
      capabilitiesResult,
      statusResult,
      snapshotResult,
      runsResult,
      researchSurfaceResult,
      topnLatestResult,
      retrainSurfaceResult,
      observabilityResult,
      expandedRunResult,
    ] =
      sections;
    const sectionErrors = {
      capabilities:
        capabilitiesResult.status === 'rejected'
          ? String(
              capabilitiesResult.reason instanceof Error
                ? capabilitiesResult.reason.message
                : capabilitiesResult.reason,
            )
          : null,
      status:
        statusResult.status === 'rejected'
          ? String(statusResult.reason instanceof Error ? statusResult.reason.message : statusResult.reason)
          : null,
      snapshot:
        snapshotResult.status === 'rejected'
          ? String(snapshotResult.reason instanceof Error ? snapshotResult.reason.message : snapshotResult.reason)
          : null,
      runs:
        runsResult.status === 'rejected'
          ? String(runsResult.reason instanceof Error ? runsResult.reason.message : runsResult.reason)
          : null,
      observability:
        observabilityResult.status === 'rejected'
          ? String(
              observabilityResult.reason instanceof Error
                ? observabilityResult.reason.message
                : observabilityResult.reason,
            )
          : null,
      expanded_run:
        expandedRunResult.status === 'rejected'
          ? String(
              expandedRunResult.reason instanceof Error ? expandedRunResult.reason.message : expandedRunResult.reason,
            )
          : null,
    };

    return buildFactoryMarketViewResponse({
      capabilities:
        capabilitiesResult.status === 'fulfilled' ? (capabilitiesResult.value as Record<string, unknown>) : null,
      status: statusResult.status === 'fulfilled' ? (statusResult.value as Record<string, unknown>) : null,
      snapshot: snapshotResult.status === 'fulfilled' ? (snapshotResult.value as Record<string, unknown>) : null,
      runs: runsResult.status === 'fulfilled' ? (runsResult.value as Record<string, unknown>) : null,
      researchSurface:
        researchSurfaceResult.status === 'fulfilled'
          ? (researchSurfaceResult.value as Record<string, unknown>)
          : null,
      topnLatest: topnLatestResult.status === 'fulfilled' ? (topnLatestResult.value as Record<string, unknown>) : null,
      retrainSurface:
        retrainSurfaceResult.status === 'fulfilled'
          ? (retrainSurfaceResult.value as Record<string, unknown>)
          : null,
      observability:
        observabilityResult.status === 'fulfilled' ? (observabilityResult.value as Record<string, unknown>) : null,
      expandedRun:
        expandedRunResult.status === 'fulfilled' ? (expandedRunResult.value as Record<string, unknown>) : null,
      selectedRunId,
      sectionErrors,
    });
  }

  async coreChainAcceptance(
    actor: { actorId?: string | null; role: string },
    params: { strategy_id?: string | null; personal_strategy_id?: string | null; include_raw?: boolean } = {},
  ): Promise<StrategyCoreChainAcceptanceResponse> {
    const generatedAt = new Date().toISOString();
    const actorId = String(actor.actorId ?? '').trim();
    const actorRole = String(actor.role ?? 'user').trim() || 'user';
    const authenticated = Boolean(actorId);
    const loginMissingReason = '当前请求未登录，无法验收当前用户的个人策略、模拟盘和 AI 写回链路。';
    const requestedStrategyId = String(params.strategy_id ?? '').trim() || null;
    const requestedPersonalStrategyId = String(params.personal_strategy_id ?? '').trim() || null;

    const [healthRead, rankingRead] = await Promise.all([
      this.settleAcceptance('mcp.health', this.mcp.checkAvailableTools()),
      requestedStrategyId
        ? Promise.resolve({ value: null, error: null } as AcceptanceRead<unknown>)
        : this.settleAcceptance('strategy_market.ranking', this.rank({ status: 'all', limit: 1 })),
    ]);

    const rankingRows = this.acceptanceRows(rankingRead.value);
    const rankedStrategyId = this.strategyIdFromRecord(rankingRows[0]);
    const initialMarketStrategyId = requestedStrategyId || rankedStrategyId || null;

    const [capabilitiesRead, factoryViewRead, detailRead, favoritesRead, myStrategiesRead] = await Promise.all([
      this.settleAcceptance(
        'strategy_market.capabilities',
        this.capabilities({ userId: actorId || null, role: actorRole }),
      ),
      this.settleAcceptance(
        'strategy_market.factory_market_view',
        this.factoryMarketView({
          includeDetails: false,
          actor: { userId: actorId || null, role: actorRole },
        }),
      ),
      initialMarketStrategyId
        ? this.settleAcceptance(
            'strategy_market.detail',
            this.detail(initialMarketStrategyId, { userId: actorId || null, role: actorRole }),
          )
        : Promise.resolve({ value: null, error: '未找到可验收策略' } as AcceptanceRead<unknown>),
      authenticated
        ? this.settleAcceptance('strategy_market.my_favorites', this.myFavorites(actorId, actorRole))
        : Promise.resolve({ value: { favorites: [], items: [], count: 0 }, error: null } as AcceptanceRead<unknown>),
      authenticated
        ? this.settleAcceptance(
            'strategy_market.my_strategies',
            this.myStrategies(actorId, actorRole, { limit: 100 }),
          )
        : Promise.resolve({ value: { strategies: [], items: [], count: 0 }, error: null } as AcceptanceRead<unknown>),
    ]);

    const capabilities = this.asRecord(capabilitiesRead.value);
    const actorPermissions = this.asRecord(capabilities.actor_permissions);
    const detail = this.asRecord(detailRead.value);
    const detailStrategy = this.asRecord(detail.strategy);
    const resolvedMarketStrategyId =
      this.strategyIdFromRecord(detailStrategy) || initialMarketStrategyId || null;
    const strategyName = String(detailStrategy.name ?? '').trim() || resolvedMarketStrategyId;
    const ownerState = this.asRecord(detail.owner_state);
    const detailPersonalContext = this.asRecord(detail.personal_strategy_context);
    const targetIsPersonal = Boolean(
      ownerState.personal_strategy ||
        detailPersonalContext.personal_strategy ||
        this.isAcceptancePersonalStrategyRecord(detailStrategy),
    );

    const myStrategyRows = this.acceptanceRows(myStrategiesRead.value);
    const favoriteRows = this.acceptanceRows(favoritesRead.value);
    const favoriteRecord = favoriteRows.find((row) => this.strategyIdFromRecord(row) === resolvedMarketStrategyId) ?? null;
    const explicitPersonalRow = requestedPersonalStrategyId
      ? myStrategyRows.find((row) => this.strategyIdFromRecord(row) === requestedPersonalStrategyId) ?? null
      : null;
    const sourceMatchedPersonalRow = resolvedMarketStrategyId
      ? myStrategyRows.find((row) => {
          const id = this.strategyIdFromRecord(row);
          if (!id) return false;
          if (id === resolvedMarketStrategyId && this.isAcceptancePersonalStrategyRecord(row)) return true;
          return this.sourceStrategyIdFromRecord(row) === resolvedMarketStrategyId;
        }) ?? null
      : null;
    const fallbackPersonalRow =
      !requestedPersonalStrategyId && !sourceMatchedPersonalRow
        ? myStrategyRows.find((row) => this.isAcceptancePersonalStrategyRecord(row)) ?? null
        : null;
    const personalRow = explicitPersonalRow ?? sourceMatchedPersonalRow ?? fallbackPersonalRow;
    const personalStrategyId =
      requestedPersonalStrategyId ||
      this.strategyIdFromRecord(personalRow) ||
      (targetIsPersonal ? resolvedMarketStrategyId : null);

    const [
      personalContextRead,
      paperContextRead,
      paperSessionRead,
      aiTaskRunsRead,
      aiExperimentsRead,
    ] = personalStrategyId
      ? authenticated
        ? await Promise.all([
          this.settleAcceptance(
            'strategy_market.personal_strategy_context',
            this.personalStrategyContext(personalStrategyId, { actorId, role: actorRole }),
          ),
          this.settleAcceptance(
            'strategy_market.paper_context',
            this.paperContext(personalStrategyId, { actorId, role: actorRole }),
          ),
          this.settleAcceptance(
            'strategy_market.paper_session',
            this.paperSession(personalStrategyId, { actorId, role: actorRole }),
          ),
          this.settleAcceptance(
            'strategy_market.task_runs.ai_optimize_personal_strategy',
            this.taskRuns({
              strategy_id: personalStrategyId,
              task_name: 'ai_optimize_personal_strategy',
              limit: 10,
            }),
          ),
          this.settleAcceptance(
            'strategy_market.ai_experiments.personal_strategy',
            this.aiExperiments({
              strategy_id: personalStrategyId,
              generated_strategy_id: personalStrategyId,
              source: 'strategy_manager.personal_strategy',
              limit: 10,
            }),
          ),
        ])
        : [
            { value: null, error: loginMissingReason },
            { value: null, error: loginMissingReason },
            { value: null, error: loginMissingReason },
            { value: null, error: loginMissingReason },
            { value: null, error: loginMissingReason },
          ]
      : [
          { value: null, error: '尚未找到个人策略' },
          { value: null, error: '尚未找到个人策略' },
          { value: null, error: '尚未找到个人策略' },
          { value: null, error: '尚未找到个人策略' },
          { value: null, error: '尚未找到个人策略' },
        ];

    const health = this.asRecord(healthRead.value);
    const factoryView = this.asRecord(factoryViewRead.value);
    const factoryRuns = this.asRecord(factoryView.runs);
    const latestFactoryRun = this.asRecord(factoryRuns.latest);
    const factorySurface = this.asRecord(factoryView.surface);
    const visibleFactoryOutputs = this.asRecordArray(factorySurface.visible_outputs);
    const factoryOutputVisible =
      visibleFactoryOutputs.length > 0 ||
      Boolean(String(latestFactoryRun.run_id ?? '').trim()) ||
      Object.keys(this.asRecord(factoryView.snapshot)).length > 0;
    const personalContext = this.asRecord(personalContextRead.value);
    const personalDraft = this.asRecord(personalContext.draft_snapshot);
    const personalOwnerState = this.asRecord(personalContext.owner_state);
    const personalPaperState = this.asRecord(personalContext.paper_session_state);
    const paperSession = this.asRecord(paperSessionRead.value);
    const paperSessionState = this.asRecord(paperSession.paper_session_state);
    const paperContext = this.asRecord(paperContextRead.value);
    const personalTrack = this.asRecord(paperContext.personal);
    const personalTrackAccount = this.asRecord(personalTrack.account);
    const personalAccountId = String(
      personalPaperState.account_id ??
        paperSessionState.account_id ??
        personalTrack.account_id ??
        personalTrackAccount.account_id ??
        personalTrackAccount.id ??
        '',
    ).trim();
    const paperSessionCompleted = Boolean(
      personalAccountId &&
        (personalPaperState.has_session ||
          paperSessionState.has_session ||
          personalTrack.available ||
          Object.keys(this.asRecord(paperSession.session)).length > 0),
    );

    const aiTaskRows = this.acceptanceRows(aiTaskRunsRead.value);
    const aiExperimentRows = this.acceptanceRows(aiExperimentsRead.value);
    const successfulAiTask = aiTaskRows.find((row) =>
      ['success', 'succeeded', 'completed'].includes(String(row.status ?? '').trim().toLowerCase()),
    ) ?? null;
    const successfulAiExperiment = aiExperimentRows.find((row) =>
      ['success', 'succeeded', 'completed'].includes(String(row.status ?? '').trim().toLowerCase()),
    ) ?? null;
    const aiSubmitCompleted = Boolean(successfulAiTask || successfulAiExperiment);
    const aiSubmitLastSuccessAt = this.latestTimestampFromRecords(successfulAiTask, successfulAiExperiment);

    const mcpReachable = Boolean(health.reachable);
    const canCreatePersonalStrategy = Boolean(actorPermissions.can_create_personal_strategy && resolvedMarketStrategyId);
    const canCreatePaperSession = Boolean(actorPermissions.can_create_paper_session && personalStrategyId);
    const personalCompleted = Boolean(
      personalStrategyId &&
        (personalContext.personal_strategy ||
          personalOwnerState.personal_strategy ||
          this.isAcceptancePersonalStrategyRecord(personalRow) ||
          targetIsPersonal),
    );
    const mutationGuard = this.asRecord(personalContext.mutation_guard);
    const aiReadCompleted = Boolean(personalStrategyId && Object.keys(personalDraft).length > 0);
    const aiSuggestAvailable = Boolean(
      aiReadCompleted &&
        (this.actionModeAvailable(personalContext, 'generate_update_suggestion') ||
          this.actionModeAvailable(personalContext, 'view') ||
          actorPermissions.can_ai_suggest_personal_strategy),
    );
    const aiOptimizeAvailable = Boolean(
      aiReadCompleted &&
        (this.actionModeAvailable(personalContext, 'optimize') ||
          this.actionModeAvailable(personalContext, 'persist_update') ||
          mutationGuard.allowed === true),
    );

    const steps: StrategyCoreChainStep[] = [
      this.buildCoreChainStep({
        key: 'view_strategy',
        title: '查看策略',
        completed: Boolean(resolvedMarketStrategyId && detailStrategy.id),
        can_complete: Boolean(resolvedMarketStrategyId && detailStrategy.id),
        degraded: Boolean(detailRead.error && resolvedMarketStrategyId),
        success_condition: 'strategy_manager.detail 返回当前策略详情，策略超市能看到工厂/榜单产物。',
        failure_reason:
          resolvedMarketStrategyId && detailStrategy.id
            ? null
            : detailRead.error || rankingRead.error || '策略超市当前没有可验收策略。',
        dependency_gaps: [
          ...(!mcpReachable ? ['mcp_unreachable'] : []),
          ...(!resolvedMarketStrategyId ? ['strategy_market_empty'] : []),
          ...(detailRead.error ? ['strategy_detail_unavailable'] : []),
          ...(factoryViewRead.error ? ['factory_market_view_unavailable'] : []),
          ...(!factoryOutputVisible ? ['factory_output_not_visible'] : []),
        ],
        last_success_at: detailStrategy.id ? generatedAt : null,
        next_action: resolvedMarketStrategyId ? '打开策略详情页继续验收个人策略动作。' : '先运行策略工厂或刷新策略榜单。',
        action: {
          label: '打开策略详情',
          method: 'GET',
          path: resolvedMarketStrategyId ? `/strategy-market/${resolvedMarketStrategyId}` : '/strategy-market/ranking',
          href: resolvedMarketStrategyId ? `/strategy-market/${encodeURIComponent(resolvedMarketStrategyId)}` : '/strategy-market',
        },
        evidence: [
          ...(strategyName ? [`策略 ${strategyName}`] : []),
          ...(String(latestFactoryRun.run_id ?? '').trim()
            ? [`最近工厂运行 ${String(latestFactoryRun.run_id)}`]
            : []),
          ...(favoriteRecord ? ['当前用户已收藏/订阅该策略'] : []),
        ],
        sources: ['strategy_manager.detail', 'strategy_manager.rank', 'strategy_market.factory_market_view'],
        detail: {
          strategy_id: resolvedMarketStrategyId,
          factory_output_visible: factoryOutputVisible,
          factory_visible_output_count: visibleFactoryOutputs.length,
        },
      }),
      this.buildCoreChainStep({
        key: 'personal_strategy',
        title: '收藏为个人策略',
        completed: personalCompleted,
        can_complete: personalCompleted || canCreatePersonalStrategy,
        degraded: Boolean(myStrategiesRead.error && !personalStrategyId),
        success_condition: '当前用户存在由目标策略 fork/复制出的个人策略草稿，并且 owner_state.personal_strategy 为真。',
        failure_reason: personalCompleted
          ? null
          : !authenticated
            ? loginMissingReason
            : myStrategiesRead.error || '当前用户还没有该策略对应的个人策略草稿。',
        dependency_gaps: [
          ...(!authenticated ? ['login_missing'] : []),
          ...(!resolvedMarketStrategyId ? ['market_strategy_missing'] : []),
          ...(!canCreatePersonalStrategy && !personalCompleted ? ['login_or_personal_strategy_permission_missing'] : []),
          ...(myStrategiesRead.error ? ['my_strategies_unavailable'] : []),
        ],
        last_success_at: personalCompleted
          ? this.latestTimestampFromRecords(personalContext, personalRow, personalDraft) ?? generatedAt
          : null,
        next_action: personalCompleted ? '进入个人策略上下文，继续检查模拟盘。' : '从策略详情页复制为我的策略。',
        action: {
          label: personalCompleted ? '打开个人策略' : '复制为个人策略',
          method: personalCompleted ? 'GET' : 'POST',
          path: personalCompleted && personalStrategyId
            ? `/strategy-market/${personalStrategyId}`
            : `/strategy-market/${resolvedMarketStrategyId ?? ':id'}/fork`,
          href: personalCompleted && personalStrategyId
            ? `/strategy-market/${encodeURIComponent(personalStrategyId)}`
            : resolvedMarketStrategyId
              ? `/strategy-market/${encodeURIComponent(resolvedMarketStrategyId)}`
              : '/strategy-market',
        },
        evidence: [
          ...(personalStrategyId ? [`个人策略 ${personalStrategyId}`] : []),
          ...(this.sourceStrategyIdFromRecord(personalRow) ? [`来源策略 ${this.sourceStrategyIdFromRecord(personalRow)}`] : []),
          ...(favoriteRecord ? ['收藏/订阅记录存在'] : []),
        ],
        sources: ['strategy_manager.my_strategies', 'strategy_manager.fork_strategy', 'strategy_manager.personal_strategy_context'],
        detail: {
          personal_strategy_id: personalStrategyId,
          source_strategy_id: this.sourceStrategyIdFromRecord(personalRow) ?? null,
          favorite_exists: Boolean(favoriteRecord),
        },
      }),
      this.buildCoreChainStep({
        key: 'paper_session',
        title: '加入模拟盘',
        completed: paperSessionCompleted,
        can_complete: paperSessionCompleted || canCreatePaperSession,
        degraded: Boolean((paperSessionRead.error || paperContextRead.error) && personalStrategyId && !paperSessionCompleted),
        success_condition: '个人策略存在 strategy_paper_session，且能解析出 personal_strategy 模拟盘账户。',
        failure_reason: paperSessionCompleted
          ? null
          : !authenticated
            ? loginMissingReason
            : paperSessionRead.error || paperContextRead.error || '当前个人策略尚未创建个人模拟盘会话。',
        dependency_gaps: [
          ...(!authenticated ? ['login_missing'] : []),
          ...(!personalStrategyId ? ['personal_strategy_missing'] : []),
          ...(!canCreatePaperSession && !paperSessionCompleted ? ['paper_session_permission_missing'] : []),
          ...(paperSessionRead.error ? ['paper_session_unavailable'] : []),
          ...(paperContextRead.error ? ['paper_context_unavailable'] : []),
        ],
        last_success_at: paperSessionCompleted
          ? this.latestTimestampFromRecords(
              paperSession,
              this.asRecord(paperSession.session),
              personalTrack,
              this.asRecord(personalTrack.latest_nav),
            ) ?? generatedAt
          : null,
        next_action: paperSessionCompleted ? '打开模拟盘，继续检查 AI 读取个人策略。' : '为个人策略创建模拟盘会话。',
        action: {
          label: paperSessionCompleted ? '打开模拟盘' : '创建模拟盘',
          method: paperSessionCompleted ? 'GET' : 'POST',
          path: paperSessionCompleted
            ? `/paper-trading?mode=personal-strategy&strategy_id=${personalStrategyId ?? ''}${personalAccountId ? `&account_id=${personalAccountId}` : ''}`
            : `/strategy-market/${personalStrategyId ?? ':id'}/paper-session`,
          href: paperSessionCompleted
            ? `/paper-trading?mode=personal-strategy&strategy_id=${encodeURIComponent(personalStrategyId ?? '')}${personalAccountId ? `&account_id=${encodeURIComponent(personalAccountId)}` : ''}`
            : personalStrategyId
              ? `/strategy-market/${encodeURIComponent(personalStrategyId)}`
              : '/strategy-market?workspace=mine',
        },
        evidence: [
          ...(personalAccountId ? [`模拟盘账户 ${personalAccountId}`] : []),
          ...(String(personalTrack.reason ?? '').trim() ? [`模拟盘说明 ${String(personalTrack.reason)}`] : []),
        ],
        sources: ['strategy_manager.paper_session_get', 'strategy_market.paper_context', 'paper_trading.*'],
        detail: {
          account_id: personalAccountId || null,
          paper_session_state: personalPaperState,
        },
      }),
      this.buildCoreChainStep({
        key: 'ai_read',
        title: '让 AI 读取',
        completed: aiReadCompleted,
        can_complete: aiSuggestAvailable,
        degraded: Boolean(personalContextRead.error && personalStrategyId),
        success_condition: 'personal_strategy_context 返回 draft_snapshot，AI 建议动作能读取当前个人策略草稿。',
        failure_reason: aiReadCompleted
          ? null
          : !authenticated
            ? loginMissingReason
            : personalContextRead.error || '尚未拿到可供 AI 读取的个人策略草稿上下文。',
        dependency_gaps: [
          ...(!authenticated ? ['login_missing'] : []),
          ...(!personalStrategyId ? ['personal_strategy_missing'] : []),
          ...(personalContextRead.error ? ['personal_strategy_context_unavailable'] : []),
          ...(!aiSuggestAvailable && personalStrategyId ? ['ai_suggestion_action_unavailable'] : []),
        ],
        last_success_at: aiReadCompleted ? generatedAt : null,
        next_action: aiReadCompleted ? '生成 AI 修改建议，或直接进入 AI 写回验收。' : '先打开个人策略上下文。',
        action: {
          label: '生成 AI 建议',
          method: 'POST',
          path: `/strategy-market/${personalStrategyId ?? ':id'}/ai-modification-suggestions`,
          href: personalStrategyId ? `/strategy-market/${encodeURIComponent(personalStrategyId)}` : '/strategy-market?workspace=mine',
          body: {
            objective: '验收核心链路：读取个人策略草稿并生成低风险修改建议',
            focus_fields: ['description', 'params', 'factor_weights', 'tags'],
            persist: false,
          },
        },
        evidence: [
          ...(personalContext.strategy_name ? [`AI 上下文策略 ${String(personalContext.strategy_name)}`] : []),
          `草稿字段 ${Object.keys(personalDraft).length}`,
        ],
        sources: ['strategy_manager.personal_strategy_context', 'strategy_manager.personal_strategy_suggestions'],
        detail: {
          draft_stats: this.asRecord(personalContext.draft_stats),
          mutation_guard: mutationGuard,
        },
      }),
      this.buildCoreChainStep({
        key: 'ai_submit',
        title: '让 AI 提交修改',
        completed: aiSubmitCompleted,
        can_complete: Boolean(aiSubmitCompleted || aiOptimizeAvailable),
        degraded: Boolean((aiTaskRunsRead.error || aiExperimentsRead.error) && personalStrategyId && !aiSubmitCompleted),
        success_condition: 'ai_optimize_personal_strategy 产生成功 task_run 或 completed AI experiment，并写回当前个人策略。',
        failure_reason: aiSubmitCompleted
          ? null
          : !authenticated
            ? loginMissingReason
            : aiOptimizeAvailable
            ? '未发现最近成功的 AI 写回记录；当前具备触发条件。'
            : String(mutationGuard.reason ?? personalContextRead.error ?? '当前个人策略不允许 AI 写回。'),
        dependency_gaps: [
          ...(!authenticated ? ['login_missing'] : []),
          ...(!personalStrategyId ? ['personal_strategy_missing'] : []),
          ...(!aiReadCompleted && personalStrategyId ? ['ai_read_context_missing'] : []),
          ...(!aiOptimizeAvailable && personalStrategyId ? ['ai_optimize_action_unavailable'] : []),
          ...(aiTaskRunsRead.error ? ['ai_task_runs_unavailable'] : []),
          ...(aiExperimentsRead.error ? ['ai_experiments_unavailable'] : []),
          ...(!aiSubmitCompleted ? ['ai_submit_success_missing'] : []),
        ],
        last_success_at: aiSubmitLastSuccessAt,
        next_action: aiSubmitCompleted ? '查看 AI 写回结果和个人策略最新草稿。' : '触发 AI 优化写回并刷新验收面板。',
        action: {
          label: aiSubmitCompleted ? '打开个人策略' : '执行 AI 优化',
          method: aiSubmitCompleted ? 'GET' : 'POST',
          path: aiSubmitCompleted && personalStrategyId
            ? `/strategy-market/${personalStrategyId}`
            : `/strategy-market/${personalStrategyId ?? ':id'}/ai-optimize`,
          href: personalStrategyId ? `/strategy-market/${encodeURIComponent(personalStrategyId)}` : '/strategy-market?workspace=mine',
          body: aiSubmitCompleted
            ? null
            : {
                objective: '验收核心链路：AI 写回个人策略草稿',
                focus_fields: ['description', 'params', 'factor_weights', 'tags'],
              },
        },
        evidence: [
          ...(successfulAiTask ? [`task_run ${String(successfulAiTask.id ?? successfulAiTask.task_run_id ?? '-')}`] : []),
          ...(successfulAiExperiment ? [`experiment ${String(successfulAiExperiment.experiment_id ?? '-')}`] : []),
          `AI task rows ${aiTaskRows.length}`,
        ],
        sources: ['strategy_manager.ai_optimize_personal_strategy', 'strategy_manager.task_runs', 'strategy_manager.ai_experiments'],
        detail: {
          latest_task_run: successfulAiTask,
          latest_experiment: successfulAiExperiment,
        },
      }),
    ];

    const blockedSteps = steps.filter((step) => step.status === 'blocked').map((step) => step.key);
    const degradedSteps = steps.filter((step) => step.status === 'degraded').map((step) => step.key);
    const readySteps = steps.filter((step) => step.status === 'ready').length;
    const completedSteps = steps.filter((step) => step.completed).length;
    const overallStatus: StrategyCoreChainStepStatus =
      degradedSteps.length > 0
        ? 'degraded'
        : blockedSteps.length > 0
          ? 'blocked'
          : completedSteps === steps.length
            ? 'passed'
            : 'ready';

    const response: StrategyCoreChainAcceptanceResponse = {
      dto_version: 'strategy_market.core_chain_acceptance.v1',
      generated_at: generatedAt,
      actor: {
        user_id: actorId || null,
        role: actorRole,
      },
      environment: {
        authenticated,
        mcp_reachable: mcpReachable,
        mcp_source: String(health.source ?? health.transportKind ?? '').trim() || null,
        degraded: Boolean(
          !mcpReachable ||
            healthRead.error ||
            capabilitiesRead.error ||
            factoryViewRead.error ||
            detailRead.error ||
            myStrategiesRead.error,
        ),
        errors: {
          mcp_health: healthRead.error,
          capabilities: capabilitiesRead.error,
          ranking: rankingRead.error,
          factory_market_view: factoryViewRead.error,
          detail: detailRead.error,
          my_favorites: favoritesRead.error,
          my_strategies: myStrategiesRead.error,
          personal_context: personalContextRead.error,
          paper_context: paperContextRead.error,
          paper_session: paperSessionRead.error,
          ai_task_runs: aiTaskRunsRead.error,
          ai_experiments: aiExperimentsRead.error,
          auth: authenticated ? null : loginMissingReason,
        },
      },
      target: {
        requested_strategy_id: requestedStrategyId,
        market_strategy_id: resolvedMarketStrategyId,
        personal_strategy_id: personalStrategyId,
        source_strategy_id:
          this.sourceStrategyIdFromRecord(personalRow) ??
          (String(personalContext.source_strategy_id ?? '').trim() || null),
        strategy_name: strategyName,
        personal_strategy_name: String(personalContext.strategy_name ?? personalRow?.name ?? '').trim() || null,
      },
      summary: {
        overall_status: overallStatus,
        runnable: steps.every((step) => step.completed || step.can_complete) && degradedSteps.length === 0,
        fully_completed: completedSteps === steps.length,
        completed_steps: completedSteps,
        ready_steps: readySteps,
        blocked_steps: blockedSteps,
        degraded_steps: degradedSteps,
        broken_steps: [...blockedSteps, ...degradedSteps],
      },
      steps,
    };

    if (params.include_raw) {
      response.raw = {
        capabilities,
        factory_view: factoryView,
        detail,
        my_favorites: favoritesRead.value,
        my_strategies: myStrategiesRead.value,
        personal_context: personalContext,
        paper_context: paperContext,
        paper_session: paperSession,
        ai_task_runs: aiTaskRunsRead.value,
        ai_experiments: aiExperimentsRead.value,
      };
    }

    return response;
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

  async capabilities(
    actor?: { userId?: string | null; role?: string | null },
    options: StrategyManagerCallOptions = {},
  ) {
    try {
      const capabilities = this.asRecord(await this.call('capabilities', {}, {
        timeoutMs: options.timeoutMs ?? StrategyMarketService.READ_SURFACE_TIMEOUT_MS,
      }));
      return {
        ...capabilities,
        system_capabilities: capabilities,
        actor_permissions: this.buildActorPermissions(actor),
      };
    } catch (error) {
      this.logger.warn(`策略能力集降级为本地权限视图: ${this.describeError(error)}`);
      return {
        system_capabilities: {},
        actor_permissions: this.buildActorPermissions(actor),
        degraded: true,
        degraded_reason: this.describeError(error),
      };
    }
  }

  async capabilityDiagnostics() {
    const health = await this.mcp.checkAvailableTools().catch((error) => ({
      reachable: false,
      toolCount: null,
      expectedTools: null,
      matched: false,
      source: 'unavailable',
      message: this.describeError(error),
    }));
    return buildStrategyCapabilityDiagnostics({ mcpRuntime: health });
  }

  async dailySnapshots(params: { limit?: number; start_date?: string; end_date?: string } = {}) {
    try {
      return await this.call('daily_snapshots', params);
    } catch (error) {
      return this.degradedReadSurface('daily_snapshots', error, {
        snapshots: [],
        items: [],
        count: 0,
      });
    }
  }

  async dailySnapshot(snapshotDate?: string, options: StrategyManagerCallOptions = {}) {
    return this.call('daily_snapshot', { snapshot_date: snapshotDate }, options);
  }

  async incubationAccounts(id: string, params: { status?: string; limit?: number } = {}) {
    return this.call('incubation_accounts', { strategy_id: id, ...params });
  }

  async incubationMetrics(id: string, params: { limit?: number; start_date?: string; end_date?: string } = {}) {
    return this.call('incubation_metrics', { strategy_id: id, ...params }, {
      timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS,
    });
  }

  async paperAccount(id: string, params: { limit?: number } = {}) {
    return this.call('paper_account', { strategy_id: id, ...params }, {
      timeoutMs: StrategyMarketService.READ_SURFACE_TIMEOUT_MS,
    });
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
    try {
      return await this.call('vector_indexes', params);
    } catch (error) {
      return this.degradedReadSurface('vector_indexes', error, {
        indexes: [],
        registries: [],
        items: [],
        count: 0,
      });
    }
  }

  async vectorIndexSnapshots(
    params: { index_name?: string; index_version?: string; status?: string; limit?: number } = {},
  ) {
    try {
      return await this.call('vector_index_snapshots', params);
    } catch (error) {
      return this.degradedReadSurface('vector_index_snapshots', error, {
        snapshots: [],
        items: [],
        count: 0,
      });
    }
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
    try {
      return await this.call('vector_health', params);
    } catch (error) {
      return this.degradedReadSurface('vector_health', error, {
        healthy: false,
        indexes: [],
        versions: [],
        items: [],
        count: 0,
      });
    }
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
