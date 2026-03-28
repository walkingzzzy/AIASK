import { expect, test, type ConsoleMessage, type Locator, type Page } from '@playwright/test';
import { dismissOnboarding, openProtectedPage } from './helpers/app';

test.describe.configure({ mode: 'serial' });
test.setTimeout(90_000);

function collectConsoleErrors(page: Page) {
  const messages: string[] = [];
  const handler = (message: ConsoleMessage) => {
    if (message.type() === 'error') {
      messages.push(message.text());
    }
  };
  page.on('console', handler);
  return {
    messages,
    dispose: () => page.off('console', handler),
  };
}

async function waitForExecutionAttemptResult(
  page: Page,
  executionIdInput: Locator,
  timeoutMs = 25_000,
): Promise<'success' | 'retry' | 'timeout'> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const value = await executionIdInput.inputValue().catch(() => '');
    if (/exec_/.test(value)) {
      return 'success';
    }

    const transientError = await page.getByText('Failed to fetch').isVisible().catch(() => false);
    if (transientError) {
      return 'retry';
    }

    await page.waitForTimeout(500);
  }

  return 'timeout';
}

test('should complete P0-P1 workbench flows without critical regressions', async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  const performanceStatuses: number[] = [];

  page.on('response', (response) => {
    if (response.url().includes('/api/paper-trading/performance')) {
      performanceStatuses.push(response.status());
    }
  });

  const viewName = `事件回归-${Date.now()}`;
  const artifactId = `art_pw_exec_${Date.now()}`;

  await openProtectedPage(page, '/events?code=000001&days=7&type=all');
  await expect(page).toHaveURL(/\/events(?:\?.*)?$/);
  await expect(page.getByRole('heading', { name: '事件日历', level: 1 })).toBeVisible();
  await expect(page.getByText('订阅标的', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: '收起 Copilot', exact: true })).toBeVisible();

  await page.getByPlaceholder('events 视图').fill(viewName);
  await page.getByRole('button', { name: '保存当前视图', exact: true }).click();
  await expect(page.getByRole('button', { name: viewName, exact: true })).toBeVisible();

  await page.getByRole('button', { name: '双栏', exact: true }).click();
  await expect(page.getByRole('heading', { name: '事件订阅' })).toBeVisible();

  await page.getByRole('button', { name: '执行中心', exact: true }).click();
  await expect(page).toHaveURL(/\/execution(?:\?.*)?$/);
  await dismissOnboarding(page);
  await expect(page.getByRole('heading', { name: '执行中心' })).toBeVisible();
  await page.waitForTimeout(1_500);

  const executionForm = page.locator('form').filter({
    has: page.getByRole('button', { name: '提交执行' }),
  }).first();
  await executionForm.getByLabel('股票代码').fill('000001');
  await executionForm.getByLabel('数量').fill('200');
  await executionForm.getByPlaceholder('可选，用于任务编排追踪').fill(artifactId);
  const executionStatusForm = page.locator('form').filter({
    has: page.getByRole('button', { name: '查询状态' }),
  }).first();
  const executionIdInput = executionStatusForm.getByLabel('execution_id');

  let executionSubmitted = false;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await executionForm.getByRole('button', { name: '提交执行' }).click();
    const outcome = await waitForExecutionAttemptResult(page, executionIdInput);
    if (outcome === 'success') {
      executionSubmitted = true;
      break;
    }
    if (attempt === 2 || outcome === 'timeout') {
      await expect(executionIdInput).toHaveValue(/exec_/, { timeout: 5_000 });
    } else {
      await page.waitForTimeout(1_000);
    }
  }
  expect(executionSubmitted).toBe(true);

  await expect(page.getByText('最近一次执行返回')).toBeVisible();
  await expect(page.getByRole('heading', { name: '执行复盘摘要' })).toBeVisible();
  await expect(page.getByText('Artifact 关联执行')).toBeVisible();
  await expect(page.getByRole('button', { name: '打开 artifact 详情页', exact: true })).toBeVisible();

  await Promise.all([
    page.waitForURL(/\/execution\/artifacts\/art_pw_exec_/),
    page.getByRole('button', { name: '打开 artifact 详情页', exact: true }).click(),
  ]);

  await dismissOnboarding(page);
  await expect(page.getByRole('heading', { name: 'Artifact 详情' })).toBeVisible();
  await expect(page.getByText('Artifact 摘要')).toBeVisible();
  await expect(page.getByRole('button', { name: '执行中心', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '执行中心', exact: true }).click();
  await expect(page).toHaveURL(/\/execution\?(?=.*artifact_id=art_pw_exec_).*/);
  await expect(page.getByRole('heading', { name: '执行中心' })).toBeVisible();

  await Promise.all([
    page.waitForURL(/\/performance\?(?=.*mode=account)(?=.*execution_id=exec_).*/, { timeout: 20_000 }),
    page.waitForResponse((response) => (
      response.url().includes('/api/paper-trading/performance') && response.status() === 200
    ), { timeout: 20_000 }),
    page.getByRole('button', { name: '打开绩效复盘', exact: true }).click(),
  ]);

  await dismissOnboarding(page);
  await expect(page.getByRole('heading', { name: '绩效中心' })).toBeVisible();
  await expect(page.getByText(/来源执行任务：exec_/)).toBeVisible();
  await expect(page.getByRole('tab', { name: '组合归因' })).toBeVisible();
  expect(performanceStatuses.filter((status) => status >= 400)).toHaveLength(0);

  await page.getByRole('tab', { name: '组合归因' }).click();
  await expect(page).toHaveURL(/\/performance\?(?=.*mode=portfolio)(?=.*portfolio_id=).*/);
  await expect(page.getByText('收益归因拆解')).toBeVisible();

  await openProtectedPage(page, '/screener');
  await expect(page).toHaveURL(/\/screener$/);
  await expect(page.getByRole('heading', { name: '条件选股' })).toBeVisible();

  await page.getByRole('button', { name: '高股息银行股', exact: true }).click();
  await page.getByRole('button', { name: '开始筛选', exact: true }).click();
  await expect(page.getByText(/筛选结果（\d+ 只）/)).toBeVisible();

  const firstResultRow = page.locator('tbody tr').first();
  const firstWatchHref = await firstResultRow.getByRole('link').first().getAttribute('href');
  const firstWatchCode = firstWatchHref
    ? new URL(firstWatchHref, 'http://127.0.0.1').searchParams.get('code') ?? ''
    : '';
  expect(firstWatchCode).toMatch(/^\d{6}$/);

  const firstWatchButton = page.getByRole('button', { name: '☆' }).first();
  await firstWatchButton.click();
  await expect(page.getByRole('button', { name: '★' }).first()).toBeVisible();

  await page.getByRole('tab', { name: '条件组合' }).click();
  await page.getByRole('button', { name: '市盈率 < 20', exact: true }).click();
  await page.getByRole('button', { name: '执行筛选', exact: true }).click();
  await expect(page.getByText(/筛选结果（\d+ 只）/)).toBeVisible();

  await page.getByRole('button', { name: 'AI 分析结果', exact: true }).click();
  await expect(page.getByLabel('AI 输入框')).toContainText('请帮我分析筛选结果');
  await page.getByRole('button', { name: '打开自选股', exact: true }).click();

  await expect(page).toHaveURL(/\/watchlist$/);
  await dismissOnboarding(page);
  await expect(page.getByRole('heading', { name: /我的自选/ })).toBeVisible();
  await expect(page.getByText(firstWatchCode).first()).toBeVisible();

  await openProtectedPage(page, '/strategy-market');
  await expect(page).toHaveURL(/\/strategy-market$/);
  await dismissOnboarding(page);
  await expect(page.getByRole('heading', { name: '策略超市' })).toBeVisible();
  await expect(page.getByText('工厂摘要')).toBeVisible();
  await expect(page.getByRole('link', { name: /质量优选·前57%/ }).first()).toBeVisible();

  await page.getByRole('button', { name: '+ 加入组合' }).first().click();
  await page.getByRole('button', { name: /组合购物车/ }).click();
  await expect(page.getByRole('dialog', { name: '组合购物车' })).toBeVisible();
  await page.getByRole('button', { name: '等权分配', exact: true }).click();
  await expect(page.getByText('权重合计: 100.0%')).toBeVisible();
  await page.getByPlaceholder('组合名称（可选）').fill(`策略组合-${Date.now()}`);
  await page.getByRole('button', { name: '创建策略组合', exact: true }).click();
  await expect(page.getByRole('button', { name: /组合购物车/ })).toBeVisible();

  await page.getByRole('link', { name: /质量优选·前57% quality_factor/ }).first().click();
  await expect(page).toHaveURL(/\/strategy-market\/factory_/);
  await expect(page.getByRole('heading', { name: '质量优选·前57%' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '策略概览' })).toBeVisible();

  const subscribeButton = page.getByRole('button', { name: /订阅策略|取消订阅/ });
  const subscribeLabel = await subscribeButton.textContent();
  await subscribeButton.click();
  await expect(page.getByRole('button', { name: subscribeLabel?.includes('取消') ? '订阅策略' : '取消订阅' })).toBeVisible();

  consoleErrors.dispose();
  expect(consoleErrors.messages.filter((message) => message.includes('/api/paper-trading/performance'))).toHaveLength(0);
});
