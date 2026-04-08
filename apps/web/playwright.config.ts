import { defineConfig, devices } from '@playwright/test';

const E2E_PORT = Number(process.env.E2E_PORT || 3100);
const E2E_BASE_URL = process.env.E2E_BASE_URL || `http://127.0.0.1:${E2E_PORT}`;
const BFF_PORT = Number(process.env.BFF_PORT || 3001);
const BFF_BASE_URL = `http://127.0.0.1:${BFF_PORT}/api`;
const ARTIFACTS_ROOT = '../../.playwright/apps-web';
const USE_EXTERNAL_SERVERS = process.env.PW_NO_WEBSERVER === '1';

/**
 * T-044: Playwright E2E Test Configuration
 */
export default defineConfig({
    testDir: './e2e',
    outputDir: `${ARTIFACTS_ROOT}/test-results`,
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : undefined,
    reporter: process.env.CI
        ? 'github'
        : [['html', { open: 'never', outputFolder: `${ARTIFACTS_ROOT}/playwright-report` }]],

    use: {
        baseURL: E2E_BASE_URL,
        trace: 'on-first-retry',
        screenshot: 'only-on-failure',
    },

    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
            testIgnore: /sitewide-pages\.spec\.ts/,
        },
        {
            name: 'chromium-sitewide',
            use: { ...devices['Desktop Chrome'] },
            testMatch: /sitewide-pages\.spec\.ts/,
        },
        {
            name: 'webkit',
            use: { ...devices['Desktop Safari'] },
            testIgnore: /sitewide-pages\.spec\.ts/,
        },
        {
            name: 'webkit-sitewide',
            use: { ...devices['Desktop Safari'] },
            testMatch: /sitewide-pages\.spec\.ts/,
        },
        {
            name: 'mobile',
            use: { ...devices['iPhone 14'] },
            testIgnore: /sitewide-pages\.spec\.ts/,
        },
        {
            name: 'mobile-sitewide',
            use: { ...devices['iPhone 14'] },
            testMatch: /sitewide-pages\.spec\.ts/,
        },
    ],

    webServer: USE_EXTERNAL_SERVERS
        ? undefined
        : [
            {
                command: 'npm run dev',
                cwd: '../bff',
                url: `${BFF_BASE_URL}/health/ready`,
                reuseExistingServer: false,
                timeout: 120_000,
                env: {
                    ...process.env,
                    BFF_PORT: String(BFF_PORT),
                    DATABASE_URL: process.env.E2E_DATABASE_URL || '',
                    CORS_ORIGIN: `http://127.0.0.1:${E2E_PORT},http://localhost:${E2E_PORT}`,
                    DATABASE_POOL_MAX: process.env.DATABASE_POOL_MAX || '2',
                    MCP_POOL_SIZE: process.env.MCP_POOL_SIZE || '4',
                    MCP_POOL_ACQUIRE_TIMEOUT_MS: process.env.MCP_POOL_ACQUIRE_TIMEOUT_MS || '15000',
                    MCP_STDIO_STARTUP_PROFILE: process.env.MCP_STDIO_STARTUP_PROFILE || 'tool-only',
                    MCP_HEALTH_CACHE_TTL_MS: process.env.MCP_HEALTH_CACHE_TTL_MS || '15000',
                    AKSHARE_MCP_DB_POOL_MIN: process.env.AKSHARE_MCP_DB_POOL_MIN || '1',
                    AKSHARE_MCP_DB_POOL_MAX: process.env.AKSHARE_MCP_DB_POOL_MAX || '2',
                    AKSHARE_MCP_SCHEMA_LOCK_KEY: process.env.AKSHARE_MCP_SCHEMA_LOCK_KEY || '84217051',
                    MARKET_SCHEDULER_ENABLED: process.env.MARKET_SCHEDULER_ENABLED || 'false',
                    STRATEGY_MARKET_AUTO_REFRESH_ENABLED: process.env.STRATEGY_MARKET_AUTO_REFRESH_ENABLED || 'false',
                    APP_ENABLE_DEMO_USER: process.env.APP_ENABLE_DEMO_USER || 'true',
                    APP_ADMIN_PASSWORD: process.env.APP_ADMIN_PASSWORD || 'admin',
                    APP_DEMO_PASSWORD: process.env.APP_DEMO_PASSWORD || 'demo123',
                    APP_JWT_SECRET: process.env.APP_JWT_SECRET || 'dev-secret-change-me',
                },
            },
            {
                command: `npx next dev -p ${E2E_PORT}`,
                url: E2E_BASE_URL,
                reuseExistingServer: false,
                timeout: 120_000,
                env: {
                    ...process.env,
                    NEXT_PUBLIC_BFF_BASE_URL: BFF_BASE_URL,
                    NEXT_PUBLIC_WS_URL: BFF_BASE_URL.replace(/\/api$/, ''),
                },
            },
        ],
});
