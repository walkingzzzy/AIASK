import test from 'node:test';
import assert from 'node:assert/strict';

const { PerformanceService } = await import('../dist/performance/performance.service.js');

test('PerformanceService.attribution requires a real portfolio context', async () => {
  const calls = [];
  const service = new PerformanceService({
    callTool: async (tool, args) => {
      calls.push({ tool, args });
      if (tool === 'portfolio_manager' && args.action === 'list') {
        return { data: { portfolios: [] } };
      }
      throw new Error(`unexpected tool call: ${tool}.${args.action}`);
    },
  });

  await assert.rejects(
    () => service.attribution('u_demo'),
    (error) => {
      const response = error.getResponse?.();
      assert.equal(response?.acceptanceStatus, 'prerequisite_missing');
      assert.equal(response?.code, 'PREREQUISITE_MISSING');
      assert.match(String(response?.message ?? ''), /暂无组合/);
      return true;
    },
  );

  assert.deepEqual(
    calls.map(({ tool, args }) => `${tool}.${args.action}`),
    ['portfolio_manager.list'],
  );
});

test('PerformanceService.benchmarkComparison requires a real portfolio context', async () => {
  const service = new PerformanceService({
    callTool: async (tool, args) => {
      if (tool === 'portfolio_manager' && args.action === 'list') {
        return { data: { portfolios: [] } };
      }
      throw new Error(`unexpected tool call: ${tool}.${args.action}`);
    },
  });

  await assert.rejects(
    () => service.benchmarkComparison('u_demo'),
    (error) => {
      const response = error.getResponse?.();
      assert.equal(response?.acceptanceStatus, 'prerequisite_missing');
      assert.equal(response?.code, 'PREREQUISITE_MISSING');
      assert.match(String(response?.message ?? ''), /暂无组合/);
      return true;
    },
  );
});
