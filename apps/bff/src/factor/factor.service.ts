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

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async getLibrary() {
    const cacheKey = 'factor:library';
    const ttlSeconds = this.cacheService.resolveTtl('factor.library', FactorService.LIBRARY_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { ...cached.value as Record<string, unknown>, meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } };
    }

    const payload = await this.mcp.callTool('get_factor_library', {});
    const result = { data: this.normalizeLibrary(payload), meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async calculateFactor(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    // calculate_factor accepts a single code + factor; call per stock and merge
    const results: unknown[] = [];
    for (const code of body.stock_codes) {
      const payload = await this.mcp.callTool('calculate_factor', { code, factor: body.factor_name });
      const flat = this.flattenMcpResult(payload);
      results.push({ stock_code: code, ...flat });
    }
    return { data: results };
  }

  async calculateIc(body: { factor_name: string; stock_codes: string[] }) {
    const payload = await this.mcp.callTool('calculate_factor_ic', { codes: body.stock_codes, factor: body.factor_name });
    return this.flattenMcpResult(payload);
  }

  async backtestFactor(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('backtest_factor', { codes: body.stock_codes, factor: body.factor_name });
    return this.flattenMcpResult(payload);
  }

  async validateOos(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('validate_factor_oos', { codes: body.stock_codes, factor: body.factor_name });
    return this.flattenMcpResult(payload);
  }

  async robustnessCheck(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('factor_robustness_check', { codes: body.stock_codes, factor: body.factor_name });
    return this.flattenMcpResult(payload);
  }

  async icHistory(params: { factor_name: string; period?: string; limit?: number }) {
    const payload = await this.callQuantManager('factor_ic_history', {
      factor_name: params.factor_name,
      period: params.period ?? '20',
      limit: params.limit ?? 60,
    });
    return { data: payload };
  }

  async decay(params: { factor_name: string; period?: string; limit?: number }) {
    const historyResp = await this.icHistory(params);
    const root = this.flattenMcpResult(historyResp?.data);
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
    const base = absIc.length ? (absIc[0] || 1e-9) : 1e-9;
    const decayCurve = sorted.map((r, idx) => ({ date: r.date, value: base > 0 ? (absIc[idx] / base) : 0 }));

    let halfLife: number | null = null;
    for (let i = 0; i < decayCurve.length; i += 1) {
      if ((decayCurve[i]?.value ?? 0) <= 0.5) { halfLife = i; break; }
    }

    return {
      data: {
        factor_name: params.factor_name,
        period: params.period ?? '20',
        sample_count: sorted.length,
        half_life: halfLife,
        decay_curve: decayCurve,
      },
    };
  }

  async batchCompute(params: { codes: string[]; factors?: string[]; persist?: boolean; compute_ic?: boolean; period?: number }) {
    const payload = await this.callQuantManager('batch_compute_factors', {
      codes: params.codes,
      factors: params.factors ?? ['momentum', 'value', 'quality'],
      persist: params.persist ?? true,
      compute_ic: params.compute_ic ?? true,
      period: params.period ?? 20,
    });
    return { data: payload };
  }

  async llmFactorMining(body: {
    stock_codes: string[];
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
      codes: body.stock_codes,
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
        data_dependency: Array.isArray(factor.data_dependency) ? factor.data_dependency.map((item) => String(item)) : ['kline'],
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
}
