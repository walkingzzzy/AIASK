import test from 'node:test';
import assert from 'node:assert/strict';

const { StrategyMarketService } = await import('../dist/strategy/strategy.service.core.js');

function createCacheStub() {
  return {
    resolveTtl: () => 30,
    getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
    set: async () => {},
    del: async () => {},
    clear: async () => {},
  };
}

function createService(overrides = {}) {
  const service = new StrategyMarketService(
    {
      checkAvailableTools: async () => ({ reachable: true, source: 'test-runtime' }),
      callTool: async () => {
        throw new Error('unexpected mcp call');
      },
    },
    createCacheStub(),
    {},
    {},
  );
  Object.assign(service, overrides);
  return service;
}

test('StrategyMarketService.coreChainAcceptance reports a fully connected user chain', async () => {
  const service = createService({
    capabilities: async () => ({
      actor_permissions: {
        can_create_personal_strategy: true,
        can_create_paper_session: true,
        can_ai_suggest_personal_strategy: true,
        can_ai_optimize_personal_strategy: true,
      },
    }),
    factoryMarketView: async () => ({
      runs: { latest: { run_id: 'run-1', status: 'success' } },
      surface: { visible_outputs: [{ key: 'ranking', title: '策略榜单', status: 'available' }] },
    }),
    detail: async (id) => ({
      strategy: { id, name: 'Alpha Market', status: 'listed' },
      owner_state: { personal_strategy: false },
    }),
    myFavorites: async () => ({
      favorites: [{ id: 'market-1', subscribed_at: '2026-04-24T01:00:00.000Z' }],
    }),
    myStrategies: async () => ({
      items: [
        {
          id: 'personal-1',
          name: 'Alpha Market · 我的版本',
          tags: ['personal_strategy'],
          params: {
            metadata: {
              source_strategy_id: 'market-1',
              forked_at: '2026-04-24T01:05:00.000Z',
            },
          },
          owner_state: { personal_strategy: true, editable: true },
        },
      ],
    }),
    personalStrategyContext: async (id) => ({
      strategy_id: id,
      strategy_name: 'Alpha Market · 我的版本',
      personal_strategy: true,
      source_strategy_id: 'market-1',
      owner_state: { personal_strategy: true, editable: true },
      mutation_guard: { allowed: true, reason: null },
      action_modes: [
        { action_kind: 'view', available: true },
        { action_kind: 'generate_update_suggestion', available: true },
        { action_kind: 'optimize', available: true },
      ],
      draft_snapshot: {
        id,
        name: 'Alpha Market · 我的版本',
        params: { metadata: { source_strategy_id: 'market-1' } },
        factor_weights: { momentum: 1 },
        tags: ['personal_strategy'],
      },
      paper_session_state: { has_session: true, account_id: 'pp-1' },
    }),
    paperContext: async () => ({
      personal: {
        available: true,
        account_id: 'pp-1',
        latest_nav: { nav_date: '2026-04-24', total_value: 100800 },
      },
    }),
    paperSession: async () => ({
      paper_session_state: { has_session: true, account_id: 'pp-1' },
      session: { account_id: 'pp-1', last_used_at: '2026-04-24T01:10:00.000Z' },
    }),
    taskRuns: async () => ({
      items: [
        {
          id: 7,
          task_name: 'ai_optimize_personal_strategy',
          status: 'success',
          completed_at: '2026-04-24T01:20:00.000Z',
        },
      ],
    }),
    aiExperiments: async () => ({
      items: [
        {
          experiment_id: 'sge-1',
          status: 'completed',
          created_at: '2026-04-24T01:19:00.000Z',
        },
      ],
    }),
  });

  const result = await service.coreChainAcceptance(
    { actorId: 'user-1', role: 'user' },
    { strategy_id: 'market-1' },
  );

  assert.equal(result.dto_version, 'strategy_market.core_chain_acceptance.v1');
  assert.equal(result.target.market_strategy_id, 'market-1');
  assert.equal(result.target.personal_strategy_id, 'personal-1');
  assert.equal(result.summary.overall_status, 'passed');
  assert.equal(result.summary.fully_completed, true);
  assert.equal(result.summary.broken_steps.length, 0);
  assert.deepEqual(result.steps.map((step) => step.status), ['passed', 'passed', 'passed', 'passed', 'passed']);
  assert.equal(result.steps.find((step) => step.key === 'ai_submit')?.last_success_at, '2026-04-24T01:20:00.000Z');
});

test('StrategyMarketService.coreChainAcceptance marks downstream steps blocked when no personal strategy exists', async () => {
  const service = createService({
    capabilities: async () => ({
      actor_permissions: {
        can_create_personal_strategy: true,
        can_create_paper_session: true,
        can_ai_suggest_personal_strategy: true,
        can_ai_optimize_personal_strategy: true,
      },
    }),
    factoryMarketView: async () => ({
      runs: { latest: { run_id: 'run-2', status: 'success' } },
      surface: { visible_outputs: [{ key: 'ranking', title: '策略榜单', status: 'available' }] },
    }),
    detail: async (id) => ({
      strategy: { id, name: 'Beta Market', status: 'listed' },
      owner_state: { personal_strategy: false },
    }),
    myFavorites: async () => ({ favorites: [] }),
    myStrategies: async () => ({ items: [] }),
  });

  const result = await service.coreChainAcceptance(
    { actorId: 'user-1', role: 'user' },
    { strategy_id: 'market-2' },
  );

  const byKey = new Map(result.steps.map((step) => [step.key, step]));
  assert.equal(byKey.get('view_strategy')?.status, 'passed');
  assert.equal(byKey.get('personal_strategy')?.status, 'ready');
  assert.equal(byKey.get('paper_session')?.status, 'blocked');
  assert.equal(byKey.get('ai_read')?.status, 'blocked');
  assert.equal(byKey.get('ai_submit')?.status, 'blocked');
  assert.equal(result.summary.runnable, false);
  assert.deepEqual(result.summary.broken_steps, ['paper_session', 'ai_read', 'ai_submit']);
});

test('StrategyMarketService.coreChainAcceptance returns structured anonymous state instead of throwing auth errors', async () => {
  const service = createService({
    capabilities: async () => ({
      actor_permissions: {
        can_create_personal_strategy: false,
        can_create_paper_session: false,
        can_ai_suggest_personal_strategy: false,
        can_ai_optimize_personal_strategy: false,
      },
    }),
    factoryMarketView: async () => ({
      runs: { latest: { run_id: 'run-public', status: 'success' } },
      surface: { visible_outputs: [{ key: 'ranking', title: '策略榜单', status: 'available' }] },
    }),
    detail: async (id) => ({
      strategy: { id, name: 'Public Strategy', status: 'listed' },
      owner_state: { personal_strategy: false },
    }),
  });

  const result = await service.coreChainAcceptance(
    { actorId: null, role: 'user' },
    { strategy_id: 'market-public' },
  );

  assert.equal(result.actor.user_id, null);
  assert.equal(result.environment.authenticated, false);
  assert.equal(result.environment.errors.auth.includes('未登录'), true);
  assert.equal(result.steps.find((step) => step.key === 'view_strategy')?.status, 'passed');
  assert.equal(result.steps.find((step) => step.key === 'personal_strategy')?.status, 'blocked');
  assert.equal(
    result.steps.find((step) => step.key === 'personal_strategy')?.dependency_gaps.includes('login_missing'),
    true,
  );
});
