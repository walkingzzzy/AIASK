import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { AssistantController } from '../../src/assistant/assistant.controller';

test('controller forwards unified decision request context to service', async () => {
  const assistantService = {
    diagnosis: async () => ({}),
    shouldBuy: async () => ({}),
    shouldSell: async () => ({}),
    getIndustryChain: async () => ({}),
    generateDailyReport: async () => ({}),
  };

  const calls: unknown[][] = [];
  const unifiedService = {
    async getUnifiedDecisionSummary(...args: unknown[]) {
      calls.push(args);
      return { card: { action: 'buy' }, request: { code: '600519' } };
    },
    async getUnifiedDecisionDetails() {
      return { card: { action: 'buy' }, details: {} };
    },
    async getUnifiedDecisionDiffLogs() {
      return { items: [], total: 0, filters: {} };
    },
  };

  const controller = new AssistantController(assistantService as never, unifiedService as never);
  const response = await controller.unifiedDecision(
    { code: '600519', investmentStyle: 'aggressive', legacyMode: true },
    {
      user: { sub: 'user-1' },
      traceId: 'trace-1',
      headers: { 'x-request-id': 'ignored' },
    },
  );

  assert.deepEqual(calls[0], ['600519', 'aggressive', 'user-1', true, 'trace-1']);
  assert.equal(response.success, true);
  assert.equal(response.traceId, 'trace-1');
});

test('controller maps diff log query filters to service contract', async () => {
  const assistantService = {
    diagnosis: async () => ({}),
    shouldBuy: async () => ({}),
    shouldSell: async () => ({}),
    getIndustryChain: async () => ({}),
    generateDailyReport: async () => ({}),
  };

  const calls: unknown[][] = [];
  const unifiedService = {
    async getUnifiedDecisionSummary() {
      return {};
    },
    async getUnifiedDecisionDetails() {
      return {};
    },
    async getUnifiedDecisionDiffLogs(...args: unknown[]) {
      calls.push(args);
      return { items: [], total: 0, filters: { limit: 5, stockCode: '600519', actionAlignment: 'mixed' } };
    },
  };

  const controller = new AssistantController(assistantService as never, unifiedService as never);
  const response = await controller.unifiedDecisionDiffLogs(
    { limit: 5, code: '600519', actionAlignment: 'mixed' },
    {
      user: { id: 'user-2' },
      headers: { 'x-request-id': 'trace-2' },
    },
  );

  assert.deepEqual(calls[0], ['user-2', { limit: 5, stockCode: '600519', actionAlignment: 'mixed' }]);
  assert.equal(response.success, true);
  assert.equal(response.traceId, 'trace-2');
});
