import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class SentimentService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async analyzeStock(code: string) {
    const payload = await this.callTool('analyze_stock_sentiment', { code });
    return { sourceTool: 'analyze_stock_sentiment' as const, result: payload };
  }

  async fearGreedIndex() {
    const payload = await this.callTool('calculate_fear_greed_index', {});
    return { sourceTool: 'calculate_fear_greed_index' as const, result: payload };
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
