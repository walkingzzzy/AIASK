'use client';

export type RuntimeHealthStatus = 'normal' | 'degraded' | 'untrusted' | 'unknown';
export type RuntimeHealthSignal = 'operational' | 'boolean';

export type RuntimeHealthComponent = {
  status: RuntimeHealthStatus;
  signal: RuntimeHealthSignal;
  reasons: string[];
  raw: Record<string, unknown>;
};

export type RuntimeHealthSnapshot = {
  service: string;
  status: RuntimeHealthStatus;
  reasons: string[];
  timestamp: string | null;
  readiness: string | null;
  dependencies: {
    mcp: RuntimeHealthComponent;
    db: RuntimeHealthComponent;
    cache: RuntimeHealthComponent;
    vector: RuntimeHealthComponent;
    audit: RuntimeHealthComponent;
    notifications: RuntimeHealthComponent;
  };
  raw: Record<string, unknown>;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? '').trim()).filter(Boolean);
  }
  const normalized = String(value ?? '').trim();
  return normalized ? [normalized] : [];
}

function normalizeSignal(value: unknown, fallback: RuntimeHealthSignal): RuntimeHealthSignal {
  return value === 'boolean' || value === 'operational' ? value : fallback;
}

function normalizeStatus(value: unknown): RuntimeHealthStatus {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (!normalized) return 'unknown';
  if (normalized === 'normal' || normalized === 'ok' || normalized === 'healthy' || normalized === 'ready') {
    return 'normal';
  }
  if (normalized === 'degraded' || normalized === 'warning' || normalized === 'partial') {
    return 'degraded';
  }
  if (
    normalized === 'untrusted'
    || normalized === 'unavailable'
    || normalized === 'blocked'
    || normalized === 'offline'
    || normalized === 'failed'
    || normalized === 'error'
  ) {
    return 'untrusted';
  }
  return 'unknown';
}

function dedupeReasons(...values: unknown[]): string[] {
  return values
    .flatMap((value) => asStringList(value))
    .filter((value, index, list) => list.indexOf(value) === index);
}

function buildComponent(
  value: unknown,
  fallbackStatus: RuntimeHealthStatus,
  fallbackSignal: RuntimeHealthSignal,
  ...reasonSources: unknown[]
): RuntimeHealthComponent {
  const raw = asRecord(value);
  const explicitStatus = normalizeStatus(raw.status);
  return {
    status: explicitStatus === 'unknown' ? fallbackStatus : explicitStatus,
    signal: normalizeSignal(raw.signal, fallbackSignal),
    reasons: dedupeReasons(raw.reasons, raw.degradedReasons, ...reasonSources),
    raw,
  };
}

export function normalizeSystemHealthSnapshot(input: unknown): RuntimeHealthSnapshot {
  const raw = asRecord(input);
  const probes = asRecord(raw.probes);
  const mcpRaw = asRecord(raw.mcp);
  const dbRaw = asRecord(raw.db);
  const cacheRaw = asRecord(raw.cache);
  const vectorRaw = asRecord(raw.vector);
  const auditRaw = asRecord(raw.audit);
  const notificationsRaw = asRecord(raw.notifications);

  const mcp = buildComponent(
    mcpRaw,
    mcpRaw.reachable === false ? 'untrusted' : mcpRaw.degraded === true || mcpRaw.matched === false ? 'degraded' : 'normal',
    'operational',
    mcpRaw.fallbackReason,
    mcpRaw.fallback_reason,
    mcpRaw.reachable === false ? 'mcp_unreachable' : null,
    mcpRaw.matched === false ? 'mcp_tool_count_mismatch' : null,
  );

  const db = buildComponent(
    dbRaw,
    dbRaw.enabled === false ? 'degraded' : dbRaw.healthy === true ? 'normal' : 'untrusted',
    'boolean',
    dbRaw.enabled === false ? 'database_disabled' : null,
    dbRaw.enabled === true && dbRaw.healthy !== true ? 'db_unhealthy' : null,
  );

  const cache = buildComponent(
    cacheRaw,
    cacheRaw.redisReady === true ? 'normal' : 'degraded',
    'boolean',
    cacheRaw.configured === false ? 'redis_not_configured' : null,
    cacheRaw.configured !== false && cacheRaw.redisReady !== true ? 'cache_memory_fallback' : null,
  );

  const vector = buildComponent(
    vectorRaw,
    Object.keys(vectorRaw).length === 0
      ? 'unknown'
      : vectorRaw.lastError || vectorRaw.error
        ? 'untrusted'
        : 'normal',
    'operational',
    vectorRaw.fallbackReason,
    vectorRaw.fallback_reason,
    vectorRaw.quality_flags,
    !vectorRaw.active_index && Object.keys(vectorRaw).length > 0 ? 'vector_active_index_missing' : null,
    !vectorRaw.latest_snapshot && Object.keys(vectorRaw).length > 0 ? 'vector_latest_snapshot_missing' : null,
  );

  const audit = buildComponent(
    auditRaw,
    auditRaw.degraded === true ? 'degraded' : 'normal',
    'operational',
    auditRaw.degradedReason,
  );

  const notifications = buildComponent(
    notificationsRaw,
    notificationsRaw.configured === true && Number(notificationsRaw.failed ?? 0) > 0 && Number(notificationsRaw.delivered ?? 0) <= 0
      ? 'degraded'
      : 'normal',
    'operational',
    notificationsRaw.configured === true && Number(notificationsRaw.failed ?? 0) > 0 && Number(notificationsRaw.delivered ?? 0) <= 0
      ? 'notification_external_delivery_failed'
      : null,
  );

  const explicitStatus = normalizeStatus(raw.status);
  const reasons = dedupeReasons(
    raw.reasons,
    raw.degradedReasons,
    mcp.reasons,
    db.reasons,
    cache.reasons,
    vector.reasons,
    audit.reasons,
    notifications.reasons,
  );

  const derivedStatus =
    explicitStatus !== 'unknown'
      ? explicitStatus
      : mcp.status === 'untrusted' || db.status === 'untrusted'
        ? 'untrusted'
        : reasons.length > 0
          ? 'degraded'
          : 'normal';

  return {
    service: String(raw.service ?? 'aiask-bff'),
    status: derivedStatus,
    reasons,
    timestamp: typeof raw.timestamp === 'string' ? raw.timestamp : null,
    readiness: typeof probes.readiness === 'string' ? probes.readiness : null,
    dependencies: {
      mcp,
      db,
      cache,
      vector,
      audit,
      notifications,
    },
    raw,
  };
}

export function healthStatusVariant(status: RuntimeHealthStatus): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'normal') return 'success';
  if (status === 'degraded') return 'warning';
  if (status === 'untrusted') return 'danger';
  return 'neutral';
}

export function formatHealthStatusLabel(status: RuntimeHealthStatus): string {
  if (status === 'normal') return '正常';
  if (status === 'degraded') return '降级';
  if (status === 'untrusted') return '不可信';
  return '未知';
}

export function formatHealthSignalLabel(signal: RuntimeHealthSignal): string {
  return signal === 'operational' ? '值守级' : '布尔健康';
}
