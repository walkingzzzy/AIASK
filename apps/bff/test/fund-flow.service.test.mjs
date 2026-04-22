import test from 'node:test';
import assert from 'node:assert/strict';

const { FundFlowService } = await import('../dist/fund-flow/fund-flow.service.js');

test('FundFlowService.getSectorFundFlow degrades to an empty payload when MCP sector flow is unavailable', async () => {
  let cacheSetCalls = 0;
  const service = new FundFlowService(
    {
      callTool: async () => {
        throw new Error('sector flow upstream unavailable');
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
    {
      resolveTtl: (_scope, fallbackSeconds) => fallbackSeconds,
      getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
      set: async () => {
        cacheSetCalls += 1;
      },
    },
  );

  const response = await service.getSectorFundFlow();

  assert.equal(response.degraded, true);
  assert.equal(response.message, '板块资金流暂时不可用，已降级为空结果');
  assert.deepEqual(response.data?.flows, []);
  assert.deepEqual(response.fallback_reason, [
    'sector_fund_flow_unavailable',
    'streamable_http_connect_failed',
  ]);
  assert.equal(response.detail.acceptance_status, 'degraded');
  assert.equal(response.detail.path, '/fund-flow/sector');
  assert.equal(response.detail.transport.active_transport, 'stdio');
  assert.match(String(response.detail.upstream?.message ?? ''), /sector flow upstream unavailable/);
  assert.equal(cacheSetCalls, 0);
});
