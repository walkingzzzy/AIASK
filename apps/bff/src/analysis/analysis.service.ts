import { BadGatewayException, Injectable } from '@nestjs/common';
import type {
  AnalysisReportBundle,
  DeepAnalysisRunResponse,
  DeepAnalysisTask,
} from '@aiask/shared-types';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class AnalysisService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async createRun(params: {
    code?: string;
    task?: DeepAnalysisTask;
    runId?: string;
    investmentStyle?: string;
    userId?: string;
    market?: string;
  }): Promise<DeepAnalysisRunResponse> {
    const payload = await this.callTool('analyze_stock_product_workflow', {
      code: params.code,
      task: params.task ?? 'deep_analysis',
      run_id: params.runId,
      investment_style: params.investmentStyle ?? 'balanced',
      user_id: params.userId,
      market: params.market ?? 'cn',
    });
    return this.extractToolData<DeepAnalysisRunResponse>(payload);
  }

  async getRun(runId: string): Promise<DeepAnalysisRunResponse> {
    const payload = await this.readResource(
      `resource://analysis-run/${this.normalizeResourceId(runId)}/summary`,
    );
    return payload as DeepAnalysisRunResponse;
  }

  async getRunReport(runId: string): Promise<AnalysisReportBundle> {
    const payload = await this.readResource(
      `resource://analysis-run/${this.normalizeResourceId(runId)}/report`,
    );
    return payload as AnalysisReportBundle;
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

  private async readResource(uri: string) {
    try {
      return await this.mcpGatewayService.readResource(uri);
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: '读取 MCP 资源失败',
        detail: error instanceof Error ? error.message : String(error),
        resourceUri: uri,
      });
    }
  }

  private extractToolData<T>(payload: unknown): T {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return payload as T;
    }
    const record = payload as Record<string, unknown>;
    if (Object.prototype.hasOwnProperty.call(record, 'data')) {
      return (record.data ?? null) as T;
    }
    return payload as T;
  }

  private normalizeResourceId(value: string): string {
    return String(value ?? '').trim();
  }
}
