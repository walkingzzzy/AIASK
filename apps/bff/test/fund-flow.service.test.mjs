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

test('FundFlowService.getSectorFundFlow keeps price change separate from fund-flow amounts', async () => {
  const service = new FundFlowService(
    {
      callTool: async () => ({
        success: true,
        data: [
          { name: '银行', change_percent: 1.23, net_inflow: 350000000, main_net_inflow: 120000000 },
          { name: '煤炭', changePercent: -0.4, value: 2.6 },
        ],
      }),
      getTransportSnapshot: () => ({}),
    },
    {
      resolveTtl: (_scope, fallbackSeconds) => fallbackSeconds,
      getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
      set: async () => {},
    },
  );

  const response = await service.getSectorFundFlow();
  const flows = response.data.flows;

  assert.equal(flows[0].changePercent, 1.23);
  assert.equal(flows[0].netInflow, 350000000);
  assert.equal(flows[0].mainInflow, 120000000);
  assert.equal(flows[1].changePercent, -0.4);
  assert.equal(flows[1].netInflow, null);
  assert.equal(flows[1].mainInflow, null);
});
