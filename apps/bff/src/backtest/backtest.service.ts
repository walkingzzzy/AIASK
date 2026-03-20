import { BadGatewayException, Injectable } from '@nestjs/common';
import type {
  BacktestBatchFailure,
  BacktestBatchResponse,
  BacktestBatchResultItem,
  BacktestMetricSnapshot,
  BacktestMetricsResponse,
  BacktestRunResponse,
} from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

export type RunBacktestInput = {
  code: string;
  strategy: string;
  startDate?: string;
  endDate?: string;
  initialCapital?: number;
  shortPeriod?: number;
  longPeriod?: number;
  lookback?: number;
  threshold?: number;
  rsiPeriod?: number;
  oversold?: number;
  overbought?: number;
  commission?: number;
  slippage?: number;
  artifactId?: string;
};

export type BatchBacktestInput = {
  codes: string[];
  strategy: string;
  startDate?: string;
  endDate?: string;
  initialCapital?: number;
  commission?: number;
  shortPeriod?: number;
  longPeriod?: number;
};

@Injectable()
export class BacktestService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async run(input: RunBacktestInput): Promise<BacktestRunResponse> {
    const requestedArtifactId =
      typeof input.artifactId === 'string' && input.artifactId.trim().length > 0
        ? input.artifactId.trim()
        : undefined;
    const normalized: Record<string, unknown> = {
      code: input.code.trim(),
      strategy: input.strategy.trim() || 'ma_cross',
      start_date: input.startDate || null,
      end_date: input.endDate || null,
      initial_capital: input.initialCapital ?? 100000,
      short_period: input.shortPeriod ?? 5,
      long_period: input.longPeriod ?? 20,
      lookback: input.lookback ?? 20,
      threshold: input.threshold ?? 0.02,
      rsi_period: input.rsiPeriod ?? 14,
      oversold: input.oversold ?? 30,
      overbought: input.overbought ?? 70,
      artifact_id: requestedArtifactId,
    };
    if (input.commission != null) normalized.commission = input.commission;
    if (input.slippage != null) normalized.slippage = input.slippage;

    const args = { action: 'run', kwargs: JSON.stringify(normalized) };
    const payload: any = await this.callTool('backtest_manager', args);
    const artifactId =
      this.pickString(payload, ['data.artifact_id', 'data.artifactId', 'artifact_id', 'artifactId']) ||
      requestedArtifactId ||
      `art_${normalized.code}_${Date.now()}`;

    const engineResult = this.pickObject(payload, [
      'data.result.result',
      'data.result.data.result',
      'data.result',
      'result.result',
      'result.data.result',
      'result',
      'data',
    ]) ?? {};

    return {
      artifactId,
      backtestId: this.pickString(payload, ['data.backtest_id', 'data.id', 'backtest_id', 'id']),
      sourceTool: 'backtest_manager' as const,
      argsMatched: args,
      result: payload,
      metrics: this.normalizeMetrics(engineResult),
      equity_curve: Array.isArray(engineResult.equity_curve) ? engineResult.equity_curve : [],
      dates: Array.isArray(engineResult.dates) ? engineResult.dates : [],
      trades: Array.isArray(engineResult.trades) ? engineResult.trades : [],
      profit_factor: this.toNum(engineResult.profit_factor),
      initial_capital: this.toNum(engineResult.initial_capital),
      final_capital: this.toNum(engineResult.final_capital),
    };
  }

  async list(limit = 10) {
    const args = { action: 'list', kwargs: JSON.stringify({ limit: Math.min(Math.max(limit, 1), 100) }) };
    const payload = await this.callTool('backtest_manager', args);
    return {
      sourceTool: 'backtest_manager' as const,
      argsMatched: args,
      result: payload,
      items: this.pickArray(payload, ['data.results', 'results', 'data.items', 'items']),
    };
  }

  async metricsByArtifact(artifactId: string): Promise<BacktestMetricsResponse> {
    const args = { action: 'backtest_metrics', kwargs: JSON.stringify({ artifact_id: artifactId.trim() }) };
    const payload = await this.callTool('performance_manager', args);
    return {
      artifactId: artifactId.trim(),
      sourceTool: 'performance_manager' as const,
      argsMatched: args,
      result: payload,
      metrics: this.normalizeMetrics(payload),
    };
  }

  /** P3-3: Batch backtest multiple codes */
  async batch(input: BatchBacktestInput): Promise<BacktestBatchResponse> {
    const args: Record<string, unknown> = {
      codes: input.codes,
      strategy: input.strategy,
      initial_capital: input.initialCapital ?? 100000,
    };
    if (input.startDate) args.start_date = input.startDate;
    if (input.endDate) args.end_date = input.endDate;
    if (input.commission != null) args.commission = input.commission;
    if (input.shortPeriod != null) args.short_period = input.shortPeriod;
    if (input.longPeriod != null) args.long_period = input.longPeriod;
    const payload = await this.callTool('run_batch_backtest', args);
    const results = this.normalizeBatchResults(
      this.pickArray(payload, ['data.results', 'results']),
      input.codes,
    );
    const failed = results
      .filter((row) => row.success === false && row.code)
      .map((row) => ({
        code: String(row.code),
        reasonCode: String(row.reasonCode ?? 'missing_result'),
        reason: String(row.reason ?? '未返回回测结果'),
        failedMetric: row.failedMetric ?? null,
      })) satisfies BacktestBatchFailure[];
    return {
      sourceTool: 'run_batch_backtest' as const,
      argsMatched: args,
      result: payload,
      results,
      failed,
      summary: this.pickObject(payload, ['data.summary', 'summary']) ?? undefined,
    };
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

  private normalizeMetrics(payload: any): BacktestMetricSnapshot {
    const d =
      this.pickObject(payload, ['data.metrics', 'metrics', 'result', 'data', 'payload']) ??
      payload ??
      {};
    return {
      totalReturn: this.toPercent(d.total_return ?? d.totalReturn ?? d.cumulative_return),
      sharpe: this.toNum(d.sharpe_ratio ?? d.sharpe ?? d.sharpeRatio),
      maxDrawdown: this.toPercent(d.max_drawdown ?? d.maxDrawdown),
      winRate: this.toPercent(d.win_rate ?? d.winRate),
      totalTrades: this.toNum(d.total_trades ?? d.totalTrades ?? d.trade_count ?? d.trades_count),
      profitFactor: this.toNum(d.profit_factor ?? d.profitFactor),
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

  private toPercent(v: unknown): number | null {
    const n = this.toNum(v);
    if (n == null) return null;
    return Math.abs(n) <= 1 ? n * 100 : n;
  }

  private normalizeBatchResults(rows: unknown[], requestedCodes: string[]): BacktestBatchResultItem[] {
    const mapped = rows.map((row) => {
      const record = (row && typeof row === 'object') ? { ...(row as Record<string, unknown>) } : {};
      if ('total_return' in record) record.total_return = this.toPercent(record.total_return);
      if ('max_drawdown' in record) record.max_drawdown = this.toPercent(record.max_drawdown);
      if ('win_rate' in record) record.win_rate = this.toPercent(record.win_rate);
      return {
        ...record,
        code: typeof record.code === 'string' ? record.code : undefined,
        success: record.success === false ? false : true,
        reasonCode: typeof record.reason_code === 'string' ? record.reason_code : null,
        reason: typeof record.reason === 'string' ? record.reason : null,
        failedMetric:
          record.failed_metric && typeof record.failed_metric === 'object' && !Array.isArray(record.failed_metric)
            ? (record.failed_metric as BacktestBatchResultItem['failedMetric'])
            : null,
      } satisfies BacktestBatchResultItem;
    });

    const rowMap = new Map(
      mapped
        .filter((item) => typeof item.code === 'string' && item.code.trim().length > 0)
        .map((item) => [String(item.code), item]),
    );

    return requestedCodes.map((code) => rowMap.get(code) ?? {
      code,
      success: false,
      reasonCode: 'missing_result',
      reason: '未返回回测结果，通常因为 K 线数据不足或上游回测执行失败',
      failedMetric: null,
    });
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
      return String(record.error ?? record.message ?? 'backtest tool error');
    }
    if (typeof record.data === 'string' && /error executing tool|validation error/i.test(record.data)) {
      return record.data;
    }
    return null;
  }

  private pickString(payload: any, paths: string[]): string | null {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (typeof v === 'string' && v.trim()) return v.trim();
      if (typeof v === 'number' && Number.isFinite(v)) return String(v);
    }
    return null;
  }

  private pickArray(payload: any, paths: string[]): unknown[] {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (Array.isArray(v)) return v;
    }
    return [];
  }

  private pickObject(payload: any, paths: string[]): Record<string, unknown> | null {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        return v as Record<string, unknown>;
      }
    }
    return null;
  }

  private readPath(obj: any, path: string): unknown {
    return path.split('.').reduce((acc: any, key: string) => (acc == null ? undefined : acc[key]), obj);
  }
}
