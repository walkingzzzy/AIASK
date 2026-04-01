import 'reflect-metadata';
import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { McpGatewayService } from '../../src/mcp-gateway/mcp-gateway.service';
import { MarketService } from '../../src/market/market.service';

test('balanced startup profile defaults to one heavy worker slot', () => {
  const configService = {
    get(key: string, defaultValue?: string) {
      if (key === 'MCP_STDIO_STARTUP_PROFILE') return 'balanced';
      return defaultValue;
    },
  };

  const service = new McpGatewayService(configService as never);
  const internal = service as any;

  assert.equal(internal.fullProfilePoolSlots, 1);
  assert.equal(internal.resolveStartupProfile(0), 'worker');
  assert.equal(internal.resolveStartupProfile(1), 'tool-only');
});

test('worker startup profile keeps heavy tools without enabling full autonomy profile', () => {
  const configService = {
    get(key: string, defaultValue?: string) {
      if (key === 'MCP_STDIO_STARTUP_PROFILE') return 'worker';
      return defaultValue;
    },
  };

  const service = new McpGatewayService(configService as never);
  const internal = service as any;

  assert.equal(internal.fullProfilePoolSlots, internal.poolSize);
  assert.equal(internal.resolveStartupProfile(0), 'worker');
  assert.equal(internal.resolveStartupProfile(3), 'worker');
});

test('market quote errors from MCP are not cached as successful payloads', async () => {
  let cacheSetCalled = false;
  const service = new MarketService(
    {
      callTool: async () => ({ success: false, error: 'quote backend unavailable' }),
    } as never,
    {
      resolveTtl: () => 30,
      getWithMeta: async () => ({ value: null, meta: { backend: 'memory' as const } }),
      set: async () => {
        cacheSetCalled = true;
      },
    } as never,
  );

  await assert.rejects(
    () => service.getQuote('600519'),
    (error: any) => {
      assert.equal(error?.getStatus?.(), 502);
      const response = error?.getResponse?.() as Record<string, unknown>;
      assert.equal(response?.detail, 'quote backend unavailable');
      return true;
    },
  );
  assert.equal(cacheSetCalled, false);
});

test('recycleConnection replaces a broken pooled transport in place', async () => {
  const service = new McpGatewayService({ get: (_key: string, defaultValue?: string) => defaultValue } as never);
  const internal = service as any;
  const closeCalls: number[] = [];

  const stale = {
    id: 0,
    client: { name: 'stale-client' },
    transport: { close: async () => closeCalls.push(0) },
    busy: false,
    connectPromise: null,
  };
  const fresh = {
    id: 0,
    client: { name: 'fresh-client' },
    transport: { close: async () => closeCalls.push(100) },
    busy: false,
    connectPromise: null,
  };

  internal.pool = [stale];
  internal.createConnection = async (id: number) => ({ ...fresh, id });

  await internal.recycleConnection(stale);

  assert.deepEqual(closeCalls, [0]);
  assert.equal(stale.client.name, 'fresh-client');
  assert.equal(stale.transport, fresh.transport);
  assert.equal(internal.pool.length, 1);
});

test('disposeAll closes pooled transports and rejects pending waiters', async () => {
  const service = new McpGatewayService({ get: (_key: string, defaultValue?: string) => defaultValue } as never);
  const internal = service as any;
  const closeCalls: string[] = [];
  const rejected: string[] = [];

  const pooled = {
    id: 1,
    client: {},
    transport: { close: async () => closeCalls.push('pool:1') },
    busy: false,
    connectPromise: null,
  };
  const dedicated = {
    id: 9,
    client: {},
    transport: { close: async () => closeCalls.push('dedicated:quant_manager') },
    busy: false,
    connectPromise: null,
  };
  const makeWaiter = () => ({
    resolve: () => undefined,
    reject: (error: Error) => rejected.push(error.message),
    timeout: setTimeout(() => undefined, 5_000),
  });

  internal.pool = [pooled];
  internal.dedicatedConnections = new Map([['quant_manager', dedicated]]);
  internal.waitQueue = [makeWaiter()];
  internal.dedicatedWaitQueues = new Map([['quant_manager', [makeWaiter()]]]);
  internal.initialized = true;

  await internal.disposeAll();

  assert.deepEqual(closeCalls.sort(), ['dedicated:quant_manager', 'pool:1']);
  assert.deepEqual(rejected, ['MCP gateway is shutting down', 'MCP gateway is shutting down']);
  assert.equal(internal.pool.length, 0);
  assert.equal(internal.dedicatedConnections.size, 0);
  assert.equal(internal.dedicatedWaitQueues.size, 0);
  assert.equal(internal.initialized, false);
});
