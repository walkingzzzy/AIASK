import { Injectable, Logger } from '@nestjs/common';
import { DbService } from '../db/db.service';

export type AuditEntry = {
  trace_id: string;
  method: string;
  path: string;
  status: number;
  duration_ms: number;
  user: { id: string; username: string; role: 'admin' | 'user' } | null;
  ts: string;
};

@Injectable()
export class AuditStore {
  private readonly logger = new Logger(AuditStore.name);
  private readonly entries: AuditEntry[] = [];
  private readonly maxSize = 300;

  constructor(private readonly dbService: DbService) {}

  append(entry: AuditEntry) {
    this.entries.push(entry);
    if (this.entries.length > this.maxSize) {
      this.entries.splice(0, this.entries.length - this.maxSize);
    }

    if (this.dbService.enabled) {
      void this.dbService
        .query(
          `INSERT INTO audit_logs
             (trace_id, method, path, status, duration_ms, user_id, username, user_role, ts)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
          [
            entry.trace_id,
            entry.method,
            entry.path,
            entry.status,
            entry.duration_ms,
            entry.user?.id ?? null,
            entry.user?.username ?? null,
            entry.user?.role ?? null,
            entry.ts,
          ],
        )
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : String(error);
          this.logger.warn(`写入审计日志失败，已降级到内存: ${message}`);
        });
    }
  }

  async list(limit = 20): Promise<AuditEntry[]> {
    const safe = Math.max(1, Math.min(200, Number(limit) || 20));

    if (this.dbService.enabled) {
      try {
        const result = await this.dbService.query<{
          trace_id: string;
          method: string;
          path: string;
          status: number;
          duration_ms: number;
          user_id: string | null;
          username: string | null;
          user_role: string | null;
          ts: string | Date;
        }>(
          `SELECT trace_id, method, path, status, duration_ms, user_id, username, user_role, ts
             FROM audit_logs
            ORDER BY ts DESC
            LIMIT $1`,
          [safe],
        );

        return result.rows.map((row: {
          trace_id: string;
          method: string;
          path: string;
          status: number;
          duration_ms: number;
          user_id: string | null;
          username: string | null;
          user_role: string | null;
          ts: string | Date;
        }) => ({
          trace_id: row.trace_id,
          method: row.method,
          path: row.path,
          status: Number(row.status),
          duration_ms: Number(row.duration_ms),
          user:
            row.user_id && row.username
              ? {
                  id: row.user_id,
                  username: row.username,
                  role: row.user_role === 'admin' ? 'admin' : 'user',
                }
              : null,
          ts: new Date(row.ts).toISOString(),
        }));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        this.logger.warn(`读取审计日志失败，已降级到内存: ${message}`);
      }
    }

    return this.entries.slice(-safe).reverse();
  }
}

