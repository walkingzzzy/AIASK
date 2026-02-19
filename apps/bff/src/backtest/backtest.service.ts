import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

export type RunBacktestInput = {
  code: string;
  strategy: string;
  startDate?: string;
  endDate?: string;
  initialCapital?: number;
  shortPeriod?: number;
  longPeriod?: number;
  artifactId?: string;
};

export type NormalizedBacktestMetrics = {
  totalReturn: number | null; sharpe: number | null; maxDrawdown: number | null;
  winRate: number | null; totalTrades: number | null; profitFactor: number | null;
};

@Injectable()
export class BacktestService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async run(input: RunBacktestInput) {
    const normalized = {
      code: input.code.trim(),
      strategy: input.strategy.trim() || 'ma_cross',
      start_date: input.startDate || null,
      end_date: input.endDate || null,
      initial_capital: input.initialCapital ?? 100000,
      short_period: input.shortPeriod ?? 5,
      long_period: input.longPeriod ?? 20,
      artifact_id: input.artifactId || undefined,
    };

    const args = { action: 'run', kwargs: JSON.stringify(normalized) };
    const payload = await this.callTool('backtest_manager', args);
    const artifactId =
      this.pickString(payload, ['data.artifact_id', 'data.artifactId', 'artifact_id', 'artifactId']) ||
      normalized.artifact_id ||
      `art_${normalized.code}_${Date.now()}`;

    return {
      artifactId,
      backtestId: this.pickString(payload, ['data.backtest_id', 'data.id', 'backtest_id', 'id']),
      sourceTool: 'backtest_manager' as const,
      argsMatched: args,
      result: payload,
      metrics: this.normalizeMetrics(payload),
    };
  }

  async list(limit = 10) {
    const args = { action: 'list', kwargs: JSON.stringify({ limit: Math.min(Math.max(limit, 1), 100) }) };
    const payload = await this.callTool('backtest_manager', args);
    return { sourceTool: 'backtest_manager' as const, argsMatched: args, result: payload };
  }

  async metricsByArtifact(artifactId: string) {
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

  private normalizeMetrics(payload: any): NormalizedBacktestMetrics {
    const d = payload?.data?.metrics ?? payload?.data ?? payload?.metrics ?? payload ?? {};
    return {
      totalReturn: this.toNum(d.total_return ?? d.totalReturn ?? d.cumulative_return),
      sharpe: this.toNum(d.sharpe_ratio ?? d.sharpe ?? d.sharpeRatio),
      maxDrawdown: this.toNum(d.max_drawdown ?? d.maxDrawdown),
      winRate: this.toNum(d.win_rate ?? d.winRate),
      totalTrades: this.toNum(d.total_trades ?? d.totalTrades ?? d.trade_count),
      profitFactor: this.toNum(d.profit_factor ?? d.profitFactor),
    };
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private pickString(payload: any, paths: string[]): string | null {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (typeof v === 'string' && v.trim()) return v.trim();
      if (typeof v === 'number' && Number.isFinite(v)) return String(v);
    }
    return null;
  }

  private readPath(obj: any, path: string): unknown {
    return path.split('.').reduce((acc: any, key: string) => (acc == null ? undefined : acc[key]), obj);
  }
}

