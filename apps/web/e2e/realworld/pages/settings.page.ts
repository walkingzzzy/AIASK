import { expect, type Page } from '@playwright/test';

export class SettingsPageObject {
  constructor(private readonly page: Page) {}

  private async clickUntilResponse(
    buttonName: string,
    matcher: (url: string, method: string, status: number) => boolean,
    attempts = 3,
  ) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const responsePromise = this.page.waitForResponse(
        (response) => matcher(response.url(), response.request().method(), response.status()),
        { timeout: 3_000 },
      ).catch(() => null);

      await this.page.getByRole('button', { name: buttonName, exact: true }).click();
      const response = await responsePromise;
      if (response) {
        return response;
      }

      await this.page.waitForTimeout(500);
    }

    throw new Error(`missing response for ${buttonName}`);
  }

  async openTab(name: string) {
    await this.page.getByRole('tab', { name }).click();
  }

  async waitForProfileReady() {
    await this.openTab('账户信息');
    await expect(this.page.locator('#settings-nickname')).toBeEnabled({ timeout: 20_000 });
    await expect(this.page.locator('#settings-risk-level')).toBeEnabled({ timeout: 20_000 });
    await expect(this.page.getByRole('button', { name: '保存资料', exact: true })).toBeEnabled({ timeout: 20_000 });
  }

  async saveProfile(nickname: string, riskLevel: string) {
    await this.waitForProfileReady();
    const nicknameInput = this.page.locator('#settings-nickname');
    const riskLevelSelect = this.page.locator('#settings-risk-level');

    await expect(nicknameInput).toBeVisible();
    await expect(riskLevelSelect).toHaveValue(/保守|稳健|激进/, { timeout: 20_000 });

    await nicknameInput.fill(nickname);
    await expect(nicknameInput).toHaveValue(nickname);

    await riskLevelSelect.selectOption(riskLevel);
    await expect(riskLevelSelect).toHaveValue(riskLevel);

    await this.clickUntilResponse(
      '保存资料',
      (url, method, status) => url.includes('/api/auth/profile') && method === 'POST' && status < 400,
    );
  }

  async openSessionsTab() {
    await this.openTab('活跃会话');
    await expect
      .poll(async () => {
        const locators = [
          this.page.getByRole('table'),
          this.page.getByText('暂无活跃会话', { exact: true }),
          this.page.getByText(/活跃总数：\d+/),
        ];

        for (const locator of locators) {
          if (await locator.first().isVisible().catch(() => false)) {
            return true;
          }
        }

        return false;
      })
      .toBe(true);
  }

  async generateReport() {
    await this.clickUntilResponse(
      '生成投资报告',
      (url, method, status) => url.includes('/api/export/report') && method === 'GET' && status < 400,
    );
  }

  async changePassword(oldPassword: string, newPassword: string) {
    await this.waitForProfileReady();
    await this.page.locator('#settings-old-password').fill(oldPassword);
    await this.page.locator('#settings-new-password').fill(newPassword);
    await this.page.locator('#settings-confirm-password').fill(newPassword);
    await this.clickUntilResponse(
      '修改密码',
      (url, method, status) => url.includes('/api/auth/change-password') && method === 'POST' && status < 400,
    );
  }
}
