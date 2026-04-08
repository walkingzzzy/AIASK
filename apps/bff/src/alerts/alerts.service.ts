import { BadGatewayException, Injectable, Optional } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';
import { WsGateway } from '../ws/ws.gateway';

export type CreateAlertInput = {
  code: string;
  indicator: string;
  condition: '>' | '<' | '>=' | '<=' | '==';
  value: number;
};

export type NormalizedAlertItem = {
  id: string; code: string; indicator: string; condition: string; value: number | null;
};

export type AlertsListDto = {
  status: string;
  items: NormalizedAlertItem[];
  sourceTool: 'alerts_manager';
  argsMatched: Record<string, unknown>;
  meta: {
    fetchedAt: string;
    cache: { hit: boolean; backend: 'redis' | 'memory' | 'none'; key: string; ttlSeconds: number };
  };
};

@Injectable()
export class AlertsService {
  private static readonly LIST_TTL_SECONDS = 30;

  constructor(
    private readonly mcpGatewayService: McpGatewayService,
    private readonly cacheService: CommonCacheService,
    @Optional() private readonly wsGateway?: WsGateway,
  ) { }

  async create(input: CreateAlertInput, userId = 'default') {
    const normalized = {
      code: input.code.trim(),
      indicator: input.indicator.trim(),
      condition: input.condition,
      value: Number(input.value),
      user_id: userId,
    };

    const args = {
      action: 'create',
      params: normalized,
    };

    const payload = await this.callTool('alerts_manager', args);
    const alertId =
      this.pickString(payload, ['data.alert_id', 'data.alertId', 'data.id', 'alert_id', 'alertId', 'id']) ||
      `alert_${normalized.code}_${normalized.indicator}_${normalized.condition}`;

    await this.clearUserListCache(userId);

    return {
      alertId,
      sourceTool: 'alerts_manager' as const,
      argsMatched: args,
      result: payload,
    };
  }

  /** 检查告警并推送触发的告警到 WebSocket */
  async checkAndPush(userId = 'default') {
    const payload = await this.callTool('alerts_manager', {
      action: 'check',
      params: { user_id: userId },
    });
    const triggered = this.pickArray(payload, ['data.triggered', 'data.items', 'triggered', 'items']);

    if (triggered.length > 0 && this.wsGateway) {
      for (const alert of triggered) {
        const item = this.normalizeAlertItem(alert);
        this.wsGateway.pushAlert(userId || null, {
          alertId: item.id,
          code: item.code,
          indicator: item.indicator,
          condition: item.condition,
          value: item.value,
          message: `告警触发: ${item.code} ${item.indicator} ${item.condition} ${item.value}`,
          level: 'warn',
        });
      }
    }

    return { triggered: triggered.length, items: triggered.map((x) => this.normalizeAlertItem(x)) };
  }

  async list(status = 'active', userId = 'default'): Promise<AlertsListDto> {
    const normalizedStatus = (status || 'active').trim().toLowerCase();
    const cacheKey = this.listCacheKey(userId, normalizedStatus);
    const ttlSeconds = this.cacheService.resolveTtl('alerts.list', AlertsService.LIST_TTL_SECONDS);
    const cached = await this.cacheService.getWithMeta<AlertsListDto>(cacheKey);
    if (cached.value) {
      return {
        ...cached.value,
        meta: {
          ...cached.value.meta,
          cache: { hit: true, backend: cached.meta.backend, key: cacheKey, ttlSeconds },
        },
      };
    }

    const args = {
      action: 'list',
      params: { status: normalizedStatus, user_id: userId },
    };

    const payload = await this.callTool('alerts_manager', args);
    const result: AlertsListDto = {
      status: normalizedStatus,
      items: this.pickArray(payload, ['data.items', 'data.alerts', 'data', 'items', 'alerts']).map((x) => this.normalizeAlertItem(x)),
      sourceTool: 'alerts_manager',
      argsMatched: args,
      meta: {
        fetchedAt: new Date().toISOString(),
        cache: { hit: false, backend: 'none', key: cacheKey, ttlSeconds },
      },
    };

    await this.cacheService.set(cacheKey, result, ttlSeconds);
    return result;
  }

  async remove(alertId: string, userId = 'default') {
    const normalized = alertId.trim();
    const args = {
      action: 'delete',
      params: { alert_id: normalized, user_id: userId },
    };

    const payload = await this.callTool('alerts_manager', args);
    await this.clearUserListCache(userId);

    return {
      alertId: normalized,
      sourceTool: 'alerts_manager' as const,
      argsMatched: args,
      result: payload,
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      const result = await this.mcpGatewayService.callTool(name, args);
      if (typeof result === 'string' && /error executing tool|validation error/i.test(result)) {
        throw new Error(result);
      }
      return result;
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private normalizeAlertItem(raw: unknown): NormalizedAlertItem {
    const record = this.asRecord(raw);
    return {
      id: String(record.alertId ?? record.alert_id ?? record.id ?? ''),
      code: String(record.code ?? record.stock_code ?? ''),
      indicator: String(record.indicator ?? ''),
      condition: String(record.condition ?? ''),
      value: this.toNum(record.value ?? record.threshold),
    };
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private pickArray(payload: unknown, paths: string[]): unknown[] {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (Array.isArray(v)) return v;
    }
    return [];
  }

  private pickString(payload: unknown, paths: string[]): string | null {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (typeof v === 'string' && v.trim()) return v.trim();
    }
    return null;
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  }

  private readPath(obj: unknown, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, key) => {
      if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
        return undefined;
      }
      return (acc as Record<string, unknown>)[key];
    }, obj);
  }

  private listCacheKey(userId: string, status: string) {
    return `alerts:list:${userId}:${status}`;
  }

  private async clearUserListCache(userId: string) {
    await Promise.all([
      this.cacheService.del(this.listCacheKey(userId, 'active')),
      this.cacheService.del(this.listCacheKey(userId, 'inactive')),
      this.cacheService.del(this.listCacheKey(userId, 'all')),
    ]);
  }
}
