import { test } from '@playwright/test';
import { loginAsRole } from '../support/auth';
import { getBundle } from '../support/bundle';
import { runScenario } from '../support/scenario';
import { getSurface } from '../support/surfaces';
import {
  runBacktestWorkflow,
  runDataCenterWorkflow,
  runMarketWorkflow,
  runStockAnalysisWorkflow,
} from '../workflows/market-workflows';

test.setTimeout(360_000);

test('[surface:market-tabs] [scenario:workflow] 行情搜索到个股分析链路', async ({ page }, testInfo) => {
  const surface = getSurface('market-tabs');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/market');
    await runMarketWorkflow(page);
  });
});

test('[surface:data-center-tabs] [scenario:workflow] 数据中心多标签查询链路', async ({ page }, testInfo) => {
  const surface = getSurface('data-center-tabs');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/data');
    await runDataCenterWorkflow(page);
  });
});

test('[surface:stock-analysis-tabs] [scenario:workflow] 个股多标签分析链路', async ({ page }, testInfo) => {
  const surface = getSurface('stock-analysis-tabs');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/stock');
    await runStockAnalysisWorkflow(page);
  });
});

test('[surface:backtest] [scenario:workflow] 回测提交与批量对比', async ({ page }, testInfo) => {
  const surface = getSurface('backtest');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/backtest');
    await runBacktestWorkflow(page);
  }, {
    allowApi5xx: [/503 \/api\/backtest\/run/],
    allowConsoleErrors: [/Failed to load resource: the server responded with a status of 503 \(Service Unavailable\) @ \/api\/backtest\/run/i],
  });
});
