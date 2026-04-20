import { Injectable, OnModuleInit } from '@nestjs/common';
import { AuditStore } from '../audit/audit.store';
import { CommonCacheService } from '../common/cache.service';
import { DbService } from '../db/db.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { NotificationService } from '../notification/notification.service';

type HealthStatus = 'ok' | 'degraded' | 'unavailable';

@Injectable()
export class HealthService implements OnModuleInit {
  private startedAt = new Date().toISOString();
  private startupCompleted = false;

  constructor(
    private readonly db: DbService,
    private readonly cache: CommonCacheService,
    private readonly auditStore: AuditStore,
    private readonly mcpGatewayService: McpGatewayService,
    private readonly notificationService: NotificationService,
  ) {}

  onModuleInit(): void {
    this.startupCompleted = true;
  }

  async getHealth() {
    const cache = this.cache.getStats();
    const mcp = await this.mcpGatewayService.checkAvailableTools();
    const audit = this.auditStore.getStatus();
    const notifications = this.notificationService.getDeliveryStatus();
    const degradedReasons: string[] = [];

    if (this.db.enabled && !this.db.healthy) {
      degradedReasons.push('db_unhealthy');
    }
    if (!cache.redisReady) {
      degradedReasons.push('cache_memory_fallback');
    }
    if (audit.degraded) {
      degradedReasons.push(audit.degradedReason ?? 'audit_degraded');
    }
    if (!mcp.reachable) {
      degradedReasons.push('mcp_unreachable');
    } else if (mcp.degraded) {
      degradedReasons.push(mcp.fallbackReason ?? 'mcp_fallback_active');
    }
    if (notifications.configured && notifications.failed > 0 && notifications.delivered <= 0) {
      degradedReasons.push('notification_external_delivery_failed');
    }

    const status: HealthStatus = !mcp.reachable
      ? 'unavailable'
      : degradedReasons.length > 0
        ? 'degraded'
        : 'ok';

    return {
      success: status !== 'unavailable',
      service: 'aiask-bff',
      status,
      startedAt: this.startedAt,
      probes: {
        liveness: 'ok',
        startup: this.startupCompleted ? 'complete' : 'starting',
        readiness: status === 'unavailable' ? 'blocked' : degradedReasons.length > 0 ? 'degraded' : 'ready',
      },
      db: {
        enabled: this.db.enabled,
        healthy: this.db.healthy,
        mode: this.db.enabled ? 'postgres' : 'memory',
      },
      cache: {
        redisReady: cache.redisReady,
        activeBackend: cache.redisReady ? 'redis' : 'memory',
        hitRate: cache.hitRate,
        errors: cache.errors,
      },
      audit,
      notifications,
      mcp,
      degradedReasons,
      timestamp: new Date().toISOString(),
    };
  }

  async getDbHealth() {
    const base = {
      enabled: this.db.enabled,
      healthy: this.db.healthy,
    };

    if (!this.db.enabled) {
      return { success: true, data: { ...base, mode: 'memory' } };
    }

    let reachable = false;
    let latencyMs = -1;
    try {
      const start = Date.now();
      await this.db.query('SELECT 1');
      latencyMs = Date.now() - start;
      reachable = true;
    } catch {
      reachable = false;
    }

    return {
      success: reachable,
      data: {
        ...base,
        reachable,
        latencyMs,
        mode: 'postgres',
      },
    };
  }
}
