import test from 'node:test';
import assert from 'node:assert/strict';

const {
  buildMcpTransportFailureDetail,
  toMcpTransportSnapshot,
  withToolTransportMeta,
} = await import('../dist/mcp-gateway/mcp-transport.contract.js');

const gatewaySnapshot = {
  requestedTransport: 'streamable-http',
  transportKind: 'stdio',
  degraded: true,
  fallbackReason: 'streamable_http_connect_failed',
  sourceChain: ['streamable-http', 'stdio'],
  endpoint: '/tmp/akshare-mcp',
  lastError: 'connect ECONNREFUSED',
};

test('toMcpTransportSnapshot normalizes gateway transport into shared contract shape', () => {
  assert.deepEqual(
    toMcpTransportSnapshot(gatewaySnapshot),
    {
      requested_transport: 'streamable-http',
      active_transport: 'stdio',
      degraded: true,
      fallback_reason: 'streamable_http_connect_failed',
      source_chain: ['streamable-http', 'stdio'],
      endpoint: '/tmp/akshare-mcp',
      last_error: 'connect ECONNREFUSED',
    },
  );
});

test('tool meta and degraded responses share the same transport contract', () => {
  const transport = toMcpTransportSnapshot(gatewaySnapshot);
  const meta = withToolTransportMeta(
    {
      backend_requested: 'streamable-http',
      backend_used: 'stdio',
      fallback_used: true,
      fallback_reason: 'streamable_http_connect_failed',
      latency_ms: 12,
    },
    gatewaySnapshot,
  );
  const detail = buildMcpTransportFailureDetail(gatewaySnapshot, {
    acceptanceStatus: 'degraded',
    path: '/health',
    upstream: { message: 'boom' },
  });

  assert.deepEqual(meta.transport, transport);
  assert.equal(detail.acceptance_status, 'degraded');
  assert.equal(detail.path, '/health');
  assert.deepEqual(detail.upstream, { message: 'boom' });
  assert.deepEqual(detail.transport, transport);
});
