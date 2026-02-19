import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

type ToolCallResult = { payload: unknown; argsMatched: Record<string, unknown> };

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
    const cacheKey = `research:list:${normalized}:${startDate}:${endDate}:${keyword.toLowerCase()}:${limit}`;
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

    const reportAttempts: Array<Record<string, unknown>> = [
      { stock_code: normalized, limit },
      { symbol: normalized, limit },
      { code: normalized, limit },
    ];

    const noticeAttempts: Array<Record<string, unknown>> = [
      { start_date: startDate, end_date: endDate, stock_code: normalized, types: null },
      { start_date: startDate, end_date: endDate, code: normalized, types: null },
      { start_date: startDate, end_date: endDate, symbol: normalized, types: null },
    ];

    const reportsCall = await this.callWithArgs('get_stock_research', reportAttempts);
    const noticesCall = await this.callWithArgs('get_stock_notices', noticeAttempts);

    const reports = this.filterItems(
      this.normalizeItems(this.extractArray(reportsCall.payload), 'report'),
      startDate,
      endDate,
      keyword,
      limit,
    );
    const notices = this.filterItems(
      this.normalizeItems(this.extractArray(noticesCall.payload), 'notice'),
      startDate,
      endDate,
      keyword,
      limit,
    );

    const result: ResearchListDto = {
      code: normalized,
      query: { startDate, endDate, keyword, limit },
      reports,
      notices,
      sourceTools: { reports: 'get_stock_research', notices: 'get_stock_notices' },
      argsMatched: { reports: reportsCall.argsMatched, notices: noticesCall.argsMatched },
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
    };

    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try { return await this.mcpGatewayService.callTool(name, args); }
    catch (error) { throw new BadGatewayException({ success: false, message: `调用 MCP ${name} 失败`, detail: error instanceof Error ? error.message : String(error) }); }
  }

  async getStockNews(code: string, limit = 20) {
    const attempts: Array<Record<string, unknown>> = [{ stock_code: code.trim(), limit }, { code: code.trim(), limit }];
    const { payload } = await this.callWithArgs('get_stock_news', attempts);
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { items: list.map((n: any) => ({ title: String(n.title ?? ''), date: String(n.date ?? n.publish_date ?? ''), source: String(n.source ?? ''), url: String(n.url ?? n.link ?? '') })), count: list.length };
  }

  async getMarketNews(limit = 20) {
    const payload = await this.callTool('get_market_news', { limit });
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { items: list.map((n: any) => ({ title: String(n.title ?? ''), date: String(n.date ?? n.publish_date ?? ''), source: String(n.source ?? ''), url: String(n.url ?? n.link ?? '') })), count: list.length };
  }

  async searchResearch(keyword?: string, code?: string, days = 30) {
    const args: Record<string, unknown> = { days };
    if (keyword) args.keyword = keyword.trim();
    if (code) args.stock_code = code.trim();
    const payload = await this.callTool('search_research', args);
    const d = (payload as any)?.data ?? payload ?? {};
    const reports = Array.isArray(d?.reports) ? d.reports : Array.isArray(d) ? d : [];
    return { reports: reports.map((r: any) => ({ title: String(r.title ?? ''), institution: String(r.institution ?? ''), rating: String(r.rating ?? ''), date: String(r.date ?? ''), stockCode: String(r.stockCode ?? r.stock_code ?? '') })), total: reports.length };
  }

  async getAnalystRanking(year?: string) {
    const args: Record<string, unknown> = {};
    if (year) args.year = year.trim();
    const payload = await this.callTool('get_analyst_ranking', args);
    const d = (payload as any)?.data ?? payload ?? {};
    const analysts = Array.isArray(d?.analysts) ? d.analysts : Array.isArray(d) ? d : [];
    return { analysts: analysts.map((a: any) => ({ rank: Number(a.rank ?? 0), name: String(a.name ?? ''), institution: String(a.institution ?? ''), industry: String(a.industry ?? ''), winRate: Number(a.winRate ?? a.win_rate ?? 0) })), total: analysts.length };
  }

  async getResearchReports(code?: string, limit = 10) {
    const args: Record<string, unknown> = { limit };
    if (code) args.symbol = code.trim();
    const payload = await this.callTool('get_research_reports', args);
    const root = (payload as any)?.data ?? payload ?? [];
    const list = Array.isArray(root) ? root : [];
    return { reports: list.map((r: any) => ({ title: String(r.title ?? ''), institution: String(r.institution ?? ''), author: String(r.author ?? ''), rating: String(r.rating ?? ''), date: String(r.date ?? '') })), count: list.length };
  }

  async getMacroIndicator(indicator?: string) {
    const payload = await this.callTool('get_macro_indicator', { indicator: indicator ?? 'gdp' });
    return { sourceTool: 'get_macro_indicator' as const, result: payload };
  }

  async getProfitForecast(code: string) {
    const attempts: Array<Record<string, unknown>> = [{ symbol: code.trim() }, { stock_code: code.trim() }, { code: code.trim() }];
    const { payload } = await this.callWithArgs('get_profit_forecast', attempts);
    const d = (payload as any)?.data ?? payload ?? {};
    const items = Array.isArray(d?.items) ? d.items : Array.isArray(d) ? d : [];
    return { items: items.map((f: any) => ({ date: String(f.date ?? ''), institution: String(f.institution ?? ''), rating: String(f.rating ?? ''), epsForecast: Number(f.eps_forecast ?? f.epsForecast ?? 0), netprofitForecast: Number(f.netprofit_forecast ?? f.netprofitForecast ?? 0) })), total: items.length };
  }

  private extractArray(payload: any): any[] {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.data)) return payload.data;
    if (Array.isArray(payload?.data?.items)) return payload.data.items;
    if (Array.isArray(payload?.items)) return payload.items;
    if (Array.isArray(payload?.data?.list)) return payload.data.list;
    return [];
  }

  private normalizeItems(list: any[], kind: 'report' | 'notice'): ResearchItem[] {
    return list.map((it: any) => ({
      title: String(it.title ?? it.report_title ?? it.notice_title ?? it.name ?? it.标题 ?? `${kind.toUpperCase()}-ITEM`),
      date: String(it.date ?? it.publish_date ?? it.pub_date ?? it.notice_date ?? it.datetime ?? it.time ?? it.日期 ?? ''),
      source: String(it.source ?? it.org_name ?? it.media ?? it.来源 ?? 'unknown'),
      summary: String(it.summary ?? it.content ?? it.abstract ?? it.remark ?? it.内容 ?? ''),
      raw: it,
    }));
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
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcpGatewayService.callTool(tool, args);
        return { payload, argsMatched: args };
      } catch (error) {
        lastError = error;
      }
    }
    throw new BadGatewayException({
      success: false,
      message: `调用 MCP ${tool} 失败`,
      detail: lastError instanceof Error ? lastError.message : String(lastError),
    });
  }
}

