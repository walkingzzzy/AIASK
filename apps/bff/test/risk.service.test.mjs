import test from 'node:test';
import assert from 'node:assert/strict';

const { RiskService } = await import('../dist/risk/risk.service.js');

function createCacheStub() {
  return {
    resolveTtl: () => 60,
    getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
    set: async () => {
      throw new Error('cache.set should not be called when summary is degraded');
    },
  };
}

test('RiskService.getSummary returns a degraded summary when any required module fails', async () => {
  const calls = [];
  const service = new RiskService(
    {
      callTool: async (tool, args) => {
        calls.push({ tool, args });
        if (tool === 'portfolio_manager' && args.action === 'list') {
          return { data: { portfolios: [{ id: 19, name: 'Alpha' }] } };
        }
        if (tool === 'risk_manager') {
          return { success: true, data: { ok: true } };
        }
        throw new Error(`unexpected tool call: ${tool}.${args.action}`);
      },
    },
    createCacheStub(),
  );

  const response = await service.getSummary({ userId: 'u_demo', injectFail: 'stress' });

  assert.equal(response.degraded, true);
  assert.equal(response.stressResult, null);
  assert.equal(response.varResult != null, true);
  assert.equal(response.exposureResult != null, true);
  assert.equal(response.moduleStatus.stress.ok, false);
  assert.match(String(response.moduleStatus.stress.reason ?? ''), /injected failure/);
  assert.equal(response.degradeReasons.length, 1);

  assert.equal(calls.filter(({ tool }) => tool === 'risk_manager').length, 2);
});
