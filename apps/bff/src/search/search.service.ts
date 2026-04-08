import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class SearchService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async similarStocks(params: { code: string; topN?: number; type?: string }) {
    const payload = await this.callTool('search_similar_stocks', {
      code: params.code, top_n: params.topN ?? 10, similarity_type: params.type ?? 'both',
    });
    return {
      sourceTool: 'search_similar_stocks' as const,
      result: payload,
      items: this.pickArray(payload, [
        'data.similar_stocks',
        'data.data.similar_stocks',
        'similar_stocks',
        'results',
      ]),
    };
  }

  async semanticSearch(params: { query: string; limit?: number }) {
    const limit = params.limit ?? 10;
    const { payload, sourceTool, fallbackReason } = await this.callSemanticToolWithFallback(params.query, limit);
    return {
      sourceTool,
      result: payload,
      ...(fallbackReason ? { fallback: { used: true, reason: fallbackReason } } : {}),
      items: this.pickArray(payload, [
        'data.results',
        'data.data.results',
        'results',
        'items',
      ]),
    };
  }

  async searchByKline(params: { code: string; topN?: number }) {
    const payload = await this.callTool('search_by_kline', {
      code: params.code, top_n: params.topN ?? 10,
    });
    return {
      sourceTool: 'search_by_kline' as const,
      result: payload,
      items: this.pickArray(payload, [
        'data.results',
        'data.data.results',
        'results',
        'items',
      ]),
    };
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

  private async callSemanticToolWithFallback(query: string, limit: number) {
    try {
      const payload = await this.mcpGatewayService.callTool('semantic_stock_search', {
        query,
        limit,
      });
      const toolError = this.extractToolError(payload);
      if (!toolError) {
        return { payload, sourceTool: 'semantic_stock_search' as const, fallbackReason: null };
      }
      return this.buildSemanticFallback(query, limit, toolError);
    } catch (error) {
      return this.buildSemanticFallback(query, limit, this.describeError(error));
    }
  }

  private async buildSemanticFallback(query: string, limit: number, reason: string) {
    const payload = await this.callTool('search_stocks', {
      keyword: query.trim(),
      limit,
    });
    return {
      payload,
      sourceTool: 'search_stocks' as const,
      fallbackReason: reason,
    };
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

  private describeError(error: unknown) {
    if (error instanceof Error) {
      return error.message;
    }
    return String(error);
  }

  private pickArray(payload: unknown, paths: string[]) {
    for (const path of paths) {
      const value = this.readPath(payload, path);
      if (Array.isArray(value)) return value;
    }
    return [];
  }

  private readPath(value: unknown, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, key) => {
      if (!acc || typeof acc !== 'object') return undefined;
      return (acc as Record<string, unknown>)[key];
    }, value);
  }
}
