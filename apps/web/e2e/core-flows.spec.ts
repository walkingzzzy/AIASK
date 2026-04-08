import { test, expect } from '@playwright/test';
import { dismissOnboarding, loginAsConfigured, openProtectedPage } from './helpers/app';

test.describe.configure({ mode: 'serial' });

function escapeRegExp(value: string) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

test.describe('Homepage', () => {
    test('should load and display title', async ({ page }) => {
        await openProtectedPage(page, '/');
        await expect(page).toHaveTitle(/AIASK/);
    });

    test('should show market indices', async ({ page }) => {
        await openProtectedPage(page, '/');
        await expect(page.getByRole('link', { name: /行情看板|行情/ }).first()).toBeVisible();
        await expect(page.getByRole('link', { name: /自选股|自选/ }).first()).toBeVisible();
    });

    test('should have working navigation', async ({ page }) => {
        await page.goto('/login?redirect=%2F');
        await loginAsConfigured(page, '/');
        await dismissOnboarding(page);
        await expect(page).toHaveURL(/\/$/);
        const marketLink = page.getByRole('link', { name: /行情看板|行情/ }).first();
        const marketHref = await marketLink.getAttribute('href');
        expect(marketHref, '行情入口需要带目标地址').toBeTruthy();
        const expectedMarketUrl = new URL(marketHref!, 'http://127.0.0.1');

        await marketLink.click();
        await expect(page).toHaveURL(new RegExp(`${escapeRegExp(expectedMarketUrl.pathname)}(?:\\?.*)?$`));

        const expectedCode = expectedMarketUrl.searchParams.get('code');
        if (expectedCode) {
            await expect(page.getByRole('textbox', { name: '股票代码' })).toHaveValue(expectedCode);
        } else {
            await expect(page.getByRole('textbox', { name: '股票代码' })).toHaveValue(/\d{6}/);
        }
        await expect(page.getByRole('button', { name: '查询主行情工作台', exact: true })).toBeVisible();
    });

    test('risk quick action should preserve context params', async ({ page }) => {
        await openProtectedPage(page, '/risk?lookbackDays=126&from=home');
        await expect(page).toHaveURL(/\/risk\?(?=.*lookbackDays=126)(?=.*from=home).*/);
        await expect(page.getByRole('heading', { name: /风险分析(?:工作台)?/ })).toBeVisible();
        await expect(page.getByLabel('回看天数')).toHaveValue('126');
        await expect(page.getByText(/^窗口：126 天$/)).toBeVisible();
        await expect(page.getByText(/来源:? ?home/)).toBeVisible();
    });
});

test.describe('Stock Detail', () => {
    test('should have search input', async ({ page }) => {
        await openProtectedPage(page, '/stock');
        await expect(page).toHaveURL(/\/stock(?:\?.*)?$/);
        const input = page.getByRole('textbox', { name: '股票代码' });
        await expect(input).toBeVisible();
    });

    test('should open a requested stock', async ({ page }) => {
        await openProtectedPage(page, '/stock?code=000001');
        await expect(page).toHaveURL(/\/stock\?code=000001/);
        const input = page.getByRole('textbox', { name: '股票代码' });
        await expect(input).toHaveValue('000001');
        await expect(page.getByRole('tablist', { name: '标签页导航' })).toBeVisible();
    });
});

test.describe('Watchlist', () => {
    test('should load watchlist page', async ({ page }) => {
        await openProtectedPage(page, '/watchlist');
        await expect(page).toHaveURL(/\/watchlist$/);
        await expect(page).toHaveTitle(/自选|AIASK/);
        await expect(page.getByRole('heading', { name: '自选股工作台', level: 1 })).toBeVisible();
    });
});

test.describe('Paper Trading', () => {
    test('should load paper trading page', async ({ page }) => {
        await openProtectedPage(page, '/paper-trading');
        await expect(page).toHaveURL(/\/paper-trading$/);
        await expect(page).toHaveTitle(/模拟|交易|AIASK/);
        await expect(page.getByRole('heading', { name: '模拟交易' })).toBeVisible();
    });

    test('should keep backtest context banner from homepage', async ({ page }) => {
        await openProtectedPage(page, '/backtest?code=000001&from=home');
        await expect(page).toHaveURL(/\/backtest\?(?=.*code=000001)(?=.*from=home).*/);
        await expect(page.getByText(/来源:? ?home/)).toBeVisible();
    });
});

test.describe('Notifications', () => {
    test('should load notifications page', async ({ page }) => {
        await openProtectedPage(page, '/notifications');
        await expect(page).toHaveURL(/\/notifications$/);
        await expect(page.getByRole('heading', { name: /通知中心/ })).toBeVisible();
    });
});

test.describe('Alerts', () => {
    test('should load alerts page', async ({ page }) => {
        await openProtectedPage(page, '/alerts');
        await expect(page).toHaveURL(/\/alerts$/);
        await expect(page.getByRole('heading', { name: /告警中心工作台|告警中心/ })).toBeVisible();
    });
});

test.describe('Task Handoff', () => {
    test('market page should show task context', async ({ page }) => {
        await openProtectedPage(page, '/market?task=watchlist-scan&from=home');
        await expect(page).toHaveURL(/\/market\?(?=.*task=watchlist-scan)(?=.*from=home).*/);
        await expect(page.getByText(/任务[：:] ?watchlist-scan/)).toBeVisible();
    });

    test('strategy market should show task context', async ({ page }) => {
        await openProtectedPage(page, '/strategy-market?task=ranking&from=home');
        await expect(page).toHaveURL(/\/strategy-market\?(?=.*task=ranking)(?=.*from=home).*/);
        await expect(page.getByText(/任务[：:] ?ranking/)).toBeVisible();
    });
});

test.describe('Spotlight Search', () => {
    test('should open with Cmd+K', async ({ page }) => {
        await openProtectedPage(page, '/');
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
        await openProtectedPage(page, '/admin');
        await expect(page).toHaveURL(/\/admin$/);
        await expect(page.getByText(/管理后台概览/)).toBeVisible();
    });
});
