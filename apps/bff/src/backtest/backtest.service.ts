import { BadGatewayException, Injectable } from '@nestjs/common';
import type {
  BacktestBatchFailure,
  BacktestBatchResponse,
  BacktestBatchResultItem,
  BacktestMetricSnapshot,
  BacktestMetricsResponse,
  BacktestOptimizationCandidate,
  BacktestOptimizationResponse,
  BacktestRunResponse,
  BacktestWalkForwardFold,
  BacktestWalkForwardResponse,
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

export type OptimizeBacktestInput = RunBacktestInput & {
  objective?: 'balanced' | 'sharpe' | 'total_return';
  topN?: number;
  maxCandidates?: number;
};

export type WalkForwardBacktestInput = RunBacktestInput & {
  objective?: 'balanced' | 'sharpe' | 'total_return';
  trainDays?: number;
  testDays?: number;
  stepDays?: number;
  maxFolds?: number;
};

@Injectable()
export class BacktestService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async run(input: RunBacktestInput): Promise<BacktestRunResponse> {
    const { normalized, requestedArtifactId, args } = this.buildRunArgs(input);
    const payload = await this.callTool('backtest_manager', args);
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

  async optimize(input: OptimizeBacktestInput): Promise<BacktestOptimizationResponse> {
    const objective = this.normalizeObjective(input.objective);
    const candidates = this.buildParameterCandidates(input).slice(
      0,
      Math.max(1, Math.min(input.maxCandidates ?? 12, 24)),
    );
    const results: BacktestOptimizationCandidate[] = [];

    for (let index = 0; index < candidates.length; index += 1) {
      const params = candidates[index];
      const artifactId = `opt_${input.code.trim()}_${input.strategy.trim()}_${index + 1}`;
      try {
        const run = await this.run({
          ...input,
          ...params,
          artifactId,
        });
        results.push({
          candidateId: `candidate_${index + 1}`,
          success: true,
          params,
          artifactId: run.artifactId ?? artifactId,
          metrics: run.metrics,
          score: this.scoreMetrics(run.metrics, objective),
        });
      } catch (error) {
        results.push({
          candidateId: `candidate_${index + 1}`,
          success: false,
          params,
          artifactId,
          metrics: undefined,
          score: null,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    const successful = results
      .filter((item) => item.success && item.metrics)
      .sort((left, right) => (right.score ?? -Infinity) - (left.score ?? -Infinity));
    const bestCandidate = successful[0] ?? null;
    return {
      sourceTool: 'backtest_manager',
      code: input.code.trim(),
      strategy: input.strategy.trim(),
      objective,
      evaluatedCount: results.length,
      parameterSpace: this.buildParameterSpace(candidates),
      candidates: results.slice(0, Math.max(1, Math.min(input.topN ?? 8, results.length || 1))),
      bestCandidate,
      recommendedParams: bestCandidate?.params ?? {},
    };
  }

  async walkForward(input: WalkForwardBacktestInput): Promise<BacktestWalkForwardResponse> {
    const objective = this.normalizeObjective(input.objective);
    const trainDays = Math.max(30, input.trainDays ?? 180);
    const testDays = Math.max(10, input.testDays ?? 60);
    const stepDays = Math.max(5, input.stepDays ?? testDays);
    const maxFolds = Math.max(1, Math.min(input.maxFolds ?? 6, 12));
    const start = this.parseDate(input.startDate);
    const end = this.parseDate(input.endDate);
    if (!start || !end || start >= end) {
      throw new BadGatewayException({
        success: false,
        message: 'walk-forward 需要有效的 startDate/endDate，且 startDate 必须早于 endDate',
      });
    }

    const folds: BacktestWalkForwardFold[] = [];
    let foldIndex = 0;
    let cursor = new Date(start);
    while (foldIndex < maxFolds) {
      const trainStart = new Date(cursor);
      const trainEnd = this.addDays(trainStart, trainDays - 1);
      const testStart = this.addDays(trainEnd, 1);
      const testEnd = this.addDays(testStart, testDays - 1);
      if (testEnd > end) break;

      try {
        const trainRun = await this.run({
          ...input,
          startDate: this.formatDate(trainStart),
          endDate: this.formatDate(trainEnd),
          artifactId: `wf_train_${input.code.trim()}_${foldIndex + 1}`,
        });
        const testRun = await this.run({
          ...input,
          startDate: this.formatDate(testStart),
          endDate: this.formatDate(testEnd),
          artifactId: `wf_test_${input.code.trim()}_${foldIndex + 1}`,
        });
        const score = this.scoreMetrics(testRun.metrics, objective);
        folds.push({
          fold: foldIndex + 1,
          trainStart: this.formatDate(trainStart),
          trainEnd: this.formatDate(trainEnd),
          testStart: this.formatDate(testStart),
          testEnd: this.formatDate(testEnd),
          trainArtifactId: trainRun.artifactId ?? null,
          testArtifactId: testRun.artifactId ?? null,
          trainMetrics: trainRun.metrics,
          testMetrics: testRun.metrics,
          score,
          passed: score > 0,
          error: null,
        });
      } catch (error) {
        folds.push({
          fold: foldIndex + 1,
          trainStart: this.formatDate(trainStart),
          trainEnd: this.formatDate(trainEnd),
          testStart: this.formatDate(testStart),
          testEnd: this.formatDate(testEnd),
          score: null,
          passed: false,
          error: error instanceof Error ? error.message : String(error),
        });
      }

      cursor = this.addDays(cursor, stepDays);
      foldIndex += 1;
    }

    const testMetrics = folds.map((item) => item.testMetrics).filter(Boolean) as BacktestMetricSnapshot[];
    const positiveFoldRatio = folds.length > 0
      ? folds.filter((item) => item.passed).length / folds.length
      : 0;
    const avgTestSharpe = this.average(testMetrics.map((item) => item.sharpe));
    const avgTestReturn = this.average(testMetrics.map((item) => item.totalReturn));
    const worstDrawdown = this.maxAbs(testMetrics.map((item) => item.maxDrawdown));
    const passed = folds.length > 0
      && positiveFoldRatio >= 0.5
      && (avgTestSharpe ?? -Infinity) >= 0
      && (worstDrawdown ?? Infinity) <= 35;

    return {
      sourceTool: 'backtest_manager',
      code: input.code.trim(),
      strategy: input.strategy.trim(),
      objective,
      trainDays,
      testDays,
      stepDays,
      folds,
      summary: {
        foldCount: folds.length,
        positiveFoldRatio: Number(positiveFoldRatio.toFixed(4)),
        avgTestSharpe,
        avgTestReturn,
        worstDrawdown,
        passed,
        stability: positiveFoldRatio >= 0.67 ? 'stable' : positiveFoldRatio >= 0.5 ? 'mixed' : 'fragile',
        recommendation: passed
          ? 'walk_forward_pass'
          : 'walk_forward_review_required',
      },
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

  private normalizeMetrics(payload: unknown): BacktestMetricSnapshot {
    const d = this.pickObject(payload, ['data.metrics', 'metrics', 'result', 'data', 'payload'])
      ?? this.asRecord(payload);
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

  private buildRunArgs(input: RunBacktestInput) {
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
    return {
      requestedArtifactId,
      normalized,
      args: { action: 'run', kwargs: JSON.stringify(normalized) },
    };
  }

  private buildParameterCandidates(input: OptimizeBacktestInput): Array<Record<string, number>> {
    const strategy = input.strategy.trim().toLowerCase();
    if (strategy === 'ma_cross') {
      const shorts = [3, 5, 8, 10, 13];
      const longs = [15, 20, 30, 50, 80];
      return shorts.flatMap((shortPeriod) =>
        longs
          .filter((longPeriod) => longPeriod > shortPeriod)
          .map((longPeriod) => ({ shortPeriod, longPeriod })),
      );
    }
    if (strategy === 'momentum') {
      const lookbacks = [10, 20, 30, 60];
      const thresholds = [0.01, 0.015, 0.02, 0.03];
      return lookbacks.flatMap((lookback) => thresholds.map((threshold) => ({ lookback, threshold })));
    }
    if (strategy === 'rsi') {
      const periods = [7, 14, 21];
      const oversoldLevels = [20, 25, 30];
      const overboughtLevels = [70, 75, 80];
      return periods.flatMap((rsiPeriod) =>
        oversoldLevels.flatMap((oversold) =>
          overboughtLevels
            .filter((overbought) => overbought > oversold + 25)
            .map((overbought) => ({ rsiPeriod, oversold, overbought })),
        ),
      );
    }
    return [{}];
  }

  private buildParameterSpace(candidates: Array<Record<string, number>>) {
    return candidates.reduce<Record<string, number[]>>((acc, candidate) => {
      Object.entries(candidate).forEach(([key, value]) => {
        const existing = acc[key] ?? [];
        if (!existing.includes(value)) existing.push(value);
        acc[key] = existing.sort((left, right) => left - right);
      });
      return acc;
    }, {});
  }

  private scoreMetrics(metrics: BacktestMetricSnapshot | undefined, objective: string) {
    if (!metrics) return Number.NEGATIVE_INFINITY;
    const totalReturn = metrics.totalReturn ?? -100;
    const sharpe = metrics.sharpe ?? -5;
    const maxDrawdown = Math.abs(metrics.maxDrawdown ?? 100);
    const profitFactor = metrics.profitFactor ?? 0;
    if (objective === 'total_return') {
      return Number((totalReturn - maxDrawdown * 0.25 + profitFactor * 2).toFixed(4));
    }
    if (objective === 'balanced') {
      return Number((sharpe * 30 + totalReturn - maxDrawdown * 0.45 + profitFactor * 4).toFixed(4));
    }
    return Number((sharpe * 40 + totalReturn * 0.35 - maxDrawdown * 0.3 + profitFactor * 3).toFixed(4));
  }

  private normalizeObjective(value: string | undefined) {
    return ['balanced', 'sharpe', 'total_return'].includes(String(value))
      ? String(value)
      : 'balanced';
  }

  private parseDate(value: string | undefined) {
    if (!value) return null;
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  private addDays(base: Date, days: number) {
    const next = new Date(base);
    next.setUTCDate(next.getUTCDate() + days);
    return next;
  }

  private formatDate(value: Date) {
    return value.toISOString().slice(0, 10);
  }

  private average(values: Array<number | null>) {
    const filtered = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    if (!filtered.length) return null;
    return Number((filtered.reduce((sum, value) => sum + value, 0) / filtered.length).toFixed(4));
  }

  private maxAbs(values: Array<number | null>) {
    const filtered = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    if (!filtered.length) return null;
    return Number(Math.max(...filtered.map((value) => Math.abs(value))).toFixed(4));
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

  private pickString(payload: unknown, paths: string[]): string | null {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (typeof v === 'string' && v.trim()) return v.trim();
      if (typeof v === 'number' && Number.isFinite(v)) return String(v);
    }
    return null;
  }

  private pickArray(payload: unknown, paths: string[]): unknown[] {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (Array.isArray(v)) return v;
    }
    return [];
  }

  private pickObject(payload: unknown, paths: string[]): Record<string, unknown> | null {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        return v as Record<string, unknown>;
      }
    }
    return null;
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  }

  private readPath(obj: unknown, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, key) => {
      if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
        return undefined;
      }
      return (acc as Record<string, unknown>)[key];
    }, obj);
  }
}
