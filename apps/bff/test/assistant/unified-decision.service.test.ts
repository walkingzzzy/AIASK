import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { AssistantUnifiedService } from '../../src/assistant/assistant-unified.service';
import { validateContract } from '../contract/api-contracts';

function createLegacyCard(action: string, confidence: number) {
  return {
    action,
    confidence,
    summary: `${action} summary`,
    reasons: [`${action} reason`],
    executionPlan: [],
    risks: [],
    dataProvenance: [],
    complianceNotice: 'notice',
  };
}

test('unified summary logs legacy comparison audit and returns audit metadata', async () => {
  let appended: Record<string, unknown> | null = null;
  const mcp = {
    async callTool(name: string) {
      assert.equal(name, 'get_unified_decision_summary');
      return {
        data: {
          action: 'buy',
          confidence: 0.72,
          summary: '统一决策偏多',
          reasons: ['基本面改善'],
          risks: ['短线波动'],
          gate_flags: [],
          details_available: true,
        },
      };
    },
  };
  const assistantService = {
    shouldBuy: async () => ({ card: createLegacyCard('buy', 0.71) }),
    diagnosis: async () => ({ card: createLegacyCard('hold', 0.49) }),
    decisionManagerAnalyze: async () => ({ card: createLegacyCard('buy', 0.68) }),
  };
  const auditStore = {
    async append(entry: Record<string, unknown>) {
      appended = entry;
      return 42;
    },
    async listByUser() {
      return [];
    },
  };

  const service = new AssistantUnifiedService(mcp as never, assistantService as never, auditStore as never);
  const result = await service.getUnifiedDecisionSummary('600519', 'balanced', 'user-1', true, 'trace-1');

  assert.equal(result.card.action, 'buy');
  assert.equal(result.legacyComparison?.auditId, 42);
  assert.equal(result.legacyComparison?.auditLogged, true);
  assert.equal(result.legacyComparison?.traceId, 'trace-1');
  assert.equal(result.legacyComparison?.actionAlignment, 'mixed');
  const auditEntry = appended as Record<string, unknown> | null;
  assert.equal(auditEntry?.stockCode, '600519');
  assert.equal(auditEntry?.traceId, 'trace-1');
  assert.equal(auditEntry?.investmentStyle, 'balanced');
});

test('diff log query returns empty payload for anonymous user without touching store', async () => {
  let called = false;
  const service = new AssistantUnifiedService(
    { callTool: async () => ({}) } as never,
    {} as never,
    {
      async append() {
        return 1;
      },
      async listByUser() {
        called = true;
        return [];
      },
    } as never,
  );

  const result = await service.getUnifiedDecisionDiffLogs('', { limit: 5, stockCode: '600519' });

  assert.equal(called, false);
  assert.deepEqual(result.items, []);
  assert.equal(result.total, 0);
  assert.deepEqual(result.filters, {
    limit: 5,
    stockCode: '600519',
    actionAlignment: null,
  });
});

test('diff log envelope matches the declared API contract', () => {
  const payload = {
    success: true,
    data: {
      items: [
        {
          id: 1,
          traceId: 'trace-1',
          userId: 'user-1',
          stockCode: '600519',
          investmentStyle: 'balanced',
          unifiedAction: 'buy',
          actionAlignment: 'mixed',
          legacyActions: [
            { source: 'should_i_buy', action: 'buy' },
            { source: 'smart_stock_diagnosis', action: 'hold' },
          ],
          disagreements: ['smart_stock_diagnosis 与统一决策动作不一致'],
          diffSummary: '统一决策与旧入口部分一致、部分分歧。',
          details: { unified: { action: 'buy' } },
          createdAt: '2026-03-20T08:00:00.000Z',
        },
      ],
      total: 1,
      filters: {
        limit: 10,
        stockCode: '600519',
        actionAlignment: 'mixed',
      },
    },
    traceId: 'trace-1',
  };

  const result = validateContract('GET /assistant/unified-decision/diff-logs', payload);
  assert.equal(result.valid, true, result.errors?.join('\n'));
});
