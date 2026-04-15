import { expect, type Page } from '@playwright/test';
import { dismissOnboarding } from '../../helpers/app';
import { SettingsPageObject } from '../pages/settings.page';
import { generateTotp } from '../support/totp';

const BFF_BASE_URL = process.env.E2E_BFF_BASE_URL || 'http://127.0.0.1:3401/api';

export async function registerThroughUi(page: Page, username: string, password: string) {
  await page.goto('/register');
  await page.locator('#reg-username').fill(username);
  await page.locator('#reg-password').fill(password);
  await page.locator('#reg-confirm').fill(password);
  await page.getByRole('button', { name: '创建账号' }).click();
  await dismissOnboarding(page);
}

export async function loginThroughUi(page: Page, username: string, password: string, redirect = '/market') {
  await page.goto(`/login?redirect=${encodeURIComponent(redirect)}`);
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
  await dismissOnboarding(page);
}

async function clickUntilApiResponse(
  page: Page,
  trigger: () => Promise<void>,
  matcher: (url: string, method: string, status: number) => boolean,
  attempts = 3,
) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const responsePromise = page.waitForResponse(
      (response) => matcher(response.url(), response.request().method(), response.status()),
      { timeout: 3_000 },
    ).catch(() => null);

    await trigger();
    const response = await responsePromise;
    if (response) {
      return response;
    }

    await page.waitForTimeout(500);
  }

  throw new Error('missing expected api response');
}

async function expectProfileState(page: Page, expected: { nickname: string; riskLevel: string }, timeout = 20_000) {
  await expect
    .poll(async () => {
      const result = await page.evaluate(async (profileUrl) => {
        const response = await fetch(profileUrl, {
          credentials: 'include',
          headers: { accept: 'application/json' },
        });
        const payload = await response.json().catch(() => null);
        return {
          ok: response.ok,
          payload,
        };
      }, `${BFF_BASE_URL}/auth/profile`);
      if (!result?.ok) {
        return null;
      }
      const data = (result?.payload?.data ?? result?.payload ?? {}) as { nickname?: string | null; riskLevel?: string | null };
      return {
        nickname: data.nickname ?? '',
        riskLevel: data.riskLevel ?? '',
      };
    }, { timeout })
    .toEqual(expected);
}

export async function runLoginLifecycleWorkflow(page: Page, username: string, password: string) {
  await loginThroughUi(page, username, password, '/settings');
  await expect(page).toHaveURL(/\/settings(?:\?.*)?$/);

  await page.getByRole('button', { name: '退出', exact: true }).click();
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/);

  await page.goto('/settings');
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/);
}

export async function runSettingsWorkflow(page: Page, username: string, password: string) {
  const settings = new SettingsPageObject(page);
  const newPassword = `${password}-next`;
  const nickname = `E2E-${Date.now()}`;

  await page.goto('/settings');
  if (/\/login(?:\?|$)/.test(page.url())) {
    await loginThroughUi(page, username, password, '/settings');
  } else {
    await dismissOnboarding(page);
  }
  await settings.waitForProfileReady();
  await settings.saveProfile(nickname, '激进');
  await expectProfileState(page, { nickname, riskLevel: '激进' });

  await settings.generateReport();
  await expect(page.locator('pre').filter({ hasText: '投资报告' })).toBeVisible({ timeout: 20_000 });

  await settings.openSessionsTab();
  await settings.changePassword(password, newPassword);
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/);

  await loginThroughUi(page, username, newPassword, '/settings');
  await settings.waitForProfileReady();
  await expectProfileState(page, { nickname, riskLevel: '激进' });
}

export async function runTwoFactorWorkflow(page: Page, username: string, password: string) {
  await page.goto('/settings/security');
  if (/\/login(?:\?|$)/.test(page.url())) {
    await loginThroughUi(page, username, password, '/settings/security');
  } else {
    await dismissOnboarding(page);
  }
  await expect(page.getByRole('button', { name: /启用 2FA|关闭 2FA/ })).toBeVisible({ timeout: 20_000 });
  await clickUntilApiResponse(
    page,
    async () => {
      await page.getByRole('button', { name: /启用 2FA/ }).click();
    },
    (url, method, status) => url.includes('/api/auth/2fa/setup') && method === 'POST' && status < 400,
  );
  await expect(page.locator('code').first()).toBeVisible({ timeout: 20_000 });
  const secret = await page.locator('code').first().textContent();
  if (!secret) {
    throw new Error('missing TOTP secret');
  }
  await page.getByPlaceholder('000000').fill(generateTotp(secret));
  await clickUntilApiResponse(
    page,
    async () => {
      await page.getByRole('button', { name: '验证' }).click();
    },
    (url, method, status) => url.includes('/api/auth/2fa/verify') && method === 'POST' && status < 400,
  );
  await expect(page.getByText('双因素认证已启用')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole('button', { name: '关闭 2FA' })).toBeVisible();
  await clickUntilApiResponse(
    page,
    async () => {
      await page.getByRole('button', { name: '关闭 2FA' }).click();
    },
    (url, method, status) => url.includes('/api/auth/2fa/disable') && method === 'POST' && status < 400,
  );
  await expect(page.getByText('双因素认证已关闭')).toBeVisible({ timeout: 20_000 });
}
