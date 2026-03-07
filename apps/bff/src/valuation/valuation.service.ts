import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class ValuationService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async dcf(params: { code: string; discountRate?: number; growthRate?: number; years?: number }) {
    const payload = await this.callTool('dcf_valuation', {
      code: params.code, discount_rate: params.discountRate ?? 0.1,
      growth_rate: params.growthRate ?? 0.05, years: params.years ?? 5,
    });
    return { sourceTool: 'dcf_valuation' as const, result: payload };
  }

  async ddm(params: { code: string; dividend?: number; growthRate?: number; requiredReturn?: number }) {
    const payload = await this.callTool('ddm_valuation', {
      code: params.code, dividend: params.dividend,
      growth_rate: params.growthRate ?? 0.03, required_return: params.requiredReturn ?? 0.08,
    });
    return { sourceTool: 'ddm_valuation' as const, result: payload };
  }

  async relative(params: { code: string; metrics?: string[]; peers?: string[] }) {
    const payload = await this.callTool('relative_valuation', {
      code: params.code, metrics: params.metrics ?? ['pe', 'pb', 'ps'],
      peers: params.peers,
    });
    return { sourceTool: 'relative_valuation' as const, result: payload };
  }

  async scenarioDcf(params: { code: string; baseRevenue?: number; industry?: string; years?: number }) {
    const payload = await this.callTool('scenario_dcf_valuation', {
      code: params.code, base_revenue: params.baseRevenue,
      industry: params.industry, years: params.years ?? 5,
    });
    return { sourceTool: 'scenario_dcf_valuation' as const, result: payload };
  }

  async overview(code: string) {
    const [metrics, historical] = await Promise.all([
      this.fetchMetrics(code),
      this.fetchHistorical(code),
    ]);
    return { metrics, historical };
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
}
