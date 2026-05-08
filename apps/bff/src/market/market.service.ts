import { BadGatewayException, Injectable, Optional } from '@nestjs/common';
import type {
  MarketKlinePeriod,
  MarketKlineResponseDto,
  MarketOrderBookResponseDto,
  MarketQuoteResponseDto,
  NormalizedKlinePoint,
  NormalizedOrderBook,
  NormalizedQuote,
  ToolArgs,
} from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import { DbService } from '../db/db.service';
import {
  buildResultContract,
  extractFreshness,
  extractPlatformMeta,
} from '../common/result-contract';
import {
  buildResultContractMeta,
  callToolWithContract,
} from '../common/tool-contracts';
import { buildDataQuality, trustedDataQuality, unavailableDataQuality, uniqueQualityReasons } from '../common/data-quality';

@Injectable()
export class MarketService {
  private static readonly QUOTE_TTL_SECONDS = 30;
  private static readonly KLINE_TTL_SECONDS = 30;
  private static readonly ORDER_BOOK_TTL_SECONDS = 30;
  private static readonly DEFAULT_KLINE_LIMIT = 60;
  private static readonly MAX_KLINE_LIMIT = 1000;

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
    @Optional() private readonly dbService?: DbService,
  ) {}

  async getQuote(code: string): Promise<MarketQuoteResponseDto> {
    const stockCode = code.trim();
    const cacheKey = `market:quote:${stockCode}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.quote', MarketService.QUOTE_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<MarketQuoteResponseDto>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const attempts: ToolArgs[] = [{ code: stockCode }];

    let call: Awaited<ReturnType<MarketService['callWithArgs']>>;
    try {
      call = await this.callWithArgs('get_realtime_quote', attempts);
    } catch (error) {
      const fetchedAt = new Date().toISOString();
      const reason = this.summarizeQuoteFailure(error);
      return {
        quote: {
          symbol: stockCode,
          code: stockCode,
          name: '',
          last: null,
          price: null,
          change: null,
          pct_change: null,
          changePercent: null,
          change_pct: null,
          volume: null,
          turnover: null,
          amount: null,
          timestamp: null,
        },
        tool: 'get_realtime_quote',
        argsTried: attempts,
        argsMatched: {},
        meta: {
          fetchedAt,
          cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
        },
        result_contract: buildResultContract({
          summary: `${stockCode} 实时行情暂时不可用，页面已保留降级原因，未把空报价当作真实行情。`,
          status: 'unavailable',
          availableViews: ['summary', 'next_step'],
          evidence: [
            { label: '标的', value: stockCode },
            { label: '最新价', value: '-' },
            { label: '涨跌幅', value: '-' },
          ],
          riskNotes: [reason],
          freshness: { updatedAt: fetchedAt, label: '行情降级时间' },
          platformMeta: {
            sourceTool: 'get_realtime_quote',
            referencePath: '/market/quote',
            sourceChain: ['get_realtime_quote'],
            degraded: true,
            fallbackReason: ['quote_unavailable', reason],
          },
        }),
        contract_meta: buildResultContractMeta({
          canonicalTool: 'get_realtime_quote',
          canonicalArgs: attempts[0],
          argsMatched: {},
          aliasHits: [],
        }),
        data_quality: unavailableDataQuality('get_realtime_quote', reason, {
          emptyReason: '实时行情上游暂时不可用，未返回可验证价格',
          qualityFlags: ['quote_unavailable'],
        }),
      };
    }
    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = call;
    const quote = this.normalizeQuote(payload, stockCode);
    const fetchedAt = new Date().toISOString();
    const result: MarketQuoteResponseDto = {
      quote,
      tool: 'get_realtime_quote',
      argsTried: attempts,
      argsMatched,
      meta: {
        fetchedAt,
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
      result_contract: buildResultContract({
        summary: `${quote.name || quote.code || stockCode} 最新价 ${quote.price ?? '-'}，涨跌幅 ${quote.changePercent ?? '-'}%。`,
        availableViews: ['summary', 'visual', 'next_step'],
        evidence: [
          { label: '标的', value: quote.name || quote.code || stockCode },
          { label: '最新价', value: quote.price == null ? '-' : String(quote.price) },
          { label: '涨跌幅', value: quote.changePercent == null ? '-' : `${quote.changePercent}%` },
          { label: '成交量', value: quote.volume == null ? '-' : String(quote.volume) },
        ],
        freshness: extractFreshness(payload, fetchedAt, '行情抓取时间'),
        platformMeta: extractPlatformMeta(payload, {
          sourceTool: 'get_realtime_quote',
          referencePath: '/market/quote',
          freshnessLabel: '行情抓取时间',
        }),
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool,
        canonicalArgs,
        argsMatched,
        aliasHits,
      }),
      data_quality: this.buildQuoteQuality('get_realtime_quote', quote),
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getKline(
    code: string,
    period: MarketKlinePeriod | string,
    limit?: number,
  ): Promise<MarketKlineResponseDto> {
    const normalized = code.trim();
    const klinePeriod = this.normalizeKlinePeriod(period);
    const klineLimit = this.normalizeKlineLimit(limit);
    const cacheKey = `market:kline:${normalized}:${klinePeriod}:${klineLimit}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.kline', MarketService.KLINE_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<MarketKlineResponseDto>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const attempts: ToolArgs[] = [{ code: normalized, period: klinePeriod, limit: klineLimit }];

    let call: Awaited<ReturnType<MarketService['callWithArgs']>>;
    try {
      call = await this.callWithArgs('get_kline', attempts, 'get_kline_data', {
        timeoutMs: 20_000,
        retryOnTransportError: false,
      });
    } catch (error) {
      const fetchedAt = new Date().toISOString();
      const reason = this.describeError(error);
      const dbRows = await this.loadKlineFromDb(normalized, klinePeriod, klineLimit).catch(() => []);
      if (dbRows.length > 0) {
        const fallbackReason = this.summarizeKlineFallbackReasons([reason]);
        const { points: kline, qualityWarnings } = this.normalizeKlineWithQuality(dbRows, klineLimit);
        const stalenessWarnings = this.buildKlineStalenessWarnings(kline);
        const platformMeta = {
          sourceTool: 'db.get_klines',
          referencePath: '/market/kline',
          sourceChain: ['get_kline', 'get_kline_data', 'db.get_klines'],
          degraded: true,
          fallbackReason: fallbackReason.length > 0 ? fallbackReason : ['K 线上游响应较慢，已使用本地历史数据。'],
          freshnessLabel: 'K线抓取时间',
        };
        const riskNotes = uniqueQualityReasons([platformMeta.fallbackReason, qualityWarnings, stalenessWarnings]);
        const result: MarketKlineResponseDto = {
          kline,
          tool: 'get_kline_data',
          argsTried: attempts,
          argsMatched: { code: normalized, period: klinePeriod, limit: klineLimit, fallback: 'db.get_klines' },
          meta: {
            fetchedAt,
            cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
          },
          result_contract: buildResultContract({
            summary: `${normalized} ${klinePeriod} K 线已从本地历史数据加载，共 ${kline.length} 根。`,
            status: 'degraded',
            availableViews: ['summary', 'visual', 'next_step'],
            evidence: [
              { label: '标的', value: normalized },
              { label: '周期', value: klinePeriod },
              { label: '样本数', value: String(kline.length) },
              { label: '最新日期', value: kline.at(-1)?.date || '-' },
            ],
            riskNotes,
            freshness: { updatedAt: fetchedAt, label: 'K线抓取时间' },
            platformMeta,
          }),
          contract_meta: buildResultContractMeta({
            canonicalTool: 'db.get_klines',
            canonicalArgs: { code: normalized, period: klinePeriod, limit: klineLimit },
            argsMatched: { code: normalized, period: klinePeriod, limit: klineLimit },
            aliasHits: [],
          }),
          data_quality: this.buildKlineQuality('db.get_klines', kline.length, [...qualityWarnings, ...stalenessWarnings], platformMeta),
        };
        await this.cacheService.set(cacheKey, result, Math.min(ttlSeconds, 60));
        return result;
      }
      const displayReason = this.summarizeKlineUnavailableReason(reason);
      return {
        kline: [],
        tool: 'get_kline_data',
        argsTried: attempts,
        argsMatched: {},
        meta: {
          fetchedAt,
          cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
        },
        result_contract: buildResultContract({
          summary: `${normalized} ${klinePeriod} K 线暂时不可用，页面已展示降级说明，未把空图表当作真实 K 线。`,
          status: 'unavailable',
          availableViews: ['summary', 'next_step'],
          evidence: [
            { label: '标的', value: normalized },
            { label: '周期', value: klinePeriod },
            { label: '样本数', value: '0' },
          ],
          riskNotes: [displayReason],
          freshness: { updatedAt: fetchedAt, label: 'K线降级时间' },
          platformMeta: {
            sourceTool: 'get_kline_data',
            referencePath: '/market/kline',
            sourceChain: ['get_kline_data', 'get_kline'],
            degraded: true,
            fallbackReason: [displayReason],
          },
        }),
        contract_meta: buildResultContractMeta({
          canonicalTool: 'get_kline_data',
          canonicalArgs: attempts[0],
          argsMatched: {},
          aliasHits: [],
        }),
        data_quality: unavailableDataQuality('get_kline_data', displayReason, {
          emptyReason: 'K线行情上游暂时不可用，未返回可验证交易日数据',
          qualityFlags: ['kline_unavailable'],
        }),
      };
    }
    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = call;
    const { points: kline, qualityWarnings } = this.normalizeKlineWithQuality(payload, klineLimit);
    const fetchedAt = new Date().toISOString();
    const rawPlatformMeta = extractPlatformMeta(payload, {
      sourceTool: canonicalTool,
      referencePath: '/market/kline',
      freshnessLabel: 'K线抓取时间',
    });
    const fallbackReason = this.summarizeKlineFallbackReasons(rawPlatformMeta.fallbackReason ?? []);
    const platformMeta = {
      ...rawPlatformMeta,
      degraded: fallbackReason.length > 0,
      fallbackReason,
    };
    const klineStatus = kline.length <= 0 ? 'empty' : platformMeta.degraded ? 'degraded' : 'ready';
    const stalenessWarnings = this.buildKlineStalenessWarnings(kline);
    const riskNotes = uniqueQualityReasons([fallbackReason, qualityWarnings, stalenessWarnings]);
    const result: MarketKlineResponseDto = {
      kline,
      tool: 'get_kline_data',
      argsTried: attempts,
      argsMatched,
      meta: {
        fetchedAt,
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
      result_contract: buildResultContract({
        summary: kline.length > 0
          ? `${normalized} ${klinePeriod} K 线已加载，共 ${kline.length} 根。`
          : `${normalized} ${klinePeriod} K 线返回空结果，页面不会把空图表当作真实走势。`,
        status: klineStatus,
        availableViews: kline.length > 0 ? ['summary', 'visual', 'next_step'] : ['summary', 'next_step'],
        evidence: [
          { label: '标的', value: normalized },
          { label: '周期', value: klinePeriod },
          { label: '样本数', value: String(kline.length) },
          { label: '最新日期', value: kline.at(-1)?.date || '-' },
        ],
        riskNotes,
        freshness: extractFreshness(payload, fetchedAt, 'K线抓取时间'),
        platformMeta,
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool,
        canonicalArgs,
        argsMatched,
        aliasHits,
      }),
      data_quality: this.buildKlineQuality(canonicalTool, kline.length, [...qualityWarnings, ...stalenessWarnings], platformMeta),
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getOrderBook(code: string): Promise<MarketOrderBookResponseDto> {
    const normalized = code.trim();
    const cacheKey = `market:order-book:${normalized}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.order_book', MarketService.ORDER_BOOK_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<MarketOrderBookResponseDto>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const attempts: ToolArgs[] = [{ code: normalized }];

    let call: Awaited<ReturnType<MarketService['callWithArgs']>>;
    try {
      call = await this.callWithArgs('get_order_book', attempts);
    } catch (error) {
      const fetchedAt = new Date().toISOString();
      const reason = this.summarizeOrderBookFailure(error);
      return {
        orderBook: {
          symbol: normalized,
          bids: [],
          asks: [],
          timestamp: null,
        },
        tool: 'get_order_book',
        argsTried: attempts,
        argsMatched: {},
        meta: {
          fetchedAt,
          cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
        },
        result_contract: buildResultContract({
          summary: `${normalized} 五档盘口暂时不可用，页面已保留为空盘口并展示原因。`,
          status: 'unavailable',
          availableViews: ['summary', 'next_step'],
          evidence: [
            { label: '标的', value: normalized },
            { label: '买盘档数', value: '0' },
            { label: '卖盘档数', value: '0' },
          ],
          riskNotes: [reason],
          freshness: { updatedAt: fetchedAt, label: '盘口降级时间' },
          platformMeta: {
            sourceTool: 'get_order_book',
            referencePath: '/market/order-book',
            sourceChain: ['get_order_book'],
            degraded: true,
            fallbackReason: ['order_book_unavailable', reason],
          },
        }),
        contract_meta: buildResultContractMeta({
          canonicalTool: 'get_order_book',
          canonicalArgs: attempts[0],
          argsMatched: {},
          aliasHits: [],
        }),
        data_quality: unavailableDataQuality('get_order_book', reason, {
          emptyReason: '盘口上游暂时不可用',
          qualityFlags: ['order_book_unavailable'],
        }),
      };
    }
    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = call;
    const orderBook = this.normalizeOrderBook(payload, normalized);
    const fetchedAt = new Date().toISOString();
    const result: MarketOrderBookResponseDto = {
      orderBook,
      tool: 'get_order_book',
      argsTried: attempts,
      argsMatched,
      meta: {
        fetchedAt,
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
      result_contract: buildResultContract({
        summary: `${normalized} 五档盘口已加载，买盘 ${orderBook.bids.length} 档，卖盘 ${orderBook.asks.length} 档。`,
        availableViews: ['summary', 'compare', 'next_step'],
        evidence: [
          { label: '标的', value: normalized },
          { label: '买盘档数', value: String(orderBook.bids.length) },
          { label: '卖盘档数', value: String(orderBook.asks.length) },
          { label: '盘口时间', value: orderBook.timestamp || '-' },
        ],
        freshness: extractFreshness(payload, fetchedAt, '盘口抓取时间'),
        platformMeta: extractPlatformMeta(payload, {
          sourceTool: canonicalTool,
          referencePath: '/market/order-book',
          freshnessLabel: '盘口抓取时间',
        }),
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool,
        canonicalArgs,
        argsMatched,
        aliasHits,
      }),
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  private normalizeKlinePeriod(period: string): MarketKlinePeriod {
    const value = period.trim();
    if (value === 'weekly' || value === 'monthly') {
      return value;
    }
    return 'daily';
  }

  private normalizeKlineLimit(limit?: number) {
    if (!Number.isFinite(limit)) {
      return MarketService.DEFAULT_KLINE_LIMIT;
    }
    return Math.max(1, Math.min(MarketService.MAX_KLINE_LIMIT, Math.floor(limit ?? MarketService.DEFAULT_KLINE_LIMIT)));
  }

  async getStockList() {
    const cacheKey = 'market:stock-list';
    const ttlSeconds = this.cacheService.resolveTtl('market.stock_list', 3600);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return {
        ...(cached.value as Record<string, unknown>),
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }
    const payload = await this.callTool('get_stock_list', {});
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const stocks = this.asRecordArray(data.stocks ?? root);
    const result = {
      stocks: stocks.map((stock) => ({ code: String(stock.code ?? ''), name: String(stock.name ?? '') })),
      count: stocks.length,
      meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  // 000001 在个股场景通常指平安银行；指数场景请走显式的 getIndexQuote / index 订阅路径。
  private static readonly INDEX_CODES = new Set(['399001', '399006', '000688', '000300', '000016', '000905']);

  private static readonly INDEX_QUOTE_SOURCE = 'get_index_quote' as const;

  async getBatchQuotes(codes: string[]) {
    const indexCodes = codes.filter(c => MarketService.INDEX_CODES.has(c));
    const stockCodes = codes.filter(c => !MarketService.INDEX_CODES.has(c));

    const [indexResults, stockResult]: [Array<NormalizedQuote | null>, { quotes: Record<string, unknown>[]; warnings: string[] }] = await Promise.all([
      Promise.all(indexCodes.map(c => this.getIndexQuote(c).then(r => r.quote).catch(() => null))),
      stockCodes.length > 0
        ? this.callTool('get_batch_quotes', { stock_codes: stockCodes }).then((payload) => {
            const root = this.unwrapPayload(payload);
            const data = this.asRecord(root);
            return { quotes: this.asRecordArray(data.quotes ?? root), warnings: [] };
          }).catch(async (error) => {
            const settled = await Promise.allSettled(stockCodes.map((code) => this.getQuote(code)));
            return {
              quotes: settled
                .filter((item): item is PromiseFulfilledResult<MarketQuoteResponseDto> => item.status === 'fulfilled')
                .map((item) => item.value.quote as unknown as Record<string, unknown>),
              warnings: [
                `get_batch_quotes failed; returned ${settled.filter((item) => item.status === 'fulfilled').length}/${stockCodes.length} individual quotes`,
                error instanceof Error ? error.message : String(error),
              ],
            };
          })
        : Promise.resolve({ quotes: [], warnings: [] }),
    ]);

    const list = [
      ...indexResults.filter(Boolean),
      ...stockResult.quotes.map((quote) => this.normalizeQuote(quote)),
    ];
    return { quotes: list, count: list.length, warnings: stockResult.warnings };
  }

  async getIndexBatchQuotes(codes: string[]) {
    const normalizedCodes = codes.map((code) => code.trim()).filter(Boolean);
    const quotes: Array<NormalizedQuote | null> = await Promise.all(
      normalizedCodes.map((code) => this.getIndexQuote(code).then((result) => result.quote).catch(() => null)),
    );
    const list = quotes.filter((quote): quote is NormalizedQuote => Boolean(quote));
    return { quotes: list, count: list.length };
  }

  async getMinuteKline(code: string, period = '5m', limit = 300) {
    const stockCode = code.trim();
    const cacheKey = `market:minute-kline:${stockCode}:${period}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.minute_kline', 30);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return {
        ...(cached.value as Record<string, unknown>),
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }
    const attempts: Array<Record<string, unknown>> = [
      { stock_code: stockCode, period, limit },
      { code: stockCode, period, limit },
    ];
    const { payload } = await this.callWithArgs('get_minute_kline', attempts);
    const points = this.normalizeKline(payload);
    const result = {
      kline: points,
      meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getIndexQuote(indexCode: string): Promise<{
    quote: NormalizedQuote;
    sourceTool: typeof MarketService.INDEX_QUOTE_SOURCE;
    meta: { fetchedAt: string; cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number } };
  }> {
    const code = indexCode.trim();
    const cacheKey = `market:index-quote:${code}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.index_quote', 30);
    const cached = await this.cacheService.getWithMeta<{
      quote: NormalizedQuote;
      sourceTool: typeof MarketService.INDEX_QUOTE_SOURCE;
      meta: { fetchedAt: string; cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number } };
    }>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        sourceTool: MarketService.INDEX_QUOTE_SOURCE,
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }
    const attempts: Array<Record<string, unknown>> = [{ index_code: code }, { code }];
    const { payload } = await this.callWithArgs('get_index_quote', attempts);
    const result = {
      quote: this.normalizeQuote(payload, code),
      sourceTool: MarketService.INDEX_QUOTE_SOURCE,
      meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getTradeDetails(code: string, limit = 20) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [
      { stock_code: stockCode, limit },
      { code: stockCode, limit },
    ];
    const { payload } = await this.callWithArgs('get_trade_details', attempts);
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      trades: list.map((trade) => ({
        time: String(trade.time ?? ''),
        price: this.toNum(trade.price),
        volume: this.toNum(trade.volume),
        direction: String(trade.direction ?? ''),
      })),
      count: list.length,
    };
  }

  async getLimitUpStocks(date?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    const payload = await this.callTool('get_limit_up_stocks', args);
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      stocks: list.map((stock) => ({
        code: String(stock.code ?? ''),
        name: String(stock.name ?? ''),
        price: this.toNum(stock.price),
        changePercent: this.toNum(stock.changePercent ?? stock.change_percent ?? stock.pct_chg),
        continuousDays: this.toNum(stock.continuousDays ?? stock.continuous_days),
        industry: String(stock.industry ?? ''),
      })),
      count: list.length,
    };
  }

  async getLimitUpStats(date?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    try {
      const payload = await this.callTool('get_limit_up_statistics', args);
      const data = this.asRecord(this.unwrapPayload(payload));
      const result = {
        totalLimitUp: this.toNum(data.totalLimitUp ?? data.total_limit_up),
        firstBoard: this.toNum(data.firstBoard ?? data.first_board),
        secondBoard: this.toNum(data.secondBoard ?? data.second_board),
        failedBoard: this.toNum(data.failedBoard ?? data.failed_board),
        limitDown: this.toNum(data.limitDown ?? data.limit_down),
        successRate: this.toNum(data.successRate ?? data.success_rate),
        date: String(data.date ?? ''),
      };
      const sampleCount = Object.values(result).some((value) => value != null && value !== '') ? 1 : 0;
      return {
        ...result,
        data_quality: sampleCount > 0
          ? trustedDataQuality('get_limit_up_statistics', sampleCount, result.date || null)
          : buildDataQuality({
            status: 'empty',
            reasons: ['limit_up_statistics_empty'],
            emptyReason: '涨停统计接口没有返回有效数据',
            sources: [{ name: 'get_limit_up_statistics', status: 'empty', sampleCount: 0 }],
            qualityFlags: ['limit_up_statistics_empty'],
          }),
      };
    } catch (error) {
      const reason = this.describeError(error);
      return {
        totalLimitUp: null,
        firstBoard: null,
        secondBoard: null,
        failedBoard: null,
        limitDown: null,
        successRate: null,
        date: date?.trim() ?? '',
        degraded: true,
        fallback_used: false,
        fallback_reason: reason,
        data_quality: unavailableDataQuality('get_limit_up_statistics', reason, {
          emptyReason: '涨停统计上游不可用，未返回可验证数据',
          qualityFlags: ['limit_up_statistics_unavailable'],
        }),
      };
    }
  }

  async getMarketBlocks(blockType = 'industry', limit?: number) {
    const cacheKey = `market:blocks:${blockType}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.blocks', 300);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return {
        ...(cached.value as Record<string, unknown>),
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }
    const args: Record<string, unknown> = { block_type: blockType };
    if (limit) args.limit = limit;
    try {
      const payload = await this.callTool('get_market_blocks', args);
      const root = this.unwrapPayload(payload);
      const data = this.asRecord(root);
      const blocks = this.asRecordArray(data.blocks ?? root);
      const result = {
        blocks: blocks.map((block) => ({
          code: String(block.block_code ?? block.code ?? ''),
          name: String(block.block_name ?? block.name ?? ''),
          stockCount: this.toNum(block.stock_count ?? block.stockCount),
          avgChange: this.toNum(block.avg_change_pct ?? block.avgChange),
          leaderCode: String(block.leader_code ?? ''),
          leaderName: String(block.leader_name ?? ''),
        })),
        count: blocks.length,
        blockType,
        meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
        data_quality: blocks.length > 0
          ? trustedDataQuality('get_market_blocks', blocks.length)
          : buildDataQuality({
            status: 'empty',
            reasons: ['market_blocks_empty'],
            emptyReason: '板块行情接口没有返回有效板块数据',
            sources: [{ name: 'get_market_blocks', status: 'empty', sampleCount: 0 }],
            qualityFlags: ['market_blocks_empty'],
          }),
      };
      if (blocks.length > 0) {
        await this.cacheService.set(cacheKey, result, ttlSeconds);
      }
      return result;
    } catch (error) {
      const reason = this.describeError(error);
      return {
        blocks: [],
        count: 0,
        blockType,
        degraded: true,
        fallback_used: false,
        fallback_reason: reason,
        meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
        data_quality: unavailableDataQuality('get_market_blocks', reason, {
          emptyReason: '板块行情上游不可用，未返回可验证数据',
          qualityFlags: ['market_blocks_unavailable'],
        }),
      };
    }
  }

  async getBlockStocks(blockCode: string) {
    const payload = await this.callTool('get_block_stocks', { block_code: blockCode.trim() });
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const stocks = this.asRecordArray(data.stocks ?? root);
    return {
      blockCode: blockCode.trim(),
      stocks: stocks.map((stock) => ({
        code: String(stock.stock_code ?? stock.code ?? ''),
        name: String(stock.stock_name ?? stock.name ?? ''),
        price: this.toNum(stock.price),
        changePercent: this.toNum(stock.change_pct ?? stock.changePercent),
      })),
      count: stocks.length,
    };
  }

  async searchStocks(keyword: string, limit = 20) {
    const normalizedKeyword = keyword.trim();
    let results: Record<string, unknown>[] = [];

    try {
      const payload = await this.callTool('search_stocks', { keyword: normalizedKeyword, limit });
      const root = this.unwrapPayload(payload);
      const data = this.asRecord(root);
      results = this.asRecordArray(data.results ?? root);
    } catch {
      const stockList = await this.getStockList();
      const loweredKeyword = normalizedKeyword.toLowerCase();
      const fallbackResults = Array.isArray((stockList as { stocks?: Array<Record<string, unknown>> }).stocks)
        ? (stockList as { stocks: Array<Record<string, unknown>> }).stocks
        : [];
      results = fallbackResults
        .filter((stock) => [stock.code, stock.name, stock.industry].some((value) => String(value ?? '').toLowerCase().includes(loweredKeyword)))
        .slice(0, limit)
        .map((stock) => ({
          code: stock.code,
          name: stock.name,
          industry: stock.industry ?? '',
        }));
    }

    return {
      keyword: normalizedKeyword,
      results: results.map((stock) => ({
        code: String(stock.code ?? ''),
        name: String(stock.name ?? ''),
        industry: String(stock.industry ?? ''),
      })),
      count: results.length,
    };
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private normalizeQuote(payload: unknown, fallbackCode?: string): NormalizedQuote {
    const data = this.asRecord(this.unwrapPayload(payload));
    const code = String(data.code ?? data.stock_code ?? data.index_code ?? data.symbol ?? fallbackCode ?? '');
    const price = this.toNum(data.price ?? data.current ?? data.close ?? data.Close);
    const changePercent = this.toNum(data.changePercent ?? data.change_percent ?? data.pct_change ?? data.pct_chg);
    const amount = this.toNum(data.amount ?? data.turnover ?? data.Amount);
    return {
      symbol: code,
      code,
      name: String(data.name ?? data.stock_name ?? data.index_name ?? ''),
      last: price,
      price,
      change: this.toNum(data.change ?? data.price_change),
      pct_change: changePercent,
      changePercent,
      change_pct: changePercent,
      volume: this.toNum(data.volume ?? data.vol ?? data.Volume),
      turnover: amount,
      amount,
      high: this.toNum(data.high ?? data.High),
      low: this.toNum(data.low ?? data.Low),
      open: this.toNum(data.open ?? data.Open),
      close: this.toNum(data.close ?? data.Close ?? data.current ?? data.price),
      prevClose: this.toNum(data.prevClose ?? data.preClose ?? data.prev_close ?? data.pre_close),
      timestamp: data.timestamp ? String(data.timestamp) : data.date ? String(data.date) : null,
    };
  }

  private normalizeKline(payload: unknown): NormalizedKlinePoint[] {
    return this.normalizeKlineWithQuality(payload).points;
  }

  private buildQuoteQuality(sourceName: string, quote: NormalizedQuote) {
    const hasPrice = quote.price != null && Number.isFinite(Number(quote.price));
    if (hasPrice) {
      return trustedDataQuality(sourceName, 1, quote.timestamp ?? null);
    }
    return buildDataQuality({
      status: 'empty',
      reasons: ['quote_price_missing'],
      emptyReason: '实时行情没有返回有效价格',
      sources: [{ name: sourceName, status: 'empty', freshness: quote.timestamp ?? null, sampleCount: 0 }],
      qualityFlags: ['quote_price_missing'],
    });
  }

  private buildKlineQuality(
    sourceName: string,
    sampleCount: number,
    qualityWarnings: string[],
    platformMeta: { degraded?: boolean; fallbackReason?: string[]; freshnessLabel?: string | null },
  ) {
    const reasons = uniqueQualityReasons([qualityWarnings, platformMeta.fallbackReason]);
    if (sampleCount <= 0) {
      return buildDataQuality({
        status: 'empty',
        reasons: [...reasons, 'kline_empty'],
        emptyReason: 'K线接口没有返回有效交易日数据',
        qualityFlags: qualityWarnings,
        sources: [{ name: sourceName, status: 'empty', sampleCount: 0 }],
      });
    }
    if (platformMeta.degraded) {
      return buildDataQuality({
        status: 'partial',
        reasons: reasons.length > 0 ? reasons : ['K 线使用备用数据源，当前样本仍可查看'],
        sources: [{ name: sourceName, status: 'partial', sampleCount }],
      });
    }
    const unresolvedWarnings = qualityWarnings.filter((warning) => !this.isKlineNormalizationWarning(warning));
    if (unresolvedWarnings.length > 0) {
      return buildDataQuality({
        status: 'partial',
        reasons: unresolvedWarnings,
        sources: [{ name: sourceName, status: 'partial', sampleCount }],
      });
    }
    return trustedDataQuality(sourceName, sampleCount);
  }

  private summarizeKlineFallbackReasons(reasons: string[]) {
    return uniqueQualityReasons(reasons.map((reason) => {
      if (/total_timeout_exceeded|using db\.get_klines|after total timeout|request timed out|timeout/i.test(reason)) {
        return 'K 线实时主链路响应较慢，已自动切换到备用历史数据。';
      }
      return reason;
    }));
  }

  private summarizeKlineUnavailableReason(reason: string) {
    if (/total_timeout_exceeded|after total timeout|request timed out|timeout|mcp error -32001/i.test(reason)) {
      return 'K 线实时主链路响应较慢，且本地历史数据暂未命中；本次未返回可验证交易日数据。';
    }
    return 'K 线行情上游暂时不可用，本次未返回可验证交易日数据。';
  }

  private summarizeQuoteFailure(error: unknown) {
    const reason = this.describeError(error);
    if (/request timed out|timeout|mcp error -32001/i.test(reason)) {
      return '实时行情服务当前响应较慢，本次未返回可验证报价。';
    }
    return '实时行情服务暂时不可用，本次未返回可验证报价。';
  }

  private summarizeOrderBookFailure(error: unknown) {
    const reason = this.describeError(error);
    if (/request timed out|timeout|mcp error -32001/i.test(reason)) {
      return '盘口服务当前响应较慢，本次未返回可验证盘口数据。';
    }
    return '盘口服务暂时不可用，本次未返回可验证盘口数据。';
  }

  private isKlineNormalizationWarning(reason: string) {
    return /^K线已去重 \d+ 条同日重复记录$/.test(reason)
      || /^K线成交量已统一为手，转换 \d+ 条记录$/.test(reason)
      || /^K线忽略 \d+ 条疑似换手率的 turnover 字段$/.test(reason);
  }

  private buildKlineStalenessWarnings(points: NormalizedKlinePoint[]) {
    const latestDate = points.at(-1)?.date?.slice(0, 10);
    if (!latestDate) return [];
    const latestTime = new Date(`${latestDate}T00:00:00.000Z`).getTime();
    if (!Number.isFinite(latestTime)) return [];
    const now = Date.now();
    const ageDays = Math.floor((now - latestTime) / 86400000);
    if (ageDays > 10) {
      return [`K 线备用历史数据最新交易日为 ${latestDate}，可能滞后于实时行情。`];
    }
    return [];
  }

  private normalizeKlineWithQuality(
    payload: unknown,
    limit = MarketService.MAX_KLINE_LIMIT,
  ): { points: NormalizedKlinePoint[]; qualityWarnings: string[] } {
    const root = this.unwrapPayload(payload);
    const list = Array.isArray(root)
      ? this.asRecordArray(root)
      : this.asRecordArray(this.asRecord(root).data ?? this.asRecord(root).records ?? this.asRecord(root).items);
    const qualityWarnings: string[] = [];
    const byDate = new Map<string, { point: NormalizedKlinePoint; score: number }>();
    let duplicateCount = 0;
    let convertedVolumeCount = 0;
    let ignoredTurnoverCount = 0;

    for (const rawPoint of list) {
      const date = String(rawPoint.date ?? rawPoint.Date ?? rawPoint.trade_date ?? rawPoint.timestamp ?? '').slice(0, 10);
      if (!date) continue;
      const close = this.toFinite(rawPoint.close ?? rawPoint.Close);
      const volumeRaw = this.toFinite(rawPoint.volume ?? rawPoint.vol ?? rawPoint.Volume);
      const turnoverRaw = this.toFinite(rawPoint.amount ?? rawPoint.Amount ?? rawPoint.turnover);
      const turnover = turnoverRaw != null && Math.abs(turnoverRaw) >= 1_000_000 ? turnoverRaw : null;
      if (turnoverRaw != null && turnover == null && Math.abs(turnoverRaw) > 0) {
        ignoredTurnoverCount += 1;
      }
      const volume = this.normalizeKlineVolume(volumeRaw, close, turnover);
      if (volumeRaw != null && volume != null && Math.abs(volumeRaw - volume) > 1) {
        convertedVolumeCount += 1;
      }
      const point: NormalizedKlinePoint = {
        timestamp: rawPoint.timestamp ? String(rawPoint.timestamp) : date,
        date,
        open: this.toFinite(rawPoint.open ?? rawPoint.Open) ?? 0,
        close: close ?? 0,
        low: this.toFinite(rawPoint.low ?? rawPoint.Low) ?? 0,
        high: this.toFinite(rawPoint.high ?? rawPoint.High) ?? 0,
        volume: volume ?? 0,
        turnover,
      };
      const validOhlc = [point.open, point.close, point.low, point.high].every((value) => Number.isFinite(value) && value > 0);
      const score = (validOhlc ? 4 : 0) + (turnover != null ? 2 : 0) + (volume != null && volume > 0 ? 1 : 0);
      const previous = byDate.get(date);
      if (previous) {
        duplicateCount += 1;
      }
      if (!previous || score >= previous.score) {
        byDate.set(date, { point, score });
      }
    }

    if (duplicateCount > 0) {
      qualityWarnings.push(`K线已去重 ${duplicateCount} 条同日重复记录`);
    }
    if (convertedVolumeCount > 0) {
      qualityWarnings.push(`K线成交量已统一为手，转换 ${convertedVolumeCount} 条记录`);
    }
    if (ignoredTurnoverCount > 0) {
      qualityWarnings.push(`K线忽略 ${ignoredTurnoverCount} 条疑似换手率的 turnover 字段`);
    }

    const points = Array.from(byDate.values())
      .map((item) => item.point)
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-Math.max(1, Math.min(limit, MarketService.MAX_KLINE_LIMIT)));
    return { points, qualityWarnings };
  }

  private async loadKlineFromDb(code: string, period: MarketKlinePeriod, limit: number): Promise<Record<string, unknown>[]> {
    if (!this.dbService?.enabled) return [];
    const rowLimit = period === 'daily'
      ? limit
      : Math.min(Math.max(limit * (period === 'weekly' ? 7 : 31), limit), 5000);
    const result = await this.dbService.query<{
      time: Date | string;
      code: string;
      open: number | string;
      high: number | string;
      low: number | string;
      close: number | string;
      volume: number | string;
      amount: number | string | null;
      turnover: number | string | null;
      change_pct: number | string | null;
    }>(
      `SELECT time, code, open, high, low, close, volume, amount, turnover, change_pct
         FROM (
           SELECT time, code, open, high, low, close, volume, amount, turnover, change_pct
            FROM kline_1d
            WHERE code = $1
            ORDER BY time DESC
            LIMIT $2
         ) recent_bars
        ORDER BY time ASC`,
      [code, rowLimit],
    );
    const dailyRows = result.rows.map((row) => ({
      date: this.formatDbKlineDate(row.time),
      code: row.code,
      open: this.toNum(row.open),
      high: this.toNum(row.high),
      low: this.toNum(row.low),
      close: this.toNum(row.close),
      volume: this.toNum(row.volume),
      amount: this.toNum(row.amount),
      turnover: this.toNum(row.turnover),
      change_pct: this.toNum(row.change_pct),
      source: 'timescaledb',
    }));
    const normalizedDailyRows = this.normalizeKlineWithQuality(dailyRows, rowLimit).points.map((point) => ({
      ...point,
      amount: point.turnover ?? null,
      source: 'timescaledb',
    }));
    if (period === 'daily') {
      return normalizedDailyRows.slice(-limit);
    }
    return this.aggregateDbKlineRows(normalizedDailyRows, period).slice(-limit);
  }

  private aggregateDbKlineRows(rows: Record<string, unknown>[], period: Exclude<MarketKlinePeriod, 'daily'>) {
    const grouped = new Map<string, Record<string, unknown>[]>();
    for (const row of rows) {
      const date = String(row.date ?? '').slice(0, 10);
      if (!date) continue;
      const key = period === 'weekly' ? this.isoWeekKey(date) : date.slice(0, 7);
      const group = grouped.get(key) ?? [];
      group.push(row);
      grouped.set(key, group);
    }
    return Array.from(grouped.values()).map((group) => {
      const sorted = group.slice().sort((a, b) => String(a.date ?? '').localeCompare(String(b.date ?? '')));
      const first = sorted[0] ?? {};
      const last = sorted.at(-1) ?? {};
      const highs = sorted.map((row) => this.toNum(row.high)).filter((value): value is number => value != null);
      const lows = sorted.map((row) => this.toNum(row.low)).filter((value): value is number => value != null);
      const sum = (field: string) => {
        const values = sorted.map((row) => this.toNum(row[field])).filter((value): value is number => value != null);
        return values.length > 0 ? values.reduce((total, value) => total + value, 0) : null;
      };
      const amount = sum('amount') ?? sum('turnover');
      return {
        date: String(last.date ?? ''),
        code: String(last.code ?? first.code ?? ''),
        open: this.toNum(first.open),
        high: highs.length > 0 ? Math.max(...highs) : null,
        low: lows.length > 0 ? Math.min(...lows) : null,
        close: this.toNum(last.close),
        volume: sum('volume'),
        amount,
        turnover: amount,
        source: 'timescaledb',
        period,
      };
    });
  }

  private isoWeekKey(dateText: string) {
    const date = new Date(`${dateText}T00:00:00.000Z`);
    if (Number.isNaN(date.getTime())) return dateText;
    const day = date.getUTCDay() || 7;
    date.setUTCDate(date.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
    const week = Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
    return `${date.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
  }

  private formatDbKlineDate(value: Date | string): string {
    if (value instanceof Date) {
      return value.toISOString().slice(0, 10);
    }
    return String(value ?? '').slice(0, 10);
  }

  private toFinite(value: unknown): number | null {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  private normalizeKlineVolume(volume: number | null, close: number | null, turnover: number | null): number | null {
    if (volume == null) return null;
    if (close == null || close <= 0 || turnover == null || turnover <= 0) return volume;
    const estimatedShares = turnover / close;
    if (estimatedShares <= 0) return volume;
    const shareDiff = Math.abs(volume - estimatedShares) / estimatedShares;
    if (shareDiff <= 0.3) {
      return Math.round(volume / 100);
    }
    return volume;
  }

  private normalizeOrderBook(payload: unknown, fallbackCode?: string): NormalizedOrderBook {
    const data = this.asRecord(this.unwrapPayload(payload));
    const mkEntries = (value: unknown): Array<{ price: number; volume: number }> =>
      (Array.isArray(value) ? value.slice(0, 5) : []).map((entry) => {
        const record = this.asRecord(entry);
        const tuple = Array.isArray(entry) ? entry : [];
        return {
          price: Number(record.price ?? tuple[0] ?? 0),
          volume: Number(record.volume ?? tuple[1] ?? 0),
        };
      });
    return {
      symbol: String(data.code ?? data.stock_code ?? data.symbol ?? fallbackCode ?? ''),
      bids: mkEntries(data.bids ?? data.bid),
      asks: mkEntries(data.asks ?? data.ask),
      timestamp: data.timestamp != null ? String(data.timestamp) : data.date != null ? String(data.date) : null,
    };
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
    return value
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      const message = payload.trim();
      return /error executing tool|validation error|failed|exception/i.test(message) ? message : null;
    }
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const record = payload as Record<string, unknown>;
    if (record.success === false && typeof record.error === 'string' && record.error.trim()) {
      return record.error;
    }
    if (record.success === false && typeof record.message === 'string' && record.message.trim()) {
      return record.message;
    }
    if (record.success === false && record.error && typeof record.error === 'object') {
      const nested = record.error as Record<string, unknown>;
      if (typeof nested.message === 'string' && nested.message.trim()) {
        return nested.message;
      }
    }
    return null;
  }

  private async callWithArgs(
    primaryTool: string,
    attempts: Array<Record<string, unknown>>,
    fallbackTool?: string,
    options: { timeoutMs?: number; retryOnTransportError?: boolean } = {},
  ) {
    const result = await callToolWithContract(
      primaryTool,
      attempts,
      async (name, args) => {
        const payload = await this.mcpGatewayService.callTool(name, args, {
          retryOnTransportError: options.retryOnTransportError ?? true,
          timeoutMs: options.timeoutMs,
        });
        const toolError = this.extractToolError(payload);
        if (toolError) {
          throw new Error(toolError);
        }
        return payload;
      },
      fallbackTool ? [fallbackTool] : [],
    );
    return {
      payload: result.payload,
      argsMatched: result.argsMatched,
      canonicalArgs: result.canonicalArgs,
      aliasHits: result.aliasHits,
      canonicalTool: result.canonicalTool,
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      const payload = await this.mcpGatewayService.callTool(name, args, { retryOnTransportError: true });
      const toolError = this.extractToolError(payload);
      if (toolError) {
        throw new Error(toolError);
      }
      return payload;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private describeError(error: unknown) {
    if (error instanceof BadGatewayException) {
      const response = error.getResponse();
      if (typeof response === 'object' && response && 'detail' in response) {
        const detail = String((response as { detail?: unknown }).detail ?? '').trim();
        if (detail) return detail;
      }
    }
    return error instanceof Error ? error.message : String(error);
  }
}
