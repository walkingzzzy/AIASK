import { BadGatewayException, Injectable } from '@nestjs/common';
import type {
  PerformanceAttributionComponent,
  PerformanceAttributionResponse,
  PerformanceBenchmarkAlignment,
  PerformanceBenchmarkComparisonResponse,
  PerformanceAttributionStockItem,
  PerformanceSectorPerformanceItem,
} from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

type PortfolioContext = {
  portfolioId: number;
  portfolioName: string | null;
  autoSelectedPortfolio: boolean;
};

@Injectable()
export class PerformanceService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async attribution(
    userId: string,
    portfolioId?: number,
    lookbackDays?: number,
    benchmark = '000300',
  ): Promise<PerformanceAttributionResponse> {
    const context = await this.resolvePortfolioContext(userId, portfolioId);
    if (!context) {
      return {
        message: '当前用户暂无组合，请先创建组合后再查看归因结果',
        portfolioId: null,
        portfolioName: null,
        autoSelectedPortfolio: false,
        benchmark,
        lookbackDays: this.normalizeLookbackDays(lookbackDays),
        attributionByStock: [],
        sectorPerformance: [],
        sourceTool: 'performance_manager',
        argsMatched: {},
      };
    }

    const normalizedLookbackDays = this.normalizeLookbackDays(lookbackDays);
    const argsMatched = {
      action: 'attribution',
      params: {
        portfolio_id: context.portfolioId,
        lookback_days: normalizedLookbackDays,
        benchmark,
      },
    };
    let payload: unknown;
    try {
      payload = await this.callManager('attribution', argsMatched.params);
    } catch (error) {
      const nonFatalMessage = this.extractNonFatalAttributionMessage(error);
      if (nonFatalMessage) {
        return this.buildAttributionFallback(context, benchmark, normalizedLookbackDays, argsMatched, nonFatalMessage);
      }
      throw error;
    }
    const record = this.extractDataRecord(payload);
    const dataWindow = this.asRecord(record.data_window);
    const attribution = this.asRecord(record.attribution);

    return {
      message: this.toStringValue(record.message),
      portfolioId: context.portfolioId,
      portfolioName: context.portfolioName,
      autoSelectedPortfolio: context.autoSelectedPortfolio,
      benchmark: this.toStringValue(record.benchmark) ?? benchmark,
      lookbackDays: this.toInt(dataWindow.lookback_days) ?? this.toInt(record.lookback_days) ?? normalizedLookbackDays,
      totalReturn: this.toNum(record.total_return),
      totalReturnPct: this.toNum(record.total_return_pct),
      attribution: {
        stockSelection: this.normalizeAttributionComponent(attribution.stock_selection),
        sectorAllocation: this.normalizeAttributionComponent(attribution.sector_allocation),
        timing: this.normalizeAttributionComponent(attribution.timing),
      },
      attributionByStock: this.normalizeAttributionByStock(
        this.pickArray(payload, ['data.attribution_by_stock', 'attribution_by_stock']),
      ),
      sectorPerformance: this.normalizeSectorPerformance(this.asRecord(record.sector_performance)),
      benchmarkAlignment: this.normalizeBenchmarkAlignment(this.asRecord(record.benchmark_alignment), benchmark),
      method: this.toStringValue(record.method),
      windowAudit: this.toRecordOrNull(record.window_audit),
      fees: this.toRecordOrNull(record.fees),
      sourceTool: 'performance_manager',
      argsMatched,
      result: payload,
    };
  }

  async benchmarkComparison(
    userId: string,
    portfolioId?: number,
    lookbackDays?: number,
    benchmark = '000300',
  ): Promise<PerformanceBenchmarkComparisonResponse> {
    const context = await this.resolvePortfolioContext(userId, portfolioId);
    if (!context) {
      return {
        message: '当前用户暂无组合，请先创建组合后再查看基准对比',
        portfolioId: null,
        portfolioName: null,
        autoSelectedPortfolio: false,
        benchmark,
        lookbackDays: this.normalizeLookbackDays(lookbackDays),
        sourceTool: 'performance_manager',
        argsMatched: {},
      };
    }

    const normalizedLookbackDays = this.normalizeLookbackDays(lookbackDays);
    const argsMatched = {
      action: 'benchmark_comparison',
      params: {
        portfolio_id: context.portfolioId,
        lookback_days: normalizedLookbackDays,
        benchmark,
      },
    };
    let payload: unknown;
    try {
      payload = await this.callManager('benchmark_comparison', argsMatched.params);
    } catch (error) {
      return this.buildBenchmarkComparisonFallback(
        context,
        benchmark,
        normalizedLookbackDays,
        argsMatched,
        this.extractNonFatalBenchmarkMessage(error),
      );
    }
    const record = this.extractDataRecord(payload);

    return {
      message: this.toStringValue(record.message),
      portfolioId: context.portfolioId,
      portfolioName: context.portfolioName,
      autoSelectedPortfolio: context.autoSelectedPortfolio,
      benchmark: this.toStringValue(record.benchmark) ?? benchmark,
      lookbackDays: this.toInt(record.lookback_days) ?? normalizedLookbackDays,
      alignedDays: this.toInt(record.aligned_days),
      portfolioReturn: this.toNum(record.portfolio_return),
      portfolioReturnPct: this.toNum(record.portfolio_return_pct),
      benchmarkReturn: this.toNum(record.benchmark_return),
      benchmarkReturnPct: this.toNum(record.benchmark_return_pct),
      excessReturn: this.toNum(record.excess_return),
      excessReturnPct: this.toNum(record.excess_return_pct),
      trackingError: this.toNum(record.tracking_error),
      trackingErrorPct: this.toNum(record.tracking_error_pct),
      annualizedExcessReturn: this.toNum(record.annualized_excess_return),
      annualizedExcessReturnPct: this.toNum(record.annualized_excess_return_pct),
      informationRatio: this.toNum(record.information_ratio),
      outperformance: typeof record.outperformance === 'boolean' ? record.outperformance : undefined,
      portfolioTotalReturnAccount: this.toNum(record.portfolio_total_return_account),
      portfolioTotalReturnSeries: this.toNum(record.portfolio_total_return_series),
      windowAudit: this.toRecordOrNull(record.window_audit),
      fees: this.toRecordOrNull(record.fees),
      sourceTool: 'performance_manager',
      argsMatched,
      result: payload,
    };
  }

  private async resolvePortfolioContext(userId: string, portfolioId?: number): Promise<PortfolioContext | null> {
    if (Number.isFinite(portfolioId) && Number(portfolioId) > 0) {
      const payload = await this.callTool('portfolio_manager', {
        action: 'get',
        kwargs: JSON.stringify({ user_id: userId, portfolio_id: Number(portfolioId) }),
      });
      const record = this.extractDataRecord(payload);
      const resolvedId = this.toInt(record.id ?? record.portfolioId ?? record.portfolio_id);
      if (!resolvedId) return null;
      return {
        portfolioId: resolvedId,
        portfolioName: this.toStringValue(record.name),
        autoSelectedPortfolio: false,
      };
    }

    const payload = await this.callTool('portfolio_manager', {
      action: 'list',
      kwargs: JSON.stringify({ user_id: userId }),
    });
    const first = this.pickArray(payload, ['data.portfolios', 'portfolios'])[0];
    const resolvedId = this.toInt(first?.id ?? first?.portfolioId ?? first?.portfolio_id);
    if (!resolvedId) return null;
    return {
      portfolioId: resolvedId,
      portfolioName: this.toStringValue(first?.name),
      autoSelectedPortfolio: true,
    };
  }

  private async callManager(action: string, params: Record<string, unknown>) {
    return this.callTool('performance_manager', {
      action,
      kwargs: JSON.stringify(params),
    });
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

  private buildAttributionFallback(
    context: PortfolioContext,
    benchmark: string,
    lookbackDays: number,
    argsMatched: { action: string; params: Record<string, unknown> },
    message: string,
  ): PerformanceAttributionResponse {
    return {
      message,
      portfolioId: context.portfolioId,
      portfolioName: context.portfolioName,
      autoSelectedPortfolio: context.autoSelectedPortfolio,
      benchmark,
      lookbackDays,
      attributionByStock: [],
      sectorPerformance: [],
      sourceTool: 'performance_manager',
      argsMatched,
    };
  }

  private buildBenchmarkComparisonFallback(
    context: PortfolioContext,
    benchmark: string,
    lookbackDays: number,
    argsMatched: { action: string; params: Record<string, unknown> },
    message: string,
  ): PerformanceBenchmarkComparisonResponse {
    return {
      message,
      portfolioId: context.portfolioId,
      portfolioName: context.portfolioName,
      autoSelectedPortfolio: context.autoSelectedPortfolio,
      benchmark,
      lookbackDays,
      sourceTool: 'performance_manager',
      argsMatched,
    };
  }

  private extractNonFatalAttributionMessage(error: unknown): string | null {
    const detail = this.extractExceptionDetail(error);
    if (!detail) return null;
    if (
      detail.includes('价格序列日期交集不足')
      || detail.includes('持仓数据不足')
      || detail.includes('无法计算择时贡献')
    ) {
      return detail;
    }
    return null;
  }

  private extractNonFatalBenchmarkMessage(error: unknown): string {
    const detail = this.extractExceptionDetail(error);
    if (
      detail.includes('价格序列日期交集不足')
      || detail.includes('持仓数据不足')
      || detail.includes('无法对齐基准')
      || detail.includes('benchmark')
      || detail.includes('基准')
    ) {
      return detail;
    }
    return detail || '当前无法获取基准对比，已返回空结果。';
  }

  private extractExceptionDetail(error: unknown): string {
    if (error instanceof BadGatewayException) {
      const response = error.getResponse();
      if (response && typeof response === 'object') {
        const body = response as Record<string, unknown>;
        if (typeof body.detail === 'string' && body.detail.trim()) {
          return body.detail;
        }
        if (typeof body.message === 'string' && body.message.trim()) {
          return body.message;
        }
      }
    }
    if (error instanceof Error) {
      return error.message;
    }
    return String(error ?? '');
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
      return String(record.error ?? record.message ?? 'performance tool error');
    }
    if (typeof record.data === 'string' && /error executing tool|validation error/i.test(record.data)) {
      return record.data;
    }
    return null;
  }

  private extractDataRecord(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return {};
    }
    const record = payload as Record<string, unknown>;
    const data = record.data;
    return data && typeof data === 'object' && !Array.isArray(data) ? data as Record<string, unknown> : record;
  }

  private pickArray(payload: unknown, paths: string[]) {
    for (const path of paths) {
      const value = this.readPath(payload, path);
      if (Array.isArray(value)) {
        return value
          .filter((item) => item && typeof item === 'object' && !Array.isArray(item))
          .map((item) => item as Record<string, unknown>);
      }
    }
    return [] as Record<string, unknown>[];
  }

  private normalizeAttributionByStock(rows: Record<string, unknown>[]): PerformanceAttributionStockItem[] {
    return rows.map((row) => ({
      code: this.toStringValue(row.code) ?? undefined,
      sector: this.toStringValue(row.sector) ?? undefined,
      weight: this.toNum(row.weight),
      weightPct: this.toNum(row.weight_pct),
      stockReturn: this.toNum(row.stock_return),
      stockReturnPct: this.toNum(row.stock_return_pct),
      lifetimeReturn: this.toNum(row.lifetime_return),
      lifetimeReturnPct: this.toNum(row.lifetime_return_pct),
      contribution: this.toNum(row.contribution),
      contributionPct: this.toNum(row.contribution_pct),
    }));
  }

  private normalizeSectorPerformance(source: Record<string, unknown>): PerformanceSectorPerformanceItem[] {
    return Object.entries(source)
      .map(([sector, value]) => {
        const record = this.asRecord(value);
        return {
          sector,
          weight: this.toNum(record.weight),
          weightPct: this.toNum(record.weight_pct),
          return: this.toNum(record.return),
          returnPct: this.toNum(record.return_pct),
        };
      })
      .sort((left, right) => (right.weightPct ?? 0) - (left.weightPct ?? 0));
  }

  private normalizeBenchmarkAlignment(
    source: Record<string, unknown>,
    fallbackBenchmark: string,
  ): PerformanceBenchmarkAlignment | null {
    if (!Object.keys(source).length) return null;
    return {
      benchmark: this.toStringValue(source.benchmark) ?? fallbackBenchmark,
      benchmarkReturn: this.toNum(source.benchmark_return),
      benchmarkReturnPct: this.toNum(source.benchmark_return_pct),
      excessReturn: this.toNum(source.excess_return),
      excessReturnPct: this.toNum(source.excess_return_pct),
      aligned: typeof source.aligned === 'boolean' ? source.aligned : undefined,
      alignmentMethod: this.toStringValue(source.alignment_method),
    };
  }

  private normalizeAttributionComponent(source: unknown): PerformanceAttributionComponent | null {
    const record = this.asRecord(source);
    if (!Object.keys(record).length) return null;
    return {
      return: this.toNum(record.return),
      contribution: this.toNum(record.contribution),
      description: this.toStringValue(record.description),
      status: this.toStringValue(record.status),
      basis: this.toStringValue(record.basis),
      alignedDays: this.toInt(record.aligned_days),
      assetsUsed: this.toInt(record.assets_used),
      staticTotalReturn: this.toNum(record.static_total_return),
      realizedTotalReturn: this.toNum(record.realized_total_return),
    };
  }

  private normalizeLookbackDays(days?: number) {
    const value = Number(days);
    if (!Number.isFinite(value) || value <= 0) return 90;
    return Math.min(Math.max(Math.trunc(value), 20), 2000);
  }

  private readPath(payload: unknown, path: string): unknown {
    return path.split('.').reduce<unknown>((current, segment) => {
      if (!current || typeof current !== 'object' || Array.isArray(current)) {
        return undefined;
      }
      return (current as Record<string, unknown>)[segment];
    }, payload);
  }

  private asRecord(value: unknown) {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
  }

  private toRecordOrNull(value: unknown) {
    const record = this.asRecord(value);
    return Object.keys(record).length > 0 ? record : null;
  }

  private toStringValue(value: unknown) {
    return typeof value === 'string' && value.trim().length > 0 ? value : null;
  }

  private toNum(value: unknown) {
    if (typeof value === 'string') {
      const normalized = value.replace(/[%\s,]/g, '');
      const number = Number(normalized);
      return Number.isFinite(number) ? number : null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  private toInt(value: unknown) {
    const number = this.toNum(value);
    return number == null ? null : Math.trunc(number);
  }
}
