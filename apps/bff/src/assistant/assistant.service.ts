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

  async getIndustryChain(keyword?: string, chainId?: string) {
    const args: Record<string, unknown> = {};
    if (keyword) args.keyword = keyword.trim();
    if (chainId) args.chain_id = chainId.trim();
    const payload = await this.mcp.callTool('get_industry_chain', args);
    const d = (payload as any)?.data ?? payload ?? {};
    const chains = Array.isArray(d?.chains) ? d.chains : Array.isArray(d) ? d : [];
    return { chains: chains.map((c: any) => ({ id: String(c.id ?? ''), name: String(c.name ?? ''), upstream: Array.isArray(c.upstream) ? c.upstream : [], midstream: Array.isArray(c.midstream) ? c.midstream : [], downstream: Array.isArray(c.downstream) ? c.downstream : [] })) };
  }

  async generateDailyReport(date?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    const payload = await this.mcp.callTool('generate_daily_report', args);
    const d = (payload as any)?.data ?? payload ?? {};
    return { date: String(d.date ?? ''), marketSummary: String(d.market_summary ?? d.marketSummary ?? ''), hotSectors: Array.isArray(d.hot_sectors ?? d.hotSectors) ? (d.hot_sectors ?? d.hotSectors) : [], sentiment: String(d.sentiment ?? ''), outlook: String(d.outlook ?? ''), generatedAt: String(d.generated_at ?? d.generatedAt ?? '') };
  }

  private normalizeCard(payload: any): DecisionCardDto {
    const d = payload?.data ?? payload ?? {};
    const toText = (value: unknown): string => {
      if (typeof value === 'string') return value.trim();
      if (typeof value === 'number' || typeof value === 'boolean') return String(value);
      if (Array.isArray(value)) {
        return value.map((item) => toText(item)).filter(Boolean).join('；');
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
          const text = toText(record[key]);
          if (text) return text;
        }
        return Object.entries(record)
          .map(([key, item]) => {
            const text = toText(item);
            return text ? `${key}: ${text}` : '';
          })
          .filter(Boolean)
          .join('；');
      }
      return '';
    };
    const toArr = (v: unknown): string[] => {
      if (Array.isArray(v)) return v.map((item) => toText(item)).filter(Boolean);
      if (typeof v === 'string') return v.split(/[;；\n]/).map((s: string) => s.trim()).filter(Boolean);
      if (v && typeof v === 'object') {
        return Object.values(v as Record<string, unknown>).map((item) => toText(item)).filter(Boolean);
      }
      return [];
    };
    const provenance = (() => {
      const raw = d.data_provenance ?? d.dataProvenance ?? d.sources ?? d.data_sources;
      if (Array.isArray(raw)) {
        return raw.map((item) => {
          if (item && typeof item === 'object') {
            const obj = item as Record<string, unknown>;
            return {
              source: toText(obj.source ?? obj.name),
              dataset: toText(obj.dataset ?? obj.table ?? obj.topic),
              timestamp: toText(obj.timestamp ?? obj.updated_at ?? obj.updatedAt),
            };
          }
          return toText(item);
        }).filter((item) => {
          if (typeof item === 'string') return item.length > 0;
          return Boolean(item.source || item.dataset || item.timestamp);
        });
      }
      const text = toText(raw);
      return text ? [text] : [];
    })();
    const reasons = toArr(d.reasons ?? d.reason_list ?? d.factors);
    const executionPlan = toArr(d.execution_plan ?? d.executionPlan ?? d.plan ?? d.steps);
    const risks = toArr(d.risks ?? d.risk_factors ?? d.warnings);
    const summary = toText(
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
