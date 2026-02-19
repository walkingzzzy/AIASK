import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type RiskSummaryInput = {
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
    const portfolioId = Number.isFinite(input.portfolioId) ? input.portfolioId : undefined;
    const lookbackDays = Number.isFinite(input.lookbackDays)
      ? Math.min(Math.max(Number(input.lookbackDays), 30), 2000)
      : 252;
    const injectFail = input.injectFail;

    const cacheKey = `risk:summary:${portfolioId ?? 'all'}:${lookbackDays}:${injectFail ?? 'none'}`;
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

    const varKwargs: Record<string, unknown> = { lookback_days: lookbackDays };
    const exposureKwargs: Record<string, unknown> = {};
    const stressKwargs: Record<string, unknown> = { scenarios: ['market_crash', 'sector_rotation'] };
    if (portfolioId !== undefined) {
      varKwargs.portfolio_id = portfolioId;
      exposureKwargs.portfolio_id = portfolioId;
      stressKwargs.portfolio_id = portfolioId;
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
      portfolioId: portfolioId ?? null,
      lookbackDays,
      injectedFail: injectFail ?? null,
      sourceTools: {
        var: 'risk_manager' as const,
        stress: 'risk_manager' as const,
        exposure: 'risk_manager' as const,
      },
      argsMatched: {
        var: { action: 'calculate_var', kwargs: JSON.stringify(varKwargs) },
        stress: { action: 'stress_test', kwargs: JSON.stringify(stressKwargs) },
        exposure: { action: 'risk_exposure', kwargs: JSON.stringify(exposureKwargs) },
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
    kwargs: Record<string, unknown>,
  ): Promise<SafeCall> {
    if (injectFail === channel) {
      return Promise.resolve({ ok: false, error: `${action}: injected failure for week4.1` });
    }
    return this.safeManagerCall(tool, action, kwargs);
  }

  private async safeManagerCall(tool: string, action: string, kwargs: Record<string, unknown>): Promise<SafeCall> {
    try {
      const data = await this.mcpGatewayService.callTool(tool, {
        action,
        kwargs: JSON.stringify(kwargs),
      });
      return { ok: true as const, data };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return { ok: false as const, error: `${action}: ${message}` };
    }
  }

  async getVarOnly(input: RiskSummaryInput) {
    try {
      const summary = await this.getSummary(input);
      return {
        portfolioId: summary.portfolioId,
        lookbackDays: summary.lookbackDays,
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
}

