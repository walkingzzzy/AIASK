import test from 'node:test';
import assert from 'node:assert/strict';

const { AlertsService } = await import('../dist/alerts/alerts.service.js');

test('AlertsService.list returns explicit degraded payload instead of throwing when MCP list is unavailable', async () => {
  const fakeMcp = {
    async callTool() {
      throw new Error('alerts manager timeout');
    },
  };
  const fakeCache = {
    resolveTtl() {
      return 30;
    },
    async getWithMeta() {
      return { value: null, meta: { backend: 'none' } };
    },
    async set() {
      throw new Error('degraded alert list must not be cached');
    },
  };
  const service = new AlertsService(fakeMcp, fakeCache);

  const result = await service.list('active', 'u_admin');

  assert.equal(result.status, 'active');
  assert.deepEqual(result.items, []);
  assert.equal(result.degraded, true);
  assert.equal(result.fallback_used, true);
  assert.match(result.fallback_reason, /alerts manager timeout/);
  assert.equal(result.meta.cache.hit, false);
});
