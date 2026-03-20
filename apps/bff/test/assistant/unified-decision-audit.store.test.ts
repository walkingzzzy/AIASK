import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { AssistantUnifiedAuditStore } from '../../src/assistant/assistant-unified-audit.store';

test('audit store filters in-memory diff logs by user, code and alignment', async () => {
  const store = new AssistantUnifiedAuditStore({ enabled: false } as never);

  await store.append({
    traceId: 'trace-1',
    userId: 'user-1',
    stockCode: '600519',
    investmentStyle: 'balanced',
    unifiedAction: 'buy',
    actionAlignment: 'aligned',
    legacyActions: [{ source: 'should_i_buy', action: 'buy' }],
    disagreements: [],
    diffSummary: '一致',
    details: {},
    createdAt: '2026-03-20T08:00:00.000Z',
  });
  await store.append({
    traceId: 'trace-2',
    userId: 'user-1',
    stockCode: '000001',
    investmentStyle: 'balanced',
    unifiedAction: 'hold',
    actionAlignment: 'mixed',
    legacyActions: [{ source: 'should_i_buy', action: 'buy' }],
    disagreements: ['动作不一致'],
    diffSummary: '部分分歧',
    details: {},
    createdAt: '2026-03-20T09:00:00.000Z',
  });
  await store.append({
    traceId: 'trace-3',
    userId: 'user-2',
    stockCode: '600519',
    investmentStyle: 'aggressive',
    unifiedAction: 'sell',
    actionAlignment: 'divergent',
    legacyActions: [{ source: 'should_i_buy', action: 'buy' }],
    disagreements: ['方向完全相反'],
    diffSummary: '明显分歧',
    details: {},
    createdAt: '2026-03-20T10:00:00.000Z',
  });

  const filtered = await store.listByUser('user-1', {
    stockCode: '600519',
    actionAlignment: 'aligned',
    limit: 10,
  });

  assert.equal(filtered.length, 1);
  assert.equal(filtered[0]?.traceId, 'trace-1');
  assert.equal(filtered[0]?.stockCode, '600519');
  assert.equal(filtered[0]?.actionAlignment, 'aligned');
});

test('audit store returns newest records first in memory mode', async () => {
  const store = new AssistantUnifiedAuditStore({ enabled: false } as never);

  await store.append({
    traceId: 'trace-1',
    userId: 'user-1',
    stockCode: '600519',
    investmentStyle: 'balanced',
    unifiedAction: 'buy',
    actionAlignment: 'aligned',
    legacyActions: [],
    disagreements: [],
    diffSummary: 'first',
    details: {},
    createdAt: '2026-03-20T08:00:00.000Z',
  });
  await store.append({
    traceId: 'trace-2',
    userId: 'user-1',
    stockCode: '600519',
    investmentStyle: 'balanced',
    unifiedAction: 'hold',
    actionAlignment: 'mixed',
    legacyActions: [],
    disagreements: [],
    diffSummary: 'second',
    details: {},
    createdAt: '2026-03-20T09:00:00.000Z',
  });

  const items = await store.listByUser('user-1', { limit: 10 });

  assert.equal(items.length, 2);
  assert.equal(items[0]?.traceId, 'trace-2');
  assert.equal(items[1]?.traceId, 'trace-1');
});
