import { expect, type Page } from '@playwright/test';
import { MarketPageObject } from '../pages/market.page';
import { clickVisibleTab, expectAnyVisible } from '../support/assertions';

export async function runMarketWorkflow(page: Page) {
  const market = new MarketPageObject(page);

  await page.goto('/market');
  await market.openIndexTab();
  await page.getByLabel('指数代码').fill('000300');
  await page.getByRole('button', { name: '查询指数行情', exact: true }).click();
  await expect(page.getByText('指数名称')).toBeVisible({ timeout: 20_000 });

  await market.searchKeyword('平安');
  await expectAnyVisible([
    page.getByText(/平安银行|中国平安/).first(),
    page.getByRole('button', { name: /加载全市场列表|加载全部股票列表/ }),
  ]);

  await market.batchQuotes('000001,600519');
  await expect(page.getByRole('table').last().locator('tbody tr')).toHaveCount(2, { timeout: 20_000 });

  await page.goto('/stock');
  await page.getByRole('textbox', { name: '股票代码' }).fill('000001');
  await page.getByRole('button', { name: '立即查询股票', exact: true }).click();
  await expect(page.getByRole('heading', { name: /000001|平安银行/ }).first()).toBeVisible({ timeout: 20_000 });

  await clickVisibleTab(page, ['估值']);
  await expectAnyVisible([
    page.getByText(/PE|市盈率/),
    page.getByText('查询股票后显示估值数据'),
  ]);

  await clickVisibleTab(page, ['资讯']);
  await expectAnyVisible([
    page.getByRole('heading', { name: '最新资讯' }),
    page.getByText(/研报|公告|新闻/).first(),
  ]);
}

export async function runStockAnalysisWorkflow(page: Page) {
  await page.goto('/stock');
  await page.getByRole('textbox', { name: '股票代码' }).fill('000001');
  await page.getByRole('button', { name: '立即查询股票', exact: true }).click();
  await expect(page.getByRole('heading', { name: /000001|平安银行/ }).first()).toBeVisible({ timeout: 20_000 });

  await clickVisibleTab(page, ['技术面']);
  await expectAnyVisible([
    page.getByText('MACD'),
    page.getByText('查询股票后显示技术指标'),
  ]);

  await clickVisibleTab(page, ['资金流']);
  await expectAnyVisible([
    page.getByText('净流入'),
    page.getByText('暂无资金流向数据'),
  ]);

  await clickVisibleTab(page, ['估值']);
  await expectAnyVisible([
    page.getByText(/PE|市盈率/),
    page.getByText('查询股票后显示估值数据'),
  ]);

  await clickVisibleTab(page, ['资讯']);
  await expectAnyVisible([
    page.getByRole('heading', { name: '最新资讯' }),
    page.getByText(/研报|公告|新闻/).first(),
  ]);
}

export async function runDataCenterWorkflow(page: Page) {
  await page.goto('/data');
  await page.getByRole('button', { name: '查询期权链工作台', exact: true }).click();
  await expectAnyVisible([
    page.getByRole('columnheader', { name: '行权价', exact: true }),
    page.getByText('无期权数据', { exact: true }),
  ]);

  await clickVisibleTab(page, ['交易日历']);
  await page.getByRole('button', { name: '加载交易日历工作台', exact: true }).click();
  await expectAnyVisible([
    page.getByRole('columnheader', { name: '交易日', exact: true }),
    page.getByText('无交易日历数据', { exact: true }),
  ]);

  await clickVisibleTab(page, ['IPO']);
  await page.getByRole('button', { name: '查询IPO信息工作台', exact: true }).click();
  await expectAnyVisible([
    page.getByRole('columnheader', { name: '发行价', exact: true }),
    page.getByText(/无 ?IPO ?数据/),
  ]);
}

export async function runBacktestWorkflow(page: Page) {
  await page.goto('/backtest?code=600519&from=realworld-e2e');
  await page.locator('#backtest-stock-code').fill('600519');
  await page.getByRole('button', { name: '运行回测' }).click();
  await expectAnyVisible([
    page.getByText('回测制品'),
    page.getByText('收益'),
    page.getByText(/历史 K 线不足|回测运行失败|上游回测服务暂时不可用/),
  ], 40_000);

  await page.getByLabel('股票代码（逗号分隔）').fill('600519,000001');
  await page.getByRole('button', { name: '批量回测', exact: true }).click();
  await expectAnyVisible([
    page.getByText('批量回测对比'),
    page.getByText(/股票代码|总收益/),
  ], 40_000);
}
