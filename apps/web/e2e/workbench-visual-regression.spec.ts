import { expect, test, type Page } from '@playwright/test';
import {
  assertNoCriticalPageIssues,
  assertNoHorizontalOverflow,
  assertProtectedShell,
  createPageIssueCollector,
  loginAsConfigured,
  openProtectedPage,
  waitForSettledUi,
} from './helpers/app';

test.describe.configure({ mode: 'serial' });
test.setTimeout(180_000);

type WorkbenchRouteSpec = {
  name: string;
  path: string;
  verify: (page: Page) => Promise<void>;
};

const WORKBENCH_ROUTES: WorkbenchRouteSpec[] = [
  {
    name: '事件工作台',
    path: '/events?code=000001&days=7&type=all',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '事件日历工作台' })).toBeVisible();
      await expect(page.getByRole('button', { name: /订阅当前事件|取消当前订阅|取消事件订阅/ }).first()).toBeVisible();
      await expect(page.getByText('Event Workspace')).toBeVisible();
      await expect(page.getByText('Workspace Summary')).toBeVisible();
      await expect(page.getByText('事件中心').first()).toBeVisible();
    },
  },
  {
    name: '执行工作台',
    path: '/execution?code=000001',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '执行工作台' })).toBeVisible();
      await expect(page.getByRole('button', { name: '去绩效中心复盘' })).toBeVisible();
      await expect(page.getByRole('button', { name: '提交执行' })).toBeVisible();
      await expect(page.getByText('Execution Workspace')).toBeVisible();
      await expect(page.getByText('执行工作台').first()).toBeVisible();
    },
  },
  {
    name: '绩效复盘工作台',
    path: '/performance?mode=account&days=30',
    verify: async (page) => {
      await expect(page.getByRole('heading', { name: '绩效复盘工作台' })).toBeVisible();
      await expect(page.getByRole('tab', { name: '账户绩效' })).toBeVisible();
      await expect(page.getByRole('button', { name: '刷新当前数据' })).toBeVisible();
      await expect(page.getByText('Performance Workspace')).toBeVisible();
      await expect(page.getByText('绩效中心').first()).toBeVisible();
    },
  },
];

async function verifyStrategyDetailWorkbench(page: Page) {
  await openProtectedPage(page, '/strategy-market');
  await assertProtectedShell(page);
  await waitForSettledUi(page, 1_500);

  const detailHref = await page.locator('a[href^="/strategy-market/"]').first().getAttribute('href');
  expect(detailHref, '策略详情链接不能为空').toBeTruthy();

  const collector = createPageIssueCollector(page);
  try {
    await openProtectedPage(page, detailHref!);
    await assertProtectedShell(page);
    await waitForSettledUi(page, 2_500);

    await expect(page).toHaveURL(/\/strategy-market\/[^/?#]+/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByText('Strategy Workspace')).toBeVisible();
    await expect(page.getByText('Workspace Summary')).toBeVisible();
    await expect(page.getByText('页面 策略详情').first()).toBeVisible();
    await expect(page.getByRole('tab', { name: '策略概览' })).toBeVisible();
    await expect(page.getByRole('button', { name: '加入组合' })).toBeVisible();
    await expect(page.getByText('当前页面').first()).toBeVisible();
    await expect(page.getByText('策略详情').first()).toBeVisible();
    await assertNoHorizontalOverflow(page);
    assertNoCriticalPageIssues(collector);
  } finally {
    collector.dispose();
  }
}

test('should keep key workbench pages visually consistent', async ({ page }) => {
  await loginAsConfigured(page, WORKBENCH_ROUTES[0].path);

  for (const route of WORKBENCH_ROUTES) {
    await test.step(route.name, async () => {
      const collector = createPageIssueCollector(page);
      try {
        await openProtectedPage(page, route.path);
        await assertProtectedShell(page);
        await waitForSettledUi(page, 1_400);
        await route.verify(page);
        await assertNoHorizontalOverflow(page);
        assertNoCriticalPageIssues(collector);
      } finally {
        collector.dispose();
      }
    });
  }

  await test.step('策略详情工作台', async () => {
    await verifyStrategyDetailWorkbench(page);
  });
});
