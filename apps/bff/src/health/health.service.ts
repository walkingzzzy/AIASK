import { Injectable, OnModuleInit } from '@nestjs/common';
import { AuditStore } from '../audit/audit.store';
import { CommonCacheService } from '../common/cache.service';
import { DbService } from '../db/db.service';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { NotificationService } from '../notification/notification.service';
import { ObservabilityService } from '../observability/observability.service';

type HealthStatus = 'normal' | 'degraded' | 'untrusted';
type HealthSignal = 'operational' | 'boolean';
type ComponentSnapshot = Record<string, unknown> & {
  status: HealthStatus;
  signal: HealthSignal;
  reasons: string[];
};
type HealthSnapshot = {
  success: true;
  service: 'aiask-bff';
  status: HealthStatus;
  startedAt: string;
  probes: {
    liveness: 'normal';
    startup: 'complete' | 'starting';
    readiness: 'ready' | 'degraded' | 'blocked';
  };
  db: ComponentSnapshot;
  cache: ComponentSnapshot;
  audit: ComponentSnapshot;
  notifications: ComponentSnapshot;
  mcp: ComponentSnapshot;
  vector: ComponentSnapshot;
  reasons: string[];
  degradedReasons: string[];
  timestamp: string;
};
type HealthCacheEntry = {
  value: HealthSnapshot;
  expiresAt: number;
};
type ComponentCacheEntry = {
  value: ComponentSnapshot;
  expiresAt: number;
  staleUntil: number;
};

@Injectable()
export class HealthService implements OnModuleInit {
  private static readonly HEALTH_CACHE_TTL_MS = 10_000;
  private static readonly VECTOR_HEALTH_CACHE_TTL_MS = 60_000;
  private static readonly VECTOR_HEALTH_STALE_IF_ERROR_MS = 5 * 60_000;
  private startedAt = new Date().toISOString();
  private startupCompleted = false;
  private healthCache: HealthCacheEntry | null = null;
  private healthInFlight: Promise<HealthSnapshot> | null = null;
  private vectorHealthCache: ComponentCacheEntry | null = null;
  private vectorHealthInFlight: Promise<ComponentSnapshot> | null = null;

  constructor(
    private readonly db: DbService,
    private readonly cache: CommonCacheService,
    private readonly auditStore: AuditStore,
    private readonly mcpGatewayService: McpGatewayService,
    private readonly notificationService: NotificationService,
    private readonly observability: ObservabilityService,
  ) {}

  onModuleInit(): void {
    this.startupCompleted = true;
  }

  async getHealth(): Promise<HealthSnapshot> {
    const cached = this.getCachedHealth();
    if (cached) {
      return cached;
    }

    if (this.healthInFlight) {
      return this.healthInFlight;
    }

    this.healthInFlight = this.buildHealth().finally(() => {
      this.healthInFlight = null;
    });
    return this.healthInFlight;
  }

  private async buildHealth(): Promise<HealthSnapshot> {
    const cache = this.cache.getStats();
    const mcp = await this.mcpGatewayService.checkAvailableTools();
    const audit = this.auditStore.getStatus();
    const notifications = this.notificationService.getDeliveryStatus();
    const db = this.buildDbSnapshot();
    const cacheSnapshot = this.buildCacheSnapshot(cache);
    const mcpSnapshot = this.buildMcpSnapshot(mcp);
    const vector = await this.buildVectorSnapshot(mcpSnapshot);
    const auditSnapshot = this.buildAuditSnapshot(audit);
    const notificationSnapshot = this.buildNotificationSnapshot(notifications);

    const reasons = this.uniqueReasons(
      db.reasons,
      cacheSnapshot.reasons,
      auditSnapshot.reasons,
      mcpSnapshot.reasons,
      vector.reasons,
      notificationSnapshot.reasons,
    );

    const status: HealthStatus =
      db.status === 'untrusted' || mcpSnapshot.status === 'untrusted'
        ? 'untrusted'
        : reasons.length > 0
          ? 'degraded'
          : 'normal';

    this.observability.setDependencyState('vector', vector.status);
    this.observability.setDependencyState('audit', auditSnapshot.status);
    this.observability.setDependencyState('notifications', notificationSnapshot.status);

    return this.cacheHealth({
      success: true,
      service: 'aiask-bff',
      status,
      startedAt: this.startedAt,
      probes: {
        liveness: 'normal',
        startup: this.startupCompleted ? 'complete' : 'starting',
        readiness: status === 'untrusted' ? 'blocked' : reasons.length > 0 ? 'degraded' : 'ready',
      },
      db,
      cache: cacheSnapshot,
      audit: auditSnapshot,
      notifications: notificationSnapshot,
      mcp: mcpSnapshot,
      vector,
      reasons,
      degradedReasons: reasons,
      timestamp: new Date().toISOString(),
    });
  }

  async getDbHealth() {
    if (!this.db.enabled) {
      return {
        ...this.buildDbSnapshot(),
        reachable: false,
        latencyMs: null,
      };
    }

    let reachable = false;
    let latencyMs: number | null = null;
    try {
      const start = Date.now();
      await this.db.query('SELECT 1');
      latencyMs = Date.now() - start;
      reachable = true;
    } catch {
      reachable = false;
    }

    const base = this.buildDbSnapshot();
    return {
      ...base,
      status: reachable ? 'normal' : 'untrusted',
      reasons: reachable ? [] : this.uniqueReasons(base.reasons, ['db_probe_failed']),
      reachable,
      latencyMs,
    };
  }

  private buildDbSnapshot(): ComponentSnapshot {
    const db = typeof (this.db as { getHealthSnapshot?: () => Record<string, unknown> }).getHealthSnapshot === 'function'
      ? this.db.getHealthSnapshot()
      : {
        enabled: this.db.enabled,
        healthy: this.db.healthy,
        lastError: null,
        lastLatencyMs: null,
        lastCheckedAt: null,
        lastFailureStage: null,
      };
    const reasons = !db.enabled
      ? ['database_disabled']
      : !db.healthy
        ? this.uniqueReasons(
          typeof db.lastFailureStage === 'string' ? [db.lastFailureStage] : [],
          ['db_unhealthy'],
        )
        : [];

    return {
      ...db,
      mode: db.enabled ? 'postgres' : 'memory',
      status: !db.enabled ? 'degraded' : db.healthy ? 'normal' : 'untrusted',
      signal: 'operational',
      reasons,
    };
  }

  private buildCacheSnapshot(cache: ReturnType<CommonCacheService['getStats']>): ComponentSnapshot {
    const usingFallback = !cache.configured || !cache.redisReady || cache.fallbackActive === true;
    const reasons: string[] = [];
    if (!cache.configured) {
      reasons.push('redis_not_configured');
    } else if (usingFallback) {
      reasons.push('cache_memory_fallback', 'redis_unavailable');
    }
    if (typeof cache.lastFailureStage === 'string' && cache.lastFailureStage.trim()) {
      reasons.push(cache.lastFailureStage);
    }

    return {
      ...cache,
      activeBackend: usingFallback ? 'memory' : 'redis',
      status: usingFallback ? 'degraded' : 'normal',
      signal: 'operational',
      reasons: this.uniqueReasons(reasons),
    };
  }

  private buildAuditSnapshot(audit: ReturnType<AuditStore['getStatus']>): ComponentSnapshot {
    const reasons = audit.degraded
      ? [audit.degradedReason ?? 'audit_degraded']
      : [];
    return {
      ...audit,
      status: audit.degraded ? 'degraded' : 'normal',
      signal: 'operational',
      reasons,
    };
  }

  private buildNotificationSnapshot(
    notifications: ReturnType<NotificationService['getDeliveryStatus']>,
  ): ComponentSnapshot {
    const degraded =
      notifications.configured
      && notifications.failed > 0
      && notifications.delivered <= 0;
    return {
      ...notifications,
      status: degraded ? 'degraded' : 'normal',
      signal: 'operational',
      reasons: degraded ? ['notification_external_delivery_failed'] : [],
    };
  }

  private buildMcpSnapshot(
    mcp: Awaited<ReturnType<McpGatewayService['checkAvailableTools']>>,
  ): ComponentSnapshot {
    const reasons: string[] = [];
    if (!mcp.reachable) {
      reasons.push('mcp_unreachable');
    }
    if (mcp.fallbackReason) {
      reasons.push(mcp.fallbackReason);
    }
    if (mcp.matched === false) {
      reasons.push('mcp_tool_count_mismatch');
    }

    return {
      ...mcp,
      status: !mcp.reachable ? 'untrusted' : mcp.degraded || mcp.matched === false ? 'degraded' : 'normal',
      signal: 'operational',
      reasons: this.uniqueReasons(reasons),
    };
  }

  private async buildVectorSnapshot(mcp: ComponentSnapshot): Promise<ComponentSnapshot> {
    if (mcp.status === 'untrusted') {
      return {
        status: 'untrusted',
        signal: 'operational',
        reasons: ['mcp_unreachable', 'vector_health_unavailable'],
      };
    }

    const cached = this.getCachedVectorSnapshot();
    if (cached) {
      return cached;
    }

    if (this.vectorHealthInFlight) {
      return this.vectorHealthInFlight;
    }

    this.vectorHealthInFlight = this.probeVectorSnapshot().finally(() => {
      this.vectorHealthInFlight = null;
    });
    return this.vectorHealthInFlight;
  }

  private async probeVectorSnapshot(): Promise<ComponentSnapshot> {
    let payload: Record<string, unknown> | null = null;
    let lastError: string | null = null;

    try {
      const result = await this.mcpGatewayService.callTool(
        'strategy_manager',
        {
          action: 'vector_health',
          params: {
            index_name: 'strategy_behavior',
            limit_versions: 5,
          },
        },
        {
          timeoutMs: 8_000,
        },
      );
      payload = this.unwrapManagerPayload(result);
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }

    if (!payload) {
      const stale = this.getStaleVectorSnapshot(lastError);
      if (stale) {
        return stale;
      }
      return {
        status: 'untrusted',
        signal: 'operational',
        reasons: ['vector_health_probe_failed'],
        lastError,
      };
    }

    const reasons = this.uniqueReasons(
      this.readReasonList(payload.fallback_reason),
      this.readReasonList(payload.quality_flags),
      !payload.active_index ? ['vector_active_index_missing'] : [],
      !payload.latest_snapshot ? ['vector_latest_snapshot_missing'] : [],
      Number(payload.collection_count ?? 0) <= 0 ? ['vector_collection_missing'] : [],
      payload.pgvector_enabled === false ? ['pgvector_disabled'] : [],
      this.hasDegradedVectorStatus(payload) ? ['vector_snapshot_degraded'] : [],
    );

    return this.cacheVectorSnapshot({
      ...payload,
      status: reasons.length > 0 ? 'degraded' : 'normal',
      signal: 'operational',
      reasons,
      lastError,
      stale: false,
      checkedAt: new Date().toISOString(),
    });
  }

  private cacheVectorSnapshot(value: ComponentSnapshot): ComponentSnapshot {
    const now = Date.now();
    this.vectorHealthCache = {
      value,
      expiresAt: now + HealthService.VECTOR_HEALTH_CACHE_TTL_MS,
      staleUntil: now + HealthService.VECTOR_HEALTH_STALE_IF_ERROR_MS,
    };
    return value;
  }

  private getCachedVectorSnapshot(): ComponentSnapshot | null {
    if (!this.vectorHealthCache || Date.now() > this.vectorHealthCache.expiresAt) {
      return null;
    }
    return this.vectorHealthCache.value;
  }

  private getStaleVectorSnapshot(lastError: string | null): ComponentSnapshot | null {
    if (!this.vectorHealthCache || Date.now() > this.vectorHealthCache.staleUntil) {
      return null;
    }
    if (this.vectorHealthCache.value.status === 'untrusted') {
      return null;
    }
    return {
      ...this.vectorHealthCache.value,
      stale: true,
      lastProbeError: lastError,
      staleReason: lastError ? 'vector_health_probe_failed' : 'vector_health_probe_empty',
    };
  }

  private hasDegradedVectorStatus(payload: Record<string, unknown>): boolean {
    const values = [
      (payload.latest_snapshot as Record<string, unknown> | null | undefined)?.status,
      (payload.active_index as Record<string, unknown> | null | undefined)?.status,
    ];
    return values.some((value) => String(value ?? '').trim().toLowerCase() === 'degraded');
  }

  private unwrapManagerPayload(result: unknown): Record<string, unknown> | null {
    if (!result || typeof result !== 'object') {
      return null;
    }
    const node = result as Record<string, unknown>;
    if (node.success === false) {
      return null;
    }
    if (node.data && typeof node.data === 'object' && !Array.isArray(node.data)) {
      return node.data as Record<string, unknown>;
    }
    return node;
  }

  private readReasonList(value: unknown): string[] {
    if (Array.isArray(value)) {
      return value.map((item) => String(item ?? '').trim()).filter(Boolean);
    }
    const normalized = String(value ?? '').trim();
    return normalized ? [normalized] : [];
  }

  private uniqueReasons(...lists: string[][]): string[] {
    return lists
      .flat()
      .map((item) => String(item ?? '').trim())
      .filter((item, index, all) => item.length > 0 && all.indexOf(item) === index);
  }

  private cacheHealth(value: HealthSnapshot): HealthSnapshot {
    this.healthCache = {
      value,
      expiresAt: Date.now() + HealthService.HEALTH_CACHE_TTL_MS,
    };
    return value;
  }

  private getCachedHealth(): HealthSnapshot | null {
    if (!this.healthCache) return null;
    if (Date.now() > this.healthCache.expiresAt) {
      return null;
    }
    return this.healthCache.value;
  }
}
