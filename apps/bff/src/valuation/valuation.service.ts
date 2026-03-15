import { BadGatewayException, Injectable } from '@nestjs/common';
import type { StockValuationOverview } from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class ValuationService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async dcf(params: { code: string; discountRate?: number; growthRate?: number; years?: number }) {
    const payload = await this.callTool('dcf_valuation', {
      code: params.code, discount_rate: params.discountRate ?? 0.1,
      growth_rate: params.growthRate ?? 0.05, years: params.years ?? 5,
    });
    return { sourceTool: 'dcf_valuation' as const, data: this.extractToolData(payload), result: payload };
  }

  async ddm(params: { code: string; dividend?: number; growthRate?: number; requiredReturn?: number }) {
    const payload = await this.callTool('ddm_valuation', {
      code: params.code, dividend: params.dividend,
      growth_rate: params.growthRate ?? 0.03, required_return: params.requiredReturn ?? 0.08,
    });
    return { sourceTool: 'ddm_valuation' as const, data: this.extractToolData(payload), result: payload };
  }

  async relative(params: { code: string; metrics?: string[]; peers?: string[] }) {
    const payload = await this.callTool('relative_valuation', {
      code: params.code, metrics: params.metrics ?? ['pe', 'pb', 'ps'],
      peers: params.peers,
    });
    return { sourceTool: 'relative_valuation' as const, data: this.extractToolData(payload), result: payload };
  }

  async scenarioDcf(params: { code: string; baseRevenue?: number; industry?: string; years?: number }) {
    const payload = await this.callTool('scenario_dcf_valuation', {
      code: params.code, base_revenue: params.baseRevenue,
      industry: params.industry, years: params.years ?? 5,
    });
    return { sourceTool: 'scenario_dcf_valuation' as const, data: this.extractToolData(payload), result: payload };
  }

  async overview(code: string) {
    const [metrics, historical] = await Promise.all([
      this.fetchMetrics(code),
      this.fetchHistorical(code),
    ]);
    return {
      metrics: this.normalizeOverviewMetrics(this.extractToolData(metrics)),
      historical: this.extractToolData(historical),
      result: { metrics, historical },
    };
  }

  private async fetchMetrics(code: string) {
    try {
      return await this.mcpGatewayService.callTool('get_valuation_metrics', { code });
    } catch {
      return null;
    }
  }

  private async fetchHistorical(code: string) {
    try {
      return await this.mcpGatewayService.callTool('get_historical_valuation', { code, days: 365 });
    } catch {
      return null;
    }
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

  private normalizeOverviewMetrics(payload: unknown): StockValuationOverview {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return {};
    }
    const record = payload as Record<string, unknown>;
    return {
      pe: this.toNum(record.pe ?? record.pe_ratio ?? record.PE),
      pe_ttm: this.toNum(record.pe_ttm ?? record.peTtm ?? record.pe ?? record.pe_ratio ?? record.PE),
      pb: this.toNum(record.pb ?? record.pb_ratio ?? record.PB),
      ps: this.toNum(record.ps ?? record.ps_ratio ?? record.PS),
      pcf: this.toNum(record.pcf ?? record.pcf_ratio ?? record.PCF),
      market_cap: this.toNum(record.market_cap ?? record.marketCap ?? record.total_mv),
      float_market_cap: this.toNum(record.float_market_cap ?? record.cirMarketCap ?? record.circ_mv),
      pe_percentile: this.toNum(record.pe_percentile ?? record.pePercentile),
      pb_percentile: this.toNum(record.pb_percentile ?? record.pbPercentile),
      dividend_yield: this.toNum(record.dividend_yield ?? record.dividendYield),
      premium_percentile: this.toNum(record.premium_percentile ?? record.premiumPercentile),
    };
  }

  private toNum(value: unknown): number | undefined {
    if (value == null || value === '') return undefined;
    const n = Number(value);
    return Number.isFinite(n) ? n : undefined;
  }
}
