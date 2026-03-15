import { BadGatewayException, Injectable, Logger } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import { DbService } from '../db/db.service';

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

export type FundamentalCapitalDto = {
  code: string;
  totalShares: number | null;
  total_shares: number | null;
  floatShares: number | null;
  float_shares: number | null;
  restrictedShares: number | null;
  restricted_shares: number | null;
  capitalData: Array<{
    date: string;
    totalShares: number | null;
    total_shares: number | null;
    floatShares: number | null;
    float_shares: number | null;
    restrictedShares: number | null;
    restricted_shares: number | null;
  }>;
  holders: Array<never>;
  sourceTool: 'get_stock_capital';
  argsMatched: Record<string, unknown>;
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
};

export type FundamentalPeersDto = {
  code: string;
  name: string;
  industry: string;
  peerCount: number;
  peer_count: number;
  peers: Array<Record<string, unknown>>;
  targetMetrics: Record<string, unknown>;
  target_metrics: Record<string, unknown>;
  comparison: Record<string, unknown>;
  industryStats: Record<string, unknown>;
  industry_stats: Record<string, unknown>;
  fallbackSource?: string;
  fallbackReason?: string;
  sourceTool: 'relative_valuation';
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
  private readonly logger = new Logger(FundamentalService.name);
  private static readonly OVERVIEW_TTL_SECONDS = 300;
  private static readonly HISTORY_TTL_SECONDS = 300;
  private static readonly CAPITAL_TTL_SECONDS = 300;
  private static readonly PEERS_TTL_SECONDS = 300;

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
    private readonly dbService: DbService,
  ) { }

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

    // Fallback 1: DB 直查 stocks 表补充 pe/pb/market_cap
    if (valuation.pe == null || valuation.pb == null || valuation.marketCap == null) {
      try {
        const dbVal = await this.dbFallbackValuation(normalized);
        valuation = {
          pe: valuation.pe ?? dbVal.pe,
          pb: valuation.pb ?? dbVal.pb,
          ps: valuation.ps,
          marketCap: valuation.marketCap ?? dbVal.marketCap,
        };
      } catch (e) {
        this.logger.warn(`DB valuation fallback failed for ${normalized}: ${e}`);
      }
    }

    // Fallback 2: if PE/PB still null, try F10 data (TDX has MorePE, PB_MRQ, StaticPE_TTM)
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

  async getCapital(code: string): Promise<FundamentalCapitalDto> {
    const normalized = code.trim();
    const cacheKey = `fundamental:capital:${normalized}`;
    const ttlSeconds = this.cacheService.resolveTtl('fundamental.capital', FundamentalService.CAPITAL_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<FundamentalCapitalDto>(cacheKey);
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
      { code: normalized },
      { stock_code: normalized },
      { symbol: normalized },
    ];
    const { payload, argsMatched } = await this.callWithArgs('get_stock_capital', attempts);
    const capitalData = this.normalizeCapitalData(payload);
    const latest = capitalData.at(-1) ?? null;
    const totalShares = latest?.totalShares ?? null;
    const floatShares = latest?.floatShares ?? null;
    const restrictedShares =
      totalShares != null && floatShares != null ? Math.max(0, totalShares - floatShares) : null;

    const result: FundamentalCapitalDto = {
      code: normalized,
      totalShares,
      total_shares: totalShares,
      floatShares,
      float_shares: floatShares,
      restrictedShares,
      restricted_shares: restrictedShares,
      capitalData,
      holders: [],
      sourceTool: 'get_stock_capital',
      argsMatched,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
    };

    if (capitalData.length > 0 || totalShares != null || floatShares != null) {
      await this.cacheService.set(cacheKey, result, ttlSeconds);
    }

    return result;
  }

  async getPeers(code: string): Promise<FundamentalPeersDto> {
    const normalized = code.trim();
    const cacheKey = `fundamental:peers:${normalized}`;
    const ttlSeconds = this.cacheService.resolveTtl('fundamental.peers', FundamentalService.PEERS_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<FundamentalPeersDto>(cacheKey);
    if (cached.value && !this.isStalePeersCache(cached.value)) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const attempts: Array<Record<string, unknown>> = [
      { code: normalized, metrics: ['pe', 'pb', 'ps'] },
      { code: normalized },
    ];
    const { payload, argsMatched } = await this.callWithArgs('relative_valuation', attempts);
    const root = this.unwrapRoot(payload);
    let rawPeers = Array.isArray(root.peers)
      ? root.peers
      : Array.isArray(root.items)
        ? root.items
        : Array.isArray(root.results)
          ? root.results
          : [];
    let targetMetrics = this.normalizePeerMetrics(root.target_metrics ?? root.targetMetrics);
    let normalizedPeers = rawPeers
      .map((peer: unknown) => this.normalizePeerEntry(peer))
      .filter((peer: Record<string, unknown>) => String(peer.code ?? '').trim());
    let comparison = this.readRecord(root.comparison);
    let industryStats = this.readRecord(root.industry_stats ?? root.industryStats);
    let name = String(root.name ?? '');
    let industry = String(root.industry ?? '');
    let fallbackSource: string | undefined;
    let fallbackReason: string | undefined;

    if ((root.success === false || normalizedPeers.length === 0) && this.dbService.enabled) {
      try {
        const dbFallback = await this.buildPeerFallbackFromDb(normalized);
        if (dbFallback) {
          normalizedPeers = dbFallback.peers;
          targetMetrics = dbFallback.targetMetrics;
          comparison = dbFallback.comparison;
          industryStats = dbFallback.industryStats;
          name = dbFallback.name;
          industry = dbFallback.industry;
          fallbackSource = dbFallback.fallbackSource;
          fallbackReason = typeof root.error === 'string' ? root.error : 'relative_valuation unavailable';
          rawPeers = normalizedPeers;
        }
      } catch (error) {
        this.logger.warn(`DB peer fallback failed for ${normalized}: ${error}`);
      }
    }

    if (!normalizedPeers.some((peer: Record<string, unknown>) => String(peer.code ?? '') === normalized)) {
      normalizedPeers.unshift({
        code: normalized,
        name,
        marketCap: targetMetrics.marketCap ?? null,
        market_cap: targetMetrics.marketCap ?? null,
        pe: targetMetrics.pe ?? null,
        pb: targetMetrics.pb ?? null,
        ps: targetMetrics.ps ?? null,
        roe: targetMetrics.roe ?? null,
        revenueGrowth: targetMetrics.revenueGrowth ?? null,
        revenue_growth: targetMetrics.revenueGrowth ?? null,
        profitGrowth: targetMetrics.profitGrowth ?? null,
        profit_growth: targetMetrics.profitGrowth ?? null,
        price: targetMetrics.price ?? null,
        changePct: targetMetrics.changePct ?? null,
        change_pct: targetMetrics.changePct ?? null,
        isTarget: true,
      });
    } else {
      for (const peer of normalizedPeers) {
        if (String(peer.code ?? '') === normalized) {
          peer.isTarget = true;
        }
      }
    }

    const peerCount = Number(root.peer_count ?? root.peerCount ?? (rawPeers.length || normalizedPeers.length));

    const result: FundamentalPeersDto = {
      code: normalized,
      name,
      industry,
      peerCount,
      peer_count: peerCount,
      peers: normalizedPeers.slice(0, 10),
      targetMetrics,
      target_metrics: targetMetrics,
      comparison,
      industryStats,
      industry_stats: industryStats,
      fallbackSource,
      fallbackReason,
      sourceTool: 'relative_valuation',
      argsMatched,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
    };

    if (result.peers.length > 0) {
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

  /** DB fallback: 从 stocks 表直查估值指标 */
  private async dbFallbackValuation(code: string): Promise<NormalizedValuation> {
    try {
      const res = await this.dbService.query<{ pe_ratio: number | null; pb_ratio: number | null; market_cap: number | null }>(
        `SELECT pe_ratio, pb_ratio, market_cap FROM stocks WHERE code = $1 LIMIT 1`,
        [code],
      );
      const row = res.rows[0];
      if (!row) return { pe: null, pb: null, ps: null, marketCap: null };
      return {
        pe: row.pe_ratio != null ? Number(row.pe_ratio) : null,
        pb: row.pb_ratio != null ? Number(row.pb_ratio) : null,
        ps: null,
        marketCap: row.market_cap != null ? Number(row.market_cap) : null,
      };
    } catch {
      return { pe: null, pb: null, ps: null, marketCap: null };
    }
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

  private normalizeCapitalData(payload: any) {
    const root = this.unwrapRoot(payload);
    const list = Array.isArray(root.capital_data)
      ? root.capital_data
      : Array.isArray(root.capitalData)
        ? root.capitalData
        : Array.isArray(root.data)
          ? root.data
          : Array.isArray(root)
            ? root
            : [];

    return list.map((it: any) => {
      const totalShares = this.toNum(it.zgb ?? it.total_shares ?? it.totalShares);
      const floatShares = this.toNum(it.ltgb ?? it.float_shares ?? it.floatShares);
      const restrictedShares =
        totalShares != null && floatShares != null ? Math.max(0, totalShares - floatShares) : null;

      return {
        date: String(it.Date ?? it.date ?? it.report_date ?? ''),
        totalShares,
        total_shares: totalShares,
        floatShares,
        float_shares: floatShares,
        restrictedShares,
        restricted_shares: restrictedShares,
      };
    });
  }

  private normalizePeerEntry(value: unknown): Record<string, unknown> {
    const row = this.readRecord(value);
    const marketCap = this.toNum(row.market_cap ?? row.marketCap ?? row.total_mv);
    const pe = this.toNum(row.pe ?? row.pe_ratio ?? row.PE);
    const pb = this.toNum(row.pb ?? row.pb_ratio ?? row.PB);
    const ps = this.toNum(row.ps ?? row.ps_ratio ?? row.PS);
    const roe = this.toNum(row.roe ?? row.ROE);
    const revenueGrowth = this.toNum(row.revenue_growth ?? row.revenueGrowth ?? row.revenue_yoy ?? row.rev_yoy);
    const profitGrowth = this.toNum(row.profit_growth ?? row.profitGrowth ?? row.net_yoy);
    const price = this.toNum(row.price ?? row.close);
    const changePct = this.toNum(row.change_pct ?? row.changePercent ?? row.pct_chg);

    return {
      code: String(row.code ?? row.stock_code ?? ''),
      name: String(row.name ?? row.stock_name ?? ''),
      marketCap,
      market_cap: marketCap,
      pe,
      pb,
      ps,
      roe,
      revenueGrowth,
      revenue_growth: revenueGrowth,
      profitGrowth,
      profit_growth: profitGrowth,
      price,
      changePct,
      change_pct: changePct,
    };
  }

  private normalizePeerMetrics(value: unknown) {
    const row = this.readRecord(value);
    return {
      marketCap: this.toNum(row.market_cap ?? row.marketCap ?? row.total_mv),
      pe: this.toNum(row.pe ?? row.pe_ratio ?? row.PE),
      pb: this.toNum(row.pb ?? row.pb_ratio ?? row.PB),
      ps: this.toNum(row.ps ?? row.ps_ratio ?? row.PS),
      roe: this.toNum(row.roe ?? row.ROE),
      revenueGrowth: this.toNum(row.revenue_growth ?? row.revenueGrowth ?? row.revenue_yoy ?? row.rev_yoy),
      profitGrowth: this.toNum(row.profit_growth ?? row.profitGrowth ?? row.net_yoy),
      price: this.toNum(row.price ?? row.close),
      changePct: this.toNum(row.change_pct ?? row.changePercent ?? row.pct_chg),
    };
  }

  private isStalePeersCache(value: FundamentalPeersDto) {
    const peers = Array.isArray(value.peers) ? value.peers : [];
    if (peers.length === 0) return true;
    if (peers.length > 1) return false;

    const first = this.readRecord(peers[0]);
    const hasMetrics = ['marketCap', 'market_cap', 'pe', 'pb', 'roe', 'revenueGrowth', 'profitGrowth']
      .some((key) => first[key] != null && first[key] !== '');

    return Boolean(first.isTarget) && !hasMetrics;
  }

  private async buildPeerFallbackFromDb(code: string) {
    const targetResult = await this.dbService.query<{
      code: string;
      name: string | null;
      industry: string | null;
      market_cap: number | null;
      pe: number | null;
      pb: number | null;
      roe: number | null;
      revenue_growth: number | null;
      profit_growth: number | null;
      price: number | null;
      change_pct: number | null;
    }>(
      `SELECT
         s.code,
         s.stock_name AS name,
         s.industry,
         s.market_cap,
         s.pe_ratio AS pe,
         s.pb_ratio AS pb,
         f.roe,
         f.revenue_growth,
         f.profit_growth,
         q.price,
         q.change_pct
       FROM stocks s
       LEFT JOIN LATERAL (
         SELECT roe, revenue_growth, profit_growth
         FROM financials
         WHERE code = s.code
         ORDER BY report_date DESC
         LIMIT 1
       ) f ON TRUE
       LEFT JOIN LATERAL (
         SELECT price, change_pct
         FROM stock_quotes
         WHERE code = s.code
         ORDER BY time DESC
         LIMIT 1
       ) q ON TRUE
       WHERE s.code = $1
       LIMIT 1`,
      [code],
    );
    const target = targetResult.rows[0];
    if (!target) return null;

    const peerResult = target.market_cap != null
      ? await this.dbService.query<{
          code: string;
          name: string | null;
          market_cap: number | null;
          pe: number | null;
          pb: number | null;
          roe: number | null;
          revenue_growth: number | null;
          profit_growth: number | null;
          price: number | null;
          change_pct: number | null;
        }>(
          `SELECT
             s.code,
             s.stock_name AS name,
             s.market_cap,
             s.pe_ratio AS pe,
             s.pb_ratio AS pb,
             f.roe,
             f.revenue_growth,
             f.profit_growth,
             q.price,
             q.change_pct
           FROM stocks s
           LEFT JOIN LATERAL (
             SELECT roe, revenue_growth, profit_growth
             FROM financials
             WHERE code = s.code
             ORDER BY report_date DESC
             LIMIT 1
           ) f ON TRUE
           LEFT JOIN LATERAL (
             SELECT price, change_pct
             FROM stock_quotes
             WHERE code = s.code
             ORDER BY time DESC
             LIMIT 1
           ) q ON TRUE
           WHERE s.code <> $1
           ORDER BY ABS(COALESCE(s.market_cap, 0) - $2) ASC, s.code ASC
           LIMIT 9`,
          [code, target.market_cap],
        )
      : await this.dbService.query<{
          code: string;
          name: string | null;
          market_cap: number | null;
          pe: number | null;
          pb: number | null;
          roe: number | null;
          revenue_growth: number | null;
          profit_growth: number | null;
          price: number | null;
          change_pct: number | null;
        }>(
          `SELECT
             s.code,
             s.stock_name AS name,
             s.market_cap,
             s.pe_ratio AS pe,
             s.pb_ratio AS pb,
             f.roe,
             f.revenue_growth,
             f.profit_growth,
             q.price,
             q.change_pct
           FROM stocks s
           LEFT JOIN LATERAL (
             SELECT roe, revenue_growth, profit_growth
             FROM financials
             WHERE code = s.code
             ORDER BY report_date DESC
             LIMIT 1
           ) f ON TRUE
           LEFT JOIN LATERAL (
             SELECT price, change_pct
             FROM stock_quotes
             WHERE code = s.code
             ORDER BY time DESC
             LIMIT 1
           ) q ON TRUE
           WHERE s.code <> $1
           ORDER BY s.market_cap DESC NULLS LAST, s.code ASC
           LIMIT 9`,
          [code],
        );

    const peers = [
      this.normalizePeerEntry({
        code: target.code,
        name: target.name,
        market_cap: target.market_cap,
        pe: target.pe,
        pb: target.pb,
        roe: target.roe,
        revenue_growth: target.revenue_growth,
        profit_growth: target.profit_growth,
        price: target.price,
        change_pct: target.change_pct,
        isTarget: true,
      }),
      ...peerResult.rows.map((row) => this.normalizePeerEntry(row)),
    ];

    const targetMetrics = this.normalizePeerMetrics({
      market_cap: target.market_cap,
      pe: target.pe,
      pb: target.pb,
      roe: target.roe,
      revenue_growth: target.revenue_growth,
      profit_growth: target.profit_growth,
      price: target.price,
      change_pct: target.change_pct,
    });
    const industryStats = this.buildPeerIndustryStats(peers.slice(1));
    const comparison = this.buildPeerComparison(targetMetrics, industryStats);

    return {
      name: String(target.name ?? ''),
      industry: String(target.industry ?? ''),
      targetMetrics,
      peers,
      comparison,
      industryStats,
      fallbackSource: target.market_cap != null ? 'db.market_cap_similarity' : 'db.market_cap_desc',
    };
  }

  private buildPeerIndustryStats(peers: Array<Record<string, unknown>>) {
    const stats: Record<string, unknown> = {};
    const metrics = ['pe', 'pb', 'roe', 'revenueGrowth', 'profitGrowth'] as const;

    for (const metric of metrics) {
      const values = peers
        .map((peer) => this.toNum(peer[metric]))
        .filter((value): value is number => value != null);
      if (values.length === 0) continue;

      const sorted = [...values].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      const median = sorted.length % 2 === 0
        ? (sorted[mid - 1] + sorted[mid]) / 2
        : sorted[mid];

      stats[metric] = {
        mean: Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100) / 100,
        median: Math.round(median * 100) / 100,
        min: Math.min(...values),
        max: Math.max(...values),
        count: values.length,
      };
    }

    return stats;
  }

  private buildPeerComparison(
    targetMetrics: ReturnType<FundamentalService['normalizePeerMetrics']>,
    industryStats: Record<string, unknown>,
  ) {
    const comparison: Record<string, unknown> = {};
    const metricMap: Record<string, number | null> = {
      pe: targetMetrics.pe,
      pb: targetMetrics.pb,
      roe: targetMetrics.roe,
      revenueGrowth: targetMetrics.revenueGrowth,
      profitGrowth: targetMetrics.profitGrowth,
    };

    for (const [metric, targetValue] of Object.entries(metricMap)) {
      const stat = this.readRecord(industryStats[metric]);
      const mean = this.toNum(stat.mean);
      const median = this.toNum(stat.median);
      if (targetValue == null || mean == null || median == null) continue;

      comparison[metric] = {
        target: targetValue,
        industry_mean: mean,
        industry_median: median,
        premium_to_mean: mean === 0 ? null : Math.round(((targetValue - mean) / mean) * 10_000) / 100,
        premium_to_median: median === 0 ? null : Math.round(((targetValue - median) / median) * 10_000) / 100,
      };
    }

    return comparison;
  }

  private unwrapRoot(payload: any): any {
    if (payload == null) return {};
    if (payload && typeof payload === 'object') {
      if (payload.data != null) {
        return this.unwrapRoot(payload.data);
      }
      if (payload.result != null && typeof payload.result === 'object') {
        return this.unwrapRoot(payload.result);
      }
    }
    return payload;
  }

  private readRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
  }

  private toNum(v: unknown): number | null {
    if (v === null || v === undefined || v === '') return null;
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
