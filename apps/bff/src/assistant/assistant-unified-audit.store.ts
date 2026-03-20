import { Injectable, Logger } from '@nestjs/common';
import { DbService } from '../db/db.service';

export type UnifiedDecisionDiffAuditEntry = {
  traceId?: string | null;
  userId?: string | null;
  stockCode: string;
  investmentStyle: 'aggressive' | 'balanced' | 'conservative';
  unifiedAction: string;
  actionAlignment: 'aligned' | 'mixed' | 'divergent';
  legacyActions: Array<{ source: string; action: string }>;
  disagreements: string[];
  diffSummary: string;
  details: Record<string, unknown>;
  createdAt: string;
};

export type UnifiedDecisionDiffAuditRecord = UnifiedDecisionDiffAuditEntry & {
  id: number;
};

export type UnifiedDecisionDiffAuditQuery = {
  limit?: number;
  stockCode?: string;
  actionAlignment?: 'aligned' | 'mixed' | 'divergent';
};

@Injectable()
export class AssistantUnifiedAuditStore {
  private readonly logger = new Logger(AssistantUnifiedAuditStore.name);
  private readonly entries: UnifiedDecisionDiffAuditRecord[] = [];
  private readonly maxSize = 300;
  private seq = 1;

  constructor(private readonly dbService: DbService) {}

  async append(entry: UnifiedDecisionDiffAuditEntry): Promise<number | null> {
    const record: UnifiedDecisionDiffAuditRecord = {
      ...entry,
      id: this.seq++,
    };

    this.entries.push(record);
    if (this.entries.length > this.maxSize) {
      this.entries.splice(0, this.entries.length - this.maxSize);
    }

    if (!this.dbService.enabled) {
      return record.id;
    }

    try {
      const result = await this.dbService.query<{ id: number }>(
        `INSERT INTO unified_decision_diff_audit
           (trace_id, user_id, stock_code, investment_style, unified_action, action_alignment,
            legacy_actions, disagreements, diff_summary, details, created_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10::jsonb,$11)
         RETURNING id`,
        [
          entry.traceId ?? null,
          entry.userId ?? null,
          entry.stockCode,
          entry.investmentStyle,
          entry.unifiedAction,
          entry.actionAlignment,
          JSON.stringify(entry.legacyActions),
          JSON.stringify(entry.disagreements),
          entry.diffSummary,
          JSON.stringify(entry.details ?? {}),
          entry.createdAt,
        ],
      );
      return Number(result.rows[0]?.id ?? record.id);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.logger.warn(`写入 unified diff 审计失败，已降级到内存: ${message}`);
      return record.id;
    }
  }

  async listByUser(
    userId: string,
    query: UnifiedDecisionDiffAuditQuery = {},
  ): Promise<UnifiedDecisionDiffAuditRecord[]> {
    const safe = Math.max(1, Math.min(100, Number(query.limit) || 20));
    const stockCode = String(query.stockCode ?? '').trim();
    const actionAlignment = String(query.actionAlignment ?? '').trim() as UnifiedDecisionDiffAuditQuery['actionAlignment'];

    if (!this.dbService.enabled) {
      return this.entries
        .filter((entry) => String(entry.userId ?? '') === String(userId ?? ''))
        .filter((entry) => !stockCode || entry.stockCode === stockCode)
        .filter((entry) => !actionAlignment || entry.actionAlignment === actionAlignment)
        .slice(-safe)
        .reverse();
    }

    try {
      const conditions = ['user_id = $1'];
      const params: unknown[] = [userId];

      if (stockCode) {
        params.push(stockCode);
        conditions.push(`stock_code = $${params.length}`);
      }

      if (actionAlignment) {
        params.push(actionAlignment);
        conditions.push(`action_alignment = $${params.length}`);
      }

      params.push(safe);

      const result = await this.dbService.query<{
        id: number;
        trace_id: string | null;
        user_id: string | null;
        stock_code: string;
        investment_style: 'aggressive' | 'balanced' | 'conservative';
        unified_action: string;
        action_alignment: 'aligned' | 'mixed' | 'divergent';
        legacy_actions: Array<{ source: string; action: string }> | string | null;
        disagreements: string[] | string | null;
        diff_summary: string;
        details: Record<string, unknown> | string | null;
        created_at: string | Date;
      }>(
        `SELECT id, trace_id, user_id, stock_code, investment_style, unified_action,
                action_alignment, legacy_actions, disagreements, diff_summary, details, created_at
           FROM unified_decision_diff_audit
          WHERE ${conditions.join(' AND ')}
          ORDER BY created_at DESC
          LIMIT $${params.length}`,
        params,
      );

      return result.rows.map((row) => ({
        id: Number(row.id),
        traceId: row.trace_id,
        userId: row.user_id,
        stockCode: row.stock_code,
        investmentStyle: row.investment_style,
        unifiedAction: row.unified_action,
        actionAlignment: row.action_alignment,
        legacyActions: this.parseJson<Array<{ source: string; action: string }>>(row.legacy_actions, []),
        disagreements: this.parseJson<string[]>(row.disagreements, []),
        diffSummary: row.diff_summary,
        details: this.parseJson<Record<string, unknown>>(row.details, {}),
        createdAt: new Date(row.created_at).toISOString(),
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.logger.warn(`读取 unified diff 审计失败，已降级到内存: ${message}`);
      return this.entries
        .filter((entry) => String(entry.userId ?? '') === String(userId ?? ''))
        .filter((entry) => !stockCode || entry.stockCode === stockCode)
        .filter((entry) => !actionAlignment || entry.actionAlignment === actionAlignment)
        .slice(-safe)
        .reverse();
    }
  }

  private parseJson<T>(value: unknown, fallback: T): T {
    if (value == null) return fallback;
    if (typeof value === 'string') {
      try {
        return JSON.parse(value) as T;
      } catch {
        return fallback;
      }
    }
    return value as T;
  }
}
