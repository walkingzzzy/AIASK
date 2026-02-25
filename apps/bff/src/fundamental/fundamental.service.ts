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
  sourceTool: string;
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

/** Map human-readable field names → TDX FN codes */
const FIELD_TO_FN: Record<string, string> = {
  eps: 'FN1',
  eps_deducted: 'FN2',
  undistributed_profit_per_share: 'FN3',
  bvps: 'FN4',
  roe: 'FN6',
  cost_profit_rate: 'FN193',
  operating_profit_rate: 'FN194',
  roe_diluted: 'FN197',
  net_profit_margin: 'FN199',
  debt_ratio: 'FN210',
  revenue: 'FN230',
  operating_profit: 'FN231',
  net_profit: 'FN232',
};
const FN_TO_FIELD: Record<string, string> = Object.fromEntries(
  Object.entries(FIELD_TO_FN).map(([k, v]) => [v, k]),
);

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
    let valuation = this.normalizeValuation(valuationCall.payload);

    // Fallback: if PE/PB still null, try F10 data (TDX has MorePE, PB_MRQ, StaticPE_TTM)
    if (valuation.pe == null || valuation.pb == null) {
      try {
        const f10 = await this.callWithArgs('tdx_get_f10_info', attempts);
        const fd = (f10.payload as any)?.data?.data ?? (f10.payload as any)?.data ?? f10.payload ?? {};
        valuation = {
          pe: valuation.pe ?? this.toNum(fd.StaticPE_TTM ?? fd.MorePE),
          pb: valuation.pb ?? this.toNum(fd.PB_MRQ),
          ps: valuation.ps,
          marketCap: valuation.marketCap,
        };
      } catch { /* F10 fallback is best-effort */ }
    }

    const result: FundamentalOverviewDto = {
      code: normalized,
      financials: this.normalizeFinancials(financialsCall.payload),
      valuation,
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

    let points: FundamentalHistoryDto['points'] = [];
    let sourceTool = 'get_historical_valuation';
    let argsMatched: Record<string, unknown> = {};

    // Primary: try get_historical_valuation
    try {
      const historyCall = await this.callWithArgs('get_historical_valuation', attempts);
      points = this.normalizeHistory(historyCall.payload);
      argsMatched = historyCall.argsMatched;
    } catch { /* primary source failed, will try fallback */ }

    // Fallback: if points empty, build synthetic history from kline + current valuation
    if (points.length === 0) {
      try {
        points = await this.buildSyntheticHistory(normalized, safeDays);
        sourceTool = 'get_kline_data+get_valuation_metrics';
        argsMatched = { code: normalized, days: safeDays, synthetic: true };
      } catch { /* fallback also failed */ }
    }

    const result: FundamentalHistoryDto = {
      code: normalized,
      days: safeDays,
      points,
      sourceTool,
      argsMatched,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
    };

    if (points.length > 0) {
      await this.cacheService.set(cacheKey, result, ttlSeconds);
    }
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
    // Map human-readable field names to TDX FN codes
    const fnFields = fields.map((f) => FIELD_TO_FN[f] ?? f);
    const trimDate = date.trim();
    // Try "00000000" (year=0, mmdd=0) for latest report, then the requested date
    const datesToTry = ['00000000', trimDate];
    let payload: any = null;
    let usedDate = trimDate;
    let hasRealData = false;
    for (const d of datesToTry) {
      try {
        payload = await this.mcpGatewayService.callTool('tdx_get_financial_history', {
          stock_codes: codes,
          fields: fnFields,
          date: d,
        });
        usedDate = d;
        const raw = (payload as any)?.data ?? payload ?? {};
        const innerData = raw.data ?? raw;
        hasRealData = Object.values(innerData).some((stockFields: any) => {
          if (!stockFields || typeof stockFields !== 'object') return false;
          return Object.values(stockFields).some((v) => v != null && v !== '--' && v !== '');
        });
        if (hasRealData) break;
      } catch { /* try next date */ }
    }

    // Fallback: if TDX financial history returned all null, use snapshot + overview data
    if (!hasRealData && codes.length > 0) {
      try {
        const code = codes[0].replace(/\.\w+$/, ''); // strip .SH/.SZ suffix
        const snapshotData = await this.buildFinancialFallback(code);
        if (snapshotData) {
          return { date: trimDate, fields, fnFields, source: 'snapshot_fallback', data: snapshotData };
        }
      } catch { /* fallback failed */ }
    }

    const raw = (payload as any)?.data ?? payload ?? {};
    const translated = this.translateFnFields(raw.data ?? raw);
    return { date: usedDate, fields, fnFields, data: translated };
  }

  async getF10Info(code: string) {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code.trim() }, { code: code.trim() }];
    const { payload } = await this.callWithArgs('tdx_get_f10_info', attempts);
    return { code: code.trim(), f10: (payload as any)?.data ?? payload ?? {} };
  }

  /**
   * Fallback: build synthetic PE/PB history from kline prices + current valuation.
   * PE_hist ≈ PE_now * (price_hist / price_now), same for PB.
   */
  private async buildSyntheticHistory(code: string, days: number) {
    const klineAttempts: Array<Record<string, unknown>> = [
      { code, period: 'daily', limit: days },
      { stock_code: code, period: 'daily', limit: days },
    ];
    const { payload: klinePayload } = await this.callWithArgs('get_kline_data', klineAttempts, 'get_kline');
    const klineRoot = (klinePayload as any)?.data ?? klinePayload ?? [];
    const klineList: any[] = Array.isArray(klineRoot)
      ? klineRoot
      : Array.isArray(klineRoot?.klines) ? klineRoot.klines
      : Array.isArray(klineRoot?.data) ? klineRoot.data : [];
    if (klineList.length === 0) return [];

    // Get current valuation
    const valAttempts: Array<Record<string, unknown>> = [
      { stock_code: code }, { code }, { symbol: code },
    ];
    let curPe: number | null = null;
    let curPb: number | null = null;
    try {
      const { payload: valPayload } = await this.callWithArgs('get_valuation_metrics', valAttempts);
      const v = this.normalizeValuation(valPayload);
      curPe = v.pe;
      curPb = v.pb;
    } catch { /* valuation unavailable */ }

    // If no current PE/PB, try F10 fallback
    if (curPe == null || curPb == null) {
      try {
        const f10 = await this.callWithArgs('tdx_get_f10_info', valAttempts);
        const fd = (f10.payload as any)?.data?.data ?? (f10.payload as any)?.data ?? f10.payload ?? {};
        curPe = curPe ?? this.toNum(fd.StaticPE_TTM ?? fd.MorePE);
        curPb = curPb ?? this.toNum(fd.PB_MRQ);
      } catch { /* best-effort */ }
    }

    const latestClose = this.toNum(
      klineList.at(-1)?.close ?? klineList.at(-1)?.Close ?? klineList.at(-1)?.price,
    );
    if (latestClose == null || latestClose === 0) return [];

    return klineList.map((it: any) => {
      const close = this.toNum(it.close ?? it.Close ?? it.price);
      const ratio = close != null && close > 0 ? close / latestClose : null;
      return {
        date: String(it.date ?? it.trade_date ?? it.Date ?? ''),
        pe: curPe != null && ratio != null ? Math.round(curPe * ratio * 100) / 100 : null,
        pb: curPb != null && ratio != null ? Math.round(curPb * ratio * 100) / 100 : null,
        ps: null,
        close,
      };
    });
  }

  /** Translate FN codes in TDX response back to human-readable field names */
  private translateFnFields(data: any): any {
    if (!data || typeof data !== 'object') return data;
    const result: Record<string, any> = {};
    for (const [stockCode, fields] of Object.entries(data)) {
      if (fields && typeof fields === 'object' && !Array.isArray(fields)) {
        const translated: Record<string, unknown> = {};
        for (const [fnKey, val] of Object.entries(fields as Record<string, unknown>)) {
          const humanKey = FN_TO_FIELD[fnKey] ?? fnKey;
          translated[humanKey] = val === '--' ? null : val;
        }
        result[stockCode] = translated;
      } else {
        result[stockCode] = fields;
      }
    }
    return result;
  }

  /** Fallback: build financial data from snapshot + overview when TDX history is unavailable */
  private async buildFinancialFallback(code: string): Promise<Record<string, Record<string, unknown>> | null> {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code }, { code }];
    const results: Record<string, unknown> = {};

    // Try financial snapshot
    try {
      const { payload } = await this.callWithArgs('tdx_get_financial_snapshot', attempts);
      const snap = (payload as any)?.data ?? payload ?? {};
      const d = snap.data ?? snap;
      if (d && typeof d === 'object') {
        for (const [k, v] of Object.entries(d)) {
          if (v != null && v !== '' && v !== '--') results[k] = v;
        }
      }
    } catch { /* best-effort */ }

    // Try get_financials for ROE, net profit, revenue
    try {
      const { payload } = await this.callWithArgs('get_financials', attempts);
      const fin = this.normalizeFinancials(payload);
      if (fin.roe != null) results['roe'] = `${fin.roe}%`;
      if (fin.netProfit != null) results['net_profit'] = fin.netProfit;
      if (fin.revenue != null) results['revenue'] = fin.revenue;
      if (fin.debtRatio != null) results['debt_ratio'] = `${fin.debtRatio}%`;
    } catch { /* best-effort */ }

    if (Object.keys(results).length === 0) return null;
    return { [code]: results };
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

  private async callWithArgs(tool: string, attempts: Array<Record<string, unknown>>, altTool?: string) {
    let lastError: unknown = null;
    const tools = altTool ? [tool, altTool] : [tool];
    for (const t of tools) {
      for (const args of attempts) {
        try {
          const payload = await this.mcpGatewayService.callTool(t, args);
          return { payload, argsMatched: args };
        } catch (error) {
          lastError = error;
        }
      }
    }

    throw new BadGatewayException({
      success: false,
      message: `调用 MCP ${tool} 失败`,
      detail: lastError instanceof Error ? lastError.message : String(lastError),
    });
  }
}

