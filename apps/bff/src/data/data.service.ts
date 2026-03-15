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
      start_date: params.startDate, end_date: params.endDate, count: params.count ?? 30,
    });
    return {
      sourceTool: 'get_trading_dates' as const,
      result: payload,
      dates: this.pickTradingDates(payload),
    };
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

  private pickTradingDates(payload: unknown) {
    const root = this.readPath(payload, 'data.dates') ?? this.readPath(payload, 'dates');
    if (!Array.isArray(root)) return [];
    return root.map((item) => this.normalizeTradingDate(item)).filter(Boolean);
  }

  private normalizeTradingDate(value: unknown) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const row = value as Record<string, unknown>;
      return {
        date: String(row.date ?? row.trade_date ?? row.trading_date ?? ''),
        dayOfWeek: String(row.dayOfWeek ?? row.day_of_week ?? row.weekday ?? ''),
        isTrading: row.isTrading ?? row.is_trading ?? row.open ?? true,
      };
    }

    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const normalized = raw.length === 8 ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` : raw;
    const date = new Date(normalized);
    const dayOfWeek = Number.isNaN(date.getTime())
      ? ''
      : ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][date.getDay()];
    return {
      date: normalized,
      dayOfWeek,
      isTrading: true,
    };
  }

  private readPath(value: unknown, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, key) => {
      if (!acc || typeof acc !== 'object') return undefined;
      return (acc as Record<string, unknown>)[key];
    }, value);
  }
}
