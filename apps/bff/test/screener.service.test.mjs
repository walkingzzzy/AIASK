import test from 'node:test';
import assert from 'node:assert/strict';

const { ScreenerService } = await import('../dist/screener/screener.service.js');

const cacheStub = {
  getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
  resolveTtl: () => 60,
  set: async () => {},
};

test('ScreenerService.semanticSearch emits result_contract for result workbench rendering', async () => {
  const service = new ScreenerService(
    {
      callTool: async (tool) => {
        assert.equal(tool, 'semantic_stock_search');
        return {
          meta: { fetchedAt: '2026-04-21T10:00:00.000Z' },
          data: {
            items: [
              { code: '600519', name: '贵州茅台', industry: '白酒' },
            ],
          },
        };
      },
    },
    cacheStub,
  );

  const response = await service.semanticSearch('高端白酒龙头', 20);
  assert.equal(response.result_contract?.platformMeta?.sourceTool, 'semantic_stock_search');
  assert.equal(response.result_contract?.workbenchTask?.kind, 'screener-result');
  assert.equal(response.result_contract?.recommendedActions?.[0]?.actionId, 'screener.open-copilot-followup');
  assert.match(
    response.result_contract?.recommendedLinks?.map((item) => item.label).join(' / ') ?? '',
    /去工厂运行态/,
  );
  assert.match(response.result_contract?.summary ?? '', /筛到 1 只股票/);
});
