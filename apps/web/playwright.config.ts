import { defineConfig, devices } from '@playwright/test';

const E2E_PORT = Number(process.env.E2E_PORT || 3100);
const E2E_BASE_URL = process.env.E2E_BASE_URL || `http://127.0.0.1:${E2E_PORT}`;
const BFF_PORT = Number(process.env.BFF_PORT || 3001);
const BFF_BASE_URL = `http://127.0.0.1:${BFF_PORT}/api`;

/**
 * T-044: Playwright E2E Test Configuration
 */
export default defineConfig({
    testDir: './e2e',
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : undefined,
    reporter: process.env.CI ? 'github' : 'html',

    use: {
        baseURL: E2E_BASE_URL,
        trace: 'on-first-retry',
        screenshot: 'only-on-failure',
    },

    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
        {
            name: 'webkit',
            use: { ...devices['Desktop Safari'] },
        },
        {
            name: 'mobile',
            use: { ...devices['iPhone 14'] },
        },
    ],

    webServer: process.env.CI ? undefined : [
        {
            command: 'npm run dev',
            cwd: '../bff',
            url: `${BFF_BASE_URL}/health`,
            reuseExistingServer: false,
            timeout: 120_000,
            env: {
                ...process.env,
                BFF_PORT: String(BFF_PORT),
                CORS_ORIGIN: `http://127.0.0.1:${E2E_PORT},http://localhost:${E2E_PORT}`,
                DATABASE_POOL_MAX: process.env.DATABASE_POOL_MAX || '4',
                MCP_POOL_SIZE: process.env.MCP_POOL_SIZE || '2',
                MCP_STDIO_STARTUP_PROFILE: process.env.MCP_STDIO_STARTUP_PROFILE || 'tool-only',
                AKSHARE_MCP_DB_POOL_MIN: process.env.AKSHARE_MCP_DB_POOL_MIN || '1',
                AKSHARE_MCP_DB_POOL_MAX: process.env.AKSHARE_MCP_DB_POOL_MAX || '2',
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
            },
        },
    ],
});
