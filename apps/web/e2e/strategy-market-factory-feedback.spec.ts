import { expect, test } from '@playwright/test';
import {
  assertNoCriticalPageIssues,
  assertNoHorizontalOverflow,
  assertProtectedShell,
  createPageIssueCollector,
  openProtectedPage,
  waitForSettledUi,
} from './helpers/app';
import { mockStrategyMarketScenario } from './helpers/strategy-market-mocks';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

test('should render P3 feedback loop surfaces in strategy market dashboard', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await mockStrategyMarketScenario(page);
  await openProtectedPage(page, '/strategy-market?task=ranking&from=e2e');
  await assertProtectedShell(page);
  await waitForSettledUi(page, 1_200);

  await expect(page.getByText(/任务: ranking/)).toBeVisible();
  await page.getByRole('button', { name: '展开工厂运行态' }).click();

  await expect(page.getByRole('heading', { name: '策略工厂运行态' })).toBeVisible();
  await expect(page.getByText('P3 反馈闭环', { exact: true })).toBeVisible();
  await expect(page.getByText('晋级评审状态')).toBeVisible();
  await expect(page.getByText(/approved 3/i)).toBeVisible();
  await expect(page.getByText(/反馈家族 4/)).toBeVisible();
  await expect(page.getByText(/晋级评审 5/)).toBeVisible();
  await expect(page.getByText(/阻断任务 2/)).toBeVisible();
  await expect(page.getByText(/冷却任务 1/)).toBeVisible();

  await page.getByRole('button', { name: '查看详情' }).click();

  await expect(page.getByText('生命周期反馈闭环')).toBeVisible();
  await expect(page.getByText('生命周期反馈输入')).toBeVisible();
  await expect(page.getByText('Research Artifact')).toBeVisible();
  await expect(page.getByText('生成模式控制明细')).toBeVisible();
  await expect(page.getByText('受抑制范围')).toBeVisible();
  await expect(page.getByText(/manual review 2/i).first()).toBeVisible();
  await expect(page.getByText(/drawdown breach/i).first()).toBeVisible();

  await assertNoHorizontalOverflow(page);
  assertNoCriticalPageIssues(collector);
  collector.dispose();
});
