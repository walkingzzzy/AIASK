import { BadGatewayException, Injectable } from '@nestjs/common';
import type { ResultContract, ResultContractMeta } from '@aiask/shared-types';
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
import type { DataQuality } from '../common/data-quality';
import { buildDataQuality } from '../common/data-quality';

type ToolCallResult = {
  payload: unknown;
  argsMatched: Record<string, unknown>;
  canonicalArgs: Record<string, unknown>;
  aliasHits: ResultContractMeta['aliasHits'];
  canonicalTool: string;
};

export type ResearchQueryOptions = {
  days?: number;
  startDate?: string;
  endDate?: string;
  keyword?: string;
  limit?: number;
};

export type ResearchItem = { title: string; date: string; source: string; summary: string; raw: unknown };

export type ResearchListDto = {
  code: string;
  query: { startDate: string; endDate: string; keyword: string; limit: number };
  reports: ResearchItem[];
  notices: ResearchItem[];
  sourceTools: { reports: 'get_stock_research'; notices: 'get_stock_notices' };
  argsMatched: { reports: Record<string, unknown>; notices: Record<string, unknown> };
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
  result_contract?: ResultContract | null;
  data_quality?: DataQuality | null;
  contract_meta?: {
    reports: ResultContractMeta;
    notices: ResultContractMeta;
  };
};

@Injectable()
export class ResearchService {
  private static readonly LIST_TTL_SECONDS = 3600;

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async getList(code: string, options: ResearchQueryOptions = {}): Promise<ResearchListDto> {
    const normalized = code.trim();
    const limit = Math.min(Math.max(options.limit ?? 20, 1), 100);
    const { startDate, endDate } = this.resolveRange(options);
    const keyword = (options.keyword ?? '').trim();
    const cacheKey = `research:list:v2:${normalized}:${startDate}:${endDate}:${keyword.toLowerCase()}:${limit}`;
    const ttlSeconds = this.cacheService.resolveTtl('research.list', ResearchService.LIST_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<ResearchListDto>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const [reportsResult, noticesResult] = await Promise.allSettled([
      this.callWithArgs('get_stock_research', [{ code: normalized, limit }]),
      this.callWithArgs('get_stock_notices', [{
        code: normalized,
        start_date: startDate,
        end_date: endDate,
        types: null,
      }]),
    ]);
    const reportsCall = reportsResult.status === 'fulfilled' ? reportsResult.value : null;
    const noticesCall = noticesResult.status === 'fulfilled' ? noticesResult.value : null;

    const reports = this.filterItems(
      reportsCall ? this.normalizeItems(this.extractArray(reportsCall.payload), 'report') : [],
      startDate,
      endDate,
      keyword,
      limit,
    );
    const notices = this.filterItems(
      noticesCall ? this.normalizeItems(this.extractArray(noticesCall.payload), 'notice') : [],
      startDate,
      endDate,
      keyword,
      limit,
    );
    const totalCount = reports.length + notices.length;
    const fetchedAt = new Date().toISOString();
    const failedSources = [
      reportsResult.status === 'rejected'
        ? { name: 'get_stock_research', error: this.formatUpstreamError(reportsResult.reason) }
        : null,
      noticesResult.status === 'rejected'
        ? { name: 'get_stock_notices', error: this.formatUpstreamError(noticesResult.reason) }
        : null,
    ].filter((item): item is { name: string; error: string } => item != null);
    const emptyReason = `当前 ${startDate} 至 ${endDate} 窗口未命中研报或公告。`;
    const unavailableReason = failedSources.length > 0
      ? failedSources.map((source) => `${source.name}_unavailable: ${source.error}`).join('；')
      : null;
    const qualityStatus = failedSources.length > 0
      ? (totalCount > 0 ? 'partial' : 'unavailable')
      : (totalCount > 0 ? 'trusted' : 'empty');
    const dataQuality = buildDataQuality({
      status: qualityStatus,
      reasons: failedSources.length > 0 ? failedSources.map((source) => `${source.name}_unavailable`) : (totalCount > 0 ? [] : ['research_window_empty']),
      qualityFlags: [
        ...(failedSources.length > 0 ? ['research_source_unavailable'] : []),
        ...(totalCount === 0 && failedSources.length === 0 ? ['valid_empty'] : []),
      ],
      emptyReason: failedSources.length > 0 ? unavailableReason : (totalCount > 0 ? null : emptyReason),
      sources: [
        {
          name: 'get_stock_research',
          status: reportsResult.status === 'rejected' ? 'failed' : (reports.length > 0 ? 'trusted' : 'empty'),
          freshness: fetchedAt,
          sampleCount: reports.length,
          error: reportsResult.status === 'rejected' ? this.formatUpstreamError(reportsResult.reason) : null,
        },
        {
          name: 'get_stock_notices',
          status: noticesResult.status === 'rejected' ? 'failed' : (notices.length > 0 ? 'trusted' : 'empty'),
          freshness: fetchedAt,
          sampleCount: notices.length,
          error: noticesResult.status === 'rejected' ? this.formatUpstreamError(noticesResult.reason) : null,
        },
      ],
    });

    const result: ResearchListDto = {
      code: normalized,
      query: { startDate, endDate, keyword, limit },
      reports,
      notices,
      sourceTools: { reports: 'get_stock_research', notices: 'get_stock_notices' },
      argsMatched: { reports: reportsCall?.argsMatched ?? {}, notices: noticesCall?.argsMatched ?? {} },
      meta: {
        fetchedAt,
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
      result_contract: buildResultContract({
        summary: failedSources.length > 0
          ? `${normalized} 研报公告部分数据源不可用，当前保留 ${reports.length} 条研报、${notices.length} 条公告。`
          : `${normalized} 在 ${startDate} 至 ${endDate} 区间内命中 ${reports.length} 条研报、${notices.length} 条公告。`,
        status: failedSources.length > 0 ? (totalCount > 0 ? 'degraded' : 'unavailable') : (totalCount > 0 ? 'ready' : 'empty'),
        availableViews: ['summary', 'compare', 'next_step'],
        evidence: [
          { label: '股票代码', value: normalized },
          { label: '研报数量', value: String(reports.length) },
          { label: '公告数量', value: String(notices.length) },
          { label: '关键词', value: keyword || '未设置' },
        ],
        riskNotes: failedSources.length > 0
          ? [unavailableReason ?? '研究数据源暂不可用，页面不按正常研究结果展示。']
          : (totalCount === 0 ? [emptyReason, '建议扩大时间范围或切换关键词。'] : []),
        freshness: extractFreshness({ meta: { fetchedAt } }, null, '资讯抓取时间'),
        platformMeta: extractPlatformMeta(
          {
            meta: {
              fetchedAt,
              source_chain: ['get_stock_research', 'get_stock_notices'],
              degraded: failedSources.length > 0,
              fallback_reason: failedSources.map((source) => `${source.name}_unavailable`),
            },
          },
          {
            sourceTool: 'research.list',
            referencePath: '/research/list',
            freshnessLabel: '资讯抓取时间',
          },
        ),
      }),
      data_quality: dataQuality,
      contract_meta: reportsCall && noticesCall ? {
        reports: buildResultContractMeta({
          canonicalTool: reportsCall.canonicalTool,
          canonicalArgs: reportsCall.canonicalArgs,
          argsMatched: reportsCall.argsMatched,
          aliasHits: reportsCall.aliasHits,
        }),
        notices: buildResultContractMeta({
          canonicalTool: noticesCall.canonicalTool,
          canonicalArgs: noticesCall.canonicalArgs,
          argsMatched: noticesCall.argsMatched,
          aliasHits: noticesCall.aliasHits,
        }),
      } : undefined,
    };

    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try { return await this.mcpGatewayService.callTool(name, args); }
    catch (error) { throw new BadGatewayException({ success: false, message: `调用 MCP ${name} 失败`, detail: error instanceof Error ? error.message : String(error) }); }
  }

  async getStockNews(code: string, limit = 20) {
    const normalized = code.trim();
    const attempts: Array<Record<string, unknown>> = [{ stock_code: normalized, limit }, { code: normalized, limit }];
    let payload: unknown;
    try {
      ({ payload } = await this.callWithArgs('get_stock_news', attempts));
    } catch (error) {
      const detail = buildMcpTransportFailureDetail(this.mcpGatewayService.getTransportSnapshot(), {
        acceptanceStatus: 'degraded',
        path: '/research/stock-news',
        upstream: this.extractUpstreamDetail(error),
      });
      const reason = this.formatUpstreamError(error);
      return {
        items: [],
        count: 0,
        degraded: true,
        fallback_used: true,
        fallback_reason: ['stock_news_unavailable', detail.transport.fallback_reason, reason].filter(Boolean),
        message: '个股资讯暂时不可用，已降级为空结果',
        detail,
        transport: detail.transport,
        result_contract: buildResultContract({
          summary: `${normalized} 个股资讯暂时不可用，页面已保留为空列表并展示原因。`,
          status: 'unavailable',
          availableViews: ['summary', 'next_step'],
          evidence: [
            { label: '股票代码', value: normalized },
            { label: '资讯数量', value: '0' },
          ],
          riskNotes: [reason],
          freshness: { updatedAt: new Date().toISOString(), label: '资讯降级时间' },
          platformMeta: {
            sourceTool: 'get_stock_news',
            referencePath: '/research/stock-news',
            sourceChain: ['get_stock_news'],
            degraded: true,
            fallbackReason: ['stock_news_unavailable', reason],
          },
        }),
        data_quality: buildDataQuality({
          status: 'unavailable',
          reasons: ['stock_news_unavailable', reason],
          qualityFlags: ['stock_news_unavailable'],
          emptyReason: '个股资讯上游暂时不可用',
          sources: [{ name: 'get_stock_news', status: 'failed', error: reason, sampleCount: 0 }],
        }),
      };
    }
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      items: list.map((item) => ({
        title: String(item.title ?? ''),
        date: String(item.date ?? item.publish_date ?? ''),
        source: String(item.source ?? ''),
        url: String(item.url ?? item.link ?? ''),
      })),
      count: list.length,
    };
  }

  async getMarketNews(limit = 20) {
    try {
      const payload = await this.callTool('get_market_news', { limit });
      const list = this.asRecordArray(this.unwrapPayload(payload));
      return {
        items: list.map((item) => ({
          title: String(item.title ?? ''),
          date: String(item.date ?? item.publish_date ?? ''),
          source: String(item.source ?? ''),
          url: String(item.url ?? item.link ?? ''),
        })),
        count: list.length,
      };
    } catch (error) {
      const detail = buildMcpTransportFailureDetail(this.mcpGatewayService.getTransportSnapshot(), {
        acceptanceStatus: 'degraded',
        path: '/research/market-news',
        upstream: this.extractUpstreamDetail(error),
      });
      return {
        items: [],
        count: 0,
        degraded: true,
        message: '市场新闻暂时不可用，已降级为空结果',
        fallback_reason: ['market_news_unavailable', detail.transport.fallback_reason].filter(Boolean),
        detail,
        transport: detail.transport,
      };
    }
  }

  async searchResearch(keyword?: string, code?: string, days = 30) {
    const args: Record<string, unknown> = { days };
    if (keyword) args.keyword = keyword.trim();
    if (code) args.stock_code = code.trim();
    const payload = await this.callTool('search_research', args);
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const reports = this.asRecordArray(data.reports ?? root);
    return {
      reports: reports.map((report) => ({
        title: String(report.title ?? ''),
        institution: String(report.institution ?? ''),
        rating: String(report.rating ?? ''),
        date: String(report.date ?? ''),
        stockCode: String(report.stockCode ?? report.stock_code ?? ''),
      })),
      total: reports.length,
    };
  }

  async getAnalystRanking(year?: string) {
    const args: Record<string, unknown> = {};
    if (year) args.year = year.trim();
    const payload = await this.callTool('get_analyst_ranking', args);
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const analysts = this.asRecordArray(data.analysts ?? root);
    return {
      analysts: analysts.map((analyst) => ({
        rank: Number(analyst.rank ?? 0),
        name: String(analyst.name ?? ''),
        institution: String(analyst.institution ?? ''),
        industry: String(analyst.industry ?? ''),
        winRate: Number(analyst.winRate ?? analyst.win_rate ?? 0),
      })),
      total: analysts.length,
    };
  }

  async getResearchReports(code?: string, limit = 10) {
    const args: Record<string, unknown> = { limit };
    if (code) args.symbol = code.trim();
    const payload = await this.callTool('get_research_reports', args);
    const list = this.asRecordArray(this.unwrapPayload(payload));
    return {
      reports: list.map((report) => ({
        title: String(report.title ?? ''),
        institution: String(report.institution ?? ''),
        author: String(report.author ?? ''),
        rating: String(report.rating ?? ''),
        date: String(report.date ?? ''),
      })),
      count: list.length,
    };
  }

  async getMacroIndicator(indicator?: string) {
    const payload = await this.callTool('get_macro_indicator', { indicator: indicator ?? 'gdp' });
    return { sourceTool: 'get_macro_indicator' as const, result: payload };
  }

  async getProfitForecast(code: string) {
    const attempts: Array<Record<string, unknown>> = [{ symbol: code.trim() }, { stock_code: code.trim() }, { code: code.trim() }];
    const { payload } = await this.callWithArgs('get_profit_forecast', attempts);
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const items = this.asRecordArray(data.items ?? root);
    return {
      items: items.map((item) => ({
        date: String(item.date ?? ''),
        institution: String(item.institution ?? ''),
        rating: String(item.rating ?? ''),
        epsForecast: Number(item.eps_forecast ?? item.epsForecast ?? 0),
        netprofitForecast: Number(item.netprofit_forecast ?? item.netprofitForecast ?? 0),
      })),
      total: items.length,
    };
  }

  private extractArray(payload: unknown): Record<string, unknown>[] {
    const root = this.unwrapPayload(payload);
    if (Array.isArray(root)) return this.asRecordArray(root);
    const record = this.asRecord(root);
    return this.asRecordArray(record.items ?? record.list ?? record.data);
  }

  private normalizeItems(list: ReadonlyArray<Record<string, unknown>>, kind: 'report' | 'notice'): ResearchItem[] {
    return list.map((item) => ({
      title: String(item.title ?? item.report_title ?? item.notice_title ?? item.name ?? item.标题 ?? `${kind.toUpperCase()}-ITEM`),
      date: String(item.date ?? item.publish_date ?? item.pub_date ?? item.notice_date ?? item.datetime ?? item.time ?? item.日期 ?? ''),
      source: String(item.source ?? item.org_name ?? item.media ?? item.来源 ?? 'unknown'),
      summary: String(item.summary ?? item.content ?? item.abstract ?? item.remark ?? item.内容 ?? ''),
      raw: item,
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

  private filterItems(items: ResearchItem[], startDate: string, endDate: string, keyword: string, limit: number): ResearchItem[] {
    const s = new Date(`${startDate}T00:00:00`).getTime();
    const e = new Date(`${endDate}T23:59:59`).getTime();
    const kw = keyword.toLowerCase();
    return items
      .filter((it) => {
        const t = Date.parse(it.date);
        const dateOk = Number.isNaN(t) ? true : t >= s && t <= e;
        const kwOk = !kw || `${it.title} ${it.summary} ${JSON.stringify(it.raw)}`.toLowerCase().includes(kw);
        return dateOk && kwOk;
      })
      .slice(0, limit);
  }

  private resolveRange(options: ResearchQueryOptions) {
    if (options.startDate && options.endDate) return { startDate: options.startDate, endDate: options.endDate };
    const days = Math.min(Math.max(options.days ?? 30, 1), 365);
    const end = new Date();
    const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
    const toDate = (d: Date) => d.toISOString().slice(0, 10);
    return { startDate: toDate(start), endDate: toDate(end) };
  }

  private async callWithArgs(tool: string, attempts: Array<Record<string, unknown>>): Promise<ToolCallResult> {
    const result = await callToolWithContract(
      tool,
      attempts,
      (name, args) => this.mcpGatewayService.callTool(name, args),
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

  private formatUpstreamError(error: unknown): string {
    const detail = this.extractUpstreamDetail(error);
    if (detail && typeof detail === 'object') {
      const record = detail as Record<string, unknown>;
      const errorBody = record.error && typeof record.error === 'object'
        ? record.error as Record<string, unknown>
        : null;
      const message = record.message ?? errorBody?.message ?? record.detail;
      if (typeof message === 'string' && message.trim()) return message.trim();
      if (typeof record.detail === 'string' && record.detail.trim()) return record.detail.trim();
    }
    return error instanceof Error ? error.message : String(error);
  }
}
