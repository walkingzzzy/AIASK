import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:3400';
const browser = process.env.E2E_BROWSER || 'chromium';
const defaultReportsRoot = path.join('..', '..', 'reports', 'realworld-e2e');
const outputDir = process.env.E2E_PLAYWRIGHT_OUTPUT_DIR || path.join(defaultReportsRoot, 'test-results');
const jsonOutput = process.env.E2E_PLAYWRIGHT_JSON || path.join(outputDir, 'report.json');
const htmlOutput = process.env.E2E_PLAYWRIGHT_HTML || path.join(defaultReportsRoot, 'html-report');

function projectForBrowser(name: string) {
  if (name === 'webkit') {
    return {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    };
  }
  if (name === 'mobile') {
    return {
      name: 'mobile',
      use: { ...devices['iPhone 14'] },
    };
  }
  return {
    name: 'chromium',
    use: { ...devices['Desktop Chrome'] },
  };
}

export default defineConfig({
  testDir: './e2e/realworld/specs',
  outputDir,
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: jsonOutput }],
    ['html', { open: 'never', outputFolder: htmlOutput }],
  ],
  use: {
    baseURL: baseUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [projectForBrowser(browser)],
});
