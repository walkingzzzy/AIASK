import { Injectable, Logger } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import { DbService } from '../db/db.service';
import { callToolWithContract } from '../common/tool-contracts';
import {
  getCapital,
  getF10Info,
  getFinancialHistory,
  getFinancialSnapshot,
  getHistory,
  getOverview,
  getPeers,
  getStockInfo,
  type FundamentalServiceApiHost,
} from './fundamental.service.api';
import {
  FundamentalCapitalDto,
  FundamentalHistoryDto,
  FundamentalOverviewDto,
  FundamentalPeersDto,
  NormalizedFinancials,
  NormalizedValuation,
} from './fundamental.types';

@Injectable()
export class FundamentalService {
  private readonly logger = new Logger(FundamentalService.name);
  private static readonly OVERVIEW_TTL_SECONDS = 300;
  private static readonly HISTORY_TTL_SECONDS = 300;
  private static readonly CAPITAL_TTL_SECONDS = 300;
  private static readonly PEERS_TTL_SECONDS = 300;
  private static readonly STOCK_INFO_TTL_SECONDS = 120;

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
    private readonly dbService: DbService,
  ) { }

  async getOverview(code: string): Promise<FundamentalOverviewDto> {
    return getOverview(this as unknown as FundamentalServiceApiHost, code);
  }

  async getHistory(code: string, days = 90): Promise<FundamentalHistoryDto> {
    return getHistory(this as unknown as FundamentalServiceApiHost, code, days);
  }

  async getCapital(code: string): Promise<FundamentalCapitalDto> {
    return getCapital(this as unknown as FundamentalServiceApiHost, code);
  }

  async getPeers(code: string): Promise<FundamentalPeersDto> {
    return getPeers(this as unknown as FundamentalServiceApiHost, code);
  }

  async getStockInfo(code: string) {
    return getStockInfo(this as unknown as FundamentalServiceApiHost, code);
  }

  async getFinancialSnapshot(code: string) {
    return getFinancialSnapshot(this as unknown as FundamentalServiceApiHost, code);
  }

  async getFinancialHistory(codes: string[], fields: string[], date: string) {
    return getFinancialHistory(this as unknown as FundamentalServiceApiHost, codes, fields, date);
  }

  async getF10Info(code: string) {
    return getF10Info(this as unknown as FundamentalServiceApiHost, code);
  }

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

  private async buildStockInfoFallbackFromDb(code: string) {
    if (!this.dbService.enabled) return null;
    const res = await this.dbService.query<{
      name: string | null;
      industry: string | null;
      market_cap: number | null;
    }>(
      `SELECT stock_name AS name, industry, market_cap FROM stocks WHERE code = $1 LIMIT 1`,
      [code],
    );
    const row = res.rows[0];
    if (!row) return null;
    const marketCap = row.market_cap != null ? Number(row.market_cap) : null;
    return {
      code,
      name: String(row.name ?? ''),
      industry: String(row.industry ?? ''),
      listDate: '',
      totalShares: null,
      floatShares: null,
      totalMarketCap: Number.isFinite(marketCap) ? marketCap : null,
      floatMarketCap: null,
      degraded: true,
      fallbackSource: 'db.stocks',
    };
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
    const result = await callToolWithContract(
      tool,
      attempts,
      (name, args) => this.mcpGatewayService.callTool(name, args),
      altTool ? [altTool] : [],
    );
    return {
      payload: result.payload,
      argsMatched: result.argsMatched,
      canonicalArgs: result.canonicalArgs,
      aliasHits: result.aliasHits,
      canonicalTool: result.canonicalTool,
    };
  }
}
