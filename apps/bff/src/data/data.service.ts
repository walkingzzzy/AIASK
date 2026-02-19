import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class DataService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async getOptionChain(params: { underlying: string; expiryMonth?: string; limit?: number }) {
    const payload = await this.callTool('get_option_chain', {
      underlying: params.underlying, expiry_month: params.expiryMonth, limit: params.limit ?? 50,
    });
    return { sourceTool: 'get_option_chain' as const, result: payload };
  }

  async getTradingDates(params: { startDate?: string; endDate?: string; count?: number }) {
    const payload = await this.callTool('get_trading_dates', {
      start_date: params.startDate, end_date: params.endDate, count: params.count,
    });
    return { sourceTool: 'get_trading_dates' as const, result: payload };
  }

  async getIpoInfo(params: { ipoType?: string; includeFuture?: boolean }) {
    const payload = await this.callTool('get_ipo_info', {
      ipo_type: params.ipoType, include_future: params.includeFuture ?? true,
    });
    return { sourceTool: 'get_ipo_info' as const, result: payload };
  }

  async getCbInfo(code: string) {
    const payload = await this.callTool('get_cb_info', { code });
    return { sourceTool: 'get_cb_info' as const, result: payload };
  }

  async getStockCapital(params: { code: string; dates?: string[] }) {
    const payload = await this.callTool('get_stock_capital', {
      code: params.code, dates: params.dates,
    });
    return { sourceTool: 'get_stock_capital' as const, result: payload };
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
