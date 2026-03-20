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
  roe: number | null;
  netProfit: number | null;
  revenue: number | null;
  debtRatio: number | null;
  grossProfitMargin: number | null;
  netProfitMargin: number | null;
  operatingCashFlow: number | null;
};

/** 兼容历史财务字段编码，统一归一到可读字段名。 */
const LEGACY_FIELD_ALIASES: Record<string, string> = {
  FN1: 'eps',
  FN2: 'eps_deducted',
  FN3: 'undistributed_profit_per_share',
  FN4: 'bvps',
  FN6: 'roe',
  FN193: 'cost_profit_rate',
  FN194: 'operating_profit_rate',
  FN197: 'roe_diluted',
  FN199: 'net_profit_margin',
  FN210: 'debt_ratio',
  FN230: 'revenue',
  FN231: 'operating_profit',
  FN232: 'net_profit',
};

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
    const rootValue = this.unwrapRoot(payload);
    const root = this.readRecord(rootValue);
    let rawPeers = Array.isArray(rootValue)
      ? this.readRecordArray(rootValue)
      : Array.isArray(root.peers)
        ? this.readRecordArray(root.peers)
        : Array.isArray(root.items)
          ? this.readRecordArray(root.items)
          : Array.isArray(root.results)
            ? this.readRecordArray(root.results)
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
    const data = this.readRecord(this.unwrapRoot(payload));
    return {
      code: code.trim(),
      name: String(data.name ?? ''),
      industry: String(data.industry ?? ''),
      listDate: String(data.listDate ?? data.list_date ?? ''),
      totalShares: this.toNum(data.totalShares ?? data.total_shares),
      floatShares: this.toNum(data.floatShares ?? data.float_shares),
      totalMarketCap: this.toNum(data.totalMarketCap ?? data.total_market_cap),
      floatMarketCap: this.toNum(data.floatMarketCap ?? data.float_market_cap),
    };
  }

  async getFinancialSnapshot(code: string) {
    const normalized = code.trim();
    return { code: normalized, snapshot: await this.buildFinancialRecord(normalized) };
  }

  async getFinancialHistory(codes: string[], fields: string[], date: string) {
    const normalizedFields = fields.map((field) => LEGACY_FIELD_ALIASES[field] ?? field);
    const trimDate = date.trim();
    const data: Record<string, Record<string, unknown>> = {};

    for (const rawCode of codes) {
      const normalizedCode = rawCode.replace(/\.\w+$/, '').trim();
      if (!normalizedCode) continue;
      const snapshotData = await this.buildFinancialFallback(normalizedCode, normalizedFields);
      data[normalizedCode] = snapshotData?.[normalizedCode] ?? Object.fromEntries(
        normalizedFields.map((field) => [field, null]),
      );
    }

    return {
      date: trimDate,
      requestedFields: fields,
      fields: normalizedFields,
      source: 'aggregated_financials',
      data,
    };
  }

  async getF10Info(code: string) {
    const normalized = code.trim();
    const attempts: Array<Record<string, unknown>> = [{ stock_code: normalized }, { code: normalized }];

    const readProviderMessage = (value: unknown): string => {
      if (!value || typeof value !== 'object') return '';
      const response = (value as { response?: unknown }).response;
      if (response && typeof response === 'object') {
        const message = (response as { message?: unknown }).message;
        if (typeof message === 'string' && message.trim()) return message.trim();
      }
      const message = (value as { message?: unknown }).message;
      return typeof message === 'string' ? message.trim() : '';
    };

    const buildAggregatedProfile = async () => {
      const fallbackReasons: string[] = [];
      const sourceChain = ['bff.getF10Info'];
      const f10: Record<string, unknown> = {
        code: normalized,
        source: 'aggregated_company_profile',
        profileType: 'aggregated',
        fallbackHint: '当前页面展示的是聚合公司资料与财务摘要。',
      };
      let hasFallbackData = false;

      try {
        const stockInfo = await this.getStockInfo(normalized);
        const stockInfoHasData = Object.values(stockInfo).some((value, index) => index > 0 && value != null && value !== '');
        if (stockInfoHasData) {
          Object.assign(f10, stockInfo);
          hasFallbackData = true;
          sourceChain.push('bff.getStockInfo');
        }
      } catch (fallbackError) {
        this.logger.warn(`F10 stock info fallback failed for ${normalized}: ${String(fallbackError)}`);
        const message = readProviderMessage(fallbackError);
        if (message) fallbackReasons.push(`get_stock_info: ${message}`);
      }

      try {
        const { payload } = await this.callWithArgs('get_financials', attempts);
        const financials = this.normalizeFinancials(payload);
        const financialRoot = this.readRecord(this.unwrapRoot(payload));
        const reportDate = financialRoot?.reportDate ?? financialRoot?.report_date;
        const financialPatch: Record<string, unknown> = {};
        if (reportDate != null && String(reportDate).trim()) financialPatch.reportDate = String(reportDate).trim();
        if (financials.roe != null) financialPatch.roe = financials.roe;
        if (financials.netProfit != null) financialPatch.netProfit = financials.netProfit;
        if (financials.revenue != null) financialPatch.revenue = financials.revenue;
        if (financials.debtRatio != null) financialPatch.debtRatio = financials.debtRatio;
        if (financials.grossProfitMargin != null) financialPatch.grossProfitMargin = financials.grossProfitMargin;
        if (financials.netProfitMargin != null) financialPatch.netProfitMargin = financials.netProfitMargin;
        if (financials.operatingCashFlow != null) financialPatch.operatingCashFlow = financials.operatingCashFlow;
        if (Object.keys(financialPatch).length > 0) {
          Object.assign(f10, financialPatch);
          hasFallbackData = true;
          sourceChain.push('bff.getFinancials');
        }
      } catch (financialError) {
        this.logger.warn(`F10 financial fallback failed for ${normalized}: ${String(financialError)}`);
        const message = readProviderMessage(financialError);
        if (message) fallbackReasons.push(`get_financials: ${message}`);
      }

      try {
        const { payload } = await this.callWithArgs('get_valuation_metrics', attempts);
        const valuation = this.normalizeValuation(payload);
        const valuationPatch: Record<string, unknown> = {};
        if (valuation.pe != null) valuationPatch.pe = valuation.pe;
        if (valuation.pb != null) valuationPatch.pb = valuation.pb;
        if (valuation.ps != null) valuationPatch.ps = valuation.ps;
        if (valuation.marketCap != null && f10.totalMarketCap == null) valuationPatch.totalMarketCap = valuation.marketCap;
        if (Object.keys(valuationPatch).length > 0) {
          Object.assign(f10, valuationPatch);
          hasFallbackData = true;
          sourceChain.push('bff.getValuationMetrics');
        }
      } catch (valuationError) {
        this.logger.warn(`F10 valuation fallback failed for ${normalized}: ${String(valuationError)}`);
        const message = readProviderMessage(valuationError);
        if (message) fallbackReasons.push(`get_valuation_metrics: ${message}`);
      }

      try {
        const { payload } = await this.callWithArgs('get_profit_forecast', [
          { symbol: normalized },
          { stock_code: normalized },
          { code: normalized },
        ]);
        const root = this.unwrapRoot(payload);
        const rootRecord = this.readRecord(root);
        const items = Array.isArray(root)
          ? this.readRecordArray(root)
          : this.readRecordArray(rootRecord.items);
        const latestForecast = items.find((item) => Object.keys(item).length > 0);
        if (latestForecast) {
          const forecastPatch: Record<string, unknown> = {};
          const institution = String(latestForecast.institution ?? '').trim();
          const rating = String(latestForecast.rating ?? '').trim();
          const date = String(latestForecast.date ?? '').trim();
          const epsForecast = this.toNum(latestForecast.eps_forecast ?? latestForecast.epsForecast);
          const netprofitForecast = this.toNum(latestForecast.netprofit_forecast ?? latestForecast.netprofitForecast);
          if (date) forecastPatch.forecastDate = date;
          if (institution) forecastPatch.forecastInstitution = institution;
          if (rating) forecastPatch.forecastRating = rating;
          if (epsForecast != null) forecastPatch.epsForecast = epsForecast;
          if (netprofitForecast != null) forecastPatch.netprofitForecast = netprofitForecast;
          if (Object.keys(forecastPatch).length > 0) {
            Object.assign(f10, forecastPatch);
            hasFallbackData = true;
            sourceChain.push('bff.getProfitForecast');
          }
        }
      } catch (forecastError) {
        this.logger.warn(`F10 profit forecast fallback failed for ${normalized}: ${String(forecastError)}`);
        const message = readProviderMessage(forecastError);
        if (message) fallbackReasons.push(`get_profit_forecast: ${message}`);
      }

      try {
        const { payload } = await this.callWithArgs('get_stock_capital', attempts);
        const capitalRows = this.normalizeCapitalData(payload);
        const latestCapital = [...capitalRows].reverse().find((row) => row.totalShares != null || row.floatShares != null);
        if (latestCapital) {
          if (latestCapital.totalShares != null) f10.totalShares = latestCapital.totalShares;
          if (latestCapital.floatShares != null) f10.floatShares = latestCapital.floatShares;
          hasFallbackData = true;
          sourceChain.push('bff.getStockCapital');
        }
      } catch (capitalError) {
        this.logger.warn(`F10 capital fallback failed for ${normalized}: ${String(capitalError)}`);
        const message = readProviderMessage(capitalError);
        if (message) fallbackReasons.push(`get_stock_capital: ${message}`);
      }

      if (hasFallbackData) {
        return {
          code: normalized,
          f10: {
            ...f10,
            source_chain: Array.from(new Set(sourceChain)),
            fallback_reason: Array.from(new Set(fallbackReasons.filter(Boolean))),
          },
        };
      }

      throw new BadGatewayException({
        success: false,
        message: fallbackReasons.find(Boolean) || '公司资料暂不可用',
        code: normalized,
      });
    };

    return buildAggregatedProfile();
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
    const klineRoot = this.unwrapRoot(klinePayload);
    const klineRecord = this.readRecord(klineRoot);
    const klineList = Array.isArray(klineRoot)
      ? this.readRecordArray(klineRoot)
      : this.readRecordArray(klineRecord.klines ?? klineRecord.data);
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

    // If no current PE/PB, try overview fallback
    if (curPe == null || curPb == null) {
      try {
        const overview = await this.getOverview(code);
        curPe = curPe ?? overview.valuation.pe;
        curPb = curPb ?? overview.valuation.pb;
      } catch { /* best-effort */ }
    }

    const latestClose = this.toNum(
      klineList.at(-1)?.close ?? klineList.at(-1)?.Close ?? klineList.at(-1)?.price,
    );
    if (latestClose == null || latestClose === 0) return [];

    return klineList.map((item) => {
      const close = this.toNum(item.close ?? item.Close ?? item.price);
      const ratio = close != null && close > 0 ? close / latestClose : null;
      return {
        date: String(item.date ?? item.trade_date ?? item.Date ?? ''),
        pe: curPe != null && ratio != null ? Math.round(curPe * ratio * 100) / 100 : null,
        pb: curPb != null && ratio != null ? Math.round(curPb * ratio * 100) / 100 : null,
        ps: null,
        close,
      };
    });
  }

  private async buildFinancialFallback(
    code: string,
    fields?: string[],
  ): Promise<Record<string, Record<string, unknown>> | null> {
    const record = await this.buildFinancialRecord(code);
    const keys = Array.isArray(fields) && fields.length > 0 ? fields : Object.keys(record);
    const filtered = Object.fromEntries(keys.map((field) => [field, record[field] ?? null]));
    const hasData = Object.values(filtered).some((value) => value != null && value !== '' && value !== '--');
    if (!hasData) return null;
    return { [code]: filtered };
  }

  private async buildFinancialRecord(code: string): Promise<Record<string, unknown>> {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code }, { code }];
    const results: Record<string, unknown> = {};

    try {
      const { payload } = await this.callWithArgs('get_financials', attempts);
      const root = this.readRecord(this.unwrapRoot(payload));
      const fin = this.normalizeFinancials(payload);
      const reportDate = root.reportDate ?? root.report_date;
      const eps = this.toNum(root.eps ?? root.basic_eps ?? root.EPS ?? root.eps_ttm);
      const epsDeducted = this.toNum(root.eps_deducted ?? root.deducted_eps);
      const bvps = this.toNum(root.bvps ?? root.book_value_per_share);
      const undistributedProfitPerShare = this.toNum(
        root.undistributed_profit_per_share ?? root.retained_profit_per_share,
      );
      const operatingProfitRate = this.toNum(
        root.operating_profit_rate ?? root.op_profit_margin ?? root.operatingProfitRate,
      );
      const costProfitRate = this.toNum(root.cost_profit_rate ?? root.costProfitRate);
      const roeDiluted = this.toNum(root.roe_diluted ?? root.roeDiluted);
      const operatingProfit = this.toNum(root.operating_profit ?? root.operatingProfit);

      if (reportDate != null && String(reportDate).trim()) results.reportDate = String(reportDate).trim();
      if (eps != null) results.eps = eps;
      if (epsDeducted != null) results.eps_deducted = epsDeducted;
      if (undistributedProfitPerShare != null) results.undistributed_profit_per_share = undistributedProfitPerShare;
      if (bvps != null) results.bvps = bvps;
      if (fin.roe != null) results.roe = fin.roe;
      if (costProfitRate != null) results.cost_profit_rate = costProfitRate;
      if (operatingProfitRate != null) results.operating_profit_rate = operatingProfitRate;
      if (roeDiluted != null) results.roe_diluted = roeDiluted;
      if (fin.netProfitMargin != null) results.net_profit_margin = fin.netProfitMargin;
      if (fin.debtRatio != null) results.debt_ratio = fin.debtRatio;
      if (fin.revenue != null) results.revenue = fin.revenue;
      if (operatingProfit != null) results.operating_profit = operatingProfit;
      if (fin.netProfit != null) results.net_profit = fin.netProfit;
      if (fin.grossProfitMargin != null) results.gross_profit_margin = fin.grossProfitMargin;
      if (fin.operatingCashFlow != null) results.operating_cash_flow = fin.operatingCashFlow;
    } catch { /* best-effort */ }

    try {
      const stockInfo = await this.getStockInfo(code);
      if (stockInfo.name) results.name = stockInfo.name;
      if (stockInfo.industry) results.industry = stockInfo.industry;
      if (stockInfo.listDate) results.listDate = stockInfo.listDate;
      if (stockInfo.totalShares != null) results.totalShares = stockInfo.totalShares;
      if (stockInfo.floatShares != null) results.floatShares = stockInfo.floatShares;
      if (stockInfo.totalMarketCap != null) results.totalMarketCap = stockInfo.totalMarketCap;
      if (stockInfo.floatMarketCap != null) results.floatMarketCap = stockInfo.floatMarketCap;
    } catch { /* best-effort */ }

    return results;
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

  private normalizeValuation(payload: unknown): NormalizedValuation {
    const d = this.readRecord(this.unwrapRoot(payload));
    return {
      pe: this.toNum(d.pe_ratio ?? d.pe ?? d.PE),
      pb: this.toNum(d.pb_ratio ?? d.pb ?? d.PB),
      ps: this.toNum(d.ps_ratio ?? d.ps ?? d.PS),
      marketCap: this.toNum(d.market_cap ?? d.total_mv ?? d.marketCap),
    };
  }

  private normalizeFinancials(payload: unknown): NormalizedFinancials {
    const d = this.readRecord(this.unwrapRoot(payload));
    return {
      roe: this.toNum(d.roe ?? d.ROE),
      netProfit: this.toNum(d.net_profit ?? d.profit ?? d.netProfit),
      revenue: this.toNum(d.revenue ?? d.operating_revenue),
      debtRatio: this.toNum(d.debt_ratio ?? d.asset_liability_ratio ?? d.debtRatio),
      grossProfitMargin: this.toNum(d.gross_profit_margin ?? d.grossProfitMargin ?? d.gross_margin),
      netProfitMargin: this.toNum(d.net_profit_margin ?? d.netProfitMargin ?? d.net_margin),
      operatingCashFlow: this.toNum(d.operating_cash_flow ?? d.n_cashflow_act ?? d.operatingCashFlow),
    };
  }

  private normalizeHistory(payload: unknown) {
    const root = this.unwrapRoot(payload);
    const rootRecord = this.readRecord(root);
    const list = Array.isArray(root)
      ? this.readRecordArray(root)
      : this.readRecordArray(rootRecord.records ?? rootRecord.data);

    return list.map((item) => ({
      date: String(item.date ?? item.trade_date ?? item.Date ?? ''),
      pe: this.toNum(item.pe_ratio ?? item.pe ?? item.PE),
      pb: this.toNum(item.pb_ratio ?? item.pb ?? item.PB),
      ps: this.toNum(item.ps_ratio ?? item.ps ?? item.PS),
      close: this.toNum(item.close ?? item.price ?? item.Close),
    }));
  }

  private normalizeCapitalData(payload: unknown) {
    const root = this.unwrapRoot(payload);
    const rootRecord = this.readRecord(root);
    const list = Array.isArray(root)
      ? this.readRecordArray(root)
      : this.readRecordArray(rootRecord.capital_data ?? rootRecord.capitalData ?? rootRecord.data);

    return list.map((item) => {
      const totalShares = this.toNum(item.zgb ?? item.total_shares ?? item.totalShares);
      const floatShares = this.toNum(item.ltgb ?? item.float_shares ?? item.floatShares);
      const restrictedShares =
        totalShares != null && floatShares != null ? Math.max(0, totalShares - floatShares) : null;

      return {
        date: String(item.Date ?? item.date ?? item.report_date ?? ''),
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

  private unwrapRoot(payload: unknown): unknown {
    if (payload == null) return {};
    if (Array.isArray(payload)) return payload;
    if (payload && typeof payload === 'object') {
      const record = payload as Record<string, unknown>;
      if (record.data != null) {
        return this.unwrapRoot(record.data);
      }
      if (record.result != null) {
        return this.unwrapRoot(record.result);
      }
    }
    return payload;
  }

  private readRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
  }

  private readRecordArray(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
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
