import { test } from '@playwright/test';
import { loginAsRole } from '../support/auth';
import { getBundle } from '../support/bundle';
import { runScenario } from '../support/scenario';
import { getSurface } from '../support/surfaces';
import {
  runPaperTradingWorkflow,
  runPerformanceWorkflow,
  runStrategyDetailWorkflow,
  runStrategyMarketWorkflow,
} from '../workflows/strategy-workflows';

test.setTimeout(360_000);

test('[surface:paper-trading-order-workbench] [scenario:workflow] 模拟交易下单撤单', async ({ page }, testInfo) => {
  const surface = getSurface('paper-trading-order-workbench');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/paper-trading');
    await runPaperTradingWorkflow(page);
  });
});

test('[surface:performance-review-workbench] [scenario:workflow] 绩效刷新与归因切换', async ({ page }, testInfo) => {
  const surface = getSurface('performance-review-workbench');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', `/performance?mode=account&account_id=${encodeURIComponent(bundle.execution.accountId)}`);
    await runPerformanceWorkflow(page, bundle.execution.accountId, bundle.portfolio.portfolioId);
  });
});

test('[surface:strategy-market-catalog-workbench] [scenario:workflow] 策略超市目录到组合购物车', async ({ page }, testInfo) => {
  const surface = getSurface('strategy-market-catalog-workbench');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/strategy-market');
    await runStrategyMarketWorkflow(page);
  });
});

test('[surface:strategy-detail-review-workbench] [scenario:workflow] 策略详情审查与订阅切换', async ({ page }, testInfo) => {
  const surface = getSurface('strategy-detail-review-workbench');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', bundle.strategy.route);
    await runStrategyDetailWorkflow(page, bundle.strategy.route);
  });
});
