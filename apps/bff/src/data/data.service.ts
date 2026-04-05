import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';

@Injectable()
export class DataService {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

  async getOptionChain(params: { underlying: string; expiryMonth?: string; limit?: number }) {
    const payload = await this.callTool('get_option_chain', {
      underlying: params.underlying, expiry_month: params.expiryMonth, limit: params.limit ?? 50,
    });
    return { sourceTool: 'get_option_chain' as const, result: payload };
  }

  async getTradingDates(params: { startDate?: string; endDate?: string; count?: number }) {
    const payload = await this.callTool('get_trading_dates', {
      start_date: params.startDate, end_date: params.endDate, count: params.count ?? 30,
    });
    return {
      sourceTool: 'get_trading_dates' as const,
      result: payload,
      dates: this.pickTradingDates(payload),
    };
  }

  async getIpoInfo(params: { ipoType?: string; includeFuture?: boolean }) {
    const payload = await this.callTool('get_ipo_info', {
      ipo_type: params.ipoType, include_future: params.includeFuture ?? true,
    });
    return { sourceTool: 'get_ipo_info' as const, result: payload };
  }

  async getCbInfo(code: string) {
    const payload = await this.callTool('get_cb_info', { code });
    return { sourceTool: 'get_cb_info' as const, result: payload };
  }

  async getStockCapital(params: { code: string; dates?: string[] }) {
    const payload = await this.callTool('get_stock_capital', {
      code: params.code, dates: params.dates,
    });
    return { sourceTool: 'get_stock_capital' as const, result: payload };
  }

  async predictionDiagnosisWorkflow(params: {
    probabilities: number[];
    labels: number[];
    rawScores?: number[];
    method?: string;
    plattA?: number;
    plattB?: number;
    coverageTarget?: number;
    datasetId?: string;
    runId?: string;
    persistArtifact?: boolean;
    outputArtifactId?: string;
    asOf?: string;
  }) {
    return this.callTool('prediction_diagnosis_workflow', {
      probabilities: params.probabilities,
      labels: params.labels,
      raw_scores: params.rawScores,
      method: params.method,
      platt_a: params.plattA,
      platt_b: params.plattB,
      coverage_target: params.coverageTarget,
      dataset_id: params.datasetId,
      run_id: params.runId,
      persist_artifact: params.persistArtifact,
      output_artifact_id: params.outputArtifactId,
      as_of: params.asOf,
    });
  }

  async dataQualityWorkflow(params: {
    datasetId?: string;
    records?: Array<Record<string, unknown>>;
    requiredFields?: string[];
    asOfField?: string;
    asOfValue?: string;
    source?: string;
    sourceChain?: string[];
    minimumQualityThreshold?: number;
    persistArtifact?: boolean;
    outputArtifactId?: string;
    asOf?: string;
  }) {
    return this.callTool('data_quality_workflow', {
      dataset_id: params.datasetId,
      records: params.records,
      required_fields: params.requiredFields,
      as_of_field: params.asOfField,
      as_of_value: params.asOfValue,
      source: params.source,
      source_chain: params.sourceChain,
      minimum_quality_threshold: params.minimumQualityThreshold,
      persist_artifact: params.persistArtifact,
      output_artifact_id: params.outputArtifactId,
      as_of: params.asOf,
    });
  }

  async getToolCatalog() {
    const payload = await this.readResource('resource://server/tool-catalog');
    return { resourceUri: 'resource://server/tool-catalog' as const, result: payload };
  }

  async getWorkflowGuide(name: string) {
    const normalizedName = this.normalizeWorkflowGuideName(name);
    const uri = `resource://workflow/${normalizedName}/guide`;
    return this.readResourceEnvelope(uri);
  }

  async getRunSnapshot(runId: string) {
    const uri = `resource://run/${this.normalizeResourceId(runId)}`;
    return this.readResourceEnvelope(uri);
  }

  async getDatasetQuality(datasetId: string) {
    const uri = `resource://dataset/${this.normalizeResourceId(datasetId)}/quality`;
    return this.readResourceEnvelope(uri);
  }

  async getDatasetProfile(datasetId: string) {
    const uri = `resource://dataset/${this.normalizeResourceId(datasetId)}/profile`;
    return this.readResourceEnvelope(uri);
  }

  async getFactorProfile(factorId: string) {
    const uri = `resource://factor/${this.normalizeResourceId(factorId)}/profile`;
    return this.readResourceEnvelope(uri);
  }

  async getModelProfile(modelId: string) {
    const uri = `resource://model/${this.normalizeResourceId(modelId)}/profile`;
    return this.readResourceEnvelope(uri);
  }

  async getStrategyGovernance(strategyId: string) {
    const uri = `resource://strategy/${this.normalizeResourceId(strategyId)}/governance`;
    return this.readResourceEnvelope(uri);
  }

  async getExperimentSummary(experimentId: string) {
    const uri = `resource://experiment/${this.normalizeResourceId(experimentId)}/summary`;
    return this.readResourceEnvelope(uri);
  }

  async getSystemGovernanceReport() {
    return this.readResourceEnvelope('resource://governance/system/report');
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

  private async readResource(uri: string) {
    try {
      return await this.mcpGatewayService.readResource(uri);
    } catch (error) {
      throw new BadGatewayException({
        success: false, message: `读取 MCP 资源失败`,
        detail: error instanceof Error ? error.message : String(error),
        resourceUri: uri,
      });
    }
  }

  private pickTradingDates(payload: unknown) {
    const root = this.readPath(payload, 'data.dates') ?? this.readPath(payload, 'dates');
    if (!Array.isArray(root)) return [];
    return root.map((item) => this.normalizeTradingDate(item)).filter(Boolean);
  }

  private normalizeTradingDate(value: unknown) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const row = value as Record<string, unknown>;
      return {
        date: String(row.date ?? row.trade_date ?? row.trading_date ?? ''),
        dayOfWeek: String(row.dayOfWeek ?? row.day_of_week ?? row.weekday ?? ''),
        isTrading: row.isTrading ?? row.is_trading ?? row.open ?? true,
      };
    }

    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const normalized = raw.length === 8 ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` : raw;
    const date = new Date(normalized);
    const dayOfWeek = Number.isNaN(date.getTime())
      ? ''
      : ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][date.getDay()];
    return {
      date: normalized,
      dayOfWeek,
      isTrading: true,
    };
  }

  private readPath(value: unknown, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, key) => {
      if (!acc || typeof acc !== 'object') return undefined;
      return (acc as Record<string, unknown>)[key];
    }, value);
  }

  private async readResourceEnvelope(uri: string) {
    const payload = await this.readResource(uri);
    return { resourceUri: uri, result: payload };
  }

  private normalizeWorkflowGuideName(name: string): string {
    const raw = String(name ?? '').trim();
    const aliasMap: Record<string, string> = {
      'stock-analysis-guide': 'stock-analysis',
      'factor-governance-guide': 'factor-governance',
      'strategy-promotion-guide': 'strategy-promotion',
      'governance-monitoring-guide': 'governance-monitoring',
    };
    return aliasMap[raw] ?? raw;
  }

  private normalizeResourceId(value: string): string {
    return String(value ?? '').trim();
  }
}
