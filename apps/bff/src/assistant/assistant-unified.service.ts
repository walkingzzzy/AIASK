import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { AssistantService, type DecisionCardDto } from './assistant.service';
import {
  AssistantUnifiedAuditStore,
  type UnifiedDecisionDiffAuditQuery,
} from './assistant-unified-audit.store';
import {
  buildResultContract,
  extractFreshness,
  extractPlatformMeta,
  uniqueStrings,
} from '../common/result-contract';

export type UnifiedGateFlagDto = {
  name: string;
  status: string;
  severity: string;
  blocking: boolean;
  message: string;
  source?: string;
};

export type UnifiedPositionSignalDto = {
  label: string;
  suggestedPositionPct: number | null;
  positionCapPct: number | null;
  requestedStyle?: string;
  userRiskLevel?: string | null;
};

export type UnifiedLegacyResultDto = {
  source: string;
  action: string;
  confidence: number | null;
  summary: string;
  reasons: string[];
  risks: string[];
};

export type UnifiedLegacyComparisonDto = {
  enabled: boolean;
  comparedAt: string;
  actionAlignment: 'aligned' | 'mixed' | 'divergent';
  disagreements: string[];
  diffSummary: string;
  legacyResults: UnifiedLegacyResultDto[];
  auditId?: number | null;
  auditLogged?: boolean;
  traceId?: string | null;
  investmentStyle?: 'aggressive' | 'balanced' | 'conservative';
};

export type UnifiedDecisionCardDto = DecisionCardDto & {
  finalScore: number | null;
  gateFlags: UnifiedGateFlagDto[];
  vetoReason: string | null;
  positionSignal: UnifiedPositionSignalDto | null;
  rawAiAction?: string | null;
  recommendedHorizon?: string | null;
  updatedAt?: string | null;
  dataQuality?: Record<string, unknown> | null;
  fallbackReason?: string[];
};

type UnifiedDecisionRequest = {
  code: string;
  investmentStyle: 'aggressive' | 'balanced' | 'conservative';
  legacyMode: boolean;
};

@Injectable()
export class AssistantUnifiedService {
  constructor(
    private readonly mcp: McpGatewayService,
    private readonly assistantService: AssistantService,
    private readonly auditStore: AssistantUnifiedAuditStore,
  ) {}

  async getUnifiedDecisionSummary(
    code: string,
    investmentStyle: 'aggressive' | 'balanced' | 'conservative' = 'balanced',
    userId?: string,
    legacyMode = false,
    traceId?: string,
  ) {
    const payload = await this.callTool('get_unified_decision_summary', {
      code: code.trim(),
      investment_style: investmentStyle,
      ...(userId ? { user_id: userId } : {}),
    });

    const card = this.normalizeUnifiedCard(payload);
    return {
      card,
      raw: payload,
      detailsAvailable: Boolean(this.unwrapData(payload).details_available ?? true),
      request: { code: code.trim(), investmentStyle, legacyMode } satisfies UnifiedDecisionRequest,
      result_contract: this.buildUnifiedResultContract(card, payload, {
        code: code.trim(),
        investmentStyle,
        taskLabel: '统一决策摘要',
      }),
      ...(legacyMode
        ? {
            legacyComparison: await this.buildLegacyComparison({
              code,
              unifiedCard: card,
              investmentStyle,
              userId,
              traceId,
            }),
          }
        : {}),
    };
  }

  async getUnifiedDecisionDetails(
    code: string,
    investmentStyle: 'aggressive' | 'balanced' | 'conservative' = 'balanced',
    userId?: string,
    legacyMode = false,
    traceId?: string,
  ) {
    const payload = await this.callTool('get_unified_decision_details', {
      code: code.trim(),
      investment_style: investmentStyle,
      ...(userId ? { user_id: userId } : {}),
    });

    const data = this.unwrapData(payload);
    const card = this.normalizeUnifiedCard(payload);
    return {
      card,
      details: data.details ?? data,
      raw: payload,
      request: { code: code.trim(), investmentStyle, legacyMode } satisfies UnifiedDecisionRequest,
      result_contract: this.buildUnifiedResultContract(card, payload, {
        code: code.trim(),
        investmentStyle,
        taskLabel: '统一决策详情',
      }),
      ...(legacyMode
        ? {
            legacyComparison: await this.buildLegacyComparison({
              code,
              unifiedCard: card,
              investmentStyle,
              userId,
              traceId,
            }),
          }
        : {}),
    };
  }

  async getUnifiedDecisionDiffLogs(
    userId: string,
    query: UnifiedDecisionDiffAuditQuery = {},
  ) {
    const normalizedUserId = String(userId ?? '').trim();
    if (!normalizedUserId) {
      return {
        items: [],
        total: 0,
        filters: {
          limit: Math.max(1, Math.min(100, Number(query.limit) || 20)),
          stockCode: String(query.stockCode ?? '').trim() || null,
          actionAlignment: String(query.actionAlignment ?? '').trim() || null,
        },
      };
    }

    const logs = await this.auditStore.listByUser(normalizedUserId, query);
    return {
      items: logs,
      total: logs.length,
      filters: {
        limit: Math.max(1, Math.min(100, Number(query.limit) || 20)),
        stockCode: String(query.stockCode ?? '').trim() || null,
        actionAlignment: String(query.actionAlignment ?? '').trim() || null,
      },
    };
  }

  private unwrapData(payload: unknown): Record<string, unknown> {
    if (!payload || typeof payload !== 'object') return {};
    const record = payload as Record<string, unknown>;
    if (record.data && typeof record.data === 'object') {
      return record.data as Record<string, unknown>;
    }
    return record;
  }

  private normalizeUnifiedCard(payload: unknown): UnifiedDecisionCardDto {
    const data = this.unwrapData(payload);
    const toText = (value: unknown): string => {
      if (typeof value === 'string') return value.trim();
      if (typeof value === 'number' || typeof value === 'boolean') return String(value);
      if (Array.isArray(value)) return value.map((item) => toText(item)).filter(Boolean).join('；');
      if (value && typeof value === 'object') {
        const record = value as Record<string, unknown>;
        const preferred = ['summary', 'analysis', 'conclusion', 'description', 'reason', 'label', 'message'];
        for (const key of preferred) {
          const text = toText(record[key]);
          if (text) return text;
        }
      }
      return '';
    };
    const toArr = (value: unknown): string[] => {
      if (Array.isArray(value)) return value.map((item) => toText(item)).filter(Boolean);
      if (typeof value === 'string') return value.split(/[;；\n]/).map((item) => item.trim()).filter(Boolean);
      return [];
    };
    const toNumber = (value: unknown): number | null => {
      const numeric = Number(value);
      return Number.isFinite(numeric) ? numeric : null;
    };

    const rawProvenance = data.data_provenance ?? data.dataProvenance;
    const dataProvenance = Array.isArray(rawProvenance)
      ? rawProvenance.map((item) => {
          if (typeof item === 'string') return item;
          if (item && typeof item === 'object') {
            const row = item as Record<string, unknown>;
            return {
              source: toText(row.source),
              dataset: toText(row.dataset),
              timestamp: toText(row.timestamp),
            };
          }
          return toText(item);
        }).filter((item) => {
          if (typeof item === 'string') return item.length > 0;
          return Boolean(item.source || item.dataset || item.timestamp);
        })
      : [];

    const gateFlags = Array.isArray(data.gate_flags)
      ? data.gate_flags.map((item) => {
          const row = item && typeof item === 'object' ? (item as Record<string, unknown>) : {};
          return {
            name: toText(row.name),
            status: toText(row.status),
            severity: toText(row.severity) || 'low',
            blocking: Boolean(row.blocking),
            message: toText(row.message),
            source: toText(row.source) || undefined,
          };
        }).filter((item) => item.name || item.message)
      : [];

    const positionSignal = data.position_signal && typeof data.position_signal === 'object'
      ? (() => {
          const row = data.position_signal as Record<string, unknown>;
          return {
            label: toText(row.label) || '暂不出手',
            suggestedPositionPct: toNumber(row.suggested_position_pct ?? row.suggestedPositionPct),
            positionCapPct: toNumber(row.position_cap_pct ?? row.positionCapPct),
            requestedStyle: toText(row.requested_style ?? row.requestedStyle) || undefined,
            userRiskLevel: toText(row.user_risk_level ?? row.userRiskLevel) || null,
          };
        })()
      : null;

    const confidence = (() => {
      const numeric = toNumber(data.confidence);
      if (numeric == null) return null;
      return numeric > 1 ? numeric / 100 : numeric;
    })();

    const fallbackReason = Array.isArray(data.fallback_reason)
      ? data.fallback_reason.map((item) => toText(item)).filter(Boolean)
      : [];

    return {
      action: toText(data.action),
      confidence,
      summary: toText(data.summary),
      reasons: toArr(data.reasons),
      executionPlan: positionSignal?.label ? [`建议仓位：${positionSignal.label}`] : [],
      risks: toArr(data.risks),
      dataProvenance,
      complianceNotice:
        toText(data.compliance_notice ?? data.complianceNotice) || '本分析结果仅供参考，不构成投资建议。',
      finalScore: toNumber(data.final_score ?? data.finalScore),
      gateFlags,
      vetoReason: toText(data.veto_reason ?? data.vetoReason) || null,
      positionSignal,
      rawAiAction: toText(data.raw_ai_action ?? data.rawAiAction) || null,
      recommendedHorizon: toText(data.recommended_horizon ?? data.recommendedHorizon) || null,
      updatedAt: toText(data.updated_at ?? data.updatedAt) || null,
      dataQuality: data.data_quality && typeof data.data_quality === 'object'
        ? (data.data_quality as Record<string, unknown>)
        : null,
      fallbackReason,
    };
  }

  private normalizeLegacyAction(action: string): string {
    const value = String(action || '').trim().toLowerCase();
    if (value.includes('buy')) return 'buy';
    if (value.includes('sell') || value.includes('avoid')) return 'sell';
    if (value.includes('reduce') || value.includes('consider_sell')) return 'reduce';
    if (value.includes('hold')) return 'hold';
    if (value.includes('wait') || value.includes('watch')) return 'watch';
    return value || 'unknown';
  }

  private buildUnifiedResultContract(
    card: UnifiedDecisionCardDto,
    payload: unknown,
    options: {
      code: string;
      investmentStyle: 'aggressive' | 'balanced' | 'conservative';
      taskLabel: string;
    },
  ) {
    const followupQuery = options.code;
    const evidence = [
      card.action ? { label: '建议动作', value: card.action, tone: 'positive' as const } : null,
      card.finalScore != null ? { label: '综合评分', value: String(card.finalScore) } : null,
      card.positionSignal?.label ? { label: '建议仓位', value: card.positionSignal.label } : null,
      ...card.reasons.slice(0, 3).map((reason) => ({ label: '关键信号', value: reason })),
    ].filter((item): item is NonNullable<typeof item> => item != null);
    const gateWarnings = card.gateFlags
      .filter((flag) => flag.blocking || flag.severity === 'high')
      .map((flag) => `${flag.name || '门禁'}：${flag.message}`);

    return buildResultContract({
      summary: card.summary || `${options.taskLabel}已生成，请继续查看下一步建议。`,
      availableViews: ['summary', 'next_step', 'visual'],
      recommendedActions: [
        {
          id: 'assistant.open-copilot-followup',
          actionId: 'assistant.open-copilot-followup',
          label: '打开 Copilot 继续追问',
          description: '把统一决策结果继续转成下一步研究与执行动作。',
          payload: {
            code: options.code,
            investmentStyle: options.investmentStyle,
          },
        },
        {
          id: 'assistant.load-unified-details',
          actionId: 'assistant.load-unified-details',
          label: '展开统一决策详情',
          description: '继续拉取统一决策详情和差异对比。',
          payload: {
            code: options.code,
            investmentStyle: options.investmentStyle,
          },
        },
      ],
      recommendedLinks: [
        {
          id: 'unified-open-stock',
          label: '个股详情',
          href: `/stock?code=${encodeURIComponent(options.code)}`,
        },
        {
          id: 'unified-open-skills',
          label: '去技能中心',
          href: `/skills?skill=${encodeURIComponent('akshare-stock-deep-analysis')}`,
        },
        {
          id: 'unified-open-strategy-market',
          label: '去策略超市',
          href: `/strategy-market?from=assistant&task=strategy_review&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'unified-open-favorites',
          label: '去我的收藏',
          href: `/strategy-market?workspace=favorites&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'unified-open-mine',
          label: '去我的策略',
          href: `/strategy-market?workspace=mine&from=assistant&q=${encodeURIComponent(followupQuery)}`,
        },
        {
          id: 'unified-open-factory',
          label: '去工厂运行态',
          href: `/strategy-market?from=assistant&task=factory_cycle&q=${encodeURIComponent(followupQuery)}`,
        },
      ],
      evidence,
      riskNotes: uniqueStrings([
        ...card.risks,
        ...gateWarnings,
        card.vetoReason,
        card.complianceNotice,
      ]),
      freshness: extractFreshness(payload, card.updatedAt || null, '统一决策结果'),
      platformMeta: extractPlatformMeta(payload, {
        sourceTool: 'get_unified_decision_summary',
        referencePath: '/data/tool-catalog',
      }),
      skillSuggestions: [
        {
          skillId: 'akshare-stock-deep-analysis',
          label: '个股深度分析',
          reason: '补齐统一决策背后的详细证据。',
          supportedTask: 'quick_scan',
        },
        {
          skillId: 'akshare-trading-decision',
          label: '交易决策计划',
          reason: '把统一决策继续转成执行计划。',
          supportedTask: 'trade_plan',
        },
        {
          skillId: 'akshare-fundamental',
          label: '基本面快照',
          reason: '快速补齐当前标的基本面上下文。',
          supportedTask: 'fundamental_snapshot',
        },
      ],
      strategySuggestions: [
        {
          id: 'unified-decision-strategy-followup',
          label: '去策略超市继续研究',
          description: '基于统一决策结论继续看相关策略与工厂运行态。',
          query: followupQuery,
          task: 'strategy_review',
        },
        {
          id: 'unified-decision-factory-followup',
          label: '去工厂看运行态',
          description: '基于统一决策结论继续看工厂运行与治理状态。',
          query: followupQuery,
          task: 'factory_cycle',
        },
      ],
      workbenchTask: {
        title: `${options.taskLabel}：${options.code}`,
        href: `/assistant?code=${encodeURIComponent(options.code)}`,
        kind: 'assistant-unified-decision',
        payload: {
          code: options.code,
          investmentStyle: options.investmentStyle,
          action: card.action || null,
        },
      },
    });
  }

  private async buildLegacyComparison({
    code,
    unifiedCard,
    investmentStyle,
    userId,
    traceId,
  }: {
    code: string;
    unifiedCard: UnifiedDecisionCardDto;
    investmentStyle: 'aggressive' | 'balanced' | 'conservative';
    userId?: string;
    traceId?: string;
  }): Promise<UnifiedLegacyComparisonDto> {
    const stockCode = code.trim();
    const comparedAt = new Date().toISOString();
    const settled = await Promise.allSettled([
      this.assistantService.shouldBuy(stockCode),
      this.assistantService.diagnosis(stockCode),
      this.assistantService.decisionManagerAnalyze(stockCode),
    ]);

    const legacyResults: UnifiedLegacyResultDto[] = settled.flatMap((result, index) => {
      const source = ['should_i_buy', 'smart_stock_diagnosis', 'decision_manager.analyze'][index];
      if (result.status !== 'fulfilled') {
        return [];
      }
      const card = result.value.card;
      return [{
        source,
        action: this.normalizeLegacyAction(card.action),
        confidence: card.confidence,
        summary: card.summary,
        reasons: card.reasons,
        risks: card.risks,
      }];
    });

    const unifiedAction = this.normalizeLegacyAction(unifiedCard.action);
    const disagreements = legacyResults.flatMap((item) => {
      const rows: string[] = [];
      if (item.action !== unifiedAction) {
        rows.push(`${item.source} 与统一决策动作不一致（${item.action} vs ${unifiedAction}）`);
      }
      if (item.confidence != null && unifiedCard.confidence != null && Math.abs(item.confidence - unifiedCard.confidence) >= 0.2) {
        rows.push(`${item.source} 与统一决策置信度差异较大`);
      }
      return rows;
    });

    const alignedCount = legacyResults.filter((item) => item.action === unifiedAction).length;
    const actionAlignment: 'aligned' | 'mixed' | 'divergent' = alignedCount === legacyResults.length
      ? 'aligned'
      : alignedCount === 0
        ? 'divergent'
        : 'mixed';

    let diffSummary = '已启用旧入口对照。';
    if (!legacyResults.length) {
      diffSummary = '已启用旧入口对照，但旧入口结果暂不可用。';
    } else if (actionAlignment === 'aligned') {
      diffSummary = '统一决策与旧入口整体方向一致，可用作灰度收敛参考。';
    } else if (actionAlignment === 'divergent') {
      diffSummary = '统一决策与旧入口方向明显分歧，建议重点审查事件闸门和量化证据。';
    } else {
      diffSummary = '统一决策与旧入口部分一致、部分分歧，建议结合详情层逐项复核。';
    }

    const auditId = await this.auditStore.append({
      traceId: traceId ?? null,
      userId: userId ?? null,
      stockCode,
      investmentStyle,
      unifiedAction,
      actionAlignment,
      legacyActions: legacyResults.map((item) => ({ source: item.source, action: item.action })),
      disagreements,
      diffSummary,
      details: {
        unified: {
          action: unifiedAction,
          confidence: unifiedCard.confidence,
          summary: unifiedCard.summary,
          vetoReason: unifiedCard.vetoReason,
          finalScore: unifiedCard.finalScore,
        },
        legacyResults,
      },
      createdAt: comparedAt,
    });

    return {
      enabled: true,
      comparedAt,
      actionAlignment,
      disagreements,
      diffSummary,
      legacyResults,
      auditId,
      auditLogged: auditId != null,
      traceId: traceId ?? null,
      investmentStyle,
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      const payload = await this.mcp.callTool(name, args);
      const toolError = this.extractToolError(payload);
      if (toolError) {
        throw new Error(toolError);
      }
      return payload;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `MCP ${name} 调用失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
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
