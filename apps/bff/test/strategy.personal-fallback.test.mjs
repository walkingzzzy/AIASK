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

function strategyRow(overrides = {}) {
  return {
    id: 'personal-1',
    name: 'Alpha · 我的版本',
    description: 'personal draft',
    author_id: 'user-1',
    strategy_type: 'custom',
    params: { metadata: { source_strategy_id: 'market-1' } },
    factor_weights: { momentum: 1 },
    status: 'draft',
    tags: ['personal_strategy', 'forked_strategy'],
    backtest_artifact_id: null,
    subscriber_count: 0,
    avg_rating: 0,
    review_count: 0,
    metrics: {},
    ...overrides,
  };
}

function createService(db, callTool) {
  return new StrategyMarketService(
    {
      checkAvailableTools: async () => ({ reachable: true }),
      callTool:
        callTool ??
        (async () => {
          throw new Error('strategy_manager unavailable');
        }),
    },
    createCacheStub(),
    db,
    {},
  );
}

test('StrategyMarketService.detail fallback preserves personal owner editability', async () => {
  const db = {
    query: async () => ({ rows: [strategyRow()] }),
  };
  const service = createService(db);

  const result = await service.detail('personal-1', { userId: 'user-1', role: 'admin' });

  assert.equal(result.degraded_detail, true);
  assert.equal(result.owner_state.personal_strategy, true);
  assert.equal(result.owner_state.owned, true);
  assert.equal(result.owner_state.editable, true);
  assert.equal(result.runtime_action_contract.state.editable, true);
});

test('StrategyMarketService.myStrategies falls back to local DB rows with owner actions', async () => {
  const db = {
    query: async () => ({ rows: [{ ...strategyRow(), total_count: 1 }] }),
  };
  const service = createService(db);

  const result = await service.myStrategies('user-1', 'user', { limit: 20 });
  const row = result.items[0];

  assert.equal(result.local_fallback_used, true);
  assert.equal(result.count, 1);
  assert.equal(row.owner_state.personal_strategy, true);
  assert.equal(row.owner_state.editable, true);
  assert.equal(row.runtime_action_contract.state.editable, true);
});

test('StrategyMarketService.forkStrategy uses DB fallback when strategy_manager is unavailable', async () => {
  let inserted = null;
  const db = {
    query: async (sql, params = []) => {
      if (/INSERT INTO strategies/i.test(sql)) {
        inserted = {
          id: params[0],
          name: params[1],
          description: params[2],
          author_id: params[3],
          strategy_type: params[4],
          params: JSON.parse(params[5]),
          factor_weights: JSON.parse(params[6]),
          status: 'draft',
          tags: params[7],
          backtest_artifact_id: params[8],
          subscriber_count: 0,
          avg_rating: 0,
          review_count: 0,
          metrics: {},
        };
        return { rows: [], rowCount: 1 };
      }
      if (/INSERT INTO strategy_lineage/i.test(sql)) {
        return { rows: [], rowCount: 1 };
      }
      if (params[0] === 'market-1') {
        return {
          rows: [
            strategyRow({
              id: 'market-1',
              name: 'Alpha',
              author_id: 'publisher',
              params: {},
              tags: [],
              status: 'listed',
            }),
          ],
        };
      }
      if (inserted && params[0] === inserted.id) {
        return { rows: [inserted] };
      }
      return { rows: [] };
    },
  };
  const service = createService(db);

  const result = await service.forkStrategy('market-1', { actorId: 'user-1', role: 'user' });

  assert.match(result.strategy_id, /^strat_/);
  assert.equal(result.source_strategy_id, 'market-1');
  assert.equal(result.local_fallback_used, true);
  assert.equal(result.owner_state.owned, true);
  assert.equal(result.owner_state.editable, true);
  assert.equal(result.strategy.params.metadata.source_strategy_id, 'market-1');
});

test('StrategyMarketService.deletePersonalStrategy DB fallback is owner-only', async () => {
  const updates = [];
  const db = {
    query: async (sql, params = []) => {
      if (/UPDATE strategies/i.test(sql)) {
        updates.push(params);
        return { rows: [], rowCount: 1 };
      }
      return { rows: [strategyRow({ id: params[0] })] };
    },
  };
  const service = createService(db);

  const result = await service.deletePersonalStrategy('personal-1', { actorId: 'user-1', role: 'admin' });

  assert.equal(result.archived, true);
  assert.equal(result.local_fallback_used, true);
  assert.deepEqual(updates[0], ['personal-1', 'user-1']);
});

test('StrategyMarketService.deletePersonalStrategy archives local mirror after manager success', async () => {
  const updates = [];
  const db = {
    query: async (sql, params = []) => {
      if (/UPDATE strategies/i.test(sql)) {
        updates.push(params);
        return { rows: [], rowCount: 1 };
      }
      return { rows: [strategyRow({ id: params[0] })] };
    },
  };
  const service = createService(db, async () => ({
    data: {
      strategy_id: 'personal-1',
      archived: true,
    },
  }));

  const result = await service.deletePersonalStrategy('personal-1', { actorId: 'user-1', role: 'admin' });

  assert.equal(result.archived, true);
  assert.equal(result.local_mirror_archived, true);
  assert.deepEqual(updates[0], ['personal-1', 'user-1']);
});
