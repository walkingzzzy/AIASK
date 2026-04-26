import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import {
  buildResultContract,
  extractFreshness,
  extractPlatformMeta,
  readPath,
  toText,
} from '../common/result-contract';

@Injectable()
export class SearchService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async similarStocks(params: { code: string; topN?: number; type?: string }) {
    const payload = await this.callTool('search_similar_stocks', {
      code: params.code, top_n: params.topN ?? 10, similarity_type: params.type ?? 'both',
    });
    const items = this.pickArray(payload, [
      'data.similar_stocks',
      'data.data.similar_stocks',
      'similar_stocks',
      'results',
    ]);
    return {
      sourceTool: 'search_similar_stocks' as const,
      result: payload,
      items,
      result_contract: this.buildSearchResultContract({
        payload,
        sourceTool: 'search_similar_stocks',
        queryLabel: params.code,
        items,
        taskLabel: '相似股票搜索',
      }),
    };
  }

  async semanticSearch(params: { query: string; limit?: number }) {
    const limit = params.limit ?? 10;
    const payload = await this.callTool('semantic_stock_search', {
      query: params.query,
      limit,
    });
    const items = this.pickArray(payload, [
      'data.results',
      'data.data.results',
      'results',
      'items',
    ]);
    return {
      sourceTool: 'semantic_stock_search' as const,
      result: payload,
      items,
      result_contract: this.buildSearchResultContract({
        payload,
        sourceTool: 'semantic_stock_search',
        queryLabel: params.query,
        items,
        taskLabel: '语义搜索',
      }),
    };
  }

  async searchByKline(params: { code: string; topN?: number }) {
    const payload = await this.callTool('search_by_kline', {
      code: params.code, top_n: params.topN ?? 10,
    });
    const items = this.pickArray(payload, [
      'data.results',
      'data.data.results',
      'results',
      'items',
    ]);
    return {
      sourceTool: 'search_by_kline' as const,
      result: payload,
      items,
      result_contract: this.buildSearchResultContract({
        payload,
        sourceTool: 'search_by_kline',
        queryLabel: params.code,
        items,
        taskLabel: 'K线搜索',
      }),
    };
  }

  private buildSearchResultContract(options: {
    payload: unknown;
    sourceTool: string;
    queryLabel: string;
    items: unknown[];
    taskLabel: string;
  }) {
    const first = this.asRecord(options.items[0]);
    const primaryCode = toText(first.code ?? first.stock_code ?? first.symbol);
    const primaryName = toText(first.name ?? first.stock_name ?? first.display_name);
    const primaryIndustry = toText(first.industry ?? first.sector);
    const followupQuery = primaryName || primaryCode || options.queryLabel;
    return buildResultContract({
      summary: options.items.length > 0
        ? `${options.taskLabel}“${options.queryLabel}”返回 ${options.items.length} 条结果，优先结果 ${primaryName || primaryCode || '已命中候选标的'}。`
        : `${options.taskLabel}“${options.queryLabel}”当前没有命中结果，建议调整关键词或切换搜索方式。`,
      availableViews: ['summary', 'next_step', ...(options.items.length > 1 ? (['compare'] as const) : [])],
      recommendedActions: [
        {
          id: 'search.open-copilot-followup',
          actionId: 'search.open-copilot-followup',
          label: '打开 Copilot 解读结果',
          description: '把当前搜索结果继续转成下一步研究动作。',
          payload: {
            query: options.queryLabel,
            primaryCode: primaryCode || null,
          },
        },
      ],
      recommendedLinks: [
        primaryCode
          ? {
              id: 'search-open-stock',
              label: '个股详情',
              href: `/stock?code=${encodeURIComponent(primaryCode)}`,
            }
          : {
              id: 'search-open-research',
              label: '继续研究页',
              href: '/research',
            },
        {
          id: 'search-open-skills',
          label: '去技能中心',
          href: `/skills?skill=${encodeURIComponent('akshare-market')}`,
        },
        {
          id: 'search-open-strategy-market',
          label: '去策略超市',
          href: `/strategy-market?from=search&task=strategy_review&q=${encodeURIComponent(followupQuery)}${primaryIndustry ? `&category=${encodeURIComponent(primaryIndustry)}` : ''}`,
        },
        {
          id: 'search-open-factory',
          label: '去工厂运行态',
          href: `/strategy-market?from=search&task=factory_cycle&q=${encodeURIComponent(followupQuery)}${primaryIndustry ? `&category=${encodeURIComponent(primaryIndustry)}` : ''}`,
        },
      ],
      evidence: [
        { label: '结果数', value: String(options.items.length) },
        primaryCode ? { label: '优先代码', value: primaryCode } : null,
        primaryName ? { label: '优先结果', value: primaryName } : null,
        primaryIndustry ? { label: '所属行业', value: primaryIndustry } : null,
      ].filter((item): item is NonNullable<typeof item> => item != null),
      riskNotes: options.items.length > 0 ? [] : ['当前搜索为空，建议改用更明确的主题词或股票代码。'],
      freshness: extractFreshness(options.payload, null, `${options.taskLabel}结果`),
      platformMeta: extractPlatformMeta(options.payload, {
        sourceTool: options.sourceTool,
        referencePath: '/data/tool-catalog',
      }),
      skillSuggestions: [
        {
          skillId: 'akshare-market',
          label: '行情快扫',
          reason: '围绕当前候选标的继续补齐行情与走势。',
          supportedTask: 'quick_scan',
        },
        {
          skillId: 'akshare-fund-news',
          label: '资讯摘要',
          reason: '继续补齐新闻和研报线索。',
          supportedTask: 'research_digest',
        },
        {
          skillId: 'akshare-fundamental',
          label: '基本面快照',
          reason: '快速补齐候选标的基本面证据。',
          supportedTask: 'fundamental_snapshot',
        },
      ],
      strategySuggestions: [
        {
          id: `${options.sourceTool}-strategy-followup`,
          label: '去策略超市继续研究',
          description: '把当前搜索线索转到策略页继续筛选。',
          query: followupQuery,
          category: primaryIndustry || undefined,
          task: 'strategy_review',
        },
        {
          id: `${options.sourceTool}-factory-followup`,
          label: '去工厂看运行态',
          description: '围绕当前线索查看策略工厂的运行与治理状态。',
          query: followupQuery,
          category: primaryIndustry || undefined,
          task: 'factory_cycle',
        },
      ],
      workbenchTask: {
        title: `${options.taskLabel}：${options.queryLabel}`,
        href: '/search',
        kind: 'search-result',
        payload: {
          query: options.queryLabel,
          sourceTool: options.sourceTool,
          primaryCode: primaryCode || null,
          primaryIndustry: primaryIndustry || null,
        },
      },
    });
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      return await this.mcpGatewayService.callTool(name, args);
    } catch (error) {
      throw new BadGatewayException({
        success: false, message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      return /error executing tool|validation error|unknown tool/i.test(payload) ? payload : null;
    }
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const record = payload as Record<string, unknown>;
    if (record.data && typeof record.data === 'string' && /error executing tool|validation error|unknown tool/i.test(record.data)) {
      return record.data;
    }
    if (record.success === false) {
      return String(record.error ?? record.message ?? 'search semantic tool error');
    }
    return null;
  }
  private pickArray(payload: unknown, paths: string[]) {
    for (const path of paths) {
      const value = this.readPath(payload, path);
      if (Array.isArray(value)) return value;
    }
    return [];
  }

  private readPath(value: unknown, path: string): unknown {
    return readPath(value, path);
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  }
}
