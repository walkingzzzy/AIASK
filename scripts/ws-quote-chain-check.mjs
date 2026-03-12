#!/usr/bin/env node

/**
 * WS quote chain regression check
 *
 * 前提：apps/bff 已成功构建，存在 dist 产物。
 * 用途：验证本次“实时推送链路最小修复”的关键行为是否仍然成立。
 */

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const gatewayDist = resolve(process.cwd(), 'apps/bff/dist/ws/ws.gateway.js');
const schedulerDist = resolve(process.cwd(), 'apps/bff/dist/market/market.scheduler.js');

if (!existsSync(gatewayDist) || !existsSync(schedulerDist)) {
  throw new Error('缺少 apps/bff/dist 构建产物，请先执行 npm run build -w apps/bff');
}

const { WsGateway } = require(gatewayDist);
const { MarketScheduler } = require(schedulerDist);

async function main() {
  const schedulerCalls = { add: [], remove: [] };
  const gateway = new WsGateway({
    addSubscribedCodes: (codes) => schedulerCalls.add.push([...codes]),
    removeSubscribedCodes: (codes) => schedulerCalls.remove.push([...codes]),
  });

  const emitted = [];
  gateway.server = {
    to(room) {
      return {
        emit(event, payload) {
          emitted.push({ room, event, payload });
        },
      };
    },
  };

  const joined = [];
  const left = [];
  const client1 = {
    id: 'client-1',
    join: async (room) => joined.push(['client-1', room]),
    leave: async (room) => left.push(['client-1', room]),
  };
  const client2 = {
    id: 'client-2',
    join: async (room) => joined.push(['client-2', room]),
    leave: async (room) => left.push(['client-2', room]),
  };

  gateway.handleQuoteSub(client1, { codes: ['600519'], type: 'stock' });
  gateway.handleQuoteSub(client2, { codes: ['600519'], type: 'stock' });
  assert.deepEqual(schedulerCalls.add, [['600519'], ['600519']]);

  gateway.handleQuoteUnsub(client1, { codes: ['600519'], type: 'stock' });
  assert.deepEqual(schedulerCalls.remove, []);

  gateway.handleDisconnect(client2);
  assert.deepEqual(schedulerCalls.remove, [['600519']]);

  gateway.pushQuote('600519', 'stock', { price: 1400 });
  assert.ok(emitted.some((item) => item.room === 'quote:stock:600519' && item.event === 'quote:update'));
  assert.ok(emitted.some((item) => item.room === 'quote:broadcast' && item.event === 'quote:update'));

  const schedulerPushCalls = { single: [], batch: [] };
  const scheduler = new MarketScheduler(
    {
      getBatchQuotes: async (codes) => ({ quotes: codes.map((code, i) => ({ code, price: 100 + i })) }),
      getIndexQuote: async () => ({}),
    },
    {
      pushQuote: (code, type, data) => schedulerPushCalls.single.push({ code, type, data }),
      pushBatchQuotes: (items) => schedulerPushCalls.batch.push(items),
    },
  );

  scheduler.addSubscribedCodes(['600519', '000001']);
  await scheduler.pushBatchQuotes();

  assert.equal(schedulerPushCalls.single.length, 2);
  assert.equal(schedulerPushCalls.batch.length, 1);
  assert.deepEqual(
    schedulerPushCalls.single.map((item) => item.code).sort(),
    ['000001', '600519'],
  );

  console.log('WS_QUOTE_CHAIN_CHECK_OK');
  console.log(JSON.stringify({
    joined,
    left,
    schedulerCalls,
    emittedCount: emitted.length,
    schedulerPushSummary: {
      single: schedulerPushCalls.single.length,
      batch: schedulerPushCalls.batch.length,
    },
  }, null, 2));
}

main().catch((error) => {
  console.error('WS_QUOTE_CHAIN_CHECK_FAIL');
  console.error(error);
  process.exit(1);
});

