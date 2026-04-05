import { Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type NormalizedFactorItem = {
  name: string;
  description: string;
  category: string;
  default_period?: number;
  data_dependency?: string[];
};

type IcHistoryItem = { date: string; ic_value?: number; rank_ic?: number; stock_count?: number };

@Injectable()
export class FactorService {
  private static readonly LIBRARY_TTL_SECONDS = 3600;
  private static readonly CALCULATE_FACTOR_CONCURRENCY = 4;

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async getLibrary() {
    const cacheKey = 'factor:library';
    const ttlSeconds = this.cacheService.resolveTtl('factor.library', FactorService.LIBRARY_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return {
        ...(cached.value as Record<string, unknown>),
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }

    const payload = await this.mcp.callTool('get_factor_library', {});
    const result = {
      ...this.normalizeLibrary(payload),
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds },
      },
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async calculateFactor(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const stockCodes = this.normalizeCodes(body.stock_codes);
    const sharedArgs = this.withDateRangeArgs({ factor: body.factor_name }, body);
    const concurrency = Math.min(FactorService.CALCULATE_FACTOR_CONCURRENCY, Math.max(stockCodes.length, 1));
    const results = await this.mapWithConcurrency(stockCodes, concurrency, async (code) => {
      const payload = await this.mcp.callTool('calculate_factor', { code, ...sharedArgs });
      const flat = this.flattenMcpResult(payload);
      return { stock_code: code, ...flat };
    });
    return {
      factor_name: body.factor_name,
      start_date: body.start_date ?? null,
      end_date: body.end_date ?? null,
      requested_count: stockCodes.length,
      completed_count: results.length,
      results,
    };
  }

  async calculateIc(body: { factor_name: string; stock_codes: string[] }) {
    const payload = await this.mcp.callTool('calculate_factor_ic', {
      codes: body.stock_codes,
      factor: body.factor_name,
    });
    return this.flattenMcpResult(payload);
  }

  async backtestFactor(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool(
      'backtest_factor',
      this.withDateRangeArgs({ codes: this.normalizeCodes(body.stock_codes), factor: body.factor_name }, body),
    );
    return this.flattenMcpResult(payload);
  }

  async validateOos(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool(
      'validate_factor_oos',
      this.withDateRangeArgs({ codes: this.normalizeCodes(body.stock_codes), factor: body.factor_name }, body),
    );
    return this.flattenMcpResult(payload);
  }

  async robustnessCheck(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool(
      'factor_robustness_check',
      this.withDateRangeArgs({ codes: this.normalizeCodes(body.stock_codes), factor: body.factor_name }, body),
    );
    return this.flattenMcpResult(payload);
  }

  async icHistory(params: { factor_name: string; period?: string; limit?: number }) {
    const payload = await this.callQuantManager('factor_ic_history', {
      factor_name: params.factor_name,
      period: params.period ?? '20',
      limit: params.limit ?? 60,
    });
    return payload;
  }

  async decay(params: { factor_name: string; period?: string; limit?: number }) {
    const historyResp = await this.icHistory(params);
    const root = this.flattenMcpResult(historyResp);
    const raw = Array.isArray(root.history) ? root.history : [];
    const list = raw.map((row) => {
      const record = this.asRecord(row);
      return {
        date: String(record.date ?? ''),
        ic_value: this.toNum(record.ic_value),
        rank_ic: this.toNum(record.rank_ic),
        stock_count: this.toNum(record.stock_count) ?? 0,
      };
    }) as IcHistoryItem[];
    const sorted = list.filter((r) => r.date).sort((a, b) => a.date.localeCompare(b.date));
    const absIc = sorted.map((r) => Math.abs(this.toNum(r.ic_value) ?? 0));
    const base = absIc.length ? absIc[0] || 1e-9 : 1e-9;
    const decayCurve = sorted.map((r, idx) => ({ date: r.date, value: base > 0 ? absIc[idx] / base : 0 }));

    let halfLife: number | null = null;
    for (let i = 0; i < decayCurve.length; i += 1) {
      if ((decayCurve[i]?.value ?? 0) <= 0.5) {
        halfLife = i;
        break;
      }
    }

    return {
      factor_name: params.factor_name,
      period: params.period ?? '20',
      sample_count: sorted.length,
      half_life: halfLife,
      decay_curve: decayCurve,
    };
  }

  async batchCompute(params: {
    codes: string[];
    factors?: string[];
    persist?: boolean;
    compute_ic?: boolean;
    period?: number;
  }) {
    const payload = await this.callQuantManager('batch_compute_factors', {
      codes: params.codes,
      factors: params.factors ?? ['momentum', 'value', 'quality'],
      persist: params.persist ?? true,
      compute_ic: params.compute_ic ?? true,
      period: params.period ?? 20,
    });
    return payload;
  }

  async llmFactorMining(body: {
    stock_codes?: string[];
    candidate_count?: number;
    lookback_bars?: number;
    alternative_lookback_days?: number;
    allow_fallback?: boolean;
    persist_artifact?: boolean;
    artifact_id?: string;
    dedup_mode?: string;
    dedup_high_similarity_threshold?: number;
    dedup_failure_similarity_threshold?: number;
    startup_warmup?: boolean;
    startup_warmup_force?: boolean;
    startup_warmup_limit?: number;
    startup_warmup_task_type?: string;
  }) {
    const payload = await this.callQuantManager('llm_factor_mining', {
      codes: body.stock_codes?.length ? body.stock_codes : undefined,
      candidate_count: body.candidate_count,
      lookback_bars: body.lookback_bars,
      alternative_lookback_days: body.alternative_lookback_days,
      allow_fallback: body.allow_fallback,
      persist_artifact: body.persist_artifact,
      artifact_id: body.artifact_id,
      dedup_mode: body.dedup_mode,
      dedup_high_similarity_threshold: body.dedup_high_similarity_threshold,
      dedup_failure_similarity_threshold: body.dedup_failure_similarity_threshold,
      startup_warmup: body.startup_warmup,
      startup_warmup_force: body.startup_warmup_force,
      startup_warmup_limit: body.startup_warmup_limit,
      startup_warmup_task_type: body.startup_warmup_task_type,
    });
    return this.flattenMcpResult(payload);
  }

  async candidateWorkflow(body: {
    task?: string;
    code?: string;
    stock_codes?: string[];
    artifact_id?: string;
    candidate_index?: number;
    candidate_count?: number;
    lookback_bars?: number;
    horizon_days?: number;
    max_dates?: number;
    allow_fallback?: boolean;
    persist_artifact?: boolean;
    write_memory?: boolean;
    run_scheduler_now?: boolean;
    idempotency_key?: string;
    as_of?: string;
  }) {
    const payload = await this.mcp.callTool('factor_candidate_workflow', {
      task: body.task ?? 'pipeline',
      code: body.code,
      codes: body.stock_codes?.length ? this.normalizeCodes(body.stock_codes) : undefined,
      artifact_id: body.artifact_id,
      candidate_index: body.candidate_index,
      candidate_count: body.candidate_count,
      lookback_bars: body.lookback_bars,
      horizon_days: body.horizon_days,
      max_dates: body.max_dates,
      allow_fallback: body.allow_fallback,
      persist_artifact: body.persist_artifact,
      write_memory: body.write_memory,
      run_scheduler_now: body.run_scheduler_now,
      idempotency_key: body.idempotency_key,
      as_of: body.as_of,
    });
    return this.normalizeCandidateWorkflow(payload);
  }

  async validateCandidate(body: {
    artifact_id?: string;
    candidate_index?: number;
    candidate?: Record<string, unknown>;
    stock_codes?: string[];
    lookback_bars?: number;
    horizon_days?: number;
    max_dates?: number;
    persist_artifact?: boolean;
    write_memory?: boolean;
    output_artifact_id?: string;
  }) {
    const payload = await this.callQuantManager('validate_factor_candidate', {
      artifact_id: body.artifact_id,
      candidate_index: body.candidate_index,
      candidate: body.candidate,
      codes: body.stock_codes,
      lookback_bars: body.lookback_bars,
      horizon_days: body.horizon_days,
      max_dates: body.max_dates,
      persist_artifact: body.persist_artifact,
      write_memory: body.write_memory,
      output_artifact_id: body.output_artifact_id,
    });
    return this.flattenMcpResult(payload);
  }

  async factorResearchMemory(body: {
    op?: string;
    artifact_id?: string;
    candidate?: Record<string, unknown>;
    query_text?: string;
    stock_codes?: string[];
    status?: string;
    family?: string;
    limit?: number;
  }) {
    const payload = await this.callQuantManager('factor_research_memory', {
      op: body.op ?? 'list',
      artifact_id: body.artifact_id,
      candidate: body.candidate,
      query_text: body.query_text,
      codes: body.stock_codes,
      status: body.status,
      family: body.family,
      limit: body.limit,
    });
    return this.flattenMcpResult(payload);
  }

  async factorCandidateRegistry(body: {
    op?: string;
    artifact_id?: string;
    stock_codes?: string[];
    family?: string;
    grade?: string;
    recommendation?: string;
    min_score?: number;
    only_active?: boolean;
    limit?: number;
  }) {
    const payload = await this.callQuantManager('factor_candidate_registry', {
      op: body.op ?? 'list',
      artifact_id: body.artifact_id,
      codes: body.stock_codes,
      family: body.family,
      grade: body.grade,
      recommendation: body.recommendation,
      min_score: body.min_score,
      only_active: body.only_active,
      limit: body.limit,
    });
    return this.flattenMcpResult(payload);
  }

  async replayFactorEpisode(body: {
    op?: string;
    artifact_id?: string;
    source_artifact_id?: string;
    stock_codes?: string[];
    candidate_limit?: number;
    lookback_bars?: number;
    horizon_days?: number;
    max_dates?: number;
    write_memory?: boolean;
    persist_artifact?: boolean;
    output_artifact_id?: string;
    limit?: number;
  }) {
    const payload = await this.callQuantManager('replay_factor_episode', {
      op: body.op ?? 'run',
      artifact_id: body.artifact_id,
      source_artifact_id: body.source_artifact_id,
      codes: body.stock_codes,
      candidate_limit: body.candidate_limit,
      lookback_bars: body.lookback_bars,
      horizon_days: body.horizon_days,
      max_dates: body.max_dates,
      write_memory: body.write_memory,
      persist_artifact: body.persist_artifact,
      output_artifact_id: body.output_artifact_id,
      limit: body.limit,
    });
    return this.flattenMcpResult(payload);
  }

  async schedulerStatus() {
    const payload = await this.callQuantManager('scheduler_status');
    return this.flattenMcpResult(payload);
  }

  async schedulerRunNow() {
    const payload = await this.callQuantManager('scheduler_run_now');
    return this.flattenMcpResult(payload);
  }

  async observability() {
    const sections = await Promise.allSettled([
      this.schedulerStatus(),
      this.factorCandidateRegistry({ op: 'summary', limit: 200 }),
      this.factorCandidateRegistry({ op: 'active_pool', limit: 20 }),
      this.factorResearchMemory({ op: 'stats', limit: 200 }),
      this.callQuantManager('model_registry', { op: 'summary', limit: 200 }).then((payload) =>
        this.flattenMcpResult(payload),
      ),
      this.callQuantManager('model_registry', { op: 'retrain_summary', limit: 200 }).then((payload) =>
        this.flattenMcpResult(payload),
      ),
      this.callQuantManager('model_registry', { op: 'retrain_list', limit: 5 }).then((payload) =>
        this.flattenMcpResult(payload),
      ),
    ]);

    const scheduler = this.unwrapSettledObject(sections[0], 'scheduler');
    const registrySummaryRoot = this.unwrapSettledObject(sections[1], 'registry_summary');
    const activePoolRoot = this.unwrapSettledObject(sections[2], 'active_pool');
    const memoryRoot = this.unwrapSettledObject(sections[3], 'memory_stats');
    const modelRoot = this.unwrapSettledObject(sections[4], 'model_registry_summary');
    const retrainSummaryRoot = this.unwrapSettledObject(sections[5], 'retrain_summary');
    const retrainQueueRoot = this.unwrapSettledObject(sections[6], 'retrain_queue');

    const registrySummary = this.asRecord(registrySummaryRoot.data.summary);
    const activePool = this.asRecord(activePoolRoot.data.active_pool);
    const memoryStats = this.asRecord(memoryRoot.data.stats);
    const modelRegistrySummary = this.asRecord(modelRoot.data.summary);
    const retrainSummary = this.asRecord(retrainSummaryRoot.data.summary);
    const retrainQueue = this.asRecordArray(retrainQueueRoot.data.items);
    const lastResult = this.asRecord(scheduler.data.last_result);
    const lastValidation = this.asRecord(lastResult.llm_validation);

    return {
      overview: {
        scheduler_quality_status: scheduler.data.quality_status ?? null,
        scheduler_stale: Boolean(scheduler.data.stale),
        candidate_count: this.toNum(registrySummary.count) ?? 0,
        active_count: this.toNum(registrySummary.active_count) ?? this.toNum(activePool.count) ?? 0,
        governed_active_count: this.toNum(registrySummary.governed_active_count) ?? 0,
        blocked_count: this.toNum(registrySummary.blocked_count) ?? 0,
        excluded_count: this.toNum(activePool.excluded_count) ?? 0,
        champion_count: this.toNum(modelRegistrySummary.champion_count) ?? 0,
        challenger_count: this.toNum(modelRegistrySummary.challenger_count) ?? 0,
        latest_active_candidate_updated_at: activePool.latest_active_candidate_updated_at ?? null,
        latest_blocked_candidate_updated_at: activePool.latest_blocked_candidate_updated_at ?? null,
        recent_generated_candidate_count: this.toNum(lastValidation.generated_candidate_count) ?? 0,
        recent_validated_candidate_count: this.toNum(lastValidation.validated_candidate_count) ?? 0,
        recent_validation_failed_count: this.toNum(lastValidation.validation_failed_count) ?? 0,
        recent_active_pool_count_after_run: this.toNum(lastValidation.active_pool_count_after_run) ?? 0,
        recent_governed_active_count_after_run: this.toNum(lastValidation.governed_active_count_after_run) ?? 0,
        retrain_plan_count: this.toNum(retrainSummary.count) ?? 0,
        retrain_pending_count: this.toNum(this.asRecord(retrainSummary.status_counts).planned) ?? 0,
      },
      scheduler: scheduler.data,
      recent_run: {
        last_result: lastResult,
        llm_validation: lastValidation,
      },
      registry_summary: registrySummary,
      active_pool: activePool,
      memory_stats: memoryStats,
      model_registry_summary: modelRegistrySummary,
      retrain_summary: retrainSummary,
      retrain_queue: retrainQueue,
      degraded: sections.some((section) => section.status === 'rejected'),
      errors: [
        scheduler.error,
        registrySummaryRoot.error,
        activePoolRoot.error,
        memoryRoot.error,
        modelRoot.error,
        retrainSummaryRoot.error,
        retrainQueueRoot.error,
      ].filter(Boolean),
    };
  }

  private async callQuantManager(action: string, params: Record<string, unknown> = {}) {
    return this.mcp.callTool('quant_manager', {
      action,
      params,
    });
  }

  private normalizeLibrary(payload: unknown): { factors: NormalizedFactorItem[] } {
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const list = this.asRecordArray(data.factors ?? data.data ?? root);
    return {
      factors: list.map((factor) => ({
        name: String(factor.name ?? factor.factor_name ?? ''),
        description: String(factor.description ?? factor.desc ?? ''),
        category: String(factor.category ?? factor.group ?? ''),
        default_period: this.toNum(factor.default_period) ?? 20,
        data_dependency: Array.isArray(factor.data_dependency)
          ? factor.data_dependency.map((item) => String(item))
          : ['kline'],
      })),
    };
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  /** Flatten MCP tool result: merge nested `data` object to top level */
  private flattenMcpResult(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object') return { raw: payload };
    const obj = payload as Record<string, unknown>;
    if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) {
      const { data: inner, ...rest } = obj;
      return { ...rest, ...(inner as Record<string, unknown>) };
    }
    return obj;
  }

  private normalizeCandidateWorkflow(payload: unknown): Record<string, unknown> {
    const root = this.flattenMcpResult(payload);
    const task = String(root.task ?? 'pipeline').trim().toLowerCase();
    const generation = this.readWorkflowStepData(root, 'quant_manager.llm_factor_mining');
    const validation = this.readWorkflowStepData(root, 'quant_manager.validate_factor_candidate');
    const summary = this.asRecord(root.summary);
    const artifactId =
      summary.artifact_id ??
      generation.artifact_id ??
      validation.artifact_id ??
      root.artifact_id ??
      null;
    const base = artifactId == null ? root : { ...root, artifact_id: artifactId };

    if (task === 'generate' && Object.keys(generation).length > 0) {
      return { ...base, ...generation };
    }
    if (task === 'validate' && Object.keys(validation).length > 0) {
      return { ...base, ...validation };
    }

    return {
      ...base,
      generation: Object.keys(generation).length > 0 ? generation : undefined,
      validation: Object.keys(validation).length > 0 ? validation : undefined,
    };
  }

  private readWorkflowStepData(root: Record<string, unknown>, stepName: string): Record<string, unknown> {
    const steps = Array.isArray(root.steps) ? root.steps : [];
    const matched = steps.find((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return false;
      return String((item as Record<string, unknown>).step ?? '') === stepName;
    });
    if (!matched || typeof matched !== 'object' || Array.isArray(matched)) return {};
    const output = this.asRecord((matched as Record<string, unknown>).output);
    return this.asRecord(output.data);
  }

  private unwrapPayload(payload: unknown): unknown {
    const record = this.asRecord(payload);
    return record.data !== undefined ? record.data : payload;
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

  private unwrapSettledObject(
    result: PromiseSettledResult<Record<string, unknown>>,
    section: string,
  ): { data: Record<string, unknown>; error: string | null } {
    if (result.status === 'fulfilled') {
      return { data: result.value ?? {}, error: null };
    }
    const message = result.reason instanceof Error ? result.reason.message : String(result.reason);
    return {
      data: {},
      error: `${section}: ${message}`,
    };
  }

  private normalizeCodes(codes: string[]): string[] {
    const seen = new Set<string>();
    return codes
      .map((code) => String(code ?? '').trim())
      .filter((code) => code.length > 0)
      .filter((code) => {
        if (seen.has(code)) return false;
        seen.add(code);
        return true;
      });
  }

  private withDateRangeArgs<T extends Record<string, unknown>>(
    base: T,
    body: { start_date?: string; end_date?: string },
  ): T & { start_date?: string; end_date?: string } {
    const result: T & { start_date?: string; end_date?: string } = { ...base };
    const startDate = body.start_date?.trim();
    const endDate = body.end_date?.trim();
    if (startDate) {
      result.start_date = startDate;
    }
    if (endDate) {
      result.end_date = endDate;
    }
    return result;
  }

  private async mapWithConcurrency<T, R>(
    items: T[],
    concurrency: number,
    mapper: (item: T, index: number) => Promise<R>,
  ): Promise<R[]> {
    if (items.length === 0) {
      return [];
    }

    const results = new Array<R>(items.length);
    const workerCount = Math.max(1, Math.min(concurrency, items.length));
    let nextIndex = 0;

    const workers = Array.from({ length: workerCount }, async () => {
      while (true) {
        const currentIndex = nextIndex;
        nextIndex += 1;
        if (currentIndex >= items.length) {
          return;
        }
        results[currentIndex] = await mapper(items[currentIndex], currentIndex);
      }
    });

    await Promise.all(workers);
    return results;
  }
}
