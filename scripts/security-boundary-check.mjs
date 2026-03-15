#!/usr/bin/env node

/**
 * Security boundary regression check
 *
 * 前提：apps/bff 已成功构建，存在 dist 产物。
 * 用途：验证关键身份绑定与 WebSocket 房间授权不会回退到“信任客户端传参”。
 */

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);
const controllerDist = resolve(process.cwd(), 'apps/bff/dist/strategy/strategy.controller.js');
const gatewayDist = resolve(process.cwd(), 'apps/bff/dist/ws/ws.gateway.js');
const paperGatewayDist = resolve(process.cwd(), 'apps/bff/dist/paper-trading/paper-trading.gateway.js');

if (!existsSync(controllerDist) || !existsSync(gatewayDist) || !existsSync(paperGatewayDist)) {
  throw new Error('缺少 apps/bff/dist 构建产物，请先执行 npm run build -w apps/bff');
}

const { StrategyMarketController } = require(controllerDist);
const { WsGateway } = require(gatewayDist);
const { PaperTradingGateway } = require(paperGatewayDist);

function makeReq(userId) {
  return {
    user: userId ? { id: userId } : undefined,
    headers: { 'x-trace-id': 'trace-security-check' },
  };
}

function makeSocket({ userId } = {}) {
  const joined = [];
  const emitted = [];
  return {
    id: `socket-${userId ?? 'anon'}`,
    data: userId ? { user: { id: userId } } : {},
    handshake: { auth: {}, headers: {} },
    join: async (room) => {
      joined.push(room);
    },
    emit: (event, payload) => {
      emitted.push({ event, payload });
    },
    _joined: joined,
    _emitted: emitted,
  };
}

async function checkStrategyController() {
  const calls = [];
  const service = {
    create: async (payload) => {
      calls.push(['create', payload]);
      return payload;
    },
    subscribe: async (strategyId, userId) => {
      calls.push(['subscribe', { strategyId, userId }]);
      return { strategyId, userId };
    },
    review: async (strategyId, userId, rating, comment) => {
      calls.push(['review', { strategyId, userId, rating, comment }]);
      return { strategyId, userId, rating, comment };
    },
    getSignals: async (strategyId, userId, query) => {
      calls.push(['signals', { strategyId, userId, query }]);
      return { strategyId, userId, query };
    },
  };

  const controller = new StrategyMarketController(service);

  await controller.create(
    {
      name: 'secure strategy',
      strategy_type: 'momentum',
      author_id: 'spoofed-author',
    },
    makeReq('real-user'),
  );
  assert.equal(calls[0][0], 'create');
  assert.equal(calls[0][1].author_id, 'real-user');

  await controller.subscribe(
    'strat-1',
    { user_id: 'spoofed-user' },
    makeReq('real-user'),
  );
  assert.deepEqual(calls[1], ['subscribe', { strategyId: 'strat-1', userId: 'real-user' }]);

  await controller.review(
    'strat-1',
    { user_id: 'spoofed-user', rating: 5, comment: 'great' },
    makeReq('real-user'),
  );
  assert.deepEqual(calls[2], ['review', {
    strategyId: 'strat-1',
    userId: 'real-user',
    rating: 5,
    comment: 'great',
  }]);

  await controller.signals(
    'strat-1',
    { user_id: 'spoofed-user', limit: 20 },
    makeReq('real-user'),
  );
  assert.deepEqual(calls[3], ['signals', {
    strategyId: 'strat-1',
    userId: 'real-user',
    query: { limit: 20 },
  }]);

  await assert.rejects(
    () => controller.subscribe('strat-1', {}, makeReq()),
    (error) => error?.constructor?.name === 'UnauthorizedException',
  );

  return {
    createAuthorId: calls[0][1].author_id,
    subscribeUserId: calls[1][1].userId,
    reviewUserId: calls[2][1].userId,
    signalsUserId: calls[3][1].userId,
  };
}

async function checkWsGateway() {
  const listAccountsCalls = [];
  const gateway = new WsGateway(
    {
      addSubscribedCodes: () => {},
      removeSubscribedCodes: () => {},
    },
    {
      verifyAccessToken: async () => ({ id: 'unused' }),
    },
    {
      listAccounts: async (userId) => {
        listAccountsCalls.push(userId);
        return { accounts: [{ id: 'acct-1' }, { account_id: 'acct-2' }] };
      },
      summary: async () => ({ account_id: 'acct-summary' }),
    },
  );

  const authorized = makeSocket({ userId: 'user-1' });
  await gateway.handleTradeSub(authorized, { accountId: 'acct-2' });
  assert.deepEqual(authorized._joined, ['trade:acct-2']);

  const unauthorized = makeSocket({ userId: 'user-1' });
  await gateway.handleTradeSub(unauthorized, { accountId: 'acct-x' });
  assert.deepEqual(unauthorized._joined, []);
  assert.equal(unauthorized._emitted.at(-1)?.event, 'ws:error');
  assert.equal(unauthorized._emitted.at(-1)?.payload?.code, 'forbidden_account');

  const unauthenticated = makeSocket();
  gateway.handleAlertSub(unauthenticated);
  assert.deepEqual(unauthenticated._joined, []);
  assert.equal(unauthenticated._emitted.at(-1)?.payload?.code, 'unauthorized');

  const watchlist = makeSocket({ userId: 'watch-user' });
  gateway.handleWatchlistSub(watchlist);
  assert.deepEqual(watchlist._joined, ['watchlist:watch-user']);

  return {
    listAccountsCalls,
    authorizedRooms: authorized._joined,
    unauthorizedError: unauthorized._emitted.at(-1)?.payload,
    watchlistRooms: watchlist._joined,
  };
}

async function checkPaperTradingGateway() {
  const verifyCalls = [];
  const listAccountsCalls = [];
  const snapshotCalls = [];
  const gateway = new PaperTradingGateway(
    {
      listAccounts: async (userId) => {
        listAccountsCalls.push(userId);
        return { accounts: [{ id: 'acct-1' }, { id: 'acct-2' }] };
      },
      summary: async () => ({ account_id: 'acct-summary' }),
      realtimeSnapshot: async (userId, accountId) => {
        snapshotCalls.push({ userId, accountId });
        return { userId, accountId, ok: true };
      },
    },
    {
      verifyAccessToken: async (token) => {
        verifyCalls.push(token);
        return { id: 'paper-user' };
      },
    },
  );

  const authorized = {
    id: 'paper-client-ok',
    data: {},
    handshake: { auth: { accessToken: 'token-ok', account_id: 'acct-2' }, query: {}, headers: {} },
    rooms: new Set(['paper-client-ok']),
    join: async (room) => {
      authorized.rooms.add(room);
    },
    emit: (event, payload) => {
      authorized._emitted.push({ event, payload });
    },
    disconnect: (force) => {
      authorized._disconnects.push(force);
    },
    _emitted: [],
    _disconnects: [],
  };
  await gateway.handleConnection(authorized);
  assert.ok(authorized.rooms.has('paper:paper-user:acct-2'));
  assert.equal(authorized._disconnects.length, 0);
  assert.equal(authorized._emitted.at(-1)?.event, 'paper.snapshot');

  const forbidden = {
    id: 'paper-client-bad',
    data: {},
    handshake: { auth: { accessToken: 'token-bad', account_id: 'acct-x' }, query: {}, headers: {} },
    rooms: new Set(['paper-client-bad']),
    join: async (room) => {
      forbidden.rooms.add(room);
    },
    emit: (event, payload) => {
      forbidden._emitted.push({ event, payload });
    },
    disconnect: (force) => {
      forbidden._disconnects.push(force);
    },
    _emitted: [],
    _disconnects: [],
  };
  await gateway.handleConnection(forbidden);
  assert.equal(forbidden.rooms.size, 1);
  assert.equal(forbidden._emitted.at(-1)?.event, 'paper.snapshot.error');
  assert.equal(forbidden._emitted.at(-1)?.payload?.code, 'forbidden_account');
  assert.deepEqual(forbidden._disconnects, [true]);

  return {
    verifyCalls,
    listAccountsCalls,
    snapshotCalls,
    authorizedRooms: [...authorized.rooms].filter((room) => room.startsWith('paper:')),
    forbiddenError: forbidden._emitted.at(-1)?.payload,
  };
}

async function main() {
  const controller = await checkStrategyController();
  const gateway = await checkWsGateway();
  const paperGateway = await checkPaperTradingGateway();

  console.log('SECURITY_BOUNDARY_CHECK_OK');
  console.log(JSON.stringify({ controller, gateway, paperGateway }, null, 2));
}

main().catch((error) => {
  console.error('SECURITY_BOUNDARY_CHECK_FAIL');
  console.error(error);
  process.exit(1);
});
