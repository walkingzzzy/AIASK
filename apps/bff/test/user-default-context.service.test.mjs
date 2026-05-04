import test from 'node:test';
import assert from 'node:assert/strict';

const { UserDefaultContextService } = await import('../dist/user-default-context/user-default-context.service.js');

function createService({
  prefs = {},
  watchlistGroups = [],
  positionsPayload = { positions: [] },
} = {}) {
  let savedPrefs = null;
  const preferencesService = {
    getUserPreferences: async () => savedPrefs ?? prefs,
    setUserPreferences: async (_userId, nextPrefs) => {
      savedPrefs = nextPrefs;
    },
  };
  const watchlistService = {
    listGroups: async () => watchlistGroups,
  };
  const paperTradingService = {
    positions: async () => positionsPayload,
  };
  return {
    service: new UserDefaultContextService(preferencesService, watchlistService, paperTradingService),
    getSavedPrefs: () => savedPrefs,
  };
}

test('UserDefaultContextService ignores legacy 000001/600519 when not user-confirmed', async () => {
  const { service } = createService({
    prefs: {
      defaultStockCode: '600519',
      userDefaultContext: { stockCode: '000001' },
      workspaceState: {
        activeWorkspaceId: 'workspace-a',
        workspaces: [
          {
            id: 'workspace-a',
            name: '默认工作区',
            context: { stockCode: '600519' },
          },
        ],
      },
    },
  });

  const context = await service.getDefaultContext('user-a');
  assert.equal(context.trustedStockCode, null);
  assert.equal(context.stockSource, 'none');
  assert.equal(context.emptyReason, 'legacy_system_fallback_ignored');
});

test('UserDefaultContextService resolves watchlist before paper positions and profile preferences', async () => {
  const { service } = createService({
    prefs: {
      userDefaultContext: { stockCode: '300750' },
    },
    watchlistGroups: [
      {
        id: 'g1',
        name: '测试分组',
        items: [{ code: '601318' }],
      },
    ],
    positionsPayload: {
      account_id: 'sandbox-a',
      positions: [{ stock_code: '000858', quantity: 100 }],
    },
  });

  const context = await service.getDefaultContext('user-a');
  assert.equal(context.trustedStockCode, '601318');
  assert.equal(context.stockSource, 'watchlist');
  assert.equal(context.paperPositionLeadCode, '000858');
  assert.equal(context.profileStockCode, '300750');
});

test('UserDefaultContextService uses confirmed workspace stock before watchlist', async () => {
  const confirmedAt = '2026-04-27T05:00:00.000Z';
  const { service } = createService({
    prefs: {
      workspaceState: {
        activeWorkspaceId: 'workspace-a',
        workspaces: [
          {
            id: 'workspace-a',
            name: '确认工作区',
            context: { stockCode: '600519', stockConfirmedAt: confirmedAt },
          },
        ],
      },
    },
    watchlistGroups: [
      {
        id: 'g1',
        name: '测试分组',
        items: [{ code: '601318' }],
      },
    ],
  });

  const context = await service.getDefaultContext('user-a');
  assert.equal(context.trustedStockCode, '600519');
  assert.equal(context.stockSource, 'workspace');
  assert.equal(context.stockConfirmedAt, confirmedAt);
});

test('UserDefaultContextService saves confirmed stock to profile and active workspace context', async () => {
  const { service, getSavedPrefs } = createService({
    prefs: {
      userDefaultContext: {},
      workspaceState: {
        activeWorkspaceId: 'workspace-a',
        workspaces: [
          {
            id: 'workspace-a',
            name: '默认工作区',
            context: {},
          },
        ],
      },
    },
  });

  const context = await service.saveDefaultContext('user-a', {
    stockCode: '000001',
    accountId: 'sandbox-a',
    strategyId: 'strategy-a',
    strategyName: '测试策略',
  });
  const savedPrefs = getSavedPrefs();

  assert.equal(context.trustedStockCode, '000001');
  assert.equal(context.stockSource, 'workspace');
  assert.match(context.stockConfirmedAt, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(savedPrefs.userDefaultContext.stockCode, '000001');
  assert.equal(savedPrefs.workspaceState.workspaces[0].context.stockCode, '000001');
  assert.equal(savedPrefs.workspaceState.workspaces[0].context.accountId, 'sandbox-a');
  assert.equal(savedPrefs.workspaceState.workspaces[0].context.strategyId, 'strategy-a');
});
