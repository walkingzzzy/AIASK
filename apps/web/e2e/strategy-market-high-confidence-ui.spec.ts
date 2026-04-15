import { expect, test } from '@playwright/test';
import {
  assertNoCriticalPageIssues,
  assertNoHorizontalOverflow,
  assertProtectedShell,
  createPageIssueCollector,
  openProtectedPage,
  waitForSettledUi,
} from './helpers/app';
import {
  DEMO_STRATEGY_ID,
  mockStrategyMarketScenario,
} from './helpers/strategy-market-mocks';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

const ALLOWABLE_ENV_PAGE_ERRORS = [
  /\/api\/chat\/conversations\/sync .*access control checks/i,
  /\/login\?redirect=.*_rsc=.*access control checks/i,
  /_next\/static\/webpack\/.*hot-update\.json .*access control checks/i,
  /^Error: 数据服务暂不可用$/i,
];

test('keeps high-confidence UI hidden when quality UI V2 flag is off', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await mockStrategyMarketScenario(page, { qualityUiV2Enabled: false });
  await openProtectedPage(page, '/strategy-market?task=ranking&from=e2e');
  await assertProtectedShell(page);
  await waitForSettledUi(page, 1_200);

  await page.getByRole('button', { name: '展开工厂运行态' }).click();
  await expect(page.getByRole('heading', { name: '策略工厂运行态' })).toBeVisible();
  await expect(page.getByText('高置信质量面板', { exact: true })).toHaveCount(0);

  await openProtectedPage(page, `/strategy-market/${DEMO_STRATEGY_ID}`);
  await waitForSettledUi(page, 1_200);
  await expect(page.getByText('高置信质量', { exact: true })).toHaveCount(0);
  await page.getByRole('tab', { name: '工厂审查' }).click();
  await waitForSettledUi(page, 600);
  await expect(page.getByText('高置信质量面板', { exact: true })).toHaveCount(0);

  await assertNoHorizontalOverflow(page);
  assertNoCriticalPageIssues(collector, {
    allowPageErrors: ALLOWABLE_ENV_PAGE_ERRORS,
  });
  collector.dispose();
});

test('renders additive high-confidence UI when quality UI V2 flag is on', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await mockStrategyMarketScenario(page, { qualityUiV2Enabled: true });
  await openProtectedPage(page, '/strategy-market?task=ranking&from=e2e');
  await assertProtectedShell(page);
  await waitForSettledUi(page, 1_200);

  await page.getByRole('button', { name: '展开工厂运行态' }).click();
  await expect(page.getByText('高置信质量面板', { exact: true })).toBeVisible();
  await expect(page.getByText(/预测质量：strong 2/i)).toBeVisible();
  await expect(page.getByText(/执行质量：strong 1/i)).toBeVisible();
  await expect(page.getByText(/证据对齐：aligned 2/i)).toBeVisible();
  await expect(page.getByText('Signal Quality Registry', { exact: true })).toBeVisible();
  await expect(page.getByText(/drift stable/i)).toBeVisible();

  await openProtectedPage(page, `/strategy-market/${DEMO_STRATEGY_ID}`);
  await waitForSettledUi(page, 1_200);
  await expect(page.getByText('高置信质量', { exact: true })).toBeVisible();
  await expect(page.getByText(/预测质量: 强/)).toBeVisible();
  await expect(page.getByText(/执行质量: 混合/)).toBeVisible();
  await expect(page.getByText(/合同状态: 诊断可用/)).toBeVisible();
  await expect(page.getByText('Step-level Lineage', { exact: true })).toBeVisible();
  await expect(page.getByText('Recent Runtime Actions', { exact: true })).toBeVisible();
  await expect(page.getByText('freeze_reentry', { exact: true }).first()).toBeVisible();
  await page.getByRole('tab', { name: '工厂审查' }).click();
  await waitForSettledUi(page, 600);
  await expect(page.getByText('高置信质量面板', { exact: true })).toBeVisible();
  await expect(page.getByText(/预测质量: 强/)).toBeVisible();
  await expect(page.getByText(/执行质量: 混合/)).toBeVisible();
  await expect(page.getByRole('heading', { name: '执行链路' })).toBeVisible();
  await expect(page.getByText('证据门禁', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('mixed_with_degraded', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('池子画像', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('high_vol_growth', { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/hard:1/i)).toBeVisible();
  await expect(page.getByText(/degraded:1/i)).toBeVisible();
  await expect(page.getByText(/non_same_day_source/i)).toBeVisible();
  await expect(page.getByText('风控来源', { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/trend_expansion/i)).toBeVisible();
  await expect(page.getByText(/atr_bucketed_high_vol_growth_breakout/i)).toBeVisible();
  await expect(page.getByText('Step-level Lineage', { exact: true })).toBeVisible();
  await expect(page.getByText('freeze_reentry', { exact: true }).first()).toBeVisible();

  await assertNoHorizontalOverflow(page);
  assertNoCriticalPageIssues(collector, {
    allowPageErrors: ALLOWABLE_ENV_PAGE_ERRORS,
  });
  collector.dispose();
});
