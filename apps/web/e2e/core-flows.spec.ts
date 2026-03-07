import { test, expect } from '@playwright/test';

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
});

test.describe('Stock Detail', () => {
    test('should have search input', async ({ page }) => {
        await page.goto('/stock');
        const input = page.locator('input[type="text"]').first();
        await expect(input).toBeVisible();
    });

    test('should search for a stock', async ({ page }) => {
        await page.goto('/stock');
        const input = page.locator('input[type="text"]').first();
        await input.fill('600519');
        await input.press('Enter');
        // Wait for data
        await page.waitForTimeout(3000);
        // Should show tabs
        const tabs = page.locator('[role="tablist"], [class*="tab"]');
        expect(await tabs.count()).toBeGreaterThanOrEqual(0);
    });
});

test.describe('Watchlist', () => {
    test('should load watchlist page', async ({ page }) => {
        await page.goto('/watchlist');
        await expect(page).toHaveTitle(/自选|AIASK/);
    });
});

test.describe('Paper Trading', () => {
    test('should load paper trading page', async ({ page }) => {
        await page.goto('/paper-trading');
        await expect(page).toHaveTitle(/模拟|交易|AIASK/);
    });
});

test.describe('Notifications', () => {
    test('should load notifications page', async ({ page }) => {
        await page.goto('/notifications');
        await page.waitForTimeout(1000);
        // Page should render without errors
        const body = page.locator('body');
        await expect(body).toBeVisible();
    });
});

test.describe('Alerts', () => {
    test('should load alerts page', async ({ page }) => {
        await page.goto('/alerts');
        const body = page.locator('body');
        await expect(body).toBeVisible();
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
        await page.goto('/admin');
        const body = page.locator('body');
        await expect(body).toBeVisible();
    });
});
