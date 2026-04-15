import { expect, type Page } from '@playwright/test';

export class MarketPageObject {
  constructor(private readonly page: Page) {}

  async openSearchTab() {
    await this.page.getByRole('tab', { name: '搜索' }).click();
    await expect(this.page.getByLabel('搜索关键词')).toBeVisible();
  }

  async searchKeyword(keyword: string) {
    await this.openSearchTab();
    await this.page.getByLabel('搜索关键词').fill(keyword);
    await this.page.getByRole('button', { name: '搜索', exact: true }).click();
  }

  async batchQuotes(codes: string) {
    await this.page.getByLabel('批量股票代码').fill(codes);
    await this.page.getByRole('button', { name: '批量行情', exact: true }).click();
  }

  async openIndexTab() {
    await this.page.getByRole('tab', { name: '指数' }).click();
    await expect(this.page.getByLabel('指数代码')).toBeVisible();
  }
}
