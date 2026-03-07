import { Injectable, NotFoundException } from '@nestjs/common';
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
    return {
      ...health,
      totalCalls: 0,
      avgLatency: 0,
      p99Latency: 0,
      errorRate: 0,
      tools: [],
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
      return {
        items: records,
        path: result.path as string | undefined,
        count: Number(result.count ?? records.length),
      };
    } catch {
      return { items: [], count: 0 };
    }
  }

  async retryDeadLetter(id: string): Promise<{ success: boolean; message: string }> {
    const { items } = await this.getDeadLetters();
    const found = Array.isArray(items)
      ? items.find((r) => r && typeof r === 'object' && (r as Record<string, unknown>).id === id)
      : undefined;
    if (!found) {
      throw new NotFoundException(`Dead letter ${id} not found`);
    }
    return {
      success: false,
      message: 'MCP does not support per-item retry; use clear and re-sync.',
    };
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
}
