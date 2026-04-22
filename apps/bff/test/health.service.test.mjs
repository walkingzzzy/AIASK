import test from 'node:test';
import assert from 'node:assert/strict';

const { HealthService } = await import('../dist/health/health.service.js');

function createDbStub(overrides = {}) {
  return {
    enabled: true,
    healthy: true,
    query: async () => ({ rows: [] }),
    getHealthSnapshot: () => ({
      enabled: true,
      healthy: true,
      ...overrides,
    }),
    ...overrides,
  };
}

function createCacheStub(overrides = {}) {
  return {
    getStats: () => ({
      configured: true,
      redisReady: true,
      hitRate: 1,
      errors: 0,
      ...overrides,
    }),
  };
}

function createMcpGatewayStub({ health, vectorHealth }) {
  return {
    checkAvailableTools: async () => health,
    callTool: async () => vectorHealth ?? {
      success: true,
      data: {
        active_index: { status: 'normal' },
        latest_snapshot: { status: 'normal' },
        collection_count: 1,
        pgvector_enabled: true,
      },
    },
  };
}

function createObservabilityStub() {
  return {
    setDependencyState() {},
  };
}

test('HealthService reports degraded when fallback paths are active', async () => {
  const service = new HealthService(
    createDbStub(),
    createCacheStub({
      configured: true,
      redisReady: false,
      fallbackActive: true,
      hitRate: 0.25,
      errors: 1,
      lastFailureStage: 'redis_connect_failed',
      lastError: 'ECONNREFUSED 127.0.0.1:6379',
    }),
    {
      getStatus: () => ({
        configuredBackend: 'postgres',
        activeBackend: 'memory',
        degraded: true,
        degradedReason: 'audit_db_write_failed',
        lastPersistError: 'db timeout',
        lastReadError: null,
        memoryEntries: 8,
      }),
    },
    createMcpGatewayStub({
      health: {
        reachable: true,
        degraded: true,
        fallbackReason: 'streamable_http_connect_failed',
        transportKind: 'stdio',
        matched: true,
      },
      vectorHealth: {
        success: true,
        data: {
          backend: 'faiss',
          health_mode: 'fallback',
          active_index: { status: 'normal', index_version: 'strategy_behavior@20260421' },
          latest_snapshot: { status: 'degraded', index_version: 'strategy_behavior@20260420' },
          collection_count: 1,
          pgvector_enabled: true,
          quality_flags: ['embedding_provider_fallback_used'],
        },
      },
    }),
    {
      getDeliveryStatus: () => ({
        configured: false,
        source: 'none',
        attempted: 0,
        delivered: 0,
        failed: 0,
        lastError: null,
        lastDeliveredAt: null,
        target: null,
      }),
    },
    createObservabilityStub(),
  );

  service.onModuleInit();
  const health = await service.getHealth();

  assert.equal(health.success, true);
  assert.equal(health.status, 'degraded');
  assert.equal(health.probes.readiness, 'degraded');
  assert.equal(health.cache.status, 'degraded');
  assert.equal(health.cache.signal, 'operational');
  assert.equal(health.mcp.status, 'degraded');
  assert.equal(health.mcp.signal, 'operational');
  assert.equal(health.vector.status, 'degraded');
  assert.equal(health.vector.signal, 'operational');
  assert.equal(health.audit.status, 'degraded');
  assert.ok(health.degradedReasons.includes('cache_memory_fallback'));
  assert.ok(health.degradedReasons.includes('redis_connect_failed'));
  assert.ok(health.degradedReasons.includes('audit_db_write_failed'));
  assert.ok(health.degradedReasons.includes('streamable_http_connect_failed'));
  assert.ok(health.degradedReasons.includes('embedding_provider_fallback_used'));
  assert.ok(health.degradedReasons.includes('vector_snapshot_degraded'));
});

test('HealthService reports untrusted when MCP is unreachable', async () => {
  const service = new HealthService(
    createDbStub({
      enabled: false,
      healthy: false,
    }),
    createCacheStub(),
    {
      getStatus: () => ({
        configuredBackend: 'memory',
        activeBackend: 'memory',
        degraded: true,
        degradedReason: 'database_disabled',
        lastPersistError: null,
        lastReadError: null,
        memoryEntries: 1,
      }),
    },
    createMcpGatewayStub({
      health: {
        reachable: false,
        degraded: true,
        fallbackReason: 'streamable_http_connect_failed',
        transportKind: 'none',
        matched: false,
      },
    }),
    {
      getDeliveryStatus: () => ({
        configured: false,
        source: 'none',
        attempted: 0,
        delivered: 0,
        failed: 0,
        lastError: null,
        lastDeliveredAt: null,
        target: null,
      }),
    },
    createObservabilityStub(),
  );

  service.onModuleInit();
  const health = await service.getHealth();

  assert.equal(health.success, true);
  assert.equal(health.status, 'untrusted');
  assert.equal(health.probes.readiness, 'blocked');
  assert.equal(health.mcp.status, 'untrusted');
  assert.equal(health.vector.status, 'untrusted');
  assert.equal(health.vector.signal, 'operational');
  assert.ok(health.degradedReasons.includes('mcp_unreachable'));
  assert.ok(health.degradedReasons.includes('vector_health_unavailable'));
});

test('HealthService surfaces db and cache failure stages for on-call debugging', async () => {
  const service = new HealthService(
    createDbStub({
      enabled: true,
      healthy: false,
      lastFailureStage: 'db_query_failed',
      lastError: 'Connection terminated due to connection timeout',
      lastLatencyMs: 8123,
      lastCheckedAt: '2026-04-21T01:23:45.000Z',
    }),
    createCacheStub({
      configured: true,
      redisReady: true,
      fallbackActive: true,
      hitRate: 0.11,
      errors: 3,
      lastFailureStage: 'redis_write_failed',
      lastError: 'WRONGTYPE Operation against a key holding the wrong kind of value',
      lastErrorAt: '2026-04-21T01:23:48.000Z',
    }),
    {
      getStatus: () => ({
        configuredBackend: 'postgres',
        activeBackend: 'postgres',
        degraded: false,
        degradedReason: null,
        lastPersistError: null,
        lastReadError: null,
        memoryEntries: 0,
      }),
    },
    createMcpGatewayStub({
      health: {
        reachable: true,
        degraded: false,
        fallbackReason: null,
        transportKind: 'stdio',
        matched: true,
      },
    }),
    {
      getDeliveryStatus: () => ({
        configured: false,
        source: 'none',
        attempted: 0,
        delivered: 0,
        failed: 0,
        lastError: null,
        lastDeliveredAt: null,
        target: null,
      }),
    },
    createObservabilityStub(),
  );

  service.onModuleInit();
  const health = await service.getHealth();

  assert.equal(health.status, 'untrusted');
  assert.equal(health.db.status, 'untrusted');
  assert.equal(health.db.signal, 'operational');
  assert.ok(health.db.reasons.includes('db_query_failed'));
  assert.equal(health.cache.status, 'degraded');
  assert.equal(health.cache.signal, 'operational');
  assert.ok(health.cache.reasons.includes('redis_write_failed'));
});
