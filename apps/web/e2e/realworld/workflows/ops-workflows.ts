import { expect, type Page } from '@playwright/test';
import { expectAnyVisible } from '../support/assertions';

export async function runAlertWorkflow(page: Page) {
  const stockCode = `000001`;
  await page.goto('/alerts');
  await page.locator('#alerts-stock-code').fill(stockCode);
  await page.locator('#alerts-indicator').fill('price');
  await page.locator('#alerts-condition').selectOption('>');
  await page.locator('#alerts-threshold').fill('12');
  await page.getByRole('button', { name: '创建告警' }).click();
  await page.getByRole('button', { name: '确认创建' }).click();
  await expect(page.getByText(new RegExp(`${stockCode}\\s*·\\s*price\\s*>\\s*12`)).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: '删除' }).first().click();
  await page.getByRole('button', { name: '确认删除' }).click();
}

export async function runWatchlistWorkflow(page: Page, groupName: string) {
  await page.goto('/watchlist');
  await page.getByRole('button', { name: '新建分组' }).click();
  await page.getByPlaceholder('分组名称').fill(groupName);
  await page.getByRole('button', { name: '创建分组' }).click();
  await expect(page.getByRole('button', { name: new RegExp(groupName) })).toBeVisible({ timeout: 20_000 });

  await page.locator('#watchlist-search').fill('平安');
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  await expect(page.getByRole('button', { name: /\+ 添加/ }).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole('button', { name: /\+ 添加/ }).first().click();
  await expect(page.getByText(/000001|平安银行/).first()).toBeVisible({ timeout: 20_000 });
}

export async function runNotificationWorkflow(page: Page) {
  await page.goto('/notifications');
  await page.getByRole('button', { name: /告警|交易|系统|资讯/ }).first().click();

  if (await page.getByRole('button', { name: /全部标记已读/ }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: /全部标记已读/ }).click();
  }

  if (await page.getByRole('button', { name: /选中当前筛选|取消全选当前筛选/ }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: /选中当前筛选|取消全选当前筛选/ }).click();
    if (await page.getByRole('button', { name: /批量删除/ }).isEnabled().catch(() => false)) {
      await page.getByRole('button', { name: /批量删除/ }).click();
    }
  }

  await expectAnyVisible([
    page.getByText(/通知流与逐条处理区|当前筛选已清空|条待处理/),
    page.getByText(/暂无.*通知/),
  ]);
}

export async function runAdminCacheWorkflow(page: Page) {
  await page.goto('/admin/cache');
  await page.getByRole('button', { name: /清除全部缓存/ }).click();
  await page.getByLabel(/我已知晓全量清理/).check();
  await page.getByRole('button', { name: '确认清理' }).click();
  await expect(page.getByText('缓存已清理')).toBeVisible({ timeout: 20_000 });
}

export async function runAdminDeadLettersWorkflow(page: Page) {
  await page.goto('/admin/dead-letters');
  await expectAnyVisible([
    page.getByText('待处理死信'),
    page.getByText('当前没有待处理死信'),
  ]);

  if (await page.getByRole('button', { name: /🔄 重试|重试中/ }).first().isVisible().catch(() => false)) {
    await page.getByRole('button', { name: /🔄 重试|重试中/ }).first().click();
    await expectAnyVisible([
      page.getByText('死信已重试'),
      page.getByText(/待处理死信|当前没有待处理死信/),
    ], 25_000);
  }

  if (await page.getByRole('button', { name: '清除全部' }).isVisible().catch(() => false)) {
    await page.getByRole('button', { name: '清除全部' }).click();
    await expectAnyVisible([
      page.getByText('死信队列已清空'),
      page.getByText('当前没有待处理死信'),
    ], 20_000);
  }
}
