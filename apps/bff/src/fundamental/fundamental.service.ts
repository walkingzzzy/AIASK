import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type FundamentalOverviewDto = {
  code: string;
  financials: NormalizedFinancials;
  valuation: NormalizedValuation;
  sourceTools: {
    financials: 'get_financials';
    valuation: 'get_valuation_metrics';
  };
  argsMatched: {
    financials: Record<string, unknown>;
    valuation: Record<string, unknown>;
  };
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
};

export type FundamentalHistoryDto = {
  code: string;
  days: number;
  points: Array<{ date: string; pe: number | null; pb: number | null; ps: number | null; close: number | null }>;
  sourceTool: 'get_historical_valuation';
  argsMatched: Record<string, unknown>;
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
};

export type NormalizedValuation = {
  pe: number | null; pb: number | null; ps: number | null; marketCap: number | null;
};
export type NormalizedFinancials = {
  roe: number | null; netProfit: number | null; revenue: number | null; debtRatio: number | null;
};

@Injectable()
export class FundamentalService {
  private static readonly OVERVIEW_TTL_SECONDS = 300;
  private static readonly HISTORY_TTL_SECONDS = 300;

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async getOverview(code: string): Promise<FundamentalOverviewDto> {
    const normalized = code.trim();
    const cacheKey = `fundamental:overview:${normalized}`;
    const ttlSeconds = this.cacheService.resolveTtl('fundamental.overview', FundamentalService.OVERVIEW_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<FundamentalOverviewDto>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const attempts: Array<Record<string, unknown>> = [
      { stock_code: normalized },
      { code: normalized },
      { symbol: normalized },
    ];

    const financialsCall = await this.callWithArgs('get_financials', attempts);
    const valuationCall = await this.callWithArgs('get_valuation_metrics', attempts);

    const result: FundamentalOverviewDto = {
      code: normalized,
      financials: this.normalizeFinancials(financialsCall.payload),
      valuation: this.normalizeValuation(valuationCall.payload),
      sourceTools: {
        financials: 'get_financials',
        valuation: 'get_valuation_metrics',
      },
      argsMatched: {
        financials: financialsCall.argsMatched,
        valuation: valuationCall.argsMatched,
      },
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
    };

    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getHistory(code: string, days = 90): Promise<FundamentalHistoryDto> {
    const normalized = code.trim();
    const safeDays = Number.isFinite(days) ? Math.min(Math.max(days, 7), 365) : 90;
    const cacheKey = `fundamental:history:${normalized}:${safeDays}`;
    const ttlSeconds = this.cacheService.resolveTtl('fundamental.history', FundamentalService.HISTORY_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<FundamentalHistoryDto>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const attempts: Array<Record<string, unknown>> = [
      { code: normalized, days: safeDays },
      { stock_code: normalized, days: safeDays },
      { symbol: normalized, days: safeDays },
    ];

    const historyCall = await this.callWithArgs('get_historical_valuation', attempts);
    const result: FundamentalHistoryDto = {
      code: normalized,
      days: safeDays,
      points: this.normalizeHistory(historyCall.payload),
      sourceTool: 'get_historical_valuation',
      argsMatched: historyCall.argsMatched,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
    };

    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getStockInfo(code: string) {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code.trim() }, { code: code.trim() }];
    const { payload } = await this.callWithArgs('get_stock_info', attempts);
    const d = (payload as any)?.data ?? payload ?? {};
    return { code: code.trim(), name: String(d.name ?? ''), industry: String(d.industry ?? ''), listDate: String(d.listDate ?? d.list_date ?? ''), totalShares: this.toNum(d.totalShares ?? d.total_shares), floatShares: this.toNum(d.floatShares ?? d.float_shares), totalMarketCap: this.toNum(d.totalMarketCap ?? d.total_market_cap), floatMarketCap: this.toNum(d.floatMarketCap ?? d.float_market_cap) };
  }

  async getFinancialSnapshot(code: string) {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code.trim() }, { code: code.trim() }];
    const { payload } = await this.callWithArgs('tdx_get_financial_snapshot', attempts);
    return { code: code.trim(), snapshot: (payload as any)?.data ?? payload ?? {} };
  }

  async getFinancialHistory(codes: string[], fields: string[], date: string) {
    const payload = await this.mcpGatewayService.callTool('tdx_get_financial_history', { stock_codes: codes, fields, date: date.trim() });
    return { date: date.trim(), data: (payload as any)?.data ?? payload ?? {} };
  }

  async getF10Info(code: string) {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code.trim() }, { code: code.trim() }];
    const { payload } = await this.callWithArgs('tdx_get_f10_info', attempts);
    return { code: code.trim(), f10: (payload as any)?.data ?? payload ?? {} };
  }

  private normalizeValuation(payload: any): NormalizedValuation {
    const d = payload?.data ?? payload ?? {};
    return {
      pe: this.toNum(d.pe_ratio ?? d.pe ?? d.PE),
      pb: this.toNum(d.pb_ratio ?? d.pb ?? d.PB),
      ps: this.toNum(d.ps_ratio ?? d.ps ?? d.PS),
      marketCap: this.toNum(d.market_cap ?? d.total_mv ?? d.marketCap),
    };
  }

  private normalizeFinancials(payload: any): NormalizedFinancials {
    const d = payload?.data ?? payload ?? {};
    return {
      roe: this.toNum(d.roe ?? d.ROE),
      netProfit: this.toNum(d.net_profit ?? d.profit ?? d.netProfit),
      revenue: this.toNum(d.revenue ?? d.operating_revenue),
      debtRatio: this.toNum(d.debt_ratio ?? d.asset_liability_ratio ?? d.debtRatio),
    };
  }

  private normalizeHistory(payload: any) {
    const root = payload?.data ?? payload ?? [];
    const list = Array.isArray(root)
      ? root
      : Array.isArray(root?.records)
        ? root.records
        : Array.isArray(root?.data)
          ? root.data
          : [];

    return list.map((it: any) => ({
      date: String(it.date ?? it.trade_date ?? it.Date ?? ''),
      pe: this.toNum(it.pe_ratio ?? it.pe ?? it.PE),
      pb: this.toNum(it.pb_ratio ?? it.pb ?? it.PB),
      ps: this.toNum(it.ps_ratio ?? it.ps ?? it.PS),
      close: this.toNum(it.close ?? it.price ?? it.Close),
    }));
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private async callWithArgs(tool: string, attempts: Array<Record<string, unknown>>) {
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcpGatewayService.callTool(tool, args);
        return { payload, argsMatched: args };
      } catch (error) {
        lastError = error;
      }
    }

    throw new BadGatewayException({
      success: false,
      message: `调用 MCP ${tool} 失败`,
      detail: lastError instanceof Error ? lastError.message : String(lastError),
    });
  }
}

