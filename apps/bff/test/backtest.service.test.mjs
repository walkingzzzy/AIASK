import test from 'node:test';
import assert from 'node:assert/strict';

const { BacktestService } = await import('../dist/backtest/backtest.service.js');

function buildGateway() {
  return {
    async callTool(name, args) {
      if (name !== 'backtest_manager') {
        return { success: false, error: 'unsupported tool' };
      }
      const payload = JSON.parse(String(args.kwargs ?? '{}'));
      const shortPeriod = Number(payload.short_period ?? 5);
      const longPeriod = Number(payload.long_period ?? 20);
      const lookback = Number(payload.lookback ?? 20);
      const threshold = Number(payload.threshold ?? 0.02);
      const score =
        shortPeriod * 0.7
        + longPeriod * 0.15
        + lookback * 0.05
        - threshold * 100;
      return {
        success: true,
        data: {
          artifact_id: payload.artifact_id ?? 'artifact_demo',
          result: {
            total_return: 12 + shortPeriod * 0.8 - threshold * 50,
            sharpe_ratio: Number((1 + score / 20).toFixed(4)),
            max_drawdown: 8 + Math.max(0, longPeriod - shortPeriod) * 0.1,
            win_rate: 55,
            trade_count: 14,
            profit_factor: 1.4,
            initial_capital: payload.initial_capital ?? 100000,
            final_capital: 112000,
            equity_curve: [100000, 101000, 103000],
            dates: ['2025-01-01', '2025-01-02', '2025-01-03'],
            trades: [],
          },
        },
      };
    },
  };
}

function buildFailingGateway(message = 'transport timeout') {
  return {
    async callTool() {
      throw new Error(message);
    },
  };
}

test('BacktestService.optimize ranks candidates and returns best params', async () => {
  const service = new BacktestService(buildGateway());
  const data = await service.optimize({
    code: '600519',
    strategy: 'ma_cross',
    startDate: '2025-01-01',
    endDate: '2025-12-31',
    objective: 'balanced',
    maxCandidates: 5,
    topN: 3,
  });

  assert.equal(data.code, '600519');
  assert.equal(data.strategy, 'ma_cross');
  assert.equal(data.evaluatedCount, 5);
  assert.ok(Array.isArray(data.candidates));
  assert.equal(data.candidates.length, 3);
  assert.equal(typeof data.bestCandidate?.params?.shortPeriod, 'number');
});

test('BacktestService.walkForward returns fold summary', async () => {
  const service = new BacktestService(buildGateway());
  const data = await service.walkForward({
    code: '600519',
    strategy: 'momentum',
    startDate: '2025-01-01',
    endDate: '2025-12-31',
    lookback: 20,
    threshold: 0.02,
    trainDays: 90,
    testDays: 30,
    stepDays: 30,
    maxFolds: 4,
  });

  assert.ok(Array.isArray(data.folds));
  assert.ok(data.folds.length >= 1);
  assert.equal(data.summary?.foldCount, data.folds.length);
  assert.equal(typeof data.summary?.positiveFoldRatio, 'number');
});

test('BacktestService.run returns degraded envelope instead of throwing when manager unavailable', async () => {
  const service = new BacktestService(buildFailingGateway('backtest manager unavailable'));
  const data = await service.run({
    code: '600519',
    strategy: 'ma_cross',
    startDate: '2025-01-01',
    endDate: '2025-12-31',
    artifactId: 'artifact_unavailable',
  });

  assert.equal(data.degraded, true);
  assert.equal(data.artifactId, 'artifact_unavailable');
  assert.equal(data.sourceTool, 'backtest_manager');
  assert.equal(data.failureReason?.reasonCode, 'backtest_run_failed');
  assert.match(String(data.fallbackReason), /backtest manager unavailable/);
  assert.deepEqual(data.equity_curve, []);
  assert.deepEqual(data.dates, []);
  assert.deepEqual(data.trades, []);
  assert.equal(data.metrics?.totalReturn, null);
});

test('BacktestService.list returns empty degraded envelope instead of throwing when manager unavailable', async () => {
  const service = new BacktestService(buildFailingGateway('backtest list timeout'));
  const data = await service.list(20);

  assert.equal(data.degraded, true);
  assert.equal(data.sourceTool, 'backtest_manager');
  assert.deepEqual(data.items, []);
  assert.match(String(data.fallbackReason), /backtest list timeout/);
});
