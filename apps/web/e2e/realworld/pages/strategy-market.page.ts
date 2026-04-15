import { expect, type Page } from '@playwright/test';

export class StrategyMarketPageObject {
  constructor(private readonly page: Page) {}

  async addFirstStrategyToCart() {
    await expect(this.page.getByRole('button', { name: /(?:\+ )?加入组合/ }).first()).toBeVisible();
    await this.page.getByRole('button', { name: /(?:\+ )?加入组合/ }).first().click();
  }

  async openCart() {
    await this.page.getByRole('button', { name: /组合购物车/ }).click();
    await expect(this.page.getByRole('dialog', { name: '组合购物车' })).toBeVisible();
  }

  async createPortfolioFromCart(name: string) {
    await this.openCart();
    await this.page.getByRole('button', { name: '等权分配', exact: true }).click();
    await this.page.getByPlaceholder('组合名称（可选）').fill(name);
    await this.page.getByRole('button', { name: '创建策略组合', exact: true }).click();
  }

  async firstDetailHref() {
    const href = await this.page.locator('a[href^="/strategy-market/"]').evaluateAll((nodes) => {
      for (const node of nodes) {
        const candidate = node.getAttribute('href');
        if (candidate && /^\/strategy-market\/[^/?#]+(?:\?.*)?$/.test(candidate) && candidate !== '/strategy-market') {
          return candidate;
        }
      }
      return null;
    });

    if (!href) {
      throw new Error('strategy detail href not found');
    }
    return href;
  }
}
