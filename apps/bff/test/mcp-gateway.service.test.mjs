import test from 'node:test';
import assert from 'node:assert/strict';
import { delimiter, resolve } from 'node:path';

const { McpGatewayService, buildIsolatedPythonPath } = await import('../dist/mcp-gateway/mcp-gateway.service.js');

test('buildIsolatedPythonPath ignores ambient PYTHONPATH and keeps only configured plus repo roots', () => {
  const cwd = '/repo/packages/akshare-mcp';
  const configured = ['relative-extra', '/repo/packages/akshare-mcp/src'].join(delimiter);
  const ambient = [
    '/repo/.claude/worktrees/agent-aec932a8/packages/akshare-mcp/src',
    '/tmp/foreign-pythonpath',
  ].join(delimiter);
  const value = buildIsolatedPythonPath({
    cwd,
    configured,
    ambient,
    exists: () => true,
  });

  assert.deepEqual(value.split(delimiter), [
    resolve(cwd, 'relative-extra'),
    resolve(cwd, 'src'),
    resolve(cwd, '..', 'strategy-factory', 'src'),
  ]);
});

function createGatewayForMetrics() {
  return new McpGatewayService(
    {
      get: (key, fallback) => {
        if (key === 'MCP_METRICS_WINDOW_SIZE') return '20';
        return fallback;
      },
    },
    {
      recordMcpCall: () => {},
    },
  );
}

test('McpGatewayService reports current-window health separately from cumulative history', () => {
  const gateway = createGatewayForMetrics();

  gateway.recordToolMetric('get_kline', 30000, true, null, new Error('timed out'));
  for (let index = 0; index < 20; index += 1) {
    gateway.recordToolMetric('get_kline', 25, false, null);
  }

  const snapshot = gateway.getMetricsSnapshot();
  const kline = snapshot.tools.find((tool) => tool.name === 'get_kline');

  assert.equal(snapshot.totalCalls, 20);
  assert.equal(snapshot.errorRate, 0);
  assert.equal(snapshot.current.totalErrors, 0);
  assert.equal(snapshot.cumulative.totalCalls, 21);
  assert.equal(snapshot.cumulative.totalErrors, 1);
  assert.equal(kline?.status, 'healthy');
  assert.equal(kline?.errors, 0);
  assert.equal(kline?.cumulativeErrors, 1);
});

test('McpGatewayService applies default dedicated timeout overrides for high-latency tools', () => {
  const gateway = createGatewayForMetrics();

  assert.equal(gateway.resolveToolTimeoutMs(null, 'get_kline'), 60000);
  assert.equal(gateway.resolveToolTimeoutMs(null, 'strategy_manager'), 120000);
  assert.equal(gateway.resolveToolTimeoutMs(1500, 'get_kline'), 1500);
});
