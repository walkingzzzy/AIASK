import test from 'node:test';
import assert from 'node:assert/strict';

const {
  resolveMarketSchedulerEnabled,
  resolveMarketSchedulerDisabledReason,
} = await import('../dist/market/market.scheduler.js');

test('MarketScheduler enables itself when no MCP pool narrowing env is set', () => {
  const env = {
    NODE_ENV: 'development',
    MCP_POOL_SIZE: '8',
  };

  assert.equal(resolveMarketSchedulerEnabled(env), true);
  assert.equal(resolveMarketSchedulerDisabledReason(env), null);
});

test('MarketScheduler disables itself for tool-only MCP startup profile by default', () => {
  const env = {
    NODE_ENV: 'development',
    MCP_STDIO_STARTUP_PROFILE: 'tool-only',
    MCP_POOL_SIZE: '8',
  };

  assert.equal(resolveMarketSchedulerEnabled(env), false);
  assert.equal(resolveMarketSchedulerDisabledReason(env), 'MCP_STDIO_STARTUP_PROFILE=tool-only');
});

test('MarketScheduler disables itself when all MCP pool slots are tool-only', () => {
  const env = {
    NODE_ENV: 'development',
    MCP_STDIO_STARTUP_PROFILE: 'balanced',
    MCP_FULL_PROFILE_POOL_SLOTS: '0',
    MCP_POOL_SIZE: '8',
  };

  assert.equal(resolveMarketSchedulerEnabled(env), false);
  assert.equal(resolveMarketSchedulerDisabledReason(env), 'MCP_FULL_PROFILE_POOL_SLOTS=0');
});

test('MarketScheduler explicit enable overrides tool-only defaults', () => {
  const env = {
    NODE_ENV: 'development',
    MARKET_SCHEDULER_ENABLED: 'true',
    MCP_STDIO_STARTUP_PROFILE: 'tool-only',
    MCP_FULL_PROFILE_POOL_SLOTS: '0',
  };

  assert.equal(resolveMarketSchedulerEnabled(env), true);
  assert.equal(resolveMarketSchedulerDisabledReason(env), null);
});

test('MarketScheduler enables by default for streamable-http MCP transport', () => {
  const env = {
    NODE_ENV: 'development',
    MCP_TRANSPORT: 'streamable-http',
    MCP_STDIO_STARTUP_PROFILE: 'tool-only',
    MCP_FULL_PROFILE_POOL_SLOTS: '0',
    MCP_POOL_SIZE: '1',
  };

  assert.equal(resolveMarketSchedulerEnabled(env), true);
  assert.equal(resolveMarketSchedulerDisabledReason(env), null);
});
