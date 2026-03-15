import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type NormalizedFlowItem = {
  date: string; name: string; netInflow: number | null; mainInflow: number | null;
  mainOutflow: number | null; retailInflow: number | null; retailOutflow: number | null;
  changePercent?: number | null;
};

@Injectable()
export class FundFlowService {
  private static readonly STOCK_TTL_SECONDS = 60;
  private static readonly SECTOR_TTL_SECONDS = 120;
  private static readonly CONCEPT_TTL_SECONDS = 120;
  private static readonly NORTH_TTL_SECONDS = 120;

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async getStockFundFlow(code: string) {
    const stockCode = code.trim();
    const cacheKey = `fund-flow:stock:${stockCode}`;
    const ttlSeconds = this.cacheService.resolveTtl('fund-flow.stock', FundFlowService.STOCK_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { ...cached.value as Record<string, unknown>, meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } };
    }

    const attempts: Array<Record<string, unknown>> = [
      { stock_code: stockCode },
      { code: stockCode },
      { symbol: stockCode },
    ];

    const { payload } = await this.callWithArgs('get_stock_fund_flow', attempts);
    const d = (payload as any)?.data ?? payload ?? {};
    // MCP returns a single flat object, not an array — wrap it
    const flows = Array.isArray(d) ? this.normalizeFlows(payload) : [{
      date: new Date().toISOString().slice(0, 10),
      name: String(d.name ?? ''),
      netInflow: this.toNum(d.mainNetInflow ?? d.main_net_inflow ?? d.net_inflow),
      mainInflow: this.toNum(d.mainNetInflow ?? d.main_net_inflow),
      mainOutflow: null,
      retailInflow: this.toNum(d.smallNetInflow ?? d.small_net_inflow),
      retailOutflow: null,
    }];
    const result = { data: { flows }, meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getSectorFundFlow() {
    const cacheKey = 'fund-flow:sector';
    const ttlSeconds = this.cacheService.resolveTtl('fund-flow.sector', FundFlowService.SECTOR_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { ...cached.value as Record<string, unknown>, meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } };
    }

    const payload = await this.mcp.callTool('get_sector_fund_flow', {});
    const result = { data: { flows: this.normalizeFlows(payload) }, meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getConceptFundFlow() {
    const cacheKey = 'fund-flow:concept';
    const ttlSeconds = this.cacheService.resolveTtl('fund-flow.concept', FundFlowService.CONCEPT_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { ...cached.value as Record<string, unknown>, meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } };
    }

    const payload = await this.mcp.callTool('get_concept_fund_flow', {});
    const result = { data: { flows: this.normalizeFlows(payload) }, meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } };
    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async getNorthFund() {
    const cacheKey = 'fund-flow:north';
    const ttlSeconds = this.cacheService.resolveTtl('fund-flow.north', FundFlowService.NORTH_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta(cacheKey);
    if (cached.value) {
      return { ...cached.value as Record<string, unknown>, meta: { fetchedAt: '', cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds } } };
    }

    const payload = await this.mcp.callTool('get_north_fund', {});
    const flows = this.normalizeFlows(payload);
    const result = { data: { flows }, meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } } };
    if (flows.length > 0) {
      await this.cacheService.set(cacheKey, result, ttlSeconds);
    }
    return result;
  }

  async getDragonTiger(date?: string, code?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    if (code) args.stock_code = code.trim();
    const payload = await this.mcp.callTool('get_dragon_tiger', args);
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { data: { items: list.map((x: any) => {
      const reason = x.reason == null || String(x.reason) === 'nan' ? '' : String(x.reason);
      return { code: String(x.code ?? ''), name: String(x.name ?? ''), closePrice: this.toNum(x.closePrice ?? x.close_price ?? x.price), changePercent: this.toNum(x.changePercent ?? x.change_percent), reason, buyAmount: this.toNum(x.buyAmount ?? x.buy_amount), sellAmount: this.toNum(x.sellAmount ?? x.sell_amount), netAmount: this.toNum(x.netAmount ?? x.net_amount) };
    }) } };
  }

  async getMarginData(code?: string, days = 30) {
    const args: Record<string, unknown> = { days };
    if (code) args.stock_code = code.trim();
    const payload = await this.mcp.callTool('get_margin_data', args);
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { data: { items: list.map((x: any) => ({ date: String(x.date ?? ''), code: String(x.code ?? ''), name: String(x.name ?? ''), marginBalance: this.toNum(x.marginBalance ?? x.margin_balance), marginBuy: this.toNum(x.marginBuy ?? x.margin_buy), shortBalance: this.toNum(x.shortBalance ?? x.short_balance), totalBalance: this.toNum(x.totalBalance ?? x.total_balance) })) } };
  }

  async getMarginRanking(topN = 20, sortBy = 'balance') {
    const payload = await this.mcp.callTool('get_margin_ranking', { top_n: topN, sort_by: sortBy });
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { data: { items: list.map((x: any) => ({ code: String(x.code ?? ''), name: String(x.name ?? ''), marginBalance: this.toNum(x.marginBalance ?? x.margin_balance), marginBuy: this.toNum(x.marginBuy ?? x.margin_buy), totalBalance: this.toNum(x.totalBalance ?? x.total_balance) })) } };
  }

  async getBlockTrades(date?: string, code?: string, limit = 500) {
    const args: Record<string, unknown> = { limit };
    if (date) args.date = date.trim();
    if (code) args.stock_code = code.trim();
    const payload = await this.mcp.callTool('get_block_trades', args);
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { data: { items: list.map((x: any) => ({ date: String(x.date ?? ''), code: String(x.code ?? ''), name: String(x.name ?? ''), price: this.toNum(x.price), volume: this.toNum(x.volume), amount: this.toNum(x.amount), premium: this.toNum(x.premium), buyer: String(x.buyer ?? ''), seller: String(x.seller ?? '') })) } };
  }

  async getNorthFundHolding(code: string) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [{ stock_code: stockCode }, { code: stockCode }];
    const { payload } = await this.callWithArgs('get_north_fund_holding', attempts);
    const d = (payload as any)?.data ?? payload ?? {};
    return { data: { code: stockCode, shares: this.toNum(d.shares), ratio: this.toNum(d.ratio), change: this.toNum(d.change) } };
  }

  async getNorthFundTop(topN = 20) {
    const payload = await this.mcp.callTool('get_north_fund_top', { top_n: topN });
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { data: { items: list.map((x: any) => ({ code: String(x.code ?? ''), name: String(x.name ?? ''), shares: this.toNum(x.shares), ratio: this.toNum(x.ratio), marketCap: this.toNum(x.marketCap ?? x.market_cap) })) } };
  }

  private normalizeFlows(payload: any): NormalizedFlowItem[] {
    const root = payload?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root
      : Array.isArray(root?.items) ? root.items
      : Array.isArray(root?.flows) ? root.flows
      : Array.isArray(root?.data) ? root.data
      : Array.isArray(root?.records) ? root.records : [];
    return list.map((x: any) => ({
      date: String(x.date ?? x.trade_date ?? x.Date ?? ''),
      name: String(x.name ?? x.sector_name ?? x.concept_name ?? ''),
      changePercent: this.toNum(x.changePercent ?? x.change_percent),
      netInflow: this.toNum(x.net_inflow ?? x.netInflow ?? x.mainNetInflow ?? x.net_amount ?? x.total ?? x.value),
      mainInflow: this.toNum(x.main_inflow ?? x.mainInflow ?? x.mainNetInflow ?? x.main_net_inflow ?? x.superLargeNetInflow),
      mainOutflow: this.toNum(x.main_outflow ?? x.mainOutflow),
      retailInflow: this.toNum(x.retail_inflow ?? x.retailInflow ?? x.smallNetInflow ?? x.inflow),
      retailOutflow: this.toNum(x.retail_outflow ?? x.retailOutflow ?? x.outflow),
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
