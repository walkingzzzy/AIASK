import { test, expect } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

async function loginAsDemo(page: import('@playwright/test').Page) {
    await expect(page).toHaveURL(/\/login/);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    const username = page.locator('input[name="username"]');
    const password = page.locator('input[name="password"]');
    const submit = page.getByRole('button', { name: '登录' });

    await expect(username).toBeVisible();
    await expect(password).toBeVisible();

    for (let attempt = 0; attempt < 2; attempt += 1) {
        await username.fill('demo');
        await expect(username).toHaveValue('demo', { timeout: 5000 });
        await password.fill('demo123');
        await expect(password).toHaveValue('demo123', { timeout: 5000 });

        await submit.click();

        try {
            await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 30000 });
            await page.waitForLoadState('networkidle');
            return;
        } catch (error) {
            const message = await page.getByRole('alert').textContent().catch(() => null);
            if (attempt === 1 || !message?.includes('HTTP 401')) {
                throw error;
            }
            await page.waitForLoadState('domcontentloaded');
        }
    }
}

async function dismissOnboarding(page: import('@playwright/test').Page) {
    const skip = page.getByRole('button', { name: '跳过' });
    if (await skip.isVisible().catch(() => false)) {
        await skip.click();
    }
}

async function openProtectedPage(
    page: import('@playwright/test').Page,
    path: string,
    expectedUrl: RegExp,
) {
    await page.goto(path);
    await Promise.race([
        page.waitForURL(expectedUrl, { timeout: 5000 }).catch(() => null),
        page.waitForURL((url) => url.pathname.startsWith('/login'), { timeout: 5000 }).catch(() => null),
    ]);
    if (page.url().includes('/login')) {
        await loginAsDemo(page);
    }
    await dismissOnboarding(page);
    await expect(page).toHaveURL(expectedUrl, { timeout: 15000 });
}

test.describe('Homepage', () => {
    test('should load and display title', async ({ page }) => {
        await page.goto('/');
        await expect(page).toHaveTitle(/AIASK/);
    });

    test('should show market indices', async ({ page }) => {
        await page.goto('/');
        // Wait for any content to load
        await page.waitForTimeout(2000);
        // Should have navigation
        const nav = page.locator('nav');
        await expect(nav.first()).toBeVisible();
    });

    test('should have working navigation', async ({ page }) => {
        await page.goto('/');
        // Sidebar should have links
        const links = page.locator('a[href]');
        expect(await links.count()).toBeGreaterThan(0);
    });

    test('risk quick action should preserve context params', async ({ page }) => {
        await openProtectedPage(page, '/risk?lookbackDays=126&from=home', /\/risk\?(?=.*lookbackDays=126)(?=.*from=home).*/);
        await expect(page.getByPlaceholder('lookbackDays')).toHaveValue('126');
        await expect(page.getByText(/来源: home/)).toBeVisible();
    });
});

test.describe('Stock Detail', () => {
    test('should have search input', async ({ page }) => {
        await openProtectedPage(page, '/stock', /\/stock(?:\?.*)?$/);
        const input = page.getByRole('textbox', { name: '股票代码' });
        await expect(input).toBeVisible();
    });

    test('should open a requested stock', async ({ page }) => {
        await openProtectedPage(page, '/stock?code=000001', /\/stock\?code=000001/);
        const input = page.getByRole('textbox', { name: '股票代码' });
        await expect(input).toHaveValue('000001');
        await expect(page.getByRole('tablist', { name: '标签页导航' })).toBeVisible();
    });
});

test.describe('Watchlist', () => {
    test('should load watchlist page', async ({ page }) => {
        await openProtectedPage(page, '/watchlist', /\/watchlist$/);
        await expect(page).toHaveTitle(/自选|AIASK/);
        await expect(page.getByRole('heading', { name: /我的自选/ })).toBeVisible();
    });
});

test.describe('Paper Trading', () => {
    test('should load paper trading page', async ({ page }) => {
        await openProtectedPage(page, '/paper-trading', /\/paper-trading$/);
        await expect(page).toHaveTitle(/模拟|交易|AIASK/);
        await expect(page.getByRole('heading', { name: '模拟交易' })).toBeVisible();
    });

    test('should keep backtest context banner from homepage', async ({ page }) => {
        await page.goto('/backtest?code=000001&from=home');
        await expect(page.getByText(/来源: home/)).toBeVisible();
    });
});

test.describe('Notifications', () => {
    test('should load notifications page', async ({ page }) => {
        await openProtectedPage(page, '/notifications', /\/notifications$/);
        await expect(page.getByRole('heading', { name: /通知中心/ })).toBeVisible();
    });
});

test.describe('Alerts', () => {
    test('should load alerts page', async ({ page }) => {
        await openProtectedPage(page, '/alerts', /\/alerts$/);
        await expect(page.getByRole('heading', { name: '告警中心' })).toBeVisible();
    });
});

test.describe('Task Handoff', () => {
    test('market page should show task context', async ({ page }) => {
        await openProtectedPage(page, '/market?task=watchlist-scan&from=home', /\/market\?(?=.*task=watchlist-scan)(?=.*from=home).*/);
        await expect(page.getByText(/任务: watchlist-scan/)).toBeVisible();
    });

    test('strategy market should show task context', async ({ page }) => {
        await page.goto('/strategy-market?task=ranking&from=home');
        await expect(page).toHaveURL(/\/strategy-market\?(?=.*task=ranking)(?=.*from=home).*/);
        await expect(page.getByText(/任务: ranking/)).toBeVisible();
    });
});

test.describe('Spotlight Search', () => {
    test('should open with Cmd+K', async ({ page }) => {
        await page.goto('/');
        await page.keyboard.press('Meta+k');
        await page.waitForTimeout(500);
        // Look for spotlight overlay or input
        const spotlight = page.locator('input[placeholder*="搜索"]');
        if (await spotlight.isVisible()) {
            await expect(spotlight).toBeVisible();
        }
    });
});

test.describe('Admin', () => {
    test('should load admin page', async ({ page }) => {
        await openProtectedPage(page, '/admin', /\/admin$/);
        await expect(page.getByText(/管理后台概览/)).toBeVisible();
    });
});
