import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type NormalizedScreenResult = { stocks: Array<{ code: string; name: string; matchScore: number | null }> };
export type NormalizedSignal = { name: string; type: string; value: string; direction: string };

@Injectable()
export class TdxService {
  private static readonly SIGNALS_TTL_SECONDS = 300;

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async pushMessage(body: { message: string; stock_code?: string }) {
    const payload = await this.mcp.callTool('push_message', body);
    return { data: payload };
  }

  async pushWarn(body: { message: string; stock_code?: string }) {
    const payload = await this.mcp.callTool('push_warn', body);
    return { data: payload };
  }

  async createWatchlist(body: { name: string; stock_codes: string[] }) {
    const payload = await this.mcp.callTool('create_watchlist', body);
    return { data: payload };
  }

  async calculateIndicator(body: { code: string; indicator: string; params?: Record<string, unknown> }) {
    const payload = await this.mcp.callTool('tdx_calculate_indicator', body);
    return { data: payload };
  }

  async screenStocks(body: { formula?: string; conditions?: Record<string, unknown> }) {
    const payload = await this.mcp.callTool('tdx_screen_stocks', body);
    return { data: this.normalizeScreenResult(payload) };
  }

  async getExpertSignals(code: string) {
    const stockCode = code.trim();
    const cacheKey = `tdx:signals:${stockCode}`;
    const ttlSeconds = this.cacheService.resolveTtl('tdx.signals', TdxService.SIGNALS_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { ...cached.value as Record<string, unknown>, meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } };
    }

    const attempts: Array<Record<string, unknown>> = [
      { stock_code: stockCode },
      { code: stockCode },
    ];

    const { payload } = await this.callWithArgs('tdx_get_expert_signals', attempts);
    const result = { data: { signals: this.normalizeSignals(payload) }, meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  private normalizeScreenResult(payload: any): NormalizedScreenResult {
    const root = payload?.data ?? payload ?? {};
    const list = Array.isArray(root) ? root : Array.isArray(root?.stocks) ? root.stocks : Array.isArray(root?.data) ? root.data : [];
    return {
      stocks: list.map((s: any) => ({
        code: String(s.code ?? s.stock_code ?? s.symbol ?? ''),
        name: String(s.name ?? s.stock_name ?? ''),
        matchScore: this.toNum(s.score ?? s.match_score),
      })),
    };
  }

  private normalizeSignals(payload: any): NormalizedSignal[] {
    const root = payload?.data ?? payload ?? {};
    const list = Array.isArray(root) ? root : Array.isArray(root?.signals) ? root.signals : Array.isArray(root?.data) ? root.data : [];
    return list.map((s: any) => ({
      name: String(s.name ?? s.signal_name ?? ''),
      type: String(s.type ?? s.signal_type ?? ''),
      value: String(s.value ?? s.signal_value ?? ''),
      direction: String(s.direction ?? s.signal ?? ''),
    }));
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private async callWithArgs(primaryTool: string, attempts: Array<Record<string, unknown>>) {
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcp.callTool(primaryTool, args);
        return { payload, argsMatched: args };
      } catch (e) {
        lastError = e;
      }
    }
    throw new BadGatewayException({
      success: false,
      message: `MCP ${primaryTool} 调用失败`,
      detail: lastError instanceof Error ? lastError.message : String(lastError),
    });
  }
}
