import test from 'node:test';
import assert from 'node:assert/strict';

const { PaperTradingService } = await import('../dist/paper-trading/paper-trading.service.js');

function createCacheStub() {
  return {
    resolveTtl: () => 30,
    getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
    set: async () => {
      throw new Error('cache.set should not be called on failed summary');
    },
  };
}

test('PaperTradingService.summary propagates upstream failure instead of returning an empty snapshot', async () => {
  const calls = [];
  const service = new PaperTradingService(
    {
      callTool: async (tool, args) => {
        calls.push({ tool, args });
        throw new Error('summary unavailable');
      },
    },
    {
      execute: async () => {
        throw new Error('idempotency.execute should not be called in summary');
      },
    },
    createCacheStub(),
  );

  await assert.rejects(
    () => service.summary('u_demo', 'acct-1'),
    (error) => {
      assert.equal(typeof error?.getResponse, 'function');
      const response = error.getResponse();
      assert.equal(response.success, false);
      assert.equal(response.message, '调用 paper_trading_manager.summary 失败');
      assert.match(String(response.detail ?? ''), /summary unavailable/);
      return true;
    },
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].tool, 'paper_trading_manager');
  assert.equal(calls[0].args.action, 'summary');
});
