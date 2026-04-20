import { Injectable, NotFoundException } from '@nestjs/common';
import { existsSync } from 'fs';
import { appendFile, mkdir, readFile, rm, writeFile } from 'fs/promises';
import { dirname, isAbsolute, resolve } from 'path';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import { AuthService } from '../auth/auth.service';

@Injectable()
export class AdminService {
  private static readonly TOOL_TIMEOUT_MS = 5_000;

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
      const raw = await this.callToolWithTimeout('get_cache_stats', {});
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
      const raw = await this.callToolWithTimeout('clear_cache', {});
      const result = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
      mcpCleared = Number(result.cleared_count ?? 0);
    } catch {
      // ignore MCP clear failure
    }
    return { cleared: bffCleared, mcpCleared };
  }

  async getDeadLetters(): Promise<{ items: unknown[]; path?: string; count: number }> {
    try {
      const raw = await this.callToolWithTimeout('get_dead_letters', { limit: 20 });
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
      const raw = await this.callToolWithTimeout('batch_sync_klines', {
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
      const raw = await this.callToolWithTimeout('clear_dead_letters', {});
      const result = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
      return { removed: Number(result.removed ?? 0) };
    } catch {
      return { removed: 0 };
    }
  }

  async seedDeadLetters(count = 1): Promise<{ added: number; path: string }> {
    const safeCount = Math.max(1, Math.min(10, Number(count) || 1));
    let toolPath = 'cache/dead_letters/kline_save_failures.jsonl';

    try {
      const raw = await this.callToolWithTimeout('get_dead_letters', { limit: 1 });
      const result = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {};
      if (typeof result.path === 'string' && result.path.trim()) {
        toolPath = result.path.trim();
      }
    } catch {
      // fall back to the default cache path when MCP does not report the file location
    }

    const resolvedPath = this.resolveDeadLetterPath(toolPath);
    const now = Date.now();
    const records = Array.from({ length: safeCount }, (_, index) => ({
      id: `pw-audit-dead-letter-${now}-${index + 1}`,
      kind: 'save_failure',
      stock_code: index % 2 === 0 ? '600519' : '000001',
      retry: index === 0 ? 3 : 1,
      enqueued_at: Math.floor((now - index * 60_000) / 1000),
      failed_at: Math.floor((now + index) / 1000),
      error: 'Playwright 审计样本：用于验证死信队列重试与清理动作',
      klines_count: 0,
      sample_dates: [],
      source: 'bff.admin.seed_dead_letters',
    }));

    await mkdir(dirname(resolvedPath), { recursive: true });
    await appendFile(
      resolvedPath,
      `${records.map((record) => JSON.stringify(record)).join('\n')}\n`,
      'utf-8',
    );
    return { added: records.length, path: resolvedPath };
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

  private async callToolWithTimeout(name: string, args: Record<string, unknown>) {
    return await new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`${name} timed out after ${AdminService.TOOL_TIMEOUT_MS}ms`)), AdminService.TOOL_TIMEOUT_MS);
      this.mcp.callTool(name, args).then(
        (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        (error) => {
          clearTimeout(timer);
          reject(error);
        },
      );
    });
  }
}
