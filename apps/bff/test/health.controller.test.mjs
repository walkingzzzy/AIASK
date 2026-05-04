import test from 'node:test';
import assert from 'node:assert/strict';

const { HealthController } = await import('../dist/health/health.controller.js');

function createHealthSnapshot(readiness) {
  return {
    success: true,
    service: 'aiask-bff',
    status: readiness === 'blocked' ? 'untrusted' : readiness === 'degraded' ? 'degraded' : 'normal',
    startedAt: '2026-04-28T00:00:00.000Z',
    probes: {
      liveness: 'normal',
      startup: 'complete',
      readiness,
    },
    db: { status: 'normal', signal: 'operational', reasons: [] },
    cache: { status: 'normal', signal: 'operational', reasons: [] },
    audit: { status: 'normal', signal: 'operational', reasons: [] },
    notifications: { status: 'normal', signal: 'operational', reasons: [] },
    mcp: { status: 'normal', signal: 'operational', reasons: [] },
    vector: {
      status: readiness === 'degraded' ? 'degraded' : 'normal',
      signal: 'operational',
      reasons: readiness === 'degraded' ? ['vector_health_probe_failed'] : [],
    },
    reasons: readiness === 'degraded' ? ['vector_health_probe_failed'] : [],
    degradedReasons: readiness === 'degraded' ? ['vector_health_probe_failed'] : [],
    timestamp: '2026-04-28T00:00:01.000Z',
  };
}

test('HealthController.ready returns success for degraded operational readiness', async () => {
  const controller = new HealthController({
    getHealth: async () => createHealthSnapshot('degraded'),
  });

  const response = await controller.getReadyHealth();

  assert.equal(response.success, true);
  assert.equal(response.data.probes.readiness, 'degraded');
  assert.deepEqual(response.data.degradedReasons, ['vector_health_probe_failed']);
});

test('HealthController.ready rejects blocked readiness', async () => {
  const controller = new HealthController({
    getHealth: async () => createHealthSnapshot('blocked'),
  });

  await assert.rejects(() => controller.getReadyHealth(), {
    name: 'ServiceUnavailableException',
  });
});
