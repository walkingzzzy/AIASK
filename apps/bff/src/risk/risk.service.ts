import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type RiskSummaryInput = {
  userId?: string;
  portfolioId?: number;
  lookbackDays?: number;
  injectFail?: 'var' | 'stress' | 'exposure';
};

type SafeCall = { ok: true; data: unknown } | { ok: false; error: string };

@Injectable()
export class RiskService {
  private static readonly SUMMARY_TTL_SECONDS = 60;

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async getSummary(input: RiskSummaryInput) {
    const userId = String(input.userId ?? 'default');
    const portfolioId = Number.isFinite(input.portfolioId) ? input.portfolioId : undefined;
    const lookbackDays = Number.isFinite(input.lookbackDays)
      ? Math.min(Math.max(Number(input.lookbackDays), 30), 2000)
      : 252;
    const injectFail = input.injectFail;

    const cacheKey = `risk:summary:${userId}:${portfolioId ?? 'auto'}:${lookbackDays}:${injectFail ?? 'none'}`;
    const ttlSeconds = this.cacheService.resolveTtl('risk.summary', RiskService.SUMMARY_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<any>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const riskContext = await this.resolveRiskContext(userId, portfolioId);
    if (riskContext.mode === 'empty') {
      const result = {
        portfolioId: null,
        lookbackDays,
        injectedFail: injectFail ?? null,
        sourceContext: riskContext,
        sourceTools: {
          var: 'risk_manager' as const,
          stress: 'risk_manager' as const,
          exposure: 'risk_manager' as const,
        },
        argsMatched: { var: null, stress: null, exposure: null },
        varResult: null,
        stressResult: null,
        exposureResult: null,
        moduleStatus: {
          var: { ok: false, reason: riskContext.reason },
          stress: { ok: false, reason: riskContext.reason },
          exposure: { ok: false, reason: riskContext.reason },
        },
        degraded: false,
        empty: true,
        degradeReasons: [],
        meta: {
          fetchedAt: new Date().toISOString(),
          cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds },
        },
      };
      await this.cacheService.set(cacheKey, result, ttlSeconds);
      return result;
    }

    const varKwargs: Record<string, unknown> = { lookback_days: lookbackDays };
    const exposureKwargs: Record<string, unknown> = {};
    const stressKwargs: Record<string, unknown> = { scenarios: ['market_crash', 'sector_rotation'] };
    if (riskContext.mode === 'portfolio') {
      varKwargs.portfolio_id = riskContext.portfolioId;
      exposureKwargs.portfolio_id = riskContext.portfolioId;
      stressKwargs.portfolio_id = riskContext.portfolioId;
    } else {
      varKwargs.codes = [...riskContext.codes];
      varKwargs.weights = [...riskContext.weights];
      varKwargs.portfolio_value = riskContext.portfolioValue;

      exposureKwargs.codes = [...riskContext.codes];
      exposureKwargs.weights = [...riskContext.weights];
      exposureKwargs.portfolio_value = riskContext.portfolioValue;

      stressKwargs.codes = [...riskContext.codes];
      stressKwargs.weights = [...riskContext.weights];
      stressKwargs.portfolio_value = riskContext.portfolioValue;
    }

    const [varResult, stressResult, exposureResult] = await Promise.all([
      this.maybeInjectedCall('var', injectFail, 'risk_manager', 'calculate_var', varKwargs),
      this.maybeInjectedCall('stress', injectFail, 'risk_manager', 'stress_test', stressKwargs),
      this.maybeInjectedCall('exposure', injectFail, 'risk_manager', 'risk_exposure', exposureKwargs),
    ]);

    const degraded = !varResult.ok || !stressResult.ok || !exposureResult.ok;
    const degradeReasons = [varResult, stressResult, exposureResult]
      .filter((x) => !x.ok)
      .map((x) => x.error);

    const result = {
      portfolioId: riskContext.mode === 'portfolio' ? riskContext.portfolioId : null,
      lookbackDays,
      injectedFail: injectFail ?? null,
      sourceContext: riskContext,
      sourceTools: {
        var: 'risk_manager' as const,
        stress: 'risk_manager' as const,
        exposure: 'risk_manager' as const,
      },
      argsMatched: {
        var: { action: 'calculate_var', params: varKwargs },
        stress: { action: 'stress_test', params: stressKwargs },
        exposure: { action: 'risk_exposure', params: exposureKwargs },
      },
      varResult: varResult.ok ? varResult.data : null,
      stressResult: stressResult.ok ? stressResult.data : null,
      exposureResult: exposureResult.ok ? exposureResult.data : null,
      moduleStatus: {
        var: { ok: varResult.ok, reason: varResult.ok ? null : varResult.error },
        stress: { ok: stressResult.ok, reason: stressResult.ok ? null : stressResult.error },
        exposure: { ok: exposureResult.ok, reason: exposureResult.ok ? null : exposureResult.error },
      },
      degraded,
      empty: false,
      degradeReasons,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none' as const, key: cacheKey, ttlSeconds },
      },
    };

    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  private maybeInjectedCall(
    channel: 'var' | 'stress' | 'exposure',
    injectFail: RiskSummaryInput['injectFail'],
    tool: string,
    action: string,
    params: Record<string, unknown>,
  ): Promise<SafeCall> {
    if (injectFail === channel) {
      return Promise.resolve({ ok: false, error: `${action}: injected failure for week4.1` });
    }
    return this.safeManagerCall(tool, action, params);
  }

  private async safeManagerCall(tool: string, action: string, params: Record<string, unknown>): Promise<SafeCall> {
    try {
      const data = await this.mcpGatewayService.callTool(tool, {
        action,
        kwargs: params,
      });
      const toolError = this.extractToolError(data);
      if (toolError) {
        return { ok: false as const, error: `${action}: ${toolError}` };
      }
      return { ok: true as const, data };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return { ok: false as const, error: `${action}: ${message}` };
    }
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      const text = payload.trim();
      if (!text) return null;
      return /^Error executing tool\b/i.test(text) || /\bvalidation error\b/i.test(text) ? text : null;
    }

    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return null;
    }

    const record = payload as Record<string, unknown>;
    if (record.success === false) {
      if (typeof record.message === 'string' && record.message.trim()) {
        return record.message;
      }
      if (typeof record.error === 'string' && record.error.trim()) {
        return record.error;
      }
      if (record.error && typeof record.error === 'object') {
        const nested = record.error as Record<string, unknown>;
        if (typeof nested.message === 'string' && nested.message.trim()) {
          return nested.message;
        }
      }
    }

    return null;
  }

  async getVarOnly(input: RiskSummaryInput) {
    try {
      const summary = await this.getSummary(input);
      return {
        portfolioId: summary.portfolioId,
        lookbackDays: summary.lookbackDays,
        sourceContext: summary.sourceContext ?? null,
        sourceTool: summary.sourceTools.var,
        argsMatched: summary.argsMatched.var,
        result: summary.varResult,
        degraded: summary.varResult == null,
        degradedReason: summary.moduleStatus?.var?.reason ?? null,
        meta: summary.meta,
      };
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '获取 VaR 数据失败',
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async resolveRiskContext(userId: string, requestedPortfolioId?: number) {
    if (requestedPortfolioId !== undefined) {
      const owned = await this.portfolioExistsForUser(userId, requestedPortfolioId);
      if (owned) {
        return { mode: 'portfolio' as const, portfolioId: requestedPortfolioId };
      }
    }

    const latestPortfolioId = await this.findLatestPortfolioId(userId);
    if (latestPortfolioId != null) {
      return { mode: 'portfolio' as const, portfolioId: latestPortfolioId };
    }

    const paperContext = await this.loadPaperTradingWeights(userId);
    if (paperContext) {
      return {
        mode: 'paper-trading' as const,
        accountId: paperContext.accountId,
        codes: paperContext.codes,
        weights: paperContext.weights,
        portfolioValue: paperContext.portfolioValue,
      };
    }

    return {
      mode: 'empty' as const,
      reason: '当前用户暂无组合或模拟持仓，无法生成风险汇总',
    };
  }

  private async findLatestPortfolioId(userId: string) {
    try {
      const payload = await this.mcpGatewayService.callTool('portfolio_manager', {
        action: 'list',
        kwargs: JSON.stringify({ user_id: userId }),
      });
      const record = this.extractDataRecord(payload);
      const portfolios = Array.isArray(record.portfolios) ? record.portfolios as Record<string, unknown>[] : [];
      const first = portfolios[0];
      const portfolioId = Number(first?.id ?? first?.portfolio_id);
      return Number.isFinite(portfolioId) ? portfolioId : null;
    } catch {
      return null;
    }
  }

  private async portfolioExistsForUser(userId: string, portfolioId: number) {
    try {
      const payload = await this.mcpGatewayService.callTool('portfolio_manager', {
        action: 'get',
        kwargs: JSON.stringify({ user_id: userId, portfolio_id: portfolioId }),
      });
      const record = this.extractDataRecord(payload);
      const id = Number(record.id ?? record.portfolio_id);
      return Number.isFinite(id);
    } catch {
      return false;
    }
  }

  private async loadPaperTradingWeights(userId: string) {
    try {
      const payload = await this.mcpGatewayService.callTool('paper_trading_manager', {
        action: 'positions',
        kwargs: JSON.stringify({ user_id: userId }),
      });
      const record = this.extractDataRecord(payload);
      const positions = Array.isArray(record.positions)
        ? record.positions as Record<string, unknown>[]
        : Array.isArray(record.items)
          ? record.items as Record<string, unknown>[]
          : [];
      const usable = positions
        .map((position) => {
          const code = String(position.stock_code ?? position.code ?? '').trim();
          const marketValue = Number(position.market_value ?? position.marketValue ?? 0);
          const quantity = Number(position.quantity ?? position.shares ?? 0);
          const currentPrice = Number(position.current_price ?? position.currentPrice ?? position.price ?? 0);
          const costPrice = Number(position.cost_price ?? position.costPrice ?? 0);
          const fallbackValue = quantity * (currentPrice > 0 ? currentPrice : costPrice);
          const value = marketValue > 0 ? marketValue : fallbackValue;
          return { code, value };
        })
        .filter((position) => position.code && Number.isFinite(position.value) && position.value > 0);

      if (!usable.length) {
        return null;
      }

      const portfolioValue = usable.reduce((sum, position) => sum + position.value, 0);
      if (!Number.isFinite(portfolioValue) || portfolioValue <= 0) {
        return null;
      }

      return {
        accountId: String(record.account_id ?? record.accountId ?? ''),
        portfolioValue,
        codes: usable.map((position) => position.code),
        weights: usable.map((position) => position.value / portfolioValue),
      };
    } catch {
      return null;
    }
  }

  private extractDataRecord(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return {};
    }
    const record = payload as Record<string, unknown>;
    const data = record.data;
    return data && typeof data === 'object' && !Array.isArray(data) ? data as Record<string, unknown> : record;
  }
}
