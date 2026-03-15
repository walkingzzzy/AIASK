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

    const attempts: ToolArgs[] = [
      { stock_code: stockCode },
      { code: stockCode },
      { symbol: stockCode },
    ];

    const { payload, argsMatched } = await this.callWithArgs('get_realtime_quote', attempts);
    const result: MarketQuoteResponseDto = {
      quote: this.normalizeQuote(payload, stockCode),
      tool: 'get_realtime_quote',
      argsTried: attempts,
      argsMatched,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
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

    const attempts: ToolArgs[] = [
      { code: normalized, period: klinePeriod, limit: klineLimit, start_date: '', end_date: '', adjust: '' },
      { stock_code: normalized, period: klinePeriod, limit: klineLimit },
    ];

    const { payload, argsMatched } = await this.callWithArgs('get_kline_data', attempts, 'get_kline');
    const result: MarketKlineResponseDto = {
      kline: this.normalizeKline(payload),
      tool: 'get_kline_data',
      argsTried: attempts,
      argsMatched,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
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

    const attempts: ToolArgs[] = [
      { stock_code: normalized },
      { code: normalized },
      { symbol: normalized },
    ];

    const { payload, argsMatched } = await this.callWithArgs('get_order_book', attempts);
    const result: MarketOrderBookResponseDto = {
      orderBook: this.normalizeOrderBook(payload, normalized),
      tool: 'get_order_book',
      argsTried: attempts,
      argsMatched,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
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
        ...(cached.value as any),
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }
    const payload = await this.callTool('get_stock_list', {});
    const root = (payload as any)?.data ?? payload ?? {};
    const stocks = Array.isArray(root?.stocks) ? root.stocks : Array.isArray(root) ? root : [];
    const result = {
      stocks: stocks.map((s: any) => ({ code: String(s.code ?? ''), name: String(s.name ?? '') })),
      count: stocks.length,
      meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
    };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  // 000001 在个股场景通常指平安银行；指数场景请走显式的 getIndexQuote / index 订阅路径。
  private static readonly INDEX_CODES = new Set(['399001', '399006', '000688', '000300', '000016', '000905']);

  async getBatchQuotes(codes: string[]) {
    const indexCodes = codes.filter(c => MarketService.INDEX_CODES.has(c));
    const stockCodes = codes.filter(c => !MarketService.INDEX_CODES.has(c));

    const [indexResults, stockResult] = await Promise.all([
      Promise.all(indexCodes.map(c => this.getIndexQuote(c).then(r => r.quote).catch(() => null))),
      stockCodes.length > 0
        ? this.callTool('get_batch_quotes', { stock_codes: stockCodes }).then(p => {
            const root = (p as any)?.data ?? (p as any)?.quotes ?? p ?? [];
            return Array.isArray(root) ? root : [];
          })
        : Promise.resolve([]),
    ]);

    const list = [
      ...indexResults.filter(Boolean),
      ...stockResult.map((q: any) => this.normalizeQuote(q)),
    ];
    return { quotes: list, count: list.length };
  }

  async getIndexBatchQuotes(codes: string[]) {
    const normalizedCodes = codes.map((code) => code.trim()).filter(Boolean);
    const quotes = await Promise.all(
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
        ...(cached.value as any),
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

  async getIndexQuote(indexCode: string) {
    const code = indexCode.trim();
    const cacheKey = `market:index-quote:${code}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.index_quote', 30);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return {
        ...(cached.value as any),
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }
    const attempts: Array<Record<string, unknown>> = [{ index_code: code }, { code }];
    const { payload } = await this.callWithArgs('get_index_quote', attempts);
    const result = {
      quote: this.normalizeQuote(payload, code),
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
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return {
      trades: list.map((t: any) => ({
        time: String(t.time ?? ''),
        price: this.toNum(t.price),
        volume: this.toNum(t.volume),
        direction: String(t.direction ?? ''),
      })),
      count: list.length,
    };
  }

  async getLimitUpStocks(date?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    const payload = await this.callTool('get_limit_up_stocks', args);
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return {
      stocks: list.map((s: any) => ({
        code: String(s.code ?? ''),
        name: String(s.name ?? ''),
        price: this.toNum(s.price),
        changePercent: this.toNum(s.changePercent ?? s.change_percent ?? s.pct_chg),
        continuousDays: this.toNum(s.continuousDays ?? s.continuous_days),
        industry: String(s.industry ?? ''),
      })),
      count: list.length,
    };
  }

  async getLimitUpStats(date?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    const payload = await this.callTool('get_limit_up_statistics', args);
    const d = (payload as any)?.data ?? payload ?? {};
    return {
      totalLimitUp: this.toNum(d.totalLimitUp ?? d.total_limit_up),
      firstBoard: this.toNum(d.firstBoard ?? d.first_board),
      secondBoard: this.toNum(d.secondBoard ?? d.second_board),
      failedBoard: this.toNum(d.failedBoard ?? d.failed_board),
      limitDown: this.toNum(d.limitDown ?? d.limit_down),
      successRate: this.toNum(d.successRate ?? d.success_rate),
      date: String(d.date ?? ''),
    };
  }

  async getMarketBlocks(blockType = 'industry', limit?: number) {
    const cacheKey = `market:blocks:${blockType}`;
    const ttlSeconds = this.cacheService.resolveTtl('market.blocks', 300);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return {
        ...(cached.value as any),
        meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } },
      };
    }
    const args: Record<string, unknown> = { block_type: blockType };
    if (limit) args.limit = limit;
    const payload = await this.callTool('get_market_blocks', args);
    const root = (payload as any)?.data ?? payload ?? {};
    const blocks = Array.isArray(root?.blocks) ? root.blocks : Array.isArray(root) ? root : [];
    const result = {
      blocks: blocks.map((b: any) => ({
        code: String(b.block_code ?? b.code ?? ''),
        name: String(b.block_name ?? b.name ?? ''),
        stockCount: this.toNum(b.stock_count ?? b.stockCount),
        avgChange: this.toNum(b.avg_change_pct ?? b.avgChange),
        leaderCode: String(b.leader_code ?? ''),
        leaderName: String(b.leader_name ?? ''),
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
    const root = (payload as any)?.data ?? payload ?? {};
    const stocks = Array.isArray(root?.stocks) ? root.stocks : Array.isArray(root) ? root : [];
    return {
      blockCode: blockCode.trim(),
      stocks: stocks.map((s: any) => ({
        code: String(s.stock_code ?? s.code ?? ''),
        name: String(s.stock_name ?? s.name ?? ''),
        price: this.toNum(s.price),
        changePercent: this.toNum(s.change_pct ?? s.changePercent),
      })),
      count: stocks.length,
    };
  }

  async searchStocks(keyword: string, limit = 20) {
    const payload = await this.callTool('search_stocks', { keyword: keyword.trim(), limit });
    const root = (payload as any)?.data ?? payload ?? {};
    const results = Array.isArray(root?.results) ? root.results : Array.isArray(root) ? root : [];
    return {
      keyword: keyword.trim(),
      results: results.map((s: any) => ({
        code: String(s.code ?? ''),
        name: String(s.name ?? ''),
        industry: String(s.industry ?? ''),
      })),
      count: results.length,
    };
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private normalizeQuote(payload: any, fallbackCode?: string): NormalizedQuote {
    const d = payload?.data ?? payload ?? {};
    const code = String(d.code ?? d.stock_code ?? d.index_code ?? d.symbol ?? fallbackCode ?? '');
    const price = this.toNum(d.price ?? d.current ?? d.close ?? d.Close);
    const changePercent = this.toNum(d.changePercent ?? d.change_percent ?? d.pct_change ?? d.pct_chg);
    const amount = this.toNum(d.amount ?? d.turnover ?? d.Amount);
    return {
      symbol: code,
      code,
      name: String(d.name ?? d.stock_name ?? d.index_name ?? ''),
      last: price,
      price,
      change: this.toNum(d.change ?? d.price_change),
      pct_change: changePercent,
      changePercent,
      change_pct: changePercent,
      volume: this.toNum(d.volume ?? d.vol ?? d.Volume),
      turnover: amount,
      amount,
      high: this.toNum(d.high ?? d.High),
      low: this.toNum(d.low ?? d.Low),
      open: this.toNum(d.open ?? d.Open),
      close: this.toNum(d.close ?? d.Close ?? d.current ?? d.price),
      prevClose: this.toNum(d.prevClose ?? d.preClose ?? d.prev_close ?? d.pre_close),
      timestamp: d.timestamp ? String(d.timestamp) : d.date ? String(d.date) : null,
    };
  }

  private normalizeKline(payload: any): NormalizedKlinePoint[] {
    const root = payload?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : Array.isArray(root?.data) ? root.data : Array.isArray(root?.records) ? root.records : [];
    return list.map((x: any) => ({
      timestamp: x.timestamp ? String(x.timestamp) : x.date ? String(x.date) : null,
      date: String(x.date ?? x.Date ?? x.trade_date ?? ''),
      open: Number(x.open ?? x.Open ?? 0),
      close: Number(x.close ?? x.Close ?? 0),
      low: Number(x.low ?? x.Low ?? 0),
      high: Number(x.high ?? x.High ?? 0),
      volume: Number(x.volume ?? x.vol ?? x.Volume ?? 0),
      turnover: this.toNum(x.turnover ?? x.amount ?? x.Amount),
    }));
  }

  private normalizeOrderBook(payload: any, fallbackCode?: string): NormalizedOrderBook {
    const d = payload?.data ?? payload ?? {};
    const mkEntries = (a: any): Array<{ price: number; volume: number }> =>
      (Array.isArray(a) ? a.slice(0, 5) : []).map((x: any) => ({
        price: Number(x.price ?? x[0] ?? 0),
        volume: Number(x.volume ?? x[1] ?? 0),
      }));
    return {
      symbol: String(d.code ?? d.stock_code ?? d.symbol ?? fallbackCode ?? ''),
      bids: mkEntries(d.bids ?? d.bid),
      asks: mkEntries(d.asks ?? d.ask),
      timestamp: d.timestamp != null ? String(d.timestamp) : d.date != null ? String(d.date) : null,
    };
  }

  private async callWithArgs(
    primaryTool: string,
    attempts: Array<Record<string, unknown>>,
    fallbackTool?: string,
  ) {
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcpGatewayService.callTool(primaryTool, args);
        return { payload, argsMatched: args };
      } catch (error) {
        lastError = error;
      }

      if (fallbackTool) {
        try {
          const payload = await this.mcpGatewayService.callTool(fallbackTool, args);
          return { payload, argsMatched: args };
        } catch (error) {
          lastError = error;
        }
      }
    }

    throw new BadGatewayException({
      success: false,
      message: `调用 MCP ${primaryTool} 失败`,
      detail: lastError instanceof Error ? lastError.message : String(lastError),
    });
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      return await this.mcpGatewayService.callTool(name, args);
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }
}
