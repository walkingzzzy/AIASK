import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class TechnicalService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async calculateIndicators(params: { code: string; indicators: string[]; period?: string; limit?: number }) {
    const payload = await this.callTool('calculate_technical_indicators', {
      code: params.code, indicators: params.indicators,
      period: params.period ?? 'daily', limit: params.limit ?? 100,
    });
    return { sourceTool: 'calculate_technical_indicators' as const, data: this.extractToolData(payload), result: payload };
  }

  async checkPatterns(params: { code: string; period?: string; limit?: number }) {
    const payload = await this.callTool('check_candlestick_patterns', {
      code: params.code, period: params.period ?? 'daily', limit: params.limit ?? 100,
    });
    return { sourceTool: 'check_candlestick_patterns' as const, data: this.extractToolData(payload), result: payload };
  }

  async getAvailablePatterns() {
    const payload = await this.callTool('get_available_patterns', {});
    return { sourceTool: 'get_available_patterns' as const, data: this.extractToolData(payload), result: payload };
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

  private extractToolData(payload: unknown): unknown {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return payload;
    }
    const record = payload as Record<string, unknown>;
    return Object.prototype.hasOwnProperty.call(record, 'data') ? record.data : payload;
  }
}
