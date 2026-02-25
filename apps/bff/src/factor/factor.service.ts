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
    return { data: this.flattenMcpResult(payload) };
  }

  async backtestFactor(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('backtest_factor', { codes: body.stock_codes, factor: body.factor_name });
    return { data: this.flattenMcpResult(payload) };
  }

  async validateOos(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('validate_factor_oos', { codes: body.stock_codes, factor: body.factor_name });
    return { data: this.flattenMcpResult(payload) };
  }

  async robustnessCheck(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('factor_robustness_check', { codes: body.stock_codes, factor: body.factor_name });
    return { data: this.flattenMcpResult(payload) };
  }

  async icHistory(params: { factor_name: string; period?: string; limit?: number }) {
    const payload = await this.mcp.callTool('quant_manager', {
      action: 'factor_ic_history',
      kwargs: JSON.stringify({ factor_name: params.factor_name, period: params.period ?? '20', limit: params.limit ?? 60 }),
    });
    return { data: payload };
  }

  async decay(params: { factor_name: string; period?: string; limit?: number }) {
    const historyResp = await this.icHistory(params);
    const root = (historyResp?.data as any)?.data ?? historyResp?.data ?? {};
    const raw = Array.isArray(root?.history) ? root.history : [];
    const list = raw.map((r: any) => ({
      date: String(r.date ?? ''),
      ic_value: this.toNum(r.ic_value),
      rank_ic: this.toNum(r.rank_ic),
      stock_count: this.toNum(r.stock_count) ?? 0,
    })) as IcHistoryItem[];
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
    const payload = await this.mcp.callTool('quant_manager', {
      action: 'batch_compute_factors',
      kwargs: JSON.stringify({ codes: params.codes, factors: params.factors ?? ['momentum', 'value', 'quality'], persist: params.persist ?? true, compute_ic: params.compute_ic ?? true, period: params.period ?? 20 }),
    });
    return { data: payload };
  }

  private normalizeLibrary(payload: any): { factors: NormalizedFactorItem[] } {
    const root = payload?.data ?? payload ?? {};
    const list = Array.isArray(root) ? root : Array.isArray(root?.factors) ? root.factors : Array.isArray(root?.data) ? root.data : [];
    return {
      factors: list.map((f: any) => ({
        name: String(f.name ?? f.factor_name ?? ''),
        description: String(f.description ?? f.desc ?? ''),
        category: String(f.category ?? f.group ?? ''),
        default_period: this.toNum(f.default_period) ?? 20,
        data_dependency: Array.isArray(f.data_dependency) ? f.data_dependency.map((x: any) => String(x)) : ['kline'],
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
}
