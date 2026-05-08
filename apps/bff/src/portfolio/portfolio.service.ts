import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

export type CreatePortfolioInput = {
  name: string;
  description?: string;
  initialCapital?: number;
  strategies?: Array<{ strategyId: string; weight: number }>;
};

export type AddHoldingInput = {
  portfolioId: number;
  code: string;
  shares: number;
  costPrice?: number;
};

type StrategyAllocation = {
  strategyId: string;
  weight: number;
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
  riskContribution: Record<string, number>;
};
export type NormalizedStressTest = {
  scenarios: Array<{ name: string; impact: number | null; description: string }>;
};

@Injectable()
export class PortfolioService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async list(userId = 'default') {
    const args = this.managerArgs('list', { user_id: userId });
    const payload = await this.callTool('portfolio_manager', args);
    const portfolios = this.pickArray(payload, ['data.portfolios', 'portfolios'])
      .map((item) => this.normalizePortfolioRecord(item, { includeAllocations: false }));
    return {
      sourceTool: 'portfolio_manager' as const,
      argsMatched: args,
      portfolios,
      result: payload,
    };
  }

  async create(input: CreatePortfolioInput, userId = 'default') {
    const strategyAllocations = (input.strategies ?? [])
      .map((item) => ({
        strategy_id: String(item.strategyId ?? '').trim(),
        weight: Number(item.weight),
      }))
      .filter((item) => item.strategy_id && Number.isFinite(item.weight));

    const args = this.managerArgs('create', {
      name: input.name.trim(),
      user_id: userId,
      description: input.description?.trim() || '',
      initial_capital: input.initialCapital ?? 100000,
      ...(strategyAllocations.length > 0
        ? {
            metadata: {
              source: 'strategy_market_cart',
              strategy_allocations: strategyAllocations,
            },
          }
        : {}),
    });
    const payload = await this.callTool('portfolio_manager', args);
    return {
      sourceTool: 'portfolio_manager' as const,
      argsMatched: args,
      portfolioId: this.pickNumber(payload, ['data.portfolio_id', 'portfolio_id', 'data.id', 'id']),
      strategyAllocations: strategyAllocations.map((item) => ({
        strategyId: item.strategy_id,
        weight: item.weight,
      })),
      result: payload,
    };
  }

  async get(portfolioId: number, userId = 'default') {
    const detailArgs = this.managerArgs('get', { portfolio_id: portfolioId, user_id: userId });
    const holdingsArgs = this.managerArgs('get_holdings', { portfolio_id: portfolioId, user_id: userId });
    const [portfolioPayload, holdingsPayload] = await Promise.all([
      this.callTool('portfolio_manager', detailArgs),
      this.callTool('portfolio_manager', holdingsArgs),
    ]);
    const portfolio = this.extractDataRecord(portfolioPayload);
    const holdings = this.pickArray(holdingsPayload, ['data.holdings', 'holdings']);
    const initialCapital = this.pickNumber(portfolioPayload, ['data.initial_capital', 'initial_capital']) ?? 0;
    const currentValue = this.pickNumber(portfolioPayload, ['data.current_value', 'current_value']) ?? initialCapital;
    const totalReturn = initialCapital > 0 ? ((currentValue - initialCapital) / initialCapital) * 100 : 0;
    const normalizedPortfolio = this.normalizePortfolioRecord(portfolio, { includeAllocations: true });

    return {
      ...normalizedPortfolio,
      portfolioId,
      totalAssets: currentValue,
      totalReturn,
      holdings,
      sourceTool: 'portfolio_manager' as const,
      argsMatched: { detail: detailArgs, holdings: holdingsArgs },
      result: { portfolio: portfolioPayload, holdings: holdingsPayload },
    };
  }

  async addHolding(input: AddHoldingInput, userId = 'default') {
    const args = this.managerArgs('add_holding', {
      portfolio_id: input.portfolioId,
      user_id: userId,
      code: input.code.trim(),
      shares: input.shares,
      ...(input.costPrice != null ? { cost_price: input.costPrice } : {}),
    });
    const payload = await this.callTool('portfolio_manager', args);
    return {
      sourceTool: 'portfolio_manager' as const,
      argsMatched: args,
      added: this.pickBoolean(payload, ['data.added', 'added']) ?? true,
      result: payload,
    };
  }

  async removeHolding(portfolioId: number, code: string, userId = 'default') {
    const args = this.managerArgs('remove_holding', { portfolio_id: portfolioId, user_id: userId, code: code.trim() });
    const payload = await this.callTool('portfolio_manager', args);
    return {
      sourceTool: 'portfolio_manager' as const,
      argsMatched: args,
      removed: this.pickBoolean(payload, ['data.removed', 'removed']) ?? true,
      result: payload,
    };
  }

  async delete(portfolioId: number, userId = 'default') {
    const args = this.managerArgs('delete', { portfolio_id: portfolioId, user_id: userId });
    const payload = await this.callTool('portfolio_manager', args);
    return {
      sourceTool: 'portfolio_manager' as const,
      argsMatched: args,
      portfolioId,
      deleted: this.pickBoolean(payload, ['data.deleted', 'deleted']) ?? true,
      result: payload,
    };
  }

  async optimize(portfolioId: number, userId = 'default') {
    const context = await this.loadPortfolioContext(portfolioId, userId);
    const args = {
      stocks: context.codes,
      method: 'max_sharpe',
    };
    const payload = await this.callTool('optimize_portfolio', args);
    return {
      sourceTool: 'optimize_portfolio' as const,
      argsMatched: args,
      result: payload,
      optimization: this.normalizeOptimization(payload),
    };
  }

  async riskAnalysis(portfolioId: number, userId = 'default') {
    const context = await this.loadPortfolioContext(portfolioId, userId);
    const args = {
      holdings: context.weightedHoldings.map((item) => ({ code: item.code, weight: item.weight })),
    };
    const payload = await this.callTool('analyze_portfolio_risk', args);
    const riskContribution = await this.buildRiskContribution(context.weightedHoldings);
    return {
      sourceTool: 'analyze_portfolio_risk' as const,
      argsMatched: args,
      result: payload,
      riskMetrics: this.normalizeRiskAnalysis(payload, riskContribution),
    };
  }

  async stressTest(portfolioId: number, userId = 'default') {
    const context = await this.loadPortfolioContext(portfolioId, userId);
    const args = {
      holdings: context.weightedHoldings.map((item) => ({ code: item.code, weight: item.weight, value: item.value })),
    };
    const payload = await this.callTool('stress_test_portfolio', args);
    return {
      sourceTool: 'stress_test_portfolio' as const,
      argsMatched: args,
      result: payload,
      stressResult: this.normalizeStressTest(payload),
    };
  }

  private toNum(v: unknown): number | null {
    if (typeof v === 'string') {
      const normalized = v.replace(/[%\s,]/g, '');
      const n = Number(normalized);
      return Number.isFinite(n) ? n : null;
    }
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private normalizeOptimization(payload: unknown): NormalizedOptimization {
    const d = this.extractDataRecord(payload);
    const w = d.weights ?? d.allocation ?? {};
    return {
      weights: typeof w === 'object' && w !== null ? Object.fromEntries(Object.entries(w).map(([k, v]) => [k, Number(v) || 0])) : {},
      expectedReturn: this.toNum(d.expected_return ?? d.expectedReturn),
      expectedRisk: this.toNum(d.expected_risk ?? d.expectedRisk ?? d.risk ?? d.volatility),
      sharpe: this.toNum(d.sharpe_ratio ?? d.sharpe),
    };
  }

  private normalizeRiskAnalysis(payload: unknown, riskContribution: Record<string, number> = {}): NormalizedRiskAnalysis {
    const d = this.extractDataRecord(payload);
    const varBlock = this.readPath(d, 'var') as Record<string, unknown> | undefined;
    const riskBlock = this.readPath(d, 'risk') as Record<string, unknown> | undefined;
    return {
      var95: this.toNum(varBlock?.var_95 ?? d.var_95 ?? d.var95 ?? d.VaR_95),
      var99: this.toNum(varBlock?.var_99 ?? d.var_99 ?? d.var99 ?? d.VaR_99),
      cvar: this.toNum(varBlock?.cvar ?? d.cvar ?? d.CVaR ?? d.expected_shortfall),
      beta: this.toNum(riskBlock?.beta ?? d.beta ?? d.Beta),
      volatility: this.toNum(riskBlock?.portfolio_volatility ?? d.volatility ?? d.vol ?? d.std),
      riskContribution,
    };
  }

  private normalizeStressTest(payload: unknown): NormalizedStressTest {
    const d = this.extractDataRecord(payload);
    const stressTests = (this.readPath(d, 'stress_tests') as Record<string, unknown> | undefined) ?? {};
    const list: Record<string, unknown>[] = Array.isArray(d)
      ? (d as Record<string, unknown>[])
      : Array.isArray((d as Record<string, unknown>)?.scenarios)
        ? ((d as Record<string, unknown>).scenarios as Record<string, unknown>[])
        : Array.isArray((d as Record<string, unknown>)?.results)
          ? ((d as Record<string, unknown>).results as Record<string, unknown>[])
          : Object.entries(stressTests).map(([name, value]) => ({ name, ...(value as Record<string, unknown>) }));
    return {
      scenarios: list.map((scenario) => ({
        name: String(scenario.name ?? scenario.scenario ?? ''),
        impact: this.toNum(scenario.impact ?? scenario.loss ?? scenario.pnl ?? scenario.total_loss_pct ?? scenario.portfolio_impact_pct),
        description: String(scenario.description ?? scenario.desc ?? scenario.summary ?? ''),
      })),
    };
  }

  private normalizePortfolioRecord(
    record: Record<string, unknown>,
    options: { includeAllocations: boolean },
  ) {
    const strategyAllocations = this.extractStrategyAllocations(record);
    const summary = strategyAllocations.length > 0
      ? strategyAllocations
        .map((item) => `${item.strategyId}(${(item.weight * 100).toFixed(1).replace(/\.0$/, '')}%)`)
        .join(' / ')
      : '';

    const normalized = {
      id: this.toNum(record.id),
      name: record.name != null ? String(record.name) : '',
      description: record.description != null ? String(record.description) : '',
      userId: record.user_id != null ? String(record.user_id) : 'default',
      initialCapital: this.toNum(record.initial_capital) ?? 0,
      currentValue: this.toNum(record.current_value) ?? 0,
      createdAt: record.created_at != null ? String(record.created_at) : '',
      updatedAt: record.updated_at != null ? String(record.updated_at) : '',
      strategyAllocationCount: strategyAllocations.length,
      strategyAllocationSummary: summary || null,
    };

    if (options.includeAllocations) {
      return {
        ...normalized,
        strategyAllocations,
      };
    }

    return normalized;
  }

  private extractStrategyAllocations(record: Record<string, unknown>): StrategyAllocation[] {
    const metadata = this.parseMetadata(record.metadata);
    const raw = Array.isArray(metadata.strategy_allocations)
      ? metadata.strategy_allocations
      : Array.isArray(record.strategyAllocations)
        ? record.strategyAllocations
        : [];

    return raw
      .map((item) => {
        if (!item || typeof item !== 'object') return null;
        const row = item as Record<string, unknown>;
        const strategyId = String(row.strategy_id ?? row.strategyId ?? '').trim();
        const weight = this.toNum(row.weight);
        if (!strategyId || weight == null) return null;
        return { strategyId, weight };
      })
      .filter((item): item is StrategyAllocation => item != null);
  }

  private parseMetadata(value: unknown): Record<string, unknown> {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
    if (typeof value === 'string') {
      try {
        const parsed = JSON.parse(value);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed as Record<string, unknown>;
        }
      } catch {
        return {};
      }
    }
    return {};
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      const result = await this.mcpGatewayService.callTool(name, args);
      const toolError = this.extractToolError(result);
      if (toolError) {
        throw new Error(toolError);
      }
      return result;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private managerArgs(action: string, params: Record<string, unknown>) {
    return {
      action,
      kwargs: JSON.stringify(params),
    };
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      return /error executing tool|validation error/i.test(payload) ? payload : null;
    }
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const record = payload as Record<string, unknown>;
    if (record.success === false) {
      return String(record.error ?? record.message ?? 'portfolio tool error');
    }
    if (typeof record.data === 'string' && /error executing tool|validation error/i.test(record.data)) {
      return record.data;
    }
    return null;
  }

  private extractDataRecord(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object') {
      return {};
    }
    const record = payload as Record<string, unknown>;
    const data = record.data;
    return data && typeof data === 'object' && !Array.isArray(data) ? data as Record<string, unknown> : record;
  }

  private async loadPortfolioContext(portfolioId: number, userId = 'default') {
    const detailArgs = this.managerArgs('get', { portfolio_id: portfolioId, user_id: userId });
    const holdingsArgs = this.managerArgs('get_holdings', { portfolio_id: portfolioId, user_id: userId });
    const [detailPayload, holdingsPayload] = await Promise.all([
      this.callTool('portfolio_manager', detailArgs),
      this.callTool('portfolio_manager', holdingsArgs),
    ]);
    const portfolio = this.extractDataRecord(detailPayload);
    const holdings = this.pickArray(holdingsPayload, ['data.holdings', 'holdings']);

    if (!holdings.length) {
      throw new BadGatewayException({
        success: false,
        message: '组合暂无持仓，无法执行组合分析',
        detail: `portfolioId=${portfolioId}`,
      });
    }

    const rawHoldings = holdings
      .map((item) => {
        const code = String(item.code ?? '').trim();
        const shares = this.toNum(item.shares) ?? 0;
        const costPrice = this.toNum(item.cost_price ?? item.costPrice) ?? 1;
        return { code, shares, costPrice };
      })
      .filter((item) => item.code);

    const quoteMap = await this.loadCurrentPrices(rawHoldings.map((item) => item.code));
    const holdingsWithMarketValue = rawHoldings.map((item) => {
      const currentPrice = quoteMap.get(item.code) ?? item.costPrice;
      const value = Math.max((item.shares || 0) * (currentPrice || item.costPrice || 0), 1);
      return { ...item, currentPrice, value };
    });

    const totalValue = holdingsWithMarketValue.reduce((sum, item) => sum + item.value, 0) || holdingsWithMarketValue.length;
    const weightedHoldings = holdingsWithMarketValue.map((item) => ({
      ...item,
      weight: totalValue > 0 ? item.value / totalValue : 1 / rawHoldings.length,
    }));

    return {
      portfolio,
      holdings,
      codes: weightedHoldings.map((item) => item.code),
      weightedHoldings,
    };
  }

  private async loadCurrentPrices(codes: string[]) {
    const normalizedCodes = Array.from(new Set(codes.map((code) => code.trim()).filter(Boolean)));
    const priceMap = new Map<string, number>();
    if (!normalizedCodes.length) {
      return priceMap;
    }

    try {
      const payload = await this.callTool('get_batch_quotes', { stock_codes: normalizedCodes });
      const quotes = this.pickArray(payload, ['data.quotes', 'data', 'quotes']);
      quotes.forEach((quote) => {
        const code = String(quote.code ?? quote.symbol ?? '').trim();
        const price = this.toNum(quote.price ?? quote.last ?? quote.close);
        if (code && price != null && price > 0) {
          priceMap.set(code, price);
        }
      });
      return priceMap;
    } catch {
      return priceMap;
    }
  }

  private async buildRiskContribution(
    holdings: Array<{ code: string; weight: number }>,
  ): Promise<Record<string, number>> {
    if (!holdings.length) {
      return {};
    }
    if (holdings.length === 1) {
      return { [holdings[0].code]: 1 };
    }

    const returnsSeries = await Promise.all(
      holdings.map(async (holding) => ({
        code: holding.code,
        weight: holding.weight,
        returns: await this.loadDailyReturns(holding.code),
      })),
    );

    const usable = returnsSeries.filter((item) => item.returns.length >= 2);
    if (usable.length < 2) {
      return this.fallbackRiskContribution(holdings);
    }

    const minLength = Math.min(...usable.map((item) => item.returns.length));
    if (!Number.isFinite(minLength) || minLength < 2) {
      return this.fallbackRiskContribution(holdings);
    }

    const aligned = usable.map((item) => item.returns.slice(-minLength));
    const weights = usable.map((item) => item.weight);
    const covariance = aligned.map((rowI) =>
      aligned.map((rowJ) => this.sampleCovariance(rowI, rowJ)),
    );

    const sigmaW = covariance.map((row) =>
      row.reduce((sum, value, index) => sum + value * weights[index], 0),
    );
    const portfolioVariance = sigmaW.reduce((sum, value, index) => sum + weights[index] * value, 0);
    if (!Number.isFinite(portfolioVariance) || portfolioVariance <= 0) {
      return this.fallbackRiskContribution(holdings);
    }

    const raw = usable.map((item, index) => ({
      code: item.code,
      contribution: Math.max((weights[index] * sigmaW[index]) / portfolioVariance, 0),
    }));
    const total = raw.reduce((sum, item) => sum + item.contribution, 0);
    if (!Number.isFinite(total) || total <= 0) {
      return this.fallbackRiskContribution(holdings);
    }

    return Object.fromEntries(raw.map((item) => [item.code, item.contribution / total]));
  }

  private async loadDailyReturns(code: string) {
    try {
      const payload = await this.callTool('get_kline_data', {
        code,
        period: 'daily',
        limit: 120,
        start_date: '',
        end_date: '',
        adjust: '',
      });
      const kline = this.pickArray(payload, ['data', 'data.kline', 'kline']);
      const closes = kline
        .map((point) => this.toNum(point.close ?? point.收盘))
        .filter((value): value is number => value != null && value > 0);
      if (closes.length < 2) {
        return [];
      }
      return closes.slice(1).map((value, index) => {
        const prev = closes[index];
        return prev > 0 ? (value - prev) / prev : 0;
      });
    } catch {
      return [];
    }
  }

  private sampleCovariance(left: number[], right: number[]) {
    const length = Math.min(left.length, right.length);
    if (length < 2) {
      return 0;
    }
    const leftMean = left.slice(0, length).reduce((sum, value) => sum + value, 0) / length;
    const rightMean = right.slice(0, length).reduce((sum, value) => sum + value, 0) / length;
    let total = 0;
    for (let index = 0; index < length; index += 1) {
      total += (left[index] - leftMean) * (right[index] - rightMean);
    }
    return total / (length - 1);
  }

  private fallbackRiskContribution(holdings: Array<{ code: string; weight: number }>) {
    const totalWeight = holdings.reduce((sum, holding) => sum + Math.max(holding.weight, 0), 0);
    if (totalWeight <= 0) {
      return Object.fromEntries(holdings.map((holding) => [holding.code, 1 / holdings.length]));
    }
    return Object.fromEntries(
      holdings.map((holding) => [holding.code, Math.max(holding.weight, 0) / totalWeight]),
    );
  }

  private readPath(obj: unknown, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, key) => {
      if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
        return undefined;
      }
      return (acc as Record<string, unknown>)[key];
    }, obj);
  }

  private pickArray(payload: unknown, paths: string[]): Record<string, unknown>[] {
    for (const path of paths) {
      const value = this.readPath(payload, path);
      if (Array.isArray(value)) {
        return value as Record<string, unknown>[];
      }
    }
    return [];
  }

  private pickNumber(payload: unknown, paths: string[]): number | null {
    for (const path of paths) {
      const value = this.readPath(payload, path);
      const number = this.toNum(value);
      if (number != null) {
        return number;
      }
    }
    return null;
  }

  private pickBoolean(payload: unknown, paths: string[]): boolean | null {
    for (const path of paths) {
      const value = this.readPath(payload, path);
      if (typeof value === 'boolean') {
        return value;
      }
    }
    return null;
  }
}
