import { BadGatewayException } from '@nestjs/common';
import {
  buildResultContract,
  extractFreshness,
  extractPlatformMeta,
} from '../common/result-contract';
import { buildResultContractMeta } from '../common/tool-contracts';
import type {
  FundamentalCapitalDto,
  FundamentalHistoryDto,
  FundamentalOverviewDto,
  FundamentalPeersDto,
} from './fundamental.types';
import { LEGACY_FIELD_ALIASES } from './fundamental.types';

export async function getOverview(service: any, code: string): Promise<FundamentalOverviewDto> {
    const normalized = code.trim();
    const cacheKey = `fundamental:overview:${normalized}`;
    const ttlSeconds = service.cacheService.resolveTtl('fundamental.overview', service.constructor.OVERVIEW_TTL_SECONDS);
    const cached = await service.cacheService.getWithMeta(cacheKey);
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

    const financialsCall = await service.callWithArgs('get_financials', attempts);
    const valuationCall = await service.callWithArgs('get_valuation_metrics', attempts);
    let valuation = service.normalizeValuation(valuationCall.payload);

    // Fallback 1: DB 直查 stocks 表补充 pe/pb/market_cap
    if (valuation.pe == null || valuation.pb == null || valuation.marketCap == null) {
      try {
        const dbVal = await service.dbFallbackValuation(normalized);
        valuation = {
          pe: valuation.pe ?? dbVal.pe,
          pb: valuation.pb ?? dbVal.pb,
          ps: valuation.ps,
          marketCap: valuation.marketCap ?? dbVal.marketCap,
        };
      } catch (e) {
        service.logger.warn(`DB valuation fallback failed for ${normalized}: ${e}`);
      }
    }

    const financials = service.normalizeFinancials(financialsCall.payload);
    const result: FundamentalOverviewDto = {
      code: normalized,
      financials,
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
      result_contract: buildResultContract({
        summary: `${normalized} 当前 ROE ${resultValue(financials.roe)}，PE ${resultValue(valuation.pe)}x，PB ${resultValue(valuation.pb)}x。`,
        availableViews: ['summary', 'compare', 'next_step'],
        evidence: [
          { label: '股票代码', value: normalized },
          { label: 'ROE', value: resultValue(financials.roe) },
          { label: 'PE', value: resultValue(valuation.pe) },
          { label: 'PB', value: resultValue(valuation.pb) },
          { label: '市值', value: resultValue(valuation.marketCap) },
        ],
        freshness: extractFreshness({ meta: { fetchedAt: new Date().toISOString() } }, null, '基本面抓取时间'),
        platformMeta: extractPlatformMeta(
          {
            meta: {
              fetchedAt: new Date().toISOString(),
              source_chain: ['get_financials', 'get_valuation_metrics'],
            },
          },
          {
            sourceTool: 'fundamental.overview',
            referencePath: '/fundamental/overview',
            freshnessLabel: '基本面抓取时间',
          },
        ),
      }),
      contract_meta: {
        financials: buildResultContractMeta({
          canonicalTool: financialsCall.canonicalTool,
          canonicalArgs: financialsCall.canonicalArgs,
          argsMatched: financialsCall.argsMatched,
          aliasHits: financialsCall.aliasHits,
        }),
        valuation: buildResultContractMeta({
          canonicalTool: valuationCall.canonicalTool,
          canonicalArgs: valuationCall.canonicalArgs,
          argsMatched: valuationCall.argsMatched,
          aliasHits: valuationCall.aliasHits,
        }),
      },
    };

    await service.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

export async function getHistory(service: any, code: string, days = 90): Promise<FundamentalHistoryDto> {
    const normalized = code.trim();
    const safeDays = Number.isFinite(days) ? Math.min(Math.max(days, 7), 365) : 90;
    const cacheKey = `fundamental:history:${normalized}:${safeDays}`;
    const ttlSeconds = service.cacheService.resolveTtl('fundamental.history', service.constructor.HISTORY_TTL_SECONDS);
    const cached = await service.cacheService.getWithMeta(cacheKey);
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
      const historyCall = await service.callWithArgs('get_historical_valuation', attempts);
      points = service.normalizeHistory(historyCall.payload);
      argsMatched = historyCall.argsMatched;
    } catch { /* primary source failed, will try fallback */ }

    // Fallback: if points empty, build synthetic history from kline + current valuation
    if (points.length === 0) {
      try {
        points = await service.buildSyntheticHistory(normalized, safeDays);
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
      result_contract: buildResultContract({
        summary: `${normalized} ${safeDays} 天估值历史已加载，共 ${points.length} 个采样点。`,
        availableViews: ['summary', 'visual', 'next_step'],
        evidence: [
          { label: '股票代码', value: normalized },
          { label: '窗口天数', value: String(safeDays) },
          { label: '采样点', value: String(points.length) },
          { label: '最新日期', value: points.at(-1)?.date || '-' },
        ],
        riskNotes: points.length === 0 ? ['当前窗口没有可用估值历史，结果可能来自合成回退或上游缺数。'] : [],
        freshness: extractFreshness({ meta: { fetchedAt: new Date().toISOString() } }, null, '历史估值抓取时间'),
        platformMeta: extractPlatformMeta(
          {
            meta: {
              fetchedAt: new Date().toISOString(),
              source_chain: [sourceTool],
            },
          },
          {
            sourceTool,
            referencePath: '/fundamental/history',
            freshnessLabel: '历史估值抓取时间',
          },
        ),
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool: sourceTool,
        canonicalArgs: points.length > 0 && argsMatched.synthetic ? { code: normalized, days: safeDays } : argsMatched,
        argsMatched,
        aliasHits: argsMatched.synthetic ? [] : undefined,
      }),
    };

    if (points.length > 0) {
      await service.cacheService.set(cacheKey, result, ttlSeconds);
    }
    return result;
  }

export async function getCapital(service: any, code: string): Promise<FundamentalCapitalDto> {
    const normalized = code.trim();
    const cacheKey = `fundamental:capital:${normalized}`;
    const ttlSeconds = service.cacheService.resolveTtl('fundamental.capital', service.constructor.CAPITAL_TTL_SECONDS);
    const cached = await service.cacheService.getWithMeta(cacheKey);
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
    const { payload, argsMatched } = await service.callWithArgs('get_stock_capital', attempts);
    const capitalData = service.normalizeCapitalData(payload);
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
      contract_meta: buildResultContractMeta({
        canonicalTool: 'get_stock_capital',
        canonicalArgs: { code: normalized },
        argsMatched,
      }),
    };

    if (capitalData.length > 0 || totalShares != null || floatShares != null) {
      await service.cacheService.set(cacheKey, result, ttlSeconds);
    }

    return result;
  }

export async function getPeers(service: any, code: string): Promise<FundamentalPeersDto> {
    const normalized = code.trim();
    const cacheKey = `fundamental:peers:${normalized}`;
    const ttlSeconds = service.cacheService.resolveTtl('fundamental.peers', service.constructor.PEERS_TTL_SECONDS);
    const cached = await service.cacheService.getWithMeta(cacheKey);
    if (cached.value && !service.isStalePeersCache(cached.value)) {
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
    const { payload, argsMatched } = await service.callWithArgs('relative_valuation', attempts);
    const rootValue = service.unwrapRoot(payload);
    const root = service.readRecord(rootValue);
    let rawPeers = Array.isArray(rootValue)
      ? service.readRecordArray(rootValue)
      : Array.isArray(root.peers)
        ? service.readRecordArray(root.peers)
        : Array.isArray(root.items)
          ? service.readRecordArray(root.items)
          : Array.isArray(root.results)
            ? service.readRecordArray(root.results)
          : [];
    let targetMetrics = service.normalizePeerMetrics(root.target_metrics ?? root.targetMetrics);
    let normalizedPeers = rawPeers
      .map((peer: unknown) => service.normalizePeerEntry(peer))
      .filter((peer: Record<string, unknown>) => String(peer.code ?? '').trim());
    let comparison = service.readRecord(root.comparison);
    let industryStats = service.readRecord(root.industry_stats ?? root.industryStats);
    let name = String(root.name ?? '');
    let industry = String(root.industry ?? '');
    let fallbackSource: string | undefined;
    let fallbackReason: string | undefined;

    if ((root.success === false || normalizedPeers.length === 0) && service.dbService.enabled) {
      try {
        const dbFallback = await service.buildPeerFallbackFromDb(normalized);
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
        service.logger.warn(`DB peer fallback failed for ${normalized}: ${error}`);
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
      contract_meta: buildResultContractMeta({
        canonicalTool: 'relative_valuation',
        canonicalArgs: { code: normalized, metrics: ['pe', 'pb', 'ps'] },
        argsMatched,
      }),
    };

    if (result.peers.length > 0) {
      await service.cacheService.set(cacheKey, result, ttlSeconds);
}

function resultValue(value: unknown): string {
  if (value == null || value === '') return '-';
  return String(value);
}

    return result;
  }

export async function getStockInfo(service: any, code: string) {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code.trim() }, { code: code.trim() }];
    const { payload } = await service.callWithArgs('get_stock_info', attempts);
    const data = service.readRecord(service.unwrapRoot(payload));
    return {
      code: code.trim(),
      name: String(data.name ?? ''),
      industry: String(data.industry ?? ''),
      listDate: String(data.listDate ?? data.list_date ?? ''),
      totalShares: service.toNum(data.totalShares ?? data.total_shares),
      floatShares: service.toNum(data.floatShares ?? data.float_shares),
      totalMarketCap: service.toNum(data.totalMarketCap ?? data.total_market_cap),
      floatMarketCap: service.toNum(data.floatMarketCap ?? data.float_market_cap),
    };
  }

export async function getFinancialSnapshot(service: any, code: string) {
    const normalized = code.trim();
    return { code: normalized, snapshot: await service.buildFinancialRecord(normalized) };
  }

export async function getFinancialHistory(service: any, codes: string[], fields: string[], date: string) {
    const normalizedFields = fields.map((field) => LEGACY_FIELD_ALIASES[field] ?? field);
    const trimDate = date.trim();
    const data: Record<string, Record<string, unknown>> = {};

    for (const rawCode of codes) {
      const normalizedCode = rawCode.replace(/\.\w+$/, '').trim();
      if (!normalizedCode) continue;
      const snapshotData = await service.buildFinancialFallback(normalizedCode, normalizedFields);
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

export async function getF10Info(service: any, code: string) {
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
        const stockInfo = await service.getStockInfo(normalized);
        const stockInfoHasData = Object.values(stockInfo).some((value, index) => index > 0 && value != null && value !== '');
        if (stockInfoHasData) {
          Object.assign(f10, stockInfo);
          hasFallbackData = true;
          sourceChain.push('bff.getStockInfo');
        }
      } catch (fallbackError) {
        service.logger.warn(`F10 stock info fallback failed for ${normalized}: ${String(fallbackError)}`);
        const message = readProviderMessage(fallbackError);
        if (message) fallbackReasons.push(`get_stock_info: ${message}`);
      }

      try {
        const { payload } = await service.callWithArgs('get_financials', attempts);
        const financials = service.normalizeFinancials(payload);
        const financialRoot = service.readRecord(service.unwrapRoot(payload));
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
        service.logger.warn(`F10 financial fallback failed for ${normalized}: ${String(financialError)}`);
        const message = readProviderMessage(financialError);
        if (message) fallbackReasons.push(`get_financials: ${message}`);
      }

      try {
        const { payload } = await service.callWithArgs('get_valuation_metrics', attempts);
        const valuation = service.normalizeValuation(payload);
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
        service.logger.warn(`F10 valuation fallback failed for ${normalized}: ${String(valuationError)}`);
        const message = readProviderMessage(valuationError);
        if (message) fallbackReasons.push(`get_valuation_metrics: ${message}`);
      }

      try {
        const { payload } = await service.callWithArgs('get_profit_forecast', [
          { symbol: normalized },
          { stock_code: normalized },
          { code: normalized },
        ]);
        const root = service.unwrapRoot(payload);
        const rootRecord = service.readRecord(root);
        const items: Array<Record<string, unknown>> = Array.isArray(root)
          ? service.readRecordArray(root)
          : service.readRecordArray(rootRecord.items);
        const latestForecast = items.find((item: Record<string, unknown>) => Object.keys(item).length > 0);
        if (latestForecast) {
          const forecastPatch: Record<string, unknown> = {};
          const institution = String(latestForecast.institution ?? '').trim();
          const rating = String(latestForecast.rating ?? '').trim();
          const date = String(latestForecast.date ?? '').trim();
          const epsForecast = service.toNum(latestForecast.eps_forecast ?? latestForecast.epsForecast);
          const netprofitForecast = service.toNum(latestForecast.netprofit_forecast ?? latestForecast.netprofitForecast);
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
        service.logger.warn(`F10 profit forecast fallback failed for ${normalized}: ${String(forecastError)}`);
        const message = readProviderMessage(forecastError);
        if (message) fallbackReasons.push(`get_profit_forecast: ${message}`);
      }

      try {
        const { payload } = await service.callWithArgs('get_stock_capital', attempts);
        const capitalRows = service.normalizeCapitalData(payload);
        const latestCapital = [...capitalRows].reverse().find((row) => row.totalShares != null || row.floatShares != null);
        if (latestCapital) {
          if (latestCapital.totalShares != null) f10.totalShares = latestCapital.totalShares;
          if (latestCapital.floatShares != null) f10.floatShares = latestCapital.floatShares;
          hasFallbackData = true;
          sourceChain.push('bff.getStockCapital');
        }
      } catch (capitalError) {
        service.logger.warn(`F10 capital fallback failed for ${normalized}: ${String(capitalError)}`);
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

function resultValue(value: unknown): string {
  if (value == null || value === '') {
    return '-';
  }
  return String(value);
}
