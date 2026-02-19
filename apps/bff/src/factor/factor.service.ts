import { Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type NormalizedFactorItem = { name: string; description: string; category: string };
export type NormalizedFactorResult = { values: Record<string, number | null>; period: string };
export type NormalizedIcResult = { ic: number | null; icIr: number | null; pValue: number | null };

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
    const payload = await this.mcp.callTool('calculate_factor', body);
    return { data: payload };
  }

  async calculateIc(body: { factor_name: string; stock_codes: string[] }) {
    const payload = await this.mcp.callTool('calculate_factor_ic', body);
    return { data: payload };
  }

  async backtestFactor(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('backtest_factor', body);
    return { data: payload };
  }

  async validateOos(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('validate_factor_oos', body);
    return { data: payload };
  }

  async robustnessCheck(body: { factor_name: string; stock_codes: string[]; start_date?: string; end_date?: string }) {
    const payload = await this.mcp.callTool('factor_robustness_check', body);
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
      })),
    };
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
}
