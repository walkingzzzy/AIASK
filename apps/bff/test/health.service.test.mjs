import test from 'node:test';
import assert from 'node:assert/strict';

const { HealthService } = await import('../dist/health/health.service.js');

test('HealthService reports degraded when fallback paths are active', async () => {
  const service = new HealthService(
    {
      enabled: true,
      healthy: true,
      query: async () => ({ rows: [] }),
    },
    {
      getStats: () => ({
        redisReady: false,
        hitRate: 0.25,
        errors: 1,
      }),
    },
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
    {
      checkAvailableTools: async () => ({
        reachable: true,
        degraded: true,
        fallbackReason: 'streamable_http_connect_failed',
        transportKind: 'stdio',
      }),
    },
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
  );

  service.onModuleInit();
  const health = await service.getHealth();

  assert.equal(health.status, 'degraded');
  assert.equal(health.probes.readiness, 'degraded');
  assert.ok(health.degradedReasons.includes('cache_memory_fallback'));
  assert.ok(health.degradedReasons.includes('audit_db_write_failed'));
  assert.ok(health.degradedReasons.includes('streamable_http_connect_failed'));
});

test('HealthService reports unavailable when MCP is unreachable', async () => {
  const service = new HealthService(
    {
      enabled: false,
      healthy: false,
      query: async () => ({ rows: [] }),
    },
    {
      getStats: () => ({
        redisReady: true,
        hitRate: 1,
        errors: 0,
      }),
    },
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
    {
      checkAvailableTools: async () => ({
        reachable: false,
        degraded: true,
        fallbackReason: 'streamable_http_connect_failed',
        transportKind: 'none',
      }),
    },
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
  );

  service.onModuleInit();
  const health = await service.getHealth();

  assert.equal(health.status, 'unavailable');
  assert.equal(health.probes.readiness, 'blocked');
  assert.ok(health.degradedReasons.includes('mcp_unreachable'));
});
