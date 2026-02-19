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
  dataProvenance: string[];
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
      { stock_code: stockCode },
      { code: stockCode },
      { symbol: stockCode },
    ];
    const { payload } = await this.callWithArgs('should_i_buy', attempts);
    return { card: this.normalizeCard(payload), raw: payload };
  }

  async shouldSell(code: string) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [
      { stock_code: stockCode },
      { code: stockCode },
      { symbol: stockCode },
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
    const toArr = (v: any): string[] => {
      if (Array.isArray(v)) return v.map(String);
      if (typeof v === 'string') return v.split(/[;；\n]/).map((s: string) => s.trim()).filter(Boolean);
      return [];
    };
    const n = Number(d.confidence ?? d.score);
    return {
      action: String(d.action ?? d.decision ?? d.recommendation ?? d.signal ?? ''),
      confidence: Number.isFinite(n) ? n : null,
      summary: String(d.summary ?? d.analysis ?? d.description ?? d.reason ?? ''),
      reasons: toArr(d.reasons ?? d.reason_list ?? d.factors),
      executionPlan: toArr(d.execution_plan ?? d.executionPlan ?? d.plan ?? d.steps),
      risks: toArr(d.risks ?? d.risk_factors ?? d.warnings),
      dataProvenance: toArr(d.data_provenance ?? d.dataProvenance ?? d.sources ?? d.data_sources),
      complianceNotice: String(d.compliance_notice ?? d.complianceNotice ?? d.disclaimer ?? '本分析结果仅供参考，不构成投资建议。'),
    };
  }

  private async callWithArgs(primaryTool: string, attempts: Array<Record<string, unknown>>) {
    let lastError: unknown = null;
    for (const args of attempts) {
      try {
        const payload = await this.mcp.callTool(primaryTool, args);
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
}
