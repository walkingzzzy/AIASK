import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

export type CreatePortfolioInput = {
  name: string;
  description?: string;
  initialCapital?: number;
};

export type AddHoldingInput = {
  portfolioId: number;
  code: string;
  shares: number;
  costPrice: number;
};

export type NormalizedOptimization = {
  weights: Record<string, number>;
  expectedReturn: number | null;
  expectedRisk: number | null;
  sharpe: number | null;
};
export type NormalizedRiskAnalysis = {
  var95: number | null;
  var99: number | null;
  cvar: number | null;
  beta: number | null;
  volatility: number | null;
};
export type NormalizedStressTest = {
  scenarios: Array<{ name: string; impact: number | null; description: string }>;
};

@Injectable()
export class PortfolioService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async list() {
    const args = { action: 'list', kwargs: JSON.stringify({}) };
    const payload = await this.callTool('portfolio_manager', args);
    return { sourceTool: 'portfolio_manager' as const, argsMatched: args, result: payload };
  }

  async create(input: CreatePortfolioInput) {
    const args = {
      action: 'create',
      kwargs: JSON.stringify({
        name: input.name.trim(),
        description: input.description?.trim() || '',
        initial_capital: input.initialCapital ?? 100000,
      }),
    };
    const payload = await this.callTool('portfolio_manager', args);
    return { sourceTool: 'portfolio_manager' as const, argsMatched: args, result: payload };
  }

  async get(portfolioId: number) {
    const args = { action: 'get', kwargs: JSON.stringify({ portfolio_id: portfolioId }) };
    const payload = await this.callTool('portfolio_manager', args);
    return { portfolioId, sourceTool: 'portfolio_manager' as const, argsMatched: args, result: payload };
  }

  async addHolding(input: AddHoldingInput) {
    const args = {
      action: 'add_holding',
      kwargs: JSON.stringify({
        portfolio_id: input.portfolioId,
        code: input.code.trim(),
        shares: input.shares,
        cost_price: input.costPrice,
      }),
    };
    const payload = await this.callTool('portfolio_manager', args);
    return { sourceTool: 'portfolio_manager' as const, argsMatched: args, result: payload };
  }

  async removeHolding(portfolioId: number, code: string) {
    const args = {
      action: 'remove_holding',
      kwargs: JSON.stringify({ portfolio_id: portfolioId, code: code.trim() }),
    };
    const payload = await this.callTool('portfolio_manager', args);
    return { sourceTool: 'portfolio_manager' as const, argsMatched: args, result: payload };
  }

  async optimize(portfolioId: number) {
    const attempts = [
      { portfolio_id: portfolioId },
      { portfolioId },
    ];
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcpGatewayService.callTool('optimize_portfolio', args);
        return { sourceTool: 'optimize_portfolio' as const, result: payload, optimization: this.normalizeOptimization(payload) };
      } catch (e) { lastError = e; }
    }
    throw new BadGatewayException({ success: false, message: 'MCP optimize_portfolio 调用失败', detail: lastError instanceof Error ? lastError.message : String(lastError) });
  }

  async riskAnalysis(portfolioId: number) {
    const attempts = [
      { portfolio_id: portfolioId },
      { portfolioId },
    ];
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcpGatewayService.callTool('analyze_portfolio_risk', args);
        return { sourceTool: 'analyze_portfolio_risk' as const, result: payload, riskMetrics: this.normalizeRiskAnalysis(payload) };
      } catch (e) { lastError = e; }
    }
    throw new BadGatewayException({ success: false, message: 'MCP analyze_portfolio_risk 调用失败', detail: lastError instanceof Error ? lastError.message : String(lastError) });
  }

  async stressTest(portfolioId: number) {
    const attempts = [
      { portfolio_id: portfolioId },
      { portfolioId },
    ];
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcpGatewayService.callTool('stress_test_portfolio', args);
        return { sourceTool: 'stress_test_portfolio' as const, result: payload, stressResult: this.normalizeStressTest(payload) };
      } catch (e) { lastError = e; }
    }
    throw new BadGatewayException({ success: false, message: 'MCP stress_test_portfolio 调用失败', detail: lastError instanceof Error ? lastError.message : String(lastError) });
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private normalizeOptimization(payload: any): NormalizedOptimization {
    const d = payload?.data ?? payload ?? {};
    const w = d.weights ?? d.allocation ?? {};
    return {
      weights: typeof w === 'object' && w !== null ? Object.fromEntries(Object.entries(w).map(([k, v]) => [k, Number(v) || 0])) : {},
      expectedReturn: this.toNum(d.expected_return ?? d.expectedReturn),
      expectedRisk: this.toNum(d.expected_risk ?? d.expectedRisk ?? d.risk),
      sharpe: this.toNum(d.sharpe_ratio ?? d.sharpe),
    };
  }

  private normalizeRiskAnalysis(payload: any): NormalizedRiskAnalysis {
    const d = payload?.data ?? payload ?? {};
    return {
      var95: this.toNum(d.var_95 ?? d.var95 ?? d.VaR_95),
      var99: this.toNum(d.var_99 ?? d.var99 ?? d.VaR_99),
      cvar: this.toNum(d.cvar ?? d.CVaR ?? d.expected_shortfall),
      beta: this.toNum(d.beta ?? d.Beta),
      volatility: this.toNum(d.volatility ?? d.vol ?? d.std),
    };
  }

  private normalizeStressTest(payload: any): NormalizedStressTest {
    const d = payload?.data ?? payload ?? {};
    const list = Array.isArray(d) ? d : Array.isArray(d?.scenarios) ? d.scenarios : Array.isArray(d?.results) ? d.results : [];
    return {
      scenarios: list.map((s: any) => ({
        name: String(s.name ?? s.scenario ?? ''),
        impact: this.toNum(s.impact ?? s.loss ?? s.pnl),
        description: String(s.description ?? s.desc ?? ''),
      })),
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      return await this.mcpGatewayService.callTool(name, args);
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }
}

