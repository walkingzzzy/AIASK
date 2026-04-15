import { expect, type Page } from '@playwright/test';

export class PaperTradingPageObject {
  constructor(private readonly page: Page) {}

  async loadExample(code: '600519' | '000001' = '600519') {
    const buttonName = code === '600519' ? '载入茅台示例' : '载入平安银行示例';
    await expect(this.page.getByRole('button', { name: buttonName }).first()).toBeVisible();
    await this.page.getByRole('button', { name: buttonName }).first().click();
  }

  async enableSmartRouting(enabled = true) {
    const checkbox = this.page.locator('#paper-order-urgent-execution');
    if ((await checkbox.isChecked()) !== enabled) {
      await checkbox.click();
    }
  }

  async submitOrder() {
    await expect(
      this.page.getByRole('button', { name: /确认买入|确认卖出/ }),
    ).toBeVisible();
    await this.page.getByRole('button', { name: /确认买入|确认卖出/ }).click();

    const confirmButton = this.page.getByRole('button', { name: '确认下单', exact: true });
    if (await confirmButton.isVisible().catch(() => false)) {
      await confirmButton.click();
    }
  }

  async cancelFirstPendingOrder() {
    await expect(this.page.getByRole('button', { name: '撤单' }).first()).toBeVisible();
    await this.page.getByRole('button', { name: '撤单' }).first().click();
    await this.page.getByRole('button', { name: '确认撤单' }).click();
  }
}
