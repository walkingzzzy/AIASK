import { BadGatewayException, Injectable } from '@nestjs/common';
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
import {
  buildResultContract,
  extractFreshness,
  extractPlatformMeta,
} from '../common/result-contract';
import {
  buildResultContractMeta,
  callToolWithContract,
} from '../common/tool-contracts';

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

    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('get_realtime_quote', attempts);
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

    const attempts: ToolArgs[] = [{ code: normalized, period: klinePeriod, limit: klineLimit, start_date: '', end_date: '', adjust: '' }];

    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('get_kline_data', attempts, 'get_kline');
    const kline = this.normalizeKline(payload);
    const fetchedAt = new Date().toISOString();
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
        summary: `${normalized} ${klinePeriod} K 线已加载，共 ${kline.length} 根。`,
        availableViews: ['summary', 'visual', 'next_step'],
        evidence: [
          { label: '标的', value: normalized },
          { label: '周期', value: klinePeriod },
          { label: '样本数', value: String(kline.length) },
          { label: '最新日期', value: kline.at(-1)?.date || '-' },
        ],
        freshness: extractFreshness(payload, fetchedAt, 'K线抓取时间'),
        platformMeta: extractPlatformMeta(payload, {
          sourceTool: canonicalTool,
          referencePath: '/market/kline',
          freshnessLabel: 'K线抓取时间',
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

    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('get_order_book', attempts);
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

    const [indexResults, stockResult]: [Array<NormalizedQuote | null>, Record<string, unknown>[]] = await Promise.all([
      Promise.all(indexCodes.map(c => this.getIndexQuote(c).then(r => r.quote).catch(() => null))),
      stockCodes.length > 0
        ? this.callTool('get_batch_quotes', { stock_codes: stockCodes }).then((payload) => {
            const root = this.unwrapPayload(payload);
            const data = this.asRecord(root);
            return this.asRecordArray(data.quotes ?? root);
          })
        : Promise.resolve([]),
    ]);

    const list = [
      ...indexResults.filter(Boolean),
      ...stockResult.map((quote) => this.normalizeQuote(quote)),
    ];
    return { quotes: list, count: list.length };
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
    const payload = await this.callTool('get_limit_up_statistics', args);
    const data = this.asRecord(this.unwrapPayload(payload));
    return {
      totalLimitUp: this.toNum(data.totalLimitUp ?? data.total_limit_up),
      firstBoard: this.toNum(data.firstBoard ?? data.first_board),
      secondBoard: this.toNum(data.secondBoard ?? data.second_board),
      failedBoard: this.toNum(data.failedBoard ?? data.failed_board),
      limitDown: this.toNum(data.limitDown ?? data.limit_down),
      successRate: this.toNum(data.successRate ?? data.success_rate),
      date: String(data.date ?? ''),
    };
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
    };
    if (blocks.length > 0) {
      await this.cacheService.set(cacheKey, result, ttlSeconds);
    }
    return result;
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
    const root = this.unwrapPayload(payload);
    const list = Array.isArray(root)
      ? this.asRecordArray(root)
      : this.asRecordArray(this.asRecord(root).data ?? this.asRecord(root).records ?? this.asRecord(root).items);
    return list.map((point) => ({
      timestamp: point.timestamp ? String(point.timestamp) : point.date ? String(point.date) : null,
      date: String(point.date ?? point.Date ?? point.trade_date ?? ''),
      open: Number(point.open ?? point.Open ?? 0),
      close: Number(point.close ?? point.Close ?? 0),
      low: Number(point.low ?? point.Low ?? 0),
      high: Number(point.high ?? point.High ?? 0),
      volume: Number(point.volume ?? point.vol ?? point.Volume ?? 0),
      turnover: this.toNum(point.turnover ?? point.amount ?? point.Amount),
    }));
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
  ) {
    const result = await callToolWithContract(
      primaryTool,
      attempts,
      async (name, args) => {
        const payload = await this.mcpGatewayService.callTool(name, args);
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
      const payload = await this.mcpGatewayService.callTool(name, args);
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
}
