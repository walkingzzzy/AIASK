import test from 'node:test';
import assert from 'node:assert/strict';

const { ResearchService } = await import('../dist/research/research.service.js');

test('ResearchService.getMarketNews degrades to an empty payload when MCP market news is unavailable', async () => {
  const service = new ResearchService(
    {
      callTool: async () => {
        throw new Error('market news upstream unavailable');
      },
      getTransportSnapshot: () => ({
        requestedTransport: 'auto',
        transportKind: 'stdio',
        degraded: true,
        fallbackReason: 'streamable_http_connect_failed',
        sourceChain: ['streamable-http', 'stdio'],
        endpoint: null,
        lastError: 'connect ECONNREFUSED 127.0.0.1:8000',
        healthyConnections: 1,
        dedicatedConnections: 0,
      }),
    },
    {},
  );

  const response = await service.getMarketNews(5);

  assert.equal(response.degraded, true);
  assert.equal(response.message, '市场新闻暂时不可用，已降级为空结果');
  assert.deepEqual(response.items, []);
  assert.equal(response.count, 0);
  assert.deepEqual(response.fallback_reason, [
    'market_news_unavailable',
    'streamable_http_connect_failed',
  ]);
  assert.equal(response.detail.acceptance_status, 'degraded');
  assert.equal(response.detail.path, '/research/market-news');
  assert.equal(response.detail.transport.active_transport, 'stdio');
  assert.match(String(response.detail.upstream?.detail ?? ''), /market news upstream unavailable/);
});
