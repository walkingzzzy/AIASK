import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import type { DecisionCardDto } from './assistant.service';

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

export type UnifiedDecisionCardDto = DecisionCardDto & {
  finalScore: number | null;
  gateFlags: UnifiedGateFlagDto[];
  vetoReason: string | null;
  positionSignal: UnifiedPositionSignalDto | null;
};

type UnifiedDecisionRequest = {
  code: string;
  investmentStyle: 'aggressive' | 'balanced' | 'conservative';
};

@Injectable()
export class AssistantUnifiedService {
  constructor(private readonly mcp: McpGatewayService) {}

  async getUnifiedDecisionSummary(
    code: string,
    investmentStyle: 'aggressive' | 'balanced' | 'conservative' = 'balanced',
    userId?: string,
  ) {
    const payload = await this.callTool('get_unified_decision_summary', {
      code: code.trim(),
      investment_style: investmentStyle,
      ...(userId ? { user_id: userId } : {}),
    });

    return {
      card: this.normalizeUnifiedCard(payload),
      raw: payload,
      detailsAvailable: Boolean(this.unwrapData(payload).details_available ?? true),
      request: { code: code.trim(), investmentStyle } satisfies UnifiedDecisionRequest,
    };
  }

  async getUnifiedDecisionDetails(
    code: string,
    investmentStyle: 'aggressive' | 'balanced' | 'conservative' = 'balanced',
    userId?: string,
  ) {
    const payload = await this.callTool('get_unified_decision_details', {
      code: code.trim(),
      investment_style: investmentStyle,
      ...(userId ? { user_id: userId } : {}),
    });

    const data = this.unwrapData(payload);
    return {
      card: this.normalizeUnifiedCard(payload),
      details: data.details ?? data,
      raw: payload,
      request: { code: code.trim(), investmentStyle } satisfies UnifiedDecisionRequest,
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
          if (typeof item === "string") return item;
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
