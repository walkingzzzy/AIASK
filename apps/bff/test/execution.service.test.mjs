import test from 'node:test';
import assert from 'node:assert/strict';

const { ExecutionService } = await import('../dist/execution/execution.service.js');

test('ExecutionService.liveGatewayStatus returns a degraded envelope when live gateway is unavailable', async () => {
  const service = new ExecutionService(
    {},
    {
      callTool: async (tool, args) => {
        assert.equal(tool, 'live_trading_manager');
        assert.equal(args.action, 'gateway_status');
        throw new Error('live gateway unreachable');
      },
    },
  );

  const response = await service.liveGatewayStatus();

  assert.equal(response.configured, false);
  assert.equal(response.connected, false);
  assert.equal(response.status, 'degraded');
  assert.equal(response.read_only, true);
  assert.equal(response.allow_write, false);
  assert.match(String(response.error), /live gateway unreachable/);
  assert.equal(response.raw.degraded, true);
});
