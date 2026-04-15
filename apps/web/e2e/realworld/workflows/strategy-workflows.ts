import { expect, type Page } from '@playwright/test';
import { PaperTradingPageObject } from '../pages/paper-trading.page';
import { StrategyMarketPageObject } from '../pages/strategy-market.page';
import { expectAnyVisible } from '../support/assertions';

export async function runPaperTradingWorkflow(page: Page) {
  const paper = new PaperTradingPageObject(page);

  await page.goto('/paper-trading');
  await paper.loadExample('600519');
  await paper.enableSmartRouting(true);
  await paper.submitOrder();
  await expectAnyVisible([
    page.getByText('智能路由订单已提交'),
    page.getByText('订单已提交'),
    page.getByText(/正在通过智能路由提交订单|正在提交订单/),
  ], 30_000);

  if (await page.getByRole('button', { name: '撤单' }).first().isVisible().catch(() => false)) {
    await paper.cancelFirstPendingOrder();
    await expect(page.getByText(/已撤销/)).toBeVisible({ timeout: 20_000 });
  }
}

export async function runPerformanceWorkflow(page: Page, accountId: string, portfolioId: string) {
  await page.goto(`/performance?mode=account&account_id=${encodeURIComponent(accountId)}&days=30`);
  await expect(page.getByRole('tab', { name: '账户绩效' })).toBeVisible();
  await page.getByRole('tab', { name: '组合归因' }).click();
  await expect(page).toHaveURL(new RegExp(`portfolio_id=${portfolioId}`));
  await expectAnyVisible([
    page.getByText('收益归因拆解'),
    page.getByText('组合归因'),
  ]);
  await page.getByRole('tab', { name: '账户绩效' }).click();
}

export async function runStrategyMarketWorkflow(page: Page) {
  const market = new StrategyMarketPageObject(page);

  await page.goto('/strategy-market');
  await market.addFirstStrategyToCart();
  await market.createPortfolioFromCart(`E2E策略组合-${Date.now()}`);
  await expect(page.getByRole('button', { name: /组合购物车/ })).toBeVisible({ timeout: 20_000 });
}

export async function runStrategyDetailWorkflow(page: Page, strategyRoute: string) {
  await page.goto(strategyRoute);
  await expect(page.getByRole('tab', { name: '策略概览' })).toBeVisible();
  await page.getByRole('button', { name: /策略头图(?:取消订阅|订阅策略)/ }).click();
  await expectAnyVisible([
    page.getByRole('button', { name: /策略头图订阅策略|策略头图取消订阅/ }),
    page.getByRole('button', { name: /立即订阅|取消订阅/ }),
  ]);

  await page.getByRole('tab', { name: '工厂审查' }).click();
  await expect(page.getByRole('tab', { name: '工厂摘要' })).toBeVisible();
  await page.getByRole('tab', { name: '运行风控' }).click();
  await expectAnyVisible([
    page.getByText('运行风控'),
    page.getByText('暂无'),
  ]);
}
