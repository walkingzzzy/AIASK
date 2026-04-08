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
  DEMO_STRATEGY_NAME,
  mockStrategyMarketScenario,
} from './helpers/strategy-market-mocks';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

test('should cover strategy-market overview, factory feedback, catalog and detail flow', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await mockStrategyMarketScenario(page);
  await openProtectedPage(page, '/strategy-market?task=ranking&from=e2e-full');
  await assertProtectedShell(page);
  await waitForSettledUi(page, 1_200);

  await expect(page.getByText('Strategy Workspace')).toBeVisible();
  await expect(page.getByRole('heading', { name: '先看筛选结果，再决定订阅、组合和工厂动作。' })).toBeVisible();
  await expect(page.getByText(/来源: e2e-full/)).toBeVisible();
  await expect(page.getByText(/任务: ranking/)).toBeVisible();

  await expect(page.getByText('工厂概况')).toBeVisible();
  await expect(page.getByText('只看关键工厂指标')).toBeVisible();
  await expect(page.getByText(/快照完成率 0\.95%/)).toBeVisible();
  await expect(page.getByText(/最近失败运行 0/)).toBeVisible();

  await expect(page.getByText('联动观测')).toBeVisible();
  await expect(page.getByText('工厂运行与因子治理是否真正接通')).toBeVisible();
  await expect(page.getByText('最新工厂状态')).toBeVisible();
  await expect(page.getByText('governed pool 已就绪')).toBeVisible();

  const searchInput = page.getByLabel('搜索策略名称、描述或类型');
  const visibleDetailLink = page.locator(`a[href="/strategy-market/${DEMO_STRATEGY_ID}"]:visible`).first();
  await searchInput.fill('反馈闭环');
  await expect(visibleDetailLink).toBeVisible();

  await page.getByRole('button', { name: '展开工厂运行态' }).click();
  await expect(page.getByRole('heading', { name: '策略工厂运行态' })).toBeVisible();
  await expect(page.getByText('P3 反馈闭环', { exact: true })).toBeVisible();
  await expect(page.getByText(/反馈家族 4/)).toBeVisible();
  await expect(page.getByText(/晋级评审 5/)).toBeVisible();

  await page.getByRole('button', { name: '查看详情' }).click();
  await expect(page.getByText('生命周期反馈闭环')).toBeVisible();
  await expect(page.getByText('生命周期反馈输入')).toBeVisible();

  await visibleDetailLink.click();
  await waitForSettledUi(page, 1_000);

  await expect(page).toHaveURL(new RegExp(`/strategy-market/${DEMO_STRATEGY_ID}(?:\\?.*)?$`));
  await expect(page.getByRole('heading', { name: DEMO_STRATEGY_NAME, level: 1 })).toBeVisible();
  await expect(page.getByRole('tab', { name: '策略概览' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '实盘跟踪' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '工厂审查' })).toBeVisible();
  await expect(page.getByText('运行摘要')).toBeVisible();
  await expect(page.getByText('可信信息')).toBeVisible();
  await expect(page.getByText('净值轨迹')).toBeVisible();
  await expect(page.getByText('总收益')).toBeVisible();

  await page.getByRole('tab', { name: '实盘跟踪' }).click();
  await waitForSettledUi(page, 800);

  await expect(page.getByText('前向验证指标')).toBeVisible();
  await expect(page.getByText('信号历史')).toBeVisible();
  await expect(page.getByText('总信号数', { exact: true })).toBeVisible();
  await expect(page.getByText('600519')).toBeVisible();

  await page.getByRole('tab', { name: '工厂审查' }).click();
  await waitForSettledUi(page, 1_000);

  await expect(page.getByText('工厂质检摘要', { exact: true })).toBeVisible();
  await expect(page.getByText('孵化观察窗口', { exact: true })).toBeVisible();
  await expect(page.getByText('运行时控制面', { exact: true })).toBeVisible();
  await expect(page.getByText('事件投影 / 回放视图', { exact: true })).toBeVisible();
  await expect(page.getByText('生命周期事件流', { exact: true })).toBeVisible();
  await expect(page.getByText(/控制模式: active/)).toBeVisible();
  await expect(page.getByText(/评审: accept 0\.87/)).toBeVisible();
  await expect(page.getByText('factory-review-bot')).toBeVisible();
  await expect(page.getByText('task-projection-001')).toBeVisible();

  await assertNoHorizontalOverflow(page);
  assertNoCriticalPageIssues(collector);
  collector.dispose();
});
