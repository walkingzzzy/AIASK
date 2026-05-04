import test from 'node:test';
import assert from 'node:assert/strict';

const { PaperTradingService } = await import('../dist/paper-trading/paper-trading.service.js');

function createCacheStub(overrides = {}) {
  return {
    resolveTtl: () => 30,
    getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
    set: async () => {
      throw new Error('cache.set should not be called on failed summary');
    },
    del: async () => {},
    ...overrides,
  };
}

function createServiceWithActions(actions, options = {}) {
  const calls = [];
  const service = new PaperTradingService(
    {
      callTool: async (tool, args) => {
        calls.push({ tool, args });
        if (!(args.action in actions)) {
          throw new Error(`unexpected action: ${args.action}`);
        }
        return { success: true, data: actions[args.action] };
      },
    },
    {
      execute: async () => {
        throw new Error('idempotency.execute should not be called');
      },
    },
    createCacheStub({
      set: async () => {},
      ...options.cache,
    }),
  );
  return { service, calls };
}

async function withFixedDate(iso, run) {
  const RealDate = globalThis.Date;
  class MockDate extends RealDate {
    constructor(value) {
      super(value ?? iso);
    }
    static now() {
      return new RealDate(iso).getTime();
    }
  }
  globalThis.Date = MockDate;
  try {
    return await run();
  } finally {
    globalThis.Date = RealDate;
  }
}

test('PaperTradingService.summary degrades upstream transport failure into an explicit fallback snapshot', async () => {
  const calls = [];
  const service = new PaperTradingService(
    {
      callTool: async (tool, args) => {
        calls.push({ tool, args });
        throw new Error('summary unavailable');
      },
    },
    {
      execute: async () => {
        throw new Error('idempotency.execute should not be called in summary');
      },
    },
    createCacheStub(),
  );

  const result = await service.summary('u_demo', 'acct-1');

  assert.equal(result.account_id, 'acct-1');
  assert.equal(result.degraded, true);
  assert.equal(result.total_value, 100000);
  assert.equal(result.total_return_pct, 0);
  assert.match(result.section_errors.summary, /summary unavailable/);

  assert.equal(calls.length, 1);
  assert.equal(calls[0].tool, 'paper_trading_manager');
  assert.equal(calls[0].args.action, 'summary');
});

test('PaperTradingService.orders degrades transport failures to an empty order envelope', async () => {
  const calls = [];
  const service = new PaperTradingService(
    {
      callTool: async (tool, args) => {
        calls.push({ tool, args });
        throw new Error('orders transport timeout');
      },
    },
    {
      execute: async () => {
        throw new Error('idempotency.execute should not be called in orders');
      },
    },
    createCacheStub(),
  );

  const result = await service.orders('u_demo', 'sandbox-orders');

  assert.deepEqual(result.orders, []);
  assert.equal(result.count, 0);
  assert.equal(result.degraded, true);
  assert.match(result.fallback_reason, /orders/);
  assert.match(result.section_errors.orders, /orders transport timeout/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].args.action, 'orders');
});

test('PaperTradingService.pendingOrders degrades transport failures to an empty order envelope', async () => {
  const calls = [];
  const service = new PaperTradingService(
    {
      callTool: async (tool, args) => {
        calls.push({ tool, args });
        throw new Error('pending transport timeout');
      },
    },
    {
      execute: async () => {
        throw new Error('idempotency.execute should not be called in pendingOrders');
      },
    },
    createCacheStub(),
  );

  const result = await service.pendingOrders('u_demo', 'sandbox-pending');

  assert.deepEqual(result.orders, []);
  assert.equal(result.count, 0);
  assert.equal(result.degraded, true);
  assert.match(result.fallback_reason, /pending_orders/);
  assert.match(result.section_errors.pending_orders, /pending transport timeout/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].args.action, 'pending_orders');
});

test('PaperTradingService.updatePrices degrades transport failures to a non-throwing refresh envelope', async () => {
  const calls = [];
  const service = new PaperTradingService(
    {
      callTool: async (tool, args) => {
        calls.push({ tool, args });
        throw new Error('update prices transport timeout');
      },
    },
    {
      execute: async () => {
        throw new Error('idempotency.execute should not be called in updatePrices');
      },
    },
    createCacheStub(),
  );

  const result = await service.updatePrices('u_demo', 'playwright-demo');

  assert.equal(result.account_id, 'playwright-demo');
  assert.equal(result.degraded, true);
  assert.equal(result.refreshed, false);
  assert.equal(result.updated_count, 0);
  assert.match(result.fallback_reason, /update_prices/);
  assert.match(result.section_errors.update_prices, /update prices transport timeout/);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].args.action, 'update_prices');
});

test('PaperTradingService.trustStatus marks latest paper account as ready for demo when scan, prices, and NAV are current', async () => {
  await withFixedDate('2026-04-22T02:00:00.000Z', async () => {
    const { service } = createServiceWithActions({
      summary: {
        account_id: 'acct-1',
        total_value: 101200,
        account: { updated_at: '2026-04-22T01:59:40.000Z' },
        reconciliation: { drift_detected: false, reconciled: false },
      },
      positions: {
        positions: [
          {
            stock_code: '600519',
            quantity: 100,
            updated_at: '2026-04-22T01:59:50.000Z',
          },
        ],
        reconciliation: { drift_detected: false, reconciled: false },
      },
      orders: {
        orders: [
          {
            id: 't-1',
            trade_time: '2026-04-22T01:58:00.000Z',
          },
        ],
      },
      pending_orders: {
        orders: [],
      },
      nav_history: {
        nav: [
          {
            nav_date: '2026-04-21',
            created_at: '2026-04-21T07:30:00.000Z',
            total_value: 100800,
          },
        ],
      },
      matching_status: {
        running: true,
        scan_interval: 30,
        last_scan: '2026-04-22T01:59:45.000Z',
      },
      nav_status: {
        running: true,
        last_run: '2026-04-21T07:30:00.000Z',
      },
    });

    const result = await service.trustStatus('u_demo', 'acct-1');

    assert.equal(result.account_id, 'acct-1');
    assert.equal(result.latest, true);
    assert.equal(result.demo_ready, true);
    assert.equal(result.level, 'ready');
    assert.equal(result.environment.simulated_only, true);
    assert.equal(result.environment.dry_run, false);
    assert.equal(result.reconcile.positions.reconciled, true);
    assert.equal(result.reconcile.orders.reconciled, true);
    assert.equal(result.reconcile.nav.reconciled, true);
  });
});

test('PaperTradingService.trustStatus blocks demo when pending orders are newer than the latest matching scan', async () => {
  await withFixedDate('2026-04-22T02:00:00.000Z', async () => {
    const { service } = createServiceWithActions({
      summary: {
        account_id: 'acct-1',
        total_value: 101200,
        account: { updated_at: '2026-04-22T01:59:20.000Z' },
        reconciliation: { drift_detected: true, reconciled: true },
      },
      positions: {
        positions: [
          {
            stock_code: '600519',
            quantity: 100,
            updated_at: '2026-04-22T01:59:20.000Z',
          },
        ],
        reconciliation: { drift_detected: true, reconciled: true },
      },
      orders: {
        orders: [],
      },
      pending_orders: {
        orders: [
          {
            id: 12,
            created_at: '2026-04-22T01:59:50.000Z',
            updated_at: '2026-04-22T01:59:55.000Z',
          },
        ],
      },
      nav_history: {
        nav: [
          {
            nav_date: '2026-04-20',
            created_at: '2026-04-20T07:30:00.000Z',
            total_value: 100500,
          },
        ],
      },
      matching_status: {
        running: true,
        scan_interval: 30,
        last_scan: '2026-04-22T01:59:00.000Z',
      },
      nav_status: {
        running: true,
        last_run: '2026-04-20T07:30:00.000Z',
      },
    });

    const result = await service.trustStatus('u_demo', 'acct-1');

    assert.equal(result.latest, false);
    assert.equal(result.demo_ready, false);
    assert.equal(result.level, 'blocked');
    assert.equal(result.reconcile.orders.reconciled, false);
    assert.equal(result.reconcile.positions.reconciled, true);
    assert.equal(result.reasons.some((item) => /挂单/.test(String(item))), true);
    assert.equal(result.reasons.some((item) => /NAV 快照/.test(String(item))), true);
  });
});

test('PaperTradingService.testCleanup rejects non-sandbox accounts even when filled cleanup is requested', async () => {
  const { service } = createServiceWithActions({});
  await assert.rejects(
    () => service.testCleanup('u_demo', { account_id: 'default', include_filled_positions: true }),
    (error) => {
      const response = error.getResponse?.();
      assert.equal(response?.code, 'PAPER_TRADING_CLEANUP_FORBIDDEN');
      return true;
    },
  );
});

test('PaperTradingService.testCleanup can request sandbox filled-position reset', async () => {
  const { service, calls } = createServiceWithActions({
    pending_orders: { account_id: 'playwright-demo', orders: [], count: 0 },
    test_cleanup: {
      account_id: 'playwright-demo',
      positions_reset_count: 2,
      trades_deleted_count: 3,
      nav_deleted_count: 1,
      failed_count: 0,
    },
    reconcile: { reconciled: true },
  });

  const result = await service.testCleanup('u_demo', {
    account_id: 'playwright-demo',
    include_filled_positions: true,
  });

  assert.equal(result.cancelled_count, 0);
  assert.equal(result.filled_positions_count, 2);
  assert.equal(result.reset_trades_count, 3);
  assert.equal(result.reset_nav_count, 1);
  const cleanupCall = calls.find((call) => call.args.action === 'test_cleanup');
  assert.equal(cleanupCall?.args.params.include_filled_positions, true);
  assert.equal(cleanupCall?.args.params.cancel_pending, false);
});
