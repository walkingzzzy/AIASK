import test from 'node:test';
import assert from 'node:assert/strict';

const { SearchService } = await import('../dist/search/search.service.js');

test('SearchService.semanticSearch no longer falls back to search_stocks', async () => {
  const calls = [];
  const service = new SearchService({
    callTool: async (name) => {
      calls.push(name);
      if (name === 'semantic_stock_search') {
        throw new Error('semantic search unavailable');
      }
      if (name === 'search_stocks') {
        return { data: { results: [{ code: '600519' }] } };
      }
      throw new Error(`unexpected tool: ${name}`);
    },
  });

  await assert.rejects(() => service.semanticSearch({ query: '新能源龙头', limit: 10 }));
  assert.deepEqual(calls, ['semantic_stock_search']);
});

test('SearchService.semanticSearch returns result_contract metadata for the web result workbench', async () => {
  const service = new SearchService({
    callTool: async (name) => {
      assert.equal(name, 'semantic_stock_search');
      return {
        meta: { fetchedAt: '2026-04-21T09:00:00.000Z' },
        data: {
          results: [
            { code: '600519', name: '贵州茅台', industry: '白酒' },
          ],
        },
      };
    },
  });

  const response = await service.semanticSearch({ query: '白酒龙头', limit: 10 });
  assert.equal(response.result_contract?.platformMeta?.sourceTool, 'semantic_stock_search');
  assert.equal(response.result_contract?.workbenchTask?.kind, 'search-result');
  assert.equal(response.result_contract?.recommendedActions?.[0]?.actionId, 'search.open-copilot-followup');
  assert.match(response.result_contract?.recommendedLinks?.[0]?.href ?? '', /\/stock\?code=600519/);
  assert.match(
    response.result_contract?.recommendedLinks?.map((item) => item.label).join(' / ') ?? '',
    /去工厂运行态/,
  );
  assert.match(response.result_contract?.summary ?? '', /返回 1 条结果/);
});
