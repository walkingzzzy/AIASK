import { Injectable, Logger } from '@nestjs/common';
import { DbService } from '../db/db.service';

export type BehaviorEventInput = {
  sessionId: string;
  pageKey: string;
  route: string;
  eventType: string;
  targetType?: string;
  targetLabel?: string;
  targetId?: string;
  targetTestId?: string;
  payload?: Record<string, unknown>;
  source?: string;
  occurredAt?: string;
};

export type BehaviorEventRecord = {
  id: string;
  sessionId: string;
  pageKey: string;
  route: string;
  eventType: string;
  targetType?: string;
  targetLabel?: string;
  targetId?: string;
  targetTestId?: string;
  payload: Record<string, unknown>;
  source: string;
  createdAt: string;
};

@Injectable()
export class BehaviorStore {
  private readonly logger = new Logger(BehaviorStore.name);
  private readonly entries = new Map<string, BehaviorEventRecord[]>();
  private readonly maxMemoryEntries = 2_000;

  constructor(private readonly dbService: DbService) {}

  async append(userId: string, inputs: BehaviorEventInput[]): Promise<number> {
    const normalized = inputs
      .map((input, index) => this.normalizeInput(input, index))
      .filter((item): item is BehaviorEventRecord => item !== null);

    if (!normalized.length) {
      return 0;
    }

    const current = this.entries.get(userId) ?? [];
    current.push(...normalized);
    if (current.length > this.maxMemoryEntries) {
      current.splice(0, current.length - this.maxMemoryEntries);
    }
    this.entries.set(userId, current);

    if (this.dbService.enabled) {
      try {
        await this.dbService.tx(async (client) => {
          for (const event of normalized) {
            await client.query(
              `INSERT INTO frontend_behavior_events
                (user_id, session_id, page_key, route, event_type, target_type, target_label, target_id, target_testid, payload, source, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11,$12)`,
              [
                userId,
                event.sessionId,
                event.pageKey,
                event.route,
                event.eventType,
                event.targetType ?? null,
                event.targetLabel ?? null,
                event.targetId ?? null,
                event.targetTestId ?? null,
                JSON.stringify(event.payload ?? {}),
                event.source,
                event.createdAt,
              ],
            );
          }
        });
      } catch (error) {
        this.logger.warn(`写入前端行为事件失败，已回退内存: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    return normalized.length;
  }

  async listByUser(
    userId: string,
    options: { limit?: number; days?: number; source?: string | null; pageKey?: string | null; eventType?: string | null } = {},
  ): Promise<BehaviorEventRecord[]> {
    const limit = Math.max(1, Math.min(200, Number(options.limit) || 50));
    const days = Math.max(1, Math.min(30, Number(options.days) || 30));
    const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

    if (this.dbService.enabled) {
      try {
        const params: unknown[] = [userId, since.toISOString()];
        const clauses = ['user_id = $1', 'created_at >= $2'];

        if (options.source) {
          params.push(options.source);
          clauses.push(`source = $${params.length}`);
        }
        if (options.pageKey) {
          params.push(options.pageKey);
          clauses.push(`page_key = $${params.length}`);
        }
        if (options.eventType) {
          params.push(options.eventType);
          clauses.push(`event_type = $${params.length}`);
        }
        params.push(limit);

        const result = await this.dbService.query<{
          id: number;
          session_id: string;
          page_key: string;
          route: string;
          event_type: string;
          target_type: string | null;
          target_label: string | null;
          target_id: string | null;
          target_testid: string | null;
          payload: Record<string, unknown> | string | null;
          source: string;
          created_at: string | Date;
        }>(
          `SELECT id, session_id, page_key, route, event_type, target_type, target_label, target_id, target_testid, payload, source, created_at
             FROM frontend_behavior_events
            WHERE ${clauses.join(' AND ')}
            ORDER BY created_at DESC
            LIMIT $${params.length}`,
          params,
        );

        return result.rows.map((row) => ({
          id: String(row.id),
          sessionId: row.session_id,
          pageKey: row.page_key,
          route: row.route,
          eventType: row.event_type,
          targetType: row.target_type ?? undefined,
          targetLabel: row.target_label ?? undefined,
          targetId: row.target_id ?? undefined,
          targetTestId: row.target_testid ?? undefined,
          payload: this.readPayload(row.payload),
          source: row.source,
          createdAt: new Date(row.created_at).toISOString(),
        }));
      } catch (error) {
        this.logger.warn(`读取前端行为事件失败，已回退内存: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    return (this.entries.get(userId) ?? [])
      .filter((event) => {
        const createdAt = new Date(event.createdAt);
        if (createdAt < since) return false;
        if (options.source && event.source !== options.source) return false;
        if (options.pageKey && event.pageKey !== options.pageKey) return false;
        if (options.eventType && event.eventType !== options.eventType) return false;
        return true;
      })
      .slice(-limit)
      .reverse();
  }

  private normalizeInput(input: BehaviorEventInput, index: number): BehaviorEventRecord | null {
    const sessionId = String(input.sessionId ?? '').trim();
    const pageKey = String(input.pageKey ?? '').trim();
    const route = String(input.route ?? '').trim();
    const eventType = String(input.eventType ?? '').trim();
    if (!sessionId || !pageKey || !route || !eventType) {
      return null;
    }

    const timestamp = this.normalizeTimestamp(input.occurredAt);
    return {
      id: `${sessionId}:${timestamp}:${index}`,
      sessionId,
      pageKey,
      route,
      eventType,
      targetType: this.normalizeOptionalString(input.targetType, 64),
      targetLabel: this.normalizeOptionalString(input.targetLabel, 240),
      targetId: this.normalizeOptionalString(input.targetId, 255),
      targetTestId: this.normalizeOptionalString(input.targetTestId, 255),
      payload: input.payload && typeof input.payload === 'object' && !Array.isArray(input.payload)
        ? input.payload
        : {},
      source: this.normalizeOptionalString(input.source, 128) ?? 'web',
      createdAt: timestamp,
    };
  }

  private normalizeTimestamp(value: string | undefined) {
    const parsed = value ? new Date(value) : null;
    if (parsed && !Number.isNaN(parsed.getTime())) {
      return parsed.toISOString();
    }
    return new Date().toISOString();
  }

  private normalizeOptionalString(value: string | undefined, maxLength: number) {
    const normalized = String(value ?? '').trim();
    return normalized ? normalized.slice(0, maxLength) : undefined;
  }

  private readPayload(value: Record<string, unknown> | string | null) {
    if (!value) return {};
    if (typeof value === 'string') {
      try {
        const parsed = JSON.parse(value);
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
          ? parsed as Record<string, unknown>
          : {};
      } catch {
        return {};
      }
    }
    return value;
  }
}
