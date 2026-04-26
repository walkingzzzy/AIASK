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

function createPaperTradingStub(trackFixtures) {
  const calls = [];
  const readFixture = (accountId) => {
    if (!(accountId in trackFixtures)) {
      throw new Error(`unexpected account ${accountId}`);
    }
    return trackFixtures[accountId];
  };
  return {
    calls,
    api: {
      summary: async (userId, accountId) => {
        calls.push({ action: 'summary', userId, accountId });
        return readFixture(accountId).summary;
      },
      performance: async (userId, accountId) => {
        calls.push({ action: 'performance', userId, accountId });
        return readFixture(accountId).performance;
      },
      trustStatus: async (userId, accountId) => {
        calls.push({ action: 'trustStatus', userId, accountId });
        return readFixture(accountId).trustStatus;
      },
      navHistory: async (userId, accountId) => {
        calls.push({ action: 'navHistory', userId, accountId });
        return readFixture(accountId).navHistory;
      },
    },
  };
}

function createService(actions, trackFixtures) {
  const mcpCalls = [];
  const { api: paperTrading, calls: paperTradingCalls } = createPaperTradingStub(trackFixtures);
  const service = new StrategyMarketService(
    {
      callTool: async (tool, args) => {
        mcpCalls.push({ tool, args });
        if (!(args.action in actions)) {
          throw new Error(`unexpected action ${args.action}`);
        }
        return { success: true, data: actions[args.action] };
      },
      checkAvailableTools: async () => ({ reachable: true }),
    },
    createCacheStub(),
    {},
    paperTrading,
  );
  return { service, mcpCalls, paperTradingCalls };
}

test('StrategyMarketService.paperContext returns personal and incubation tracks without account crossover', async () => {
  const { service, paperTradingCalls } = createService(
    {
      detail: {
        strategy: {
          id: 'strat-1',
          name: 'Alpha Strategy',
          incubation_surface: {
            pipeline_stage: 'candidate',
            account_stage: 'candidate',
            account_status: 'active',
            stage_source: 'paper_account',
          },
        },
      },
      paper_session_get: {
        strategy_id: 'strat-1',
        paper_session_state: {
          available: true,
          has_session: true,
          account_id: 'personal-1',
          account_name: '个人盘',
          account_status: 'active',
        },
      },
      paper_account: {
        account: {
          id: 'incubation-1',
          strategy_id: 'strat-1',
          account_type: 'incubation',
          incubation_stage: 'candidate',
          status: 'active',
        },
        latest_nav: {
          nav_date: '2026-04-22',
          total_value: 105200,
        },
        order_summary: {
          total_orders: 6,
          total_trades: 4,
        },
      },
      incubation_metrics: {
        latest: {
          metric_date: '2026-04-22',
          account_id: 'incubation-1',
          decision: 'promote',
        },
      },
    },
    {
      'personal-1': {
        summary: {
          account_id: 'personal-1',
          total_return_pct: 12.5,
          account: { account_id: 'personal-1', name: '个人盘', status: 'active', account_type: 'personal_strategy' },
        },
        performance: { metrics: { totalReturn: 0.125 } },
        trustStatus: { account_id: 'personal-1', headline: '数据最新', latest: true, demo_ready: true },
        navHistory: { nav: [{ nav_date: '2026-04-22', total_value: 112500 }] },
      },
      'incubation-1': {
        summary: {
          account_id: 'incubation-1',
          total_return_pct: 5.2,
          account: { account_id: 'incubation-1', name: '孵化盘', status: 'active', account_type: 'incubation' },
        },
        performance: { metrics: { totalReturn: 0.052 } },
        trustStatus: { account_id: 'incubation-1', headline: '谨慎演示', latest: true, demo_ready: false },
        navHistory: { nav: [{ nav_date: '2026-04-22', total_value: 105200 }] },
      },
    },
  );

  const result = await service.paperContext('strat-1', { actorId: 'user-1', role: 'user' });

  assert.equal(result.strategy_id, 'strat-1');
  assert.equal(result.strategy_name, 'Alpha Strategy');
  assert.equal(result.personal?.kind, 'personal');
  assert.equal(result.personal?.source, 'strategy_paper_session');
  assert.equal(result.personal?.account_id, 'personal-1');
  assert.equal(result.personal?.account?.account_type, 'personal_strategy');
  assert.equal(result.personal?.trust_status?.headline, '数据最新');
  assert.equal(result.incubation?.kind, 'incubation');
  assert.equal(result.incubation?.source, 'strategy_binding');
  assert.equal(result.incubation?.account_id, 'incubation-1');
  assert.equal(result.incubation?.account?.account_type, 'incubation');
  assert.equal(result.incubation?.stage, 'candidate');
  assert.equal(result.incubation?.latest_metric?.decision, 'promote');
  assert.equal(result.incubation?.order_summary?.total_orders, 6);

  const summaryCalls = paperTradingCalls.filter((item) => item.action === 'summary');
  assert.deepEqual(
    summaryCalls.map((item) => item.accountId),
    ['personal-1', 'incubation-1'],
  );
});

test('StrategyMarketService.paperContext returns explicit unavailable reasons when only personal track exists', async () => {
  const { service } = createService(
    {
      detail: {
        strategy: {
          id: 'strat-2',
          name: 'Personal Only',
        },
      },
      paper_session_get: {
        strategy_id: 'strat-2',
        paper_session_state: {
          available: true,
          has_session: true,
          account_id: 'personal-only',
          account_status: 'active',
        },
      },
      paper_account: {},
      incubation_metrics: {},
    },
    {
      'personal-only': {
        summary: {
          account_id: 'personal-only',
          account: { account_id: 'personal-only', status: 'active', account_type: 'personal_strategy' },
        },
        performance: { metrics: { totalReturn: 0.01 } },
        trustStatus: { account_id: 'personal-only', headline: '数据最新' },
        navHistory: { nav: [{ nav_date: '2026-04-22', total_value: 101000 }] },
      },
    },
  );

  const result = await service.paperContext('strat-2', { actorId: 'user-2', role: 'user' });

  assert.equal(result.personal?.available, true);
  assert.equal(result.personal?.account_id, 'personal-only');
  assert.equal(result.incubation?.available, false);
  assert.match(String(result.incubation?.reason ?? ''), /尚未绑定孵化模拟盘账户/);
});

test('StrategyMarketService.paperContext returns explicit unavailable reasons when only incubation track exists', async () => {
  const { service } = createService(
    {
      detail: {
        strategy: {
          id: 'strat-3',
          name: 'Incubation Only',
          incubation_surface: {
            pipeline_stage: 'warmup',
            account_stage: 'warmup',
            account_status: 'active',
            stage_source: 'paper_account',
          },
        },
      },
      paper_session_get: {
        strategy_id: 'strat-3',
        paper_session_state: {
          available: true,
          has_session: false,
          mode: 'none',
        },
      },
      paper_account: {
        account: {
          id: 'incubation-only',
          account_type: 'incubation',
          incubation_stage: 'warmup',
          status: 'active',
        },
      },
      incubation_metrics: {},
    },
    {
      'incubation-only': {
        summary: {
          account_id: 'incubation-only',
          account: { account_id: 'incubation-only', status: 'active', account_type: 'incubation' },
        },
        performance: { metrics: { totalReturn: 0.02 } },
        trustStatus: { account_id: 'incubation-only', headline: '谨慎演示' },
        navHistory: { nav: [{ nav_date: '2026-04-22', total_value: 102000 }] },
      },
    },
  );

  const result = await service.paperContext('strat-3', { actorId: 'user-3', role: 'user' });

  assert.equal(result.personal?.available, false);
  assert.match(String(result.personal?.reason ?? ''), /尚未创建个人模拟盘测试/);
  assert.equal(result.incubation?.available, true);
  assert.equal(result.incubation?.account_id, 'incubation-only');
});
