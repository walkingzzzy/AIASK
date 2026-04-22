import test from 'node:test';
import assert from 'node:assert/strict';

const { RiskService } = await import('../dist/risk/risk.service.js');

function createCacheStub() {
  return {
    resolveTtl: () => 60,
    getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
    set: async () => {
      throw new Error('cache.set should not be called when summary generation fails');
    },
  };
}

test('RiskService.getSummary fails hard when any required module fails', async () => {
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

  await assert.rejects(
    () => service.getSummary({ userId: 'u_demo', injectFail: 'stress' }),
    (error) => {
      const response = error.getResponse?.();
      assert.equal(response?.code, 'RISK_SUMMARY_UNAVAILABLE');
      assert.equal(response?.message, '风险汇总暂不可用');
      assert.equal(response?.detail?.moduleStatus?.stress?.ok, false);
      assert.match(String(response?.detail?.moduleStatus?.stress?.reason ?? ''), /injected failure/);
      return true;
    },
  );

  assert.equal(calls.filter(({ tool }) => tool === 'risk_manager').length, 2);
});
