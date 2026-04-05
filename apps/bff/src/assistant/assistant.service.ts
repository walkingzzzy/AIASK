import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

export type DecisionCardDto = {
  action: string;
  confidence: number | null;
  summary: string;
  reasons: string[];
  executionPlan: string[];
  risks: string[];
  dataProvenance: Array<string | { source?: string; dataset?: string; timestamp?: string }>;
  complianceNotice: string;
};

@Injectable()
export class AssistantService {
  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cacheService: CommonCacheService,
  ) {}

  async diagnosis(code: string) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [
      { stock_code: stockCode },
      { code: stockCode },
      { symbol: stockCode },
    ];
    const { payload } = await this.callWithArgs('smart_stock_diagnosis', attempts);
    return { card: this.normalizeCard(payload), raw: payload };
  }

  async shouldBuy(code: string) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [
      { code: stockCode },
      { stock_code: stockCode },
      { symbol: stockCode },
    ];
    const { payload } = await this.callWithArgs('should_i_buy', attempts);
    return { card: this.normalizeCard(payload), raw: payload };
  }

  async shouldSell(code: string, buyPrice: number, holdingDays = 0) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [
      { code: stockCode, buy_price: buyPrice, holding_days: holdingDays },
    ];
    const { payload } = await this.callWithArgs('should_i_sell', attempts);
    return { card: this.normalizeCard(payload), raw: payload };
  }

  async analyzeWorkflow(
    code: string,
    options: {
      investmentStyle?: string;
      includeKline?: boolean;
      includeFinancials?: boolean;
      includeDecision?: boolean;
      klineLimit?: number;
      asOf?: string;
    } = {},
  ) {
    const stockCode = code.trim();
    const payload = await this.mcp.callTool('analyze_stock_workflow', {
      code: stockCode,
      investment_style: options.investmentStyle ?? 'balanced',
      include_kline: options.includeKline ?? true,
      include_financials: options.includeFinancials ?? true,
      include_decision: options.includeDecision ?? true,
      kline_limit: options.klineLimit,
      as_of: options.asOf,
    });
    const toolError = this.extractToolError(payload);
    if (toolError) {
      throw new BadGatewayException({
        success: false,
        message: 'MCP analyze_stock_workflow 调用失败',
        detail: toolError,
      });
    }
    return { card: this.normalizeWorkflowCard(payload), raw: payload };
  }

  async decisionManagerAnalyze(code: string) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [
      { action: 'analyze', code: stockCode },
      { action: 'analyze', kwargs: JSON.stringify({ code: stockCode }) },
    ];
    const { payload } = await this.callWithArgs('decision_manager', attempts);
    return { card: this.normalizeCard(payload), raw: payload };
  }

  async getIndustryChain(keyword?: string, chainId?: string) {
    const args: Record<string, unknown> = {};
    if (keyword) args.keyword = keyword.trim();
    if (chainId) args.chain_id = chainId.trim();
    const payload = await this.mcp.callTool('get_industry_chain', args);
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const chains = this.asRecordArray(data.chains ?? root);
    return {
      chains: chains.map((chain) => ({
        id: this.toText(chain.id),
        name: this.toText(chain.name),
        upstream: this.toTextArray(chain.upstream),
        midstream: this.toTextArray(chain.midstream),
        downstream: this.toTextArray(chain.downstream),
      })),
    };
  }

  async generateDailyReport(date?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    const payload = await this.mcp.callTool('generate_daily_report', args);
    const data = this.asRecord(this.unwrapPayload(payload));
    return {
      date: this.toText(data.date),
      marketSummary: this.toText(data.market_summary ?? data.marketSummary),
      hotSectors: this.asRecordArray(data.hot_sectors ?? data.hotSectors),
      sentiment: this.toText(data.sentiment),
      outlook: this.toText(data.outlook),
      generatedAt: this.toText(data.generated_at ?? data.generatedAt),
    };
  }

  private normalizeCard(payload: unknown): DecisionCardDto {
    const d = this.asRecord(this.unwrapPayload(payload));
    const toArr = (v: unknown): string[] => {
      if (Array.isArray(v)) return v.map((item) => this.toText(item)).filter(Boolean);
      if (typeof v === 'string') return v.split(/[;；\n]/).map((s: string) => s.trim()).filter(Boolean);
      if (v && typeof v === 'object') {
        return Object.values(v as Record<string, unknown>).map((item) => this.toText(item)).filter(Boolean);
      }
      return [];
    };
    const provenance = (() => {
      const raw = d.data_provenance ?? d.dataProvenance ?? d.sources ?? d.data_sources;
      if (Array.isArray(raw)) {
        return raw
          .map((item) => {
          if (item && typeof item === 'object') {
            const obj = item as Record<string, unknown>;
            return {
              source: this.toText(obj.source ?? obj.name),
              dataset: this.toText(obj.dataset ?? obj.table ?? obj.topic),
              timestamp: this.toText(obj.timestamp ?? obj.updated_at ?? obj.updatedAt),
            };
          }
            return this.toText(item);
          })
          .filter((item) => {
            if (typeof item === 'string') return item.length > 0;
            return Boolean(item.source || item.dataset || item.timestamp);
          });
      }
      const text = this.toText(raw);
      return text ? [text] : [];
    })();
    const reasons = toArr(d.reasons ?? d.reason_list ?? d.factors);
    const executionPlan = toArr(d.execution_plan ?? d.executionPlan ?? d.plan ?? d.steps);
    const risks = toArr(d.risks ?? d.risk_factors ?? d.warnings);
    const summary = this.toText(
      d.summary ??
      d.action_text ??
      d.actionText ??
      d.analysis ??
      d.description ??
      d.reason,
    ) || reasons.slice(0, 2).join('；') || risks.slice(0, 1).join('；');
    const n = Number(d.confidence ?? d.score);
    const normalizedConfidence = Number.isFinite(n)
      ? n > 1
        ? n / 100
        : n
      : null;

    return {
      action: String(d.action ?? d.decision ?? d.recommendation ?? d.signal ?? ''),
      confidence: normalizedConfidence,
      summary,
      reasons,
      executionPlan,
      risks,
      dataProvenance: provenance,
      complianceNotice: String(d.compliance_notice ?? d.complianceNotice ?? d.disclaimer ?? '本分析结果仅供参考，不构成投资建议。'),
    };
  }

  private normalizeWorkflowCard(payload: unknown): DecisionCardDto {
    const root = this.asRecord(payload);
    const data = this.asRecord(this.unwrapPayload(payload));
    const steps = Array.isArray(data.steps) ? data.steps : [];
    const decisionStep = steps.find(
      (item) => item && typeof item === 'object' && this.asRecord(item).step === 'decision_summary',
    );
    const decisionOutput = this.asRecord(this.asRecord(decisionStep).output);
    const decisionData = this.asRecord(decisionOutput.data);
    const summary = this.asRecord(data.summary);
    const meta = this.asRecord(root.meta);
    const sourceChain = Array.isArray(meta.source_chain)
      ? meta.source_chain.map((item) => this.toText(item)).filter(Boolean)
      : [];
    const decisionCard = this.normalizeCard({ data: decisionData });
    const quotePrice = summary.quote_price;
    const fallbackSummary = [
      this.toText(decisionCard.summary),
      this.toText(summary.decision_action) ? `决策动作：${this.toText(summary.decision_action)}` : '',
      quotePrice != null ? `参考价格：${this.toText(quotePrice)}` : '',
    ].filter(Boolean).join('；');

    return {
      action: decisionCard.action || this.toText(summary.decision_action) || 'watch',
      confidence: decisionCard.confidence,
      summary: fallbackSummary || '已生成股票分析工作流结果。',
      reasons: decisionCard.reasons,
      executionPlan: [
        '已聚合 stock profile / kline / financials / decision summary',
        ...this.toTextArray(data.artifacts ? Object.values(this.asRecord(data.artifacts)) : []),
      ].filter(Boolean),
      risks: decisionCard.risks,
      dataProvenance: sourceChain,
      complianceNotice: decisionCard.complianceNotice,
    };
  }

  private unwrapPayload(payload: unknown): unknown {
    const record = this.asRecord(payload);
    return record.data !== undefined ? record.data : payload;
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  }

  private asRecordArray(value: unknown): Record<string, unknown>[] {
    if (!Array.isArray(value)) return [];
    return value
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
  }

  private toTextArray(value: unknown): string[] {
    if (!Array.isArray(value)) return [];
    return value.map((item) => this.toText(item)).filter(Boolean);
  }

  private toText(value: unknown): string {
    if (typeof value === 'string') return value.trim();
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) {
      return value.map((item) => this.toText(item)).filter(Boolean).join('；');
    }
    if (value && typeof value === 'object') {
      const record = value as Record<string, unknown>;
      const preferred = [
        'summary',
        'analysis',
        'conclusion',
        'overview',
        'description',
        'reason',
        'recommendation',
        'signal',
        'value',
      ];
      for (const key of preferred) {
        const text = this.toText(record[key]);
        if (text) return text;
      }
      return Object.entries(record)
        .map(([key, item]) => {
          const text = this.toText(item);
          return text ? `${key}: ${text}` : '';
        })
        .filter(Boolean)
        .join('；');
    }
    return '';
  }

  private async callWithArgs(primaryTool: string, attempts: Array<Record<string, unknown>>) {
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcp.callTool(primaryTool, args);
        const toolError = this.extractToolError(payload);
        if (toolError) {
          throw new Error(toolError);
        }
        return { payload, argsMatched: args };
      } catch (e) {
        lastError = e;
      }
    }
    throw new BadGatewayException({
      success: false,
      message: `MCP ${primaryTool} 调用失败`,
      detail: lastError instanceof Error ? lastError.message : String(lastError),
    });
  }

  private extractToolError(payload: unknown): string | null {
    if (typeof payload === 'string') {
      const message = payload.trim();
      return message.length > 0 ? message : null;
    }
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    const record = payload as Record<string, unknown>;
    if (record.success === false && typeof record.error === 'string') {
      return record.error;
    }
    if (record.success === false && record.error && typeof record.error === 'object') {
      const nested = record.error as Record<string, unknown>;
      if (typeof nested.message === 'string' && nested.message.trim()) {
        return nested.message;
      }
    }
    return null;
  }
}
