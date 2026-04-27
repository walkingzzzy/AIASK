import { Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { buildMcpTransportFailureDetail } from '../mcp-gateway/mcp-transport.contract';
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
import {
  FastDataTimeoutError,
  attachFastDataMeta,
  buildFastDataSnapshot,
  snapshotAgeMs,
  withFastDataTimeout,
  type FastDataSnapshot,
} from '../common/fast-data-response';

export type NormalizedFlowItem = {
  date: string; name: string; netInflow: number | null; mainInflow: number | null;
  mainOutflow: number | null; retailInflow: number | null; retailOutflow: number | null;
  changePercent?: number | null;
};

type CacheBackend = 'redis' | 'memory' | 'none';
type NorthFundResponse = {
  data: { flows: NormalizedFlowItem[] };
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: CacheBackend; key: string; ttlSeconds: number };
  };
  degraded?: boolean;
  message?: string;
  fallback_reason?: string[];
};

@Injectable()
export class FundFlowService {
  private static readonly STOCK_TTL_SECONDS = 60;
  private static readonly SECTOR_TTL_SECONDS = 120;
  private static readonly CONCEPT_TTL_SECONDS = 120;
  private static readonly NORTH_TTL_SECONDS = 120;
  private static readonly NORTH_STALE_SECONDS = 300;
  private static readonly FAST_TIMEOUT_MS = 1500;
  private static readonly SECTOR_STALE_SECONDS = 300;
  private readonly northInflight = new Map<string, Promise<FastDataSnapshot<NorthFundResponse>>>();
  private readonly sectorInflight = new Map<string, Promise<FastDataSnapshot<Record<string, unknown>>>>();
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

    const attempts: Array<Record<string, unknown>> = [{ code: stockCode }];

    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('get_stock_fund_flow', attempts);
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    // MCP returns a single flat object, not an array — wrap it
    const flows = Array.isArray(root) ? this.normalizeFlows(payload) : [{
      date: new Date().toISOString().slice(0, 10),
      name: String(data.name ?? ''),
      netInflow: this.toNum(data.mainNetInflow ?? data.main_net_inflow ?? data.net_inflow),
      mainInflow: this.toNum(data.mainNetInflow ?? data.main_net_inflow),
      mainOutflow: null,
      retailInflow: this.toNum(data.smallNetInflow ?? data.small_net_inflow),
      retailOutflow: null,
    }];
    const fetchedAt = new Date().toISOString();
    const result = {
      data: { flows },
      meta: { fetchedAt, cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
      result_contract: buildResultContract({
        summary: `${stockCode} 资金流已加载，当前样本 ${flows.length} 条。`,
        availableViews: ['summary', 'compare', 'next_step'],
        evidence: [
          { label: '股票代码', value: stockCode },
          { label: '样本数', value: String(flows.length) },
          { label: '主力净流入', value: flows[0]?.mainInflow == null ? '-' : String(flows[0].mainInflow) },
          { label: '散户净流入', value: flows[0]?.retailInflow == null ? '-' : String(flows[0].retailInflow) },
        ],
        freshness: extractFreshness(payload, fetchedAt, '资金流抓取时间'),
        platformMeta: extractPlatformMeta(payload, {
          sourceTool: canonicalTool,
          referencePath: '/fund-flow/stock',
          freshnessLabel: '资金流抓取时间',
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

  async getSectorFundFlow() {
    const cacheKey = 'fund-flow:sector';
    const ttlSeconds = this.cacheService.resolveTtl('fund-flow.sector', FundFlowService.SECTOR_TTL_SECONDS);
    const staleSeconds = this.cacheService.resolveTtl('fund-flow.sector_stale', FundFlowService.SECTOR_STALE_SECONDS);
    const cached = await this.cacheService.getWithMeta<FastDataSnapshot<Record<string, unknown>> | Record<string, unknown>>(cacheKey);
    if (cached.value) {
      return this.decorateSectorCacheMeta(cached.value, true, cached.meta.backend, cacheKey, ttlSeconds, 'cache');
    }

    const staleKey = `${cacheKey}:stale`;
    const stale = await this.cacheService.getWithMeta<FastDataSnapshot<Record<string, unknown>> | Record<string, unknown>>(staleKey);
    const refresh = this.refreshSectorFundFlow(cacheKey, staleKey, ttlSeconds, staleSeconds);
    if (stale.value) {
      void refresh.catch(() => undefined);
      return this.decorateSectorCacheMeta(stale.value, true, stale.meta.backend, cacheKey, ttlSeconds, 'stale');
    }

    try {
      const snapshot = await withFastDataTimeout(refresh, FundFlowService.FAST_TIMEOUT_MS);
      return attachFastDataMeta(snapshot.payload, { source: 'live', ageMs: snapshotAgeMs(snapshot) });
    } catch (error) {
      const fallbackReason = error instanceof FastDataTimeoutError ? 'mcp_timeout' : 'mcp_unavailable';
      return attachFastDataMeta(this.buildSectorFundFlowFallback(cacheKey, ttlSeconds, error), {
        source: 'stale',
        ageMs: 0,
        fallbackReason,
      });
    }
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

  async getNorthFund(): Promise<NorthFundResponse> {
    const cacheKey = 'fund-flow:north';
    const ttlSeconds = this.cacheService.resolveTtl('fund-flow.north', FundFlowService.NORTH_TTL_SECONDS);
    const staleSeconds = this.cacheService.resolveTtl('fund-flow.north_stale', FundFlowService.NORTH_STALE_SECONDS);
    const cached = await this.cacheService.getWithMeta<FastDataSnapshot<NorthFundResponse>>(cacheKey);
    if (cached.value) {
      const payload = this.decorateNorthCacheMeta(cached.value.payload, true, cached.meta.backend, cacheKey, ttlSeconds);
      return attachFastDataMeta(payload, {
        source: 'cache',
        ageMs: snapshotAgeMs(cached.value),
      });
    }

    const staleKey = `${cacheKey}:stale`;
    const stale = await this.cacheService.getWithMeta<FastDataSnapshot<NorthFundResponse>>(staleKey);
    const refresh = this.refreshNorthFund(cacheKey, staleKey, ttlSeconds, staleSeconds);
    if (stale.value) {
      void refresh.catch(() => undefined);
      const payload = this.decorateNorthCacheMeta(stale.value.payload, true, stale.meta.backend, cacheKey, ttlSeconds);
      return attachFastDataMeta(payload, {
        source: 'stale',
        ageMs: snapshotAgeMs(stale.value),
      });
    }

    try {
      const snapshot = await withFastDataTimeout(refresh, FundFlowService.FAST_TIMEOUT_MS);
      return attachFastDataMeta(snapshot.payload, { source: 'live', ageMs: snapshotAgeMs(snapshot) });
    } catch (error) {
      const fallbackReason = error instanceof FastDataTimeoutError ? 'mcp_timeout' : 'mcp_unavailable';
      return attachFastDataMeta(this.buildNorthFundFallback(cacheKey, ttlSeconds, fallbackReason), {
        source: 'stale',
        ageMs: 0,
        fallbackReason,
      });
    }
  }

  private refreshSectorFundFlow(
    cacheKey: string,
    staleKey: string,
    ttlSeconds: number,
    staleSeconds: number,
  ): Promise<FastDataSnapshot<Record<string, unknown>>> {
    const existing = this.sectorInflight.get(cacheKey);
    if (existing) return existing;

    const refresh = this.loadSectorFundFlow(cacheKey, ttlSeconds)
      .then(async (payload) => {
        const snapshot = buildFastDataSnapshot(payload);
        await Promise.all([
          this.cacheService.set(cacheKey, snapshot, ttlSeconds),
          this.cacheService.set(staleKey, snapshot, staleSeconds),
        ]);
        return snapshot;
      })
      .finally(() => {
        this.sectorInflight.delete(cacheKey);
      });
    this.sectorInflight.set(cacheKey, refresh);
    return refresh;
  }

  private async loadSectorFundFlow(cacheKey: string, ttlSeconds: number): Promise<Record<string, unknown>> {
    const payload = await this.mcp.callTool('get_sector_fund_flow', {}, { timeoutMs: FundFlowService.FAST_TIMEOUT_MS });
    return {
      data: { flows: this.normalizeFlows(payload) },
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds },
      },
    };
  }

  private decorateSectorCacheMeta(
    cached: FastDataSnapshot<Record<string, unknown>> | Record<string, unknown>,
    hit: boolean,
    backend: CacheBackend,
    key: string,
    ttlSeconds: number,
    source: 'cache' | 'stale',
  ): Record<string, unknown> {
    const snapshot = this.isFastDataSnapshot(cached) ? cached : buildFastDataSnapshot(cached);
    const payloadMeta = this.asRecord(snapshot.payload.meta) ?? {};
    return attachFastDataMeta({
      ...snapshot.payload,
      meta: {
        ...payloadMeta,
        fetchedAt: source === 'cache' ? '' : snapshot.fetchedAt,
        cache: { hit, backend, key, ttlSeconds },
      },
    }, {
      source,
      ageMs: snapshotAgeMs(snapshot),
    });
  }

  private buildSectorFundFlowFallback(cacheKey: string, ttlSeconds: number, error: unknown): Record<string, unknown> {
    const detail = buildMcpTransportFailureDetail(this.mcp.getTransportSnapshot(), {
      acceptanceStatus: 'degraded',
      path: '/fund-flow/sector',
      upstream: this.extractUpstreamDetail(error),
    });
    return {
      data: { flows: [] },
      meta: { fetchedAt: new Date().toISOString(), cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds } },
      degraded: true,
      message: '板块资金流暂时不可用，已降级为空结果',
      fallback_reason: ['sector_fund_flow_unavailable', detail.transport.fallback_reason].filter(Boolean),
      detail,
      transport: detail.transport,
    };
  }

  private isFastDataSnapshot(value: unknown): value is FastDataSnapshot<Record<string, unknown>> {
    const record = this.asRecord(value);
    return Boolean(record?.payload && typeof record.payload === 'object' && typeof record.fetchedAt === 'string');
  }

  private refreshNorthFund(
    cacheKey: string,
    staleKey: string,
    ttlSeconds: number,
    staleSeconds: number,
  ): Promise<FastDataSnapshot<NorthFundResponse>> {
    const existing = this.northInflight.get(cacheKey);
    if (existing) return existing;

    const refresh = this.loadNorthFund(cacheKey, ttlSeconds)
      .then(async (payload) => {
        const snapshot = buildFastDataSnapshot(payload);
        await Promise.all([
          this.cacheService.set(cacheKey, snapshot, ttlSeconds),
          this.cacheService.set(staleKey, snapshot, staleSeconds),
        ]);
        return snapshot;
      })
      .finally(() => {
        this.northInflight.delete(cacheKey);
      });
    this.northInflight.set(cacheKey, refresh);
    return refresh;
  }

  private async loadNorthFund(cacheKey: string, ttlSeconds: number): Promise<NorthFundResponse> {
    const payload = await this.mcp.callTool('get_north_fund', {});
    const flows = this.normalizeFlows(payload);
    return {
      data: { flows },
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds },
      },
    };
  }

  private decorateNorthCacheMeta(
    payload: NorthFundResponse,
    hit: boolean,
    backend: CacheBackend,
    key: string,
    ttlSeconds: number,
  ): NorthFundResponse {
    return {
      ...payload,
      meta: {
        ...payload.meta,
        fetchedAt: hit ? '' : payload.meta.fetchedAt,
        cache: { hit, backend, key, ttlSeconds },
      },
    };
  }

  private buildNorthFundFallback(cacheKey: string, ttlSeconds: number, reason: string): NorthFundResponse {
    return {
      data: { flows: [] },
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds },
      },
      degraded: true,
      message: '北向资金暂时不可用，已返回空快照并在后台刷新',
      fallback_reason: ['north_fund_unavailable', reason],
    };
  }

  async getDragonTiger(date?: string, code?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    if (code) args.stock_code = code.trim();
    const payload = await this.mcp.callTool('get_dragon_tiger', args);
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      data: {
        items: list.map((item) => {
          const reason = item.reason == null || String(item.reason) === 'nan' ? '' : String(item.reason);
          return {
            code: String(item.code ?? ''),
            name: String(item.name ?? ''),
            closePrice: this.toNum(item.closePrice ?? item.close_price ?? item.price),
            changePercent: this.toNum(item.changePercent ?? item.change_percent),
            reason,
            buyAmount: this.toNum(item.buyAmount ?? item.buy_amount),
            sellAmount: this.toNum(item.sellAmount ?? item.sell_amount),
            netAmount: this.toNum(item.netAmount ?? item.net_amount),
          };
        }),
      },
    };
  }

  async getMarginData(code?: string, days = 30) {
    const args: Record<string, unknown> = { days };
    if (code) args.stock_code = code.trim();
    const payload = await this.mcp.callTool('get_margin_data', args);
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      data: {
        items: list.map((item) => ({
          date: String(item.date ?? ''),
          code: String(item.code ?? ''),
          name: String(item.name ?? ''),
          marginBalance: this.toNum(item.marginBalance ?? item.margin_balance),
          marginBuy: this.toNum(item.marginBuy ?? item.margin_buy),
          shortBalance: this.toNum(item.shortBalance ?? item.short_balance),
          totalBalance: this.toNum(item.totalBalance ?? item.total_balance),
        })),
      },
    };
  }

  async getMarginRanking(topN = 20, sortBy = 'balance') {
    const payload = await this.mcp.callTool('get_margin_ranking', { top_n: topN, sort_by: sortBy });
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      data: {
        items: list.map((item) => ({
          code: String(item.code ?? ''),
          name: String(item.name ?? ''),
          marginBalance: this.toNum(item.marginBalance ?? item.margin_balance),
          marginBuy: this.toNum(item.marginBuy ?? item.margin_buy),
          totalBalance: this.toNum(item.totalBalance ?? item.total_balance),
        })),
      },
    };
  }

  async getBlockTrades(date?: string, code?: string, limit = 500) {
    const args: Record<string, unknown> = { limit };
    if (date) args.date = date.trim();
    if (code) args.stock_code = code.trim();
    const payload = await this.mcp.callTool('get_block_trades', args);
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      data: {
        items: list.map((item) => ({
          date: String(item.date ?? ''),
          code: String(item.code ?? ''),
          name: String(item.name ?? ''),
          price: this.toNum(item.price),
          volume: this.toNum(item.volume),
          amount: this.toNum(item.amount),
          premium: this.toNum(item.premium),
          buyer: String(item.buyer ?? ''),
          seller: String(item.seller ?? ''),
        })),
      },
    };
  }

  async getNorthFundHolding(code: string) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [{ stock_code: stockCode }, { code: stockCode }];
    const { payload } = await this.callWithArgs('get_north_fund_holding', attempts);
    const data = this.asRecord(this.unwrapPayload(payload));
    return { data: { code: stockCode, shares: this.toNum(data.shares), ratio: this.toNum(data.ratio), change: this.toNum(data.change) } };
  }

  async getNorthFundTop(topN = 20) {
    const payload = await this.mcp.callTool('get_north_fund_top', { top_n: topN });
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      data: {
        items: list.map((item) => ({
          code: String(item.code ?? ''),
          name: String(item.name ?? ''),
          shares: this.toNum(item.shares),
          ratio: this.toNum(item.ratio),
          marketCap: this.toNum(item.marketCap ?? item.market_cap),
        })),
      },
    };
  }

  private normalizeFlows(payload: unknown): NormalizedFlowItem[] {
    const root = this.unwrapPayload(payload);
    const list = Array.isArray(root)
      ? this.asRecordArray(root)
      : this.asRecordArray(
          this.asRecord(root).items
          ?? this.asRecord(root).flows
          ?? this.asRecord(root).data
          ?? this.asRecord(root).records,
        );
    return list.map((item) => ({
      date: String(item.date ?? item.trade_date ?? item.Date ?? ''),
      name: String(item.name ?? item.sector_name ?? item.concept_name ?? ''),
      changePercent: this.toNum(item.changePercent ?? item.change_percent),
      netInflow: this.toNum(item.net_inflow ?? item.netInflow ?? item.mainNetInflow ?? item.net_amount ?? item.total ?? item.value),
      mainInflow: this.toNum(item.main_inflow ?? item.mainInflow ?? item.mainNetInflow ?? item.main_net_inflow ?? item.superLargeNetInflow),
      mainOutflow: this.toNum(item.main_outflow ?? item.mainOutflow),
      retailInflow: this.toNum(item.retail_inflow ?? item.retailInflow ?? item.smallNetInflow ?? item.inflow),
      retailOutflow: this.toNum(item.retail_outflow ?? item.retailOutflow ?? item.outflow),
    }));
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

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private async callWithArgs(primaryTool: string, attempts: Array<Record<string, unknown>>) {
    const result = await callToolWithContract(
      primaryTool,
      attempts,
      (name, args) => this.mcp.callTool(name, args),
    );
    return {
      payload: result.payload,
      argsMatched: result.argsMatched,
      canonicalArgs: result.canonicalArgs,
      aliasHits: result.aliasHits,
      canonicalTool: result.canonicalTool,
    };
  }

  private extractUpstreamDetail(error: unknown): unknown {
    if (error && typeof error === 'object' && typeof (error as { getResponse?: () => unknown }).getResponse === 'function') {
      return (error as { getResponse: () => unknown }).getResponse();
    }
    return {
      message: error instanceof Error ? error.message : String(error),
    };
  }
}
