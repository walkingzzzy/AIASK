import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import {
  buildResultContract,
  extractFreshness,
  extractPlatformMeta,
  uniqueStrings,
} from '../common/result-contract';
import {
  buildResultContractMeta,
  callToolWithContract,
} from '../common/tool-contracts';

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
    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('smart_stock_diagnosis', [{ code: stockCode }]);
    const card = this.normalizeCard(payload);
    return {
      card,
      raw: payload,
      result_contract: this.buildDecisionResultContract(card, payload, {
        code: stockCode,
        sourceTool: 'smart_stock_diagnosis',
        taskLabel: '个股诊断',
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool,
        canonicalArgs,
        argsMatched,
        aliasHits,
      }),
    };
  }

  async shouldBuy(code: string) {
    const stockCode = code.trim();
    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('should_i_buy', [{ code: stockCode }]);
    const card = this.normalizeCard(payload);
    return {
      card,
      raw: payload,
      result_contract: this.buildDecisionResultContract(card, payload, {
        code: stockCode,
        sourceTool: 'should_i_buy',
        taskLabel: '买入逻辑分析',
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool,
        canonicalArgs,
        argsMatched,
        aliasHits,
      }),
    };
  }

  async shouldSell(code: string, buyPrice: number, holdingDays = 0) {
    const stockCode = code.trim();
    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('should_i_sell', [
      { code: stockCode, buy_price: buyPrice, holding_days: holdingDays },
    ]);
    const card = this.normalizeCard(payload);
    return {
      card,
      raw: payload,
      result_contract: this.buildDecisionResultContract(card, payload, {
        code: stockCode,
        sourceTool: 'should_i_sell',
        taskLabel: '卖出风险提示',
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool,
        canonicalArgs,
        argsMatched,
        aliasHits,
      }),
    };
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
    const card = this.normalizeWorkflowCard(payload);
    return {
      card,
      raw: payload,
      result_contract: this.buildDecisionResultContract(card, payload, {
        code: stockCode,
        sourceTool: 'analyze_stock_workflow',
        taskLabel: '全方位综合体检',
      }),
    };
  }

  async decisionManagerAnalyze(code: string) {
    const stockCode = code.trim();
    const attempts: Array<Record<string, unknown>> = [
      { action: 'analyze', code: stockCode },
      { action: 'analyze', kwargs: JSON.stringify({ code: stockCode }) },
    ];
    const { payload, argsMatched, canonicalArgs, aliasHits, canonicalTool } = await this.callWithArgs('decision_manager', attempts);
    const card = this.normalizeCard(payload);
    return {
      card,
      raw: payload,
      result_contract: this.buildDecisionResultContract(card, payload, {
        code: stockCode,
        sourceTool: 'decision_manager',
        taskLabel: '统一决策分析',
      }),
      contract_meta: buildResultContractMeta({
        canonicalTool,
        canonicalArgs,
        argsMatched,
        aliasHits,
      }),
    };
  }

  async getIndustryChain(keyword?: string, chainId?: string) {
    const args: Record<string, unknown> = {};
    if (keyword) args.keyword = keyword.trim();
    if (chainId) args.chain_id = chainId.trim();
    const payload = await this.mcp.callTool('get_industry_chain', args);
    const root = this.unwrapPayload(payload);
    const data = this.asRecord(root);
    const chains = this.asRecordArray(data.chains ?? root);
    const normalizedChains = chains.map((chain) => ({
      id: this.toText(chain.id),
      name: this.toText(chain.name),
      upstream: this.toTextArray(chain.upstream),
      midstream: this.toTextArray(chain.midstream),
      downstream: this.toTextArray(chain.downstream),
    }));
    return {
      chains: normalizedChains,
      result_contract: this.buildIndustryChainResultContract(payload, normalizedChains, keyword, chainId),
    };
  }

  async generateDailyReport(date?: string) {
    const args: Record<string, unknown> = {};
    if (date) args.date = date.trim();
    const payload = await this.mcp.callTool('generate_daily_report', args);
    const data = this.asRecord(this.unwrapPayload(payload));
    const report = {
      date: this.toText(data.date),
      marketSummary: this.toText(data.market_summary ?? data.marketSummary),
      hotSectors: this.asRecordArray(data.hot_sectors ?? data.hotSectors),
      sentiment: this.toText(data.sentiment),
      outlook: this.toText(data.outlook),
      generatedAt: this.toText(data.generated_at ?? data.generatedAt),
    };
    return {
      ...report,
      result_contract: this.buildDailyReportResultContract(payload, report),
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

  private buildDecisionResultContract(
    card: DecisionCardDto,
    payload: unknown,
    options: {
      code?: string;
      sourceTool: string;
      taskLabel: string;
    },
  ) {
    const confidencePct = card.confidence != null ? `${Math.round(card.confidence * 100)}%` : '';
    const followupQuery = options.code || card.action || options.taskLabel;
    const evidence = [
      card.action ? { label: '建议动作', value: card.action, tone: 'positive' as const } : null,
      confidencePct ? { label: '置信度', value: confidencePct } : null,
      ...card.reasons.slice(0, 3).map((reason) => ({ label: '关键信号', value: reason })),
    ].filter((item): item is NonNullable<typeof item> => item != null);

    return buildResultContract({
      summary: card.summary || `${options.taskLabel}已生成，请继续查看下一步建议。`,
      availableViews: ['summary', 'next_step', ...(evidence.length > 2 ? (['visual'] as const) : [])],
      recommendedActions: [
        {
          id: 'assistant.open-copilot-followup',
          actionId: 'assistant.open-copilot-followup',
          label: '打开 Copilot 继续追问',
          description: '把当前分析结果继续转成研究和执行动作。',
          payload: {
            code: options.code ?? null,
            sourceTool: options.sourceTool,
          },
        },
      ],
      recommendedLinks: [
        options.code
          ? {
              id: 'assistant-open-stock',
              label: '个股详情',
              href: `/stock?code=${encodeURIComponent(options.code)}`,
            }
          : {
              id: 'assistant-open-data',
              label: '数据说明',
              href: '/data',
            },
        {
          id: 'assistant-open-skills',
          label: '去技能中心',
          href: `/skills?skill=${encodeURIComponent('akshare-stock-deep-analysis')}`,
        },
        {
          id: 'assistant-open-strategy-market',
          label: '去策略超市',
          href: `/strategy-market?from=assistant&task=strategy_review&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'assistant-open-favorites',
          label: '去我的收藏',
          href: `/strategy-market?workspace=favorites&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'assistant-open-mine',
          label: '去我的策略',
          href: `/strategy-market?workspace=mine&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'assistant-open-factory',
          label: '去工厂运行态',
          href: `/strategy-market?from=assistant&task=factory_cycle&q=${encodeURIComponent(followupQuery)}`,
        },
      ],
      evidence,
      riskNotes: uniqueStrings([...card.risks, card.complianceNotice]),
      freshness: extractFreshness(payload, null, '结果时效'),
      platformMeta: extractPlatformMeta(payload, {
        sourceTool: options.sourceTool,
        referencePath: '/data/tool-catalog',
        freshnessLabel: 'MCP 实时结果',
      }),
      skillSuggestions: this.buildAssistantSkillSuggestions(),
      strategySuggestions: [
        {
          id: `${options.sourceTool}-strategy-followup`,
          label: '去策略超市继续研究',
          description: '把当前结论转到策略页继续筛选与跟踪。',
          query: followupQuery,
          task: 'strategy_review',
        },
        {
          id: `${options.sourceTool}-factory-followup`,
          label: '去工厂看运行态',
          description: '把当前结论带到策略工厂运行态继续跟踪。',
          query: followupQuery,
          task: 'factory_cycle',
        },
      ],
      workbenchTask: {
        title: `${options.taskLabel}${options.code ? `：${options.code}` : ''}`,
        href: options.code ? `/assistant?code=${encodeURIComponent(options.code)}` : '/assistant',
        kind: 'assistant-result',
        payload: {
          code: options.code ?? null,
          sourceTool: options.sourceTool,
          action: card.action || null,
        },
      },
    });
  }

  private buildIndustryChainResultContract(
    payload: unknown,
    chains: Array<{
      id: string;
      name: string;
      upstream: string[];
      midstream: string[];
      downstream: string[];
    }>,
    keyword?: string,
    chainId?: string,
  ) {
    const primary = chains[0] ?? null;
    const followupQuery = primary?.name || keyword || chainId || '产业链';
    return buildResultContract({
      summary: primary
        ? `已找到 ${chains.length} 条产业链线索，当前聚焦 ${primary.name || primary.id || '首条产业链'}。`
        : `未找到明确产业链结果，建议调整关键词${keyword ? `“${keyword}”` : ''}后重试。`,
      availableViews: ['summary', 'next_step', ...(primary ? (['visual'] as const) : [])],
      recommendedActions: [
        {
          id: 'assistant.open-copilot-followup',
          actionId: 'assistant.open-copilot-followup',
          label: '打开 Copilot 继续追问',
          description: '继续围绕当前产业链结果做追问和联动。',
          payload: {
            keyword: keyword ?? null,
            chainId: chainId ?? null,
          },
        },
      ],
      recommendedLinks: [
        {
          id: 'industry-open-skills',
          label: '去技能中心',
          href: `/skills?skill=${encodeURIComponent('akshare-stock-deep-analysis')}`,
        },
        {
          id: 'industry-open-strategy-market',
          label: '去策略超市',
          href: `/strategy-market?from=assistant&task=strategy_review&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'industry-open-favorites',
          label: '去我的收藏',
          href: `/strategy-market?workspace=favorites&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'industry-open-mine',
          label: '去我的策略',
          href: `/strategy-market?workspace=mine&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'industry-open-factory',
          label: '去工厂运行态',
          href: `/strategy-market?from=assistant&task=factory_cycle&q=${encodeURIComponent(followupQuery)}`,
        },
      ],
      evidence: primary
        ? [
            { label: '产业链', value: primary.name || primary.id || '首条结果' },
            { label: '上游节点', value: String(primary.upstream.length) },
            { label: '中游节点', value: String(primary.midstream.length) },
            { label: '下游节点', value: String(primary.downstream.length) },
          ]
        : [],
      riskNotes: primary ? [] : ['当前结果为空，建议缩短关键词或改用更明确的产业链名称。'],
      freshness: extractFreshness(payload, null, '产业链结果'),
      platformMeta: extractPlatformMeta(payload, {
        sourceTool: 'get_industry_chain',
        referencePath: '/data/tool-catalog',
      }),
      skillSuggestions: this.buildAssistantSkillSuggestions(),
      strategySuggestions: [
        {
          id: 'industry-chain-strategy-followup',
          label: '去策略超市继续匹配相关策略',
          description: '围绕当前主题继续看策略族与工厂运行态。',
          query: followupQuery,
          task: 'strategy_review',
        },
        {
          id: 'industry-chain-factory-followup',
          label: '去工厂看运行态',
          description: '围绕当前主题查看工厂运行与治理状态。',
          query: followupQuery,
          task: 'factory_cycle',
        },
      ],
      workbenchTask: {
        title: `跟踪产业链${primary?.name ? `：${primary.name}` : ''}`,
        href: '/assistant',
        kind: 'industry-chain',
        payload: {
          keyword: keyword ?? null,
          chainId: chainId ?? null,
          primaryChain: primary?.name || primary?.id || null,
        },
      },
    });
  }

  private buildDailyReportResultContract(
    payload: unknown,
    report: {
      date: string;
      marketSummary: string;
      hotSectors: Record<string, unknown>[];
      sentiment: string;
      outlook: string;
      generatedAt: string;
    },
  ) {
    const primarySector = report.hotSectors[0]
      ? this.toText(
          report.hotSectors[0].name
            ?? report.hotSectors[0].sector
            ?? report.hotSectors[0].label,
        )
      : '';
    const followupQuery = primarySector || report.sentiment || '市场复盘';
    return buildResultContract({
      summary: report.marketSummary || `已生成 ${report.date || '当日'} 盘后复盘摘要。`,
      availableViews: ['summary', 'next_step', ...(report.hotSectors.length > 0 ? (['visual'] as const) : [])],
      recommendedActions: [
        {
          id: 'assistant.open-copilot-followup',
          actionId: 'assistant.open-copilot-followup',
          label: '打开 Copilot 继续追问',
          description: '围绕当前复盘结果继续形成后续研究动作。',
          payload: {
            date: report.date || null,
            primarySector: primarySector || null,
          },
        },
      ],
      recommendedLinks: [
        {
          id: 'daily-report-open-skills',
          label: '去技能中心',
          href: `/skills?skill=${encodeURIComponent('akshare-fund-news')}`,
        },
        {
          id: 'daily-report-open-strategy-market',
          label: '去策略超市',
          href: `/strategy-market?from=assistant&task=strategy_review&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'daily-report-open-favorites',
          label: '去我的收藏',
          href: `/strategy-market?workspace=favorites&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'daily-report-open-mine',
          label: '去我的策略',
          href: `/strategy-market?workspace=mine&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'daily-report-open-factory',
          label: '去工厂运行态',
          href: `/strategy-market?from=assistant&task=factory_cycle&q=${encodeURIComponent(followupQuery)}`,
        },
      ],
      evidence: [
        report.date ? { label: '复盘日期', value: report.date } : null,
        report.sentiment ? { label: '市场情绪', value: report.sentiment } : null,
        report.hotSectors.length > 0 ? { label: '热点板块数', value: String(report.hotSectors.length) } : null,
        primarySector ? { label: '首个热点', value: primarySector } : null,
      ].filter((item): item is NonNullable<typeof item> => item != null),
      riskNotes: uniqueStrings([report.outlook]),
      freshness: extractFreshness(payload, report.generatedAt || null, '盘后复盘'),
      platformMeta: extractPlatformMeta(payload, {
        sourceTool: 'generate_daily_report',
        referencePath: '/data/governance-report',
      }),
      skillSuggestions: this.buildAssistantSkillSuggestions(),
      strategySuggestions: [
        {
          id: 'daily-report-strategy-followup',
          label: '去策略超市继续跟踪热点',
          description: '把复盘里的热点板块带到策略页继续筛选。',
          query: followupQuery,
          task: 'factory_cycle',
        },
        {
          id: 'daily-report-factory-followup',
          label: '去工厂看运行态',
          description: '把复盘热点直接带到工厂运行态继续跟踪。',
          query: followupQuery,
          task: 'factory_cycle',
        },
      ],
      workbenchTask: {
        title: `复查盘后复盘${report.date ? `：${report.date}` : ''}`,
        href: '/assistant',
        kind: 'daily-report',
        payload: {
          date: report.date || null,
          sentiment: report.sentiment || null,
          primarySector: primarySector || null,
        },
      },
    });
  }

  private buildAssistantSkillSuggestions() {
    return [
      {
        skillId: 'akshare-stock-deep-analysis',
        label: '个股深度分析',
        reason: '把当前结果继续沉淀成更完整的研究包。',
        supportedTask: 'quick_scan',
      },
      {
        skillId: 'akshare-trading-decision',
        label: '交易决策计划',
        reason: '把当前判断继续转成更明确的交易计划。',
        supportedTask: 'trade_plan',
      },
      {
        skillId: 'akshare-fundamental',
        label: '基本面快照',
        reason: '快速补齐当前标的的基本面证据。',
        supportedTask: 'fundamental_snapshot',
      },
    ];
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
    const result = await callToolWithContract(
      primaryTool,
      attempts,
      async (name, args) => {
        const payload = await this.mcp.callTool(name, args);
        const toolError = this.extractToolError(payload);
        if (toolError) {
          throw new Error(toolError);
        }
        return payload;
      },
    );
    return {
      payload: result.payload,
      argsMatched: result.argsMatched,
      canonicalArgs: result.canonicalArgs,
      aliasHits: result.aliasHits,
      canonicalTool: result.canonicalTool,
    };
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
    if (record.success === false && typeof record.message === 'string' && record.message.trim()) {
      return record.message;
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
