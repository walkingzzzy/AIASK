import 'reflect-metadata';
import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { WsGateway } from '../../src/ws/ws.gateway';

function makeGateway() {
  const removedCodes: string[] = [];
  const marketScheduler = {
    addSubscribedCodes: (codes: string[]) => codes,
    removeSubscribedCodes: (codes: string[]) => removedCodes.push(...codes),
  };
  const authService = { verifyAccessToken: async () => null };
  const paperTradingService = { listAccounts: async () => ({ accounts: [] }), summary: async () => ({}) };

  const gw = new WsGateway(
    marketScheduler as never,
    authService as never,
    paperTradingService as never,
  );
  return { gw, removedCodes };
}

test('ws gateway _track / _untrack manages room membership correctly', () => {
  const { gw } = makeGateway();
  const internal = gw as any;

  internal._track('quote:stock:600519', 'clientA');
  internal._track('quote:stock:600519', 'clientB');

  assert.equal(internal.rooms.get('quote:stock:600519').size, 2);

  const emptiedByA = internal._untrack('quote:stock:600519', 'clientA');
  assert.equal(emptiedByA, false);
  assert.equal(internal.rooms.get('quote:stock:600519').size, 1);

  const emptiedByB = internal._untrack('quote:stock:600519', 'clientB');
  assert.equal(emptiedByB, true);
  assert.equal(internal.rooms.has('quote:stock:600519'), false);
});

test('ws gateway getStats reflects tracked rooms and unique clients', () => {
  const { gw } = makeGateway();
  const internal = gw as any;

  internal._track('quote:stock:600519', 'clientA');
  internal._track('quote:stock:000001', 'clientA');
  internal._track('quote:stock:000001', 'clientB');

  const stats = gw.getStats();
  assert.equal(stats.rooms, 2);
  assert.equal(stats.clients, 2);
  assert.equal(stats.roomDetails['quote:stock:600519'], 1);
  assert.equal(stats.roomDetails['quote:stock:000001'], 2);
});

test('ws gateway handleDisconnect removes client from all rooms and triggers scheduler cleanup', () => {
  const { gw, removedCodes } = makeGateway();
  const internal = gw as any;

  internal._track('quote:stock:600519', 'clientA');
  internal._track('quote:stock:000001', 'clientA');
  internal._track('quote:stock:000001', 'clientB');

  const fakeClient = { id: 'clientA', leave: async () => undefined };
  gw.handleDisconnect(fakeClient as never);

  // clientA removed; quote:stock:600519 now empty — code should be removed from scheduler
  assert.equal(internal.rooms.has('quote:stock:600519'), false);
  assert.ok(removedCodes.includes('600519'), 'scheduler should be notified to remove 600519');

  // quote:stock:000001 still has clientB
  assert.equal(internal.rooms.get('quote:stock:000001').size, 1);
  assert.ok(!removedCodes.includes('000001'), '000001 should remain subscribed');
});

test('ws gateway _extractTrackedQuoteCode only extracts stock rooms', () => {
  const { gw } = makeGateway();
  const internal = gw as any;

  assert.equal(internal._extractTrackedQuoteCode('quote:stock:600519'), '600519');
  assert.equal(internal._extractTrackedQuoteCode('quote:index:000001'), null);
  assert.equal(internal._extractTrackedQuoteCode('quote:broadcast'), null);
  assert.equal(internal._extractTrackedQuoteCode('alert:user123'), null);
});

test('ws gateway onAlertPushed listener receives alert and unsubscribe works', async () => {
  const { gw } = makeGateway();
  const received: unknown[] = [];

  const unsubscribe = gw.onAlertPushed((event) => {
    received.push(event);
  });

  const internal = gw as any;
  internal.emitAlertEvent({ userId: 'u1', data: { title: 'test' } });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(received.length, 1);

  unsubscribe();
  internal.emitAlertEvent({ userId: 'u1', data: { title: 'after-unsubscribe' } });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(received.length, 1, 'no more events after unsubscribe');
});
