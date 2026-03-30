import 'reflect-metadata';
import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { McpGatewayService } from '../../src/mcp-gateway/mcp-gateway.service';
import { MarketService } from '../../src/market/market.service';

test('balanced startup profile defaults to one full worker', () => {
  const configService = {
    get(key: string, defaultValue?: string) {
      if (key === 'MCP_STDIO_STARTUP_PROFILE') return 'balanced';
      return defaultValue;
    },
  };

  const service = new McpGatewayService(configService as never);
  const internal = service as any;

  assert.equal(internal.fullProfilePoolSlots, 1);
  assert.equal(internal.resolveStartupProfile(0), 'full');
  assert.equal(internal.resolveStartupProfile(1), 'tool-only');
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
