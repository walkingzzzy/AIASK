import { Injectable, NotFoundException } from '@nestjs/common';
import { existsSync } from 'fs';
import { readFile, rm, writeFile } from 'fs/promises';
import { isAbsolute, resolve } from 'path';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import { AuthService } from '../auth/auth.service';

@Injectable()
export class AdminService {
  constructor(
    private readonly mcp: McpGatewayService,
    private readonly cache: CommonCacheService,
    private readonly authService: AuthService,
  ) {}

  async getMcpStats(): Promise<Record<string, unknown>> {
    const health = await this.mcp.checkAvailableTools();
    const metrics = this.mcp.getMetricsSnapshot();
    return {
      ...health,
      ...metrics,
    };
  }

  async getCacheStats(): Promise<Record<string, unknown>> {
    const bff = this.cache.getStats();
    let mcp: Record<string, unknown> = {};
    try {
      const raw = await this.mcp.callTool('get_cache_stats', {});
      mcp = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
    } catch {
      mcp = { error: 'MCP unavailable' };
    }

    const hitRate = bff.hitRate ?? 0;
    const totalKeys = bff.memorySize ?? 0;
    const hits = bff.hits ?? 0;
    const misses = bff.misses ?? 0;

    return {
      hitRate,
      totalKeys,
      hits,
      misses,
      memoryUsed: bff.redisReady ? 'Redis' : `${bff.memorySize ?? 0} keys (memory)`,
      prefixes: bff.memorySize
        ? [{ prefix: 'bff:cache', count: bff.memorySize, hitRate }]
        : [],
      bff,
      mcp,
    };
  }

  async clearCache(prefix?: string): Promise<{ cleared: number; mcpCleared?: number }> {
    const bffCleared = await this.cache.clear(prefix);
    let mcpCleared = 0;
    try {
      const raw = await this.mcp.callTool('clear_cache', {});
      const result = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
      mcpCleared = Number(result.cleared_count ?? 0);
    } catch {
      // ignore MCP clear failure
    }
    return { cleared: bffCleared, mcpCleared };
  }

  async getDeadLetters(): Promise<{ items: unknown[]; path?: string; count: number }> {
    try {
      const raw = await this.mcp.callTool('get_dead_letters', { limit: 20 });
      const result = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
      const records = Array.isArray(result.records) ? result.records : [];
      const items = records.map((record, index) => this.normalizeDeadLetterRecord(record, index));
      return {
        items,
        path: result.path as string | undefined,
        count: Number(result.count ?? items.length),
      };
    } catch {
      return { items: [], count: 0 };
    }
  }

  async retryDeadLetter(id: string): Promise<{ success: boolean; message: string }> {
    const { items, path } = await this.getDeadLetters();
    const found = Array.isArray(items)
      ? items.find((r) => r && typeof r === 'object' && (r as Record<string, unknown>).id === id)
      : undefined;
    if (!found) {
      throw new NotFoundException(`Dead letter ${id} not found`);
    }

    const record = found as Record<string, unknown>;
    const payload = record.payload && typeof record.payload === 'object' && !Array.isArray(record.payload)
      ? record.payload as Record<string, unknown>
      : record;
    const stockCode = String(payload.stock_code ?? payload.stockCode ?? '').trim();
    if (!stockCode) {
      return {
        success: false,
        message: '死信缺少 stock_code，无法执行重同步',
      };
    }

    try {
      const raw = await this.mcp.callTool('batch_sync_klines', {
        codes: [stockCode],
        period: 'daily',
      });
      const result = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
      const data = result.data && typeof result.data === 'object' && !Array.isArray(result.data)
        ? result.data as Record<string, unknown>
        : {};
      const failed = Number(data.failed ?? 0);
      const succeeded = Number(data.success ?? 0);
      if (!result.success || failed > 0 || succeeded <= 0) {
        const errors = Array.isArray(data.errors) ? data.errors : [];
        return {
          success: false,
          message: `重同步失败: ${errors.length > 0 ? JSON.stringify(errors[0]) : '未返回成功结果'}`,
        };
      }

      if (path) {
        await this.removeDeadLetterById(path, id);
      }

      return {
        success: true,
        message: `已重新同步 ${stockCode}，并移除对应死信记录`,
      };
    } catch (error) {
      return {
        success: false,
        message: error instanceof Error ? error.message : String(error),
      };
    }
  }

  async clearDeadLetters(): Promise<{ removed: number }> {
    try {
      const raw = await this.mcp.callTool('clear_dead_letters', {});
      const result = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
      return { removed: Number(result.removed ?? 0) };
    } catch {
      return { removed: 0 };
    }
  }

  async listUsers(): Promise<Array<{ id: string; username: string; role: string; status: string; createdAt?: string; lastActive?: string }>> {
    const rows = await this.authService.listUsersForAdmin();
    return rows.map((u) => ({
      id: u.id,
      username: u.username,
      role: u.role,
      status: u.active ? 'active' : 'inactive',
      createdAt: u.createdAt,
      lastActive: undefined,
    }));
  }

  private normalizeDeadLetterRecord(record: unknown, index: number) {
    const row = record && typeof record === 'object' && !Array.isArray(record)
      ? (record as Record<string, unknown>)
      : {};

    const failedAt = this.toIsoTimestamp(row.failed_at ?? row.failedAt ?? row.timestamp);
    const enqueuedAt = this.toIsoTimestamp(row.enqueued_at ?? row.enqueuedAt);
    const rawId = row.id ?? row.dead_letter_id ?? row.deadLetterId;
    const stockCode = String(row.stock_code ?? row.stockCode ?? '').trim();
    const retry = Number(row.retry ?? row.retries ?? 0);
    const stableId = String(
      rawId ??
      `${stockCode || 'dead-letter'}:${row.failed_at ?? row.failedAt ?? failedAt ?? index}:${index}`,
    );

    return {
      ...row,
      id: stableId,
      tool: String(row.tool ?? row.toolName ?? 'data_sync'),
      error: String(row.error ?? row.message ?? '未知错误'),
      payload: row,
      timestamp: failedAt ?? enqueuedAt ?? '',
      retries: Number.isFinite(retry) ? retry : 0,
    };
  }

  private toIsoTimestamp(value: unknown): string | null {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return new Date(value * 1000).toISOString();
    }
    if (typeof value === 'string' && value.trim()) {
      const asNumber = Number(value);
      if (Number.isFinite(asNumber)) {
        return new Date(asNumber * 1000).toISOString();
      }
      const asDate = new Date(value);
      if (!Number.isNaN(asDate.getTime())) {
        return asDate.toISOString();
      }
    }
    return null;
  }

  private async removeDeadLetterById(path: string, id: string) {
    const resolvedPath = this.resolveDeadLetterPath(path);
    const content = await readFile(resolvedPath, 'utf-8');
    const lines = content.split(/\r?\n/).filter((line) => line.trim());
    const kept = lines.filter((line, index) => {
      try {
        const parsed = JSON.parse(line) as Record<string, unknown>;
        return this.normalizeDeadLetterRecord(parsed, index).id !== id;
      } catch {
        return true;
      }
    });

    if (kept.length === 0) {
      await rm(resolvedPath, { force: true });
      return;
    }

    await writeFile(resolvedPath, `${kept.join('\n')}\n`, 'utf-8');
  }

  private resolveDeadLetterPath(path: string) {
    if (isAbsolute(path)) return path;

    const candidates = [
      resolve(process.cwd(), 'packages', 'akshare-mcp', path),
      resolve(process.cwd(), '..', '..', 'packages', 'akshare-mcp', path),
      resolve(process.cwd(), path),
    ];

    const matched = candidates.find((candidate) => existsSync(candidate));
    return matched ?? candidates[0];
  }
}
