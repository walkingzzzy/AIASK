import { BadGatewayException, Injectable } from '@nestjs/common';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { CommonCacheService } from '../common/cache.service';

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
  ) {}

  async create(input: CreateAlertInput) {
    const normalized = {
      code: input.code.trim(),
      indicator: input.indicator.trim(),
      condition: input.condition,
      value: Number(input.value),
    };

    const args = {
      action: 'create',
      kwargs: JSON.stringify(normalized),
    };

    const payload = await this.callTool('alerts_manager', args);
    const alertId =
      this.pickString(payload, ['data.alert_id', 'data.alertId', 'data.id', 'alert_id', 'alertId', 'id']) ||
      `alert_${normalized.code}_${normalized.indicator}_${normalized.condition}`;

    await this.cacheService.del('alerts:list:active');
    await this.cacheService.del('alerts:list:inactive');
    await this.cacheService.del('alerts:list:all');

    return {
      alertId,
      sourceTool: 'alerts_manager' as const,
      argsMatched: args,
      result: payload,
    };
  }

  async list(status = 'active'): Promise<AlertsListDto> {
    const normalizedStatus = (status || 'active').trim().toLowerCase();
    const cacheKey = `alerts:list:${normalizedStatus}`;
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
      kwargs: JSON.stringify({ status: normalizedStatus }),
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

  async remove(alertId: string) {
    const normalized = alertId.trim();
    const args = {
      action: 'delete',
      kwargs: JSON.stringify({ alert_id: normalized }),
    };

    const payload = await this.callTool('alerts_manager', args);
    await this.cacheService.del('alerts:list:active');
    await this.cacheService.del('alerts:list:inactive');
    await this.cacheService.del('alerts:list:all');

    return {
      alertId: normalized,
      sourceTool: 'alerts_manager' as const,
      argsMatched: args,
      result: payload,
    };
  }

  private async callTool(name: string, args: Record<string, unknown>) {
    try {
      return await this.mcpGatewayService.callTool(name, args);
    } catch (error) {
      throw new BadGatewayException({
        success: false,
        message: `调用 MCP ${name} 失败`,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private normalizeAlertItem(raw: any): NormalizedAlertItem {
    return {
      id: String(raw.alertId ?? raw.alert_id ?? raw.id ?? ''),
      code: String(raw.code ?? raw.stock_code ?? ''),
      indicator: String(raw.indicator ?? ''),
      condition: String(raw.condition ?? ''),
      value: this.toNum(raw.value ?? raw.threshold),
    };
  }

  private toNum(v: unknown): number | null {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  private pickArray(payload: any, paths: string[]): unknown[] {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (Array.isArray(v)) return v;
    }
    return [];
  }

  private pickString(payload: any, paths: string[]): string | null {
    for (const p of paths) {
      const v = this.readPath(payload, p);
      if (typeof v === 'string' && v.trim()) return v.trim();
    }
    return null;
  }

  private readPath(obj: any, path: string): unknown {
    return path.split('.').reduce((acc: any, key: string) => (acc == null ? undefined : acc[key]), obj);
  }
}

