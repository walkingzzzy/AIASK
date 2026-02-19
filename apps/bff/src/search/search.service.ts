import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class SearchService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async similarStocks(params: { code: string; topN?: number; type?: string }) {
    const payload = await this.callTool('search_similar_stocks', {
      code: params.code, top_n: params.topN ?? 10, type: params.type ?? 'both',
    });
    return { sourceTool: 'search_similar_stocks' as const, result: payload };
  }

  async semanticSearch(params: { query: string; limit?: number }) {
    const payload = await this.callTool('semantic_stock_search', {
      query: params.query, limit: params.limit ?? 10,
    });
    return { sourceTool: 'semantic_stock_search' as const, result: payload };
  }

  async searchByKline(params: { code: string; topN?: number }) {
    const payload = await this.callTool('search_by_kline', {
      code: params.code, top_n: params.topN ?? 10,
    });
    return { sourceTool: 'search_by_kline' as const, result: payload };
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
}
